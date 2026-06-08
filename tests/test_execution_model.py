from __future__ import annotations

import unittest
from datetime import date

from python_quant.config import BacktestConfig
from python_quant.execution_model import (
    affordable_buy_shares,
    buy_rejection_reason,
    calculate_account_equity,
    calculate_commission,
    calculate_slippage,
    max_buy_shares_by_volume,
    max_sell_shares_by_volume,
    rebalance_account,
    round_down_to_lot,
    sell_rejection_reason,
)
from python_quant.models import PriceBar


class ExecutionModelTests(unittest.TestCase):
    def test_calculates_account_equity_from_cash_and_positions(self) -> None:
        aligned_history = {
            "000001": [PriceBar(date=date(2024, 1, 2), symbol="000001", close=10)],
            "600519": [PriceBar(date=date(2024, 1, 2), symbol="600519", close=100)],
        }

        equity = calculate_account_equity(
            500.0,
            {"000001": 100, "600519": 10},
            aligned_history,
            0,
            BacktestConfig(price_field="close"),
        )

        self.assertEqual(2500.0, equity)

    def test_rounds_and_limits_volume_to_lots(self) -> None:
        config = BacktestConfig(lot_size=100, max_volume_participation=0.25)
        bar = PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, volume=950)

        self.assertEqual(200, max_buy_shares_by_volume(bar, config))
        self.assertEqual(237, max_sell_shares_by_volume(bar, config))
        self.assertEqual(300, round_down_to_lot(399.9, 100))

    def test_twap_style_splits_volume_participation(self) -> None:
        config = BacktestConfig(
            lot_size=100,
            max_volume_participation=0.40,
            execution_style="twap",
            twap_slices=4,
        )
        bar = PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, volume=1000)

        self.assertEqual(100, max_buy_shares_by_volume(bar, config))
        self.assertEqual(100, max_sell_shares_by_volume(bar, config))

    def test_commission_uses_side_specific_rate_and_minimum(self) -> None:
        config = BacktestConfig(
            commission_rate=0.0,
            buy_commission_rate=0.001,
            sell_commission_rate=0.002,
            min_commission=5.0,
        )

        self.assertEqual(5.0, calculate_commission(1000.0, config, side="BUY"))
        self.assertEqual(20.0, calculate_commission(10_000.0, config, side="SELL"))

    def test_affordable_buy_shares_includes_full_buy_costs(self) -> None:
        config = BacktestConfig(
            lot_size=100,
            commission_rate=0.0,
            min_commission=5.0,
            transfer_fee_rate=0.001,
            slippage_rate=0.0,
        )
        bar = PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, volume=1000)

        self.assertEqual(0, affordable_buy_shares(100, 10.0, 1000.0, bar, config))
        self.assertEqual(100, affordable_buy_shares(200, 10.0, 1500.0, bar, config))

    def test_slippage_includes_participation_impact(self) -> None:
        config = BacktestConfig(
            slippage_rate=0.001,
            market_impact_coefficient=0.10,
            market_impact_exponent=1.0,
        )
        bar = PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, volume=1000)

        slippage = calculate_slippage(2_000.0, 200, bar, config)

        self.assertAlmostEqual(42.0, slippage.total)
        self.assertAlmostEqual(2.0, slippage.fixed)
        self.assertAlmostEqual(40.0, slippage.market_impact)

    def test_slippage_falls_back_to_fixed_rate_without_volume(self) -> None:
        config = BacktestConfig(
            slippage_rate=0.001,
            market_impact_coefficient=0.10,
            market_impact_exponent=1.0,
        )
        bar = PriceBar(date=date(2024, 1, 2), symbol="000001", close=10, volume=None)

        slippage = calculate_slippage(2_000.0, 200, bar, config)

        self.assertEqual(2.0, slippage.total)
        self.assertEqual(2.0, slippage.fixed)
        self.assertEqual(0.0, slippage.market_impact)

    def test_rebalance_records_suspended_sell_attempt(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    volume=0,
                    tradable=False,
                    can_buy=False,
                    can_sell=False,
                    is_suspended=True,
                )
            ]
        }

        result = rebalance_account(
            cash=0.0,
            positions={"000001": 100},
            entry_dates={"000001": date(2024, 1, 2)},
            target_holdings=(),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                price_field="close",
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual({"000001": 100}, result.positions)
        self.assertEqual("suspended", result.trade_attempts[0].reason)

    def test_rebalance_blocks_same_day_sell_by_t_plus_one(self) -> None:
        aligned_history = {
            "000001": [PriceBar(date=date(2024, 1, 3), symbol="000001", close=10)]
        }

        result = rebalance_account(
            cash=0.0,
            positions={"000001": 100},
            entry_dates={"000001": date(2024, 1, 3)},
            target_holdings=(),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                price_field="close",
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual({"000001": 100}, result.positions)
        self.assertEqual("t_plus_one_locked", result.trade_attempts[0].reason)

    def test_rebalance_allows_odd_lot_sell(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    volume=50,
                )
            ]
        }

        result = rebalance_account(
            cash=0.0,
            positions={"000001": 50},
            entry_dates={"000001": date(2024, 1, 2)},
            target_holdings=(),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                price_field="close",
                max_volume_participation=1.0,
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual({}, result.positions)
        self.assertEqual(50, result.trades[0].shares)
        self.assertEqual("rebalance_exit", result.trades[0].reason)

    def test_rebalance_does_not_buy_when_full_cost_exceeds_cash(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    volume=1000,
                )
            ]
        }

        result = rebalance_account(
            cash=1000.0,
            positions={},
            entry_dates={},
            target_holdings=("000001",),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                min_commission=5.0,
                transfer_fee_rate=0.001,
                slippage_rate=0.0,
                price_field="close",
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual({}, result.positions)
        self.assertEqual([], result.trades)
        self.assertEqual("insufficient_cash_for_lot", result.trade_attempts[0].reason)
        self.assertEqual(1000.0, result.cash)

    def test_rebalance_uses_execution_price_field_for_trades(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    open=9.5,
                    vwap=9.8,
                    volume=1000,
                )
            ]
        }

        result = rebalance_account(
            cash=10_000.0,
            positions={},
            entry_dates={},
            target_holdings=("000001",),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                price_field="close",
                execution_price_field="open",
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual(9.5, result.trades[0].price)

    def test_score_weighted_allocation_buys_more_high_score_symbol(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(date=date(2024, 1, 3), symbol="000001", close=10, volume=10_000)
            ],
            "600519": [
                PriceBar(date=date(2024, 1, 3), symbol="600519", close=10, volume=10_000)
            ],
        }

        result = rebalance_account(
            cash=10_000.0,
            positions={},
            entry_dates={},
            target_holdings=("000001", "600519"),
            target_scores={"000001": 3.0, "600519": 1.0},
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                allocation_model="score_weighted",
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                price_field="close",
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual(700, result.positions["000001"])
        self.assertEqual(200, result.positions["600519"])

    def test_rebalance_records_market_impact_slippage(self) -> None:
        aligned_history = {
            "000001": [
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    volume=1000,
                )
            ]
        }

        result = rebalance_account(
            cash=10_000.0,
            positions={},
            entry_dates={},
            target_holdings=("000001",),
            aligned_history=aligned_history,
            index=0,
            config=BacktestConfig(
                lot_size=100,
                commission_rate=0.0,
                slippage_rate=0.0,
                market_impact_coefficient=0.10,
                market_impact_exponent=1.0,
                price_field="close",
                max_volume_participation=0.20,
            ),
            current_date=date(2024, 1, 3),
        )

        self.assertEqual(200, result.trades[0].shares)
        self.assertEqual(40.0, result.trades[0].slippage)
        self.assertEqual(0.0, result.trades[0].fixed_slippage)
        self.assertEqual(40.0, result.trades[0].market_impact)

    def test_classifies_buy_rejection_reasons(self) -> None:
        self.assertEqual(
            "suspended",
            buy_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=False,
                    can_buy=False,
                    is_suspended=True,
                )
            ),
        )
        self.assertEqual(
            "not_tradable",
            buy_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=False,
                    can_buy=True,
                )
            ),
        )
        self.assertEqual(
            "limit_up_blocked",
            buy_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=True,
                    can_buy=False,
                    is_limit_up=True,
                )
            ),
        )
        self.assertEqual(
            "not_buyable",
            buy_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=True,
                    can_buy=False,
                    is_limit_up=False,
                )
            ),
        )

    def test_classifies_sell_rejection_reasons(self) -> None:
        self.assertEqual(
            "limit_down_blocked",
            sell_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=True,
                    can_sell=False,
                    is_limit_down=True,
                )
            ),
        )
        self.assertEqual(
            "not_sellable",
            sell_rejection_reason(
                PriceBar(
                    date=date(2024, 1, 3),
                    symbol="000001",
                    close=10,
                    tradable=True,
                    can_sell=False,
                    is_limit_down=False,
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
