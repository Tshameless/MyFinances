from __future__ import annotations

import unittest
from datetime import date

from python_quant.backtest import _build_target_holdings, run_backtest
from python_quant.config import BacktestConfig
from python_quant.models import PriceBar


class BacktestTests(unittest.TestCase):
    def test_uses_initial_cash_for_total_return(self) -> None:
        bars = _build_aligned_bars()
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(bars, config)

        self.assertGreater(len(result.equity_curve), 0)
        self.assertGreater(len(result.rebalance_records), 0)
        self.assertTrue(result.positions)
        self.assertTrue(result.trades)
        self.assertAlmostEqual(
            result.equity_curve[-1].equity / 100.0 - 1.0,
            result.metrics.total_return,
            places=6,
        )

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
            lot_size=1,
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

    def test_uses_adjusted_prices_when_requested(self) -> None:
        bars = _build_adjusted_price_bars()
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="adjusted_close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        self.assertGreater(result.equity_curve[-1].equity, 100.0)
        self.assertGreaterEqual(result.metrics.sortino, 0.0)
        self.assertGreaterEqual(result.metrics.calmar, 0.0)

    def test_keeps_locked_position_when_sell_is_blocked(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="AAA", close=12),
            PriceBar(date=date(2024, 1, 4), symbol="AAA", close=11, can_sell=False),
            PriceBar(date=date(2024, 1, 5), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 2), symbol="BBB", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="BBB", close=10),
            PriceBar(date=date(2024, 1, 4), symbol="BBB", close=15),
            PriceBar(date=date(2024, 1, 5), symbol="BBB", close=16),
        ]
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=1,
            price_field="close",
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            slippage_rate=0.0,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        self.assertEqual(("AAA",), result.rebalance_records[-1].holdings)

    def test_attaches_benchmark_comparison(self) -> None:
        bars = _build_aligned_bars()
        benchmark_bars = [
            PriceBar(date=date(2024, 1, 2), symbol="BENCHMARK", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="BENCHMARK", close=10.1),
            PriceBar(date=date(2024, 1, 4), symbol="BENCHMARK", close=10.2),
            PriceBar(date=date(2024, 1, 5), symbol="BENCHMARK", close=10.3),
            PriceBar(date=date(2024, 1, 8), symbol="BENCHMARK", close=10.4),
            PriceBar(date=date(2024, 1, 9), symbol="BENCHMARK", close=10.5),
        ]
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(bars, config, benchmark_bars=benchmark_bars)

        self.assertIsNotNone(result.benchmark_curve)
        self.assertIsNotNone(result.metrics.benchmark_total_return)
        self.assertIsNotNone(result.metrics.tracking_error)
        self.assertIsNotNone(result.metrics.benchmark_volatility)
        self.assertAlmostEqual(
            result.metrics.total_return - result.metrics.benchmark_total_return,
            result.metrics.excess_return,
            places=6,
        )

    def test_applies_stamp_duty_to_sell_turnover(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="AAA", close=12),
            PriceBar(date=date(2024, 1, 4), symbol="AAA", close=11),
            PriceBar(date=date(2024, 1, 5), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 2), symbol="BBB", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="BBB", close=10),
            PriceBar(date=date(2024, 1, 4), symbol="BBB", close=15),
            PriceBar(date=date(2024, 1, 5), symbol="BBB", close=16),
        ]
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=1,
            price_field="close",
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            slippage_rate=0.0,
            stamp_duty_rate=0.01,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        self.assertGreater(result.rebalance_records[-1].sell_turnover, 0.9)
        self.assertLessEqual(result.rebalance_records[-1].sell_turnover, 1.0)
        self.assertGreater(result.rebalance_records[-1].cost, 0.0)
        sell_trades = [trade for trade in result.trades or [] if trade.side == "SELL"]
        self.assertTrue(sell_trades)
        self.assertGreater(sell_trades[-1].stamp_duty, 0.0)
        self.assertEqual(
            sell_trades[-1].commission + sell_trades[-1].slippage + sell_trades[-1].stamp_duty,
            sell_trades[-1].total_cost,
        )

    def test_default_lot_size_requires_buying_whole_a_share_lots(self) -> None:
        bars = _build_aligned_bars()
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
        )

        result = run_backtest(bars, config)

        self.assertEqual((), result.equity_curve[-1].holdings)
        self.assertEqual(100.0, result.equity_curve[-1].equity)
        self.assertEqual("CASH", (result.positions or [])[-1].symbol)

    def test_t_plus_one_lock_keeps_same_day_new_buy_in_target_holdings(self) -> None:
        bars = _build_reversing_signal_bars()
        aligned_history = {
            "AAA": [bar for bar in bars if bar.symbol == "AAA"],
            "BBB": [bar for bar in bars if bar.symbol == "BBB"],
        }
        config = BacktestConfig(
            initial_cash=10_000.0,
            top_n=1,
            lot_size=100,
            rebalance_every_n_days=1,
            price_field="close",
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            slippage_rate=0.0,
            factor_weights={"momentum": 1.0},
        )

        target = _build_target_holdings(
            scores={"BBB": 1.0, "AAA": 0.0},
            aligned_history=aligned_history,
            index=1,
            current_holdings=("AAA",),
            config=config,
            entry_dates={"AAA": date(2024, 1, 3)},
            current_date=date(2024, 1, 3),
        )

        self.assertEqual(("AAA",), target)


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


def _build_adjusted_price_bars() -> list[PriceBar]:
    bars = _build_aligned_bars()
    adjusted_bars: list[PriceBar] = []
    for bar in bars:
        multiplier = 2.0 if bar.symbol == "AAA" else 1.0
        adjusted_bars.append(
            PriceBar(
                date=bar.date,
                symbol=bar.symbol,
                close=bar.close,
                adjusted_close=bar.close * multiplier,
            )
        )
    return adjusted_bars


def _build_reversing_signal_bars() -> list[PriceBar]:
    closes = {
        "AAA": [10, 12, 11, 10],
        "BBB": [10, 10, 15, 16],
    }
    dates = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]
    bars: list[PriceBar] = []
    for symbol, symbol_closes in closes.items():
        for current_date, close in zip(dates, symbol_closes, strict=True):
            bars.append(PriceBar(date=current_date, symbol=symbol, close=close))
    return bars


if __name__ == "__main__":
    unittest.main()
