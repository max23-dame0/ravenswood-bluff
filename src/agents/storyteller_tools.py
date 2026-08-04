"""
说书人工具注册表 (StorytellerToolRegistry)

将说书人的裁量能力标准化为工具注册表（PLN-038 阶段 S）：

| 工具 | 现形态 | 目标形态 |
|---|---|---|
| `assess_balance` | `_evaluate_team_advantage` | 只读：返回平衡分值 / 风险标记 |
| `choose_distortion` | 散落 `_distort_fixed_info` / `_distort_storyteller_info` | 策略选择工具：`distortion_strategy` 枚举化 |
| `adjudicate_night_info` | `decide_night_info` | 裁决工具：真实信息确定性，扭曲可选 |
| `compose_narration` | `narrate_phase` | 报幕工具 |
| `deliver_verdict` | `record_judgement` | 记账工具 |
| `review_balance` | — | 记忆查询：复盘 + 平衡档案落盘 |

核心边界（硬约束 7/8/9）：
- 真实信息计算永远保持确定性（规则引擎）；
- LLM 只能影响"是否扭曲 + 扭曲成什么"的选择面（`BOTC_ST_LLM_STRATEGY`），启发式兜底；
- 每个 `choose_distortion` 均以 `distortion_strategy` 枚举写入 `decision_ledger`；
- 人类说书人模式（`mode=human`）完全不走 LLM 策略层。
"""

from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agents.storyteller_delegation import StorytellerDecisionContext
    from src.state.game_state import GameState

logger = logging.getLogger(__name__)


class DistortionStrategy(str, Enum):
    """扭曲策略枚举：所有可审计的扭曲策略名（保持与旧字符串值兼容）。

    每个值都是既有 `_distort_*` 返回的字符串，枚举化后 `distortion_strategy`
    字段值不变，保证既有测试与审计输出兼容。
    """

    NONE = "none"
    WASHERWOMAN_PAIR_ROLE_SEEN = "washerwoman_pair_role_seen_distortion"
    LIBRARIAN_PAIR_ROLE_SEEN = "librarian_pair_role_seen_distortion"
    INVESTIGATOR_PAIR_ROLE_SEEN = "investigator_pair_role_seen_distortion"
    CHEF_PAIRS_OFFSET_HELP_EVIL = "chef_pairs_offset.help_evil"
    CHEF_PAIRS_PASSTHROUGH = "chef_pairs_passthrough"
    EMPATH_BINARY_FLIP_HELP_EVIL = "empath_binary_flip.help_evil"
    EMPATH_MERCY_TRUTH_HELP_GOOD = "empath_mercy_truth.help_good"
    EMPATH_BINARY_FLIP_DEFAULT = "empath_binary_flip.default"
    UNDERTAKER_RANDOM_ROLE_SEEN = "undertaker_random_role_seen"
    SPY_BOOK_SINGLE_ENTRY = "spy_book_single_entry_distortion"
    FIXED_INFO_PASSTHROUGH = "fixed_info_passthrough"
    FORTUNE_TELLER_MISLEAD_HELP_EVIL = "fortune_teller_mislead.help_evil"
    FORTUNE_TELLER_TRUTH_HELP_GOOD = "fortune_teller_truth.help_good"
    FORTUNE_TELLER_BOOLEAN_FLIP = "fortune_teller_boolean_flip"
    RAVENKEEPER_TRUTH_HELP_GOOD = "ravenkeeper_truth.help_good"
    RAVENKEEPER_RANDOM_ROLE = "ravenkeeper_random_role_distortion"
    STORYTELLER_INFO_PASSTHROUGH = "storyteller_info_passthrough"
    UNSPECIFIED_SUPPRESSION = "unspecified_suppression_passthrough"

    @classmethod
    def coerce(cls, value: str | None) -> DistortionStrategy:
        """将任意字符串收敛为枚举；无法识别时视为 NONE。"""
        if not value:
            return cls.NONE
        for member in cls:
            if member.value == value:
                return member
        return cls.NONE


def _llm_strategy_switch() -> str:
    """`BOTC_ST_LLM_STRATEGY=off|low|on`，默认 off（保证行为与重构前一致）。"""
    return os.getenv("BOTC_ST_LLM_STRATEGY", "off").strip().lower()


class StorytellerToolRegistry:
    """说书人工具注册表：6 个工具的注册与统一入口。

    通过类方法暴露；实际实现委托给传入的 storyteller 实例（保持单一实例状态，
    如 `decision_ledger` 与 `backend` 都在 StorytellerAgent 上）。
    """

    TOOL_NAMES = (
        "assess_balance",
        "choose_distortion",
        "adjudicate_night_info",
        "compose_narration",
        "deliver_verdict",
        "review_balance",
    )

    # ------------------------------------------------------------------
    # 1. assess_balance — 只读平衡评估
    # ------------------------------------------------------------------

    @staticmethod
    def assess_balance(st, context: StorytellerDecisionContext) -> dict[str, Any]:
        """只读工具：返回平衡分值 + 风险标记。

        正值代表正义阵营优势，负值代表邪恶阵营优势。
        """
        score = st._evaluate_team_advantage(context)
        balance = context.balance_context or {}
        return {
            "score": round(score, 3),
            "verdict": (
                "good_advantage"
                if score > 0.5
                else ("evil_advantage" if score < -0.5 else "balanced")
            ),
            "alive_good": balance.get("alive_good", 0),
            "alive_evil": balance.get("alive_evil", 0),
            "day_number": balance.get("day_number", 1),
            "hard_lock_risk": bool(balance.get("hard_lock_risk", False)),
            "early_end_risk": bool(balance.get("early_end_risk", False)),
        }

    # ------------------------------------------------------------------
    # 2. choose_distortion — 策略选择工具（枚举化 + LLM 可选 + 启发式兜底）
    # ------------------------------------------------------------------

    @staticmethod
    def choose_distortion(
        st,
        context: StorytellerDecisionContext,
        role_id: str,
        info: dict[str, Any],
        player_id: str,
    ) -> tuple[dict[str, Any], DistortionStrategy]:
        """选择扭曲策略并产出扭曲后的信息（同步启发式版）。

        返回 `(distorted_info, strategy)`：
        - 策略选择收敛为 `distortion_strategy` 枚举；
        - 仅启发式选择（保证可同步调用，与重构前行为一致）；
        - 真实信息计算（`info` 真值）不在此修改。
        """
        # 启发式兜底 = 现有 _distort_* 行为（保证重构前后一致）
        distorted, strategy_name = (
            st._distort_fixed_info(context, role_id, info, player_id)
            if st._is_fixed_info_role(role_id)
            else st._distort_storyteller_info(context, role_id, info)
        )
        strategy = DistortionStrategy.coerce(strategy_name)
        return distorted, strategy

    @staticmethod
    async def choose_distortion_async(
        st,
        context: StorytellerDecisionContext,
        role_id: str,
        info: dict[str, Any],
        player_id: str,
    ) -> tuple[dict[str, Any], DistortionStrategy]:
        """选择扭曲策略（异步版）：LLM 可选介入选择面，启发式兜底。"""
        distorted, strategy = StorytellerToolRegistry.choose_distortion(
            st, context, role_id, info, player_id
        )
        switch = _llm_strategy_switch()
        if switch in {"low", "on"} and st.mode != "human" and getattr(st, "backend", None):
            chosen = await StorytellerToolRegistry._llm_choose_strategy(
                st, context, role_id, strategy, info
            )
            if chosen is not None:
                # LLM 只选策略，扭曲信息仍由确定性 _distort_* 产出
                distorted, strategy_name = (
                    st._distort_fixed_info(context, role_id, info, player_id)
                    if st._is_fixed_info_role(role_id)
                    else st._distort_storyteller_info(context, role_id, info)
                )
                strategy_name = f"st_llm:{chosen.value}"
                strategy = DistortionStrategy.coerce(strategy_name)
        return distorted, strategy

    @staticmethod
    async def _llm_choose_strategy(
        st,
        context: StorytellerDecisionContext,
        role_id: str,
        current: DistortionStrategy,
        info: dict[str, Any],
    ) -> DistortionStrategy | None:
        """LLM 从合法策略集中选择扭曲策略（只读选择，不产私密信息）。"""
        try:
            from src.llm.base_backend import Message

            balance = StorytellerToolRegistry.assess_balance(st, context)
            options = [
                member.value
                for member in DistortionStrategy
                if member is not DistortionStrategy.NONE
            ]
            prompt = (
                f"你是《血染钟楼》说书人，负责维持对局平衡。\n"
                f"当前平衡：score={balance['score']} verdict={balance['verdict']} "
                f"hard_lock={balance['hard_lock_risk']}\n"
                f"角色 {role_id} 能力被抑制，需选择扭曲策略。可选策略（枚举值）：\n"
                f"{', '.join(options)}\n"
                f"默认启发式已选：{current.value}\n"
                "请仅返回一个策略枚举值（不要解释），权衡：若好人优势过大选帮助邪恶的策略，"
                "若邪恶优势过大选帮助好人的策略。"
            )
            response = await st.backend.generate(
                prompt,
                [Message(role="user", content="请返回一个 distortion_strategy 枚举值。")],
                max_tokens=50,
                thinking="disabled",
            )
            text = (response.content or "").strip()
            if not text:
                return None
            candidate = text.split()[-1].strip().strip('"').strip("'").strip("，。")
            # 兼容 "st_llm:" 前缀与直接枚举值
            candidate = candidate.replace("st_llm:", "")
            member = DistortionStrategy.coerce(candidate)
            return None if member is DistortionStrategy.NONE else member
        except Exception as exc:
            logger.debug("[choose_distortion] LLM 策略选择失败，回退启发式: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 3-6. 其余工具：委托到 storyteller 实例（保持行为一致）
    # ------------------------------------------------------------------

    @staticmethod
    async def adjudicate_night_info(
        st, game_state: GameState, player_id: str, role_id: str
    ) -> dict[str, Any]:
        return await st.decide_night_info(game_state, player_id, role_id)

    @staticmethod
    async def compose_narration(st, game_state: GameState) -> str:
        return await st.narrate_phase(game_state)

    @staticmethod
    def deliver_verdict(
        st, category: str, decision: str, reason: str | None = None, **fields: Any
    ) -> dict[str, Any]:
        return st.record_judgement(category, decision, reason, **fields)

    @staticmethod
    def review_balance(st, game_id: str) -> dict[str, Any]:
        """记忆查询：基于判决账本 + 对局平衡档案复盘。

        只读账本 + 写平衡档案（`data/storyteller/{game_id}/`），不触碰 GameState。
        """
        ledger = st.export_judgements()
        stats = st.export_judgement_history(game_id, limit=None)
        summary = {
            "game_id": game_id,
            "judgement_count": stats.get("judgement_count", len(ledger)),
            "statistics": stats.get("statistics", {}),
            "distortion_entries": [
                {
                    "category": e.get("category"),
                    "decision": e.get("decision"),
                    "distortion_strategy": e.get("distortion_strategy"),
                    "reason": e.get("reason"),
                }
                for e in ledger
                if e.get("distortion_strategy") not in {None, "none"}
            ],
            "balance_notes": [],
        }
        # 简单复盘规则：过度扭曲告警
        night_info_total = stats.get("statistics", {}).get("night_info_total", 0) or 0
        distorted = len(summary["distortion_entries"])
        if night_info_total and distorted / max(1, night_info_total) > 0.6:
            summary["balance_notes"].append(
                "⚠️ 扭曲率过高（>60%），建议减少 LLM 策略介入或放宽平衡约束。"
            )
        if stats.get("statistics", {}).get("hard_lock_risk"):
            summary["balance_notes"].append("⚠️ 存在 hard_lock 风险，应优先帮助劣势方。")
        return summary

    @staticmethod
    def save_balance_archive(st, game_id: str, summary: dict[str, Any]) -> Path:
        """将对局平衡档案落盘 `data/storyteller/{game_id}/`。"""
        base = Path(os.getenv("BOTC_DATA_DIR", "data")) / "storyteller" / game_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / "balance_archive.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        return path


class StorytellerProfileStore:
    """说书人跨局档案库（PLN-038 阶段 E：说书人进化机制）。

    对局隔离：单局裁决落盘 `data/storyteller/{game_id}/`（已实现）；
    跨局档案：`data/storyteller/profile/` 记录说书人的长期风格与平衡倾向，
    供其跨局"成长"——例如默认扭曲率、平衡判断偏好随经验调整。
    """

    def __init__(self, storyteller_id: str = "storyteller") -> None:
        self.storyteller_id = storyteller_id
        self._base = Path(os.getenv("BOTC_DATA_DIR", "data")) / "storyteller" / "profile"
        self._profile_path = self._base / "storyteller_profile.json"
        self._long_term_path = self._base / "long_term_memory.jsonl"

    def load_profile(self) -> dict[str, Any]:
        profile = {
            "storyteller_id": self.storyteller_id,
            "games_conducted": 0,
            "distortion_events": 0,
            "total_judgements": 0,
            "distortion_rate": 0.0,
            "notes": [],
        }
        if self._profile_path.exists():
            try:
                saved = json.loads(self._profile_path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    profile.update({k: v for k, v in saved.items() if k in profile})
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("[storyteller-profile] 加载档案失败: %s", exc)
        return profile

    def record_game_summary(
        self,
        *,
        game_id: str,
        judgement_count: int,
        distortion_events: int,
        lesson: str = "",
    ) -> dict[str, Any]:
        """局末记录：更新说书人跨局档案 + 追加长期经验。"""
        profile = self.load_profile()
        profile["games_conducted"] += 1
        profile["total_judgements"] += judgement_count
        profile["distortion_events"] += distortion_events
        total = max(1, profile["total_judgements"])
        profile["distortion_rate"] = round(profile["distortion_events"] / total, 3)
        self._base.mkdir(parents=True, exist_ok=True)
        self._profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        if lesson:
            record = {
                "ts": time.time(),
                "game_id": game_id,
                "lesson": lesson[:200],
            }
            with open(self._long_term_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return profile

    def build_long_term_summary(self, limit: int = 6) -> str:
        """生成说书人跨局经验摘要（供注入 / 复盘）。"""
        profile = self.load_profile()
        parts: list[str] = []
        if profile["games_conducted"]:
            parts.append(
                f"你已主持 {profile['games_conducted']} 局，累计裁决 {profile['total_judgements']} 次，"
                f"扭曲率 {profile['distortion_rate']:.0%}。"
            )
        lessons: list[str] = []
        if self._long_term_path.exists():
            try:
                with open(self._long_term_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            lessons.append(json.loads(line).get("lesson", ""))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass
        if lessons:
            parts.append(
                "【你以往的主持经验】\n" + "\n".join(f"- {x[:120]}" for x in lessons[-limit:] if x)
            )
        return "\n".join(parts)
