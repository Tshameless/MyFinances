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
selection_mode = "bottom"
score_source = "external"
max_group_positions = 1
rolling_risk_window = 15
execution_delay_days = 1
max_allowed_drawdown = 0.25
max_allowed_daily_var = 0.04
min_allowed_rolling_return = -0.12
min_allowed_fill_rate = 0.65
min_allowed_execution_price_coverage = 0.98
min_allowed_factor_score_coverage = 0.90
max_allowed_market_constraint_rate = 0.40
max_allowed_position_weight = 0.45
max_allowed_group_weight = 0.55
max_allowed_attribution_residual = 0.03
max_allowed_factor_correlation = 0.85
max_allowed_rebalance_changes = 2.5
min_allowed_holding_days = 4.0
price_field = "adjusted_close"
execution_price_field = "vwap"
output_dir = "reports"
symbol_name_csv = "a_share_symbols.csv"
stock_pool_csv = "stock_pool.csv"
symbol_group_csv = "symbol_groups.csv"
factor_score_csv = "factor_scores.csv"
infer_limit_rate_by_symbol = true
forward_fill_suspended_bars = true
growth_limit_up_down_rate = 0.2
buy_commission_rate = 0.0002
sell_commission_rate = 0.0004
market_impact_coefficient = 0.15
market_impact_exponent = 0.5
target_cash_weight = 0.10
max_position_weight = 0.25

[backtest.factor_weights]
momentum = 0.7
low_volatility = 0.3
""".strip(),
                encoding="utf-8",
            )

            overrides = load_config_overrides_from_toml(config_path)

            self.assertEqual(5, overrides["top_n"])
            self.assertEqual("bottom", overrides["selection_mode"])
            self.assertEqual("external", overrides["score_source"])
            self.assertEqual(1, overrides["max_group_positions"])
            self.assertEqual(15, overrides["rolling_risk_window"])
            self.assertEqual(1, overrides["execution_delay_days"])
            self.assertEqual(0.25, overrides["max_allowed_drawdown"])
            self.assertEqual(0.04, overrides["max_allowed_daily_var"])
            self.assertEqual(-0.12, overrides["min_allowed_rolling_return"])
            self.assertEqual(0.65, overrides["min_allowed_fill_rate"])
            self.assertEqual(0.98, overrides["min_allowed_execution_price_coverage"])
            self.assertEqual(0.90, overrides["min_allowed_factor_score_coverage"])
            self.assertEqual(0.40, overrides["max_allowed_market_constraint_rate"])
            self.assertEqual(0.45, overrides["max_allowed_position_weight"])
            self.assertEqual(0.55, overrides["max_allowed_group_weight"])
            self.assertEqual(0.03, overrides["max_allowed_attribution_residual"])
            self.assertEqual(0.85, overrides["max_allowed_factor_correlation"])
            self.assertEqual(2.5, overrides["max_allowed_rebalance_changes"])
            self.assertEqual(4.0, overrides["min_allowed_holding_days"])
            self.assertEqual("adjusted_close", overrides["price_field"])
            self.assertEqual("vwap", overrides["execution_price_field"])
            self.assertEqual((config_path.parent / "reports").resolve(), overrides["output_dir"])
            self.assertEqual((config_path.parent / "a_share_symbols.csv").resolve(), overrides["symbol_name_csv"])
            self.assertEqual((config_path.parent / "stock_pool.csv").resolve(), overrides["stock_pool_csv"])
            self.assertEqual((config_path.parent / "symbol_groups.csv").resolve(), overrides["symbol_group_csv"])
            self.assertEqual((config_path.parent / "factor_scores.csv").resolve(), overrides["factor_score_csv"])
            self.assertTrue(overrides["infer_limit_rate_by_symbol"])
            self.assertTrue(overrides["forward_fill_suspended_bars"])
            self.assertEqual(0.2, overrides["growth_limit_up_down_rate"])
            self.assertEqual(0.0002, overrides["buy_commission_rate"])
            self.assertEqual(0.0004, overrides["sell_commission_rate"])
            self.assertEqual(0.15, overrides["market_impact_coefficient"])
            self.assertEqual(0.5, overrides["market_impact_exponent"])
            self.assertEqual(0.10, overrides["target_cash_weight"])
            self.assertEqual(0.25, overrides["max_position_weight"])
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

    def test_loads_date_range_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
start_date = "2024-01-10"
end_date = "2024-02-20"
""".strip(),
                encoding="utf-8",
            )

            overrides = load_config_overrides_from_toml(config_path)

            self.assertEqual("2024-01-10", overrides["start_date"].isoformat())
            self.assertEqual("2024-02-20", overrides["end_date"].isoformat())

    def test_rejects_inverted_date_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "start_date"):
            BacktestConfig(start_date=__import__("datetime").date(2024, 2, 1), end_date=__import__("datetime").date(2024, 1, 1))

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

    def test_rejects_invalid_max_position_weight(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_position_weight"):
            BacktestConfig(max_position_weight=0.0)
        with self.assertRaisesRegex(ValueError, "max_position_weight"):
            BacktestConfig(max_position_weight=1.1)

    def test_rejects_invalid_target_cash_weight(self) -> None:
        with self.assertRaisesRegex(ValueError, "target_cash_weight"):
            BacktestConfig(target_cash_weight=-0.1)
        with self.assertRaisesRegex(ValueError, "target_cash_weight"):
            BacktestConfig(target_cash_weight=1.0)

    def test_rejects_invalid_max_group_positions(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_group_positions"):
            BacktestConfig(max_group_positions=0)

    def test_rejects_invalid_rolling_risk_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "rolling"):
            BacktestConfig(rolling_risk_window=0)

    def test_rejects_invalid_execution_delay_days(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution_delay_days"):
            BacktestConfig(execution_delay_days=-1)

    def test_rejects_invalid_risk_gate_thresholds(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_allowed_drawdown"):
            BacktestConfig(max_allowed_drawdown=0.0)
        with self.assertRaisesRegex(ValueError, "max_allowed_daily_var"):
            BacktestConfig(max_allowed_daily_var=1.1)
        with self.assertRaisesRegex(ValueError, "min_allowed_rolling_return"):
            BacktestConfig(min_allowed_rolling_return=-1.1)
        with self.assertRaisesRegex(ValueError, "min_allowed_fill_rate"):
            BacktestConfig(min_allowed_fill_rate=1.1)
        with self.assertRaisesRegex(ValueError, "min_allowed_execution_price_coverage"):
            BacktestConfig(min_allowed_execution_price_coverage=1.1)
        with self.assertRaisesRegex(ValueError, "min_allowed_factor_score_coverage"):
            BacktestConfig(min_allowed_factor_score_coverage=1.1)
        with self.assertRaisesRegex(ValueError, "max_allowed_market_constraint_rate"):
            BacktestConfig(max_allowed_market_constraint_rate=1.1)
        with self.assertRaisesRegex(ValueError, "max_allowed_position_weight"):
            BacktestConfig(max_allowed_position_weight=0.0)
        with self.assertRaisesRegex(ValueError, "max_allowed_group_weight"):
            BacktestConfig(max_allowed_group_weight=0.0)
        with self.assertRaisesRegex(ValueError, "max_allowed_attribution_residual"):
            BacktestConfig(max_allowed_attribution_residual=1.1)
        with self.assertRaisesRegex(ValueError, "max_allowed_factor_correlation"):
            BacktestConfig(max_allowed_factor_correlation=1.1)
        with self.assertRaisesRegex(ValueError, "max_allowed_rebalance_changes"):
            BacktestConfig(max_allowed_rebalance_changes=-0.1)
        with self.assertRaisesRegex(ValueError, "min_allowed_holding_days"):
            BacktestConfig(min_allowed_holding_days=-0.1)
        with self.assertRaisesRegex(ValueError, "market_impact_exponent"):
            BacktestConfig(market_impact_exponent=0.0)

    def test_rejects_invalid_execution_price_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution_price_field"):
            BacktestConfig(execution_price_field="high")

    def test_rejects_invalid_selection_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection_mode"):
            BacktestConfig(selection_mode="middle")

    def test_rejects_invalid_score_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "score_source"):
            BacktestConfig(score_source="mixed")

    def test_loads_custom_factor_script(self) -> None:
        import tempfile
        from python_quant.factor_registry import get_registered_factors
        
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
from python_quant.factor_registry import register_factor
from python_quant.config import BacktestConfig

@register_factor("custom_unit_test_factor")
def compute_custom_unit_test(closes: list[float], config: BacktestConfig) -> float:
    return closes[-1] * 2.0
""".strip())
            f.flush()
            temp_file_path = Path(f.name)
            
        try:
            config = BacktestConfig(
                custom_factors_py=temp_file_path,
                factor_weights={"custom_unit_test_factor": 1.0}
            )
            self.assertIn("custom_unit_test_factor", get_registered_factors())
            self.assertEqual(config.custom_factors_py, temp_file_path.resolve())
        finally:
            import os
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
