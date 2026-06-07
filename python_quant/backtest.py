from __future__ import annotations

from dataclasses import dataclass, replace
from math import sqrt

from .config import BacktestConfig
from .factors import (
    align_history_to_calendar,
    build_intersection_calendar,
    calculate_factor_scores,
    group_prices_by_symbol,
)
from .market import price_for_bar
from .models import (
    BacktestMetrics,
    BacktestResult,
    BenchmarkPoint,
    EquityPoint,
    PositionPoint,
    PriceBar,
    RebalanceRecord,
    TradeRecord,
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

    cash = config.initial_cash
    positions: dict[str, int] = {}
    entry_dates: dict[str, object] = {}
    equity_curve: list[EquityPoint] = []
    position_points: list[PositionPoint] = []
    trade_records: list[TradeRecord] = []
    rebalance_records: list[RebalanceRecord] = []
    holdings: tuple[str, ...] = ()
    total_cost = 0.0
    total_turnover = 0.0
    warmup = config.max_lookback
    previous_equity = config.initial_cash

    for index in range(warmup, common_length - 1):
        current_date = calendar[index]
        next_date = calendar[index + 1]
        current_equity = _calculate_account_equity(cash, positions, aligned_history, index, config)

        should_rebalance = not holdings or (index - warmup) % config.rebalance_every_n_days == 0
        if should_rebalance:
            scores = calculate_factor_scores(aligned_history, index, config)
            selected = _build_target_holdings(
                scores=scores,
                aligned_history=aligned_history,
                index=index,
                current_holdings=holdings,
                config=config,
                entry_dates=entry_dates,
                current_date=current_date,
            )
            trade_plan = _rebalance_account(
                cash=cash,
                positions=positions,
                entry_dates=entry_dates,
                target_holdings=selected,
                aligned_history=aligned_history,
                index=index,
                config=config,
                current_date=current_date,
            )
            cash = trade_plan.cash
            positions = trade_plan.positions
            entry_dates = trade_plan.entry_dates
            holdings = trade_plan.holdings
            turnover = trade_plan.buy_turnover + trade_plan.sell_turnover
            total_cost += trade_plan.cost
            total_turnover += turnover
            trade_records.extend(trade_plan.trades)
            rebalance_records.append(
                RebalanceRecord(
                    date=current_date,
                    holdings=holdings,
                    buy_turnover=trade_plan.buy_turnover,
                    sell_turnover=trade_plan.sell_turnover,
                    turnover=turnover,
                    cost=round(trade_plan.cost, 2),
                )
            )

        next_equity = _calculate_account_equity(cash, positions, aligned_history, index + 1, config)
        daily_return = next_equity / previous_equity - 1.0

        equity_curve.append(
            EquityPoint(
                date=next_date,
                equity=round(next_equity, 2),
                daily_return=daily_return,
                holdings=holdings,
            )
        )
        position_points.extend(
            _build_position_points(
                cash=cash,
                positions=positions,
                aligned_history=aligned_history,
                index=index + 1,
                config=config,
                total_equity=next_equity,
            )
        )
        previous_equity = next_equity

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
        positions=position_points,
        trades=trade_records,
    )


@dataclass(frozen=True)
class _AccountTradeResult:
    cash: float
    positions: dict[str, int]
    entry_dates: dict[str, object]
    holdings: tuple[str, ...]
    buy_turnover: float
    sell_turnover: float
    cost: float
    trades: list[TradeRecord]


def _calculate_account_equity(
    cash: float,
    positions: dict[str, int],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
) -> float:
    market_value = sum(
        shares * price_for_bar(aligned_history[symbol][index], config)
        for symbol, shares in positions.items()
    )
    return cash + market_value


def _rebalance_account(
    *,
    cash: float,
    positions: dict[str, int],
    entry_dates: dict[str, object],
    target_holdings: tuple[str, ...],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
    current_date: object,
) -> _AccountTradeResult:
    positions = positions.copy()
    entry_dates = entry_dates.copy()
    start_equity = _calculate_account_equity(cash, positions, aligned_history, index, config)
    sold_value = 0.0
    bought_value = 0.0
    cost = 0.0
    trades: list[TradeRecord] = []

    for symbol in sorted(set(positions) - set(target_holdings)):
        bar = aligned_history[symbol][index]
        if not _is_sellable(bar) or entry_dates.get(symbol) == current_date:
            continue
        shares = positions.pop(symbol)
        price = price_for_bar(bar, config)
        gross_value = shares * price
        commission = gross_value * config.commission_rate
        slippage = gross_value * config.slippage_rate
        stamp_duty = gross_value * config.stamp_duty_rate
        trade_cost = commission + slippage + stamp_duty
        cash += gross_value - trade_cost
        sold_value += gross_value
        cost += trade_cost
        entry_dates.pop(symbol, None)
        trades.append(
            TradeRecord(
                date=bar.date,
                symbol=symbol,
                side="SELL",
                shares=shares,
                price=round(price, 4),
                gross_value=round(gross_value, 2),
                commission=round(commission, 2),
                slippage=round(slippage, 2),
                stamp_duty=round(stamp_duty, 2),
                total_cost=round(trade_cost, 2),
                cash_change=round(gross_value - trade_cost, 2),
                reason="rebalance_exit",
            )
        )

    retained_targets = tuple(symbol for symbol in target_holdings if symbol in positions)
    new_targets = tuple(symbol for symbol in target_holdings if symbol not in positions)
    target_count = len(retained_targets) + len(new_targets)
    target_value = start_equity / target_count if target_count else 0.0

    for symbol in new_targets:
        bar = aligned_history[symbol][index]
        if not _is_buyable(bar):
            continue
        price = price_for_bar(bar, config)
        max_cash_for_position = min(target_value, cash / (1.0 + config.per_side_cost_rate))
        shares = _round_down_to_lot(max_cash_for_position / price, config.lot_size)
        if shares <= 0:
            continue
        gross_value = shares * price
        commission = gross_value * config.commission_rate
        slippage = gross_value * config.slippage_rate
        stamp_duty = 0.0
        trade_cost = commission + slippage
        cash -= gross_value + trade_cost
        positions[symbol] = shares
        entry_dates[symbol] = current_date
        bought_value += gross_value
        cost += trade_cost
        trades.append(
            TradeRecord(
                date=bar.date,
                symbol=symbol,
                side="BUY",
                shares=shares,
                price=round(price, 4),
                gross_value=round(gross_value, 2),
                commission=round(commission, 2),
                slippage=round(slippage, 2),
                stamp_duty=round(stamp_duty, 2),
                total_cost=round(trade_cost, 2),
                cash_change=round(-(gross_value + trade_cost), 2),
                reason="rebalance_entry",
            )
        )

    holdings = tuple(sorted(positions))
    return _AccountTradeResult(
        cash=cash,
        positions=positions,
        entry_dates=entry_dates,
        holdings=holdings,
        buy_turnover=0.0 if start_equity == 0 else bought_value / start_equity,
        sell_turnover=0.0 if start_equity == 0 else sold_value / start_equity,
        cost=cost,
        trades=trades,
    )


def _round_down_to_lot(shares: float, lot_size: int) -> int:
    return int(shares // lot_size) * lot_size


def _build_position_points(
    *,
    cash: float,
    positions: dict[str, int],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
    total_equity: float,
) -> list[PositionPoint]:
    if not positions:
        return [
            PositionPoint(
                date=next(iter(aligned_history.values()))[index].date,
                symbol="CASH",
                shares=0,
                price=1.0,
                market_value=round(cash, 2),
                weight=1.0 if total_equity > 0 else 0.0,
                cash=round(cash, 2),
                total_equity=round(total_equity, 2),
            )
        ]

    rows = []
    for symbol in sorted(positions):
        bar = aligned_history[symbol][index]
        price = price_for_bar(bar, config)
        market_value = positions[symbol] * price
        rows.append(
            PositionPoint(
                date=bar.date,
                symbol=symbol,
                shares=positions[symbol],
                price=round(price, 4),
                market_value=round(market_value, 2),
                weight=0.0 if total_equity == 0 else market_value / total_equity,
                cash=round(cash, 2),
                total_equity=round(total_equity, 2),
            )
        )
    return rows


def _build_target_holdings(
    *,
    scores: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    current_holdings: tuple[str, ...],
    config: BacktestConfig,
    entry_dates: dict[str, object] | None = None,
    current_date: object | None = None,
) -> tuple[str, ...]:
    if not scores and not current_holdings:
        return ()

    locked_holdings = [
        symbol
        for symbol in current_holdings
        if not _can_exit_position(
            symbol,
            aligned_history,
            index,
            entry_dates or {},
            current_date,
        )
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
        current_price = price_for_bar(benchmark_by_date[current_date], config)
        next_price = price_for_bar(benchmark_by_date[next_date], config)
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


def _can_exit_position(
    symbol: str,
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    entry_dates: dict[str, object],
    current_date: object | None,
) -> bool:
    if entry_dates.get(symbol) == current_date:
        return False
    return _is_sellable(aligned_history[symbol][index])
