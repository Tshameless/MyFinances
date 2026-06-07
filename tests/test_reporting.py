from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from python_quant.config import BacktestConfig
from python_quant.models import BacktestMetrics, EquityPoint
from python_quant.reporting import (
    save_batch_chart_svg,
    save_batch_heatmap_svg,
    save_batch_rankings,
    save_batch_report_html,
    save_equity_chart_svg,
    save_performance_summary_json,
    save_run_manifest,
    save_single_run_report_html,
)


class ReportingTests(unittest.TestCase):
    def test_saves_run_manifest_with_config_and_artifacts(self) -> None:
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
            )
            summary_json_path = save_performance_summary_json(metrics, output_dir)

            manifest_path = save_run_manifest(
                output_dir=output_dir,
                config=config,
                inputs={"demo": True, "csv": None, "benchmark_csv": None, "config": None},
                artifacts={"performance_summary_json": summary_json_path},
                metrics=metrics,
            )

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(True, payload["inputs"]["demo"])
            self.assertEqual(str(summary_json_path), payload["artifacts"]["performance_summary_json"])
            self.assertEqual(0.1, payload["metrics"]["total_return"])
            self.assertEqual(str(output_dir), payload["config"]["output_dir"])

    def test_saves_equity_chart_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            curve = [
                EquityPoint(date=__import__("datetime").date(2024, 1, 2), equity=100.0, daily_return=0.01, holdings=("AAA",)),
                EquityPoint(date=__import__("datetime").date(2024, 1, 3), equity=101.0, daily_return=0.02, holdings=("AAA",)),
            ]

            chart_path = save_equity_chart_svg(curve, output_dir)

            content = chart_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)
            self.assertIn("Equity Curve", content)

    def test_saves_batch_rankings_and_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [
                {"run_id": "run_001", "annualized_return": 0.2, "param_top_n": 2, "param_rebalance_every_n_days": 5},
                {"run_id": "run_002", "annualized_return": 0.3, "param_top_n": 3, "param_rebalance_every_n_days": 5},
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
            best_payload = json.loads(best_run_json.read_text(encoding="utf-8"))
            self.assertEqual("run_002", best_payload["best_run"]["run_id"])

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
            )
            report_path = save_single_run_report_html(
                output_dir=output_dir,
                config=config,
                metrics=metrics,
                artifacts={"equity_curve_svg": output_dir / "equity_curve.svg"},
            )

            content = report_path.read_text(encoding="utf-8")
            self.assertIn("MyFinances Backtest Report", content)
            self.assertIn("Total return", content)

    def test_saves_batch_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            rows = [
                {"run_id": "run_001", "annualized_return": 0.2, "total_return": 0.1, "sharpe": 1.0, "sortino": 1.1, "calmar": 2.0},
                {"run_id": "run_002", "annualized_return": 0.3, "total_return": 0.2, "sharpe": 1.5, "sortino": 1.6, "calmar": 3.0},
            ]
            report_path = save_batch_report_html(
                output_dir=output_dir,
                rows=rows,
                rank_by="annualized_return",
                artifacts={"batch_chart_svg": output_dir / "batch_annualized_return.svg"},
            )

            content = report_path.read_text(encoding="utf-8")
            self.assertIn("MyFinances Batch Sweep Report", content)
            self.assertIn("run_002", content)


if __name__ == "__main__":
    unittest.main()
