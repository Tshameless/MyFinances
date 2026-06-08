from __future__ import annotations

import unittest
from datetime import date, timedelta

from python_quant.analysis import (
    build_batch_stability_analysis,
    build_cost_attribution_analysis,
    build_drawdown_analysis,
    build_execution_quality_analysis,
    build_exposure_analysis,
    build_factor_correlation_analysis,
    build_factor_decay_analysis,
    build_factor_group_return_analysis,
    build_factor_ic_analysis,
    build_group_exposure_analysis,
    build_monthly_return_analysis,
    build_pnl_ledger_analysis,
    build_relative_performance_analysis,
    build_return_attribution_analysis,
    build_rolling_risk_analysis,
    build_split_performance,
    build_strategy_health_analysis,
    build_turnover_analysis,
    build_walk_forward_optimization_summary,
    build_walk_forward_summary,
    build_walk_forward_train_test_windows,
    build_walk_forward_windows,
)
from python_quant.execution_analysis import (
    build_execution_quality_analysis as build_execution_quality_direct,
)
from python_quant.exposure_analysis import build_exposure_analysis as build_exposure_direct
from python_quant.models import (
    BacktestMetrics,
    BenchmarkPoint,
    EquityPoint,
    FactorScoreRecord,
    PositionPoint,
    PriceBar,
    TradeAttemptRecord,
    TradeRecord,
)
from python_quant.risk_analysis import build_drawdown_analysis as build_drawdown_direct


class AnalysisTests(unittest.TestCase):
    def test_analysis_compatibility_exports_delegate_to_split_modules(self) -> None:
        self.assertIs(build_drawdown_analysis, build_drawdown_direct)
        self.assertIs(build_execution_quality_analysis, build_execution_quality_direct)
        self.assertIs(build_exposure_analysis, build_exposure_direct)
        self.assertTrue(callable(build_turnover_analysis))

    def test_builds_in_sample_and_out_of_sample_split(self) -> None:
        start = date(2024, 1, 2)
        curve = [
            EquityPoint(
                date=start + timedelta(days=index),
                equity=100.0 + index,
                daily_return=0.01,
                holdings=("000001",),
            )
            for index in range(6)
        ]

        split = build_split_performance(curve)

        self.assertIn("in_sample", split)
        self.assertIn("out_of_sample", split)
        self.assertEqual(3, split["in_sample"]["periods"])
        self.assertEqual(3, split["out_of_sample"]["periods"])

    def test_builds_walk_forward_windows_and_summary(self) -> None:
        dates = [date(2024, 1, 2) + timedelta(days=index) for index in range(8)]

        windows = build_walk_forward_windows(dates, window_size=3, step_size=2)
        summary = build_walk_forward_summary(
            [
                {
                    "window_id": "window_001",
                    "total_return": 0.02,
                    "annualized_return": 0.2,
                    "max_drawdown": -0.01,
                    "sharpe": 1.0,
                },
                {
                    "window_id": "window_002",
                    "total_return": -0.01,
                    "annualized_return": -0.1,
                    "max_drawdown": -0.03,
                    "sharpe": -0.2,
                },
            ]
        )

        self.assertEqual(
            [
                (date(2024, 1, 2), date(2024, 1, 4)),
                (date(2024, 1, 4), date(2024, 1, 6)),
                (date(2024, 1, 6), date(2024, 1, 8)),
            ],
            windows,
        )
        self.assertEqual(2, summary["summary"]["windows"])
        self.assertEqual(0.5, summary["summary"]["positive_window_rate"])
        self.assertEqual("window_001", summary["summary"]["best_window_id"])

    def test_builds_walk_forward_train_test_windows_and_optimization_summary(self) -> None:
        dates = [date(2024, 1, 2) + timedelta(days=index) for index in range(10)]

        windows = build_walk_forward_train_test_windows(
            dates,
            train_size=4,
            test_size=2,
            step_size=2,
        )
        summary = build_walk_forward_optimization_summary(
            [
                {
                    "window_id": "window_001",
                    "train_annualized_return": 0.2,
                    "train_health_score": 80,
                    "train_gate_status": "pass",
                    "test_total_return": 0.03,
                    "test_annualized_return": 0.3,
                    "test_max_drawdown": -0.02,
                    "param_top_n": 2,
                },
                {
                    "window_id": "window_002",
                    "train_annualized_return": 0.1,
                    "train_health_score": 60,
                    "train_gate_status": "fail",
                    "test_total_return": -0.01,
                    "test_annualized_return": -0.1,
                    "test_max_drawdown": -0.04,
                    "param_top_n": 3,
                },
            ]
        )

        self.assertEqual(3, len(windows))
        self.assertEqual(date(2024, 1, 2), windows[0]["train_start_date"])
        self.assertEqual(date(2024, 1, 5), windows[0]["train_end_date"])
        self.assertEqual(date(2024, 1, 6), windows[0]["test_start_date"])
        self.assertEqual("window_001", summary["summary"]["best_test_window_id"])
        self.assertEqual(2, summary["summary"]["selected_parameter_sets"])
        self.assertEqual("gate_pass_first_then_metric", summary["summary"]["selection_policy"])
        self.assertEqual(1, summary["summary"]["gate_passing_train_windows"])
        self.assertEqual(0.5, summary["summary"]["gate_passing_train_window_rate"])
        self.assertEqual(70, summary["summary"]["average_selected_train_health_score"])
        self.assertAlmostEqual(0.05, summary["summary"]["average_train_test_annualized_gap"])
        self.assertEqual(1, summary["summary"]["degraded_test_windows"])
        self.assertEqual(0.5, summary["summary"]["degraded_test_window_rate"])
        self.assertEqual("window_002", summary["summary"]["worst_degradation_window_id"])
        self.assertAlmostEqual(0.2, summary["summary"]["worst_train_test_annualized_gap"])
        self.assertAlmostEqual(1.5, summary["rows"][0]["test_to_train_efficiency"])
        self.assertFalse(summary["rows"][0]["is_degraded_out_of_sample"])
        self.assertTrue(summary["rows"][1]["is_degraded_out_of_sample"])
        self.assertEqual({"param_top_n=2": 1, "param_top_n=3": 1}, summary["summary"]["selected_parameter_set_counts"])
        self.assertEqual(1, summary["summary"]["parameter_drift_count"])
        self.assertEqual(1.0, summary["summary"]["parameter_drift_rate"])
        self.assertEqual({"2": 1, "3": 1}, summary["summary"]["parameter_selection_counts"]["param_top_n"])
        self.assertEqual("mixed", summary["summary"]["oos_stability_grade"])
        self.assertEqual("medium", summary["summary"]["overfit_risk"])

    def test_walk_forward_optimization_ignores_parameter_value_context_fields(self) -> None:
        summary = build_walk_forward_optimization_summary(
            [
                {
                    "window_id": "window_001",
                    "train_annualized_return": 0.2,
                    "train_health_score": 80,
                    "train_gate_status": "pass",
                    "test_total_return": 0.03,
                    "test_annualized_return": 0.3,
                    "test_max_drawdown": -0.02,
                    "param_top_n": 2,
                    "param_top_n_value_average_annualized_return": 0.2,
                },
                {
                    "window_id": "window_002",
                    "train_annualized_return": 0.1,
                    "train_health_score": 60,
                    "train_gate_status": "pass",
                    "test_total_return": 0.01,
                    "test_annualized_return": 0.2,
                    "test_max_drawdown": -0.04,
                    "param_top_n": 2,
                    "param_top_n_value_average_annualized_return": 0.4,
                },
            ]
        )

        self.assertEqual(1, summary["summary"]["selected_parameter_sets"])
        self.assertEqual(0, summary["summary"]["parameter_drift_count"])
        self.assertNotIn(
            "param_top_n_value_average_annualized_return",
            summary["summary"]["parameter_selection_counts"],
        )

    def test_builds_drawdown_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 2), equity=100.0, daily_return=0.0, holdings=()),
            EquityPoint(date=date(2024, 1, 3), equity=110.0, daily_return=0.1, holdings=()),
            EquityPoint(date=date(2024, 1, 4), equity=99.0, daily_return=-0.1, holdings=()),
        ]

        analysis = build_drawdown_analysis(curve)

        self.assertAlmostEqual(-0.1, analysis["summary"]["max_drawdown"])
        self.assertEqual("2024-01-04", analysis["summary"]["max_drawdown_date"])
        self.assertEqual("2024-01-03", analysis["summary"]["peak_date"])
        self.assertEqual(1, analysis["summary"]["underwater_days"])
        self.assertFalse(analysis["summary"]["is_recovered"])
        self.assertEqual(1, analysis["summary"]["longest_underwater_days"])
        self.assertEqual("2024-01-04", analysis["summary"]["longest_underwater_start_date"])
        self.assertEqual("2024-01-04", analysis["summary"]["longest_underwater_end_date"])
        self.assertEqual(0.95, analysis["summary"]["tail_risk_confidence"])
        self.assertAlmostEqual(0.1, analysis["summary"]["daily_var"])
        self.assertAlmostEqual(0.1, analysis["summary"]["daily_expected_shortfall"])
        self.assertAlmostEqual(-0.1, analysis["summary"]["worst_daily_return"])
        self.assertTrue(analysis["rows"][-1]["is_underwater"])
        self.assertEqual(1, analysis["rows"][-1]["underwater_days"])

    def test_builds_monthly_return_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 31), equity=110.0, daily_return=0.1, holdings=()),
            EquityPoint(date=date(2024, 2, 1), equity=121.0, daily_return=0.1, holdings=()),
            EquityPoint(date=date(2024, 2, 29), equity=108.9, daily_return=-0.1, holdings=()),
        ]

        analysis = build_monthly_return_analysis(curve)

        self.assertEqual(2, analysis["summary"]["months"])
        self.assertEqual("2024-01", analysis["summary"]["best_month"])
        self.assertEqual("2024-02", analysis["summary"]["worst_month"])

    def test_builds_rolling_risk_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 2), equity=101.0, daily_return=0.01, holdings=()),
            EquityPoint(date=date(2024, 1, 3), equity=99.99, daily_return=-0.01, holdings=()),
            EquityPoint(date=date(2024, 1, 4), equity=101.9898, daily_return=0.02, holdings=()),
            EquityPoint(date=date(2024, 1, 5), equity=100.969902, daily_return=-0.01, holdings=()),
        ]

        analysis = build_rolling_risk_analysis(curve, window=3)

        rows = analysis["rows"]
        summary = analysis["summary"]
        self.assertEqual(2, len(rows))
        self.assertEqual("2024-01-04", rows[0]["date"])
        self.assertAlmostEqual((1.01 * 0.99 * 1.02) - 1.0, rows[0]["rolling_return"])
        self.assertLess(rows[0]["rolling_max_drawdown"], 0)
        self.assertEqual(3, summary["window"])
        self.assertEqual(2, summary["periods"])
        self.assertEqual("2024-01-04", summary["best_rolling_return_date"])
        self.assertEqual("2024-01-05", summary["worst_rolling_return_date"])
        self.assertIn("average_rolling_sharpe", summary)
        self.assertGreater(summary["positive_window_rate"], 0)

    def test_builds_relative_performance_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 2), equity=101.0, daily_return=0.01, holdings=()),
            EquityPoint(date=date(2024, 1, 3), equity=99.99, daily_return=-0.01, holdings=()),
            EquityPoint(date=date(2024, 1, 4), equity=101.9898, daily_return=0.02, holdings=()),
        ]
        benchmark = [
            BenchmarkPoint(date=date(2024, 1, 2), equity=100.5, daily_return=0.005),
            BenchmarkPoint(date=date(2024, 1, 3), equity=101.0025, daily_return=0.005),
            BenchmarkPoint(date=date(2024, 1, 4), equity=101.5075, daily_return=0.005),
        ]

        analysis = build_relative_performance_analysis(curve, benchmark)

        self.assertTrue(analysis["summary"]["has_benchmark"])
        self.assertEqual(3, analysis["summary"]["periods"])
        self.assertAlmostEqual((1.005 * 0.985 * 1.015) - 1.0, analysis["summary"]["total_active_return"])
        self.assertAlmostEqual((0.005 - 0.015 + 0.015) / 3, analysis["summary"]["average_active_return"])
        self.assertEqual(2, analysis["summary"]["positive_active_days"])
        self.assertEqual(1, analysis["summary"]["negative_active_days"])
        self.assertEqual("2024-01-04", analysis["summary"]["best_active_return_date"])
        self.assertEqual("2024-01-03", analysis["summary"]["worst_active_return_date"])
        self.assertLess(analysis["summary"]["max_active_drawdown"], 0)
        self.assertIn("cumulative_active_return", analysis["rows"][0])
        self.assertIn("beta", analysis["summary"])
        self.assertIn("annualized_alpha", analysis["summary"])
        self.assertIn("r_squared", analysis["summary"])
        self.assertGreaterEqual(analysis["summary"]["r_squared"], 0.0)

    def test_builds_strategy_health_analysis(self) -> None:
        metrics = _metrics(
            total_return=-0.02,
            max_drawdown=-0.18,
            sharpe=0.2,
        )

        analysis = build_strategy_health_analysis(
            metrics=metrics,
            drawdown_summary={"max_drawdown_date": "2024-01-10"},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": -0.08,
                "worst_rolling_drawdown": -0.12,
            },
            relative_summary={"active_win_rate": 0.4},
            execution_summary={"fill_rate": 0.6},
            exposure_summary={"max_largest_position_weight": 0.55},
            return_attribution_summary={"total_residual_return": 0.02},
            cost_attribution_summary={"cost_bps": 80.0},
            pnl_ledger_summary={"reconciled": False, "max_abs_reconciliation_difference": 1.0},
            turnover_summary={
                "average_entries_per_rebalance": 2.0,
                "average_exits_per_rebalance": 2.0,
                "realized_holding_count": 3,
                "average_realized_holding_days": 1.0,
            },
        )

        self.assertEqual("blocked", analysis["summary"]["status"])
        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertGreater(analysis["summary"]["gate_failures"], 0)
        self.assertGreater(analysis["summary"]["critical_warnings"], 0)
        self.assertEqual(5, analysis["summary"]["rolling_window"])
        self.assertEqual(2.0, analysis["summary"]["average_entries_per_rebalance"])
        self.assertEqual(1.0, analysis["summary"]["average_realized_holding_days"])
        self.assertTrue(any(row["category"] == "turnover" for row in analysis["rows"]))
        self.assertTrue(analysis["warnings"])
        self.assertTrue(analysis["gates"])

    def test_strategy_health_uses_custom_gate_thresholds(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={"daily_var": 0.06},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": -0.08,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={"fill_rate": 0.95},
            exposure_summary={"max_largest_position_weight": 0.30},
            return_attribution_summary={"total_residual_return": 0.01},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            gate_thresholds={
                "max_allowed_daily_var": 0.05,
                "min_allowed_rolling_return": -0.05,
            },
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertEqual(0.06, analysis["summary"]["daily_var"])
        self.assertTrue(
            any(
                gate["category"] == "stability" and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )
        self.assertTrue(
            any(
                gate["category"] == "risk"
                and str(gate["name"]).startswith("Daily VaR")
                and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )

    def test_strategy_health_uses_turnover_gate_thresholds(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": 0.02,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={"fill_rate": 0.95},
            exposure_summary={"max_largest_position_weight": 0.30},
            return_attribution_summary={"total_residual_return": 0.001},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            turnover_summary={
                "average_entries_per_rebalance": 2.0,
                "average_exits_per_rebalance": 1.0,
                "realized_holding_count": 2,
                "average_realized_holding_days": 2.0,
            },
            gate_thresholds={
                "max_allowed_rebalance_changes": 2.0,
                "min_allowed_holding_days": 3.0,
            },
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        failed_turnover_gates = [
            gate for gate in analysis["gates"]
            if gate["category"] == "turnover" and gate["passed"] is False
        ]
        self.assertEqual(2, len(failed_turnover_gates))

    def test_strategy_health_uses_market_constraint_gate_threshold(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": 0.02,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={
                "fill_rate": 0.95,
                "market_constraint_rate": 0.75,
                "dominant_constraint_category": "limit",
            },
            exposure_summary={"max_largest_position_weight": 0.30},
            return_attribution_summary={"total_residual_return": 0.001},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            gate_thresholds={"max_allowed_market_constraint_rate": 0.50},
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertEqual(0.75, analysis["summary"]["market_constraint_rate"])
        self.assertEqual("limit", analysis["summary"]["dominant_constraint_category"])
        self.assertTrue(
            any(
                gate["category"] == "execution" and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )
        self.assertTrue(
            any(
                row["category"] == "execution" and row["name"] == "Market constraint rate"
                for row in analysis["rows"]
            )
        )

    def test_strategy_health_uses_execution_price_coverage_gate_threshold(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": 0.02,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={"fill_rate": 0.95},
            data_quality_summary={
                "execution_price_field": "vwap",
                "execution_price_coverage_rate": 0.90,
                "missing_execution_price_rows": 3,
            },
            exposure_summary={"max_largest_position_weight": 0.30},
            return_attribution_summary={"total_residual_return": 0.001},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            gate_thresholds={"min_allowed_execution_price_coverage": 0.99},
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertEqual("vwap", analysis["summary"]["execution_price_field"])
        self.assertEqual(0.90, analysis["summary"]["execution_price_coverage_rate"])
        self.assertTrue(
            any(
                gate["category"] == "data"
                and str(gate["name"]).startswith("Execution price coverage")
                and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )

    def test_strategy_health_uses_factor_correlation_gate_threshold(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": 0.02,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={"fill_rate": 0.95},
            exposure_summary={"max_largest_position_weight": 0.30},
            return_attribution_summary={"total_residual_return": 0.001},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            factor_correlation_summary={
                "strongest_pair": {
                    "factor": "momentum",
                    "compared_factor": "mean_reversion",
                    "average_correlation": 0.96,
                }
            },
            gate_thresholds={"max_allowed_factor_correlation": 0.90},
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertEqual(0.96, analysis["summary"]["strongest_factor_correlation"])
        self.assertEqual("momentum vs mean_reversion", analysis["summary"]["strongest_factor_correlation_pair"])
        self.assertTrue(
            any(
                gate["category"] == "factor" and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )
        self.assertTrue(any(row["category"] == "factor" for row in analysis["rows"]))

    def test_strategy_health_uses_group_weight_gate_threshold(self) -> None:
        analysis = build_strategy_health_analysis(
            metrics=_metrics(total_return=0.1, max_drawdown=-0.04, sharpe=1.5),
            drawdown_summary={},
            rolling_risk_summary={
                "window": 5,
                "worst_rolling_return": 0.02,
                "worst_rolling_drawdown": -0.02,
            },
            relative_summary={},
            execution_summary={"fill_rate": 0.95},
            exposure_summary={"max_largest_position_weight": 0.30},
            group_exposure_summary={
                "max_largest_group_weight": 0.72,
                "max_group_risk_contribution_group": "银行",
                "max_group_risk_contribution_share": 0.80,
            },
            return_attribution_summary={"total_residual_return": 0.001},
            cost_attribution_summary={"cost_bps": 5.0},
            pnl_ledger_summary={"reconciled": True},
            gate_thresholds={"max_allowed_group_weight": 0.60},
        )

        self.assertEqual("fail", analysis["summary"]["gate_status"])
        self.assertEqual(0.72, analysis["summary"]["max_largest_group_weight"])
        self.assertEqual("银行", analysis["summary"]["max_group_risk_contribution_group"])
        self.assertTrue(
            any(
                gate["category"] == "exposure"
                and str(gate["name"]).startswith("Maximum group weight")
                and gate["passed"] is False
                for gate in analysis["gates"]
            )
        )

    def test_builds_execution_quality_analysis(self) -> None:
        trades = [
            TradeRecord(
                date=date(2024, 1, 2),
                symbol="000001",
                side="BUY",
                shares=100,
                price=10.0,
                gross_value=1000.0,
                commission=1.0,
                slippage=0.5,
                transfer_fee=0.0,
                stamp_duty=0.0,
                total_cost=1.5,
                cash_change=-1001.5,
                reason="rebalance_entry",
            ),
            TradeRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                side="SELL",
                shares=100,
                price=11.0,
                gross_value=1100.0,
                commission=1.0,
                slippage=0.5,
                transfer_fee=0.0,
                stamp_duty=1.1,
                total_cost=2.6,
                cash_change=1097.4,
                reason="rebalance_exit",
            ),
        ]
        attempts = [
            TradeAttemptRecord(
                date=date(2024, 1, 2),
                symbol="600519",
                side="BUY",
                target_shares=100,
                price=100.0,
                reason="insufficient_cash_for_lot",
                cash=50.0,
            ),
            TradeAttemptRecord(
                date=date(2024, 1, 2),
                symbol="000333",
                side="BUY",
                target_shares=100,
                price=20.0,
                reason="limit_up_blocked",
                cash=1000.0,
            ),
            TradeAttemptRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                side="SELL",
                target_shares=100,
                price=10.0,
                reason="t_plus_one_locked",
                cash=1000.0,
            )
        ]

        analysis = build_execution_quality_analysis(trades, attempts)

        self.assertEqual(5, analysis["summary"]["orders"])
        self.assertAlmostEqual(2 / 5, analysis["summary"]["fill_rate"])
        self.assertAlmostEqual(4.1 / 2100.0 * 10_000, analysis["summary"]["cost_bps"])
        self.assertIn("insufficient_cash_for_lot", [row["key"] for row in analysis["rows"]])
        self.assertEqual(3, analysis["summary"]["constraint_categories"])
        self.assertEqual({"cash": 1, "limit": 1, "t_plus_one": 1}, analysis["summary"]["constraint_category_counts"])
        self.assertAlmostEqual(2 / 3, analysis["summary"]["market_constraint_rate"])
        self.assertEqual(2, analysis["summary"]["constraint_days"])
        self.assertEqual("2024-01-02", analysis["summary"]["worst_constraint_date"])
        self.assertEqual(2, analysis["summary"]["worst_constraint_rejected_orders"])
        self.assertEqual(200, analysis["summary"]["worst_constraint_rejected_target_shares"])
        self.assertIn("constraint_category", [row["category"] for row in analysis["rows"]])
        self.assertIn("daily_constraint", [row["category"] for row in analysis["rows"]])

    def test_builds_cost_attribution_analysis(self) -> None:
        trades = [
            TradeRecord(
                date=date(2024, 1, 2),
                symbol="000001",
                side="BUY",
                shares=100,
                price=10.0,
                gross_value=1000.0,
                commission=1.0,
                slippage=0.5,
                transfer_fee=0.1,
                stamp_duty=0.0,
                total_cost=1.6,
                cash_change=-1001.6,
                reason="rebalance_entry",
                fixed_slippage=0.2,
                market_impact=0.3,
            ),
            TradeRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                side="SELL",
                shares=100,
                price=11.0,
                gross_value=1100.0,
                commission=1.0,
                slippage=0.5,
                transfer_fee=0.1,
                stamp_duty=1.1,
                total_cost=2.7,
                cash_change=1097.3,
                reason="rebalance_exit",
                fixed_slippage=0.2,
                market_impact=0.3,
            ),
        ]

        analysis = build_cost_attribution_analysis(trades, {"000001": "银行"})

        self.assertEqual(10, len(analysis["rows"]))
        self.assertEqual(2, analysis["summary"]["trades"])
        self.assertAlmostEqual(4.3, analysis["summary"]["total_cost"])
        self.assertAlmostEqual(2.0, analysis["summary"]["component_costs"]["commission"])
        self.assertAlmostEqual(0.4, analysis["summary"]["component_costs"]["fixed_slippage"])
        self.assertAlmostEqual(0.6, analysis["summary"]["component_costs"]["market_impact"])
        self.assertAlmostEqual(1.0, analysis["summary"]["slippage_cost"])
        self.assertAlmostEqual(0.4, analysis["summary"]["fixed_slippage_cost"])
        self.assertAlmostEqual(0.6, analysis["summary"]["market_impact_cost"])
        self.assertAlmostEqual(1.1, analysis["summary"]["component_costs"]["stamp_duty"])
        self.assertAlmostEqual(1.6, analysis["summary"]["side_costs"]["BUY"])
        self.assertAlmostEqual(4.3, analysis["summary"]["group_costs"]["银行"])

    def test_builds_pnl_ledger_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 2), equity=1000.0, daily_return=0.0, holdings=("000001",)),
            EquityPoint(date=date(2024, 1, 3), equity=1010.0, daily_return=0.01, holdings=("000001",)),
        ]
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=9.0, market_value=900.0, weight=0.9, cash=100.0, total_equity=1000.0),
            PositionPoint(date=date(2024, 1, 2), symbol="CASH", shares=0, price=1.0, market_value=100.0, weight=0.1, cash=100.0, total_equity=1000.0),
            PositionPoint(date=date(2024, 1, 3), symbol="000001", shares=100, price=10.0, market_value=1000.0, weight=0.990099, cash=10.0, total_equity=1010.0),
            PositionPoint(date=date(2024, 1, 3), symbol="CASH", shares=0, price=1.0, market_value=10.0, weight=0.009901, cash=10.0, total_equity=1010.0),
        ]
        trades = [
            TradeRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                side="BUY",
                shares=10,
                price=9.0,
                gross_value=90.0,
                commission=1.0,
                slippage=0.0,
                transfer_fee=0.0,
                stamp_duty=0.0,
                total_cost=1.0,
                cash_change=-91.0,
                reason="rebalance_entry",
            )
        ]

        analysis = build_pnl_ledger_analysis(curve, positions, trades)

        self.assertEqual(2, analysis["summary"]["periods"])
        self.assertTrue(analysis["summary"]["reconciled"])
        self.assertAlmostEqual(0.0, analysis["summary"]["max_abs_reconciliation_difference"])
        self.assertAlmostEqual(10.0, analysis["summary"]["total_equity_change"])
        self.assertAlmostEqual(-91.0, analysis["rows"][1]["net_cash_flow"])
        self.assertAlmostEqual(1010.0, analysis["rows"][1]["ledger_equity"])

    def test_builds_exposure_analysis(self) -> None:
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=10, market_value=1000, weight=0.5, cash=200, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="600519", shares=10, price=80, market_value=800, weight=0.4, cash=200, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="CASH", shares=0, price=1, market_value=200, weight=0.1, cash=200, total_equity=2000),
        ]

        analysis = build_exposure_analysis(positions)

        self.assertEqual(1, analysis["summary"]["periods"])
        self.assertEqual(2.0, analysis["summary"]["average_holding_count"])
        self.assertAlmostEqual(0.9, analysis["summary"]["average_stock_weight"])
        self.assertAlmostEqual(0.41, analysis["summary"]["average_hhi_concentration"])
        self.assertAlmostEqual(0.41, analysis["summary"]["max_hhi_concentration"])
        self.assertAlmostEqual(1 / 0.41, analysis["summary"]["average_effective_position_count"])
        self.assertAlmostEqual(1 / 0.41, analysis["summary"]["min_effective_position_count"])
        self.assertAlmostEqual(1 / 0.41, analysis["rows"][0]["effective_position_count"])
        self.assertEqual("000001", analysis["rows"][0]["largest_risk_contribution_symbol"])
        self.assertAlmostEqual(0.25 / 0.41, analysis["rows"][0]["largest_risk_contribution_share"])
        self.assertEqual("000001", analysis["summary"]["max_largest_risk_contribution_symbol"])
        self.assertAlmostEqual(0.25 / 0.41, analysis["summary"]["max_largest_risk_contribution_share"])

    def test_builds_group_exposure_analysis(self) -> None:
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=10, market_value=1000, weight=0.5, cash=200, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="600519", shares=10, price=80, market_value=800, weight=0.4, cash=200, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="CASH", shares=0, price=1, market_value=200, weight=0.1, cash=200, total_equity=2000),
        ]

        analysis = build_group_exposure_analysis(
            positions,
            {"000001": "银行", "600519": "消费"},
        )

        self.assertTrue(analysis["summary"]["has_group_mapping"])
        self.assertEqual(["消费", "银行"], analysis["summary"]["groups"])
        self.assertAlmostEqual(0.5, analysis["summary"]["max_largest_group_weight"])
        self.assertAlmostEqual(0.41, analysis["summary"]["average_group_hhi_concentration"])
        self.assertAlmostEqual(1 / 0.41, analysis["summary"]["average_effective_group_count"])
        self.assertAlmostEqual(1 / 0.41, analysis["summary"]["min_effective_group_count"])
        self.assertEqual("银行", analysis["summary"]["max_group_risk_contribution_group"])
        self.assertAlmostEqual(0.25 / 0.41, analysis["summary"]["max_group_risk_contribution_share"])
        self.assertEqual(2, len(analysis["rows"]))
        bank_row = next(row for row in analysis["rows"] if row["group"] == "银行")
        self.assertAlmostEqual(0.25 / 0.41, bank_row["risk_contribution_share"])

    def test_builds_return_attribution_analysis(self) -> None:
        curve = [
            EquityPoint(date=date(2024, 1, 2), equity=1000.0, daily_return=0.0, holdings=("000001",)),
            EquityPoint(date=date(2024, 1, 3), equity=1010.0, daily_return=0.01, holdings=("000001",)),
        ]
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=10.0, market_value=1000.0, weight=1.0, cash=0.0, total_equity=1000.0),
            PositionPoint(date=date(2024, 1, 3), symbol="000001", shares=100, price=10.1, market_value=1010.0, weight=1.0, cash=0.0, total_equity=1010.0),
        ]

        analysis = build_return_attribution_analysis(
            equity_curve=curve,
            positions=positions,
            price_bars=None,
            trades=[],
            symbol_groups={"000001": "银行"},
            price_field="close",
        )

        self.assertEqual(1, analysis["summary"]["periods"])
        self.assertAlmostEqual(0.01, analysis["rows"][0]["return_contribution"])
        self.assertAlmostEqual(0.01, analysis["summary"]["group_contributions"]["银行"])
        self.assertAlmostEqual(0.0, analysis["summary"]["total_residual_return"])

    def test_builds_factor_ic_analysis(self) -> None:
        factor_scores = [
            FactorScoreRecord(
                date=date(2024, 1, 2),
                symbol="000001",
                momentum=0.1,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=1.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=1.0,
                selected=True,
            ),
            FactorScoreRecord(
                date=date(2024, 1, 2),
                symbol="600519",
                momentum=0.0,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=0.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=0.0,
                selected=False,
            ),
            FactorScoreRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                momentum=0.0,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=0.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=0.0,
                selected=False,
            ),
        ]
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=10, market_value=1000, weight=0.5, cash=0, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="600519", shares=10, price=100, market_value=1000, weight=0.5, cash=0, total_equity=2000),
            PositionPoint(date=date(2024, 1, 3), symbol="000001", shares=100, price=11, market_value=1100, weight=0.52, cash=0, total_equity=2100),
            PositionPoint(date=date(2024, 1, 3), symbol="600519", shares=10, price=99, market_value=990, weight=0.47, cash=0, total_equity=2100),
        ]

        analysis = build_factor_ic_analysis(factor_scores, positions)

        self.assertTrue(analysis["rows"])
        self.assertIn("momentum", analysis["summary"])
        self.assertIn("median_ic", analysis["summary"]["momentum"])
        self.assertIn("ic_ir", analysis["summary"]["momentum"])
        self.assertIn("ic_t_stat", analysis["summary"]["momentum"])

    def test_factor_ic_summary_includes_stability_statistics(self) -> None:
        factor_scores = [
            _factor_score(date(2024, 1, 2), "000001", 1.0),
            _factor_score(date(2024, 1, 2), "600519", 0.0),
            _factor_score(date(2024, 1, 2), "000333", 0.5),
            _factor_score(date(2024, 1, 3), "000001", 1.0),
            _factor_score(date(2024, 1, 3), "600519", 0.0),
            _factor_score(date(2024, 1, 3), "000333", 0.5),
            _factor_score(date(2024, 1, 4), "000001", 1.0),
            _factor_score(date(2024, 1, 4), "600519", 0.0),
            _factor_score(date(2024, 1, 4), "000333", 0.5),
            _factor_score(date(2024, 1, 5), "000001", 0.0),
        ]
        price_bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10),
            PriceBar(date=date(2024, 1, 2), symbol="600519", close=10),
            PriceBar(date=date(2024, 1, 2), symbol="000333", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=11),
            PriceBar(date=date(2024, 1, 3), symbol="600519", close=9),
            PriceBar(date=date(2024, 1, 3), symbol="000333", close=10.5),
            PriceBar(date=date(2024, 1, 4), symbol="000001", close=10.5),
            PriceBar(date=date(2024, 1, 4), symbol="600519", close=9.5),
            PriceBar(date=date(2024, 1, 4), symbol="000333", close=10.0),
            PriceBar(date=date(2024, 1, 5), symbol="000001", close=11.0),
            PriceBar(date=date(2024, 1, 5), symbol="600519", close=9.0),
            PriceBar(date=date(2024, 1, 5), symbol="000333", close=10.2),
        ]

        analysis = build_factor_ic_analysis(
            factor_scores,
            positions=[],
            price_bars=price_bars,
            price_field="close",
        )
        summary = analysis["summary"]["total_score"]

        self.assertEqual(3, summary["periods"])
        self.assertGreater(summary["ic_std"], 0)
        self.assertNotEqual(0, summary["ic_ir"])
        self.assertNotEqual(0, summary["ic_t_stat"])
        self.assertIn("negative_ic_rate", summary)

    def test_builds_factor_group_return_analysis(self) -> None:
        factor_scores = [
            FactorScoreRecord(
                date=date(2024, 1, 2),
                symbol="000001",
                momentum=0.1,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=1.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=1.0,
                selected=True,
            ),
            FactorScoreRecord(
                date=date(2024, 1, 2),
                symbol="600519",
                momentum=0.0,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=0.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=0.0,
                selected=False,
            ),
            FactorScoreRecord(
                date=date(2024, 1, 3),
                symbol="000001",
                momentum=0.0,
                mean_reversion=0.0,
                low_volatility=0.0,
                normalized_momentum=0.0,
                normalized_mean_reversion=0.5,
                normalized_low_volatility=0.5,
                total_score=0.0,
                selected=False,
            ),
        ]
        positions = [
            PositionPoint(date=date(2024, 1, 2), symbol="000001", shares=100, price=10, market_value=1000, weight=0.5, cash=0, total_equity=2000),
            PositionPoint(date=date(2024, 1, 2), symbol="600519", shares=10, price=100, market_value=1000, weight=0.5, cash=0, total_equity=2000),
            PositionPoint(date=date(2024, 1, 3), symbol="000001", shares=100, price=11, market_value=1100, weight=0.52, cash=0, total_equity=2100),
            PositionPoint(date=date(2024, 1, 3), symbol="600519", shares=10, price=99, market_value=990, weight=0.47, cash=0, total_equity=2100),
        ]

        analysis = build_factor_group_return_analysis(factor_scores, positions, group_count=2)

        self.assertTrue(analysis["rows"])
        self.assertEqual(2, analysis["summary"]["group_count"])
        self.assertGreater(
            analysis["summary"]["momentum"]["high_minus_low"],
            0,
        )

    def test_factor_analysis_uses_full_price_bars_when_available(self) -> None:
        factor_scores = [
            _factor_score(date(2024, 1, 2), "000001", 0.1),
            _factor_score(date(2024, 1, 2), "600519", 0.0),
        ]
        price_bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=11),
            PriceBar(date=date(2024, 1, 2), symbol="600519", close=100),
            PriceBar(date=date(2024, 1, 3), symbol="600519", close=99),
        ]

        ic_analysis = build_factor_ic_analysis(
            factor_scores + [_factor_score(date(2024, 1, 3), "000001", 0.0)],
            positions=[],
            price_bars=price_bars,
            price_field="close",
        )
        group_analysis = build_factor_group_return_analysis(
            factor_scores + [_factor_score(date(2024, 1, 3), "000001", 0.0)],
            positions=[],
            price_bars=price_bars,
            price_field="close",
            group_count=2,
        )

        self.assertEqual(2, ic_analysis["rows"][0]["sample_size"])
        self.assertEqual(2, sum(row["sample_size"] for row in group_analysis["rows"] if row["factor"] == "momentum"))

    def test_builds_factor_decay_analysis(self) -> None:
        factor_scores = [
            _factor_score(date(2024, 1, 2), "000001", 1.0),
            _factor_score(date(2024, 1, 2), "600519", 0.0),
            _factor_score(date(2024, 1, 2), "000333", 0.5),
            _factor_score(date(2024, 1, 3), "000001", 0.8),
            _factor_score(date(2024, 1, 3), "600519", 0.2),
            _factor_score(date(2024, 1, 3), "000333", 0.6),
            _factor_score(date(2024, 1, 4), "000001", 0.0),
            _factor_score(date(2024, 1, 4), "600519", 1.0),
            _factor_score(date(2024, 1, 4), "000333", 0.4),
        ]

        analysis = build_factor_decay_analysis(factor_scores)
        summary = analysis["summary"]["total_score"]

        self.assertEqual(8, len(analysis["rows"]))
        self.assertEqual(2, summary["periods"])
        self.assertIn("average_rank_correlation", summary)
        self.assertIn("average_selected_retention_rate", summary)
        self.assertIn("average_selected_turnover_rate", summary)
        self.assertGreaterEqual(summary["average_selected_retention_rate"], 0.0)

    def test_builds_factor_correlation_analysis(self) -> None:
        factor_scores = [
            _factor_score_with_components(date(2024, 1, 2), "000001", 1.0, 0.1, 0.9),
            _factor_score_with_components(date(2024, 1, 2), "600519", 0.5, 0.5, 0.5),
            _factor_score_with_components(date(2024, 1, 2), "000333", 0.0, 0.9, 0.1),
            _factor_score_with_components(date(2024, 1, 3), "000001", 0.9, 0.2, 0.8),
            _factor_score_with_components(date(2024, 1, 3), "600519", 0.4, 0.6, 0.4),
            _factor_score_with_components(date(2024, 1, 3), "000333", 0.1, 0.8, 0.2),
        ]

        analysis = build_factor_correlation_analysis(factor_scores)
        summary = analysis["summary"]

        self.assertEqual(32, len(analysis["rows"]))
        self.assertEqual(4, summary["factor_count"])
        self.assertIn("momentum__mean_reversion", summary)
        self.assertLess(summary["momentum__mean_reversion"]["average_correlation"], 0)
        self.assertIn("strongest_pair", summary)
        self.assertIn("strongest_rank_pair", summary)

    def test_builds_batch_stability_analysis(self) -> None:
        rows = [
            {"run_id": "run_001", "annualized_return": 0.2, "total_return": 0.1, "sharpe": 1.0, "max_drawdown": -0.1, "total_cost": 10.0, "gate_status": "pass", "param_top_n": 2, "param_rebalance_every_n_days": 5},
            {"run_id": "run_002", "annualized_return": 0.3, "total_return": 0.2, "sharpe": 1.2, "max_drawdown": -0.2, "total_cost": 20.0, "gate_status": "pass", "param_top_n": 3, "param_rebalance_every_n_days": 5},
            {"run_id": "run_003", "annualized_return": 0.4, "total_return": 0.3, "sharpe": 1.4, "max_drawdown": -0.2, "total_cost": 20.0, "gate_status": "fail", "failed_gate_categories": "risk;factor", "failed_gate_names": "Max drawdown;Factor correlation", "param_top_n": 4, "param_rebalance_every_n_days": 10},
        ]

        analysis = build_batch_stability_analysis(rows, rank_by="annualized_return")

        self.assertEqual("run_003", analysis["summary"]["best_run_id"])
        self.assertEqual("run_003", analysis["summary"]["best_composite_run_id"])
        self.assertIn("composite_score", analysis["rows"][0])
        self.assertEqual(1, analysis["summary"]["robust_region_run_count"])
        self.assertEqual(
            {
                "param_rebalance_every_n_days": {"min": 5.0, "max": 5.0, "values": [5.0]},
                "param_top_n": {"min": 3.0, "max": 3.0, "values": [3.0]},
            },
            analysis["summary"]["robust_region_parameter_ranges"],
        )
        self.assertEqual(2, analysis["summary"]["gate_passing_run_count"])
        self.assertEqual(1, analysis["summary"]["gate_failing_run_count"])
        self.assertEqual({"factor": 1, "risk": 1}, analysis["summary"]["failed_gate_category_counts"])
        self.assertEqual({"Factor correlation": 1, "Max drawdown": 1}, analysis["summary"]["failed_gate_name_counts"])
        sensitivity = analysis["summary"]["parameter_sensitivity"]
        self.assertEqual("4", sensitivity["param_top_n"]["best_value_by_metric"])
        self.assertEqual("10", sensitivity["param_rebalance_every_n_days"]["best_value_by_metric"])
        self.assertEqual("param_top_n", analysis["summary"]["strongest_parameter"])
        self.assertEqual("4", analysis["summary"]["best_parameter_values"]["param_top_n"])
        self.assertEqual(
            "highest_average_composite_score",
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["reason"],
        )
        self.assertTrue(
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["is_also_best_by_metric"],
        )
        self.assertEqual(
            "4",
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["best_value_by_metric"],
        )
        self.assertEqual(
            1,
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["run_count"],
        )
        self.assertIn("param_top_n_value_average_annualized_return", analysis["rows"][0])
        self.assertEqual(1, analysis["rows"][0]["param_top_n_value_run_count"])
        self.assertEqual(1.0, analysis["rows"][0]["param_rebalance_every_n_days_value_gate_passing_rate"])
        self.assertTrue(analysis["summary"]["recommended_actions"])
        self.assertIn("Factor gates fail often", " ".join(analysis["summary"]["recommended_actions"]))
        robust_rows = [row for row in analysis["rows"] if row["is_robust_region"]]
        self.assertEqual(["run_002"], [row["run_id"] for row in robust_rows])

    def test_batch_stability_flags_metric_and_composite_recommendation_divergence(self) -> None:
        rows = [
            {
                "run_id": "run_001",
                "annualized_return": 0.4,
                "total_return": 0.4,
                "sharpe": 0.0,
                "max_drawdown": -1.0,
                "total_cost": 0.0,
                "gate_status": "pass",
                "param_top_n": 2,
            },
            {
                "run_id": "run_002",
                "annualized_return": 0.2,
                "total_return": 0.2,
                "sharpe": 2.0,
                "max_drawdown": -0.01,
                "total_cost": 0.0,
                "gate_status": "pass",
                "param_top_n": 3,
            },
        ]

        analysis = build_batch_stability_analysis(rows, rank_by="annualized_return")

        self.assertEqual("2", analysis["summary"]["parameter_sensitivity"]["param_top_n"]["best_value_by_metric"])
        self.assertEqual("3", analysis["summary"]["best_parameter_values"]["param_top_n"])
        self.assertFalse(
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["is_also_best_by_metric"],
        )
        self.assertEqual(
            "2",
            analysis["summary"]["parameter_recommendation_rationale"]["param_top_n"]["best_value_by_metric"],
        )


def _metrics(
    *,
    total_return: float = 0.1,
    max_drawdown: float = -0.05,
    sharpe: float = 1.0,
) -> BacktestMetrics:
    return BacktestMetrics(
        total_return=total_return,
        annualized_return=total_return,
        max_drawdown=max_drawdown,
        volatility=0.1,
        downside_volatility=0.05,
        sharpe=sharpe,
        sortino=1.0,
        calmar=1.0,
        win_rate=0.6,
        average_turnover=0.2,
        total_cost=10.0,
        periods=20,
    )


def _factor_score(score_date: date, symbol: str, momentum: float) -> FactorScoreRecord:
    return FactorScoreRecord(
        date=score_date,
        symbol=symbol,
        momentum=momentum,
        mean_reversion=0.0,
        low_volatility=0.0,
        normalized_momentum=momentum,
        normalized_mean_reversion=0.5,
        normalized_low_volatility=0.5,
        total_score=momentum,
        selected=False,
    )


def _factor_score_with_components(
    score_date: date,
    symbol: str,
    momentum: float,
    mean_reversion: float,
    low_volatility: float,
) -> FactorScoreRecord:
    total_score = (momentum + mean_reversion + low_volatility) / 3
    return FactorScoreRecord(
        date=score_date,
        symbol=symbol,
        momentum=momentum,
        mean_reversion=mean_reversion,
        low_volatility=low_volatility,
        normalized_momentum=momentum,
        normalized_mean_reversion=mean_reversion,
        normalized_low_volatility=low_volatility,
        total_score=total_score,
        selected=total_score > 0.5,
    )


if __name__ == "__main__":
    unittest.main()
