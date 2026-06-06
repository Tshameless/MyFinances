from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt

from .config import BacktestConfig
from .models import PriceBar


def group_prices_by_symbol(bars: list[PriceBar]) -> dict[str, list[PriceBar]]:
    grouped: dict[str, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.symbol].append(bar)
    for items in grouped.values():
        items.sort(key=lambda item: item.date)
    return dict(grouped)


def build_intersection_calendar(history_by_symbol: dict[str, list[PriceBar]]) -> list[date]:
    if not history_by_symbol:
        return []

    date_sets = [
        {bar.date for bar in symbol_bars if bar.tradable}
        for symbol_bars in history_by_symbol.values()
    ]
    common_dates = set.intersection(*date_sets) if date_sets else set()
    return sorted(common_dates)


def align_history_to_calendar(
    history_by_symbol: dict[str, list[PriceBar]],
    calendar: list[date],
) -> dict[str, list[PriceBar]]:
    aligned: dict[str, list[PriceBar]] = {}
    for symbol, bars in history_by_symbol.items():
        bar_by_date = {bar.date: bar for bar in bars}
        aligned_bars = [
            bar_by_date[trading_date]
            for trading_date in calendar
            if trading_date in bar_by_date
        ]
        if len(aligned_bars) == len(calendar):
            aligned[symbol] = aligned_bars
    return aligned


def compute_daily_returns(closes: list[float]) -> list[float]:
    returns: list[float] = []
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        current = closes[index]
        if previous == 0:
            returns.append(0.0)
        else:
            returns.append(current / previous - 1.0)
    return returns


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return sqrt(max(variance, 0.0))


def calculate_factor_scores(
    history_by_symbol: dict[str, list[PriceBar]],
    up_to_index: int,
    config: BacktestConfig,
) -> dict[str, float]:
    raw_scores: dict[str, dict[str, float]] = {}

    for symbol, bars in history_by_symbol.items():
        if up_to_index >= len(bars):
            continue

        closes = [bar.close for bar in bars[: up_to_index + 1]]
        if len(closes) <= config.max_lookback:
            continue

        current_close = closes[-1]
        momentum_close = closes[-1 - config.lookback_momentum]
        mean_reversion_close = closes[-1 - config.lookback_mean_reversion]
        trailing_returns = compute_daily_returns(closes[-1 - config.lookback_volatility :])

        momentum = current_close / momentum_close - 1.0
        mean_reversion = -(current_close / mean_reversion_close - 1.0)
        low_volatility = -_stddev(trailing_returns)

        raw_scores[symbol] = {
            "momentum": momentum,
            "mean_reversion": mean_reversion,
            "low_volatility": low_volatility,
        }

    normalized: dict[str, dict[str, float]] = {}
    factor_names = list(config.factor_weights.keys())
    for factor_name in factor_names:
        factor_values = [metrics[factor_name] for metrics in raw_scores.values()]
        if not factor_values:
            continue

        factor_min = min(factor_values)
        factor_max = max(factor_values)
        spread = factor_max - factor_min

        for symbol, metrics in raw_scores.items():
            normalized.setdefault(symbol, {})
            value = metrics[factor_name]
            if spread == 0:
                normalized[symbol][factor_name] = 0.5
            else:
                normalized[symbol][factor_name] = (value - factor_min) / spread

    total_scores: dict[str, float] = {}
    for symbol, metrics in normalized.items():
        total_scores[symbol] = sum(
            metrics.get(factor_name, 0.0) * weight
            for factor_name, weight in config.factor_weights.items()
        )

    return total_scores
