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


def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _bar(current: int, total: int, width: int = 20) -> str:
    ratio = 1.0 if total <= 0 else min(1.0, max(0.0, current / total))
    filled = int(round(width * ratio))
    return "█" * filled + "░" * (width - filled)


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
        file_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(message)s"))
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        self._logger.addHandler(console)
        self._logger.addHandler(file_handler)

    @property
    def elapsed_sec(self) -> float:
        return monotonic() - self.started_monotonic

    def _pretty_console(self, level: str, event: str, message: str, fields: dict[str, Any]) -> str:
        elapsed = _duration(self.elapsed_sec)
        if event == "RUN_STARTED":
            title = str(fields.get("experiment_id", self.component)).replace("_", " ")
            return (
                "\n" + "━" * 58 + "\n"
                f"  🌱 NONGTORI · {title}\n"
                f"  Run      : {self.run_id}\n"
                f"  Snapshot : {fields.get('snapshot_id', '-')}\n"
                f"  Seed     : {fields.get('seed', '-')}\n"
                + "━" * 58
            )
        if event == "PROGRESS":
            current = int(fields.get("progress_current", 0)); total = int(fields.get("progress_total", 0))
            pct = float(fields.get("progress_pct", 0.0)); phase = str(fields.get("phase", "WORK"))
            extras = []
            for key in ("crop_samples", "failed_rows", "running_train_loss", "learning_rate"):
                if key in fields:
                    extras.append(f"{key}={_fmt(fields[key])}")
            suffix = ("  " + "  ".join(extras)) if extras else ""
            return f"[{phase:<11}] {_bar(current,total)} {pct:6.2f}%  {current:>4}/{total:<4}  elapsed={elapsed}{suffix}"
        if event == "EPOCH_STARTED":
            return f"\n┌─ Epoch {int(fields.get('epoch',0)):02d} / {int(fields.get('max_epochs',0)):02d} " + "─" * 39
        if event == "EPOCH_COMPLETED":
            best_mark = "  ↑ BEST" if bool(fields.get("checkpoint_saved")) else ""
            lines = [
                f"│ Train Loss      {_fmt(fields.get('train_loss'))}",
                f"│ Valid Loss      {_fmt(fields.get('valid_loss'))}",
                f"│ Macro F1        {_fmt(fields.get('macro_f1'))}{best_mark}",
                f"│ Accuracy        {_fmt(fields.get('accuracy'))}",
                f"│ Ordinal MAE     {_fmt(fields.get('ordinal_mae'))}",
                f"│ Weighted Kappa  {_fmt(fields.get('weighted_kappa'))}",
                f"│ LR              {_fmt(fields.get('learning_rate'), 6)}",
                f"│ Best Epoch      {fields.get('best_epoch','-')}",
                f"│ Early Stop      {fields.get('early_stopping_counter','-')} / 5",
                f"│ Epoch Time      {_duration(float(fields.get('epoch_elapsed_sec',0.0)))}",
                "└" + "─" * 57,
            ]
            return "\n".join(lines)
        if event == "CHECKPOINT_SAVED":
            sha = str(fields.get("checkpoint_sha256", ""))
            return f"✓ CHECKPOINT SAVED  epoch={fields.get('epoch')}  metric={_fmt(fields.get('metric_value'))}  sha256={sha[:12]}…"
        if event == "TEST_STARTED":
            return "\n" + "─" * 58 + f"\n  🧪 FINAL TEST · {fields.get('test_samples','?')} samples\n" + "─" * 58
        if event == "TEST_COMPLETED":
            return (
                f"✓ TEST COMPLETE  loss={_fmt(fields.get('test_loss'))}  "
                f"macro_f1={_fmt(fields.get('macro_f1'))}  "
                f"ordinal_mae={_fmt(fields.get('ordinal_mae'))}  "
                f"kappa={_fmt(fields.get('weighted_kappa'))}  accuracy={_fmt(fields.get('accuracy'))}"
            )
        if event == "REMOTE_FETCH_RETRY":
            return f"⚠ RETRY {fields.get('attempt')}/{fields.get('max_attempts')}  row={fields.get('row_idx')}  backoff={fields.get('backoff_sec')}s  {fields.get('error_type')}: {fields.get('error_message')}"
        if event == "EARLY_STOPPING_WAIT":
            return f"△ NO IMPROVEMENT  epoch={fields.get('epoch')}  patience={fields.get('early_stopping_counter')}/{fields.get('patience_limit')}  best={_fmt(fields.get('best_metric'))} @ epoch {fields.get('best_epoch')}"
        if event == "EARLY_STOPPING_TRIGGERED":
            return f"■ EARLY STOP  epoch={fields.get('epoch')}  best_epoch={fields.get('best_epoch')}  best_macro_f1={_fmt(fields.get('best_valid_macro_f1'))}"
        if event in {"RUN_FAILED", "CACHE_ROW_FAILED"} or level in {"ERROR", "CRITICAL"}:
            return (
                "\n" + "!" * 58 + "\n"
                f"  ✖ {event}: {message}\n"
                f"  Type    : {fields.get('error_type','-')}\n"
                f"  Error   : {fields.get('error_message','-')}\n"
                f"  Phase   : {fields.get('phase','-')}\n"
                f"  Elapsed : {elapsed}\n"
                + "!" * 58
            )
        if event == "RUN_FINISHED":
            symbol = "✓" if fields.get("status") == "SUCCESS" else "✖"
            return "\n" + "━" * 58 + f"\n  {symbol} RUN {fields.get('status')}  duration={_duration(float(fields.get('duration_sec',0)))}  warnings={fields.get('warning_count',0)} errors={fields.get('error_count',0)}\n" + "━" * 58
        symbol = {"WARNING": "⚠", "ERROR": "✖", "CRITICAL": "✖"}.get(level, "•")
        phase = fields.get("phase")
        prefix = f"[{phase}] " if phase else ""
        return f"{symbol} {prefix}{message}  elapsed={elapsed}"

    def emit(self, level: str, event: str, message: str, **fields: Any) -> dict[str, Any]:
        level = level.upper()
        payload = {
            "timestamp": utc_now_iso(),
            "level": level,
            "run_id": self.run_id,
            "component": self.component,
            "event": event,
            "message": message,
            "elapsed_sec": round(self.elapsed_sec, 3),
            **fields,
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        pretty = self._pretty_console(level, event, message, fields)
        method = level.lower() if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "info"
        getattr(self._logger, method)(pretty)
        # File log keeps a searchable compact structured tail even though console is human-oriented.
        if self._logger.handlers:
            file_tail = json.dumps(fields, ensure_ascii=False, sort_keys=True)
            logging.getLogger(f"nongtori.filetail.{self.run_id}")
        if level == "WARNING":
            self.warning_count += 1
        elif level in {"ERROR", "CRITICAL"}:
            self.error_count += 1
        return payload

    def progress(self, *, phase: str, current: int, total: int, message: str, **fields: Any) -> None:
        pct = 100.0 if total <= 0 else current * 100.0 / total
        self.emit("INFO", "PROGRESS", message, phase=phase, progress_current=current, progress_total=total, progress_pct=round(pct, 2), **fields)

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
            "duration_sec": round(self.elapsed_sec, 3),
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            **fields,
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.emit("INFO" if status == "SUCCESS" else "CRITICAL", "RUN_FINISHED", f"run finished with status={status}", **payload)
        return payload
