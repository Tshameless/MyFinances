from __future__ import annotations

import unittest
from datetime import date

from python_quant.backtest import run_backtest
from python_quant.config import BacktestConfig
from python_quant.models import PriceBar


class BacktestTests(unittest.TestCase):
    def test_uses_initial_cash_for_total_return(self) -> None:
        bars = _build_aligned_bars()
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            rebalance_every_n_days=2,
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
        )

        curve, rebalances, metrics = run_backtest(bars, config)

        self.assertGreater(len(curve), 0)
        self.assertGreater(len(rebalances), 0)
        self.assertAlmostEqual(curve[-1].equity / 100.0 - 1.0, metrics.total_return, places=6)

    def test_intersection_calendar_drops_missing_dates_without_misalignment(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="AAA", close=11),
            PriceBar(date=date(2024, 1, 4), symbol="AAA", close=12),
            PriceBar(date=date(2024, 1, 2), symbol="BBB", close=10),
            PriceBar(date=date(2024, 1, 4), symbol="BBB", close=11),
            PriceBar(date=date(2024, 1, 5), symbol="BBB", close=12),
        ]
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            rebalance_every_n_days=1,
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            slippage_rate=0.0,
        )

        with self.assertRaisesRegex(ValueError, "Not enough history"):
            run_backtest(bars, config)

    def test_rejects_invalid_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_n"):
            BacktestConfig(top_n=0)


def _build_aligned_bars() -> list[PriceBar]:
    closes = {
        "AAA": [10, 11, 12, 13, 14, 15],
        "BBB": [10, 10.1, 10.0, 10.2, 10.1, 10.3],
        "CCC": [10, 9.9, 9.8, 9.7, 9.6, 9.5],
    }
    dates = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
    ]
    bars: list[PriceBar] = []
    for symbol, symbol_closes in closes.items():
        for current_date, close in zip(dates, symbol_closes, strict=True):
            bars.append(PriceBar(date=current_date, symbol=symbol, close=close))
    return bars


if __name__ == "__main__":
    unittest.main()
