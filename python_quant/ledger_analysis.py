from __future__ import annotations

from collections import defaultdict

from .models import EquityPoint, PositionPoint, TradeRecord


def build_pnl_ledger_analysis(
    equity_curve: list[EquityPoint],
    positions: list[PositionPoint],
    trades: list[TradeRecord],
) -> dict[str, object]:
    if not equity_curve:
        return {"rows": [], "summary": {"periods": 0}}

    positions_by_date: dict[object, list[PositionPoint]] = defaultdict(list)
    for position in positions:
        positions_by_date[position.date].append(position)

    trades_by_date: dict[object, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        trades_by_date[trade.date].append(trade)

    rows: list[dict[str, object]] = []
    previous_equity: float | None = None
    total_net_cash_flow = 0.0
    total_cost_sum = 0.0
    total_market_pnl = 0.0
    max_abs_difference = 0.0
    for point in equity_curve:
        day_positions = positions_by_date.get(point.date, [])
        day_trades = trades_by_date.get(point.date, [])
        starting_equity = _starting_equity(point, previous_equity)
        ending_equity = point.equity
        equity_change = ending_equity - starting_equity
        total_cost = sum(trade.total_cost for trade in day_trades)
        gross_buy_value = sum(trade.gross_value for trade in day_trades if trade.side == "BUY")
        gross_sell_value = sum(trade.gross_value for trade in day_trades if trade.side == "SELL")
        net_cash_flow = sum(trade.cash_change for trade in day_trades)
        ending_cash = _ending_cash(day_positions)
        ending_market_value = sum(
            position.market_value
            for position in day_positions
            if position.symbol != "CASH"
        )
        ledger_equity = ending_cash + ending_market_value
        reconciliation_difference = ending_equity - ledger_equity
        market_pnl = equity_change - net_cash_flow
        total_net_cash_flow += net_cash_flow
        total_cost_sum += total_cost
        total_market_pnl += market_pnl
        max_abs_difference = max(max_abs_difference, abs(reconciliation_difference))

        rows.append(
            {
                "date": point.date.isoformat(),
                "starting_equity": starting_equity,
                "ending_equity": ending_equity,
                "equity_change": equity_change,
                "daily_return": point.daily_return,
                "gross_buy_value": gross_buy_value,
                "gross_sell_value": gross_sell_value,
                "net_cash_flow": net_cash_flow,
                "total_cost": total_cost,
                "market_pnl": market_pnl,
                "ending_cash": ending_cash,
                "ending_market_value": ending_market_value,
                "ledger_equity": ledger_equity,
                "reconciliation_difference": reconciliation_difference,
                "trade_count": len(day_trades),
                "holding_count": len([position for position in day_positions if position.symbol != "CASH"]),
            }
        )
        previous_equity = ending_equity

    summary = {
        "periods": len(rows),
        "total_equity_change": equity_curve[-1].equity - _starting_equity(equity_curve[0], None),
        "total_net_cash_flow": total_net_cash_flow,
        "total_cost": total_cost_sum,
        "total_market_pnl": total_market_pnl,
        "max_abs_reconciliation_difference": max_abs_difference,
        "reconciled": max_abs_difference < 0.01,
    }
    return {"rows": rows, "summary": summary}


def _starting_equity(point: EquityPoint, previous_equity: float | None) -> float:
    if previous_equity is not None:
        return previous_equity
    if point.daily_return == -1.0:
        return 0.0
    return point.equity / (1.0 + point.daily_return)


def _ending_cash(positions: list[PositionPoint]) -> float:
    cash_positions = [position for position in positions if position.symbol == "CASH"]
    if cash_positions:
        return cash_positions[-1].cash
    if positions:
        return positions[-1].cash
    return 0.0
