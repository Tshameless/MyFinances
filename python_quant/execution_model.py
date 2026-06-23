from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from .config import BacktestConfig
from .market import execution_price_for_bar, price_for_bar
from .models import Order, PriceBar, TradeAttemptRecord

logger = logging.getLogger(__name__)


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
    active_orders: dict[str, Order] | None = None,
) -> tuple[list[Order], list[str]]:
    start_equity = calculate_account_equity(cash, positions, aligned_history, index, config)
    orders: list[Order] = []
    cancel_order_ids: list[str] = []
    active_orders = active_orders or {}

    pending_buys = {}
    pending_sells = {}
    
    for oid, o in active_orders.items():
        rem = o.target_shares - o.filled_shares
        if rem <= 0:
            continue
        if o.side == "BUY":
            pending_buys[o.symbol] = pending_buys.get(o.symbol, 0) + rem
        else:
            pending_sells[o.symbol] = pending_sells.get(o.symbol, 0) + rem

    all_symbols = set(positions.keys()) | set(target_weights.keys()) | set(pending_buys.keys()) | set(pending_sells.keys())

    for symbol in sorted(all_symbols):
        if symbol not in aligned_history or index >= len(aligned_history[symbol]):
            continue
            
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        if price <= 0:
            continue

        current_shares = positions.get(symbol, 0)
        target_weight = target_weights.get(symbol, 0.0)
        target_val = start_equity * target_weight
        target_shares = round_down_to_lot(target_val / price, config.lot_size)

        diff = target_shares - current_shares

        p_buy = pending_buys.get(symbol, 0)
        p_sell = pending_sells.get(symbol, 0)

        if diff > 0: # Need to buy
            if p_sell > 0:
                for oid, o in active_orders.items():
                    if o.symbol == symbol and o.side == "SELL":
                        cancel_order_ids.append(oid)
            
            if p_buy != diff:
                for oid, o in active_orders.items():
                    if o.symbol == symbol and o.side == "BUY":
                        cancel_order_ids.append(oid)
                orders.append(Order(
                    order_id=str(uuid.uuid4()),
                    date=bar.date,
                    symbol=symbol,
                    side="BUY",
                    target_shares=diff,
                    limit_price=price,
                ))

        elif diff < 0: # Need to sell
            sell_amt = -diff
            if p_buy > 0:
                for oid, o in active_orders.items():
                    if o.symbol == symbol and o.side == "BUY":
                        cancel_order_ids.append(oid)
            
            if p_sell != sell_amt:
                for oid, o in active_orders.items():
                    if o.symbol == symbol and o.side == "SELL":
                        cancel_order_ids.append(oid)
                orders.append(Order(
                    order_id=str(uuid.uuid4()),
                    date=bar.date,
                    symbol=symbol,
                    side="SELL",
                    target_shares=sell_amt,
                    limit_price=price,
                ))

        else: # target == current
            if p_buy > 0 or p_sell > 0:
                for oid, o in active_orders.items():
                    if o.symbol == symbol:
                        cancel_order_ids.append(oid)

    return orders, cancel_order_ids


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

