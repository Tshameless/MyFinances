from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from python_quant.data_loader import (
    load_benchmark_bars_from_csv,
    load_factor_scores_from_csv,
    load_price_bars_from_csv,
    load_stock_pool_from_csv,
)
from python_quant.data_store import import_price_csv_to_sqlite
from python_quant.data_store import (
    import_benchmark_csv_to_sqlite,
    import_factor_scores_csv_to_sqlite,
    import_stock_pool_csv_to_sqlite,
    import_symbol_groups_csv_to_sqlite,
)
from python_quant.reporting import load_symbol_group_mapping


class DataLoaderTests(unittest.TestCase):
    def test_loads_optional_fields_and_normalizes_symbol(self) -> None:
        csv_content = """date,symbol,close,adjusted_close,open,vwap,volume,can_buy,can_sell,is_suspended,is_limit_up,is_limit_down,is_st,limit_rate
2024-01-02,000001,10.5,11.0,10.2,10.4,1000,0,1,true,true,false,true,0.05
2024-01-03,000001,10.8,11.2,10.6,10.7,1100,true,true,false,false,false,false,
"""
        path = _write_temp_csv(csv_content)

        bars = load_price_bars_from_csv(path)

        self.assertEqual(2, len(bars))
        self.assertEqual("000001", bars[0].symbol)
        self.assertEqual(11.0, bars[0].adjusted_close)
        self.assertEqual(10.2, bars[0].open)
        self.assertEqual(10.4, bars[0].vwap)
        self.assertEqual(1000.0, bars[0].volume)
        self.assertFalse(bars[0].can_buy)
        self.assertTrue(bars[0].can_sell)
        self.assertTrue(bars[0].is_suspended)
        self.assertTrue(bars[0].is_limit_up)
        self.assertFalse(bars[0].is_limit_down)
        self.assertTrue(bars[0].is_st)
        self.assertEqual(0.05, bars[0].limit_rate)

    def test_imports_and_loads_price_bars_from_sqlite(self) -> None:
        csv_content = """date,symbol,close,adjusted_close,open,vwap,volume,can_buy,can_sell,is_suspended,is_limit_up,is_limit_down,is_st,limit_rate
2024-01-02,000001,10.5,11.0,10.2,10.4,1000,0,1,true,true,false,true,0.05
2024-01-03,000001,10.8,11.2,10.6,10.7,1100,true,true,false,false,false,false,
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "prices.csv"
            db_path = Path(temp_dir) / "prices.sqlite"
            csv_path.write_text(csv_content, encoding="utf-8")

            row_count = import_price_csv_to_sqlite(csv_path, db_path)
            bars = load_price_bars_from_csv(db_path)

            self.assertEqual(2, row_count)
            self.assertEqual(2, len(bars))
            self.assertEqual("000001", bars[0].symbol)
            self.assertEqual(11.0, bars[0].adjusted_close)
            self.assertEqual(10.4, bars[0].vwap)
            self.assertFalse(bars[0].can_buy)
            self.assertTrue(bars[0].is_limit_up)

    def test_imports_auxiliary_csvs_to_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "data.sqlite"
            benchmark_csv = root / "benchmark.csv"
            pool_csv = root / "pool.csv"
            scores_csv = root / "scores.csv"
            groups_csv = root / "groups.csv"
            benchmark_csv.write_text("date,close,adjusted_close\n2024-01-02,10,10.1\n", encoding="utf-8")
            pool_csv.write_text("date,symbol\n2024-01-02,000001\n", encoding="utf-8")
            scores_csv.write_text("date,symbol,score\n2024-01-02,000001,1.5\n", encoding="utf-8")
            groups_csv.write_text("symbol,group\n000001,bank\n", encoding="utf-8")

            self.assertEqual(1, import_benchmark_csv_to_sqlite(benchmark_csv, db_path))
            self.assertEqual(1, import_stock_pool_csv_to_sqlite(pool_csv, db_path))
            self.assertEqual(1, import_factor_scores_csv_to_sqlite(scores_csv, db_path))
            self.assertEqual(1, import_symbol_groups_csv_to_sqlite(groups_csv, db_path))

            self.assertEqual(10.1, load_benchmark_bars_from_csv(db_path)[0].adjusted_close)
            self.assertEqual({"000001"}, load_stock_pool_from_csv(db_path)[date(2024, 1, 2)])
            self.assertEqual(1.5, load_factor_scores_from_csv(db_path)[date(2024, 1, 2)]["000001"])
            self.assertEqual({"000001": "bank"}, load_symbol_group_mapping(db_path))

    def test_loads_benchmark_without_symbol_column(self) -> None:
        csv_content = """date,close,adjusted_close
2024-01-02,10,10.2
2024-01-03,10.1,10.3
"""
        path = _write_temp_csv(csv_content)

        bars = load_benchmark_bars_from_csv(path)

        self.assertEqual("BENCHMARK", bars[0].symbol)
        self.assertEqual(10.2, bars[0].adjusted_close)

    def test_ignores_benchmark_symbol_column_and_uses_fixed_placeholder(self) -> None:
        csv_content = """date,symbol,close,adjusted_close
2024-01-02,000300,10,10.2
2024-01-03,399300,10.1,10.3
"""
        path = _write_temp_csv(csv_content)

        bars = load_benchmark_bars_from_csv(path)

        self.assertEqual("BENCHMARK", bars[0].symbol)
        self.assertEqual("BENCHMARK", bars[1].symbol)

    def test_rejects_duplicate_symbol_date(self) -> None:
        csv_content = """date,symbol,close
2024-01-02,000001,10
2024-01-02,000001,11
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "duplicate bar"):
            load_price_bars_from_csv(path)

    def test_rejects_non_positive_close(self) -> None:
        csv_content = """date,symbol,close
2024-01-02,000001,0
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "close must be > 0"):
            load_price_bars_from_csv(path)

    def test_rejects_non_a_share_symbol(self) -> None:
        csv_content = """date,symbol,close
2024-01-02,AAPL,10
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "unsupported A-share symbol format"):
            load_price_bars_from_csv(path)

    def test_rejects_invalid_limit_rate(self) -> None:
        csv_content = """date,symbol,close,limit_rate
2024-01-02,000001,10,1.5
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "limit_rate must be between 0 and 1"):
            load_price_bars_from_csv(path)

    def test_loads_stock_pool_by_effective_date(self) -> None:
        csv_content = """date,symbol
2024-01-02,000001
2024-01-02,600519
2024/01/10,000002
"""
        path = _write_temp_csv(csv_content)

        stock_pool = load_stock_pool_from_csv(path)

        self.assertEqual({"000001", "600519"}, stock_pool[date(2024, 1, 2)])
        self.assertEqual({"000002"}, stock_pool[date(2024, 1, 10)])

    def test_rejects_invalid_stock_pool_symbol(self) -> None:
        csv_content = """date,symbol
2024-01-02,AAPL
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "unsupported A-share symbol format"):
            load_stock_pool_from_csv(path)

    def test_loads_external_factor_scores(self) -> None:
        csv_content = """date,symbol,score
2024-01-02,000001,1.5
2024-01-02,600519,-0.2
2024/01/03,000001,0
"""
        path = _write_temp_csv(csv_content)

        scores = load_factor_scores_from_csv(path)

        self.assertEqual(1.5, scores[date(2024, 1, 2)]["000001"])
        self.assertEqual(-0.2, scores[date(2024, 1, 2)]["600519"])
        self.assertEqual(0.0, scores[date(2024, 1, 3)]["000001"])

    def test_rejects_duplicate_external_factor_score(self) -> None:
        csv_content = """date,symbol,score
2024-01-02,000001,1
2024-01-02,000001,2
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "duplicate factor score"):
            load_factor_scores_from_csv(path)

    def test_rejects_non_finite_external_factor_score(self) -> None:
        csv_content = """date,symbol,score
2024-01-02,000001,nan
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "score must be finite"):
            load_factor_scores_from_csv(path)


def _write_temp_csv(content: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        "w",
        suffix=".csv",
        delete=False,
        encoding="utf-8",
        newline="",
    )
    with handle:
        handle.write(content)
    return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
