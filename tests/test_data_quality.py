from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from python_quant.data_quality import (
    build_benchmark_quality_report,
    build_factor_score_quality_report,
    build_price_data_quality_report,
    build_stock_pool_quality_report,
    build_symbol_group_quality_report,
    save_benchmark_quality_report,
    save_data_quality_report,
    save_factor_score_quality_report,
    save_mapping_quality_report,
    save_stock_pool_quality_report,
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

    def test_counts_suspended_days(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10),
            PriceBar(
                date=date(2024, 1, 3),
                symbol="000001",
                close=10,
                volume=0,
                tradable=False,
                can_buy=False,
                can_sell=False,
                is_suspended=True,
                is_limit_down=True,
                is_st=True,
                limit_rate=0.05,
            ),
            PriceBar(
                date=date(2024, 1, 4),
                symbol="000001",
                close=11,
                open=10.8,
                vwap=10.9,
                is_limit_up=True,
            ),
        ]

        report = build_price_data_quality_report(bars)

        self.assertEqual(1, report.summary["suspended_days"])
        self.assertEqual(1, report.summary["symbols_with_suspended_days"])
        self.assertEqual(1, report.summary["limit_up_days"])
        self.assertEqual(1, report.summary["limit_down_days"])
        self.assertEqual(1, report.summary["st_days"])
        self.assertEqual(1, report.summary["custom_limit_rate_days"])
        self.assertEqual(2, report.summary["missing_open_rows"])
        self.assertEqual(2, report.summary["missing_vwap_rows"])
        self.assertEqual(1, report.summary["untradable_days"])
        self.assertEqual(1, report.summary["cannot_buy_days"])
        self.assertEqual(1, report.summary["cannot_sell_days"])
        self.assertEqual(1, report.symbols[0].suspended_days)
        self.assertEqual(1, report.symbols[0].limit_up_days)
        self.assertEqual(1, report.symbols[0].limit_down_days)
        self.assertEqual(1, report.symbols[0].st_days)
        self.assertEqual(1, report.symbols[0].custom_limit_rate_days)
        self.assertEqual(2, report.symbols[0].missing_open)
        self.assertEqual(2, report.symbols[0].missing_vwap)
        daily_by_date = {row["date"]: row for row in report.daily_counts}
        self.assertEqual(1, daily_by_date["2024-01-03"]["suspended_count"])
        self.assertEqual(1, daily_by_date["2024-01-03"]["limit_down_count"])
        self.assertEqual(1, daily_by_date["2024-01-03"]["st_count"])
        self.assertEqual(1, daily_by_date["2024-01-04"]["limit_up_count"])

    def test_summarizes_execution_price_field_coverage(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, open=9.9),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=11),
            PriceBar(date=date(2024, 1, 4), symbol="000001", close=12, open=11.9),
        ]

        report = build_price_data_quality_report(bars, execution_price_field="open")

        self.assertEqual("open", report.summary["execution_price_field"])
        self.assertEqual(1, report.summary["missing_execution_price_rows"])
        self.assertAlmostEqual(2 / 3, report.summary["execution_price_coverage_rate"])

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
            self.assertIn("missing_open", content)
            self.assertIn("missing_vwap", content)
            self.assertIn("suspended_days", content)
            self.assertIn("limit_up_days", content)
            self.assertIn("limit_down_days", content)
            self.assertIn("st_days", content)
            self.assertIn("custom_limit_rate_days", content)
            payload = json.loads(paths["data_quality_report_json"].read_text(encoding="utf-8"))
            self.assertEqual(1, payload["summary"]["symbol_count"])
            self.assertIn("missing_open_rows", payload["summary"])
            self.assertIn("limit_up_count", payload["daily_counts"][0])

    def test_builds_benchmark_quality_report(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="BENCHMARK", close=100, adjusted_close=100),
            PriceBar(date=date(2024, 1, 4), symbol="BENCHMARK", close=120),
        ]

        report = build_benchmark_quality_report(
            bars,
            expected_dates={date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)},
            abnormal_return_threshold=0.11,
        )

        self.assertEqual(2, report.summary["row_count"])
        self.assertEqual(1, report.summary["missing_expected_dates"])
        self.assertEqual(["2024-01-03"], report.summary["missing_expected_date_list"])
        self.assertEqual(1, report.summary["missing_adjusted_close_rows"])
        self.assertEqual(1, report.summary["abnormal_return_days"])
        self.assertAlmostEqual(0.2, report.summary["max_abs_return"])
        self.assertTrue(report.rows[1].abnormal_return)

    def test_saves_benchmark_quality_report(self) -> None:
        report = build_benchmark_quality_report(
            [
                PriceBar(date=date(2024, 1, 2), symbol="BENCHMARK", close=100),
                PriceBar(date=date(2024, 1, 3), symbol="BENCHMARK", close=101),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_benchmark_quality_report(report, output_dir)

            self.assertTrue(paths["benchmark_quality_report_csv"].exists())
            self.assertTrue(paths["benchmark_quality_report_json"].exists())
            content = paths["benchmark_quality_report_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("abnormal_return", content)
            payload = json.loads(
                paths["benchmark_quality_report_json"].read_text(encoding="utf-8")
            )
            self.assertEqual(2, payload["summary"]["row_count"])

    def test_builds_symbol_group_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_path = Path(temp_dir) / "symbol_groups.csv"
            mapping_path.write_text(
                "symbol,group\n000001,银行\n000001,金融\n600519,\n,空代码\n300001,科技\n",
                encoding="utf-8",
            )

            report = build_symbol_group_quality_report(
                mapping_path,
                expected_symbols={"000001", "600519", "000002"},
            )

            self.assertEqual(5, report.summary["row_count"])
            self.assertEqual(3, report.summary["mapped_symbol_count"])
            self.assertEqual(1, report.summary["duplicate_symbols"])
            self.assertEqual(1, report.summary["blank_symbol_rows"])
            self.assertEqual(1, report.summary["blank_group_rows"])
            self.assertEqual(1, report.summary["missing_expected_symbols"])
            self.assertEqual(["000002"], report.summary["missing_expected_symbol_list"])
            self.assertEqual(["300001"], report.summary["extra_mapped_symbol_list"])
            self.assertTrue(any(row["duplicate_symbol"] for row in report.rows))

    def test_saves_symbol_group_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            mapping_path = output_dir / "symbol_groups.csv"
            mapping_path.write_text("symbol,group\n000001,银行\n", encoding="utf-8")
            report = build_symbol_group_quality_report(mapping_path)

            paths = save_mapping_quality_report(report, output_dir)

            self.assertTrue(paths["symbol_group_quality_report_csv"].exists())
            self.assertTrue(paths["symbol_group_quality_report_json"].exists())
            content = paths["symbol_group_quality_report_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("duplicate_symbol", content)

    def test_builds_stock_pool_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pool_path = Path(temp_dir) / "stock_pool.csv"
            pool_path.write_text(
                "date,symbol\n2024-01-02,000001\n2024-01-02,000001\n2024-01-03,ABCDEF\n,600519\n2024-01-04,\n2024-01-05,300001\n",
                encoding="utf-8",
            )

            report = build_stock_pool_quality_report(
                pool_path,
                expected_symbols={"000001", "600519", "000002"},
            )

            self.assertEqual(6, report.summary["row_count"])
            self.assertEqual(4, report.summary["date_count"])
            self.assertEqual(1, report.summary["duplicate_date_symbol_rows"])
            self.assertEqual(1, report.summary["blank_date_rows"])
            self.assertEqual(1, report.summary["blank_symbol_rows"])
            self.assertEqual(1, report.summary["invalid_symbol_rows"])
            self.assertEqual(["000002"], report.summary["missing_expected_symbol_list"])
            self.assertEqual(["300001", "ABCDEF"], report.summary["extra_mapped_symbol_list"])
            self.assertTrue(any(row["duplicate_date_symbol"] for row in report.rows))

    def test_saves_stock_pool_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pool_path = output_dir / "stock_pool.csv"
            pool_path.write_text("date,symbol\n2024-01-02,000001\n", encoding="utf-8")
            report = build_stock_pool_quality_report(pool_path)

            paths = save_stock_pool_quality_report(report, output_dir)

            self.assertTrue(paths["stock_pool_quality_report_csv"].exists())
            self.assertTrue(paths["stock_pool_quality_report_json"].exists())
            content = paths["stock_pool_quality_report_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("duplicate_date_symbol", content)

    def test_builds_factor_score_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            score_path = Path(temp_dir) / "factor_scores.csv"
            score_path.write_text(
                "date,symbol,score\n"
                "2024-01-02,000001,1.5\n"
                "2024/01/02,000001,2.0\n"
                "2024-01-02,600519,nan\n"
                "2024-01-04,300001,-0.5\n"
                "bad-date,000002,0.1\n"
                "2024-01-03,AAPL,0.2\n"
                "2024-01-03,000001,\n",
                encoding="utf-8",
            )

            report = build_factor_score_quality_report(
                score_path,
                expected_symbols={"000001", "600519", "000002"},
                expected_dates={date(2024, 1, 2), date(2024, 1, 3)},
            )

            self.assertEqual(7, report.summary["row_count"])
            self.assertEqual(3, report.summary["date_count"])
            self.assertEqual(1, report.summary["duplicate_date_symbol_rows"])
            self.assertEqual(1, report.summary["invalid_date_rows"])
            self.assertEqual(1, report.summary["invalid_symbol_rows"])
            self.assertEqual(1, report.summary["invalid_score_rows"])
            self.assertEqual(1, report.summary["blank_score_rows"])
            self.assertEqual(["300001", "AAPL"], report.summary["extra_scored_symbol_list"])
            self.assertEqual(["2024-01-04"], report.summary["extra_score_date_list"])
            self.assertAlmostEqual(1 / 6, report.summary["score_coverage_rate"])
            self.assertAlmostEqual(0.66, report.summary["average_score"])
            self.assertGreater(report.summary["score_stddev"], 0.0)
            self.assertEqual(5, report.summary["unique_score_count"])
            self.assertEqual(0.0, report.summary["duplicate_score_rate"])
            self.assertEqual(0, report.summary["extreme_score_count"])
            self.assertEqual(
                ["2024-01-02", "2024-01-03", "2024-01-04"],
                [row["date"] for row in report.summary["score_distribution_by_date"]],
            )
            first_date_distribution = report.summary["score_distribution_by_date"][0]
            self.assertEqual(2, first_date_distribution["score_count"])
            self.assertAlmostEqual(1.75, first_date_distribution["average_score"])
            self.assertEqual(0.0, first_date_distribution["duplicate_score_rate"])

    def test_saves_factor_score_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            score_path = output_dir / "factor_scores.csv"
            score_path.write_text(
                "date,symbol,score\n2024-01-02,000001,1\n",
                encoding="utf-8",
            )
            report = build_factor_score_quality_report(score_path)

            paths = save_factor_score_quality_report(report, output_dir)

            self.assertTrue(paths["factor_score_quality_report_csv"].exists())
            self.assertTrue(paths["factor_score_quality_report_json"].exists())
            self.assertTrue(paths["factor_score_quality_distribution_by_date_csv"].exists())
            content = paths["factor_score_quality_report_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("invalid_score", content)
            distribution_content = paths["factor_score_quality_distribution_by_date_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("date,score_count", distribution_content)
            self.assertIn("2024-01-02,1", distribution_content)

    def test_factor_score_quality_flags_suspicious_score_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            score_path = Path(temp_dir) / "factor_scores.csv"
            score_path.write_text(
                "date,symbol,score\n"
                "2024-01-02,000001,1\n"
                "2024-01-02,000002,1\n"
                "2024-01-02,000003,1\n"
                "2024-01-02,000004,1\n"
                "2024-01-02,000005,1\n",
                encoding="utf-8",
            )

            report = build_factor_score_quality_report(score_path)

            warnings = report.summary["score_distribution_warnings"]
            self.assertEqual(["2024-01-02"], warnings["low_stddev_score_dates"])
            self.assertEqual(["2024-01-02"], warnings["high_duplicate_score_dates"])
            self.assertEqual(1, warnings["warning_date_count"])


if __name__ == "__main__":
    unittest.main()
