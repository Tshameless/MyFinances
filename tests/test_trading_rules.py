from __future__ import annotations

import unittest
from datetime import date

from python_quant.config import BacktestConfig
from python_quant.models import PriceBar
from python_quant.trading_rules import apply_inferred_limit_flags, resolve_limit_rate


class TradingRulesTests(unittest.TestCase):
    def test_infers_limit_up_and_down_flags(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10.0),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=11.0),
            PriceBar(date=date(2024, 1, 4), symbol="000001", close=9.9),
        ]
        config = BacktestConfig(
            infer_limit_flags=True,
            limit_up_down_rate=0.10,
            price_field="close",
        )

        adjusted = apply_inferred_limit_flags(bars, config)

        self.assertFalse(adjusted[1].can_buy)
        self.assertTrue(adjusted[1].is_limit_up)
        self.assertTrue(adjusted[1].can_sell)
        self.assertTrue(adjusted[2].can_buy)
        self.assertFalse(adjusted[2].can_sell)
        self.assertTrue(adjusted[2].is_limit_down)

    def test_infers_limit_flags_from_execution_price_field(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10.0, open=10.0),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=10.2, open=11.0),
            PriceBar(date=date(2024, 1, 4), symbol="000001", close=10.0, open=9.18),
        ]
        config = BacktestConfig(
            infer_limit_flags=True,
            price_field="close",
            execution_price_field="open",
            limit_up_down_rate=0.10,
        )

        adjusted = apply_inferred_limit_flags(bars, config)

        self.assertFalse(adjusted[1].can_buy)
        self.assertTrue(adjusted[1].is_limit_up)
        self.assertTrue(adjusted[1].can_sell)
        self.assertTrue(adjusted[2].can_buy)
        self.assertFalse(adjusted[2].can_sell)
        self.assertTrue(adjusted[2].is_limit_down)

    def test_keeps_existing_false_flags(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10.0, can_buy=False),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=10.1),
        ]

        adjusted = apply_inferred_limit_flags(
            bars,
            BacktestConfig(infer_limit_flags=True, price_field="close"),
        )

        self.assertFalse(adjusted[0].can_buy)
        self.assertTrue(adjusted[1].can_buy)

    def test_uses_st_limit_rate_for_limit_flag_inference(self) -> None:
        bars = [
            PriceBar(date=date(2024, 1, 2), symbol="000001", close=10.0, is_st=True),
            PriceBar(date=date(2024, 1, 3), symbol="000001", close=10.5, is_st=True),
        ]
        config = BacktestConfig(
            infer_limit_flags=True,
            st_limit_up_down_rate=0.05,
            price_field="close",
        )

        adjusted = apply_inferred_limit_flags(bars, config)

        self.assertFalse(adjusted[1].can_buy)

    def test_uses_explicit_limit_rate_before_symbol_inference(self) -> None:
        bar = PriceBar(
            date=date(2024, 1, 2),
            symbol="688001",
            close=10.0,
            limit_rate=0.15,
        )
        config = BacktestConfig(
            infer_limit_rate_by_symbol=True,
            growth_limit_up_down_rate=0.20,
        )

        self.assertEqual(0.15, resolve_limit_rate(bar, config))

    def test_infers_board_specific_limit_rate_by_symbol(self) -> None:
        config = BacktestConfig(infer_limit_rate_by_symbol=True)

        self.assertEqual(
            config.growth_limit_up_down_rate,
            resolve_limit_rate(PriceBar(date=date(2024, 1, 2), symbol="300001", close=10), config),
        )
        self.assertEqual(
            config.growth_limit_up_down_rate,
            resolve_limit_rate(PriceBar(date=date(2024, 1, 2), symbol="688001", close=10), config),
        )
        self.assertEqual(
            config.bse_limit_up_down_rate,
            resolve_limit_rate(PriceBar(date=date(2024, 1, 2), symbol="830001", close=10), config),
        )


if __name__ == "__main__":
    unittest.main()
