from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import DatasetRegistry


SOURCE_IDS = ("DATA-PEST-001", "DATA-PEST-002")
ALLOWED_COMMERCIAL = {"allowed", "allowed_with_attribution"}


def audit_mite_public_sources(
    *,
    source_dir: Path,
    output: Path,
) -> dict[str, Any]:
    registry = DatasetRegistry(source_dir)
    rows: list[dict[str, Any]] = []
    blocking: list[str] = []

    for source_id in SOURCE_IDS:
        source = registry.get(source_id)
        role = source.nongtori_mapping.get("role")
        if source.license != "CC-BY-4.0":
            blocking.append(f"{source_id}:LICENSE_NOT_CC_BY_4_0")
        if source.commercial_use not in ALLOWED_COMMERCIAL:
            blocking.append(f"{source_id}:COMMERCIAL_USE_NOT_APPROVED")
        if not role:
            blocking.append(f"{source_id}:ROLE_MISSING")
        if not source.retrieval.get("requires_api_key"):
            blocking.append(f"{source_id}:ACQUISITION_CONTRACT_MISSING_API_KEY_FLAG")

        rows.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "provider": source.provider,
                "license": source.license,
                "commercial_use": source.commercial_use,
                "role": role,
                "status": source.status.value,
                "acquisition": {
                    "requires_api_key": bool(source.retrieval.get("requires_api_key")),
                    "env_var": source.retrieval.get("env_var"),
                },
                "original_labels": source.original_labels,
                "mapping": source.nongtori_mapping,
            }
        )

    payload = {
        "status": "MITE_PUBLIC_SOURCE_GATE_READY" if not blocking else "MITE_PUBLIC_SOURCE_GATE_BLOCKED",
        "sources": rows,
        "blocking_reasons": blocking,
        "policy": {
            "do_not_merge_roles": True,
            "field_context_source": "DATA-PEST-001",
            "morphology_source": "DATA-PEST-002",
            "field_acceptance_source": "DATA-FIELD-001",
            "no_field_ready_claim_from_public_sources_only": True,
        },
        "next_gate": (
            "Acquire exact source versions, audit split/class/duplicates/augmentations, "
            "then freeze a training candidate snapshot without using field data for model selection."
        ),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
