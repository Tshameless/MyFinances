from __future__ import annotations

from .config import BacktestConfig
from .models import PriceBar

BENCHMARK_SYMBOL = "BENCHMARK"


def is_a_share_symbol(symbol: str) -> bool:
    return len(symbol) == 6 and symbol.isdigit()


def price_for_bar(bar: PriceBar, config: BacktestConfig) -> float:
    return _price_for_field(bar, config.price_field)


def execution_price_for_bar(bar: PriceBar, config: BacktestConfig) -> float:
    return _price_for_field(bar, config.execution_price_field_effective)


def _price_for_field(bar: PriceBar, field_name: str) -> float:
    if field_name == "close":
        return bar.close
    if field_name == "adjusted_close":
        if bar.adjusted_close is None:
            raise ValueError(
                f"Adjusted price requested but missing for {bar.symbol} on {bar.date.isoformat()}."
            )
        return bar.adjusted_close
    if field_name == "open":
        if bar.open is None:
            raise ValueError(
                f"Open price requested but missing for {bar.symbol} on {bar.date.isoformat()}."
            )
        return bar.open
    if field_name == "vwap":
        if bar.vwap is None:
            raise ValueError(
                f"VWAP price requested but missing for {bar.symbol} on {bar.date.isoformat()}."
            )
        return bar.vwap
    raise ValueError(f"Unsupported price field: {field_name}.")
