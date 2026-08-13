"""检索持久化存储 (RetrievalStore) — PLN-041 Phase 2 T6。

把检索语料（分块 + 元数据）落盘 `data/agents/_retrieval/`，启动时重建索引：

- 语料以 JSON 落盘（`chunks_meta.json`），Faiss/BM25 索引由语料重建（确定性）；
- 与项目"数据资产"定位一致：索引不因进程重启丢失；
- 目录可通过 `BOTC_DATA_DIR` 环境变量重定向（与 `shared_pool` / `player_profile` 一致）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


class RetrievalStore:
    """检索语料持久化：save_chunks / load_chunks。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._retrieval_dir = base_dir or _data_root() / "agents" / "_retrieval"
        self._meta_path = self._retrieval_dir / "chunks_meta.json"

    def save_chunks(self, chunks: list[dict[str, Any]]) -> Path:
        """把语料（text + metadata）落盘。"""
        self._retrieval_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        return self._meta_path

    def load_chunks(self) -> list[dict[str, Any]]:
        """加载语料；文件缺失/损坏返回空列表。"""
        if not self._meta_path.exists():
            return []
        try:
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [c for c in data if isinstance(c, dict)]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[retrieval-store] 加载语料失败: %s", exc)
            return []


def build_default_store() -> RetrievalStore:
    """构建默认持久化存储（data/agents/_retrieval/）。"""
    return RetrievalStore()
