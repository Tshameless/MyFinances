from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from python_quant.models import RebalanceRecord, TradeRecord
from python_quant.reporting_csv import save_turnover_analysis_files
from python_quant.turnover_analysis import build_turnover_analysis


class TurnoverAnalysisTests(unittest.TestCase):
    def test_builds_rebalance_and_holding_period_analysis(self) -> None:
        rebalances = [
            _rebalance(date(2024, 1, 2), ("000001", "600519")),
            _rebalance(date(2024, 1, 5), ("000001", "300750")),
        ]
        trades = [
            _trade(date(2024, 1, 2), "000001", "BUY", 100, 10.0),
            _trade(date(2024, 1, 2), "600519", "BUY", 100, 100.0),
            _trade(date(2024, 1, 5), "600519", "SELL", 100, 99.0),
            _trade(date(2024, 1, 5), "300750", "BUY", 100, 50.0),
        ]

        analysis = build_turnover_analysis(rebalances, trades)

        self.assertEqual(2, analysis["summary"]["rebalance_count"])
        self.assertEqual(3, analysis["summary"]["entry_count"])
        self.assertEqual(1, analysis["summary"]["exit_count"])
        self.assertEqual(1, analysis["summary"]["realized_holding_count"])
        self.assertEqual(3.0, analysis["summary"]["average_realized_holding_days"])
        self.assertEqual(2, analysis["summary"]["open_position_count"])
        rows = analysis["rebalance_rows"]
        self.assertEqual("300750", rows[1]["entry_symbols"])
        self.assertEqual("600519", rows[1]["exit_symbols"])

    def test_saves_turnover_analysis_files(self) -> None:
        analysis = build_turnover_analysis(
            [_rebalance(date(2024, 1, 2), ("000001",))],
            [_trade(date(2024, 1, 2), "000001", "BUY", 100, 10.0)],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = save_turnover_analysis_files(analysis, Path(temp_dir))

            self.assertTrue(paths["turnover_analysis_csv"].exists())
            self.assertTrue(paths["holding_periods_csv"].exists())
            self.assertTrue(paths["turnover_analysis_json"].exists())


def _rebalance(rebalance_date: date, holdings: tuple[str, ...]) -> RebalanceRecord:
    return RebalanceRecord(
        date=rebalance_date,
        holdings=holdings,
        buy_turnover=0.1,
        sell_turnover=0.2,
        turnover=0.3,
        cost=1.0,
    )


def _trade(
    trade_date: date,
    symbol: str,
    side: str,
    shares: int,
    price: float,
) -> TradeRecord:
    gross_value = shares * price
    return TradeRecord(
        date=trade_date,
        symbol=symbol,
        side=side,
        shares=shares,
        price=price,
        gross_value=gross_value,
        commission=0.0,
        slippage=0.0,
        transfer_fee=0.0,
        stamp_duty=0.0,
        total_cost=0.0,
        cash_change=-gross_value if side == "BUY" else gross_value,
        reason="rebalance_entry" if side == "BUY" else "rebalance_exit",
    )


if __name__ == "__main__":
    unittest.main()
