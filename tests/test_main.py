from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_quant.config import load_sweep_overrides_from_toml
from python_quant.main import (
    _build_backtest_config,
    _build_batch_row,
    _config_hash,
    _expand_sweep_combinations,
    main,
)
from python_quant.models import BacktestMetrics, BacktestResult
from python_quant.sample_data import generate_demo_bars


class MainTests(unittest.TestCase):
    def test_parser_help_keeps_chinese_text_readable(self) -> None:
        from python_quant.main import build_parser

        help_text = build_parser().format_help()

        self.assertIn("运行 MyFinances A 股量化回测工具", help_text)
        self.assertIn("使用内置演示数据", help_text)
        self.assertIn("批量扫描结果的排序指标", help_text)

    def test_demo_cli_run_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            output_dir = Path(temp_dir) / "reports"
            config_path.write_text(
                f"""
[backtest]
initial_cash = 1000000
top_n = 2
lookback_momentum = 3
lookback_mean_reversion = 2
lookback_volatility = 3
rebalance_every_n_days = 2
commission_rate = 0
slippage_rate = 0
stamp_duty_rate = 0
price_field = "adjusted_close"
output_dir = "{output_dir.as_posix()}"
""".strip(),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with (
                contextlib.redirect_stdout(buffer),
            ):
                exit_code = main(["--demo", "--config", str(config_path)])

            manifest_path = output_dir / "run_manifest.json"
            self.assertTrue(manifest_path.exists())
            self.assertTrue((output_dir / "equity_curve.csv").exists())
            self.assertTrue((output_dir / "rebalance_log.csv").exists())
            self.assertTrue((output_dir / "report.html").exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["inputs"]["demo"])
            self.assertEqual(2, manifest["config"]["top_n"])
            self.assertGreater(manifest["metrics"]["periods"], 0)
            self.assertIn("HTML 报告已保存", buffer.getvalue())
            self.assertEqual(0, exit_code)

    def test_cli_reports_expected_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "bad.toml"
            config_path.write_text(
                """
[backtest]
top_n = "2"
""".strip(),
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as raised,
            ):
                main(["--demo", "--config", str(config_path)])

            self.assertEqual(2, raised.exception.code)
            self.assertIn("top_n must be an integer", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_csv_cli_run_with_benchmark_writes_reproducible_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            price_csv = temp_path / "prices.csv"
            benchmark_csv = temp_path / "benchmark.csv"
            config_path = temp_path / "backtest.toml"
            output_dir = temp_path / "reports"

            _write_price_csv(price_csv)
            _write_benchmark_csv(benchmark_csv)
            config_path.write_text(
                f"""
[backtest]
initial_cash = 1000000
top_n = 2
lookback_momentum = 3
lookback_mean_reversion = 2
lookback_volatility = 3
rebalance_every_n_days = 2
commission_rate = 0
slippage_rate = 0
stamp_duty_rate = 0
price_field = "adjusted_close"
output_dir = "{output_dir.as_posix()}"
""".strip(),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--csv",
                        str(price_csv),
                        "--benchmark-csv",
                        str(benchmark_csv),
                        "--config",
                        str(config_path),
                    ]
                )

            self.assertEqual(0, exit_code)
            manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["inputs"]["demo"])
            self.assertEqual(str(price_csv.resolve()), manifest["input_files"]["csv"]["path"])
            self.assertEqual(
                str(benchmark_csv.resolve()),
                manifest["input_files"]["benchmark_csv"]["path"],
            )
            self.assertIsNotNone(manifest["metrics"]["benchmark_total_return"])
            equity_content = (output_dir / "equity_curve.csv").read_text(encoding="utf-8-sig")
            self.assertIn("基准权益 / benchmark_equity", equity_content)

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

    def test_build_backtest_config_uses_run_directory_when_output_dir_is_implicit(self) -> None:
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
            output_dir=None,
            factor_weight=None,
        )

        with patch.dict(os.environ, {"MYFINANCES_RUN_TIMESTAMP": "20260102-030405"}):
            config = _build_backtest_config(args)

        self.assertIn("output", config.output_dir.parts)
        self.assertIn("runs", config.output_dir.parts)
        self.assertTrue(config.output_dir.name.startswith("20260102-030405-"))
        self.assertEqual(10 + len("20260102-030405-"), len(config.output_dir.name))

    def test_config_hash_is_stable_and_excludes_output_dir(self) -> None:
        base = {
            "top_n": 3,
            "price_field": "close",
            "output_dir": Path("output/a"),
            "factor_weights": {"momentum": 1.0},
        }
        changed_output = {
            **base,
            "output_dir": Path("output/b"),
        }
        changed_parameter = {
            **base,
            "top_n": 4,
        }

        self.assertEqual(_config_hash(base), _config_hash(changed_output))
        self.assertNotEqual(_config_hash(base), _config_hash(changed_parameter))

def _write_price_csv(path: Path) -> None:
    rows = ["date,symbol,close,adjusted_close"]
    for bar in generate_demo_bars(days=45):
        rows.append(
            f"{bar.date.isoformat()},{bar.symbol},{bar.close:.2f},{bar.adjusted_close:.2f}"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_benchmark_csv(path: Path) -> None:
    dates = sorted({bar.date for bar in generate_demo_bars(days=45)})
    rows = ["date,close,adjusted_close"]
    for index, current_date in enumerate(dates):
        price = 100.0 + index * 0.25
        rows.append(f"{current_date.isoformat()},{price:.2f},{price:.2f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
