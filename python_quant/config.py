from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "python"

DEFAULT_FACTOR_WEIGHTS = {
    "momentum": 0.5,
    "mean_reversion": 0.2,
    "low_volatility": 0.3,
}


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    top_n: int = 3
    lookback_momentum: int = 20
    lookback_mean_reversion: int = 5
    lookback_volatility: int = 20
    rebalance_every_n_days: int = 5
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0005
    output_dir: Path = OUTPUT_DIR
    factor_weights: dict[str, float] = field(
        default_factory=lambda: DEFAULT_FACTOR_WEIGHTS.copy()
    )

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than 0.")
        if self.top_n <= 0:
            raise ValueError("top_n must be greater than 0.")
        if self.rebalance_every_n_days <= 0:
            raise ValueError("rebalance_every_n_days must be greater than 0.")
        if min(
            self.lookback_momentum,
            self.lookback_mean_reversion,
            self.lookback_volatility,
        ) <= 0:
            raise ValueError("All lookback windows must be greater than 0.")
        if min(self.commission_rate, self.slippage_rate) < 0:
            raise ValueError("Cost rates cannot be negative.")
        if not self.factor_weights:
            raise ValueError("factor_weights cannot be empty.")

    @property
    def per_side_cost_rate(self) -> float:
        return self.commission_rate + self.slippage_rate

    @property
    def max_lookback(self) -> int:
        return max(
            self.lookback_momentum,
            self.lookback_mean_reversion,
            self.lookback_volatility,
        )
