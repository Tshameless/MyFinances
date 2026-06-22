from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_quant.cli_config import build_backtest_config, config_hash
from python_quant.config import load_sweep_overrides_from_toml
from python_quant.main import main
from python_quant.models import BacktestMetrics, BacktestResult
from python_quant.sample_data import generate_demo_bars
from python_quant.workflows import (
    build_batch_row,
    expand_sweep_combinations,
    health_aware_rank_key,
)
from scripts.dev_check import _check_manifest_artifacts


class MainTests(unittest.TestCase):
    def test_parser_help_keeps_chinese_text_readable(self) -> None:
        from python_quant.main import build_parser

        help_text = build_parser().format_help()

        self.assertIn("运行 MyFinances A 股量化回测工具", help_text)
        self.assertIn("使用内置演示数据", help_text)
        self.assertIn("批量扫描结果的排序指标", help_text)
        self.assertIn("--rolling-risk-window", help_text)
        self.assertIn("--forward-fill-suspended-bars", help_text)

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
            self.assertTrue((output_dir / "positions.csv").exists())
            self.assertTrue((output_dir / "trades.csv").exists())
            self.assertTrue((output_dir / "trade_attempts.csv").exists())
            self.assertTrue((output_dir / "factor_scores.csv").exists())
            self.assertTrue((output_dir / "factor_ic.csv").exists())
            self.assertTrue((output_dir / "factor_ic.json").exists())
            self.assertTrue((output_dir / "factor_group_returns.csv").exists())
            self.assertTrue((output_dir / "factor_group_returns.json").exists())
            self.assertTrue((output_dir / "factor_decay.csv").exists())
            self.assertTrue((output_dir / "factor_decay.json").exists())
            self.assertTrue((output_dir / "factor_correlation.csv").exists())
            self.assertTrue((output_dir / "factor_correlation.json").exists())
            self.assertTrue((output_dir / "drawdown.csv").exists())
            self.assertTrue((output_dir / "monthly_returns.csv").exists())
            self.assertTrue((output_dir / "rolling_risk.csv").exists())
            self.assertTrue((output_dir / "relative_performance.csv").exists())
            self.assertTrue((output_dir / "execution_quality.csv").exists())
            self.assertTrue((output_dir / "exposure.csv").exists())
            self.assertTrue((output_dir / "group_exposure.csv").exists())
            self.assertTrue((output_dir / "return_attribution.csv").exists())
            self.assertTrue((output_dir / "cost_attribution.csv").exists())
            self.assertTrue((output_dir / "pnl_ledger.csv").exists())
            self.assertTrue((output_dir / "strategy_health.csv").exists())
            self.assertTrue((output_dir / "strategy_health_gates.csv").exists())
            self.assertTrue((output_dir / "report.html").exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            summary_payload = json.loads((output_dir / "performance_summary.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["inputs"]["demo"])
            self.assertEqual(2, manifest["config"]["top_n"])
            self.assertEqual(20, manifest["config"]["rolling_risk_window"])
            self.assertFalse(manifest["config"]["forward_fill_suspended_bars"])
            self.assertIn("positions_csv", manifest["artifacts"])
            self.assertIn("trades_csv", manifest["artifacts"])
            self.assertIn("trade_attempts_csv", manifest["artifacts"])
            self.assertIn("factor_scores_csv", manifest["artifacts"])
            self.assertIn("factor_ic_csv", manifest["artifacts"])
            self.assertIn("factor_ic_json", manifest["artifacts"])
            self.assertIn("factor_group_returns_csv", manifest["artifacts"])
            self.assertIn("factor_group_returns_json", manifest["artifacts"])
            self.assertIn("factor_decay_csv", manifest["artifacts"])
            self.assertIn("factor_decay_json", manifest["artifacts"])
            self.assertIn("factor_correlation_csv", manifest["artifacts"])
            self.assertIn("factor_correlation_json", manifest["artifacts"])
            self.assertIn("drawdown_csv", manifest["artifacts"])
            self.assertIn("monthly_returns_csv", manifest["artifacts"])
            self.assertIn("rolling_risk_csv", manifest["artifacts"])
            self.assertIn("relative_performance_csv", manifest["artifacts"])
            self.assertIn("execution_quality_csv", manifest["artifacts"])
            self.assertIn("exposure_csv", manifest["artifacts"])
            self.assertIn("group_exposure_csv", manifest["artifacts"])
            self.assertIn("return_attribution_csv", manifest["artifacts"])
            self.assertIn("cost_attribution_csv", manifest["artifacts"])
            self.assertIn("pnl_ledger_csv", manifest["artifacts"])
            self.assertIn("strategy_health_csv", manifest["artifacts"])
            self.assertIn("strategy_health_gates_csv", manifest["artifacts"])
            self.assertIn("split_performance", summary_payload)
            self.assertGreater(manifest["metrics"]["periods"], 0)
            self.assertIn("HTML 报告已保存", buffer.getvalue())
            self.assertIn("因子衰减分析 CSV 已保存", buffer.getvalue())
            self.assertIn("因子相关性矩阵 CSV 已保存", buffer.getvalue())
            self.assertIn("盈亏对账 CSV 已保存", buffer.getvalue())
            self.assertIn("策略健康诊断 CSV 已保存", buffer.getvalue())
            self.assertIn("策略风险闸门 CSV 已保存", buffer.getvalue())
            self.assertEqual(0, exit_code)

    def test_dev_check_validates_manifest_artifact_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            artifact_path = output_dir / "equity_curve.csv"
            artifact_path.write_text("date,equity\n2026-01-01,1\n", encoding="utf-8")

            _check_manifest_artifacts(
                {
                    "artifacts": {"equity_curve_csv": str(artifact_path)},
                    "artifact_files": {
                        "equity_curve_csv": {
                            "path": str(artifact_path),
                            "size_bytes": artifact_path.stat().st_size,
                        }
                    },
                }
            )

            with self.assertRaisesRegex(RuntimeError, "missing file metadata"):
                _check_manifest_artifacts(
                    {
                        "artifacts": {"equity_curve_csv": str(artifact_path)},
                        "artifact_files": {},
                    }
                )

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

    def test_help_still_works_when_scipy_is_unavailable(self) -> None:
        from python_quant.main import build_parser

        with patch.dict(sys.modules, {"scipy": None, "scipy.optimize": None}):
            help_text = build_parser().format_help()

        self.assertIn("运行 MyFinances A 股量化回测工具", help_text)
        self.assertIn("--help", help_text)

    def test_demo_cli_run_without_scipy_for_default_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "reports"

            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch.dict(sys.modules, {"scipy": None, "scipy.optimize": None}),
            ):
                exit_code = main(
                    [
                        "--demo",
                        "--output-dir",
                        str(output_dir),
                        "--lookback-momentum",
                        "3",
                        "--lookback-mean-reversion",
                        "2",
                        "--lookback-volatility",
                        "3",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "run_manifest.json").exists())

    def test_reports_clear_error_when_scipy_optimizer_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as raised,
                patch.dict(sys.modules, {"scipy": None, "scipy.optimize": None}),
            ):
                main(
                    [
                        "--demo",
                        "--allocation-model",
                        "max_sharpe",
                        "--lookback-momentum",
                        "3",
                        "--lookback-mean-reversion",
                        "2",
                        "--lookback-volatility",
                        "3",
                    ]
                )

            self.assertEqual(2, raised.exception.code)
            message = stderr.getvalue()
            self.assertIn("需要可选依赖 scipy", message)
            self.assertIn("equal_weight / score_weighted", message)
            self.assertNotIn("No module named", message)

    def test_csv_cli_run_with_benchmark_writes_reproducible_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            price_csv = temp_path / "prices.csv"
            benchmark_csv = temp_path / "benchmark.csv"
            stock_pool_csv = temp_path / "stock_pool.csv"
            factor_score_csv = temp_path / "factor_scores.csv"
            config_path = temp_path / "backtest.toml"
            output_dir = temp_path / "reports"

            _write_price_csv(price_csv)
            _write_benchmark_csv(benchmark_csv)
            _write_stock_pool_csv(stock_pool_csv)
            factor_score_csv.write_text(
                """date,symbol,score
2024-01-04,000001,-1
2024-01-04,600519,3
2024-01-04,000333,0
2024-01-08,000001,-1
2024-01-08,600519,3
2024-01-08,000333,0
""",
                encoding="utf-8",
            )
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
stock_pool_csv = "{stock_pool_csv.as_posix()}"
factor_score_csv = "{factor_score_csv.as_posix()}"
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
            self.assertEqual(
                str(stock_pool_csv.resolve()),
                manifest["input_files"]["stock_pool_csv"]["path"],
            )
            self.assertEqual(
                str(factor_score_csv.resolve()),
                manifest["input_files"]["factor_score_csv"]["path"],
            )
            self.assertEqual(str(stock_pool_csv.resolve()), manifest["config"]["stock_pool_csv"])
            self.assertEqual(str(factor_score_csv.resolve()), manifest["config"]["factor_score_csv"])
            self.assertIsNotNone(manifest["metrics"]["benchmark_total_return"])
            equity_content = (output_dir / "equity_curve.csv").read_text(encoding="utf-8-sig")
            self.assertIn("基准权益 / benchmark_equity", equity_content)

    def test_demo_walk_forward_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "reports"

            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                exit_code = main(
                    [
                        "--demo",
                        "--walk-forward",
                        "--walk-window",
                        "20",
                        "--walk-step",
                        "10",
                        "--output-dir",
                        str(output_dir),
                        "--lookback-momentum",
                        "3",
                        "--lookback-mean-reversion",
                        "2",
                        "--lookback-volatility",
                        "3",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "walk_forward" / "walk_forward.csv").exists())
            self.assertTrue((output_dir / "walk_forward" / "walk_forward.json").exists())
            self.assertTrue((output_dir / "walk_forward" / "walk_forward_report.html").exists())
            payload = json.loads((output_dir / "walk_forward" / "walk_forward.json").read_text(encoding="utf-8"))
            self.assertGreater(payload["summary"]["windows"], 0)
            self.assertIn("Walk-forward 验证完成", buffer.getvalue())
            self.assertIn("Walk-forward HTML 报告已保存", buffer.getvalue())

    def test_demo_sweep_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "reports"
            config_path = Path(temp_dir) / "backtest.toml"
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

[sweep]
top_n = [2, 3]
rebalance_every_n_days = [2, 3]
""".strip(),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                exit_code = main(
                    [
                        "--demo",
                        "--config",
                        str(config_path),
                        "--sweep",
                        "--rank-by",
                        "annualized_return",
                    ]
                )

            batch_dir = output_dir / "batch_runs"
            self.assertEqual(0, exit_code)
            self.assertTrue((batch_dir / "batch_summary.csv").exists())
            self.assertTrue((batch_dir / "batch_summary.json").exists())
            self.assertTrue((batch_dir / "batch_leaderboard.csv").exists())
            self.assertTrue((batch_dir / "batch_leaderboard.json").exists())
            self.assertTrue((batch_dir / "batch_report.html").exists())
            payload = json.loads((batch_dir / "batch_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(4, len(payload["rows"]))
            self.assertIn("批量参数扫描完成", buffer.getvalue())
            self.assertIn("批量 HTML 报告已保存", buffer.getvalue())

    def test_demo_walk_forward_optimization_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "reports"
            config_path = Path(temp_dir) / "backtest.toml"
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

[sweep]
top_n = [2, 3]
rebalance_every_n_days = [2, 3]
""".strip(),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                exit_code = main(
                    [
                        "--demo",
                        "--config",
                        str(config_path),
                        "--walk-optimize",
                        "--walk-train-window",
                        "20",
                        "--walk-test-window",
                        "10",
                        "--walk-step",
                        "15",
                        "--rank-by",
                        "annualized_return",
                    ]
                )

            self.assertEqual(0, exit_code)
            summary_path = output_dir / "walk_forward_optimization" / "walk_forward_optimization.json"
            self.assertTrue(summary_path.exists())
            self.assertTrue(
                (output_dir / "walk_forward_optimization" / "walk_forward_optimization_report.html").exists()
            )
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertGreater(payload["summary"]["windows"], 0)
            self.assertEqual("gate_pass_first_then_metric", payload["summary"]["selection_policy"])
            self.assertIn("selected_parameter_sets", payload["summary"])
            first_row = payload["rows"][0]
            self.assertEqual("gate_pass_first_then_metric", first_row["selection_policy"])
            self.assertEqual("annualized_return", first_row["train_rank_metric"])
            self.assertIn("train_gate_status", first_row)
            self.assertIn("train_health_score", first_row)
            self.assertIn("Walk-forward 优化完成", buffer.getvalue())
            self.assertIn("Walk-forward 优化 HTML 报告已保存", buffer.getvalue())

    def test_expands_sweep_combinations(self) -> None:
        combinations = expand_sweep_combinations(
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

        row = build_batch_row(
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

    def test_build_batch_row_includes_strategy_health_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            strategy_health_json = output_dir / "strategy_health.json"
            strategy_health_json.write_text(
                json.dumps(
                    {
                        "summary": {
                            "score": 86.5,
                            "grade": "B",
                            "gate_status": "fail",
                            "gate_failures": 2,
                            "warnings": 2,
                            "critical_warnings": 0,
                        },
                        "gates": [
                            {
                                "name": "Max drawdown",
                                "category": "risk",
                                "passed": False,
                            },
                            {
                                "name": "Factor correlation",
                                "category": "factor",
                                "passed": False,
                            },
                            {
                                "name": "Fill rate",
                                "category": "execution",
                                "passed": True,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = BacktestResult(
                equity_curve=[],
                rebalance_records=[],
                metrics=BacktestMetrics(
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
                ),
            )

            row = build_batch_row(
                run_id="run_001",
                config=type("ConfigLike", (), {"output_dir": output_dir})(),
                overrides={},
                result=result,
                artifact_paths={
                    "equity_curve_csv": output_dir / "equity_curve.csv",
                    "run_manifest_json": output_dir / "run_manifest.json",
                    "strategy_health_json": strategy_health_json,
                },
            )

            self.assertEqual(86.5, row["health_score"])
            self.assertEqual("B", row["health_grade"])
            self.assertEqual("fail", row["gate_status"])
            self.assertEqual(2, row["gate_failures"])
            self.assertEqual(2, row["health_warnings"])
            self.assertEqual("risk;factor", row["failed_gate_categories"])
            self.assertEqual("Max drawdown;Factor correlation", row["failed_gate_names"])

    def test_health_aware_rank_key_prefers_gate_passing_candidate(self) -> None:
        passing_key = health_aware_rank_key(
            0.05,
            {
                "score": 70,
                "gate_status": "pass",
                "gate_failures": 0,
                "warnings": 3,
                "critical_warnings": 0,
            },
        )
        failing_key = health_aware_rank_key(
            0.50,
            {
                "score": 95,
                "gate_status": "fail",
                "gate_failures": 1,
                "warnings": 0,
                "critical_warnings": 0,
            },
        )

        self.assertGreater(passing_key, failing_key)

    def test_build_backtest_config_normalizes_relative_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            args = argparse.Namespace(
                config=None,
                initial_cash=None,
                top_n=None,
                lot_size=None,
                max_group_positions=None,
                lookback_momentum=None,
                lookback_mean_reversion=None,
                lookback_volatility=None,
                rolling_risk_window=None,
                max_allowed_drawdown=None,
                min_allowed_rolling_return=None,
                min_allowed_fill_rate=None,
                max_allowed_position_weight=None,
                max_allowed_attribution_residual=None,
                rebalance_days=None,
                commission_rate=None,
                buy_commission_rate=None,
                sell_commission_rate=None,
                slippage_rate=None,
                stamp_duty_rate=None,
                min_commission=None,
                transfer_fee_rate=None,
                limit_up_down_rate=None,
                st_limit_up_down_rate=None,
                growth_limit_up_down_rate=None,
                bse_limit_up_down_rate=None,
                infer_limit_rate_by_symbol=False,
                max_volume_participation=None,
                target_cash_weight=None,
                max_position_weight=None,
                infer_limit_flags=False,
                forward_fill_suspended_bars=False,
                price_field=None,
                execution_price_field=None,
                execution_delay_days=None,
                start_date=None,
                end_date=None,
                output_dir=temp_dir,
                stock_pool_csv=None,
                symbol_group_csv=None,
                walk_optimize=False,
                walk_forward=False,
                walk_window=30,
                walk_step=10,
                walk_train_window=40,
                walk_test_window=20,
                factor_weight=None,
            )

            config = build_backtest_config(args)

            self.assertTrue(config.output_dir.is_absolute())

    def test_build_backtest_config_accepts_cli_lot_size(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=1,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual(1, config.lot_size)

    def test_build_backtest_config_accepts_cli_selection_mode(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            selection_mode="bottom",
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual("bottom", config.selection_mode)

    def test_build_backtest_config_accepts_cli_score_source(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            selection_mode=None,
            score_source="external",
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            factor_score_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual("external", config.score_source)

    def test_build_backtest_config_accepts_execution_price_field(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field="open",
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual("open", config.execution_price_field)

    def test_build_backtest_config_accepts_execution_delay_days(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            execution_delay_days=1,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual(1, config.execution_delay_days)

    def test_build_backtest_config_accepts_cli_rolling_risk_window(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=12,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual(12, config.rolling_risk_window)

    def test_build_backtest_config_accepts_cli_risk_gate_thresholds(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=0.25,
            max_allowed_daily_var=0.04,
            min_allowed_rolling_return=-0.12,
            min_allowed_fill_rate=0.65,
            min_allowed_execution_price_coverage=0.98,
            max_allowed_market_constraint_rate=0.40,
            max_allowed_position_weight=0.45,
            max_allowed_group_weight=0.55,
            max_allowed_attribution_residual=0.03,
            max_allowed_factor_correlation=0.82,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual(0.25, config.max_allowed_drawdown)
        self.assertEqual(0.04, config.max_allowed_daily_var)
        self.assertEqual(-0.12, config.min_allowed_rolling_return)
        self.assertEqual(0.65, config.min_allowed_fill_rate)
        self.assertEqual(0.98, config.min_allowed_execution_price_coverage)
        self.assertEqual(0.40, config.max_allowed_market_constraint_rate)
        self.assertEqual(0.45, config.max_allowed_position_weight)
        self.assertEqual(0.55, config.max_allowed_group_weight)
        self.assertEqual(0.03, config.max_allowed_attribution_residual)
        self.assertEqual(0.82, config.max_allowed_factor_correlation)

    def test_build_backtest_config_accepts_forward_fill_suspended_flag(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=True,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertTrue(config.forward_fill_suspended_bars)

    def test_build_backtest_config_accepts_cli_date_range(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date="2024-01-10",
            end_date="2024-02-20",
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        config = build_backtest_config(args)

        self.assertEqual("2024-01-10", config.start_date.isoformat())
        self.assertEqual("2024-02-20", config.end_date.isoformat())

    def test_build_backtest_config_uses_run_directory_when_output_dir_is_implicit(self) -> None:
        args = argparse.Namespace(
            config=None,
            initial_cash=None,
            top_n=None,
            lot_size=None,
            max_group_positions=None,
            lookback_momentum=None,
            lookback_mean_reversion=None,
            lookback_volatility=None,
            rolling_risk_window=None,
            max_allowed_drawdown=None,
            min_allowed_rolling_return=None,
            min_allowed_fill_rate=None,
            max_allowed_position_weight=None,
            max_allowed_attribution_residual=None,
            rebalance_days=None,
            commission_rate=None,
            buy_commission_rate=None,
            sell_commission_rate=None,
            slippage_rate=None,
            stamp_duty_rate=None,
            min_commission=None,
            transfer_fee_rate=None,
            limit_up_down_rate=None,
            st_limit_up_down_rate=None,
            growth_limit_up_down_rate=None,
            bse_limit_up_down_rate=None,
            infer_limit_rate_by_symbol=False,
            max_volume_participation=None,
            target_cash_weight=None,
            max_position_weight=None,
            infer_limit_flags=False,
            forward_fill_suspended_bars=False,
            price_field=None,
            execution_price_field=None,
            execution_delay_days=None,
            start_date=None,
            end_date=None,
            output_dir=None,
            stock_pool_csv=None,
            symbol_group_csv=None,
            walk_optimize=False,
            walk_forward=False,
            walk_window=30,
            walk_step=10,
            walk_train_window=40,
            walk_test_window=20,
            factor_weight=None,
        )

        with patch.dict(os.environ, {"MYFINANCES_RUN_TIMESTAMP": "20260102-030405"}):
            config = build_backtest_config(args)

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

        self.assertEqual(config_hash(base), config_hash(changed_output))
        self.assertNotEqual(config_hash(base), config_hash(changed_parameter))

    def test_validate_csv_cli_checks_inputs_without_writing_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            price_csv = temp_path / "prices.csv"
            benchmark_csv = temp_path / "benchmark.csv"
            stock_pool_csv = temp_path / "stock_pool.csv"
            _write_price_csv(price_csv)
            _write_benchmark_csv(benchmark_csv)
            _write_stock_pool_csv(stock_pool_csv)

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = main(
                    [
                        "--validate-csv",
                        "--csv",
                        str(price_csv),
                        "--benchmark-csv",
                        str(benchmark_csv),
                        "--stock-pool-csv",
                        str(stock_pool_csv),
                        "--output-dir",
                        str(temp_path / "quality"),
                    ]
                )

            self.assertEqual(0, exit_code)
            output = buffer.getvalue()
            self.assertIn("行情 CSV 校验通过", output)
            self.assertIn("基准 CSV 校验通过", output)
            self.assertIn("股票池 CSV 校验通过", output)
            self.assertIn("行情数据质量 CSV 已保存", output)
            self.assertIn("基准质量 CSV 已保存", output)
            self.assertIn("股票池质量 CSV 已保存", output)
            self.assertTrue((temp_path / "quality" / "price_data_quality_report.csv").exists())
            self.assertTrue((temp_path / "quality" / "price_data_quality_report.json").exists())
            self.assertTrue((temp_path / "quality" / "benchmark_quality_report.csv").exists())
            self.assertTrue((temp_path / "quality" / "benchmark_quality_report.json").exists())
            self.assertTrue((temp_path / "quality" / "stock_pool_quality_report.csv").exists())
            self.assertTrue((temp_path / "quality" / "stock_pool_quality_report.json").exists())
            self.assertFalse((temp_path / "report.html").exists())

    def test_validate_csv_requires_at_least_one_input_file(self) -> None:
        stderr = io.StringIO()
        with (
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            main(["--validate-csv"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("--validate-csv", stderr.getvalue())

    def test_validate_csv_accepts_symbol_group_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mapping_path = temp_path / "groups.csv"
            mapping_path.write_text("symbol,group\n000001,银行\n", encoding="utf-8")
            output_dir = temp_path / "quality"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--symbol-group-csv",
                        str(mapping_path),
                        "--validate-csv",
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "symbol_group_quality_report.csv").exists())
            self.assertTrue((output_dir / "symbol_group_quality_report.json").exists())

    def test_validate_csv_accepts_factor_score_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            price_csv = temp_path / "prices.csv"
            score_csv = temp_path / "factor_scores.csv"
            output_dir = temp_path / "quality"
            _write_price_csv(price_csv)
            score_csv.write_text(
                "date,symbol,score\n"
                "2024-01-04,000001,1\n"
                "2024-01-04,600519,2\n"
                "2024-01-04,000333,0\n",
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = main(
                    [
                        "--validate-csv",
                        "--csv",
                        str(price_csv),
                        "--factor-score-csv",
                        str(score_csv),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertIn("外部因子评分 CSV 校验完成", buffer.getvalue())
            self.assertTrue((output_dir / "factor_score_quality_report.csv").exists())
            self.assertTrue((output_dir / "factor_score_quality_report.json").exists())
            self.assertTrue((output_dir / "factor_score_quality_distribution_by_date.csv").exists())
            self.assertIn("外部因子评分每日分布 CSV 已保存", buffer.getvalue())


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


def _write_stock_pool_csv(path: Path) -> None:
    rows = [
        "date,symbol",
        "2024-01-02,000001",
        "2024-01-02,600519",
        "2024-01-02,000333",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

