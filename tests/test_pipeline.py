import unittest
from datetime import date

from python_quant.config import BacktestConfig
from python_quant.models import PriceBar

try:
    from python_quant.pipeline import FactorPipeline, pd_momentum, HAS_PANDAS
except ImportError:
    HAS_PANDAS = False


class TestPipeline(unittest.TestCase):
    @unittest.skipUnless(HAS_PANDAS, "Pandas not installed")
    def test_pipeline_momentum(self):
        config = BacktestConfig(lookback_momentum=1)
        pipeline = FactorPipeline(config)
        pipeline.add_factor(pd_momentum, "momentum", 1.0)
        
        bars = [
            PriceBar(date=date(2024, 1, 1), symbol="A", close=10.0),
            PriceBar(date=date(2024, 1, 2), symbol="A", close=11.0), # 10%
            PriceBar(date=date(2024, 1, 1), symbol="B", close=20.0),
            PriceBar(date=date(2024, 1, 2), symbol="B", close=21.0), # 5%
        ]
        
        scores = pipeline.run(bars)
        
        self.assertIn(date(2024, 1, 2), scores)
        self.assertIn("A", scores[date(2024, 1, 2)])
        self.assertIn("B", scores[date(2024, 1, 2)])
        
        # A should have higher momentum than B
        self.assertGreater(scores[date(2024, 1, 2)]["A"], scores[date(2024, 1, 2)]["B"])

if __name__ == '__main__':
    unittest.main()
