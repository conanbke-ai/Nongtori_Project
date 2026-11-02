from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import DatasetRegistry


SOURCE_IDS = ("DATA-PEST-001", "DATA-PEST-002")
ALLOWED_COMMERCIAL = {"allowed", "allowed_with_attribution"}
SOURCE_CONTRACTS = {
    "DATA-PEST-001": {
        "version": "1",
        "role": "STRAWBERRY_FIELD_CONTEXT_PEST_DETECTION_CANDIDATE",
        "classes": [
            "dry",
            "gray_mold",
            "scorch",
            "Tetranychus Urticae",
        ],
        "target_label": "Tetranychus Urticae",
    },
    "DATA-PEST-002": {
        "version": "210",
        "role": "TSSM_MORPHOLOGY_AND_LIFE_STAGE_REFERENCE",
        "classes": ["Adult_female", "Immature", "Viable_egg"],
    },
}


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
        contract = SOURCE_CONTRACTS[source_id]
        role = source.nongtori_mapping.get("role")
        version = source.version_or_revision
        retrieval_version = source.retrieval.get("version_number")
        if source.license != "CC-BY-4.0":
            blocking.append(f"{source_id}:LICENSE_NOT_CC_BY_4_0")
        if source.commercial_use not in ALLOWED_COMMERCIAL:
            blocking.append(f"{source_id}:COMMERCIAL_USE_NOT_APPROVED")
        if not role:
            blocking.append(f"{source_id}:ROLE_MISSING")
        elif role != contract["role"]:
            blocking.append(f"{source_id}:ROLE_MISMATCH")
        if not source.retrieval.get("requires_api_key"):
            blocking.append(f"{source_id}:ACQUISITION_CONTRACT_MISSING_API_KEY_FLAG")
        if version is None or not str(version).strip():
            blocking.append(f"{source_id}:VERSION_OR_REVISION_MISSING")
        elif str(version) != contract["version"]:
            blocking.append(f"{source_id}:VERSION_PIN_MISMATCH")
        if retrieval_version is None or not str(retrieval_version).strip():
            blocking.append(f"{source_id}:RETRIEVAL_VERSION_NUMBER_MISSING")
        elif version is not None and str(retrieval_version) != str(version):
            blocking.append(f"{source_id}:RETRIEVAL_VERSION_MISMATCH")
        if source.original_labels != contract["classes"]:
            blocking.append(f"{source_id}:CLASS_PIN_MISMATCH")
        if source_id == "DATA-PEST-001":
            if source.nongtori_mapping.get("target_label") != contract["target_label"]:
                blocking.append(f"{source_id}:TARGET_LABEL_MISMATCH")
        elif source.nongtori_mapping.get("tssm_positive_labels") != contract["classes"]:
            blocking.append(f"{source_id}:POSITIVE_LABEL_PIN_MISMATCH")

        rows.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "provider": source.provider,
                "license": source.license,
                "commercial_use": source.commercial_use,
                "role": role,
                "status": source.status.value,
                "version_or_revision": version,
                "acquisition": {
                    "requires_api_key": bool(source.retrieval.get("requires_api_key")),
                    "env_var": source.retrieval.get("env_var"),
                    "version_number": retrieval_version,
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
            "gate_scope": "REGISTERED_SOURCE_CONTRACT_PRE_ACQUISITION_ONLY",
            "no_download_snapshot_training_or_field_approval_claim": True,
            "source_registry_statuses_preserved": True,
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
