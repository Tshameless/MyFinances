from __future__ import annotations

import uuid
from datetime import date
from typing import Sequence

from .broker_gateway import BaseBrokerGateway
from .config import BacktestConfig
from .execution_model import (
    build_trade_attempt,
    affordable_buy_shares,
    buy_rejection_reason,
    calculate_commission,
    calculate_slippage,
    is_buyable,
    is_sellable,
    max_buy_shares_by_volume,
    max_sell_shares_by_volume,
    sell_rejection_reason,
)
from .models import Order, OrderStatus, PriceBar, TradeAttemptRecord, TradeRecord


class SimulatedBroker(BaseBrokerGateway):
    """
    Simulated broker gateway matching engine.
    Holds positions, cash, and processes active orders against daily market bars.
    """

    def __init__(self, initial_cash: float, config: BacktestConfig):
        self.cash = initial_cash
        self.positions: dict[str, int] = {}
        self.entry_dates: dict[str, date] = {}
        self.config = config
        
        self.active_orders: dict[str, Order] = {}
        
        self.trades_today: list[TradeRecord] = []
        self.trade_attempts_today: list[TradeAttemptRecord] = []
        
        self.all_trades: list[TradeRecord] = []
        self.all_attempts: list[TradeAttemptRecord] = []
        self.all_orders: list[Order] = []
        
        self.cost_today = 0.0
        self.bought_value_today = 0.0
        self.sold_value_today = 0.0

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def submit_orders(self, orders: Sequence[Order]) -> list[Order]:
        for o in orders:
            self.active_orders[o.order_id] = o
            self.all_orders.append(o)
        return list(orders)

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.active_orders:
            o = self.active_orders[order_id]
            o.status = OrderStatus.CANCELED
            del self.active_orders[order_id]
            return True
        return False

    def sync_orders(self, orders: Sequence[Order]) -> list[Order]:
        return list(orders)

    def get_account_cash(self) -> float:
        return self.cash

    def get_account_positions(self) -> dict[str, int]:
        return self.positions.copy()

    def process_market_data(
        self,
        current_date: date,
        aligned_history: dict[str, list[PriceBar]],
        index: int,
    ) -> None:
        """Match pending/partial orders against today's price bars."""
        self.trades_today.clear()
        self.trade_attempts_today.clear()
        self.cost_today = 0.0
        self.bought_value_today = 0.0
        self.sold_value_today = 0.0
        
        # Sort to ensure SELL runs before BUY (free up cash)
        sell_orders = [o for o in self.active_orders.values() if o.side == "SELL"]
        buy_orders = [o for o in self.active_orders.values() if o.side == "BUY"]
        
        for o in sell_orders:
            self._process_sell(o, current_date, aligned_history, index)
            
        for o in buy_orders:
            self._process_buy(o, current_date, aligned_history, index)
            
        to_remove = [
            oid for oid, o in self.active_orders.items() 
            if o.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED)
        ]
        for oid in to_remove:
            del self.active_orders[oid]

    def _process_sell(
        self, 
        order: Order, 
        current_date: date, 
        aligned_history: dict[str, list[PriceBar]], 
        index: int
    ) -> None:
        if order.symbol not in aligned_history or index >= len(aligned_history[order.symbol]):
            return
            
        bar = aligned_history[order.symbol][index]
        remaining = order.target_shares - order.filled_shares
        if remaining <= 0:
            return
            
        if self.entry_dates.get(order.symbol) == current_date:
            order.status = OrderStatus.REJECTED
            order.reason = "t_plus_one_locked"
            self._record_attempt(bar, order, self.cash)
            return
            
        if not is_sellable(bar):
            order.status = OrderStatus.REJECTED
            order.reason = sell_rejection_reason(bar)
            self._record_attempt(bar, order, self.cash)
            return
            
        max_sell = max_sell_shares_by_volume(bar, self.config)
        shares = min(remaining, max_sell)
        
        if shares <= 0:
            order.status = OrderStatus.REJECTED
            order.reason = "volume_limit_blocked"
            self._record_attempt(bar, order, self.cash)
            return
            
        # Execute trade
        order.filled_shares += shares
        if order.filled_shares < order.target_shares:
            order.status = OrderStatus.PARTIAL
            self.positions[order.symbol] = self.positions.get(order.symbol, 0) - shares
            reason = "rebalance_exit_partial_volume_limit"
        else:
            order.status = OrderStatus.FILLED
            current_pos = self.positions.get(order.symbol, 0)
            if current_pos <= shares:
                self.positions.pop(order.symbol, None)
                self.entry_dates.pop(order.symbol, None)
            else:
                self.positions[order.symbol] = current_pos - shares
            reason = "rebalance_exit"
            
        execution_price = order.limit_price or bar.close
        gross_value = shares * execution_price
        commission = calculate_commission(gross_value, self.config, side="SELL")
        slippage = calculate_slippage(gross_value, shares, bar, self.config)
        transfer_fee = gross_value * self.config.transfer_fee_rate
        stamp_duty = gross_value * self.config.stamp_duty_rate
        trade_cost = commission + slippage.total + transfer_fee + stamp_duty
        
        self.cash += gross_value - trade_cost
        self.sold_value_today += gross_value
        self.cost_today += trade_cost
        
        trade = TradeRecord(
            date=bar.date,
            symbol=order.symbol,
            side="SELL",
            shares=shares,
            price=round(execution_price, 4),
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
        self.trades_today.append(trade)
        self.all_trades.append(trade)

    def _process_buy(
        self, 
        order: Order, 
        current_date: date, 
        aligned_history: dict[str, list[PriceBar]], 
        index: int
    ) -> None:
        if order.symbol not in aligned_history or index >= len(aligned_history[order.symbol]):
            return
            
        bar = aligned_history[order.symbol][index]
        remaining = order.target_shares - order.filled_shares
        if remaining <= 0:
            return
            
        if not is_buyable(bar):
            order.status = OrderStatus.REJECTED
            order.reason = buy_rejection_reason(bar)
            self._record_attempt(bar, order, self.cash)
            return
            
        execution_price = order.limit_price or bar.close
        volume_limited = max_buy_shares_by_volume(bar, self.config)
        affordable = affordable_buy_shares(
            min(remaining, volume_limited),
            execution_price,
            self.cash,
            bar,
            self.config,
        )
        
        if affordable <= 0:
            reason = "volume_limit_blocked" if remaining > 0 and volume_limited <= 0 else "insufficient_cash_for_lot"
            order.status = OrderStatus.REJECTED
            order.reason = reason
            self._record_attempt(bar, order, self.cash)
            return
            
        order.filled_shares += affordable
        if order.filled_shares < order.target_shares:
            order.status = OrderStatus.PARTIAL
        else:
            order.status = OrderStatus.FILLED
            
        gross_value = affordable * execution_price
        commission = calculate_commission(gross_value, self.config, side="BUY")
        slippage = calculate_slippage(gross_value, affordable, bar, self.config)
        transfer_fee = gross_value * self.config.transfer_fee_rate
        stamp_duty = 0.0
        trade_cost = commission + slippage.total + transfer_fee
        
        self.cash -= gross_value + trade_cost
        self.positions[order.symbol] = self.positions.get(order.symbol, 0) + affordable
        self.entry_dates[order.symbol] = current_date
        
        self.bought_value_today += gross_value
        self.cost_today += trade_cost
        
        trade = TradeRecord(
            date=bar.date,
            symbol=order.symbol,
            side="BUY",
            shares=affordable,
            price=round(execution_price, 4),
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
        self.trades_today.append(trade)
        self.all_trades.append(trade)

    def _record_attempt(self, bar: PriceBar, order: Order, cash: float) -> None:
        attempt = build_trade_attempt(
            bar, 
            order.side, 
            order.target_shares - order.filled_shares, 
            order.limit_price or bar.close, 
            order.reason or "unknown", 
            cash
        )
        self.trade_attempts_today.append(attempt)
        self.all_attempts.append(attempt)
