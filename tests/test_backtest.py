from __future__ import annotations

import unittest
from datetime import date

from python_quant.backtest import (
    _can_exit_position,
    _is_in_allowed_stock_pool,
    run_backtest,
)
from python_quant.config import BacktestConfig
from python_quant.execution_model import generate_orders_from_weights
from python_quant.models import PriceBar
from python_quant.simulated_broker import SimulatedBroker


def _can_be_selected(
    symbol: str,
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    current_holdings: tuple[str, ...],
) -> bool:
    bar = aligned_history[symbol][index]
    if symbol in current_holdings:
        return bar.tradable or bar.can_buy or bar.can_sell
    from python_quant.execution_model import is_buyable
    return is_buyable(bar)

def _build_target_holdings(
    *,
    scores: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    current_holdings: tuple[str, ...],
    config: BacktestConfig,
    entry_dates: dict[str, object] | None = None,
    current_date: date | None = None,
    allowed_symbols: set[str] | None = None,
    symbol_groups: dict[str, str] | None = None,
) -> tuple[str, ...]:
    if not scores and not current_holdings:
        return ()

    locked_holdings = [
        symbol
        for symbol in current_holdings
        if not _can_exit_position(
            symbol,
            aligned_history,
            index,
            entry_dates or {},
            current_date,
        )
    ]
    target_size = max(config.top_n, len(locked_holdings))
    candidate_scores = {
        symbol: score
        for symbol, score in scores.items()
        if _is_in_allowed_stock_pool(symbol, allowed_symbols)
        and _can_be_selected(symbol, aligned_history, index, current_holdings)
    }
    ranked_symbols: list[str] = []
    if candidate_scores:
        ranked = sorted(
            candidate_scores.items(),
            key=lambda item: item[1],
            reverse=(config.selection_mode == "top"),
        )
        ranked_symbols = [symbol for symbol, _ in ranked[:target_size]]

    target_holdings: list[str] = list(locked_holdings)
    group_counts = _build_group_counts(target_holdings, symbol_groups)
    for symbol in ranked_symbols:
        if len(target_holdings) >= target_size:
            break
        if symbol in target_holdings:
            continue
        group_key = _group_key(symbol, symbol_groups)
        if (
            config.max_group_positions is not None
            and group_counts.get(group_key, 0) >= config.max_group_positions
        ):
            continue
        target_holdings.append(symbol)
        group_counts[group_key] = group_counts.get(group_key, 0) + 1

    return tuple(target_holdings)


def _build_group_counts(
    symbols: list[str],
    symbol_groups: dict[str, str] | None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for symbol in symbols:
        group_key = _group_key(symbol, symbol_groups)
        counts[group_key] = counts.get(group_key, 0) + 1
    return counts


def _group_key(symbol: str, symbol_groups: dict[str, str] | None) -> str:
    if not symbol_groups:
        return f"__symbol__:{symbol}"
    return symbol_groups.get(symbol, f"__symbol__:{symbol}")



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
        self.assertTrue(result.factor_scores)
        self.assertTrue(any(record.selected for record in result.factor_scores or []))
        self.assertAlmostEqual(
            result.equity_curve[-1].equity / 100.0 - 1.0,
            result.metrics.total_return,
            places=6,
        )

    def test_can_select_holdings_from_external_factor_scores(self) -> None:
        bars = _build_a_share_aligned_bars()
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

        result = run_backtest(
            bars,
            config,
            factor_scores_by_date={
                date(2024, 1, 4): {
                    "000001": -1.0,
                    "600519": 3.0,
                    "000002": 0.0,
                }
            },
        )

        self.assertEqual(("600519",), result.rebalance_records[0].holdings)
        selected_record = next(record for record in result.factor_scores or [] if record.selected)
        self.assertEqual("600519", selected_record.symbol)
        self.assertEqual(3.0, selected_record.total_score)

    def test_builtin_score_source_ignores_external_factor_scores(self) -> None:
        bars = _build_a_share_aligned_bars()
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
            score_source="builtin",
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(
            bars,
            config,
            factor_scores_by_date={
                date(2024, 1, 4): {
                    "000001": -1.0,
                    "600519": 3.0,
                    "000002": 0.0,
                }
            },
        )

        self.assertNotEqual(("600519",), result.rebalance_records[0].holdings)

    def test_external_score_source_requires_scores_for_rebalance_date(self) -> None:
        bars = _build_a_share_aligned_bars()
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
            score_source="external",
        )

        with self.assertRaisesRegex(ValueError, "External factor scores are required"):
            run_backtest(bars, config, factor_scores_by_date={})

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

    def test_forward_fills_missing_bars_as_suspended_and_blocks_trades(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="AAA", close=10),
            PriceBar(date=date(2024, 1, 3), symbol="AAA", close=12),
            PriceBar(date=date(2024, 1, 5), symbol="AAA", close=11),
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
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            slippage_rate=0.0,
            price_field="close",
            factor_weights={"momentum": 1.0},
            forward_fill_suspended_bars=True,
        )

        result = run_backtest(bars, config)

        filled_bar = next(
            bar
            for bar in result.price_bars or []
            if bar.symbol == "AAA" and bar.date == date(2024, 1, 4)
        )
        self.assertFalse(filled_bar.tradable)
        self.assertEqual(0.0, filled_bar.volume)
        self.assertEqual(12, filled_bar.close)
        self.assertTrue(any("AAA" in point.holdings for point in result.equity_curve))

    def test_suspended_fill_bar_blocks_sell_in_trade_engine(self) -> None:
        aligned_history = {
            "AAA": [
                PriceBar(date=date(2024, 1, 3), symbol="AAA", close=12),
                PriceBar(
                    date=date(2024, 1, 4),
                    symbol="AAA",
                    close=12,
                    volume=0,
                    tradable=False,
                    can_buy=False,
                    can_sell=False,
                    is_suspended=True,
                ),
            ],
            "BBB": [
                PriceBar(date=date(2024, 1, 3), symbol="BBB", close=10),
                PriceBar(date=date(2024, 1, 4), symbol="BBB", close=10),
            ],
        }
        config = BacktestConfig(
            initial_cash=100.0,
            top_n=1,
            lot_size=1,
            commission_rate=0.0,
            slippage_rate=0.0,
            price_field="close",
        )

        broker = SimulatedBroker(initial_cash=0.0, config=config)
        broker.positions = {"AAA": 10}
        broker.entry_dates = {"AAA": date(2024, 1, 3)}

        orders, _ = generate_orders_from_weights(
            cash=broker.cash,
            positions=broker.positions,
            target_weights={"BBB": 1.0},
            aligned_history=aligned_history,
            index=1,
            config=config,
        )
        broker.submit_orders(orders)
        broker.process_market_data(date(2024, 1, 4), aligned_history, 1)

        self.assertEqual({"AAA": 10}, broker.positions)
        self.assertTrue(
            any(
                attempt.symbol == "AAA" and attempt.reason == "suspended"
                for attempt in broker.trade_attempts_today
            )
        )

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

    def test_delays_trade_execution_to_next_bar(self) -> None:
        bars = _build_aligned_bars_with_open_prices()
        config = BacktestConfig(
            initial_cash=1000.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="close",
            execution_price_field="open",
            execution_delay_days=1,
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        first_trade = next(trade for trade in result.trades or [] if trade.side == "BUY")
        self.assertEqual(date(2024, 1, 5), first_trade.date)
        self.assertEqual(12.5, first_trade.price)

    def test_caps_new_position_target_weight(self) -> None:
        bars = _build_aligned_bars()
        config = BacktestConfig(
            initial_cash=1000.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
            max_position_weight=0.2,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        first_buy = next(trade for trade in result.trades or [] if trade.side == "BUY")
        self.assertLessEqual(first_buy.gross_value, 200.0)

    def test_reserves_target_cash_weight_for_new_positions(self) -> None:
        bars = _build_aligned_bars()
        config = BacktestConfig(
            initial_cash=1000.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
            target_cash_weight=0.3,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        first_buy = next(trade for trade in result.trades or [] if trade.side == "BUY")
        self.assertLessEqual(first_buy.gross_value, 700.0)

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

    def test_applies_min_commission_and_transfer_fee(self) -> None:
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
            commission_rate=0.0001,
            min_commission=5.0,
            transfer_fee_rate=0.001,
            slippage_rate=0.0,
        )

        result = run_backtest(bars, config)

        buy_trade = next(trade for trade in result.trades or [] if trade.side == "BUY")
        self.assertEqual(5.0, buy_trade.commission)
        self.assertGreater(buy_trade.transfer_fee, 0.0)
        self.assertAlmostEqual(
            buy_trade.commission
            + buy_trade.slippage
            + buy_trade.transfer_fee
            + buy_trade.stamp_duty,
            buy_trade.total_cost,
        )

    def test_applies_side_specific_commission_rates(self) -> None:
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
            initial_cash=1000.0,
            top_n=1,
            lot_size=1,
            rebalance_every_n_days=1,
            price_field="close",
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
            commission_rate=0.0,
            buy_commission_rate=0.01,
            sell_commission_rate=0.02,
            slippage_rate=0.0,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        buy_trade = next(trade for trade in result.trades or [] if trade.side == "BUY")
        sell_trade = next(trade for trade in result.trades or [] if trade.side == "SELL")
        self.assertAlmostEqual(buy_trade.gross_value * 0.01, buy_trade.commission)
        self.assertAlmostEqual(sell_trade.gross_value * 0.02, sell_trade.commission)

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
        self.assertFalse(result.trades)
        self.assertFalse(result.trade_attempts)

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

    def test_target_holdings_respects_group_position_limit(self) -> None:
        bars = _build_aligned_bars()
        aligned_history = {
            "AAA": [bar for bar in bars if bar.symbol == "AAA"],
            "BBB": [bar for bar in bars if bar.symbol == "BBB"],
            "CCC": [bar for bar in bars if bar.symbol == "CCC"],
        }
        config = BacktestConfig(
            top_n=3,
            max_group_positions=1,
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
        )

        target = _build_target_holdings(
            scores={"AAA": 3.0, "BBB": 2.0, "CCC": 1.0},
            aligned_history=aligned_history,
            index=1,
            current_holdings=(),
            config=config,
            symbol_groups={"AAA": "金融", "BBB": "金融", "CCC": "消费"},
        )

        self.assertEqual(("AAA", "CCC"), target)

    def test_target_holdings_can_select_lowest_scores_for_factor_direction_checks(self) -> None:
        bars = _build_aligned_bars()
        aligned_history = {
            "AAA": [bar for bar in bars if bar.symbol == "AAA"],
            "BBB": [bar for bar in bars if bar.symbol == "BBB"],
            "CCC": [bar for bar in bars if bar.symbol == "CCC"],
        }
        config = BacktestConfig(
            top_n=2,
            selection_mode="bottom",
            lookback_momentum=1,
            lookback_mean_reversion=1,
            lookback_volatility=1,
        )

        target = _build_target_holdings(
            scores={"AAA": 3.0, "BBB": 2.0, "CCC": 1.0},
            aligned_history=aligned_history,
            index=1,
            current_holdings=(),
            config=config,
        )

        self.assertEqual(("CCC", "BBB"), target)

    def test_stock_pool_limits_new_entries(self) -> None:
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
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(
            bars,
            config,
            stock_pool_by_date={date(2024, 1, 2): {"BBB", "CCC"}},
        )

        bought_symbols = {trade.symbol for trade in result.trades or [] if trade.side == "BUY"}
        self.assertNotIn("AAA", bought_symbols)
        self.assertTrue(bought_symbols <= {"BBB", "CCC"})

    def test_stock_pool_keeps_locked_position_until_sellable(self) -> None:
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
            allowed_symbols={"BBB"},
        )

        self.assertEqual(("AAA",), target)

    def test_volume_participation_limits_buy_shares(self) -> None:
        bars = [
            PriceBar(date=bar.date, symbol=bar.symbol, close=bar.close, volume=50)
            for bar in _build_aligned_bars()
        ]
        config = BacktestConfig(
            initial_cash=100_000.0,
            top_n=1,
            lot_size=10,
            rebalance_every_n_days=2,
            price_field="close",
            lookback_momentum=2,
            lookback_mean_reversion=1,
            lookback_volatility=2,
            commission_rate=0.0,
            slippage_rate=0.0,
            max_volume_participation=0.5,
            factor_weights={"momentum": 1.0},
        )

        result = run_backtest(bars, config)

        first_buy = next(trade for trade in result.trades or [] if trade.side == "BUY")
        self.assertEqual(20, first_buy.shares)

    def test_volume_participation_allows_partial_sell(self) -> None:
        bars = _build_reversing_signal_bars()
        aligned_history = {
            "AAA": [
                PriceBar(date=bar.date, symbol=bar.symbol, close=bar.close, volume=300)
                for bar in bars
                if bar.symbol == "AAA"
            ],
            "BBB": [
                PriceBar(date=bar.date, symbol=bar.symbol, close=bar.close, volume=1000)
                for bar in bars
                if bar.symbol == "BBB"
            ],
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
            max_volume_participation=0.5,
            factor_weights={"momentum": 1.0},
        )

        broker = SimulatedBroker(initial_cash=1000.0, config=config)
        broker.positions = {"AAA": 200}
        broker.entry_dates = {"AAA": date(2024, 1, 2)}

        orders, _ = generate_orders_from_weights(
            cash=broker.cash,
            positions=broker.positions,
            target_weights={},
            aligned_history=aligned_history,
            index=1,
            config=config,
        )
        broker.submit_orders(orders)
        broker.process_market_data(date(2024, 1, 3), aligned_history, 1)

        self.assertEqual({"AAA": 50}, broker.positions)
        self.assertEqual(150, broker.trades_today[0].shares)
        self.assertEqual("rebalance_exit_partial_volume_limit", broker.trades_today[0].reason)


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


def _build_a_share_aligned_bars() -> list[PriceBar]:
    source = _build_aligned_bars()
    symbol_map = {"AAA": "000001", "BBB": "600519", "CCC": "000002"}
    return [
        PriceBar(date=bar.date, symbol=symbol_map[bar.symbol], close=bar.close)
        for bar in source
    ]


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


def _build_aligned_bars_with_open_prices() -> list[PriceBar]:
    return [
        PriceBar(date=bar.date, symbol=bar.symbol, close=bar.close, open=bar.close - 0.5)
        for bar in _build_aligned_bars()
    ]


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
