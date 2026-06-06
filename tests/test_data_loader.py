from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_quant.data_loader import load_price_bars_from_csv


class DataLoaderTests(unittest.TestCase):
    def test_loads_optional_fields_and_normalizes_symbol(self) -> None:
        csv_content = """date,symbol,close,volume,tradable
2024-01-02, aaa ,10.5,1000,1
2024-01-03,AAA,10.8,1100,true
"""
        path = _write_temp_csv(csv_content)

        bars = load_price_bars_from_csv(path)

        self.assertEqual(2, len(bars))
        self.assertEqual("AAA", bars[0].symbol)
        self.assertEqual(1000.0, bars[0].volume)
        self.assertTrue(bars[0].tradable)

    def test_rejects_duplicate_symbol_date(self) -> None:
        csv_content = """date,symbol,close
2024-01-02,AAA,10
2024-01-02,AAA,11
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "duplicate bar"):
            load_price_bars_from_csv(path)

    def test_rejects_non_positive_close(self) -> None:
        csv_content = """date,symbol,close
2024-01-02,AAA,0
"""
        path = _write_temp_csv(csv_content)

        with self.assertRaisesRegex(ValueError, "close must be > 0"):
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
