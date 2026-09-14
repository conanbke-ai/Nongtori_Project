from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn
from torchvision import models

from ml.observability import RunLogger


def main() -> None:
    root = Path("artifacts/ripeness-v003-smoke")
    logger = RunLogger(root, "ripeness_v003_smoke")
    logger.emit(
        "INFO",
        "RUN_STARTED",
        "RIPENESS-V003 synthetic smoke test started",
        phase="SMOKE",
        experiment_id="RIPENESS-V003-SMOKE",
        snapshot_id="SYNTHETIC-NO-REMOTE-DATA",
        seed=0,
    )

    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 3)

    # Stage 1 contract: classifier head only.
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name.startswith("fc.")
    head_trainable = [name for name, p in model.named_parameters() if p.requires_grad]
    if not head_trainable or any(not name.startswith("fc.") for name in head_trainable):
        raise RuntimeError(f"head-only freeze contract failed: {head_trainable}")

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=5e-5)
    criterion = nn.CrossEntropyLoss()
    images = torch.randn(2, 3, 224, 224)
    labels = torch.tensor([0, 2], dtype=torch.long)
    logits = model(images)
    loss = criterion(logits, labels)
    loss.backward()
    optimizer.step()
    if not torch.isfinite(loss):
        raise RuntimeError("non-finite head-only smoke loss")

    # Stage 2 contract: full backbone unfreezes and can optimize.
    for parameter in model.parameters():
        parameter.requires_grad = True
    if not all(p.requires_grad for p in model.parameters()):
        raise RuntimeError("full-unfreeze contract failed")

    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
    optimizer.zero_grad()
    logits = model(images)
    loss2 = criterion(logits, labels)
    loss2.backward()
    optimizer.step()
    if not torch.isfinite(loss2):
        raise RuntimeError("non-finite full-unfreeze smoke loss")

    checkpoint = root / "smoke.pt"
    torch.save(model.state_dict(), checkpoint)
    if not checkpoint.exists() or checkpoint.stat().st_size == 0:
        raise RuntimeError("smoke checkpoint was not created")

    result = {
        "status": "SUCCESS",
        "remote_data_downloaded": False,
        "pretrained_weights_downloaded": False,
        "head_only_trainable_count": len(head_trainable),
        "all_parameters_unfrozen": True,
        "head_loss": float(loss.detach()),
        "full_loss": float(loss2.detach()),
        "checkpoint_created": True,
    }
    (root / "smoke-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.finish_summary(
        status="SUCCESS",
        summary_path=root / "summaries" / "run_summary.json",
        final_metrics=result,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
