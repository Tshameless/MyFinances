from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from python_quant.data_quality import (
    build_price_data_quality_report,
    save_data_quality_report,
)
from python_quant.models import PriceBar


class DataQualityTests(unittest.TestCase):
    def test_builds_symbol_quality_report(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, adjusted_close=10),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=12, adjusted_close=12),
            PriceBar(date=date(2024, 1, 2), symbol="600519", close=100, volume=0),
        ]

        report = build_price_data_quality_report(bars, abnormal_return_threshold=0.11)

        self.assertEqual(3, report.summary["row_count"])
        self.assertEqual(2, report.summary["symbol_count"])
        row_by_symbol = {row.symbol: row for row in report.symbols}
        self.assertEqual(1, row_by_symbol["600519"].missing_common_dates)
        self.assertEqual(1, row_by_symbol["600519"].missing_adjusted_close)
        self.assertEqual(1, row_by_symbol["600519"].zero_volume_days)
        self.assertEqual(1, row_by_symbol["000001"].abnormal_return_days)

    def test_saves_quality_report_csv_and_json(self) -> None:
        report = build_price_data_quality_report(
            [
                PriceBar(date=date(2024, 1, 2), symbol="000001", close=10),
                PriceBar(date=date(2024, 1, 3), symbol="000001", close=10.2),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_data_quality_report(report, output_dir)

            self.assertTrue(paths["data_quality_report_csv"].exists())
            self.assertTrue(paths["data_quality_report_json"].exists())
            content = paths["data_quality_report_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("missing_adjusted_close", content)
            payload = json.loads(paths["data_quality_report_json"].read_text(encoding="utf-8"))
            self.assertEqual(1, payload["summary"]["symbol_count"])


if __name__ == "__main__":
    unittest.main()
