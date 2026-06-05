from dataclasses import dataclass


@dataclass(frozen=True)
class PriceBar:
    date: str
    symbol: str
    close: float


@dataclass(frozen=True)
class EquityPoint:
    date: str
    equity: float


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    volatility: float
    sharpe: float
