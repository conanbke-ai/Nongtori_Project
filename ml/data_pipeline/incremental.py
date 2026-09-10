from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .farm_contract import validate_farm_code

LEDGER_COLUMNS = [
    "source_key", "revision", "event_type", "state_after", "row_hash",
    "previous_revision", "changed_fields_json", "source_payload_json", "recorded_at",
]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_source_key(row: dict[str, Any], key_fields: tuple[str, ...] = ("Farm", "ID")) -> str:
    if "Farm" in key_fields:
        validate_farm_code(row.get("Farm"))
    values = [_text(row.get(field)) for field in key_fields]
    if any(not value for value in values):
        raise ValueError(f"source key fields required: {key_fields}")
    return ":".join(values)


def canonical_payload(row: dict[str, Any], *, ignored_fields: Iterable[str] = ()) -> dict[str, str]:
    ignored = set(ignored_fields)
    return {str(key): _text(value) for key, value in sorted(row.items()) if key not in ignored}


def compute_row_hash(row: dict[str, Any], *, ignored_fields: Iterable[str] = ()) -> str:
    payload = canonical_payload(row, ignored_fields=ignored_fields)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def changed_fields(previous: dict[str, Any], current: dict[str, Any], *, ignored_fields: Iterable[str] = ()) -> dict[str, dict[str, str]]:
    ignored = set(ignored_fields)
    keys = sorted((set(previous) | set(current)) - ignored)
    diff: dict[str, dict[str, str]] = {}
    for key in keys:
        old = _text(previous.get(key))
        new = _text(current.get(key))
        if old != new:
            diff[key] = {"old": old, "new": new}
    return diff


def read_ledger(path: Path) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def latest_ledger_state(events: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for event in events:
        key = event["source_key"]
        revision = int(event["revision"])
        if key not in latest or revision > int(latest[key]["revision"]):
            latest[key] = event
    return latest


def _event(*, source_key: str, revision: int, event_type: str, state_after: str, row_hash: str,
           previous_revision: int | None, changed: dict[str, Any], payload: dict[str, Any], recorded_at: str) -> dict[str, str]:
    return {
        "source_key": source_key,
        "revision": str(revision),
        "event_type": event_type,
        "state_after": state_after,
        "row_hash": row_hash,
        "previous_revision": "" if previous_revision is None else str(previous_revision),
        "changed_fields_json": json.dumps(changed, ensure_ascii=False, sort_keys=True),
        "source_payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "recorded_at": recorded_at,
    }


def scan_incremental_rows(current_rows: Iterable[dict[str, Any]], previous_events: Iterable[dict[str, str]], *,
                          key_fields: tuple[str, ...] = ("Farm", "ID"), ignored_fields: Iterable[str] = (),
                          recorded_at: str | None = None) -> tuple[list[dict[str, str]], dict[str, int]]:
    previous_events = list(previous_events)
    latest = latest_ledger_state(previous_events)
    now = recorded_at or datetime.now(timezone.utc).isoformat()
    current_by_key: dict[str, dict[str, Any]] = {}
    counts = {"NEW": 0, "UPDATED": 0, "REMOVED": 0, "UNCHANGED": 0}
    emitted: list[dict[str, str]] = []

    for row in current_rows:
        if not _text(row.get("ID")):
            continue
        key = build_source_key(row, key_fields)
        if key in current_by_key:
            raise ValueError(f"duplicate source key in current source: {key}")
        current_by_key[key] = dict(row)

    for key, row in current_by_key.items():
        payload = canonical_payload(row, ignored_fields=ignored_fields)
        digest = compute_row_hash(row, ignored_fields=ignored_fields)
        previous = latest.get(key)
        if previous is None:
            counts["NEW"] += 1
            emitted.append(_event(source_key=key, revision=1, event_type="NEW", state_after="ACTIVE", row_hash=digest,
                                  previous_revision=None, changed={k: {"old": "", "new": v} for k, v in payload.items()}, payload=payload, recorded_at=now))
            continue
        previous_revision = int(previous["revision"])
        if previous["state_after"] == "ACTIVE" and previous["row_hash"] == digest:
            counts["UNCHANGED"] += 1
            continue
        previous_payload = json.loads(previous.get("source_payload_json") or "{}")
        counts["UPDATED"] += 1
        emitted.append(_event(source_key=key, revision=previous_revision + 1, event_type="UPDATED", state_after="ACTIVE", row_hash=digest,
                              previous_revision=previous_revision, changed=changed_fields(previous_payload, payload, ignored_fields=ignored_fields),
                              payload=payload, recorded_at=now))

    for key, previous in latest.items():
        if previous["state_after"] != "ACTIVE" or key in current_by_key:
            continue
        previous_revision = int(previous["revision"])
        previous_payload = json.loads(previous.get("source_payload_json") or "{}")
        counts["REMOVED"] += 1
        emitted.append(_event(source_key=key, revision=previous_revision + 1, event_type="REMOVED", state_after="REMOVED_FROM_SOURCE",
                              row_hash=previous["row_hash"], previous_revision=previous_revision, changed={}, payload=previous_payload, recorded_at=now))

    return previous_events + emitted, counts


def incremental_scan_csv(source_csv: Path, ledger_path: Path, output_ledger: Path, *,
                         key_fields: tuple[str, ...] = ("Farm", "ID"), ignored_fields: Iterable[str] = ()) -> dict[str, int]:
    with Path(source_csv).open(encoding="utf-8-sig", newline="") as f:
        current = list(csv.DictReader(f))
    ledger, counts = scan_incremental_rows(current, read_ledger(ledger_path), key_fields=key_fields, ignored_fields=ignored_fields)
    output_ledger = Path(output_ledger)
    output_ledger.parent.mkdir(parents=True, exist_ok=True)
    with output_ledger.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        writer.writeheader()
        writer.writerows(ledger)
    return counts
