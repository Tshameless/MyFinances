from __future__ import annotations

from .config import BacktestConfig
from .models import PriceBar

BENCHMARK_SYMBOL = "BENCHMARK"


def is_a_share_symbol(symbol: str) -> bool:
    return len(symbol) == 6 and symbol.isdigit()


def price_for_bar(bar: PriceBar, config: BacktestConfig) -> float:
    if config.price_field == "close":
        return bar.close
    if bar.adjusted_close is None:
        raise ValueError(
            f"Adjusted price requested but missing for {bar.symbol} on {bar.date.isoformat()}."
        )
    return bar.adjusted_close
