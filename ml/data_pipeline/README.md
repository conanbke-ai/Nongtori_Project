# Nongtori Data Pipeline v1

Design contract: `docs/AI_DATA_PIPELINE_DESIGN.md` / `docs/DESIGN_FREEZE_V1.md`.

## Scope

```text
Dataset Registry
→ Provider Adapter
→ Download
→ Audit / checksum manifest
→ Immutable Snapshot provenance
```

V1 providers: Mendeley Data public API, Hugging Face Hub, Direct HTTP, Kaggle CLI, AI-Hub `aihubshell`.

Raw datasets are intentionally **not committed to Git**. Use local/external storage paths under `data/raw`, `data/audit`, `data/snapshots` or another configured location.

## Usage

```bash
python -m ml.data_pipeline.cli list
python -m ml.data_pipeline.cli download DATA-RIP-001 --raw-root data/raw
python -m ml.data_pipeline.cli audit --input data/raw/DATA-RIP-001/1 --output data/audit/DATA-RIP-001/1
python -m ml.data_pipeline.cli snapshot DATA-RIP-001 \
  --audit-dir data/audit/DATA-RIP-001/1 \
  --snapshot-root data/snapshots \
  --snapshot-id RIP001-v1-audit001
```

Hugging Face requires `huggingface_hub`. Kaggle requires an authenticated `kaggle` CLI. AI-Hub requires download approval, official `aihubshell`, and `AIHUB_API_KEY`.

`DOWNLOADED != APPROVED`. The current audit checks file integrity metadata, empty files, checksums, and exact duplicates. Label semantic audit/normalization is the next gate before an external source can become `APPROVED/NORMALIZED`.
