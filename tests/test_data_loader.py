from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_quant.data_loader import load_benchmark_bars_from_csv, load_price_bars_from_csv


class DataLoaderTests(unittest.TestCase):
    def test_loads_optional_fields_and_normalizes_symbol(self) -> None:
        csv_content = """date,symbol,close,adjusted_close,volume,can_buy,can_sell
2024-01-02,000001,10.5,11.0,1000,0,1
2024-01-03,000001,10.8,11.2,1100,true,true
"""
        path = _write_temp_csv(csv_content)

        bars = load_price_bars_from_csv(path)

        self.assertEqual(2, len(bars))
        self.assertEqual("000001", bars[0].symbol)
        self.assertEqual(11.0, bars[0].adjusted_close)
        self.assertEqual(1000.0, bars[0].volume)
        self.assertFalse(bars[0].can_buy)
        self.assertTrue(bars[0].can_sell)

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
