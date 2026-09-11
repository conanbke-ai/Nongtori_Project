from __future__ import annotations

import json
import logging
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunLogger:
    root: Path
    component: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.log_path = self.root / "run.log"
        self.error_path = self.root / "error.log"
        self.started_at = utc_now_iso()
        self.started_monotonic = monotonic()
        self.warning_count = 0
        self.error_count = 0
        self._logger = logging.getLogger(f"nongtori.{self.component}.{self.run_id}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()
        self._logger.propagate = False
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self._logger.addHandler(console)
        self._logger.addHandler(file_handler)

    def emit(self, level: str, event: str, message: str, **fields: Any) -> dict[str, Any]:
        level = level.upper()
        payload = {
            "timestamp": utc_now_iso(),
            "level": level,
            "run_id": self.run_id,
            "component": self.component,
            "event": event,
            "message": message,
            "elapsed_sec": round(monotonic() - self.started_monotonic, 3),
            **fields,
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        getattr(self._logger, level.lower() if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "info")(
            "%s | %s | %s", event, message, json.dumps(fields, ensure_ascii=False, sort_keys=True)
        )
        if level == "WARNING":
            self.warning_count += 1
        elif level in {"ERROR", "CRITICAL"}:
            self.error_count += 1
        return payload

    def progress(self, *, phase: str, current: int, total: int, message: str, **fields: Any) -> None:
        pct = 100.0 if total <= 0 else current * 100.0 / total
        self.emit(
            "INFO",
            "PROGRESS",
            message,
            phase=phase,
            progress_current=current,
            progress_total=total,
            progress_pct=round(pct, 2),
            **fields,
        )

    def exception(self, event: str, message: str, exc: BaseException, **fields: Any) -> None:
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with self.error_path.open("a", encoding="utf-8") as f:
            f.write(f"[{utc_now_iso()}] {event}: {message}\n{stack}\n")
        self.emit("ERROR", event, message, error_type=type(exc).__name__, error_message=str(exc), stack_trace=stack, **fields)

    def finish_summary(self, *, status: str, summary_path: Path, **fields: Any) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "component": self.component,
            "status": status,
            "started_at": self.started_at,
            "finished_at": utc_now_iso(),
            "duration_sec": round(monotonic() - self.started_monotonic, 3),
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            **fields,
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.emit("INFO" if status == "SUCCESS" else "CRITICAL", "RUN_FINISHED", f"run finished with status={status}", **payload)
        return payload
