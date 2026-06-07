from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PriceBar:
    date: date
    symbol: str
    close: float
    adjusted_close: float | None = None
    volume: float | None = None
    tradable: bool = True
    can_buy: bool = True
    can_sell: bool = True


@dataclass(frozen=True)
class EquityPoint:
    date: date
    equity: float
    daily_return: float
    holdings: tuple[str, ...]


@dataclass(frozen=True)
class RebalanceRecord:
    date: date
    holdings: tuple[str, ...]
    buy_turnover: float
    sell_turnover: float
    turnover: float
    cost: float


@dataclass(frozen=True)
class PositionPoint:
    date: date
    symbol: str
    shares: int
    price: float
    market_value: float
    weight: float
    cash: float
    total_equity: float


@dataclass(frozen=True)
class TradeRecord:
    date: date
    symbol: str
    side: str
    shares: int
    price: float
    gross_value: float
    commission: float
    slippage: float
    stamp_duty: float
    total_cost: float
    cash_change: float
    reason: str


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    volatility: float
    downside_volatility: float
    sharpe: float
    sortino: float
    calmar: float
    win_rate: float
    average_turnover: float
    total_cost: float
    periods: int
    benchmark_total_return: float | None = None
    benchmark_annualized_return: float | None = None
    benchmark_volatility: float | None = None
    benchmark_max_drawdown: float | None = None
    excess_return: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None


@dataclass(frozen=True)
class BenchmarkPoint:
    date: date
    equity: float
    daily_return: float


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: list[EquityPoint]
    rebalance_records: list[RebalanceRecord]
    metrics: BacktestMetrics
    benchmark_curve: list[BenchmarkPoint] | None = None
    positions: list[PositionPoint] | None = None
    trades: list[TradeRecord] | None = None
