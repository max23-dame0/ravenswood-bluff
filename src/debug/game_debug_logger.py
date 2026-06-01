"""Per-game temporary debug logging for live playtest review."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class GameDebugLogger:
    """Write per-game terminal and LLM traces, keeping only recent sessions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session_dir: Path | None = None
        self._game_id: str | None = None
        self._terminal_handler: logging.FileHandler | None = None
        self._attached_loggers: list[logging.Logger] = []

    @property
    def enabled(self) -> bool:
        return os.getenv("BOTC_DEBUG_GAME_LOGS", "1") != "0"

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    @property
    def game_id(self) -> str | None:
        return self._game_id

    def start_game(self, game_id: str, metadata: dict[str, Any] | None = None) -> Path | None:
        if not self.enabled:
            return None
        with self._lock:
            if self._game_id == game_id and self._session_dir:
                self._merge_metadata(metadata)
                return self._session_dir
            self.end_game()

            base_dir = Path(os.getenv("BOTC_DEBUG_GAME_LOG_DIR", "runtime_game_logs"))
            base_dir.mkdir(parents=True, exist_ok=True)
            self._session_dir = self._next_slot_dir(base_dir)
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._game_id = game_id

            meta = {
                "game_id": game_id,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "files": {
                    "terminal": "terminal.log",
                    "llm": "llm.jsonl",
                    "metadata": "metadata.json",
                },
            }
            if metadata:
                meta["metadata"] = metadata
            (self._session_dir / "llm.jsonl").write_text("", encoding="utf-8")
            (self._session_dir / "metadata.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            self._attach_terminal_handler(self._session_dir / "terminal.log")
            logging.getLogger(__name__).info("Game debug logs started: %s", self._session_dir)
            return self._session_dir

    def end_game(self) -> None:
        with self._lock:
            if self._terminal_handler:
                for logger_obj in self._attached_loggers:
                    try:
                        logger_obj.removeHandler(self._terminal_handler)
                    except Exception:
                        pass
                try:
                    self._terminal_handler.close()
                except Exception:
                    pass
            self._terminal_handler = None
            self._attached_loggers = []
            self._session_dir = None
            self._game_id = None

    def log_llm_request(
        self,
        *,
        request_id: str,
        model: str,
        base_url: str | None,
        system_prompt: str,
        messages: list[dict[str, Any]],
        parameters: dict[str, Any],
    ) -> None:
        self._write_llm_record(
            {
                "type": "request",
                "request_id": request_id,
                "model": model,
                "base_url": base_url,
                "system_prompt": system_prompt,
                "messages": messages,
                "parameters": parameters,
            }
        )

    def log_llm_response(
        self,
        *,
        request_id: str,
        model: str,
        content: Any,
        tool_calls: Any,
        usage: dict[str, Any],
        finish_reason: str | None,
        diagnostics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._write_llm_record(
            {
                "type": "response" if not error else "error",
                "request_id": request_id,
                "model": model,
                "content": content,
                "tool_calls": tool_calls,
                "usage": usage,
                "finish_reason": finish_reason,
                "diagnostics": diagnostics or {},
                "error": error,
            }
        )

    def _write_llm_record(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            if not self._session_dir:
                return
            record = {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "game_id": self._game_id,
                **payload,
            }
            with (self._session_dir / "llm.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _attach_terminal_handler(self, path: Path) -> None:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.setLevel(logging.INFO)
        self._terminal_handler = handler
        logger_names = ("", "storyteller")
        self._attached_loggers = [logging.getLogger(name) for name in logger_names]
        for logger_obj in self._attached_loggers:
            logger_obj.addHandler(handler)

    def _next_slot_dir(self, base_dir: Path) -> Path:
        try:
            keep = max(1, int(os.getenv("BOTC_DEBUG_GAME_LOG_KEEP", "3")))
        except ValueError:
            keep = 3
        keep = min(keep, 9)
        index_path = base_dir / ".slot_index"
        try:
            current = int(index_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            current = 0
        next_index = (current % keep) + 1
        index_path.write_text(str(next_index), encoding="utf-8")
        return base_dir / f"recent_{next_index}"

    def _merge_metadata(self, metadata: dict[str, Any] | None) -> None:
        if not metadata or not self._session_dir:
            return
        meta_path = self._session_dir / "metadata.json"
        try:
            current = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        except Exception:
            current = {}
        existing_metadata = current.get("metadata")
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        existing_metadata.update(metadata)
        current["metadata"] = existing_metadata
        current.setdefault("game_id", self._game_id)
        current["updated_at"] = datetime.now().isoformat(timespec="seconds")
        meta_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


game_debug_logger = GameDebugLogger()
