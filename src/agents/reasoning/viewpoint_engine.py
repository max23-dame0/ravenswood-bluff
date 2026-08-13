"""证据提取与置信度引擎 (ViewpointEngine) — PLN-042 T2。

从 agent 的工作记忆/既有证据候选中提取 **hard（硬证据）/ soft（软印象）**
证据，计算观点置信度，并支持观点演化（新证据更新 / 冲突废弃）。

证据分级（防"软印象当硬证据"的推理幻觉核心）：
- **hard**：说书人信息（fortune_teller_info / investigator_info / empath_info /
  chef_info / revealed_role / demon_candidate / evil_teammates / role_candidate_hint）；
- **soft**：公开角色声明 / 他人发言观感 / 观察与印象。

置信度公式（确定性，LLM 不参与数值计算——守住确定性红线）：
    base = 0.35 + 0.15 * hard + 0.06 * soft   （线性累计）
    conf = min(0.95, base + min(0.1, hard * 0.02))

门控语义（P1-2 修复后）：`passes_gate` 要求 **hard_count >= 1**（必须有硬证据
支撑才可公开断言）；纯软印象观点即使置信度数值达标也一律拦截。单条硬证据
置信度 ≈ 0.52（0.35+0.15+0.02），两条 ≈ 0.69，随证据量递增封顶 0.95。
MIN_GATE_CONFIDENCE 保留为"软印象观点置信度参考阈值"（0.35+0.06*2=0.47 即
≥2 条软印象时会越过此数值，故门控不再依赖该数值，改由 hard_count 判定）。
"""

from __future__ import annotations

from src.agents.reasoning.viewpoint import Evidence, Viewpoint

# 门控阈值：仅硬证据可达到（纯软印象 0.35+0.06=0.41 < 0.45）
MIN_GATE_CONFIDENCE = 0.45
# 置信度封顶
MAX_CONFIDENCE = 0.95
# 冲突判定：新证据与既有观点置信度差异超过此值时触发 supersede
CONFLICT_BAY = 0.2

# 硬证据来源分类（与 decision_engine 高可信信息分类对齐）
HARD_SOURCES = {
    "fortune_teller_info",
    "investigator_info",
    "empath_info",
    "chef_info",
    "revealed_role",
    "demon_candidate",
    "evil_teammates",
    "role_candidate_hint",
}


def classify_evidence(source: str) -> str:
    """按来源分类证据：hard / soft。"""
    return "hard" if source in HARD_SOURCES else "soft"


def compute_confidence(hard_count: int, soft_count: int) -> float:
    """确定性置信度：硬证据高权重、软证据低权重、封顶 0.95。"""
    base = 0.35 + 0.15 * hard_count + 0.06 * soft_count
    bonus = min(0.1, hard_count * 0.02)
    return round(min(MAX_CONFIDENCE, base + bonus), 3)


class ViewpointEngine:
    """证据提取 + 观点构建 + 演化。"""

    # ------------------------------------------------------------------
    # 证据提取
    # ------------------------------------------------------------------

    def extract_evidence(self, memory: dict[str, list[str]]) -> list[Evidence]:
        """从分类好的记忆摘录中提取证据（调用方负责敏感过滤）。

        注意：hard 证据的 source 统一为 "hard_memory"（记忆 bucket 已在
        build_memory_snapshot 完成分类，此处不再按 HARD_SOURCES 逐一重标——
        避免一条文本被 8 个来源名重复标记导致 hard 数量虚增、置信度失真）。
        """
        evidence: list[Evidence] = []
        for text in memory.get("hard", []):
            if text and any(kw in text for kw in ("高可信", "客观", "可能是", "指出")):
                evidence.append(Evidence(kind="hard", source="hard_memory", detail=text[:120]))
        for text in memory.get("soft", []):
            if text and any(kw in text for kw in ("公开", "说", "自报", "观感", "印象")):
                evidence.append(Evidence(kind="soft", source="public_claim", detail=text[:120]))
        return evidence

    # ------------------------------------------------------------------
    # 观点构建
    # ------------------------------------------------------------------

    def build_viewpoint(
        self,
        *,
        subject_player_id: str,
        subject_name: str,
        claim: str,
        memory: dict[str, list[str]],
        source_action: str,
        day_number: int,
        round_number: int,
        evidence: list[Evidence] | None = None,
    ) -> Viewpoint | None:
        """基于记忆证据构建观点（置信度确定性计算，可被门控拦截）。"""
        evs = evidence if evidence is not None else self.extract_evidence(memory)
        hard_count = sum(1 for e in evs if e.kind == "hard")
        soft_count = sum(1 for e in evs if e.kind == "soft")
        confidence = compute_confidence(hard_count, soft_count)
        return Viewpoint(
            viewpoint_id="",
            subject_player_id=subject_player_id,
            subject_name=subject_name,
            claim=claim,
            evidence=evs,
            confidence=confidence,
            status="active",
            source_action=source_action,
            day_number=day_number,
            round_number=round_number,
        )

    # ------------------------------------------------------------------
    # 观点演化
    # ------------------------------------------------------------------

    def update_with_new_evidence(
        self, viewpoint: Viewpoint, new_evidence: list[Evidence]
    ) -> tuple[Viewpoint, str]:
        """新证据并入观点：置信度重算；若与既有硬证据冲突则废弃。

        Returns:
            (viewpoint, action)  action: "updated" | "superseded" | "no_change"
        """
        if viewpoint.status != "active":
            return viewpoint, "no_change"
        new_hard = [e for e in new_evidence if e.kind == "hard"]
        old_hard_claims = {e.detail for e in viewpoint.evidence if e.kind == "hard"}
        # 冲突检测：新硬证据的"对象"与旧硬证据矛盾（对象名不同且断言相反）
        conflict = False
        for e in new_hard:
            for old in old_hard_claims:
                if old and e.detail and e.detail[:20] != old[:20]:
                    conflict = True
                    break
            if conflict:
                break
        if conflict and len(new_hard) >= len([e for e in viewpoint.evidence if e.kind == "hard"]):
            viewpoint.mark_superseded()
            viewpoint.evidence.extend(new_evidence)
            return viewpoint, "superseded"

        merged = list(viewpoint.evidence)
        merged.extend(new_evidence)
        hard_count = sum(1 for e in merged if e.kind == "hard")
        soft_count = sum(1 for e in merged if e.kind == "soft")
        new_conf = compute_confidence(hard_count, soft_count)
        if new_conf > viewpoint.confidence:
            viewpoint.evidence = merged
            viewpoint.confidence = new_conf
            return viewpoint, "updated"
        return viewpoint, "no_change"

    @staticmethod
    def passes_gate(hard_count: int, soft_count: int = 0) -> bool:
        """门控：必须有硬证据支撑（hard_count >= 1）才可公开断言。

        纯软印象（他人发言观感，无硬证据）即使置信度数值 ≥ 阈值，也不得
        公开强断言——防止"软印象当硬事实"的推理幻觉（PLN-042 红线 3）。
        ``soft_count`` 保留为位置参数以兼容既有调用与未来扩展。
        """
        return hard_count >= 1

    @staticmethod
    def soft_claim_fallback(claim: str) -> str:
        """置信度不足时的降级表述：强断言 → 弱化疑问。"""
        for strong in ("一定是", "绝对是", "就是"):
            if strong in claim:
                return claim.replace(strong, "可能")
        return claim
