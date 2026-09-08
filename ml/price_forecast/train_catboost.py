from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from catboost import CatBoostRegressor

from features import add_lag_features, load_config, load_price_data, temporal_split
from metrics import mae, pinball_loss, smape


def main() -> None:
    parser = argparse.ArgumentParser(description="농산물 등급별 가격 분위수 CatBoost 학습")
    parser.add_argument("--data", required=True, help="CSV 또는 Parquet 가격 이력")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--output", required=True, help="모델 산출물 폴더")
    args = parser.parse_args()

    config = load_config(args.config)
    raw = load_price_data(args.data, config)
    frame = add_lag_features(raw, config)
    data_config = config["data"]
    target = data_config["target_column"]
    date_col = data_config["date_column"]
    groups = data_config["group_columns"]
    train, valid, cutoff = temporal_split(frame, date_col, int(config["validation"]["holdout_days"]))

    feature_columns = [column for column in frame.columns if column not in {target, date_col}]
    categorical = [column for column in groups if column in feature_columns]
    usable_train = train.dropna(subset=["price_lag_1"]).copy()
    usable_valid = valid.dropna(subset=["price_lag_1"]).copy()
    for column in feature_columns:
        if column not in categorical:
            fill = usable_train[column].median()
            usable_train[column] = usable_train[column].fillna(fill)
            usable_valid[column] = usable_valid[column].fillna(fill)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    predictions: dict[float, np.ndarray] = {}
    metrics: dict[str, float | str | int] = {
        "cutoff_date": cutoff.date().isoformat(),
        "train_rows": len(usable_train),
        "validation_rows": len(usable_valid),
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
        metrics[f"pinball_q{int(quantile * 100):02d}"] = pinball_loss(
            usable_valid[target].to_numpy(), predictions[quantile], quantile
        )

    actual = usable_valid[target].to_numpy()
    metrics["mae_p50"] = mae(actual, predictions[0.5])
    metrics["smape_p50"] = smape(actual, predictions[0.5])
    metrics["interval_coverage_p10_p90"] = float(np.mean((actual >= predictions[0.1]) & (actual <= predictions[0.9])))
    joblib.dump({"features": feature_columns, "categorical": categorical, "config": config}, output / "preprocessing.joblib")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
