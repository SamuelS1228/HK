from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Iterable

import numpy as np
import pandas as pd


AUTO_COLUMN_ALIASES = {
    "category": [
        "Health Segments",
        "Health Segment",
        "Segment",
        "Category",
        "Fleet Category",
        "Asset Category",
        "DC Category",
    ],
    "age": [
        "Age",
        "Vehicle Age",
        "Vehicle Age Years",
        "Asset Age",
        "Unit Age",
    ],
    "median_repair_pct": [
        "Median",
        "Median Repair %",
        "Median Repair Percent",
        "Median Repair Percentage",
        "Repair %",
        "Repair Percent",
        "Repair Percentage",
        "Median %",
    ],
}


AGGREGATION_METHODS = {
    "Median": "median",
    "Mean": "mean",
    "Max": "max",
    "Min": "min",
}


SMOOTHING_METHODS = {
    "None": "none",
    "Centered moving average": "centered_moving_average",
    "Trailing moving average": "trailing_moving_average",
    "Weighted moving average": "weighted_moving_average",
    "Exponential smoothing": "exponential",
}


@dataclass(frozen=True)
class CleanResult:
    data: pd.DataFrame
    rows_in: int
    rows_out: int
    rows_dropped_missing_category: int
    rows_dropped_missing_age: int
    rows_dropped_missing_median: int
    rows_dropped_excluded_category: int
    duplicate_category_age_rows: int
    aggregation_method: str


def normalize_column_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def auto_map_columns(df: pd.DataFrame) -> dict[str, str | None]:
    normalized_to_original = {normalize_column_name(col): col for col in df.columns}
    output: dict[str, str | None] = {}

    for logical_name, aliases in AUTO_COLUMN_ALIASES.items():
        matched = None

        for alias in aliases:
            alias_norm = normalize_column_name(alias)
            if alias_norm in normalized_to_original:
                matched = normalized_to_original[alias_norm]
                break

        if matched is None:
            for col in df.columns:
                col_norm = normalize_column_name(col)
                if logical_name == "category" and any(token in col_norm for token in ["healthsegment", "segment", "category"]):
                    matched = col
                    break
                if logical_name == "age" and col_norm in {"age", "vehicleage", "assetage", "unitage"}:
                    matched = col
                    break
                if logical_name == "median_repair_pct" and "median" in col_norm:
                    matched = col
                    break

        output[logical_name] = matched

    return output


def parse_percent(value: object) -> float:
    """
    Convert percentage-like values to percentage points.

    Examples:
    - "1.45%" -> 1.45
    - 0.0145 -> 1.45 for Excel percentage-formatted numeric cells
    - 1.45 -> 1.45
    """
    if value is None or pd.isna(value):
        return np.nan

    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return np.nan

        has_percent = "%" in raw
        cleaned = (
            raw.replace("%", "")
            .replace(",", "")
            .replace("$", "")
            .replace("−", "-")
            .strip()
        )

        if cleaned == "":
            return np.nan

        try:
            number = float(cleaned)
        except ValueError:
            return np.nan

        return number if has_percent else _numeric_to_percent_points(number)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan

    return _numeric_to_percent_points(number)


def _numeric_to_percent_points(number: float) -> float:
    if -1 <= number <= 1:
        return number * 100
    return number


def load_table(file_name: str, file_bytes: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    lower_name = file_name.lower()

    if lower_name.endswith(".csv"):
        return pd.read_csv(BytesIO(file_bytes))

    if lower_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name)

    raise ValueError("Unsupported file type. Use CSV, XLSX, or XLS.")


def clean_repair_age_data(
    raw_df: pd.DataFrame,
    category_col: str,
    age_col: str,
    median_col: str,
    excluded_categories: Iterable[str] | None = None,
    aggregation_method: str = "median",
) -> CleanResult:
    if raw_df.empty:
        return CleanResult(
            data=pd.DataFrame(columns=["category", "age", "median_repair_pct"]),
            rows_in=0,
            rows_out=0,
            rows_dropped_missing_category=0,
            rows_dropped_missing_age=0,
            rows_dropped_missing_median=0,
            rows_dropped_excluded_category=0,
            duplicate_category_age_rows=0,
            aggregation_method=aggregation_method,
        )

    missing_cols = [col for col in [category_col, age_col, median_col] if col not in raw_df.columns]
    if missing_cols:
        raise KeyError(f"Missing required column(s): {missing_cols}")

    df = raw_df[[category_col, age_col, median_col]].copy()
    df.columns = ["category", "age", "median_repair_pct"]

    rows_in = len(df)

    df["category"] = (
        df["category"]
        .astype("string")
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    )
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["median_repair_pct"] = df["median_repair_pct"].apply(parse_percent)

    missing_category_mask = df["category"].isna()
    rows_dropped_missing_category = int(missing_category_mask.sum())
    df = df.loc[~missing_category_mask].copy()

    missing_age_mask = df["age"].isna()
    rows_dropped_missing_age = int(missing_age_mask.sum())
    df = df.loc[~missing_age_mask].copy()

    missing_median_mask = df["median_repair_pct"].isna()
    rows_dropped_missing_median = int(missing_median_mask.sum())
    df = df.loc[~missing_median_mask].copy()

    df["age"] = df["age"].round().astype(int)
    df = df.loc[df["median_repair_pct"] >= 0].copy()

    rows_dropped_excluded_category = 0
    if excluded_categories:
        excluded_normalized = {str(x).strip().lower() for x in excluded_categories}
        excluded_mask = df["category"].str.lower().isin(excluded_normalized)
        rows_dropped_excluded_category = int(excluded_mask.sum())
        df = df.loc[~excluded_mask].copy()

    duplicate_category_age_rows = int(df.duplicated(subset=["category", "age"], keep=False).sum())

    if aggregation_method not in {"median", "mean", "max", "min"}:
        raise ValueError("aggregation_method must be one of: median, mean, max, min")

    clean_df = (
        df.groupby(["category", "age"], as_index=False)
        .agg(median_repair_pct=("median_repair_pct", aggregation_method))
        .sort_values(["category", "age"])
        .reset_index(drop=True)
    )

    return CleanResult(
        data=clean_df,
        rows_in=rows_in,
        rows_out=len(clean_df),
        rows_dropped_missing_category=rows_dropped_missing_category,
        rows_dropped_missing_age=rows_dropped_missing_age,
        rows_dropped_missing_median=rows_dropped_missing_median,
        rows_dropped_excluded_category=rows_dropped_excluded_category,
        duplicate_category_age_rows=duplicate_category_age_rows,
        aggregation_method=aggregation_method,
    )


def _weighted_average(values: np.ndarray) -> float:
    clean_values = values[~np.isnan(values)]
    if len(clean_values) == 0:
        return np.nan
    weights = np.arange(1, len(clean_values) + 1, dtype=float)
    return float(np.average(clean_values, weights=weights))


def apply_smoothing(
    clean_df: pd.DataFrame,
    method: str = "centered_moving_average",
    window: int = 3,
    min_periods: int = 1,
    alpha: float = 0.35,
) -> pd.DataFrame:
    """
    Add smoothed_median_repair_pct to a clean category-age DataFrame.

    Smoothing is calculated independently within each category and never overwrites
    median_repair_pct.
    """
    if clean_df.empty:
        out = clean_df.copy()
        out["smoothed_median_repair_pct"] = pd.Series(dtype=float)
        out["smoothing_method"] = method
        return out

    if method not in {
        "none",
        "centered_moving_average",
        "trailing_moving_average",
        "weighted_moving_average",
        "exponential",
    }:
        raise ValueError(
            "method must be one of: none, centered_moving_average, "
            "trailing_moving_average, weighted_moving_average, exponential"
        )

    if window < 1:
        raise ValueError("window must be >= 1")
    if min_periods < 1:
        raise ValueError("min_periods must be >= 1")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be > 0 and <= 1")

    out_parts = []

    for category, grp in clean_df.sort_values(["category", "age"]).groupby("category", sort=False):
        g = grp.sort_values("age").copy()
        values = g["median_repair_pct"].astype(float)

        if method == "none":
            smoothed = values
        elif method == "centered_moving_average":
            smoothed = values.rolling(window=window, min_periods=min_periods, center=True).mean()
        elif method == "trailing_moving_average":
            smoothed = values.rolling(window=window, min_periods=min_periods, center=False).mean()
        elif method == "weighted_moving_average":
            smoothed = values.rolling(window=window, min_periods=min_periods, center=False).apply(
                _weighted_average,
                raw=True,
            )
        elif method == "exponential":
            smoothed = values.ewm(alpha=alpha, adjust=False).mean()
        else:
            raise AssertionError("Unhandled smoothing method")

        g["smoothed_median_repair_pct"] = smoothed.astype(float)
        g["smoothing_method"] = method
        out_parts.append(g)

    return pd.concat(out_parts, ignore_index=True).sort_values(["category", "age"]).reset_index(drop=True)


def build_category_summary(clean_df: pd.DataFrame, value_col: str = "median_repair_pct") -> pd.DataFrame:
    records = []

    if value_col not in clean_df.columns:
        raise KeyError(f"{value_col!r} is not in clean_df")

    for category, grp in clean_df.sort_values("age").groupby("category"):
        grp = grp.sort_values("age").reset_index(drop=True)
        first = grp.iloc[0]
        last = grp.iloc[-1]
        peak = grp.loc[grp[value_col].idxmax()]

        age_span = int(last["age"] - first["age"])
        change_pp = float(last[value_col] - first[value_col])
        avg_change_per_age = change_pp / age_span if age_span else 0.0

        records.append(
            {
                "category": category,
                "points": int(len(grp)),
                "first_age": int(first["age"]),
                "first_value": float(first[value_col]),
                "last_age": int(last["age"]),
                "last_value": float(last[value_col]),
                "peak_age": int(peak["age"]),
                "peak_value": float(peak[value_col]),
                "change_pp": change_pp,
                "avg_change_per_age": float(avg_change_per_age),
            }
        )

    return pd.DataFrame(records)
