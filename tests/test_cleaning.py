from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fleet_repair_age import (
    auto_map_columns,
    build_category_summary,
    clean_repair_age_data,
    parse_percent,
)


class TestRepairAgeCleaning(unittest.TestCase):
    def test_parse_percent_string_with_symbol(self):
        self.assertAlmostEqual(parse_percent("1.45%"), 1.45)

    def test_parse_percent_excel_fraction(self):
        self.assertAlmostEqual(parse_percent(0.0145), 1.45)

    def test_parse_percent_numeric_percent_points(self):
        self.assertAlmostEqual(parse_percent(1.45), 1.45)

    def test_auto_map_columns(self):
        df = pd.DataFrame(
            {
                "Health Segments": ["Trailers"],
                "Age": [0],
                "Median": ["1.45%"],
            }
        )
        mapping = auto_map_columns(df)
        self.assertEqual(mapping["category"], "Health Segments")
        self.assertEqual(mapping["age"], "Age")
        self.assertEqual(mapping["median_repair_pct"], "Median")

    def test_clean_drops_missing_age_and_excludes_category(self):
        df = pd.DataFrame(
            {
                "Health Segments": ["Trailers", "Exclude", "Service / Light Fleet"],
                "Age": [None, 1, 0],
                "Median": ["1.45%", "1.21%", "4.20%"],
            }
        )
        result = clean_repair_age_data(
            df,
            category_col="Health Segments",
            age_col="Age",
            median_col="Median",
            excluded_categories=["Exclude"],
        )
        self.assertEqual(result.rows_dropped_missing_age, 1)
        self.assertEqual(result.rows_dropped_excluded_category, 1)
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data.iloc[0]["category"], "Service / Light Fleet")
        self.assertAlmostEqual(result.data.iloc[0]["median_repair_pct"], 4.20)

    def test_duplicate_category_age_aggregation(self):
        df = pd.DataFrame(
            {
                "Health Segments": ["Trailers", "Trailers"],
                "Age": [0, 0],
                "Median": ["10%", "20%"],
            }
        )
        result = clean_repair_age_data(
            df,
            category_col="Health Segments",
            age_col="Age",
            median_col="Median",
            aggregation_method="mean",
        )
        self.assertEqual(result.duplicate_category_age_rows, 2)
        self.assertEqual(len(result.data), 1)
        self.assertAlmostEqual(result.data.iloc[0]["median_repair_pct"], 15.0)

    def test_category_summary(self):
        clean_df = pd.DataFrame(
            {
                "category": ["Trailers", "Trailers", "Trailers"],
                "age": [0, 1, 2],
                "median_repair_pct": [10.0, 5.0, 20.0],
            }
        )
        summary = build_category_summary(clean_df)
        row = summary.iloc[0]
        self.assertEqual(row["first_age"], 0)
        self.assertEqual(row["last_age"], 2)
        self.assertEqual(row["peak_age"], 2)
        self.assertAlmostEqual(row["change_pp"], 10.0)
        self.assertAlmostEqual(row["avg_change_per_age"], 5.0)


if __name__ == "__main__":
    unittest.main()
