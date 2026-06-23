import unittest
from datetime import date
from typing import Tuple, Dict

from python_quant.config import BacktestConfig
from python_quant.models import PriceBar, FactorScoreRecord
from python_quant.strategy_api import AbstractStrategy, StrategyContext
from python_quant.backtest import run_backtest

class MockCustomStrategy(AbstractStrategy):
    def execute(
        self,
        context: StrategyContext,
    ) -> Tuple[Dict[str, float], Dict[str, FactorScoreRecord]]:
        # A simple strategy that always assigns 100% weight to the first available symbol
        weights = {}
        records = {}
        
        # Collect available symbols
        available = []
        for symbol, history in context.aligned_history.items():
            bar = history[context.index]
            if bar.tradable and bar.can_buy:
                available.append(symbol)
                
        if available:
            chosen = available[0]
            weights[chosen] = 1.0
            records[chosen] = FactorScoreRecord(
                date=context.current_date,
                symbol=chosen,
                total_score=1.0,
                selected=True,
                raw_scores={"custom": 1.0},
                normalized_scores={"custom": 1.0}
            )
            
        return weights, records

class TestCustomStrategy(unittest.TestCase):
    def test_run_backtest_with_custom_strategy(self):
        bars = [
            PriceBar(date(2024, 1, 1), "000001", close=10.0, open=10.0, vwap=10.0, tradable=True, can_buy=True, can_sell=True, volume=1000),
            PriceBar(date(2024, 1, 2), "000001", close=11.0, open=11.0, vwap=11.0, tradable=True, can_buy=True, can_sell=True, volume=1000),
            PriceBar(date(2024, 1, 3), "000001", close=12.0, open=12.0, vwap=12.0, tradable=True, can_buy=True, can_sell=True, volume=1000),
        ]
        config = BacktestConfig(initial_cash=10000.0, lot_size=1)
        strategy = MockCustomStrategy()
        
        result = run_backtest(bars, config=config, strategy=strategy)
        
        self.assertGreater(len(result.equity_curve), 0)
        # Verify that it bought 000001
        has_000001 = False
        for point in result.positions:
            if point.symbol == "000001" and point.shares > 0:
                has_000001 = True
                break
        self.assertTrue(has_000001)

if __name__ == '__main__':
    unittest.main()
