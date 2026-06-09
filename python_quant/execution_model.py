from __future__ import annotations

import uuid
from dataclasses import dataclass

from .config import BacktestConfig
from .market import execution_price_for_bar, price_for_bar
from .models import Order, OrderStatus, PriceBar, TradeAttemptRecord, TradeRecord


@dataclass(frozen=True)
class AccountTradeResult:
    cash: float
    positions: dict[str, int]
    entry_dates: dict[str, object]
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


def rebalance_account(
    *,
    cash: float,
    positions: dict[str, int],
    entry_dates: dict[str, object],
    target_weights: dict[str, float],
    aligned_history: dict[str, list[PriceBar]],
    index: int,
    config: BacktestConfig,
    current_date: object,
) -> AccountTradeResult:
    positions = positions.copy()
    entry_dates = entry_dates.copy()
    start_equity = calculate_account_equity(cash, positions, aligned_history, index, config)
    sold_value = 0.0
    bought_value = 0.0
    cost = 0.0
    trades: list[TradeRecord] = []
    trade_attempts: list[TradeAttemptRecord] = []
    orders: list[Order] = []

    # 1. Generate Orders
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

    retained_targets = tuple(symbol for symbol in target_weights if symbol in positions)
    new_targets = tuple(symbol for symbol in target_weights if symbol not in positions)
    target_count = len(retained_targets) + len(new_targets)
    
    target_values = {
        symbol: start_equity * weight
        for symbol, weight in target_weights.items()
    }

    for symbol in new_targets:
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        max_cash_for_position = min(target_values.get(symbol, 0.0), cash)
        requested_shares = round_down_to_lot(max_cash_for_position / price, config.lot_size)
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

    # 2. Match Orders
    for order in orders:
        bar = aligned_history[order.symbol][index]
        if order.side == "SELL":
            if entry_dates.get(order.symbol) == current_date:
                order.status = OrderStatus.REJECTED
                order.reason = "t_plus_one_locked"
                trade_attempts.append(
                    _build_trade_attempt(bar, order.side, order.target_shares, order.limit_price, order.reason, cash)
                )
                continue
            if not is_sellable(bar):
                order.status = OrderStatus.REJECTED
                order.reason = sell_rejection_reason(bar)
                trade_attempts.append(
                    _build_trade_attempt(
                        bar,
                        order.side,
                        order.target_shares,
                        order.limit_price,
                        order.reason,
                        cash,
                    )
                )
                continue
            
            shares = min(order.target_shares, max_sell_shares_by_volume(bar, config))
            if shares <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "volume_limit_blocked"
                trade_attempts.append(
                    _build_trade_attempt(bar, order.side, order.target_shares, order.limit_price, order.reason, cash)
                )
                continue
            
            order.filled_shares = shares
            if shares < order.target_shares:
                order.status = OrderStatus.PARTIAL
                positions[order.symbol] = order.target_shares - shares
                reason = "rebalance_exit_partial_volume_limit"
            else:
                order.status = OrderStatus.FILLED
                positions.pop(order.symbol)
                entry_dates.pop(order.symbol, None)
                reason = "rebalance_exit"
            
            gross_value = shares * order.limit_price
            commission = calculate_commission(gross_value, config, side="SELL")
            slippage = calculate_slippage(gross_value, shares, bar, config)
            transfer_fee = gross_value * config.transfer_fee_rate
            stamp_duty = gross_value * config.stamp_duty_rate
            trade_cost = commission + slippage.total + transfer_fee + stamp_duty
            cash += gross_value - trade_cost
            sold_value += gross_value
            cost += trade_cost
            trades.append(
                TradeRecord(
                    date=bar.date,
                    symbol=order.symbol,
                    side="SELL",
                    shares=shares,
                    price=round(order.limit_price, 4),
                    gross_value=round(gross_value, 2),
                    commission=round(commission, 2),
                    slippage=round(slippage.total, 2),
                    transfer_fee=round(transfer_fee, 2),
                    stamp_duty=round(stamp_duty, 2),
                    total_cost=round(trade_cost, 2),
                    cash_change=round(gross_value - trade_cost, 2),
                    reason=reason,
                    fixed_slippage=round(slippage.fixed, 2),
                    market_impact=round(slippage.market_impact, 2),
                )
            )

        elif order.side == "BUY":
            if not is_buyable(bar):
                order.status = OrderStatus.REJECTED
                order.reason = buy_rejection_reason(bar)
                trade_attempts.append(
                    _build_trade_attempt(bar, order.side, order.target_shares, order.limit_price, order.reason, cash)
                )
                continue
            
            volume_limited_shares = max_buy_shares_by_volume(bar, config)
            shares = affordable_buy_shares(
                min(order.target_shares, volume_limited_shares),
                order.limit_price,
                cash,
                bar,
                config,
            )
            if shares <= 0:
                reason = (
                    "volume_limit_blocked"
                    if order.target_shares > 0 and volume_limited_shares <= 0
                    else "insufficient_cash_for_lot"
                )
                order.status = OrderStatus.REJECTED
                order.reason = reason
                trade_attempts.append(
                    _build_trade_attempt(bar, order.side, order.target_shares, order.limit_price, order.reason, cash)
                )
                continue
            
            order.filled_shares = shares
            if shares < order.target_shares:
                order.status = OrderStatus.PARTIAL
            else:
                order.status = OrderStatus.FILLED
                
            gross_value = shares * order.limit_price
            commission = calculate_commission(gross_value, config, side="BUY")
            slippage = calculate_slippage(gross_value, shares, bar, config)
            transfer_fee = gross_value * config.transfer_fee_rate
            stamp_duty = 0.0
            trade_cost = commission + slippage.total + transfer_fee
            cash -= gross_value + trade_cost
            positions[order.symbol] = shares
            entry_dates[order.symbol] = current_date
            bought_value += gross_value
            cost += trade_cost
            trades.append(
                TradeRecord(
                    date=bar.date,
                    symbol=order.symbol,
                    side="BUY",
                    shares=shares,
                    price=round(order.limit_price, 4),
                    gross_value=round(gross_value, 2),
                    commission=round(commission, 2),
                    slippage=round(slippage.total, 2),
                    transfer_fee=round(transfer_fee, 2),
                    stamp_duty=round(stamp_duty, 2),
                    total_cost=round(trade_cost, 2),
                    cash_change=round(-(gross_value + trade_cost), 2),
                    reason="rebalance_entry",
                    fixed_slippage=round(slippage.fixed, 2),
                    market_impact=round(slippage.market_impact, 2),
                )
            )

    holdings = tuple(sorted(positions))
    return AccountTradeResult(
        cash=cash,
        positions=positions,
        entry_dates=entry_dates,
        holdings=holdings,
        buy_turnover=0.0 if start_equity == 0 else bought_value / start_equity,
        sell_turnover=0.0 if start_equity == 0 else sold_value / start_equity,
        cost=cost,
        trades=trades,
        trade_attempts=trade_attempts,
        orders=orders,
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


def _build_trade_attempt(
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
