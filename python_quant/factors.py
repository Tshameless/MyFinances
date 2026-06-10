from __future__ import annotations

from collections import defaultdict
from datetime import date
from .config import BacktestConfig
from .compute_backend import daily_returns, minmax_normalize, sample_stddev
from .market import price_for_bar
from .models import FactorScoreRecord, PriceBar
from .factor_registry import register_factor


def group_prices_by_symbol(bars: list[PriceBar]) -> dict[str, list[PriceBar]]:
    grouped: dict[str, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.symbol].append(bar)
    return dict(grouped)


def build_intersection_calendar(history_by_symbol: dict[str, list[PriceBar]]) -> list[date]:
    if not history_by_symbol:
        return []

    date_sets = [{bar.date for bar in symbol_bars} for symbol_bars in history_by_symbol.values()]
    common_dates = set.intersection(*date_sets) if date_sets else set()
    return sorted(common_dates)


def align_history_with_suspended_fills(
    history_by_symbol: dict[str, list[PriceBar]],
) -> tuple[list[date], dict[str, list[PriceBar]]]:
    if not history_by_symbol:
        return [], {}

    first_dates = [bars[0].date for bars in history_by_symbol.values() if bars]
    if not first_dates:
        return [], {}
    start_date = max(first_dates)
    calendar = sorted(
        {
            bar.date
            for symbol_bars in history_by_symbol.values()
            for bar in symbol_bars
            if bar.date >= start_date
        }
    )

    aligned: dict[str, list[PriceBar]] = {}
    for symbol, bars in history_by_symbol.items():
        bar_by_date = {bar.date: bar for bar in bars}
        previous_bar: PriceBar | None = None
        rows: list[PriceBar] = []
        for trading_date in calendar:
            bar = bar_by_date.get(trading_date)
            if bar is not None:
                previous_bar = bar
                rows.append(bar)
                continue
            if previous_bar is None:
                break
            rows.append(_suspended_fill_bar(previous_bar, trading_date))
        if len(rows) == len(calendar):
            aligned[symbol] = rows
    return calendar, aligned


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


def _suspended_fill_bar(previous_bar: PriceBar, trading_date: date) -> PriceBar:
    return PriceBar(
        date=trading_date,
        symbol=previous_bar.symbol,
        close=previous_bar.close,
        adjusted_close=previous_bar.adjusted_close,
        open=previous_bar.open,
        vwap=previous_bar.vwap,
        volume=0.0,
        tradable=False,
        can_buy=False,
        can_sell=False,
        is_suspended=True,
        is_limit_up=False,
        is_limit_down=False,
        is_st=previous_bar.is_st,
        limit_rate=previous_bar.limit_rate,
    )


def compute_daily_returns(closes: list[float]) -> list[float]:
    return daily_returns(closes)


def _stddev(values: list[float]) -> float:
    return sample_stddev(values)


@register_factor("momentum")
def compute_momentum(closes: list[float], config: BacktestConfig) -> float:
    momentum_close = closes[-1 - config.lookback_momentum]
    return closes[-1] / momentum_close - 1.0


@register_factor("mean_reversion")
def compute_mean_reversion(closes: list[float], config: BacktestConfig) -> float:
    mean_reversion_close = closes[-1 - config.lookback_mean_reversion]
    return -(closes[-1] / mean_reversion_close - 1.0)


@register_factor("low_volatility")
def compute_low_volatility(closes: list[float], config: BacktestConfig) -> float:
    trailing_returns = compute_daily_returns(closes[-1 - config.lookback_volatility :])
    return -_stddev(trailing_returns)


def calculate_factor_scores(
    history_by_symbol: dict[str, list[PriceBar]],
    up_to_index: int,
    config: BacktestConfig,
) -> dict[str, float]:
    return {
        symbol: record.total_score
        for symbol, record in calculate_factor_score_records(
            history_by_symbol,
            up_to_index,
            config,
        ).items()
    }


def calculate_factor_score_records(
    history_by_symbol: dict[str, list[PriceBar]],
    up_to_index: int,
    config: BacktestConfig,
    *,
    selected_symbols: set[str] | None = None,
) -> dict[str, FactorScoreRecord]:
    raw_scores: dict[str, dict[str, float]] = {}
    from .factor_registry import get_registered_factors
    registered_factors = get_registered_factors()

    for symbol, bars in history_by_symbol.items():
        if up_to_index >= len(bars):
            continue

        closes = [price_for_bar(bar, config) for bar in bars[: up_to_index + 1]]
        if len(closes) <= config.max_lookback:
            continue

        symbol_raw: dict[str, float] = {}
        for factor_name in config.factor_weights.keys():
            if factor_name in registered_factors:
                calculator = registered_factors[factor_name]
                symbol_raw[factor_name] = calculator(closes, config)
        raw_scores[symbol] = symbol_raw

    normalized: dict[str, dict[str, float]] = {}
    factor_names = list(config.normalized_factor_weights.keys())
    for factor_name in factor_names:
        factor_values = {
            symbol: metrics[factor_name]
            for symbol, metrics in raw_scores.items()
            if factor_name in metrics
        }
        if not factor_values:
            continue

        normalized_values = minmax_normalize(factor_values)
        for symbol, value in normalized_values.items():
            normalized.setdefault(symbol, {})
            normalized[symbol][factor_name] = value

    total_scores: dict[str, float] = {}
    for symbol, metrics in normalized.items():
        total_scores[symbol] = sum(
            metrics.get(factor_name, 0.0) * weight
            for factor_name, weight in config.normalized_factor_weights.items()
        )

    selected_symbols = selected_symbols or set()
    records: dict[str, FactorScoreRecord] = {}
    for symbol, score in total_scores.items():
        raw = raw_scores[symbol]
        norm = normalized.get(symbol, {})
        records[symbol] = FactorScoreRecord(
            date=history_by_symbol[symbol][up_to_index].date,
            symbol=symbol,
            momentum=raw.get("momentum", 0.0),
            mean_reversion=raw.get("mean_reversion", 0.0),
            low_volatility=raw.get("low_volatility", 0.0),
            normalized_momentum=norm.get("momentum", 0.0),
            normalized_mean_reversion=norm.get("mean_reversion", 0.0),
            normalized_low_volatility=norm.get("low_volatility", 0.0),
            total_score=score,
            selected=symbol in selected_symbols,
            raw_scores=raw,
            normalized_scores=norm,
        )
    return records
