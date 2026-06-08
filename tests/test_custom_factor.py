from __future__ import annotations

import unittest
from datetime import date

from python_quant.backtest import run_backtest
from python_quant.config import BacktestConfig
from python_quant.factor_registry import register_factor, get_registered_factors
from python_quant.factors import calculate_factor_score_records
from python_quant.models import PriceBar, FactorScoreRecord


class CustomFactorTests(unittest.TestCase):
    def setUp(self) -> None:
        # Define and register a custom factor for testing
        @register_factor("custom_dummy")
        def compute_custom_dummy(closes: list[float], config: BacktestConfig) -> float:
            # Simple dummy: return final price divided by the first price in closes
            if not closes:
                return 0.0
            return closes[-1] / closes[0]

    def tearDown(self) -> None:
        # Deregister to avoid polluting registry in other runs, though not strictly necessary
        factors_dict = get_registered_factors()
        if "custom_dummy" in factors_dict:
            del factors_dict["custom_dummy"]

    def test_custom_factor_registration_and_scoring(self) -> None:
        # 1. Verify custom factor is registered
        registered = get_registered_factors()
        self.assertIn("custom_dummy", registered)

        # 2. Build mock price bars
        # AAA has prices that increase: 10 -> 20 -> 30 -> 40
        # BBB has prices that decrease: 40 -> 30 -> 20 -> 10
        closes = {
            "AAA": [10.0, 20.0, 30.0, 40.0],
            "BBB": [40.0, 30.0, 20.0, 10.0],
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

        # 3. Create a BacktestConfig that uses the custom factor
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
            slippage_rate=0.0,
            factor_weights={"custom_dummy": 1.0},
        )

        # 4. Group prices and align
        from python_quant.factors import group_prices_by_symbol
        history_by_symbol = group_prices_by_symbol(bars)

        # Calculate factor score records at index 3 (last index)
        # max_lookback for config is 1 (the maximum of lookbacks specified)
        # closes will have length 4, which is > max_lookback (1)
        records = calculate_factor_score_records(
            history_by_symbol,
            up_to_index=3,
            config=config,
        )

        # Verify AAA and BBB records
        self.assertIn("AAA", records)
        self.assertIn("BBB", records)

        aaa_rec: FactorScoreRecord = records["AAA"]
        bbb_rec: FactorScoreRecord = records["BBB"]

        # Raw value for AAA: 40 / 10 = 4.0
        # Raw value for BBB: 10 / 40 = 0.25
        self.assertIn("custom_dummy", aaa_rec.raw_scores)
        self.assertIn("custom_dummy", bbb_rec.raw_scores)
        self.assertAlmostEqual(aaa_rec.raw_scores["custom_dummy"], 4.0)
        self.assertAlmostEqual(bbb_rec.raw_scores["custom_dummy"], 0.25)

        # Normalized value
        # min = 0.25, max = 4.0, spread = 3.75
        # AAA normalized: (4.0 - 0.25) / 3.75 = 1.0
        # BBB normalized: (0.25 - 0.25) / 3.75 = 0.0
        self.assertIn("custom_dummy", aaa_rec.normalized_scores)
        self.assertIn("custom_dummy", bbb_rec.normalized_scores)
        self.assertAlmostEqual(aaa_rec.normalized_scores["custom_dummy"], 1.0)
        self.assertAlmostEqual(bbb_rec.normalized_scores["custom_dummy"], 0.0)

        # Total scores should match normalized score * weight (1.0)
        self.assertAlmostEqual(aaa_rec.total_score, 1.0)
        self.assertAlmostEqual(bbb_rec.total_score, 0.0)

    def test_backtest_with_custom_factor(self) -> None:
        # Run backtest with the custom factor
        closes = {
            "AAA": [10.0, 20.0, 30.0, 40.0],
            "BBB": [40.0, 30.0, 20.0, 10.0],
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
            slippage_rate=0.0,
            factor_weights={"custom_dummy": 1.0},
        )

        result = run_backtest(bars, config)
        self.assertTrue(result.equity_curve)
        self.assertTrue(result.rebalance_records)
        # Top selection should be AAA because it has a higher score
        self.assertEqual(("AAA",), result.rebalance_records[0].holdings)

    def test_custom_factor_analysis(self) -> None:
        # Build mock FactorScoreRecords over two dates
        # Date 1
        rec1_aaa = FactorScoreRecord(
            date=date(2024, 1, 2),
            symbol="AAA",
            momentum=1.0,
            mean_reversion=2.0,
            low_volatility=3.0,
            normalized_momentum=0.5,
            normalized_mean_reversion=0.5,
            normalized_low_volatility=0.5,
            total_score=0.5,
            selected=True,
            raw_scores={"custom_dummy": 10.0},
            normalized_scores={"custom_dummy": 0.8},
        )
        rec1_bbb = FactorScoreRecord(
            date=date(2024, 1, 2),
            symbol="BBB",
            momentum=2.0,
            mean_reversion=1.0,
            low_volatility=2.0,
            normalized_momentum=0.8,
            normalized_mean_reversion=0.2,
            normalized_low_volatility=0.2,
            total_score=0.4,
            selected=False,
            raw_scores={"custom_dummy": 5.0},
            normalized_scores={"custom_dummy": 0.2},
        )
        # Date 2
        rec2_aaa = FactorScoreRecord(
            date=date(2024, 1, 3),
            symbol="AAA",
            momentum=1.2,
            mean_reversion=2.1,
            low_volatility=3.1,
            normalized_momentum=0.6,
            normalized_mean_reversion=0.6,
            normalized_low_volatility=0.6,
            total_score=0.6,
            selected=True,
            raw_scores={"custom_dummy": 11.0},
            normalized_scores={"custom_dummy": 0.9},
        )
        rec2_bbb = FactorScoreRecord(
            date=date(2024, 1, 3),
            symbol="BBB",
            momentum=2.1,
            mean_reversion=1.1,
            low_volatility=2.1,
            normalized_momentum=0.9,
            normalized_mean_reversion=0.3,
            normalized_low_volatility=0.3,
            total_score=0.5,
            selected=False,
            raw_scores={"custom_dummy": 6.0},
            normalized_scores={"custom_dummy": 0.3},
        )
        
        factor_scores = [rec1_aaa, rec1_bbb, rec2_aaa, rec2_bbb]
        
        # We need mock price_bars to compute returns in IC and group return analysis
        # Return for AAA on 2024-01-02 -> 2024-01-03: (22-20)/20 = 10%
        # Return for BBB on 2024-01-02 -> 2024-01-03: (38-40)/40 = -5%
        price_bars = [
            PriceBar(date=date(2024, 1, 2), symbol="AAA", close=20.0),
            PriceBar(date=date(2024, 1, 3), symbol="AAA", close=22.0),
            PriceBar(date=date(2024, 1, 2), symbol="BBB", close=40.0),
            PriceBar(date=date(2024, 1, 3), symbol="BBB", close=38.0),
        ]
        
        from python_quant.factor_analysis import (
            build_factor_ic_analysis,
            build_factor_group_return_analysis,
            build_factor_decay_analysis,
            build_factor_correlation_analysis
        )
        
        # Run IC analysis
        ic_res = build_factor_ic_analysis(factor_scores, [], price_bars=price_bars)
        self.assertIn("custom_dummy", ic_res["summary"])
        
        # Run Group return analysis
        group_res = build_factor_group_return_analysis(factor_scores, [], group_count=2, price_bars=price_bars)
        self.assertIn("custom_dummy", group_res["summary"])
        
        # Run Decay analysis
        decay_res = build_factor_decay_analysis(factor_scores)
        self.assertIn("custom_dummy", decay_res["summary"])
        
        # Run Correlation analysis
        corr_res = build_factor_correlation_analysis(factor_scores)
        self.assertIn("momentum__custom_dummy", corr_res["summary"])

    def test_custom_factor_csv_export(self) -> None:
        import tempfile
        import csv
        from pathlib import Path
        from python_quant.reporting_csv import save_factor_scores_csv
        
        rec = FactorScoreRecord(
            date=date(2024, 1, 2),
            symbol="000001",
            momentum=1.0,
            mean_reversion=2.0,
            low_volatility=3.0,
            normalized_momentum=0.5,
            normalized_mean_reversion=0.5,
            normalized_low_volatility=0.5,
            total_score=0.5,
            selected=True,
            raw_scores={"custom_dummy": 10.0},
            normalized_scores={"custom_dummy": 0.8},
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir)
            save_factor_scores_csv(
                [rec],
                out_path,
                format_symbol=lambda x: x,
                display_label=lambda x: x,
            )
            
            csv_file = out_path / "factor_scores.csv"
            self.assertTrue(csv_file.exists())
            
            with csv_file.open("r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                self.assertGreater(len(rows), 1)
                header = rows[0]
                
                # Check for dynamic factor columns in header
                self.assertIn("custom_dummy", header)
                self.assertIn("normalized_custom_dummy", header)
                
                data_row = rows[1]
                custom_dummy_idx = header.index("custom_dummy")
                normalized_custom_dummy_idx = header.index("normalized_custom_dummy")
                
                self.assertEqual(data_row[custom_dummy_idx], "10.00000000")
                self.assertEqual(data_row[normalized_custom_dummy_idx], "0.80000000")


if __name__ == "__main__":
    unittest.main()
