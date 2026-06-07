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
                )
            ]

            trades_path = save_trades(trades, output_dir)

            content = trades_path.read_text(encoding="utf-8-sig")
            self.assertIn("方向 / side", content)
            self.assertIn("成交金额 / gross_value", content)
            self.assertIn("佣金 / commission", content)
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
            report_path = save_single_run_report_html(
                output_dir=output_dir,
                config=config,
                metrics=metrics,
                artifacts={"equity_curve_svg": output_dir / "equity_curve.svg"},
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
                },
                {
                    "run_id": "run_002",
                    "annualized_return": 0.3,
                    "total_return": 0.2,
                    "sharpe": 1.5,
                    "sortino": 1.6,
                    "calmar": 3.0,
                },
            ]
            report_path = save_batch_report_html(
                output_dir=output_dir,
                rows=rows,
                rank_by="annualized_return",
                artifacts={"batch_chart_svg": output_dir / "batch_annualized_return.svg"},
            )

            content = report_path.read_text(encoding="utf-8-sig")
            self.assertIn("<h1>A股参数扫描报告</h1>", content)
            self.assertIn("研究结论", content)
            self.assertIn("最优参数", content)
            self.assertIn("结果观察", content)
            self.assertIn("最佳方案", content)
            self.assertIn("方案2", content)
            self.assertIn("内部编号", content)
            self.assertIn("run_002", content)
            self.assertIn("年化收益 / annualized_return", content)


if __name__ == "__main__":
    unittest.main()
