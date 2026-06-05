from __future__ import annotations

from math import sqrt

from . import config
from .factors import calculate_factor_scores, group_prices_by_symbol
from .models import BacktestMetrics, EquityPoint, PriceBar
from .strategy import select_symbols


def run_backtest(bars: list[PriceBar]) -> tuple[list[EquityPoint], BacktestMetrics]:
    history_by_symbol = group_prices_by_symbol(bars)
    if not history_by_symbol:
        raise ValueError("No price data available for backtest.")

    common_length = min(len(symbol_bars) for symbol_bars in history_by_symbol.values())
    if common_length < config.LOOKBACK_MOMENTUM + 2:
        raise ValueError("Not enough history to run the strategy.")

    equity = config.INITIAL_CASH
    equity_curve: list[EquityPoint] = []
    holdings: list[str] = []

    warmup = max(
        config.LOOKBACK_MOMENTUM,
        config.LOOKBACK_MEAN_REVERSION,
        config.LOOKBACK_VOLATILITY,
    )

    for index in range(warmup, common_length - 1):
        first_symbol = next(iter(history_by_symbol))
        current_date = history_by_symbol[first_symbol][index].date

        if not holdings or (index - warmup) % config.REBALANCE_EVERY_N_DAYS == 0:
            scores = calculate_factor_scores(history_by_symbol, index)
            holdings = select_symbols(scores, config.TOP_N)
            turnover_cost = equity * (config.COMMISSION_RATE + config.SLIPPAGE_RATE)
            equity -= turnover_cost

        daily_returns: list[float] = []
        for symbol in holdings:
            bars_for_symbol = history_by_symbol[symbol]
            today_close = bars_for_symbol[index].close
            next_close = bars_for_symbol[index + 1].close
            daily_returns.append(next_close / today_close - 1.0)

        portfolio_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
        equity *= 1.0 + portfolio_return
        equity_curve.append(EquityPoint(date=current_date, equity=round(equity, 2)))

    metrics = _calculate_metrics(equity_curve)
    return equity_curve, metrics


def _calculate_metrics(equity_curve: list[EquityPoint]) -> BacktestMetrics:
    if len(equity_curve) < 2:
        raise ValueError("Equity curve is too short to calculate metrics.")

    daily_returns: list[float] = []
    peak = equity_curve[0].equity
    max_drawdown = 0.0

    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1].equity
        current = equity_curve[index].equity
        daily_returns.append(current / previous - 1.0)
        peak = max(peak, current)
        drawdown = current / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    total_return = equity_curve[-1].equity / equity_curve[0].equity - 1.0
    mean_return = sum(daily_returns) / len(daily_returns)
    variance = (
        sum((daily - mean_return) ** 2 for daily in daily_returns) / max(len(daily_returns) - 1, 1)
    )
    volatility = sqrt(max(variance, 0.0)) * sqrt(252)
    annualized_return = (1.0 + total_return) ** (252 / len(daily_returns)) - 1.0
    sharpe = 0.0 if volatility == 0 else annualized_return / volatility

    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=max_drawdown,
        volatility=volatility,
        sharpe=sharpe,
    )
