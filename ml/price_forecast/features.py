from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_price_data(path: str | Path, config: dict[str, Any]) -> pd.DataFrame:
    source = Path(path)
    frame = pd.read_parquet(source) if source.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(source)
    data = config["data"]
    date_col = data["date_column"]
    target_col = data["target_column"]
    groups = data["group_columns"]
    required = [date_col, target_col, *groups]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"필수 열 누락: {', '.join(missing)}")

    frame[date_col] = pd.to_datetime(frame[date_col], errors="raise").dt.normalize()
    frame[target_col] = pd.to_numeric(frame[target_col], errors="coerce")
    for column in groups:
        frame[column] = frame[column].fillna("UNKNOWN").astype(str)
    for column in data.get("observed_numeric_columns", []):
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=[target_col]).sort_values([*groups, date_col]).reset_index(drop=True)
    duplicate = frame.duplicated([*groups, date_col], keep=False)
    if duplicate.any():
        keys = frame.loc[duplicate, [*groups, date_col]].head(5).to_dict("records")
        raise ValueError(f"시계열 키가 중복되었습니다. 집계 단위를 먼저 통일하세요: {keys}")
    if (frame[target_col] < 0).any():
        raise ValueError("가격은 0보다 작을 수 없습니다.")
    return frame


def add_calendar_features(frame: pd.DataFrame, date_col: str) -> pd.DataFrame:
    result = frame.copy()
    date = result[date_col]
    result["day_of_week"] = date.dt.dayofweek.astype("int16")
    result["month"] = date.dt.month.astype("int16")
    result["day_of_year"] = date.dt.dayofyear.astype("int16")
    result["week_of_year"] = date.dt.isocalendar().week.astype("int16")
    result["is_weekend"] = (date.dt.dayofweek >= 5).astype("int8")
    if "is_holiday" not in result.columns:
        result["is_holiday"] = 0
    result["is_holiday"] = result["is_holiday"].fillna(0).astype("int8")
    return result


def add_lag_features(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    data = config["data"]
    date_col = data["date_column"]
    target_col = data["target_column"]
    groups = data["group_columns"]
    result = add_calendar_features(frame, date_col)
    grouped = result.groupby(groups, observed=True, sort=False)[target_col]

    for lag in (1, 2, 3, 7, 14, 28, 56):
        result[f"price_lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(1)
    for window in (3, 7, 14, 28):
        result[f"price_roll_mean_{window}"] = shifted.groupby(
            [result[column] for column in groups], observed=True, sort=False
        ).transform(lambda series: series.rolling(window, min_periods=2).mean())
        result[f"price_roll_std_{window}"] = shifted.groupby(
            [result[column] for column in groups], observed=True, sort=False
        ).transform(lambda series: series.rolling(window, min_periods=2).std())
    return result


def temporal_split(frame: pd.DataFrame, date_col: str, holdout_days: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    latest = frame[date_col].max()
    cutoff = latest - pd.Timedelta(days=holdout_days)
    train = frame.loc[frame[date_col] <= cutoff].copy()
    valid = frame.loc[frame[date_col] > cutoff].copy()
    if train.empty or valid.empty:
        raise ValueError("시간순 검증을 위한 학습/검증 기간이 부족합니다.")
    return train, valid, cutoff
