from __future__ import annotations

from collections import defaultdict
from typing import cast

from .models import TradeRecord

_COST_COMPONENTS = ("commission", "fixed_slippage", "market_impact", "transfer_fee", "stamp_duty")


def build_cost_attribution_analysis(
    trades: list[TradeRecord],
    symbol_groups: dict[str, str] | None = None,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    symbol_groups = symbol_groups or {}

    for trade in trades:
        group = symbol_groups.get(trade.symbol, "未分组")
        for component in _COST_COMPONENTS:
            amount = float(getattr(trade, component))
            rows.append(
                {
                    "date": trade.date.isoformat(),
                    "symbol": trade.symbol,
                    "group": group,
                    "side": trade.side,
                    "reason": trade.reason,
                    "component": component,
                    "amount": amount,
                    "gross_value": trade.gross_value,
                    "cost_bps": 0.0 if trade.gross_value == 0 else amount / trade.gross_value * 10_000,
                }
            )

    total_cost = sum(trade.total_cost for trade in trades)
    gross_value = sum(trade.gross_value for trade in trades)
    slippage_cost = sum(trade.slippage for trade in trades)
    market_impact_cost = sum(trade.market_impact for trade in trades)
    fixed_slippage_cost = sum(trade.fixed_slippage for trade in trades)
    return {
        "rows": rows,
        "summary": {
            "trades": len(trades),
            "total_gross_value": gross_value,
            "total_cost": total_cost,
            "cost_bps": 0.0 if gross_value == 0 else total_cost / gross_value * 10_000,
            "slippage_cost": slippage_cost,
            "fixed_slippage_cost": fixed_slippage_cost,
            "market_impact_cost": market_impact_cost,
            "component_costs": _aggregate(rows, "component"),
            "side_costs": _trade_costs_by(trades, "side"),
            "reason_costs": _trade_costs_by(trades, "reason"),
            "symbol_costs": _trade_costs_by(trades, "symbol"),
            "group_costs": _group_costs(trades, symbol_groups),
            "daily_costs": _daily_costs(trades),
        },
    }


def _aggregate(rows: list[dict[str, object]], field: str) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        totals[str(row[field])] += cast(float, row["amount"])
    return dict(sorted(totals.items()))


def _trade_costs_by(trades: list[TradeRecord], field: str) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        totals[str(getattr(trade, field))] += trade.total_cost
    return dict(sorted(totals.items()))


def _group_costs(trades: list[TradeRecord], symbol_groups: dict[str, str]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        totals[symbol_groups.get(trade.symbol, "未分组")] += trade.total_cost
    return dict(sorted(totals.items()))


def _daily_costs(trades: list[TradeRecord]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        totals[trade.date.isoformat()] += trade.total_cost
    return dict(sorted(totals.items()))
