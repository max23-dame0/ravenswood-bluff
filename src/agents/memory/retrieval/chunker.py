"""分块器 (Chunker) — PLN-041 Phase 1 T2。

把两类语料切成带元数据的检索块：

1. **规则知识条目**：每角色一块（`chunk_rule_knowledge`），
   元数据含 role_id / team / role_type / timing；
2. **历史对局 jsonl**：按"轮次+事件/消息"分块（`chunk_session_jsonl`），
   元数据含 round / phase / type / speaker。

输出统一为 `{"text": str, "metadata": dict}` 结构，供 BM25/Faiss 索引。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def chunk_rule_knowledge() -> list[dict[str, Any]]:
    """规则知识按角色条目分块（每角色一块）。"""
    from src.content.rule_knowledge import RULE_KNOWLEDGE_ENTRIES

    chunks: list[dict[str, Any]] = []
    for entry in RULE_KNOWLEDGE_ENTRIES:
        text_parts = [
            f"角色: {entry['zh_name']}（{entry['en_name']}，{entry['role_id']}）",
            f"阵营: {'善良' if entry['team'] == 'good' else '邪恶'} | 类型: {entry['role_type']}",
            f"能力: {entry['description']}",
        ]
        if entry.get("night_note"):
            text_parts.append(f"夜间: {entry['night_note']}")
        if entry.get("persona_hint"):
            text_parts.append(f"风格: {entry['persona_hint']}")
        chunks.append(
            {
                "text": "\n".join(text_parts),
                "metadata": {
                    "type": "rule",
                    "role_id": entry["role_id"],
                    "team": entry["team"],
                    "role_type": entry["role_type"],
                    "timing": entry.get("timing", ""),
                },
            }
        )
    return chunks


def chunk_session_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """历史对局 jsonl 按行分块（事件/消息，带 round 元数据）。

    未知类型行跳过；文件缺失返回空列表。
    """
    p = Path(path)
    if not p.exists():
        return []
    chunks: list[dict[str, Any]] = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = record.get("type")
                if rtype not in {"event", "message"}:
                    continue
                round_n = int(record.get("round") or record.get("round_number") or 0)
                if rtype == "event":
                    payload = record.get("payload") or {}
                    text = (
                        f"事件: {payload.get('event_type', '')} "
                        f"| 参与者: {payload.get('actor', '')} | 目标: {payload.get('target', '')}"
                    )
                    metadata: dict[str, Any] = {
                        "type": "event",
                        "round": round_n,
                        "phase": str(record.get("phase", "")),
                        "event_type": payload.get("event_type", ""),
                    }
                else:
                    text = f'发言: {record.get("speaker", "")} 说: "{record.get("content", "")}"'
                    metadata = {
                        "type": "message",
                        "round": round_n,
                        "phase": str(record.get("phase", "")),
                        "speaker": record.get("speaker", ""),
                    }
                chunks.append({"text": text, "metadata": metadata})
    except OSError as exc:
        logger.warning("[chunker] 读取 %s 失败: %s", p, exc)
        return []
    return chunks
