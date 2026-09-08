from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightning.pytorch as pl
import pandas as pd
import torch
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_forecasting import GroupNormalizer, TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.metrics import QuantileLoss

from features import add_calendar_features, load_config, load_price_data


def main() -> None:
    parser = argparse.ArgumentParser(description="글로벌 다중 시계열 TFT 가격 예측 학습")
    parser.add_argument("--data", required=True)
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    frame = load_price_data(args.data, config)
    data = config["data"]
    frame = add_calendar_features(frame, data["date_column"])
    groups = data["group_columns"]
    target = data["target_column"]
    for column in data["observed_numeric_columns"]:
        frame[column] = frame.groupby(groups, observed=True)[column].transform(lambda values: values.ffill()).fillna(0.0)
    origin = frame[data["date_column"]].min()
    frame["time_idx"] = (frame[data["date_column"]] - origin).dt.days.astype(int)
    for column in ["day_of_week", "month", "day_of_year", "is_weekend", "is_holiday"]:
        frame[column] = frame[column].astype(float)

    max_prediction = int(config["model"]["max_prediction_length"])
    max_encoder = int(config["model"]["max_encoder_length"])
    validation_start = frame["time_idx"].max() - int(config["validation"]["holdout_days"])
    training_data = frame.loc[frame["time_idx"] < validation_start].copy()
    known_reals = ["time_idx", "day_of_week", "month", "day_of_year", "is_weekend", "is_holiday"]
    unknown_reals = [target, *data["observed_numeric_columns"]]
    dataset = TimeSeriesDataSet(
        training_data,
        time_idx="time_idx",
        target=target,
        group_ids=groups,
        max_encoder_length=max_encoder,
        max_prediction_length=max_prediction,
        static_categoricals=groups,
        time_varying_known_reals=known_reals,
        time_varying_unknown_reals=unknown_reals,
        target_normalizer=GroupNormalizer(groups=groups, transformation="softplus"),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=True,
    )
    validation = TimeSeriesDataSet.from_dataset(dataset, frame, min_prediction_idx=validation_start, stop_randomization=True)
    train_loader = dataset.to_dataloader(train=True, batch_size=128, num_workers=0)
    valid_loader = validation.to_dataloader(train=False, batch_size=256, num_workers=0)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = ModelCheckpoint(dirpath=output, filename="tft-{epoch:02d}-{val_loss:.4f}", monitor="val_loss", mode="min", save_top_k=1)
    trainer = pl.Trainer(
        max_epochs=80,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1,
        gradient_clip_val=0.1,
        callbacks=[EarlyStopping(monitor="val_loss", patience=8, mode="min"), checkpoint],
        deterministic=True,
        log_every_n_steps=10,
    )
    model = TemporalFusionTransformer.from_dataset(
        dataset,
        learning_rate=0.02,
        hidden_size=32,
        attention_head_size=4,
        hidden_continuous_size=16,
        dropout=0.15,
        loss=QuantileLoss(quantiles=[float(value) for value in config["model"]["quantiles"]]),
        reduce_on_plateau_patience=4,
    )
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=valid_loader)
    summary = {
        "best_checkpoint": checkpoint.best_model_path,
        "best_validation_loss": float(checkpoint.best_model_score) if checkpoint.best_model_score is not None else None,
        "validation_start": (origin + pd.Timedelta(days=validation_start)).date().isoformat(),
        "train_rows": len(training_data),
        "validation_rows": len(frame) - len(training_data),
    }
    (output / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
