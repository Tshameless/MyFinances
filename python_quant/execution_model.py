from __future__ import annotations

from dataclasses import dataclass

from .config import BacktestConfig
from .market import execution_price_for_bar, price_for_bar
from .models import PriceBar, TradeAttemptRecord, TradeRecord


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
    target_holdings: tuple[str, ...],
    target_scores: dict[str, float] | None = None,
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

    for symbol in sorted(set(positions) - set(target_holdings)):
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        if entry_dates.get(symbol) == current_date:
            trade_attempts.append(
                _build_trade_attempt(bar, "SELL", positions[symbol], price, "t_plus_one_locked", cash)
            )
            continue
        if not is_sellable(bar):
            trade_attempts.append(
                _build_trade_attempt(
                    bar,
                    "SELL",
                    positions[symbol],
                    price,
                    sell_rejection_reason(bar),
                    cash,
                )
            )
            continue
        target_shares = positions[symbol]
        shares = min(target_shares, max_sell_shares_by_volume(bar, config))
        if shares <= 0:
            trade_attempts.append(
                _build_trade_attempt(bar, "SELL", target_shares, price, "volume_limit_blocked", cash)
            )
            continue
        if shares < target_shares:
            positions[symbol] = target_shares - shares
            reason = "rebalance_exit_partial_volume_limit"
        else:
            positions.pop(symbol)
            entry_dates.pop(symbol, None)
            reason = "rebalance_exit"
        gross_value = shares * price
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
                symbol=symbol,
                side="SELL",
                shares=shares,
                price=round(price, 4),
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

    retained_targets = tuple(symbol for symbol in target_holdings if symbol in positions)
    new_targets = tuple(symbol for symbol in target_holdings if symbol not in positions)
    target_count = len(retained_targets) + len(new_targets)
    investable_equity = start_equity * (1.0 - config.target_cash_weight)
    capped_target_value = investable_equity * config.max_position_weight
    target_values = _target_values_by_symbol(
        target_holdings=target_holdings,
        target_scores=target_scores or {},
        investable_equity=investable_equity,
        capped_target_value=capped_target_value,
        config=config,
    )

    for symbol in new_targets:
        bar = aligned_history[symbol][index]
        price = execution_price_for_bar(bar, config)
        if not is_buyable(bar):
            trade_attempts.append(
                _build_trade_attempt(bar, "BUY", 0, price, buy_rejection_reason(bar), cash)
            )
            continue
        max_cash_for_position = min(target_values.get(symbol, 0.0), cash)
        requested_shares = round_down_to_lot(max_cash_for_position / price, config.lot_size)
        volume_limited_shares = max_buy_shares_by_volume(bar, config)
        shares = affordable_buy_shares(
            min(requested_shares, volume_limited_shares),
            price,
            cash,
            bar,
            config,
        )
        if shares <= 0:
            reason = (
                "volume_limit_blocked"
                if requested_shares > 0 and volume_limited_shares <= 0
                else "insufficient_cash_for_lot"
            )
            trade_attempts.append(
                _build_trade_attempt(bar, "BUY", requested_shares, price, reason, cash)
            )
            continue
        gross_value = shares * price
        commission = calculate_commission(gross_value, config, side="BUY")
        slippage = calculate_slippage(gross_value, shares, bar, config)
        transfer_fee = gross_value * config.transfer_fee_rate
        stamp_duty = 0.0
        trade_cost = commission + slippage.total + transfer_fee
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
    )


def is_buyable(bar: PriceBar) -> bool:
    return bar.tradable and bar.can_buy


def _target_values_by_symbol(
    *,
    target_holdings: tuple[str, ...],
    target_scores: dict[str, float],
    investable_equity: float,
    capped_target_value: float,
    config: BacktestConfig,
) -> dict[str, float]:
    if not target_holdings:
        return {}
    if config.allocation_model == "score_weighted":
        weights = _score_weights(target_holdings, target_scores)
    else:
        weights = {symbol: 1.0 / len(target_holdings) for symbol in target_holdings}
    return {
        symbol: min(investable_equity * weight, capped_target_value)
        for symbol, weight in weights.items()
    }


def _score_weights(
    target_holdings: tuple[str, ...],
    target_scores: dict[str, float],
) -> dict[str, float]:
    raw_values = {
        symbol: max(float(target_scores.get(symbol, 0.0)), 0.0)
        for symbol in target_holdings
    }
    total = sum(raw_values.values())
    if total <= 0:
        return {symbol: 1.0 / len(target_holdings) for symbol in target_holdings}
    return {
        symbol: value / total
        for symbol, value in raw_values.items()
    }


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
