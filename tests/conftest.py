"""Shared test fixtures and utilities for the MyFinances test suite.

Consolidates repeated PriceBar / BacktestConfig construction patterns
across the 12 test files into reusable helpers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from python_quant.config import BacktestConfig
from python_quant.models import (
    FactorScoreRecord,
    PriceBar,
)


# ---------------------------------------------------------------------------
# PriceBar builders
# ---------------------------------------------------------------------------

def make_bar(
    symbol: str = "000001",
    bar_date: date | None = None,
    close: float = 10.0,
    *,
    adjusted_close: float | None = None,
    open_price: float | None = None,
    vwap: float | None = None,
    volume: float | None = None,
    tradable: bool = True,
    can_buy: bool = True,
    can_sell: bool = True,
    is_suspended: bool = False,
    is_limit_up: bool = False,
    is_limit_down: bool = False,
    is_st: bool = False,
    limit_rate: float | None = None,
) -> PriceBar:
    """Convenient PriceBar factory with sensible defaults."""
    return PriceBar(
        date=bar_date or date(2024, 1, 2),
        symbol=symbol,
        close=close,
        adjusted_close=adjusted_close if adjusted_close is not None else close,
        open=open_price,
        vwap=vwap,
        volume=volume,
        tradable=tradable,
        can_buy=can_buy,
        can_sell=can_sell,
        is_suspended=is_suspended,
        is_limit_up=is_limit_up,
        is_limit_down=is_limit_down,
        is_st=is_st,
        limit_rate=limit_rate,
    )


def make_bar_series(
    symbol: str = "000001",
    start_date: date | None = None,
    prices: list[float] | None = None,
    count: int = 30,
    base_price: float = 10.0,
    **kwargs: Any,
) -> list[PriceBar]:
    """Generate a series of PriceBars with sequential dates.

    If ``prices`` is provided, one bar per price entry.
    Otherwise, ``count`` bars at ``base_price``.
    """
    start = start_date or date(2024, 1, 2)
    if prices is None:
        prices = [base_price] * count
    return [
        make_bar(
            symbol=symbol,
            bar_date=start + timedelta(days=i),
            close=p,
            **kwargs,
        )
        for i, p in enumerate(prices)
    ]


# ---------------------------------------------------------------------------
# FactorScoreRecord builder
# ---------------------------------------------------------------------------

def make_factor_record(
    symbol: str = "000001",
    record_date: date | None = None,
    total_score: float = 0.5,
    selected: bool = False,
    raw_scores: dict[str, float] | None = None,
    normalized_scores: dict[str, float] | None = None,
) -> FactorScoreRecord:
    """Convenient FactorScoreRecord factory."""
    return FactorScoreRecord(
        date=record_date or date(2024, 1, 2),
        symbol=symbol,
        total_score=total_score,
        selected=selected,
        raw_scores=raw_scores or {"momentum": total_score},
        normalized_scores=normalized_scores or {"momentum": total_score},
    )


# ---------------------------------------------------------------------------
# BacktestConfig builder
# ---------------------------------------------------------------------------

def make_config(**overrides: Any) -> BacktestConfig:
    """Create a BacktestConfig with optional overrides.

    Useful for tests that only need to change a few parameters.
    """
    defaults: dict[str, Any] = {
        "initial_cash": 1_000_000.0,
        "top_n": 3,
        "rebalance_every_n_days": 5,
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)
