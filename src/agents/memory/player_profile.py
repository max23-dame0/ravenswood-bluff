"""
玩家跨局档案与长期记忆库 (PlayerProfileStore)

PLN-038 阶段 E：让每个 AI 玩家拥有"个人玩家视角"的长期记忆，实现玩家进化机制。

目录结构（对局隔离 + 跨局档案分离）：

    data/agents/{player_id}/
        profile/
            profile.json            # 跨局玩家画像（胜负统计 / 角色 / 团队表现 / 战术倾向）
            long_term_memory.jsonl  # 跨局经验教训（每局结束后提炼追加）
            reflections.jsonl       # 局中反思沉淀（策略层面的即时经验）
            strategies.jsonl        # 进化策略（调整行动倾向，随经验增长而演进）
            lessons_learned.jsonl   # 向他人学习的经验（观察强势玩家打法）
            game_reviews.jsonl      # 局后复盘（每局结束时的多维总结）
        games/{game_id}/
            memory.jsonl            # 单局记忆工具落盘（MemoryTools，对局隔离）

进化解耦点：
- `MemoryTools`（本局记忆）写入 `games/{game_id}/`，只属于当前对局；
- `PlayerProfileStore`（跨局档案）独立持久化，与对局无关；
- 每局结束 `finalize_game_review()` 提炼多维复盘（局后复盘）；
- 局中 `add_reflection()` 沉淀即时经验（局中反思）；
- `learn_from_others()` 观察强势玩家打法（学习他人经验）；
- `evolve_strategies()` 基于战绩/经验调整行动倾向（调整策略）；
- 新局开始 `build_long_term_summary()` 将既往经验与进化策略注入 system prompt（进化）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


class PlayerProfileStore:
    """玩家跨局档案库：读画像、记战绩、追加/读取长期经验、进化策略。"""

    def __init__(self, player_id: str, player_name: str = "") -> None:
        self.player_id = player_id
        self.player_name = player_name
        self._profile_dir = _data_root() / "agents" / player_id / "profile"
        self._profile_path = self._profile_dir / "profile.json"
        self._long_term_path = self._profile_dir / "long_term_memory.jsonl"
        self._reflections_path = self._profile_dir / "reflections.jsonl"
        self._strategies_path = self._profile_dir / "strategies.jsonl"
        self._lessons_learned_path = self._profile_dir / "lessons_learned.jsonl"
        self._game_reviews_path = self._profile_dir / "game_reviews.jsonl"
        self._profile: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------

    @property
    def profile_dir(self) -> Path:
        return self._profile_dir

    @staticmethod
    def game_dir(player_id: str, game_id: str) -> Path:
        """对局隔离目录：data/agents/{player_id}/games/{game_id}/。"""
        return _data_root() / "agents" / player_id / "games" / str(game_id)

    # ------------------------------------------------------------------
    # 玩家画像
    # ------------------------------------------------------------------

    def load_profile(self) -> dict[str, Any]:
        """加载玩家画像（不存在时初始化默认画像）。"""
        if self._profile is not None:
            return self._profile
        profile = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "team_stats": {},  # {"good": {"played": n, "wins": m}, "evil": {...}}
            "role_stats": {},  # {role_id: {"played": n, "wins": m}}
            # 拟人化进化状态（随经验增长动态调整）
            "tendency": {  # 行动倾向（调整策略的落点）
                "aggression": 0.5,  # 攻击性：0-1，越高越爱强攻/施压
                "risk_taking": 0.5,  # 冒险性：0-1，越高越敢冒险
                "talkativeness": 0.5,  # 健谈度：0-1，越高发言越积极
                "caution": 0.5,  # 谨慎度：0-1，越高越保留信息
            },
            "evolution": {
                "reflections_done": 0,  # 局中反思次数
                "lessons_learned": 0,  # 向他人学习次数
                "reviews_done": 0,  # 局后复盘次数
                "strategy_adjustments": 0,  # 策略调整次数
            },
            "last_updated": None,
        }
        if self._profile_path.exists():
            try:
                saved = json.loads(self._profile_path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    profile.update({k: v for k, v in saved.items() if k in profile})
                    # 嵌套字段兼容合并
                    if isinstance(saved.get("tendency"), dict):
                        profile["tendency"].update(saved["tendency"])
                    if isinstance(saved.get("evolution"), dict):
                        profile["evolution"].update(saved["evolution"])
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("[profile:%s] 加载玩家画像失败，使用默认: %s", self.player_id, exc)
        self._profile = profile
        return profile

    def save_profile(self) -> None:
        """保存玩家画像。"""
        profile = self.load_profile()
        profile["last_updated"] = time.time()
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    def record_game_result(
        self, *, won: bool, role_id: str | None, team: str | None
    ) -> dict[str, Any]:
        """记录一局结果，更新战绩统计（玩家进化依据）。"""
        profile = self.load_profile()
        profile["games_played"] += 1
        if won:
            profile["wins"] += 1
        else:
            profile["losses"] += 1

        team_key = (team or "unknown").lower()
        if team_key not in profile["team_stats"]:
            profile["team_stats"][team_key] = {"played": 0, "wins": 0}
        profile["team_stats"][team_key]["played"] += 1
        if won:
            profile["team_stats"][team_key]["wins"] += 1

        if role_id:
            if role_id not in profile["role_stats"]:
                profile["role_stats"][role_id] = {"played": 0, "wins": 0}
            profile["role_stats"][role_id]["played"] += 1
            if won:
                profile["role_stats"][role_id]["wins"] += 1

        self.save_profile()
        return profile

    # ------------------------------------------------------------------
    # 1. 局中反思（reflections）
    # ------------------------------------------------------------------

    def add_reflection(self, entry: dict[str, Any]) -> Path:
        """沉淀一条局中反思（策略层面的即时经验，非私密信息）。

        人类玩家会在对局进行中不断自我校正，把"刚才那个决定做得对不对"
        沉淀下来，作为本局后续与未来对局的行动依据。
        """
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), **entry}
        with open(self._reflections_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        profile = self.load_profile()
        profile["evolution"]["reflections_done"] += 1
        self.save_profile()
        return self._reflections_path

    def read_reflections(self, limit: int = 10) -> list[dict[str, Any]]:
        """读取最近的局中反思（最新的在前）。"""
        return self._read_jsonl(self._reflections_path, limit)

    # ------------------------------------------------------------------
    # 2. 局后复盘（game_reviews）
    # ------------------------------------------------------------------

    def add_game_review(self, entry: dict[str, Any]) -> Path:
        """沉淀一份局后复盘（局末多维总结）。

        拟人化关键：人类玩家赢/输后都会复盘，总结"赢在哪/败在哪/
        下次怎么调整"，这是水平增长最主要的来源。
        """
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), **entry}
        with open(self._game_reviews_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        profile = self.load_profile()
        profile["evolution"]["reviews_done"] += 1
        self.save_profile()
        return self._game_reviews_path

    def read_game_reviews(self, limit: int = 10) -> list[dict[str, Any]]:
        """读取最近的局后复盘（最新的在前）。"""
        return self._read_jsonl(self._game_reviews_path, limit)

    # ------------------------------------------------------------------
    # 3. 学习他人经验（lessons_learned）
    # ------------------------------------------------------------------

    def learn_from_others(self, entry: dict[str, Any]) -> Path:
        """记录一条从他人（强势玩家）打法中学到的经验。

        拟人化关键：新手玩家会观察高手的战术并模仿。这里沉淀
        "某个角色/阵营的打法思路"，作为进化输入。
        """
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), **entry}
        with open(self._lessons_learned_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        profile = self.load_profile()
        profile["evolution"]["lessons_learned"] += 1
        self.save_profile()
        return self._lessons_learned_path

    def read_lessons_learned(self, limit: int = 10) -> list[dict[str, Any]]:
        """读取最近学到的他人经验（最新的在前）。"""
        return self._read_jsonl(self._lessons_learned_path, limit)

    # ------------------------------------------------------------------
    # 4. 调整策略（strategies）
    # ------------------------------------------------------------------

    def evolve_strategies(self, entry: dict[str, Any]) -> dict[str, Any]:
        """基于战绩/经验调整行动倾向（进化策略）。

        拟人化关键：随着对局增多，玩家会形成"我是更激进还是更谨慎的玩家"
        的自我认知，并据此调整后续打法。此方法把战绩反馈映射为倾向微调，
        并落盘一条策略记录。
        """
        profile = self.load_profile()
        tendency = profile["tendency"]
        # 基于胜率反馈微调倾向（delta 建议 -0.05 ~ 0.05）
        deltas = entry.get("tendency_delta") or {}
        for key, delta in deltas.items():
            if key in tendency:
                new_val = max(0.05, min(0.95, tendency[key] + delta))
                tendency[key] = round(new_val, 3)
        profile["evolution"]["strategy_adjustments"] += 1
        self.save_profile()

        record = {
            "ts": time.time(),
            "game_id": entry.get("game_id", ""),
            "won": entry.get("won"),
            "reason": entry.get("reason", ""),
            "tendency_delta": deltas,
            "tendency_after": dict(tendency),
        }
        with open(self._strategies_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return profile

    def read_strategies(self, limit: int = 8) -> list[dict[str, Any]]:
        """读取最近的策略调整记录（最新的在前）。"""
        return self._read_jsonl(self._strategies_path, limit)

    def build_evolved_tendency_summary(self) -> str:
        """生成当前进化后的行动倾向描述（调整策略的可注入结果）。

        PLN-040 T3：从"4 档标签"升级为连续画像文案（0~1 值直接描述），
        使不同 tendency 的玩家注入文案可感知差异化（配合行为标签覆盖）。
        """
        profile = self.load_profile()
        t = profile["tendency"]
        labels: list[str] = []

        def _level(value: float) -> str:
            if value >= 0.65:
                return "偏强"
            if value >= 0.55:
                return "略强"
            if value <= 0.35:
                return "偏弱"
            if value <= 0.45:
                return "略弱"
            return "中等"

        labels.append(
            f"攻击性{_level(t['aggression'])}"
            + ("（主动施压、抢占节奏）" if t["aggression"] >= 0.6 else "")
        )
        labels.append(
            f"冒险度{_level(t['risk_taking'])}"
            + ("（敢冒险换收益）" if t["risk_taking"] >= 0.6 else "")
        )
        labels.append(
            f"健谈度{_level(t['talkativeness'])}"
            + ("（乐于发言带动讨论）" if t["talkativeness"] >= 0.6 else "")
        )
        labels.append(
            f"谨慎度{_level(t['caution'])}" + ("（保护关键信息）" if t["caution"] >= 0.6 else "")
        )
        return "你的打法倾向：" + "；".join(labels)

    # ------------------------------------------------------------------
    # 长期经验教训（保留原有能力）
    # ------------------------------------------------------------------

    def append_lesson(self, entry: dict[str, Any]) -> Path:
        """追加一条跨局经验教训到长期记忆。"""
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), **entry}
        with open(self._long_term_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return self._long_term_path

    def read_lessons(self, limit: int = 12) -> list[dict[str, Any]]:
        """读取最近的经验教训（最新的在前）。"""
        return self._read_jsonl(self._long_term_path, limit)

    def build_long_term_summary(self, limit: int = 6) -> str:
        """生成供 system prompt 注入的『过往游戏经验』摘要（玩家进化）。

        拟人化增强：综合战绩 + 局后复盘要点 + 学习到的他人经验 + 进化倾向。
        仅选取结构化、可复用、非敏感内容，保证信息隔离。
        """
        profile = self.load_profile()
        parts: list[str] = []

        # 战绩
        if profile.get("games_played"):
            win_rate = (
                round(profile["wins"] / max(1, profile["games_played"]) * 100)
                if profile["games_played"]
                else 0
            )
            parts.append(
                f"你共打过 {profile['games_played']} 局，胜率约 {win_rate}%"
                f"（{profile['wins']} 胜 / {profile['losses']} 负）。"
            )
            team_stats = profile.get("team_stats", {})
            if team_stats:
                parts.append(
                    "阵营战绩："
                    + "；".join(f"{k}={v['wins']}/{v['played']}" for k, v in team_stats.items())
                )

        # 进化倾向
        tendency = self.build_evolved_tendency_summary()
        if tendency:
            parts.append(tendency)

        # 局后复盘要点（取最近 2 条的关键收获）
        reviews = self.read_game_reviews(2)
        if reviews:
            review_lines = []
            for rev in reviews:
                takeaway = str(rev.get("takeaway", "")).strip()
                if takeaway and not MemoryToolsLike.is_sensitive(takeaway):
                    review_lines.append(f"- 上一局收获：{takeaway[:90]}")
            if review_lines:
                parts.append("【你最近的局后复盘】\n" + "\n".join(review_lines))

        # 学习到的他人经验（取最近 3 条）
        learned = self.read_lessons_learned(3)
        if learned:
            learn_lines = []
            for item in learned:
                text = str(item.get("lesson", "")).strip()
                if text and not MemoryToolsLike.is_sensitive(text):
                    learn_lines.append(f"- 学到的打法：{text[:90]}")
            if learn_lines:
                parts.append("【你从优秀玩家身上学到的打法】\n" + "\n".join(learn_lines))

        # 经验教训
        lessons = self.read_lessons(limit)
        if lessons:
            lines = []
            for lesson in lessons:
                text = str(lesson.get("lesson", "")).strip()
                if not text or MemoryToolsLike.is_sensitive(text):
                    continue
                lines.append(f"- {text[:120]}")
            if lines:
                parts.append("【你以往的经验教训】\n" + "\n".join(lines))

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _read_jsonl(self, path: Path, limit: int) -> list[dict[str, Any]]:
        """读取 JSONL 文件的最新 limit 条（最新的在前）。"""
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return list(reversed(items[-limit:]))


class MemoryToolsLike:
    """轻量敏感词校验（避免与 tools.memory_tools 循环依赖）。"""

    _SENSITIVE_MARKERS = (
        "邪恶队友",
        "恶魔",
        "我是恶魔",
        "队友名单",
        "private_info",
        "TEAM_EVIL",
    )

    @staticmethod
    def is_sensitive(text: str) -> bool:
        return any(marker in (text or "") for marker in MemoryToolsLike._SENSITIVE_MARKERS)
