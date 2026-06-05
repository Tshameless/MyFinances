from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "python"

INITIAL_CASH = 1_000_000.0
TOP_N = 3
LOOKBACK_MOMENTUM = 20
LOOKBACK_MEAN_REVERSION = 5
LOOKBACK_VOLATILITY = 20
REBALANCE_EVERY_N_DAYS = 5
COMMISSION_RATE = 0.0003
SLIPPAGE_RATE = 0.0005

FACTOR_WEIGHTS = {
    "momentum": 0.5,
    "mean_reversion": 0.2,
    "low_volatility": 0.3,
}
