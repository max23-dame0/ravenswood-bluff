"""T9: 规则书注入上下文测试 — PLN-041 Phase 3。

验证 `build_role_rulebook_context`：
- 按角色注入能力/夜间时机；
- 阵营红线注入（邪恶方保密 / 善良方推演）；
- 未知角色返回空串（不注入，防止幻觉来源）。
"""

from __future__ import annotations

from src.content.rule_knowledge import build_role_rulebook_context


def test_rulebook_context_contains_role_ability() -> None:
    context = build_role_rulebook_context("washerwoman", "good")
    assert "洗衣妇" in context
    assert "村民" in context
    assert "首夜" in context


def test_rulebook_context_contains_night_note_when_present() -> None:
    context = build_role_rulebook_context("imp", "evil")
    assert "小恶魔" in context
    assert "每晚" in context
    assert "死亡" in context


def test_rulebook_context_evil_red_line() -> None:
    context = build_role_rulebook_context("imp", "evil")
    assert "保密" in context or "伪装" in context or "泄露" in context


def test_rulebook_context_good_red_line() -> None:
    context = build_role_rulebook_context("washerwoman", "good")
    assert "推理" in context or "逻辑" in context


def test_rulebook_context_unknown_role_empty() -> None:
    assert build_role_rulebook_context("not_a_role", "good") == ""


def test_rulebook_context_no_sensitive_team_names() -> None:
    context = build_role_rulebook_context("imp", "evil")
    # 注入内容不得包含具体队友名单类信息
    assert "队友名单" not in context
    assert "private_info" not in context
