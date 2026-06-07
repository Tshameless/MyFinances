from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from python_quant.config import load_sweep_overrides_from_toml
from python_quant.main import _build_backtest_config, _build_batch_row, _expand_sweep_combinations
from python_quant.models import BacktestMetrics, BacktestResult


class MainTests(unittest.TestCase):
    def test_expands_sweep_combinations(self) -> None:
        combinations = _expand_sweep_combinations(
            {
                "top_n": [2, 3],
                "rebalance_every_n_days": [5, 10],
            }
        )

        self.assertEqual(4, len(combinations))
        self.assertIn({"top_n": 2, "rebalance_every_n_days": 5}, combinations)
        self.assertIn({"top_n": 3, "rebalance_every_n_days": 10}, combinations)

    def test_loads_sweep_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "sweep.toml"
            config_path.write_text(
                """
[backtest]
top_n = 3

[sweep]
top_n = [2, 3]
rebalance_every_n_days = [5, 10]
""".strip(),
                encoding="utf-8",
            )

            sweep = load_sweep_overrides_from_toml(config_path)

            self.assertEqual([2, 3], sweep["top_n"])
            self.assertEqual([5, 10], sweep["rebalance_every_n_days"])

    def test_builds_batch_row(self) -> None:
        metrics = BacktestMetrics(
            total_return=0.1,
            annualized_return=0.2,
            max_drawdown=-0.05,
            volatility=0.15,
            downside_volatility=0.1,
            sharpe=1.1,
            sortino=1.3,
            calmar=4.0,
            win_rate=0.6,
            average_turnover=0.2,
            total_cost=10.0,
            periods=12,
        )
        result = BacktestResult(
            equity_curve=[],
            rebalance_records=[],
            metrics=metrics,
            benchmark_curve=None,
        )
        output_dir = Path("D:/project/MyFinances/output/python/batch_runs/run_001")

        row = _build_batch_row(
            run_id="run_001",
            config=type("ConfigLike", (), {"output_dir": output_dir})(),
            overrides={"top_n": 2},
            result=result,
            artifact_paths={
                "equity_curve_csv": output_dir / "equity_curve.csv",
                "run_manifest_json": output_dir / "run_manifest.json",
            },
        )

        self.assertEqual("run_001", row["run_id"])
        self.assertEqual(2, row["param_top_n"])
        self.assertEqual(str(output_dir / "run_manifest.json"), row["run_manifest_json"])

    def test_build_backtest_config_normalizes_relative_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            args = argparse.Namespace(
                config=None,
                initial_cash=None,
                top_n=None,
                lookback_momentum=None,
                lookback_mean_reversion=None,
                lookback_volatility=None,
                rebalance_days=None,
                commission_rate=None,
                slippage_rate=None,
                stamp_duty_rate=None,
                price_field=None,
                output_dir=temp_dir,
                factor_weight=None,
            )

            config = _build_backtest_config(args)

            self.assertTrue(config.output_dir.is_absolute())


if __name__ == "__main__":
    unittest.main()
