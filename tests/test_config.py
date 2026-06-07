from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_quant.config import (
    BacktestConfig,
    load_config_overrides_from_toml,
    load_sweep_overrides_from_toml,
)


class ConfigTests(unittest.TestCase):
    def test_loads_toml_config_and_resolves_relative_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
top_n = 5
price_field = "adjusted_close"
output_dir = "reports"
symbol_name_csv = "a_share_symbols.csv"

[backtest.factor_weights]
momentum = 0.7
low_volatility = 0.3
""".strip(),
                encoding="utf-8",
            )

            overrides = load_config_overrides_from_toml(config_path)

            self.assertEqual(5, overrides["top_n"])
            self.assertEqual("adjusted_close", overrides["price_field"])
            self.assertEqual((config_path.parent / "reports").resolve(), overrides["output_dir"])
            self.assertEqual((config_path.parent / "a_share_symbols.csv").resolve(), overrides["symbol_name_csv"])
            self.assertEqual(0.7, overrides["factor_weights"]["momentum"])

    def test_rejects_toml_without_backtest_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
top_n = 5
price_field = "adjusted_close"
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"\[backtest\]"):
                load_config_overrides_from_toml(config_path)

    def test_rejects_unknown_backtest_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
top_n = 5
typo_top_n = 3
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unsupported backtest field"):
                load_config_overrides_from_toml(config_path)

    def test_rejects_unknown_top_level_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
top_n = 5

[database]
url = "sqlite:///ignored.db"
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unsupported config field"):
                load_config_overrides_from_toml(config_path)

    def test_rejects_wrong_backtest_field_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
top_n = "5"
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "top_n must be an integer"):
                load_config_overrides_from_toml(config_path)

    def test_rejects_wrong_factor_weight_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]

[backtest.factor_weights]
momentum = "0.7"
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "factor_weights.momentum must be a number"):
                load_config_overrides_from_toml(config_path)

    def test_rejects_wrong_sweep_value_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]

[sweep]
rebalance_every_n_days = [5, "10"]
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "rebalance_every_n_days must be an integer"):
                load_sweep_overrides_from_toml(config_path)

    def test_rejects_unsupported_factor_weight_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported factors"):
            BacktestConfig(
                factor_weights={
                    "momentum": 0.5,
                    "alpha101": 0.5,
                }
            )


if __name__ == "__main__":
    unittest.main()
