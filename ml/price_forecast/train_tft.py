from __future__ import annotations

import argparse
import json

if __package__:
    from . import features
else:
    import features


def main() -> None:
    parser = argparse.ArgumentParser(description="글로벌 다중 시계열 TFT 가격 예측 학습")
    features.add_training_arguments(parser)
    args = parser.parse_args()
    if args.train and args.output is None:
        parser.error("--train requires --output")

    try:
        rows, config, split = features.load_training_input(args)
        candidate_rows = [row for row in rows if row.trade_day <= split.validation_end]
        features.validate_tft_history(candidate_rows)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    evidence = split.evidence(args)
    if not args.train:
        print(json.dumps({**evidence, "status": "INPUT_VALIDATED"}, ensure_ascii=False, indent=2))
        return

    import lightning.pytorch as pl
    import torch
    from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
    from pytorch_forecasting import EncoderNormalizer, TemporalFusionTransformer, TimeSeriesDataSet
    from pytorch_forecasting.metrics import QuantileLoss

    frame = features.add_calendar_features(features.training_price_frame(candidate_rows))
    groups = list(features.SERIES_FIELDS)
    target = features.TARGET_COLUMN
    days = frame[features.DATE_COLUMN]
    origin = days.min()
    frame["time_idx"] = (days - origin).dt.days.astype(int)
    for column in features.CALENDAR_FEATURES:
        frame[column] = frame[column].astype(float)

    max_prediction = int(config["model"]["max_prediction_length"])
    max_encoder = int(config["model"]["max_encoder_length"])
    validation_start = (split.train_end - origin.date()).days + 1
    training_data = frame.loc[frame["time_idx"] < validation_start].copy()
    dataset = TimeSeriesDataSet(
        training_data,
        time_idx="time_idx",
        target=target,
        group_ids=groups,
        max_encoder_length=max_encoder,
        max_prediction_length=max_prediction,
        static_categoricals=groups,
        time_varying_known_reals=list(features.TFT_KNOWN_REALS),
        time_varying_unknown_reals=list(features.TFT_UNKNOWN_REALS),
        target_normalizer=EncoderNormalizer(),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=False,
    )
    validation = TimeSeriesDataSet.from_dataset(dataset, frame, min_prediction_idx=validation_start, stop_randomization=True)
    train_loader = dataset.to_dataloader(train=True, batch_size=128, num_workers=0)
    valid_loader = validation.to_dataloader(train=False, batch_size=256, num_workers=0)

    output = args.output
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
        **evidence,
        "best_selection_validation_loss": (
            float(checkpoint.best_model_score) if checkpoint.best_model_score is not None else None
        ),
        "validation_start": (origin + pd.Timedelta(days=validation_start)).date().isoformat(),
        "train_rows": len(training_data),
        "selection_validation_rows": len(frame) - len(training_data),
    }
    (output / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
