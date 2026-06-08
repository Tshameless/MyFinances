from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from python_quant.config import BacktestConfig
from python_quant.models import (
    BacktestMetrics,
    BacktestResult,
    BenchmarkPoint,
    EquityPoint,
    FactorScoreRecord,
    PriceBar,
    RebalanceRecord,
    TradeAttemptRecord,
    TradeRecord,
)
from python_quant.run_outputs import persist_run_outputs


class RunOutputsTests(unittest.TestCase):
    def test_persists_run_outputs_with_analysis_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            symbol_group_csv = output_dir / "symbol_groups.csv"
            symbol_group_csv.write_text(
                "symbol,group\n000001,银行\n600519,消费\n",
                encoding="utf-8",
            )
            config = BacktestConfig(
                output_dir=output_dir,
                price_field="close",
                factor_weights={"momentum": 1.0},
                symbol_group_csv=symbol_group_csv,
                rolling_risk_window=2,
            )
            result = BacktestResult(
                equity_curve=[
                    EquityPoint(date=date(2024, 1, 3), equity=101.0, daily_return=0.01, holdings=("000001",)),
                    EquityPoint(date=date(2024, 1, 4), equity=102.0, daily_return=0.01, holdings=("000001",)),
                ],
                benchmark_curve=[
                    BenchmarkPoint(date=date(2024, 1, 3), equity=100.5, daily_return=0.005),
                    BenchmarkPoint(date=date(2024, 1, 4), equity=101.0, daily_return=0.005),
                ],
                rebalance_records=[
                    RebalanceRecord(
                        date=date(2024, 1, 3),
                        holdings=("000001",),
                        buy_turnover=0.1,
                        sell_turnover=0.0,
                        turnover=0.1,
                        cost=0.0,
                    )
                ],
                metrics=BacktestMetrics(
                    total_return=0.02,
                    annualized_return=0.2,
                    max_drawdown=0.0,
                    volatility=0.1,
                    downside_volatility=0.0,
                    sharpe=1.0,
                    sortino=0.0,
                    calmar=0.0,
                    win_rate=1.0,
                    average_turnover=0.1,
                    total_cost=0.0,
                    periods=2,
                ),
                factor_scores=[
                    _factor_score(date(2024, 1, 3), "000001", 1.0),
                    _factor_score(date(2024, 1, 3), "600519", 0.0),
                    _factor_score(date(2024, 1, 4), "000001", 0.0),
                    _factor_score(date(2024, 1, 4), "600519", 1.0),
                ],
                price_bars=[
                    PriceBar(date=date(2024, 1, 3), symbol="000001", close=10, open=9.9, vwap=10.0),
                    PriceBar(date=date(2024, 1, 4), symbol="000001", close=11),
                    PriceBar(date=date(2024, 1, 3), symbol="600519", close=100),
                    PriceBar(
                        date=date(2024, 1, 4),
                        symbol="600519",
                        close=100,
                        volume=0,
                        tradable=False,
                        can_buy=False,
                        can_sell=False,
                        is_suspended=True,
                        is_limit_down=True,
                        is_st=True,
                        limit_rate=0.05,
                    ),
                ],
                trades=[
                    TradeRecord(
                        date=date(2024, 1, 3),
                        symbol="000001",
                        side="BUY",
                        shares=100,
                        price=10.0,
                        gross_value=1000.0,
                        commission=1.0,
                        slippage=0.0,
                        transfer_fee=0.0,
                        stamp_duty=0.0,
                        total_cost=1.0,
                        cash_change=-1001.0,
                        reason="rebalance_entry",
                    )
                ],
                trade_attempts=[
                    TradeAttemptRecord(
                        date=date(2024, 1, 3),
                        symbol="600519",
                        side="BUY",
                        target_shares=100,
                        price=100.0,
                        reason="insufficient_cash_for_lot",
                        cash=50.0,
                    )
                ],
            )

            paths = persist_run_outputs(
                output_dir=output_dir,
                result=result,
                config=config,
                inputs={"demo": True, "csv": None, "benchmark_csv": None, "stock_pool_csv": None, "symbol_group_csv": str(symbol_group_csv), "config": None, "sweep": False},
                print_console=False,
                config_sources={"field_sources": {"top_n": "default", "price_field": "cli"}},
            )

            self.assertTrue(paths["run_manifest_json"].exists())
            self.assertTrue(paths["config_effective_json"].exists())
            self.assertTrue(paths["config_sources_json"].exists())
            self.assertTrue(paths["price_data_quality_report_csv"].exists())
            self.assertTrue(paths["price_data_quality_report_json"].exists())
            self.assertTrue(paths["factor_ic_csv"].exists())
            self.assertTrue(paths["factor_group_returns_csv"].exists())
            self.assertTrue(paths["factor_decay_csv"].exists())
            self.assertTrue(paths["factor_correlation_csv"].exists())
            self.assertTrue(paths["drawdown_csv"].exists())
            self.assertTrue(paths["monthly_returns_csv"].exists())
            self.assertTrue(paths["rolling_risk_csv"].exists())
            self.assertTrue(paths["relative_performance_csv"].exists())
            self.assertTrue(paths["execution_quality_csv"].exists())
            self.assertTrue(paths["exposure_csv"].exists())
            self.assertTrue(paths["group_exposure_csv"].exists())
            self.assertTrue(paths["return_attribution_csv"].exists())
            self.assertTrue(paths["cost_attribution_csv"].exists())
            self.assertTrue(paths["pnl_ledger_csv"].exists())
            self.assertTrue(paths["suspension_analysis_csv"].exists())
            self.assertTrue(paths["suspension_daily_csv"].exists())
            self.assertTrue(paths["turnover_analysis_csv"].exists())
            self.assertTrue(paths["holding_periods_csv"].exists())
            self.assertTrue(paths["strategy_health_csv"].exists())
            self.assertTrue(paths["strategy_health_gates_csv"].exists())
            manifest = json.loads(paths["run_manifest_json"].read_text(encoding="utf-8"))
            self.assertIn("config_effective_json", manifest["artifacts"])
            self.assertIn("config_sources_json", manifest["artifacts"])
            self.assertIn("factor_group_returns_csv", manifest["artifacts"])
            self.assertIn("factor_decay_csv", manifest["artifacts"])
            self.assertIn("factor_decay_json", manifest["artifacts"])
            self.assertIn("factor_correlation_csv", manifest["artifacts"])
            self.assertIn("factor_correlation_json", manifest["artifacts"])
            self.assertIn("price_data_quality_report_csv", manifest["artifacts"])
            self.assertIn("price_data_quality_report_json", manifest["artifacts"])
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
            self.assertIn("suspension_analysis_csv", manifest["artifacts"])
            self.assertIn("suspension_daily_csv", manifest["artifacts"])
            self.assertIn("turnover_analysis_csv", manifest["artifacts"])
            self.assertIn("holding_periods_csv", manifest["artifacts"])
            self.assertIn("strategy_health_csv", manifest["artifacts"])
            self.assertIn("strategy_health_gates_csv", manifest["artifacts"])
            self.assertEqual(str(symbol_group_csv.resolve()), manifest["input_files"]["symbol_group_csv"]["path"])
            effective_config = json.loads(paths["config_effective_json"].read_text(encoding="utf-8"))
            self.assertEqual(config.top_n, effective_config["top_n"])
            self.assertEqual(config.execution_price_field_effective, effective_config["execution_price_field_effective"])
            config_sources = json.loads(paths["config_sources_json"].read_text(encoding="utf-8"))
            self.assertEqual("cli", config_sources["field_sources"]["price_field"])
            rolling_risk = json.loads(paths["rolling_risk_json"].read_text(encoding="utf-8"))
            self.assertEqual(2, rolling_risk["summary"]["window"])
            strategy_health = json.loads(paths["strategy_health_json"].read_text(encoding="utf-8"))
            self.assertIn("score", strategy_health["summary"])
            self.assertIn("gate_status", strategy_health["summary"])
            self.assertIn("daily_var", strategy_health["summary"])
            self.assertIn("daily_expected_shortfall", strategy_health["summary"])
            self.assertIn("average_entries_per_rebalance", strategy_health["summary"])
            self.assertIn("market_constraint_rate", strategy_health["summary"])
            self.assertIn("dominant_constraint_category", strategy_health["summary"])
            self.assertIn("execution_price_coverage_rate", strategy_health["summary"])
            self.assertIn("strongest_factor_correlation", strategy_health["summary"])
            self.assertIn("strongest_factor_correlation_pair", strategy_health["summary"])
            self.assertIn("max_largest_group_weight", strategy_health["summary"])
            self.assertTrue(
                any(row["category"] == "turnover" for row in strategy_health["rows"])
            )
            self.assertTrue(
                any(row["category"] == "factor" for row in strategy_health["rows"])
            )
            self.assertTrue(
                any(
                    gate["category"] == "exposure"
                    and str(gate["name"]).startswith("Maximum group weight")
                    for gate in strategy_health["gates"]
                )
            )
            self.assertTrue(
                any(
                    gate["category"] == "data"
                    and str(gate["name"]).startswith("Execution price coverage")
                    for gate in strategy_health["gates"]
                )
            )
            self.assertTrue(
                any(
                    gate["category"] == "risk"
                    and str(gate["name"]).startswith("Daily VaR")
                    for gate in strategy_health["gates"]
                )
            )
            execution_quality = json.loads(paths["execution_quality_json"].read_text(encoding="utf-8"))
            self.assertIn("constraint_category_counts", execution_quality["summary"])
            self.assertIn("cash", execution_quality["summary"]["constraint_category_counts"])
            self.assertIn("worst_constraint_date", execution_quality["summary"])
            self.assertTrue(
                any(row["category"] == "daily_constraint" for row in execution_quality["rows"])
            )
            data_quality = json.loads(paths["price_data_quality_report_json"].read_text(encoding="utf-8"))
            self.assertIn("execution_price_field", data_quality["summary"])
            self.assertIn("execution_price_coverage_rate", data_quality["summary"])
            suspension = json.loads(paths["suspension_analysis_json"].read_text(encoding="utf-8"))
            self.assertEqual(1, suspension["summary"]["suspended_bar_count"])
            self.assertEqual(1, suspension["summary"]["suspended_symbol_count"])
            turnover = json.loads(paths["turnover_analysis_json"].read_text(encoding="utf-8"))
            self.assertIn("average_entries_per_rebalance", turnover["summary"])
            factor_decay = json.loads(paths["factor_decay_json"].read_text(encoding="utf-8"))
            self.assertIn("total_score", factor_decay["summary"])
            factor_correlation = json.loads(paths["factor_correlation_json"].read_text(encoding="utf-8"))
            self.assertIn("factor_count", factor_correlation["summary"])
            data_quality = json.loads(paths["price_data_quality_report_json"].read_text(encoding="utf-8"))
            self.assertEqual(4, data_quality["summary"]["row_count"])
            self.assertEqual(3, data_quality["summary"]["missing_open_rows"])
            self.assertEqual(1, data_quality["summary"]["limit_down_days"])
            self.assertEqual(1, data_quality["summary"]["st_days"])


def _factor_score(score_date: date, symbol: str, score: float) -> FactorScoreRecord:
    return FactorScoreRecord(
        date=score_date,
        symbol=symbol,
        momentum=score,
        mean_reversion=0.0,
        low_volatility=0.0,
        normalized_momentum=score,
        normalized_mean_reversion=0.0,
        normalized_low_volatility=0.0,
        total_score=score,
        selected=score > 0,
    )


if __name__ == "__main__":
    unittest.main()
