from __future__ import annotations

import argparse
import json

if __package__:
    from . import features
else:
    import features


def main() -> None:
    parser = argparse.ArgumentParser(description="농산물 등급별 가격 분위수 CatBoost 학습")
    features.add_training_arguments(parser)
    args = parser.parse_args()
    if args.train and args.output is None:
        parser.error("--train requires --output")

    try:
        rows, config, split = features.load_training_input(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    evidence = split.evidence(args)
    if not args.train:
        print(json.dumps({**evidence, "status": "INPUT_VALIDATED"}, ensure_ascii=False, indent=2))
        return

    import joblib
    import numpy as np
    from catboost import CatBoostRegressor

    if __package__:
        from .metrics import mae, pinball_loss, smape
    else:
        from metrics import mae, pinball_loss, smape

    frame = features.training_price_frame(row for row in rows if row.trade_day <= split.validation_end)
    frame = features.add_lag_features(frame).dropna(subset=["price_lag_1"])
    target = features.TARGET_COLUMN
    train_mask = frame[features.DATE_COLUMN].dt.date <= split.train_end
    usable_train = frame.loc[train_mask]
    usable_valid = frame.loc[~train_mask]
    if usable_train.empty or usable_valid.empty:
        parser.error("Train and selection validation both require an available prior same-series price")

    feature_columns = list(features.CATBOOST_FEATURES)
    categorical = list(features.SERIES_FIELDS)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    predictions: dict[float, np.ndarray] = {}
    metrics: dict[str, float | str | int] = {
        **evidence,
        "train_rows": len(usable_train),
        "selection_validation_rows": len(usable_valid),
    }
    seed = int(config["validation"]["random_seed"])
    for quantile in config["model"]["quantiles"]:
        quantile = float(quantile)
        model = CatBoostRegressor(
            loss_function=f"Quantile:alpha={quantile}",
            iterations=1200,
            depth=8,
            learning_rate=0.035,
            random_seed=seed,
            verbose=100,
            allow_writing_files=False,
        )
        model.fit(
            usable_train[feature_columns], usable_train[target],
            cat_features=categorical,
            eval_set=(usable_valid[feature_columns], usable_valid[target]),
            early_stopping_rounds=120,
        )
        predictions[quantile] = model.predict(usable_valid[feature_columns])
        model.save_model(output / f"catboost_q{int(quantile * 100):02d}.cbm")
        metrics[f"selection_validation_pinball_q{int(quantile * 100):02d}"] = pinball_loss(
            usable_valid[target].to_numpy(), predictions[quantile], quantile
        )

    actual = usable_valid[target].to_numpy()
    metrics["selection_validation_mae_p50"] = mae(actual, predictions[0.5])
    metrics["selection_validation_smape_p50"] = smape(actual, predictions[0.5])
    metrics["selection_validation_interval_coverage_p10_p90"] = float(
        np.mean((actual >= predictions[0.1]) & (actual <= predictions[0.9]))
    )
    joblib.dump({"features": feature_columns, "categorical": categorical, "config": config}, output / "preprocessing.joblib")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
