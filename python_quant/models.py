from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .enums import OrderStatusEnum


@dataclass(frozen=True)
class PriceBar:
    date: date
    symbol: str
    close: float
    adjusted_close: float | None = None
    adjustment_factor: float | None = None
    open: float | None = None
    vwap: float | None = None
    volume: float | None = None
    tradable: bool = True
    can_buy: bool = True
    can_sell: bool = True
    is_suspended: bool = False
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_st: bool = False
    limit_rate: float | None = None


@dataclass(frozen=True)
class CorporateAction:
    date: date
    symbol: str
    action_type: str
    value: float | None = None
    description: str | None = None


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


class OrderStatus:
    """Backward-compatible OrderStatus constants backed by StrEnum values."""

    PENDING = OrderStatusEnum.PENDING
    PARTIAL = OrderStatusEnum.PARTIAL
    FILLED = OrderStatusEnum.FILLED
    CANCELED = OrderStatusEnum.CANCELED
    REJECTED = OrderStatusEnum.REJECTED


@dataclass
class Order:
    order_id: str
    date: date
    symbol: str
    side: str
    target_shares: int
    limit_price: float | None = None
    filled_shares: int = 0
    status: str = OrderStatus.PENDING
    reason: str | None = None


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
    transfer_fee: float
    stamp_duty: float
    total_cost: float
    cash_change: float
    reason: str
    fixed_slippage: float = 0.0
    market_impact: float = 0.0


@dataclass(frozen=True)
class TradeAttemptRecord:
    date: date
    symbol: str
    side: str
    target_shares: int
    price: float
    reason: str
    cash: float


@dataclass(frozen=True)
class FactorScoreRecord:
    """因子评分记录。

    所有因子分数统一存储在 ``raw_scores`` / ``normalized_scores`` 字典中，
    不再为内置三因子保留硬编码字段。旧的 ``momentum`` 等属性通过
    ``@property`` 提供向后兼容只读访问。
    """

    date: date
    symbol: str
    total_score: float
    selected: bool
    raw_scores: dict[str, float] = field(default_factory=dict)
    normalized_scores: dict[str, float] = field(default_factory=dict)

    # ------ 向后兼容只读属性 ------

    @property
    def momentum(self) -> float:
        return self.raw_scores.get("momentum", 0.0)

    @property
    def mean_reversion(self) -> float:
        return self.raw_scores.get("mean_reversion", 0.0)

    @property
    def low_volatility(self) -> float:
        return self.raw_scores.get("low_volatility", 0.0)

    @property
    def normalized_momentum(self) -> float:
        return self.normalized_scores.get("momentum", 0.0)

    @property
    def normalized_mean_reversion(self) -> float:
        return self.normalized_scores.get("mean_reversion", 0.0)

    @property
    def normalized_low_volatility(self) -> float:
        return self.normalized_scores.get("low_volatility", 0.0)


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
    trade_attempts: list[TradeAttemptRecord] | None = None
    factor_scores: list[FactorScoreRecord] | None = None
    price_bars: list[PriceBar] | None = None
    orders: list[Order] = field(default_factory=list)
