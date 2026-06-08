from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from python_quant.config import BacktestConfig
from python_quant.models import (
    BacktestMetrics,
    EquityPoint,
    FactorScoreRecord,
    PositionPoint,
    RebalanceRecord,
    TradeAttemptRecord,
    TradeRecord,
)
from python_quant.reporting import (
    load_symbol_group_mapping,
    load_symbol_name_mapping,
    print_summary,
    save_batch_chart_svg,
    save_batch_heatmap_svg,
    save_batch_rankings,
    save_batch_report_html,
    save_equity_chart_svg,
    save_equity_curve,
    save_factor_scores,
    save_performance_summary,
    save_performance_summary_json,
    save_positions,
    save_rebalance_log,
    save_run_manifest,
    save_single_run_report_html,
    save_trade_attempts,
    save_trades,
    save_walk_forward_report_html,
)
from python_quant.reporting_csv import (
    save_batch_stability_files,
    save_cost_attribution_files,
    save_drawdown_files,
    save_execution_quality_files,
    save_exposure_files,
    save_factor_correlation_files,
    save_factor_decay_files,
    save_factor_group_return_files,
    save_group_exposure_files,
    save_monthly_return_files,
    save_pnl_ledger_files,
    save_relative_performance_files,
    save_return_attribution_files,
    save_rolling_risk_files,
    save_strategy_health_files,
    save_walk_forward_files,
    save_walk_forward_optimization_files,
)


class ReportingTests(unittest.TestCase):
    def test_saves_run_manifest_with_config_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config_path = output_dir / "backtest.toml"
            config_path.write_text("[backtest]\ntop_n = 3\n", encoding="utf-8")
            config = BacktestConfig(output_dir=output_dir)
            metrics = BacktestMetrics(
                total_return=0.1,
                annualized_return=0.2,
                max_drawdown=-0.05,
                volatility=0.15,
                downside_volatility=0.1,
                sharpe=1.2,
                sortino=1.5,
                calmar=4.0,
                win_rate=0.6,
                average_turnover=0.25,
                total_cost=123.45,
                periods=20,
            )
            summary_json_path = save_performance_summary_json(metrics, output_dir)

            manifest_path = save_run_manifest(
                output_dir=output_dir,
                config=config,
                inputs={
                    "demo": True,
                    "csv": None,
                    "benchmark_csv": None,
                    "config": str(config_path),
                },
                artifacts={"performance_summary_json": summary_json_path},
                metrics=metrics,
            )

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(True, payload["inputs"]["demo"])
            self.assertEqual(
                str(summary_json_path),
                payload["artifacts"]["performance_summary_json"],
            )
            self.assertEqual(0.1, payload["metrics"]["total_return"])
            self.assertEqual(str(output_dir), payload["config"]["output_dir"])
            self.assertIn("python_version", payload["environment"])
            self.assertIn("platform", payload["environment"])
            self.assertIn("available", payload["git"])
            if payload["git"]["available"]:
                self.assertIn("commit", payload["git"])
                self.assertIn("branch", payload["git"])
                self.assertIn("is_dirty", payload["git"])
            self.assertEqual(str(config_path.resolve()), payload["input_files"]["config"]["path"])
            self.assertEqual(
                hashlib.sha256(config_path.read_bytes()).hexdigest(),
                payload["input_files"]["config"]["sha256"],
            )
            self.assertEqual(config_path.stat().st_size, payload["input_files"]["config"]["size_bytes"])
            artifact_metadata = payload["artifact_files"]["performance_summary_json"]
            self.assertEqual(str(summary_json_path.resolve()), artifact_metadata["path"])
            self.assertEqual(summary_json_path.stat().st_size, artifact_metadata["size_bytes"])
            self.assertEqual(
                hashlib.sha256(summary_json_path.read_bytes()).hexdigest(),
                artifact_metadata["sha256"],
            )

    def test_loads_symbol_name_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "symbols.csv"
            csv_path.write_text(
                "symbol,name\n000001,平安银行\n600519,贵州茅台\n",
                encoding="utf-8",
            )

            mapping = load_symbol_name_mapping(csv_path)

            self.assertEqual("平安银行", mapping["000001"])
            self.assertEqual("贵州茅台", mapping["600519"])

    def test_rejects_non_a_share_symbol_name_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "symbols.csv"
            csv_path.write_text(
                "symbol,name\nAAPL,苹果\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unsupported A-share symbol format"):
                load_symbol_name_mapping(csv_path)

    def test_loads_symbol_group_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "groups.csv"
            csv_path.write_text(
                "symbol,group\n000001,银行\n600519,消费\n",
                encoding="utf-8",
            )

            mapping = load_symbol_group_mapping(csv_path)

            self.assertEqual("银行", mapping["000001"])
            self.assertEqual("消费", mapping["600519"])

    def test_saves_equity_chart_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            curve = [
                EquityPoint(
                    date=__import__("datetime").date(2024, 1, 2),
                    equity=100.0,
                    daily_return=0.01,
                    holdings=("AAA",),
                ),
                EquityPoint(
                    date=__import__("datetime").date(2024, 1, 3),
                    equity=101.0,
                    daily_return=0.02,
                    holdings=("AAA",),
                ),
            ]

            chart_path = save_equity_chart_svg(curve, output_dir)

            content = chart_path.read_text(encoding="utf-8-sig")
            self.assertIn("<svg", content)
            self.assertIn("策略净值走势", content)

    def test_saves_bilingual_csv_headers_and_descriptions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            curve = [
                EquityPoint(
                    date=__import__("datetime").date(2024, 1, 2),
                    equity=100.0,
                    daily_return=0.01,
                    holdings=("000001",),
                ),
            ]
            metrics = BacktestMetrics(
                total_return=0.1,
                annualized_return=0.2,
                max_drawdown=-0.05,
                volatility=0.15,
                downside_volatility=0.1,
                sharpe=1.2,
                sortino=1.5,
                calmar=4.0,
                win_rate=0.6,
                average_turnover=0.25,
                total_cost=123.45,
                periods=20,
            )

            equity_curve_path = save_equity_curve(curve, output_dir)
            rebalance_log_path = save_rebalance_log([], output_dir)
            summary_path = save_performance_summary(metrics, output_dir)

            self.assertIn("日期 / date", equity_curve_path.read_text(encoding="utf-8-sig"))
            self.assertIn("持仓 / holdings", rebalance_log_path.read_text(encoding="utf-8-sig"))
            summary_content = summary_path.read_text(encoding="utf-8-sig")
            self.assertIn("指标代码 / metric", summary_content)
            self.assertIn("说明 / description", summary_content)
            self.assertIn("总收益 = 期末权益 / 期初权益 - 1。", summary_content)
            equity_content = equity_curve_path.read_text(encoding="utf-8-sig")
            self.assertIn("权益展示 / equity_display", equity_content)
            self.assertIn("单期收益率展示 / daily_return_pct", equity_content)
            self.assertIn("持仓展示 / holdings_display", equity_content)
            self.assertIn("持仓数量 / holding_count", equity_content)
            self.assertIn("备注 / note", equity_content)
            rebalance_content = rebalance_log_path.read_text(encoding="utf-8-sig")
            self.assertIn("买入换手率展示 / buy_turnover_pct", rebalance_content)
            self.assertIn("交易成本展示 / cost_display", rebalance_content)
            self.assertIn("持仓展示 / holdings_display", rebalance_content)

    def test_saves_readable_equity_and_rebalance_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            curve = [
                EquityPoint(
                    date=__import__("datetime").date(2024, 1, 2),
                    equity=123456.78,
                    daily_return=0.0123,
                    holdings=("000001", "600519"),
                ),
            ]
            equity_curve_path = save_equity_curve(curve, output_dir)
            equity_content = equity_curve_path.read_text(encoding="utf-8-sig")
            self.assertIn("123,456.78", equity_content)
            self.assertIn("1.23%", equity_content)
            self.assertIn("000001（平安银行） | 600519（贵州茅台）", equity_content)
            self.assertIn("2只持仓", equity_content)

            equity_curve_with_names = save_equity_curve(curve, output_dir, symbol_names={"000001": "平安银行"})
            named_content = equity_curve_with_names.read_text(encoding="utf-8-sig")
            self.assertIn("000001（平安银行） | 600519（贵州茅台）", named_content)

            rebalances = [
                RebalanceRecord(
                    date=__import__("datetime").date(2024, 1, 2),
                    holdings=("000001",),
                    buy_turnover=0.25,
                    sell_turnover=0.0,
                    turnover=0.25,
                    cost=123.45,
                )
            ]
            rebalance_log_path = save_rebalance_log(rebalances, output_dir)
            rebalance_content = rebalance_log_path.read_text(encoding="utf-8-sig")
            self.assertIn("25.00%", rebalance_content)
            self.assertIn("123.45", rebalance_content)
            self.assertIn("000001（平安银行）", rebalance_content)
            self.assertIn("仅买入", rebalance_content)

    def test_saves_position_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            positions = [
                PositionPoint(
                    date=__import__("datetime").date(2024, 1, 2),
                    symbol="000001",
                    shares=100,
                    price=10.25,
                    market_value=1025.0,
                    weight=0.1025,
                    cash=8975.0,
                    total_equity=10000.0,
                ),
                PositionPoint(
                    date=__import__("datetime").date(2024, 1, 2),
                    symbol="CASH",
                    shares=0,
                    price=1.0,
                    market_value=8975.0,
                    weight=0.8975,
                    cash=8975.0,
                    total_equity=10000.0,
                ),
            ]

            positions_path = save_positions(positions, output_dir)

            content = positions_path.read_text(encoding="utf-8-sig")
            self.assertIn("代码 / symbol", content)
            self.assertIn("股数 / shares", content)
            self.assertIn("市值 / market_value", content)
            self.assertIn("10.25%", content)
            self.assertIn("000001", content)
            self.assertIn("CASH", content)

    def test_saves_trade_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            trades = [
                TradeRecord(
                    date=__import__("datetime").date(2024, 1, 2),
                    symbol="000001",
                    side="BUY",
                    shares=100,
                    price=10.25,
                    gross_value=1025.0,
                    commission=0.31,
                    slippage=0.51,
                    transfer_fee=0.02,
                    stamp_duty=0.0,
                    total_cost=0.84,
                    cash_change=-1025.84,
                    reason="rebalance_entry",
                    fixed_slippage=0.20,
                    market_impact=0.31,
                )
            ]

            trades_path = save_trades(trades, output_dir)

            content = trades_path.read_text(encoding="utf-8-sig")
            self.assertIn("方向 / side", content)
            self.assertIn("成交金额 / gross_value", content)
            self.assertIn("佣金 / commission", content)
            self.assertIn("fixed_slippage", content)
            self.assertIn("market_impact", content)
            self.assertIn("0.20", content)
            self.assertIn("0.31", content)
            self.assertIn("BUY", content)
            self.assertIn("-1025.84", content)

    def test_saves_trade_attempt_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            attempts = [
                TradeAttemptRecord(
                    date=__import__("datetime").date(2024, 1, 2),
                    symbol="000001",
                    side="BUY",
                    target_shares=0,
                    price=10.25,
                    reason="insufficient_cash_for_lot",
                    cash=99.0,
                )
            ]

            attempts_path = save_trade_attempts(attempts, output_dir)

            content = attempts_path.read_text(encoding="utf-8-sig")
            self.assertIn("目标股数 / target_shares", content)
            self.assertIn("insufficient_cash_for_lot", content)
            self.assertIn("99.00", content)

    def test_saves_factor_score_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            records = [
                FactorScoreRecord(
                    date=__import__("datetime").date(2024, 1, 2),
                    symbol="000001",
                    momentum=0.1,
                    mean_reversion=-0.02,
                    low_volatility=-0.01,
                    normalized_momentum=1.0,
                    normalized_mean_reversion=0.5,
                    normalized_low_volatility=0.25,
                    total_score=0.675,
                    selected=True,
                )
            ]

            score_path = save_factor_scores(records, output_dir)

            content = score_path.read_text(encoding="utf-8-sig")
            self.assertIn("总分 / total_score", content)
            self.assertIn("入选 / selected", content)
            self.assertIn("0.67500000", content)

    def test_print_summary_uses_chinese_labels(self) -> None:
        metrics = BacktestMetrics(
            total_return=0.1,
            annualized_return=0.2,
            max_drawdown=-0.05,
            volatility=0.15,
            downside_volatility=0.1,
            sharpe=1.2,
            sortino=1.5,
            calmar=4.0,
            win_rate=0.6,
            average_turnover=0.25,
            total_cost=123.45,
            periods=20,
        )
        curve = [
            EquityPoint(
                date=__import__("datetime").date(2024, 1, 2),
                equity=110.0,
                daily_return=0.01,
                holdings=("000001",),
            ),
        ]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            print_summary(curve, [], metrics, BacktestConfig(initial_cash=100.0))

        output = buffer.getvalue()
        self.assertIn("A股回测摘要", output)
        self.assertIn("回测摘要", output)
        self.assertIn("总收益", output)
        self.assertIn("夏普比率", output)

    def test_saves_batch_rankings_and_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [
                {
                    "run_id": "run_001",
                    "annualized_return": 0.2,
                    "param_top_n": 2,
                    "param_rebalance_every_n_days": 5,
                },
                {
                    "run_id": "run_002",
                    "annualized_return": 0.3,
                    "param_top_n": 3,
                    "param_rebalance_every_n_days": 5,
                },
            ]

            leaderboard_csv, leaderboard_json, best_run_json = save_batch_rankings(
                rows,
                output_dir,
                rank_by="annualized_return",
            )
            chart_path = save_batch_chart_svg(rows, output_dir, metric="annualized_return")
            heatmap_path = save_batch_heatmap_svg(
                rows,
                output_dir,
                x_field="param_top_n",
                y_field="param_rebalance_every_n_days",
                metric="annualized_return",
            )

            self.assertTrue(leaderboard_csv.exists())
            self.assertTrue(leaderboard_json.exists())
            self.assertTrue(best_run_json.exists())
            self.assertTrue(chart_path.exists())
            self.assertTrue(heatmap_path.exists())
            leaderboard_payload = json.loads(leaderboard_json.read_text(encoding="utf-8"))
            best_payload = json.loads(best_run_json.read_text(encoding="utf-8"))
            self.assertEqual("方案2", leaderboard_payload["reader_friendly"]["best_scheme"])
            self.assertEqual("run_002", leaderboard_payload["reader_friendly"]["best_internal_id"])
            self.assertEqual("run_002", leaderboard_payload["rows"][0]["run_id"])
            self.assertEqual("run_002", best_payload["best_run"]["run_id"])
            self.assertEqual("方案2", best_payload["reader_friendly"]["best_scheme"])
            self.assertEqual("run_002", best_payload["reader_friendly"]["best_internal_id"])
            leaderboard_content = leaderboard_csv.read_text(encoding="utf-8-sig")
            self.assertIn("方案编号 / scheme_label", leaderboard_content)
            self.assertIn("内部编号 / run_id", leaderboard_content)
            self.assertIn("方案1", leaderboard_content)
            self.assertIn("run_002", leaderboard_content)
            chart_content = chart_path.read_text(encoding="utf-8-sig")
            heatmap_content = heatmap_path.read_text(encoding="utf-8-sig")
            self.assertIn("年化收益参数对比图", chart_content)
            self.assertIn("方案1", chart_content)
            self.assertIn("方案2", chart_content)
            self.assertIn("年化收益参数热力图", heatmap_content)

    def test_saves_batch_stability_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_batch_stability_files(
                {
                    "rows": [
                        {
                            "run_id": "run_001",
                            "is_robust_region": True,
                            "composite_score": 1.2,
                            "risk_penalty": 0.1,
                        }
                    ],
                    "summary": {"best_run_id": "run_001"},
                },
                output_dir,
            )

            self.assertTrue(paths["batch_stability_csv"].exists())
            self.assertTrue(paths["batch_stability_json"].exists())
            self.assertTrue(paths["parameter_sensitivity_csv"].exists())
            self.assertIn("is_robust_region", paths["batch_stability_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_parameter_sensitivity_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_batch_stability_files(
                {
                    "rows": [],
                    "summary": {
                        "parameter_sensitivity": {
                            "param_top_n": {
                                "best_value_by_metric": "2",
                                "best_value_by_composite": "3",
                                "values": {
                                    "2": {
                                        "run_count": 2,
                                        "average_metric": 0.1,
                                        "best_metric": 0.2,
                                        "average_composite_score": 0.3,
                                        "gate_passing_run_count": 1,
                                        "gate_passing_rate": 0.5,
                                        "worst_max_drawdown": -0.1,
                                    },
                                    "3": {
                                        "run_count": 1,
                                        "average_metric": 0.05,
                                        "best_metric": 0.05,
                                        "average_composite_score": 0.5,
                                        "gate_passing_run_count": 1,
                                        "gate_passing_rate": 1.0,
                                        "worst_max_drawdown": -0.05,
                                    }
                                }
                            }
                        },
                        "best_parameter_values": {"param_top_n": "3"},
                        "parameter_recommendation_rationale": {
                            "param_top_n": {"reason": "highest_average_composite_score"}
                        },
                    },
                },
                output_dir,
            )

            content = paths["parameter_sensitivity_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("parameter,value,run_count", content)
            self.assertIn("is_recommended,is_best_by_metric,is_best_by_composite,recommendation_reason", content)
            self.assertIn("param_top_n,2,2", content)
            self.assertIn("False,True,False,", content)
            self.assertIn("True,False,True,highest_average_composite_score", content)

    def test_batch_rankings_prefer_gate_passing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [
                {
                    "run_id": "run_001",
                    "annualized_return": 0.2,
                    "health_score": 88.0,
                    "gate_status": "pass",
                    "gate_failures": 0,
                    "health_warnings": 1,
                    "critical_warnings": 0,
                },
                {
                    "run_id": "run_002",
                    "annualized_return": 0.5,
                    "health_score": 55.0,
                    "gate_status": "fail",
                    "gate_failures": 2,
                    "health_warnings": 4,
                    "critical_warnings": 1,
                },
            ]

            _, leaderboard_json, best_run_json = save_batch_rankings(
                rows,
                output_dir,
                rank_by="annualized_return",
            )

            leaderboard_payload = json.loads(leaderboard_json.read_text(encoding="utf-8"))
            best_payload = json.loads(best_run_json.read_text(encoding="utf-8"))
            self.assertEqual("gate_pass_first_then_metric", leaderboard_payload["ranking_policy"])
            self.assertEqual("run_001", leaderboard_payload["rows"][0]["run_id"])
            self.assertEqual("pass", leaderboard_payload["reader_friendly"]["best_gate_status"])
            self.assertEqual("88.000", leaderboard_payload["reader_friendly"]["best_health_score"])
            self.assertEqual("run_001", best_payload["best_run"]["run_id"])
            self.assertEqual("pass", best_payload["reader_friendly"]["best_gate_status"])

    def test_saves_walk_forward_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_walk_forward_files(
                {
                    "rows": [
                        {
                            "window_id": "window_001",
                            "start_date": "2024-01-02",
                            "end_date": "2024-02-02",
                            "periods": 20,
                            "total_return": 0.05,
                            "annualized_return": 0.2,
                            "max_drawdown": -0.03,
                            "sharpe": 1.2,
                            "win_rate": 0.6,
                            "total_cost": 10.0,
                            "run_manifest_json": "run_manifest.json",
                        }
                    ],
                    "summary": {"windows": 1},
                },
                output_dir,
            )

            self.assertTrue(paths["walk_forward_csv"].exists())
            self.assertTrue(paths["walk_forward_json"].exists())
            self.assertIn("window_001", paths["walk_forward_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_walk_forward_optimization_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_walk_forward_optimization_files(
                {
                    "rows": [
                        {
                            "window_id": "window_001",
                            "train_start_date": "2024-01-02",
                            "train_end_date": "2024-02-02",
                            "test_start_date": "2024-02-05",
                            "test_end_date": "2024-03-01",
                            "train_annualized_return": 0.2,
                            "train_sharpe": 1.1,
                            "test_total_return": 0.03,
                            "test_annualized_return": 0.18,
                            "train_test_annualized_gap": 0.02,
                            "test_to_train_efficiency": 0.9,
                            "is_degraded_out_of_sample": True,
                            "test_max_drawdown": -0.02,
                            "test_sharpe": 1.0,
                            "test_win_rate": 0.6,
                            "train_run_manifest_json": "train.json",
                            "test_run_manifest_json": "test.json",
                            "param_top_n": 2,
                        }
                    ],
                    "summary": {"windows": 1},
                },
                output_dir,
            )

            self.assertTrue(paths["walk_forward_optimization_csv"].exists())
            self.assertTrue(paths["walk_forward_optimization_json"].exists())
            content = paths["walk_forward_optimization_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("param_top_n", content)
            self.assertIn("train_test_annualized_gap", content)
            self.assertIn("test_to_train_efficiency", content)

    def test_saves_walk_forward_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            report_path = save_walk_forward_report_html(
                output_dir=output_dir,
                analysis={
                    "rows": [
                        {
                            "window_id": "window_001",
                            "start_date": "2024-01-02",
                            "end_date": "2024-02-02",
                            "total_return": 0.1,
                            "annualized_return": 0.2,
                            "max_drawdown": -0.03,
                            "sharpe": 1.2,
                            "win_rate": 0.6,
                        }
                    ],
                    "summary": {
                        "windows": 1,
                        "positive_window_rate": 1.0,
                        "average_total_return": 0.1,
                        "average_annualized_return": 0.2,
                        "average_sharpe": 1.2,
                        "worst_max_drawdown": -0.03,
                        "best_window_id": "window_001",
                        "worst_window_id": "window_001",
                    },
                },
            )

            content = report_path.read_text(encoding="utf-8-sig")
            self.assertIn("A股Walk-forward验证报告", content)
            self.assertIn("验证结论", content)
            self.assertIn("正收益窗口占比", content)
            self.assertIn("window_001", content)

    def test_saves_walk_forward_optimization_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            report_path = save_walk_forward_report_html(
                output_dir=output_dir,
                optimization=True,
                analysis={
                    "rows": [
                        {
                            "window_id": "window_001",
                            "train_start_date": "2024-01-02",
                            "test_end_date": "2024-03-01",
                            "train_annualized_return": 0.2,
                            "test_annualized_return": 0.1,
                            "train_test_annualized_gap": 0.1,
                            "test_to_train_efficiency": 0.5,
                            "is_degraded_out_of_sample": True,
                            "test_max_drawdown": -0.04,
                        }
                    ],
                    "summary": {
                        "windows": 1,
                        "positive_test_window_rate": 1.0,
                        "degraded_test_window_rate": 1.0,
                        "parameter_drift_rate": 0.0,
                        "oos_stability_grade": "mixed",
                        "overfit_risk": "medium",
                        "best_test_window_id": "window_001",
                        "worst_test_window_id": "window_001",
                        "worst_degradation_window_id": "window_001",
                        "worst_train_test_annualized_gap": 0.1,
                        "dominant_parameter_set": "param_top_n=3",
                        "dominant_parameter_set_rate": 1.0,
                        "most_drifting_parameter": "param_top_n",
                        "parameter_drift_counts": {"param_top_n": 1},
                        "degraded_parameter_sets": [
                            {
                                "window_id": "window_001",
                                "parameter_set": "param_top_n=3",
                                "train_test_annualized_gap": 0.1,
                            }
                        ],
                    },
                },
            )

            content = report_path.read_text(encoding="utf-8-sig")
            self.assertIn("A股Walk-forward优化报告", content)
            self.assertIn("样本外稳定等级", content)
            self.assertIn("过拟合风险", content)
            self.assertIn("漂移最频繁参数", content)
            self.assertIn("退化窗口参数组合", content)
            self.assertIn("param_top_n=3", content)

    def test_saves_factor_group_return_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_factor_group_return_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "next_date": "2024-01-03",
                            "factor": "momentum",
                            "group": 1,
                            "group_count": 2,
                            "sample_size": 3,
                            "average_factor_value": 0.1,
                            "average_forward_return": 0.02,
                        }
                    ],
                    "summary": {"group_count": 2},
                },
                output_dir,
            )

            self.assertTrue(paths["factor_group_returns_csv"].exists())
            self.assertTrue(paths["factor_group_returns_json"].exists())

    def test_saves_factor_decay_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_factor_decay_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "next_date": "2024-01-03",
                            "factor": "total_score",
                            "score_correlation": 0.8,
                            "rank_correlation": 0.7,
                            "sample_size": 3,
                            "selected_count": 2,
                            "selected_retention_rate": 0.5,
                            "selected_turnover_rate": 0.5,
                        }
                    ],
                    "summary": {"total_score": {"average_rank_correlation": 0.7}},
                },
                output_dir,
            )

            self.assertTrue(paths["factor_decay_csv"].exists())
            self.assertTrue(paths["factor_decay_json"].exists())
            self.assertIn("selected_retention_rate", paths["factor_decay_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_factor_correlation_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_factor_correlation_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "factor": "momentum",
                            "compared_factor": "mean_reversion",
                            "correlation": -0.8,
                            "rank_correlation": -0.7,
                            "sample_size": 3,
                        }
                    ],
                    "summary": {"strongest_pair": {"factor": "momentum", "compared_factor": "mean_reversion"}},
                },
                output_dir,
            )

            self.assertTrue(paths["factor_correlation_csv"].exists())
            self.assertTrue(paths["factor_correlation_json"].exists())
            self.assertIn("compared_factor", paths["factor_correlation_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_risk_analysis_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            drawdown_paths = save_drawdown_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "equity": 100.0,
                            "peak_date": "2024-01-02",
                            "peak_equity": 100.0,
                            "drawdown": 0.0,
                            "is_underwater": False,
                            "underwater_days": 0,
                            "underwater_start_date": "",
                            "daily_return": 0.0,
                        }
                    ],
                    "summary": {"max_drawdown": 0.0},
                },
                output_dir,
            )
            monthly_paths = save_monthly_return_files(
                {
                    "rows": [
                        {
                            "month": "2024-01",
                            "start_date": "2024-01-02",
                            "end_date": "2024-01-31",
                            "periods": 20,
                            "starting_equity": 100.0,
                            "ending_equity": 105.0,
                            "monthly_return": 0.05,
                        }
                    ],
                    "summary": {"months": 1},
                },
                output_dir,
            )
            relative_paths = save_relative_performance_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "strategy_daily_return": 0.01,
                            "benchmark_daily_return": 0.005,
                            "active_return": 0.005,
                            "cumulative_strategy_equity": 101.0,
                            "cumulative_benchmark_equity": 100.5,
                            "active_equity": 1.005,
                            "cumulative_active_return": 0.005,
                            "active_drawdown": 0.0,
                        }
                    ],
                    "summary": {"has_benchmark": True},
                },
                output_dir,
            )
            rolling_paths = save_rolling_risk_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-31",
                            "start_date": "2024-01-02",
                            "end_date": "2024-01-31",
                            "window": 20,
                            "periods": 20,
                            "rolling_return": 0.05,
                            "rolling_annualized_return": 0.8,
                            "rolling_volatility": 0.16,
                            "rolling_sharpe": 5.0,
                            "rolling_max_drawdown": -0.02,
                            "rolling_win_rate": 0.6,
                        }
                    ],
                    "summary": {"periods": 1},
                },
                output_dir,
            )
            health_paths = save_strategy_health_files(
                {
                    "rows": [
                        {
                            "category": "risk",
                            "name": "最大回撤",
                            "score": 90.0,
                            "weight": 1.0,
                            "severity": "ok",
                            "message": "最大回撤控制良好。",
                        }
                    ],
                    "summary": {"score": 90.0, "grade": "A"},
                    "warnings": [],
                    "gates": [
                        {
                            "name": "最大回撤不超过 20%",
                            "category": "risk",
                            "actual": 0.05,
                            "threshold": 0.20,
                            "passed": True,
                            "message": "通过",
                        }
                    ],
                },
                output_dir,
            )

            self.assertTrue(drawdown_paths["drawdown_csv"].exists())
            self.assertTrue(drawdown_paths["drawdown_json"].exists())
            drawdown_content = drawdown_paths["drawdown_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("is_underwater", drawdown_content)
            self.assertIn("underwater_days", drawdown_content)
            self.assertTrue(monthly_paths["monthly_returns_csv"].exists())
            self.assertTrue(monthly_paths["monthly_returns_json"].exists())
            self.assertTrue(relative_paths["relative_performance_csv"].exists())
            self.assertTrue(relative_paths["relative_performance_json"].exists())
            self.assertIn(
                "cumulative_active_return",
                relative_paths["relative_performance_csv"].read_text(encoding="utf-8-sig"),
            )
            self.assertTrue(rolling_paths["rolling_risk_csv"].exists())
            self.assertTrue(rolling_paths["rolling_risk_json"].exists())
            self.assertTrue(health_paths["strategy_health_csv"].exists())
            self.assertTrue(health_paths["strategy_health_gates_csv"].exists())
            self.assertTrue(health_paths["strategy_health_json"].exists())

    def test_saves_execution_quality_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_execution_quality_files(
                {
                    "rows": [
                        {
                            "category": "side",
                            "key": "ALL",
                            "orders": 2,
                            "filled_orders": 1,
                            "rejected_orders": 1,
                            "fill_rate": 0.5,
                            "filled_shares": 100,
                            "rejected_target_shares": 100,
                            "gross_value": 1000.0,
                            "total_cost": 1.0,
                            "cost_bps": 10.0,
                            "average_trade_value": 1000.0,
                        }
                    ],
                    "summary": {"fill_rate": 0.5},
                },
                output_dir,
            )

            self.assertTrue(paths["execution_quality_csv"].exists())
            self.assertTrue(paths["execution_quality_json"].exists())
            self.assertIn("cost_bps", paths["execution_quality_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_exposure_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_exposure_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "holding_count": 2,
                            "stock_weight": 0.9,
                            "cash_weight": 0.1,
                            "largest_position_weight": 0.5,
                            "hhi_concentration": 0.41,
                            "effective_position_count": 2.439,
                            "largest_risk_contribution_symbol": "000001",
                            "largest_risk_contribution_share": 0.61,
                            "total_equity": 2000.0,
                        }
                    ],
                    "summary": {"average_stock_weight": 0.9},
                },
                output_dir,
            )

            self.assertTrue(paths["exposure_csv"].exists())
            self.assertTrue(paths["exposure_json"].exists())
            content = paths["exposure_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("hhi_concentration", content)
            self.assertIn("largest_risk_contribution_symbol", content)

    def test_saves_group_exposure_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_group_exposure_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "group": "银行",
                            "holding_count": 1,
                            "weight": 0.5,
                            "market_value": 1000.0,
                            "risk_contribution_share": 1.0,
                        }
                    ],
                    "summary": {"has_group_mapping": True},
                },
                output_dir,
            )

            self.assertTrue(paths["group_exposure_csv"].exists())
            self.assertTrue(paths["group_exposure_json"].exists())
            content = paths["group_exposure_csv"].read_text(encoding="utf-8-sig")
            self.assertIn("group", content)
            self.assertIn("risk_contribution_share", content)

    def test_saves_return_attribution_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_return_attribution_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-03",
                            "previous_date": "2024-01-02",
                            "symbol": "000001",
                            "group": "银行",
                            "previous_weight": 1.0,
                            "asset_return": 0.01,
                            "return_contribution": 0.01,
                        }
                    ],
                    "summary": {"periods": 1},
                },
                output_dir,
            )

            self.assertTrue(paths["return_attribution_csv"].exists())
            self.assertTrue(paths["return_attribution_json"].exists())
            self.assertIn("return_contribution", paths["return_attribution_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_cost_attribution_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_cost_attribution_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "symbol": "000001",
                            "group": "银行",
                            "side": "BUY",
                            "reason": "rebalance_entry",
                            "component": "commission",
                            "amount": 1.0,
                            "gross_value": 1000.0,
                            "cost_bps": 10.0,
                        }
                    ],
                    "summary": {"total_cost": 1.0},
                },
                output_dir,
            )

            self.assertTrue(paths["cost_attribution_csv"].exists())
            self.assertTrue(paths["cost_attribution_json"].exists())
            self.assertIn("component", paths["cost_attribution_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_pnl_ledger_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            paths = save_pnl_ledger_files(
                {
                    "rows": [
                        {
                            "date": "2024-01-02",
                            "starting_equity": 1000.0,
                            "ending_equity": 1010.0,
                            "equity_change": 10.0,
                            "daily_return": 0.01,
                            "gross_buy_value": 0.0,
                            "gross_sell_value": 0.0,
                            "net_cash_flow": 0.0,
                            "total_cost": 0.0,
                            "market_pnl": 10.0,
                            "ending_cash": 10.0,
                            "ending_market_value": 1000.0,
                            "ledger_equity": 1010.0,
                            "reconciliation_difference": 0.0,
                            "trade_count": 0,
                            "holding_count": 1,
                        }
                    ],
                    "summary": {"reconciled": True},
                },
                output_dir,
            )

            self.assertTrue(paths["pnl_ledger_csv"].exists())
            self.assertTrue(paths["pnl_ledger_json"].exists())
            self.assertIn("reconciliation_difference", paths["pnl_ledger_csv"].read_text(encoding="utf-8-sig"))

    def test_saves_empty_batch_chart_with_chinese_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            chart_path = save_batch_chart_svg([], output_dir, metric="annualized_return")

            content = chart_path.read_text(encoding="utf-8-sig")
            self.assertIn("年化收益参数对比图", content)
            self.assertIn("暂无可展示数据", content)

    def test_rejects_unknown_batch_rank_metric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [{"run_id": "run_001", "annualized_return": 0.2}]

            with self.assertRaisesRegex(ValueError, "Rank metric 'missing_metric'"):
                save_batch_rankings(rows, output_dir, rank_by="missing_metric")

    def test_saves_single_run_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = BacktestConfig(output_dir=output_dir)
            metrics = BacktestMetrics(
                total_return=0.1,
                annualized_return=0.2,
                max_drawdown=-0.05,
                volatility=0.15,
                downside_volatility=0.1,
                sharpe=1.2,
                sortino=1.5,
                calmar=4.0,
                win_rate=0.6,
                average_turnover=0.25,
                total_cost=123.45,
                periods=20,
                benchmark_total_return=0.06,
                benchmark_annualized_return=0.12,
                benchmark_volatility=0.10,
                benchmark_max_drawdown=-0.08,
                excess_return=0.04,
                tracking_error=0.03,
                information_ratio=1.1,
            )
            (output_dir / "drawdown.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "max_drawdown_date": "2024-01-10",
                            "longest_underwater_days": 7,
                            "is_recovered": False,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "exposure.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "average_stock_weight": 0.82,
                            "average_holding_count": 3.5,
                            "average_effective_position_count": 2.8,
                            "max_largest_position_weight": 0.45,
                            "max_hhi_concentration": 0.31,
                            "max_largest_risk_contribution_symbol": "000001",
                            "max_largest_risk_contribution_share": 0.62,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "group_exposure.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "max_group_risk_contribution_group": "银行",
                            "max_group_risk_contribution_share": 0.58,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "relative_performance.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "total_active_return": 0.04,
                            "annualized_alpha": 0.03,
                            "beta": 0.85,
                            "r_squared": 0.64,
                            "active_win_rate": 0.67,
                            "worst_active_return_date": "2024-01-03",
                            "max_active_drawdown": -0.02,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "factor_ic.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "total_score": {
                                "mean_ic": 0.12,
                                "ic_ir": 0.75,
                                "ic_t_stat": 2.10,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "factor_decay.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "total_score": {
                                "average_rank_correlation": 0.66,
                                "average_selected_retention_rate": 0.50,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "factor_correlation.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "strongest_pair": {
                                "factor": "momentum",
                                "compared_factor": "mean_reversion",
                                "average_correlation": -0.8,
                            },
                            "strongest_rank_pair": {
                                "factor": "momentum",
                                "compared_factor": "low_volatility",
                                "average_rank_correlation": 0.7,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "rolling_risk.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "worst_rolling_return": -0.03,
                            "worst_rolling_return_date": "2024-01-12",
                            "average_rolling_sharpe": 1.23,
                            "worst_rolling_drawdown": -0.04,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "execution_quality.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "fill_rate": 0.75,
                            "cost_bps": 8.2,
                            "dominant_constraint_category": "limit",
                            "market_constraint_rate": 0.6,
                            "worst_constraint_date": "2024-01-03",
                            "worst_constraint_dominant_category": "t_plus_one",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "return_attribution.json").write_text(
                json.dumps({"summary": {"total_residual_return": 0.0012, "total_cost_drag": 0.0034}}),
                encoding="utf-8",
            )
            (output_dir / "cost_attribution.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "total_cost": 123.45,
                            "fixed_slippage_cost": 12.30,
                            "market_impact_cost": 45.60,
                            "cost_bps": 9.9,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "pnl_ledger.json").write_text(
                json.dumps({"summary": {"max_abs_reconciliation_difference": 0.0, "reconciled": True}}),
                encoding="utf-8",
            )
            (output_dir / "strategy_health.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "score": 92.5,
                            "grade": "A",
                            "gate_status": "pass",
                            "gate_failures": 0,
                            "warnings": 1,
                            "strongest_factor_correlation": 0.82,
                            "strongest_factor_correlation_pair": "momentum vs mean_reversion",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "turnover_analysis.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "average_entries_per_rebalance": 1.25,
                            "average_exits_per_rebalance": 0.75,
                            "realized_holding_count": 4,
                            "average_realized_holding_days": 8.5,
                            "open_position_count": 2,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "price_data_quality_report.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "row_count": 8,
                            "symbol_count": 2,
                            "date_count": 4,
                            "start_date": "2024-01-02",
                            "end_date": "2024-01-05",
                            "symbols_with_missing_adjusted_close": 1,
                            "execution_price_field": "open",
                            "missing_execution_price_rows": 3,
                            "execution_price_coverage_rate": 0.625,
                            "missing_open_rows": 3,
                            "missing_vwap_rows": 4,
                            "suspended_days": 1,
                            "limit_up_days": 1,
                            "limit_down_days": 1,
                            "st_days": 1,
                            "custom_limit_rate_days": 2,
                            "untradable_days": 1,
                            "cannot_buy_days": 2,
                            "cannot_sell_days": 1,
                        }
                    }
                ),
                encoding="utf-8",
            )
            report_path = save_single_run_report_html(
                output_dir=output_dir,
                config=config,
                metrics=metrics,
                artifacts={
                    "equity_curve_svg": output_dir / "equity_curve.svg",
                    "drawdown_json": output_dir / "drawdown.json",
                    "exposure_json": output_dir / "exposure.json",
                    "group_exposure_json": output_dir / "group_exposure.json",
                    "rolling_risk_json": output_dir / "rolling_risk.json",
                    "relative_performance_json": output_dir / "relative_performance.json",
                    "factor_ic_json": output_dir / "factor_ic.json",
                    "factor_decay_json": output_dir / "factor_decay.json",
                    "factor_correlation_json": output_dir / "factor_correlation.json",
                    "execution_quality_json": output_dir / "execution_quality.json",
                    "return_attribution_json": output_dir / "return_attribution.json",
                    "cost_attribution_json": output_dir / "cost_attribution.json",
                    "pnl_ledger_json": output_dir / "pnl_ledger.json",
                    "strategy_health_json": output_dir / "strategy_health.json",
                    "turnover_analysis_json": output_dir / "turnover_analysis.json",
                    "price_data_quality_report_json": output_dir / "price_data_quality_report.json",
                },
                latest_holdings=("000001", "600519"),
                latest_rebalance=RebalanceRecord(
                    date=__import__("datetime").date(2024, 1, 8),
                    holdings=("000001", "600519"),
                    buy_turnover=0.12,
                    sell_turnover=0.08,
                    turnover=0.20,
                    cost=88.80,
                ),
                symbol_names={"000001": "平安银行", "600519": "贵州茅台"},
            )

            content = report_path.read_text(encoding="utf-8-sig")
            self.assertIn("<h1>回测报告</h1>", content)
            self.assertIn("总收益 / total_return", content)
            self.assertIn("核心结论", content)
            self.assertIn("当前持仓", content)
            self.assertIn("调仓摘要", content)
            self.assertIn("基准复盘", content)
            self.assertIn("复盘摘要", content)
            self.assertIn("配置摘要", content)
            self.assertIn("指标怎么看", content)
            self.assertIn("持仓代码说明", content)
            self.assertIn("2024-01-08", content)
            self.assertIn("12.00%", content)
            self.assertIn("8.00%", content)
            self.assertIn("20.00%", content)
            self.assertIn("88.80", content)
            self.assertIn("同期基准收益为 6.00%，策略跑赢基准 4.00%。", content)
            self.assertIn("1.100", content)
            self.assertIn("最大回撤日期", content)
            self.assertIn("策略健康评分", content)
            self.assertIn("有效持仓数", content)
            self.assertIn("最大单票权重", content)
            self.assertIn("最大风险贡献标的", content)
            self.assertIn("最大风险贡献占比", content)
            self.assertIn("62.00%", content)
            self.assertIn("最大分组风险贡献", content)
            self.assertIn("最大分组贡献占比", content)
            self.assertIn("58.00%", content)
            self.assertIn("总分平均IC", content)
            self.assertIn("总分ICIR", content)
            self.assertIn("总分稳定性", content)
            self.assertIn("入选留存率", content)
            self.assertIn("年化Alpha", content)
            self.assertIn("Beta", content)
            self.assertIn("R平方", content)
            self.assertIn("92.50", content)
            self.assertIn("策略健康等级", content)
            self.assertIn("策略闸门状态", content)
            self.assertIn("策略闸门失败数", content)
            self.assertIn("策略预警数量", content)
            self.assertIn("2024-01-10", content)
            self.assertIn("7.00", content)
            self.assertIn("否", content)
            self.assertIn("滚动最差收益", content)
            self.assertIn("-3.00%", content)
            self.assertIn("滚动最差收益日", content)
            self.assertIn("2024-01-12", content)
            self.assertIn("滚动平均夏普", content)
            self.assertIn("1.23", content)
            self.assertIn("滚动最大回撤", content)
            self.assertIn("-4.00%", content)
            self.assertIn("平均股票仓位", content)
            self.assertIn("82.00%", content)
            self.assertIn("平均持仓数量", content)
            self.assertIn("3.50", content)
            self.assertIn("累计主动收益", content)
            self.assertIn("4.00%", content)
            self.assertIn("主动胜率", content)
            self.assertIn("67.00%", content)
            self.assertIn("最差主动日", content)
            self.assertIn("2024-01-03", content)
            self.assertIn("主动最大回撤", content)
            self.assertIn("-2.00%", content)
            self.assertIn("成交率", content)
            self.assertIn("75.00%", content)
            self.assertIn("8.20 bps", content)
            self.assertIn("limit", content)
            self.assertIn("60.00%", content)
            self.assertIn("2024-01-03", content)
            self.assertIn("t_plus_one", content)
            self.assertIn("收益归因残差", content)
            self.assertIn("0.12%", content)
            self.assertIn("momentum vs mean_reversion", content)
            self.assertIn("momentum vs low_volatility", content)
            self.assertIn("82.00%", content)
            self.assertIn("成本拖累", content)
            self.assertIn("0.34%", content)
            self.assertIn("成本归因 bps", content)
            self.assertIn("9.90 bps", content)
            self.assertIn("固定滑点成本", content)
            self.assertIn("12.30", content)
            self.assertIn("市场冲击成本", content)
            self.assertIn("45.60", content)
            self.assertIn("Trading Behavior Diagnostics", content)
            self.assertIn("Average entries per rebalance", content)
            self.assertIn("1.25", content)
            self.assertIn("Average exits per rebalance", content)
            self.assertIn("0.75", content)
            self.assertIn("Average rebalance changes", content)
            self.assertIn("2.00", content)
            self.assertIn("Realized holding periods", content)
            self.assertIn("Average realized holding days", content)
            self.assertIn("8.50", content)
            self.assertIn("Open positions after final bar", content)
            self.assertIn("Turnover gate status", content)
            self.assertIn("Data Quality Diagnostics", content)
            self.assertIn("Price rows", content)
            self.assertIn("Symbols missing adjusted close", content)
            self.assertIn("Execution price field", content)
            self.assertIn("Missing execution price rows", content)
            self.assertIn("Execution price coverage", content)
            self.assertIn("62.50%", content)
            self.assertIn("Missing open rows", content)
            self.assertIn("Missing VWAP rows", content)
            self.assertIn("Limit-up rows", content)
            self.assertIn("Limit-down rows", content)
            self.assertIn("Custom limit-rate rows", content)
            self.assertIn("2024-01-02 to 2024-01-05", content)
            self.assertIn("最大对账差异", content)
            self.assertIn("对账状态", content)
            self.assertIn("已对齐", content)
            self.assertIn("000001（平安银行）", content)
            self.assertIn("600519（贵州茅台）", content)

    def test_saves_batch_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [
                {
                    "run_id": "run_001",
                    "annualized_return": 0.2,
                    "total_return": 0.1,
                    "sharpe": 1.0,
                    "sortino": 1.1,
                    "calmar": 2.0,
                    "health_score": 80.0,
                    "gate_status": "pass",
                    "gate_failures": 0,
                },
                {
                    "run_id": "run_002",
                    "annualized_return": 0.3,
                    "total_return": 0.2,
                    "sharpe": 1.5,
                    "sortino": 1.6,
                    "calmar": 3.0,
                    "health_score": 60.0,
                    "gate_status": "fail",
                    "gate_failures": 2,
                },
            ]
            stability_path = output_dir / "batch_stability.json"
            stability_path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "robust_region_run_count": 1,
                            "robust_region_rate": 0.5,
                            "robust_region_average_metric": 0.2,
                            "is_parameter_island": False,
                            "gate_passing_run_count": 1,
                            "gate_failing_run_count": 1,
                            "failed_gate_category_counts": {"risk": 2, "factor": 1},
                            "failed_gate_name_counts": {"Max drawdown": 2, "Factor correlation": 1},
                            "strongest_parameter": "param_top_n",
                            "best_parameter_values": {
                                "param_top_n": "3",
                                "param_rebalance_every_n_days": "5",
                            },
                            "parameter_recommendation_rationale": {
                                "param_top_n": {
                                    "recommended_value": "3",
                                    "reason": "highest_average_composite_score",
                                    "is_also_best_by_metric": False,
                                    "best_value_by_metric": "4",
                                    "average_composite_score": 0.42,
                                    "gate_passing_rate": 0.5,
                                }
                            },
                            "parameter_recommendation_summary": "Recommended parameter values by average composite score: param_top_n=3 (composite 0.420, gate pass 50.00%). Metric and composite recommendations diverge for: param_top_n metric-best=4.",
                            "recommended_actions": [
                                "Risk gates fail often: reduce position concentration, raise cash buffer, shorten rebalance exposure, or add drawdown-aware filters.",
                                "Most common failed gate is 'Max drawdown'; review the single-run strategy_health_gates.csv files for affected runs first.",
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            report_path = save_batch_report_html(
                output_dir=output_dir,
                rows=rows,
                rank_by="annualized_return",
                artifacts={
                    "batch_chart_svg": output_dir / "batch_annualized_return.svg",
                    "batch_stability_json": stability_path,
                },
            )

            content = report_path.read_text(encoding="utf-8-sig")
            self.assertIn("<h1>A股参数扫描报告</h1>", content)
            self.assertIn("研究结论", content)
            self.assertIn("最优参数", content)
            self.assertIn("结果观察", content)
            self.assertIn("最佳方案", content)
            self.assertIn("方案2", content)
            self.assertIn("内部编号", content)
            self.assertIn("run_001", content)
            self.assertIn("Gate status", content)
            self.assertIn("Health score", content)
            self.assertIn("闸门通过运行数", content)
            self.assertIn("闸门失败运行数", content)
            self.assertIn("最常失败闸门类别", content)
            self.assertIn("risk: 2", content)
            self.assertIn("最常失败闸门", content)
            self.assertIn("Max drawdown: 2", content)
            self.assertIn("影响最强参数", content)
            self.assertIn("param_top_n", content)
            self.assertIn("推荐参数档位", content)
            self.assertIn("param_rebalance_every_n_days=5", content)
            self.assertIn("参数推荐依据", content)
            self.assertIn("平均综合分最高", content)
            self.assertIn("排序指标最优=4", content)
            self.assertIn("综合分=0.420", content)
            self.assertIn("通过率=50.00%", content)
            self.assertIn("参数推荐总结", content)
            self.assertIn("按平均综合分推荐参数", content)
            self.assertIn("排序指标最优与综合分推荐不一致", content)
            self.assertIn("建议动作", content)
            self.assertIn("风险闸门频繁失败", content)
            self.assertIn("建议动作数量", content)
            self.assertIn("gate_status", content)
            self.assertIn("health_score", content)
            self.assertIn("pass", content)
            self.assertIn("年化收益 / annualized_return", content)
            self.assertIn("稳健热区数量", content)
            self.assertIn("稳健热区占比", content)


if __name__ == "__main__":
    unittest.main()
