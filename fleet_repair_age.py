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


@dataclass(frozen=True)
class CleanResult:
    data: pd.DataFrame
    rows_in: int
    rows_out: int
    rows_dropped_missing_category: int
    rows_dropped_missing_age: int
    rows_dropped_missing_median: int
    rows_dropped_negative_median: int
    rows_dropped_excluded_category: int
    duplicate_category_age_rows: int
    aggregation_method: str


def normalize_column_name(name: object) -> str:
    """Normalize a column name for tolerant matching."""
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def auto_map_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Infer category, age, and median repair percentage columns from common names."""
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
                if logical_name == "category" and any(
                    token in col_norm for token in ["healthsegment", "segment", "category"]
                ):
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

    Examples
    --------
    "1.45%" -> 1.45
    0.0145   -> 1.45  # Excel percentage-formatted numeric cell
    1.45     -> 1.45
    "1,234%" -> 1234.0
    "--" or blank -> NaN
    "Unknown" -> NaN
    "(1.45%)" -> -1.45
    """
    if value is None or pd.isna(value):
        return np.nan

    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return np.nan

        if raw.lower() in {"nan", "none", "null", "unknown", "n/a", "na", "--", "-"}:
            return np.nan

        has_percent = "%" in raw
        is_parentheses_negative = raw.startswith("(") and raw.endswith(")")
        cleaned = (
            raw.replace("%", "")
            .replace(",", "")
            .replace("$", "")
            .replace("−", "-")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )

        if cleaned == "":
            return np.nan

        try:
            number = float(cleaned)
        except ValueError:
            return np.nan

        if is_parentheses_negative:
            number = -abs(number)

        return number if has_percent else _numeric_to_percent_points(number)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan

    return _numeric_to_percent_points(number)


def _numeric_to_percent_points(number: float) -> float:
    """Treat numeric values from -1 to 1 as Excel-style percentages/fractions."""
    if -1 <= number <= 1:
        return number * 100
    return number


def load_table(file_name: str, file_bytes: bytes, sheet_name: str | None = None) -> pd.DataFrame:
    """Load CSV or Excel bytes into a DataFrame."""
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
    """Clean and aggregate the uploaded repair-age data for plotting."""
    if raw_df.empty:
        return CleanResult(
            data=pd.DataFrame(columns=["category", "age", "median_repair_pct"]),
            rows_in=0,
            rows_out=0,
            rows_dropped_missing_category=0,
            rows_dropped_missing_age=0,
            rows_dropped_missing_median=0,
            rows_dropped_negative_median=0,
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

    negative_median_mask = df["median_repair_pct"] < 0
    rows_dropped_negative_median = int(negative_median_mask.sum())
    df = df.loc[~negative_median_mask].copy()

    # For repair-age curves, ages are treated as discrete year buckets.
    df["age"] = df["age"].round().astype(int)

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
        rows_dropped_negative_median=rows_dropped_negative_median,
        rows_dropped_excluded_category=rows_dropped_excluded_category,
        duplicate_category_age_rows=duplicate_category_age_rows,
        aggregation_method=aggregation_method,
    )


def build_category_summary(clean_df: pd.DataFrame) -> pd.DataFrame:
    """Build first/latest/peak trend stats for each category."""
    records = []

    for category, grp in clean_df.sort_values("age").groupby("category"):
        grp = grp.sort_values("age").reset_index(drop=True)
        first = grp.iloc[0]
        last = grp.iloc[-1]
        peak = grp.loc[grp["median_repair_pct"].idxmax()]

        age_span = int(last["age"] - first["age"])
        change_pp = float(last["median_repair_pct"] - first["median_repair_pct"])
        avg_change_per_age = change_pp / age_span if age_span else 0.0

        records.append(
            {
                "category": category,
                "points": int(len(grp)),
                "first_age": int(first["age"]),
                "first_value": float(first["median_repair_pct"]),
                "last_age": int(last["age"]),
                "last_value": float(last["median_repair_pct"]),
                "peak_age": int(peak["age"]),
                "peak_value": float(peak["median_repair_pct"]),
                "change_pp": change_pp,
                "avg_change_per_age": float(avg_change_per_age),
            }
        )

    return pd.DataFrame(records)
