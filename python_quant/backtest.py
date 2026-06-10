from __future__ import annotations

from dataclasses import replace
from datetime import date
from math import sqrt

from .config import BacktestConfig
from .exceptions import InsufficientDataError
from .execution_model import (
    calculate_account_equity,
    is_buyable,
    is_sellable,
    generate_orders_from_weights,
)
from .simulated_broker import SimulatedBroker
from .factors import (
    align_history_to_calendar,
    align_history_with_suspended_fills,
    build_intersection_calendar,
    calculate_factor_score_records,
    group_prices_by_symbol,
)
from .market import price_for_bar
from .models import (
    BacktestMetrics,
    BacktestResult,
    BenchmarkPoint,
    EquityPoint,
    FactorScoreRecord,
    PositionPoint,
    PriceBar,
    RebalanceRecord,
)
from .strategy import TopNFactorStrategy
from .portfolio_optimizer import PortfolioOptimizer


def run_backtest(
    bars: list[PriceBar],
    config: BacktestConfig | None = None,
    *,
    benchmark_bars: list[PriceBar] | None = None,
    stock_pool_by_date: dict[date, set[str]] | None = None,
    symbol_groups: dict[str, str] | None = None,
    factor_scores_by_date: dict[date, dict[str, float]] | None = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    history_by_symbol = group_prices_by_symbol(bars)
    if not history_by_symbol:
        raise InsufficientDataError("No price data available for backtest.")

    if config.forward_fill_suspended_bars:
        calendar, aligned_history = align_history_with_suspended_fills(history_by_symbol)
    else:
        calendar = build_intersection_calendar(history_by_symbol)
        aligned_history = align_history_to_calendar(history_by_symbol, calendar)
    common_length = len(calendar)
    if common_length < config.max_lookback + config.execution_delay_days + 2:
        raise InsufficientDataError("Not enough history to run the strategy.")

    cash = config.initial_cash
    positions: dict[str, int] = {}
    entry_dates: dict[str, object] = {}
    equity_curve: list[EquityPoint] = []
    position_points: list[PositionPoint] = []
    factor_score_records: list[FactorScoreRecord] = []
    rebalance_records: list[RebalanceRecord] = []
    holdings: tuple[str, ...] = ()
    total_cost = 0.0
    total_turnover = 0.0
    warmup = config.max_lookback
    previous_equity = config.initial_cash

    broker = SimulatedBroker(initial_cash=config.initial_cash, config=config)

    last_signal_index = common_length - config.execution_delay_days - 2
    for index in range(warmup, last_signal_index + 1):
        current_date = calendar[index]
        execution_index = index + config.execution_delay_days
        execution_date = calendar[execution_index]
        next_date = calendar[execution_index + 1]

        should_rebalance = not holdings or (index - warmup) % config.rebalance_every_n_days == 0
        if should_rebalance:
            factor_records = _factor_records_for_date(
                aligned_history,
                index,
                config,
                external_scores_by_date=factor_scores_by_date,
            )
            scores = {symbol: record.total_score for symbol, record in factor_records.items()}
            allowed_symbols = _resolve_stock_pool_for_date(stock_pool_by_date, current_date)
            
            available_records = {
                sym: rec for sym, rec in factor_records.items()
                if _is_in_allowed_stock_pool(sym, allowed_symbols) and _can_be_selected(sym, aligned_history, index, holdings)
            }
            
            locked_symbols = [
                symbol
                for symbol in holdings
                if not _can_exit_position(
                    symbol,
                    aligned_history,
                    index,
                    entry_dates or {},
                    current_date,
                )
            ]

            if config.allocation_model in {"max_sharpe", "min_variance"}:
                from .portfolio_optimizer import ScipyPortfolioOptimizer
                historical_returns = {}
                lookback = 60
                for sym in available_records:
                    bars = aligned_history[sym][max(0, index-lookback):index+1]
                    if len(bars) > 1:
                        rets = []
                        for i in range(1, len(bars)):
                            prev_p = price_for_bar(bars[i-1], config)
                            curr_p = price_for_bar(bars[i], config)
                            rets.append(curr_p / prev_p - 1.0 if prev_p > 0 else 0.0)
                        historical_returns[sym] = rets
                
                # We need to filter the top N before giving it to the optimizer to avoid OOM or slow solving on 5000 stocks
                strategy = TopNFactorStrategy(top_n=config.top_n, mode=config.selection_mode, allocation_model="equal")
                unconstrained = strategy.generate_target_weights(current_date, available_records)
                filtered_records = {s: available_records[s] for s in unconstrained}
                for s in locked_symbols:
                    if s in available_records:
                        filtered_records[s] = available_records[s]

                scipy_optimizer = ScipyPortfolioOptimizer(
                    objective=config.allocation_model,
                    target_cash_weight=config.target_cash_weight,
                    max_position_weight=config.max_position_weight,
                    max_group_positions=config.max_group_positions,
                    symbol_groups=symbol_groups,
                )
                target_weights = scipy_optimizer.generate_target_weights(
                    current_date=current_date,
                    signals=filtered_records,
                    historical_returns=historical_returns,
                    locked_symbols=locked_symbols
                )
            else:
                strategy = TopNFactorStrategy(
                    top_n=config.top_n,
                    mode=config.selection_mode,
                    allocation_model=config.allocation_model,
                )
                unconstrained_weights = strategy.generate_target_weights(current_date, available_records)
                legacy_optimizer = PortfolioOptimizer(
                    max_position_weight=config.max_position_weight,
                    max_group_positions=config.max_group_positions,
                    target_cash_weight=config.target_cash_weight,
                    symbol_groups=symbol_groups,
                )
                target_weights = legacy_optimizer.optimize(unconstrained_weights, locked_symbols)

            selected = tuple(target_weights.keys())
            
            factor_score_records.extend(
                _factor_records_for_date(
                    aligned_history,
                    index,
                    config,
                    external_scores_by_date=factor_scores_by_date,
                    selected_symbols=set(selected),
                ).values()
            )
            
            for oid in list(broker.active_orders.keys()):
                broker.cancel_order(oid)
                
            orders = generate_orders_from_weights(
                cash=cash,
                positions=positions,
                target_weights=target_weights,
                aligned_history=aligned_history,
                index=execution_index,
                config=config,
            )
            broker.submit_orders(orders)
            
            start_equity = calculate_account_equity(cash, positions, aligned_history, execution_index, config)
            
            broker.process_market_data(execution_date, aligned_history, execution_index)
            
            cash = broker.cash
            positions = broker.positions
            entry_dates = broker.entry_dates
            holdings = tuple(sorted(positions))
            
            buy_turnover = broker.bought_value_today / start_equity if start_equity > 0 else 0.0
            sell_turnover = broker.sold_value_today / start_equity if start_equity > 0 else 0.0
            turnover = buy_turnover + sell_turnover
            
            total_cost += broker.cost_today
            total_turnover += turnover
            
            rebalance_records.append(
                RebalanceRecord(
                    date=current_date,
                    holdings=holdings,
                    buy_turnover=buy_turnover,
                    sell_turnover=sell_turnover,
                    turnover=turnover,
                    cost=round(broker.cost_today, 2),
                )
            )

        next_equity = calculate_account_equity(
            cash,
            positions,
            aligned_history,
            execution_index + 1,
            config,
        )
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
                index=execution_index + 1,
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
        trades=broker.all_trades,
        trade_attempts=broker.all_attempts,
        factor_scores=factor_score_records,
        price_bars=[
            bar
            for symbol in sorted(aligned_history)
            for bar in aligned_history[symbol]
        ],
        orders=broker.all_orders,
    )


def _factor_records_for_date(
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
    *,
    external_scores_by_date: dict[date, dict[str, float]] | None = None,
    selected_symbols: set[str] | None = None,
) -> dict[str, FactorScoreRecord]:
    current_date = next(iter(aligned_history.values()))[index].date
    external_scores = None if external_scores_by_date is None else external_scores_by_date.get(current_date)
    if config.score_source == "builtin":
        external_scores = None
    if config.score_source == "external" and external_scores is None:
        raise InsufficientDataError(
            f"External factor scores are required for {current_date.isoformat()} "
            "when score_source is 'external'."
        )
    if external_scores is None:
        return calculate_factor_score_records(
            aligned_history,
            index,
            config,
            selected_symbols=selected_symbols,
        )

    selected_symbols = selected_symbols or set()
    return {
        symbol: FactorScoreRecord(
            date=current_date,
            symbol=symbol,
            momentum=score,
            mean_reversion=0.0,
            low_volatility=0.0,
            normalized_momentum=score,
            normalized_mean_reversion=0.0,
            normalized_low_volatility=0.0,
            total_score=score,
            selected=symbol in selected_symbols,
        )
        for symbol, score in external_scores.items()
        if symbol in aligned_history and index < len(aligned_history[symbol])
    }


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


def _resolve_stock_pool_for_date(
    stock_pool_by_date: dict[date, set[str]] | None,
    current_date: date,
) -> set[str] | None:
    if stock_pool_by_date is None:
        return None
    effective_dates = [
        pool_date
        for pool_date in stock_pool_by_date
        if pool_date <= current_date
    ]
    if not effective_dates:
        return set()
    return stock_pool_by_date[max(effective_dates)]


def _is_in_allowed_stock_pool(symbol: str, allowed_symbols: set[str] | None) -> bool:
    return allowed_symbols is None or symbol in allowed_symbols


def _calculate_metrics(
    equity_curve: list[EquityPoint],
    *,
    initial_cash: float,
    total_turnover: float,
    total_cost: float,
    rebalance_count: int,
) -> BacktestMetrics:
    if not equity_curve:
        raise InsufficientDataError("Equity curve is too short to calculate metrics.")

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
        raise InsufficientDataError(f"Benchmark data missing required dates: {missing_preview}")

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
        raise InsufficientDataError("Benchmark curve length does not match portfolio curve length.")

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
    return is_buyable(bar)


def _can_exit_position(
    symbol: str,
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    entry_dates: dict[str, object],
    current_date: object | None,
) -> bool:
    if entry_dates.get(symbol) == current_date:
        return False
    return is_sellable(aligned_history[symbol][index])
