from __future__ import annotations

from dataclasses import replace
from math import sqrt

from .config import BacktestConfig
from .factors import (
    align_history_to_calendar,
    build_intersection_calendar,
    calculate_factor_scores,
    group_prices_by_symbol,
)
from .models import (
    BacktestMetrics,
    BacktestResult,
    BenchmarkPoint,
    EquityPoint,
    PriceBar,
    RebalanceRecord,
)
from .strategy import select_symbols


def run_backtest(
    bars: list[PriceBar],
    config: BacktestConfig | None = None,
    *,
    benchmark_bars: list[PriceBar] | None = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    history_by_symbol = group_prices_by_symbol(bars)
    if not history_by_symbol:
        raise ValueError("No price data available for backtest.")

    calendar = build_intersection_calendar(history_by_symbol)
    aligned_history = align_history_to_calendar(history_by_symbol, calendar)
    common_length = len(calendar)
    if common_length < config.max_lookback + 2:
        raise ValueError("Not enough history to run the strategy.")

    equity = config.initial_cash
    equity_curve: list[EquityPoint] = []
    rebalance_records: list[RebalanceRecord] = []
    holdings: tuple[str, ...] = ()
    weights: dict[str, float] = {}
    total_cost = 0.0
    total_turnover = 0.0
    warmup = config.max_lookback

    for index in range(warmup, common_length - 1):
        current_date = calendar[index]
        next_date = calendar[index + 1]

        should_rebalance = not holdings or (index - warmup) % config.rebalance_every_n_days == 0
        if should_rebalance:
            scores = calculate_factor_scores(aligned_history, index, config)
            selected = _build_target_holdings(
                scores=scores,
                aligned_history=aligned_history,
                index=index,
                current_holdings=holdings,
                config=config,
            )
            target_weights = _build_target_weights(selected)
            buy_turnover, sell_turnover = _calculate_turnover_sides(weights, target_weights)
            turnover = buy_turnover + sell_turnover
            turnover_cost = equity * (
                turnover * config.per_side_cost_rate
                + sell_turnover * config.stamp_duty_rate
            )
            equity -= turnover_cost
            total_cost += turnover_cost
            total_turnover += turnover
            holdings = selected
            weights = target_weights
            rebalance_records.append(
                RebalanceRecord(
                    date=current_date,
                    holdings=holdings,
                    buy_turnover=buy_turnover,
                    sell_turnover=sell_turnover,
                    turnover=turnover,
                    cost=round(turnover_cost, 2),
                )
            )

        portfolio_return = 0.0
        for symbol, weight in weights.items():
            bars_for_symbol = aligned_history[symbol]
            today_close = _price_for_bar(bars_for_symbol[index], config)
            next_close = _price_for_bar(bars_for_symbol[index + 1], config)
            symbol_return = next_close / today_close - 1.0
            portfolio_return += weight * symbol_return

        equity *= 1.0 + portfolio_return
        equity_curve.append(
            EquityPoint(
                date=next_date,
                equity=round(equity, 2),
                daily_return=portfolio_return,
                holdings=holdings,
            )
        )

    metrics = _calculate_metrics(
        equity_curve,
        initial_cash=config.initial_cash,
        total_turnover=total_turnover,
        total_cost=total_cost,
        rebalance_count=len(rebalance_records),
    )
    benchmark_curve = None
    if benchmark_bars:
        benchmark_curve = _build_benchmark_curve(
            benchmark_bars=benchmark_bars,
            calendar=calendar,
            warmup=warmup,
            initial_cash=config.initial_cash,
            config=config,
        )
        metrics = _attach_benchmark_metrics(metrics, equity_curve, benchmark_curve)
    return BacktestResult(
        equity_curve=equity_curve,
        rebalance_records=rebalance_records,
        metrics=metrics,
        benchmark_curve=benchmark_curve,
    )


def _build_target_weights(holdings: tuple[str, ...]) -> dict[str, float]:
    if not holdings:
        return {}
    weight = 1.0 / len(holdings)
    return {symbol: weight for symbol in holdings}


def _calculate_turnover(current_weights: dict[str, float], target_weights: dict[str, float]) -> float:
    buy_turnover, sell_turnover = _calculate_turnover_sides(current_weights, target_weights)
    return buy_turnover + sell_turnover


def _calculate_turnover_sides(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> tuple[float, float]:
    symbols = set(current_weights) | set(target_weights)
    buy_turnover = 0.0
    sell_turnover = 0.0
    for symbol in symbols:
        delta = target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0)
        if delta > 0:
            buy_turnover += delta
        elif delta < 0:
            sell_turnover += -delta
    return buy_turnover, sell_turnover


def _build_target_holdings(
    *,
    scores: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    current_holdings: tuple[str, ...],
    config: BacktestConfig,
) -> tuple[str, ...]:
    if not scores and not current_holdings:
        return ()

    locked_holdings = [
        symbol
        for symbol in current_holdings
        if not _is_sellable(aligned_history[symbol][index])
    ]
    target_size = max(config.top_n, len(locked_holdings))
    candidate_scores = {
        symbol: score
        for symbol, score in scores.items()
        if _can_be_selected(symbol, aligned_history, index, current_holdings)
    }
    ranked_symbols: list[str] = []
    if candidate_scores:
        ranked_symbols = select_symbols(candidate_scores, min(len(candidate_scores), target_size))

    target_holdings: list[str] = list(locked_holdings)
    for symbol in ranked_symbols:
        if len(target_holdings) >= target_size:
            break
        if symbol in target_holdings:
            continue
        target_holdings.append(symbol)

    return tuple(target_holdings)


def _calculate_metrics(
    equity_curve: list[EquityPoint],
    *,
    initial_cash: float,
    total_turnover: float,
    total_cost: float,
    rebalance_count: int,
) -> BacktestMetrics:
    if not equity_curve:
        raise ValueError("Equity curve is too short to calculate metrics.")

    daily_returns = [point.daily_return for point in equity_curve]
    peak = initial_cash
    max_drawdown = 0.0

    for point in equity_curve:
        current = point.equity
        peak = max(peak, current)
        drawdown = current / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    total_return = equity_curve[-1].equity / initial_cash - 1.0
    mean_return = sum(daily_returns) / len(daily_returns)
    variance = (
        sum((daily - mean_return) ** 2 for daily in daily_returns)
        / max(len(daily_returns) - 1, 1)
    )
    volatility = sqrt(max(variance, 0.0)) * sqrt(252)
    downside_variance = (
        sum(min(daily, 0.0) ** 2 for daily in daily_returns)
        / len(daily_returns)
    )
    downside_volatility = sqrt(max(downside_variance, 0.0)) * sqrt(252)
    annualized_return = (1.0 + total_return) ** (252 / len(daily_returns)) - 1.0
    sharpe = 0.0 if volatility == 0 else (mean_return * 252) / volatility
    sortino = 0.0 if downside_volatility == 0 else annualized_return / downside_volatility
    calmar = 0.0 if max_drawdown == 0 else annualized_return / abs(max_drawdown)
    wins = sum(1 for daily in daily_returns if daily > 0)
    average_turnover = total_turnover / rebalance_count if rebalance_count else 0.0

    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=max_drawdown,
        volatility=volatility,
        downside_volatility=downside_volatility,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        win_rate=wins / len(daily_returns),
        average_turnover=average_turnover,
        total_cost=total_cost,
        periods=len(daily_returns),
    )


def _build_benchmark_curve(
    *,
    benchmark_bars: list[PriceBar],
    calendar: list,
    warmup: int,
    initial_cash: float,
    config: BacktestConfig,
) -> list[BenchmarkPoint]:
    benchmark_by_date = {bar.date: bar for bar in benchmark_bars}
    required_dates = calendar[warmup:]
    missing_dates = [
        trading_date.isoformat()
        for trading_date in required_dates
        if trading_date not in benchmark_by_date
    ]
    if missing_dates:
        missing_preview = ", ".join(missing_dates[:5])
        raise ValueError(f"Benchmark data missing required dates: {missing_preview}")

    equity = initial_cash
    benchmark_curve: list[BenchmarkPoint] = []
    for index in range(warmup, len(calendar) - 1):
        current_date = calendar[index]
        next_date = calendar[index + 1]
        current_price = _price_for_bar(benchmark_by_date[current_date], config)
        next_price = _price_for_bar(benchmark_by_date[next_date], config)
        daily_return = next_price / current_price - 1.0
        equity *= 1.0 + daily_return
        benchmark_curve.append(
            BenchmarkPoint(
                date=next_date,
                equity=round(equity, 2),
                daily_return=daily_return,
            )
        )
    return benchmark_curve


def _attach_benchmark_metrics(
    metrics: BacktestMetrics,
    equity_curve: list[EquityPoint],
    benchmark_curve: list[BenchmarkPoint],
) -> BacktestMetrics:
    if len(equity_curve) != len(benchmark_curve):
        raise ValueError("Benchmark curve length does not match portfolio curve length.")

    initial_benchmark_equity = benchmark_curve[0].equity / (1.0 + benchmark_curve[0].daily_return)
    benchmark_total_return = benchmark_curve[-1].equity / initial_benchmark_equity - 1.0
    benchmark_annualized_return = (1.0 + benchmark_total_return) ** (
        252 / len(benchmark_curve)
    ) - 1.0
    benchmark_daily_returns = [point.daily_return for point in benchmark_curve]
    benchmark_mean_return = sum(benchmark_daily_returns) / len(benchmark_daily_returns)
    benchmark_variance = (
        sum((daily - benchmark_mean_return) ** 2 for daily in benchmark_daily_returns)
        / max(len(benchmark_daily_returns) - 1, 1)
    )
    benchmark_volatility = sqrt(max(benchmark_variance, 0.0)) * sqrt(252)
    benchmark_peak = initial_benchmark_equity
    benchmark_max_drawdown = 0.0
    for point in benchmark_curve:
        benchmark_peak = max(benchmark_peak, point.equity)
        benchmark_drawdown = point.equity / benchmark_peak - 1.0
        benchmark_max_drawdown = min(benchmark_max_drawdown, benchmark_drawdown)
    excess_return = metrics.total_return - benchmark_total_return
    daily_excess_returns = [
        point.daily_return - benchmark_point.daily_return
        for point, benchmark_point in zip(equity_curve, benchmark_curve, strict=True)
    ]
    mean_excess_return = sum(daily_excess_returns) / len(daily_excess_returns)
    excess_variance = (
        sum((daily - mean_excess_return) ** 2 for daily in daily_excess_returns)
        / max(len(daily_excess_returns) - 1, 1)
    )
    tracking_error = sqrt(max(excess_variance, 0.0)) * sqrt(252)
    information_ratio = 0.0
    if tracking_error > 0:
        information_ratio = (mean_excess_return * 252) / tracking_error

    return replace(
        metrics,
        benchmark_total_return=benchmark_total_return,
        benchmark_annualized_return=benchmark_annualized_return,
        benchmark_volatility=benchmark_volatility,
        benchmark_max_drawdown=benchmark_max_drawdown,
        excess_return=excess_return,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
    )


def _price_for_bar(bar: PriceBar, config: BacktestConfig) -> float:
    if config.price_field == "close":
        return bar.close
    if config.price_field == "adjusted_close":
        if bar.adjusted_close is None:
            raise ValueError(
                f"Adjusted price requested but missing for {bar.symbol} on {bar.date.isoformat()}."
            )
        return bar.adjusted_close
    return bar.adjusted_close if bar.adjusted_close is not None else bar.close


def _can_be_selected(
    symbol: str,
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    current_holdings: tuple[str, ...],
) -> bool:
    bar = aligned_history[symbol][index]
    if symbol in current_holdings:
        return bar.tradable or bar.can_buy or bar.can_sell
    return _is_buyable(bar)


def _is_buyable(bar: PriceBar) -> bool:
    return bar.tradable and bar.can_buy


def _is_sellable(bar: PriceBar) -> bool:
    return bar.tradable and bar.can_sell
