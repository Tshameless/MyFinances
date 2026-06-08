from __future__ import annotations

from dataclasses import replace

from .config import BacktestConfig
from .market import execution_price_for_bar
from .models import PriceBar


def resolve_limit_rate(bar: PriceBar, config: BacktestConfig) -> float:
    if bar.limit_rate is not None:
        return bar.limit_rate
    if bar.is_st:
        return config.st_limit_up_down_rate
    if config.infer_limit_rate_by_symbol:
        if _is_bse_symbol(bar.symbol):
            return config.bse_limit_up_down_rate
        if _is_growth_board_symbol(bar.symbol):
            return config.growth_limit_up_down_rate
    return config.limit_up_down_rate


def apply_inferred_limit_flags(
    bars: list[PriceBar],
    config: BacktestConfig,
) -> list[PriceBar]:
    if not config.infer_limit_flags:
        return bars

    grouped: dict[str, list[PriceBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol, []).append(bar)

    adjusted: list[PriceBar] = []
    tolerance = 1e-8
    for symbol_bars in grouped.values():
        ordered = sorted(symbol_bars, key=lambda item: item.date)
        previous_close: float | None = None
        for bar in ordered:
            if previous_close is None:
                adjusted.append(bar)
                previous_close = bar.close
                continue

            execution_price = execution_price_for_bar(bar, config)
            daily_return = execution_price / previous_close - 1.0
            limit_rate = resolve_limit_rate(bar, config)
            inferred_can_buy = bar.can_buy
            inferred_can_sell = bar.can_sell
            inferred_is_limit_up = bar.is_limit_up
            inferred_is_limit_down = bar.is_limit_down
            if daily_return >= limit_rate - tolerance:
                inferred_can_buy = False
                inferred_is_limit_up = True
            if daily_return <= -limit_rate + tolerance:
                inferred_can_sell = False
                inferred_is_limit_down = True
            adjusted.append(
                replace(
                    bar,
                    can_buy=inferred_can_buy,
                    can_sell=inferred_can_sell,
                    is_limit_up=inferred_is_limit_up,
                    is_limit_down=inferred_is_limit_down,
                )
            )
            previous_close = bar.close

    return sorted(adjusted, key=lambda item: (item.date, item.symbol))


def _is_growth_board_symbol(symbol: str) -> bool:
    return symbol.startswith(("300", "301", "688", "689"))


def _is_bse_symbol(symbol: str) -> bool:
    return symbol.startswith(("43", "83", "87", "88", "92"))
