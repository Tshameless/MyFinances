from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date

from .config import BacktestConfig
from .market import execution_price_for_bar, price_for_bar
from .models import Order, PriceBar, TradeAttemptRecord, TradeRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountTradeResult:
    cash: float
    positions: dict[str, int]
    entry_dates: dict[str, date]
    holdings: tuple[str, ...]
    buy_turnover: float
    sell_turnover: float
    cost: float
    trades: list[TradeRecord]
    trade_attempts: list[TradeAttemptRecord]
    orders: list[Order]


@dataclass(frozen=True)
class SlippageBreakdown:
    total: float
    fixed: float
    market_impact: float


def calculate_account_equity(
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


def generate_orders_from_weights(
    cash: float,
    positions: dict[str, int],
    target_weights: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
) -> list[Order]:
    start_equity = calculate_account_equity(cash, positions, aligned_history, index, config)
    orders: list[Order] = []

    for symbol in sorted(set(positions) - set(target_weights.keys())):
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        orders.append(
            Order(
                order_id=str(uuid.uuid4()),
                date=bar.date,
                symbol=symbol,
                side="SELL",
                target_shares=positions[symbol],
                limit_price=price,
            )
        )

    target_values = {
        symbol: start_equity * weight
        for symbol, weight in target_weights.items()
    }

    new_targets = tuple(symbol for symbol in target_weights if symbol not in positions)
    for symbol in new_targets:
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        if price <= 0:
            continue
        max_cash_for_position = min(target_values.get(symbol, 0.0), cash)
        requested_shares = round_down_to_lot(max_cash_for_position / price, config.lot_size)
        if requested_shares > 0:
            orders.append(
                Order(
                    order_id=str(uuid.uuid4()),
                    date=bar.date,
                    symbol=symbol,
                    side="BUY",
                    target_shares=requested_shares,
                    limit_price=price,
                )
            )

    return orders


def rebalance_account(
    *,
    cash: float,
    positions: dict[str, int],
    entry_dates: dict[str, date],
    target_weights: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
    current_date: date,
) -> AccountTradeResult:
    """Backward-compatible one-shot rebalance helper built on the broker model."""
    from .simulated_broker import SimulatedBroker

    start_equity = calculate_account_equity(cash, positions, aligned_history, index, config)
    broker = SimulatedBroker(initial_cash=cash, config=config)
    broker.positions = positions.copy()
    broker.entry_dates = entry_dates.copy()
    orders = generate_orders_from_weights(
        cash=cash,
        positions=positions,
        target_weights=target_weights,
        aligned_history=aligned_history,
        index=index,
        config=config,
    )
    broker.submit_orders(orders)
    broker.process_market_data(current_date, aligned_history, index)

    buy_turnover = broker.bought_value_today / start_equity if start_equity > 0 else 0.0
    sell_turnover = broker.sold_value_today / start_equity if start_equity > 0 else 0.0
    return AccountTradeResult(
        cash=broker.cash,
        positions=broker.positions.copy(),
        entry_dates=broker.entry_dates.copy(),
        holdings=tuple(sorted(broker.positions)),
        buy_turnover=buy_turnover,
        sell_turnover=sell_turnover,
        cost=broker.cost_today,
        trades=list(broker.trades_today),
        trade_attempts=list(broker.trade_attempts_today),
        orders=list(broker.all_orders),
    )


def is_buyable(bar: PriceBar) -> bool:
    return bar.tradable and bar.can_buy


def is_sellable(bar: PriceBar) -> bool:
    return bar.tradable and bar.can_sell


def buy_rejection_reason(bar: PriceBar) -> str:
    if bar.is_suspended:
        return "suspended"
    if not bar.tradable:
        return "not_tradable"
    if bar.is_limit_up:
        return "limit_up_blocked"
    if not bar.can_buy:
        return "not_buyable"
    return "not_buyable"


def sell_rejection_reason(bar: PriceBar) -> str:
    if bar.is_suspended:
        return "suspended"
    if not bar.tradable:
        return "not_tradable"
    if bar.is_limit_down:
        return "limit_down_blocked"
    if not bar.can_sell:
        return "not_sellable"
    return "not_sellable"


def round_down_to_lot(shares: float, lot_size: int) -> int:
    return int(shares // lot_size) * lot_size


def max_buy_shares_by_volume(bar: PriceBar, config: BacktestConfig) -> int:
    if bar.volume is None:
        return 10**18
    participation = _effective_volume_participation(config)
    return round_down_to_lot(bar.volume * participation, config.lot_size)


def max_sell_shares_by_volume(bar: PriceBar, config: BacktestConfig) -> int:
    if bar.volume is None:
        return 10**18
    return int(bar.volume * _effective_volume_participation(config))


def _effective_volume_participation(config: BacktestConfig) -> float:
    if config.execution_style != "twap":
        return config.max_volume_participation
    return config.max_volume_participation / config.twap_slices


def affordable_buy_shares(
    requested_shares: int,
    price: float,
    cash: float,
    bar: PriceBar,
    config: BacktestConfig,
) -> int:
    shares = round_down_to_lot(requested_shares, config.lot_size)
    if shares <= 0 or price <= 0:
        return 0
    # 直接计算上界，避免 lot_size=1 时的 O(n) 线性退格
    total_rate = (
        config.buy_commission_rate_effective
        + config.slippage_rate
        + config.transfer_fee_rate
    )
    max_affordable = round_down_to_lot(
        int(cash / (price * (1.0 + total_rate))),
        config.lot_size,
    )
    shares = min(shares, max_affordable)
    # 精确校验：考虑 market_impact 和 min_commission
    while shares > 0:
        gross_value = shares * price
        commission = calculate_commission(gross_value, config, side="BUY")
        slippage = calculate_slippage(gross_value, shares, bar, config)
        transfer_fee = gross_value * config.transfer_fee_rate
        if gross_value + commission + slippage.total + transfer_fee <= cash:
            return shares
        shares -= config.lot_size
    return 0


def calculate_commission(gross_value: float, config: BacktestConfig, *, side: str) -> float:
    commission_rate = (
        config.sell_commission_rate_effective
        if side == "SELL"
        else config.buy_commission_rate_effective
    )
    commission = gross_value * commission_rate
    if gross_value > 0 and config.min_commission > 0:
        return max(commission, config.min_commission)
    return commission


def calculate_slippage(
    gross_value: float,
    shares: int,
    bar: PriceBar,
    config: BacktestConfig,
) -> SlippageBreakdown:
    fixed_slippage = gross_value * config.slippage_rate
    if bar.volume is None or bar.volume <= 0 or shares <= 0:
        return SlippageBreakdown(
            total=fixed_slippage,
            fixed=fixed_slippage,
            market_impact=0.0,
        )
    participation_rate = shares / bar.volume
    impact_rate = config.market_impact_coefficient * (
        participation_rate ** config.market_impact_exponent
    )
    market_impact = gross_value * impact_rate
    return SlippageBreakdown(
        total=fixed_slippage + market_impact,
        fixed=fixed_slippage,
        market_impact=market_impact,
    )


def build_trade_attempt(
    bar: PriceBar,
    side: str,
    target_shares: int,
    price: float,
    reason: str,
    cash: float,
) -> TradeAttemptRecord:
    return TradeAttemptRecord(
        date=bar.date,
        symbol=bar.symbol,
        side=side,
        target_shares=target_shares,
        price=round(price, 4),
        reason=reason,
        cash=round(cash, 2),
    )


# Backward-compatible alias
_build_trade_attempt = build_trade_attempt
