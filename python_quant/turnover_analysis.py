from __future__ import annotations

from datetime import date

from .models import RebalanceRecord, TradeRecord


def build_turnover_analysis(
    rebalances: list[RebalanceRecord],
    trades: list[TradeRecord],
) -> dict[str, object]:
    rebalance_rows = _build_rebalance_rows(rebalances)
    holding_rows = _build_realized_holding_rows(trades)
    holding_periods = [_int_value(row["holding_days"]) for row in holding_rows]
    entry_count = sum(_int_value(row["entries"]) for row in rebalance_rows)
    exit_count = sum(_int_value(row["exits"]) for row in rebalance_rows)
    summary = {
        "rebalance_count": len(rebalances),
        "entry_count": entry_count,
        "exit_count": exit_count,
        "average_entries_per_rebalance": 0.0 if not rebalances else entry_count / len(rebalances),
        "average_exits_per_rebalance": 0.0 if not rebalances else exit_count / len(rebalances),
        "realized_holding_count": len(holding_rows),
        "average_realized_holding_days": (
            0.0 if not holding_periods else sum(holding_periods) / len(holding_periods)
        ),
        "min_realized_holding_days": min(holding_periods, default=0),
        "max_realized_holding_days": max(holding_periods, default=0),
        "open_position_count": _count_open_positions(trades),
    }
    return {
        "summary": summary,
        "rebalance_rows": rebalance_rows,
        "holding_period_rows": holding_rows,
    }


def _build_rebalance_rows(rebalances: list[RebalanceRecord]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    previous_holdings: set[str] = set()
    for rebalance in rebalances:
        current_holdings = set(rebalance.holdings)
        entries = sorted(current_holdings - previous_holdings)
        exits = sorted(previous_holdings - current_holdings)
        retained = sorted(current_holdings & previous_holdings)
        rows.append(
            {
                "date": rebalance.date.isoformat(),
                "holding_count": len(current_holdings),
                "entries": len(entries),
                "exits": len(exits),
                "retained": len(retained),
                "entry_symbols": "|".join(entries),
                "exit_symbols": "|".join(exits),
                "retained_symbols": "|".join(retained),
                "buy_turnover": rebalance.buy_turnover,
                "sell_turnover": rebalance.sell_turnover,
                "turnover": rebalance.turnover,
                "cost": rebalance.cost,
            }
        )
        previous_holdings = current_holdings
    return rows


def _build_realized_holding_rows(trades: list[TradeRecord]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    lots: dict[str, list[dict[str, object]]] = {}
    for trade in sorted(trades, key=lambda item: (item.date, item.symbol, item.side)):
        if trade.side == "BUY":
            lots.setdefault(trade.symbol, []).append(
                {
                    "entry_date": trade.date,
                    "shares": trade.shares,
                    "entry_price": trade.price,
                }
            )
            continue
        if trade.side != "SELL":
            continue

        shares_to_close = trade.shares
        symbol_lots = lots.setdefault(trade.symbol, [])
        while shares_to_close > 0 and symbol_lots:
            lot = symbol_lots[0]
            lot_shares = _int_value(lot["shares"])
            closed_shares = min(shares_to_close, lot_shares)
            entry_date = lot["entry_date"]
            if not isinstance(entry_date, date):
                break
            rows.append(
                {
                    "symbol": trade.symbol,
                    "entry_date": entry_date.isoformat(),
                    "exit_date": trade.date.isoformat(),
                    "shares": closed_shares,
                    "entry_price": lot["entry_price"],
                    "exit_price": trade.price,
                    "holding_days": (trade.date - entry_date).days,
                    "exit_reason": trade.reason,
                }
            )
            shares_to_close -= closed_shares
            remaining_shares = lot_shares - closed_shares
            if remaining_shares > 0:
                lot["shares"] = remaining_shares
            else:
                symbol_lots.pop(0)
    return rows


def _count_open_positions(trades: list[TradeRecord]) -> int:
    shares_by_symbol: dict[str, int] = {}
    for trade in trades:
        if trade.side == "BUY":
            shares_by_symbol[trade.symbol] = shares_by_symbol.get(trade.symbol, 0) + trade.shares
        elif trade.side == "SELL":
            shares_by_symbol[trade.symbol] = shares_by_symbol.get(trade.symbol, 0) - trade.shares
    return sum(1 for shares in shares_by_symbol.values() if shares > 0)


def _int_value(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError(f"Expected int value, got {type(value).__name__}.")
    return value
