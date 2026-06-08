from __future__ import annotations

from .models import TradeAttemptRecord, TradeRecord


def build_execution_quality_analysis(
    trades: list[TradeRecord],
    attempts: list[TradeAttemptRecord],
) -> dict[str, object]:
    total_orders = len(trades) + len(attempts)
    rows: list[dict[str, str | int | float]] = []

    for side in ("ALL", "BUY", "SELL"):
        side_trades = trades if side == "ALL" else [trade for trade in trades if trade.side == side]
        side_attempts = attempts if side == "ALL" else [attempt for attempt in attempts if attempt.side == side]
        rows.append(_execution_quality_row("side", side, side_trades, side_attempts))

    for reason in sorted({attempt.reason for attempt in attempts}):
        reason_attempts = [attempt for attempt in attempts if attempt.reason == reason]
        rows.append(_execution_quality_row("rejection_reason", reason, [], reason_attempts))

    constraint_categories = sorted({_constraint_category(attempt.reason) for attempt in attempts})
    for category in constraint_categories:
        category_attempts = [
            attempt
            for attempt in attempts
            if _constraint_category(attempt.reason) == category
        ]
        rows.append(_execution_quality_row("constraint_category", category, [], category_attempts))

    for attempt_date in sorted({attempt.date for attempt in attempts}):
        date_attempts = [attempt for attempt in attempts if attempt.date == attempt_date]
        rows.append(_execution_quality_row("daily_constraint", attempt_date.isoformat(), [], date_attempts))

    filled_orders = len(trades)
    rejected_orders = len(attempts)
    filled_gross_value = sum(trade.gross_value for trade in trades)
    total_cost = sum(trade.total_cost for trade in trades)
    constraint_counts = _constraint_category_counts(attempts)
    daily_constraint_summary = _daily_constraint_summary(attempts)
    market_constraint_orders = sum(
        count
        for category, count in constraint_counts.items()
        if category in {"suspension", "limit", "tradability", "capacity", "t_plus_one"}
    )
    summary = {
        "orders": total_orders,
        "filled_orders": filled_orders,
        "rejected_orders": rejected_orders,
        "fill_rate": 0.0 if total_orders == 0 else filled_orders / total_orders,
        "filled_shares": sum(trade.shares for trade in trades),
        "rejected_target_shares": sum(attempt.target_shares for attempt in attempts),
        "filled_gross_value": filled_gross_value,
        "total_cost": total_cost,
        "cost_bps": 0.0 if filled_gross_value == 0 else total_cost / filled_gross_value * 10_000,
        "rejection_reasons": len({attempt.reason for attempt in attempts}),
        "constraint_categories": len(constraint_counts),
        "constraint_category_counts": constraint_counts,
        "dominant_constraint_category": _dominant_constraint_category(constraint_counts),
        "market_constraint_orders": market_constraint_orders,
        "market_constraint_rate": 0.0 if rejected_orders == 0 else market_constraint_orders / rejected_orders,
        "constraint_days": daily_constraint_summary["constraint_days"],
        "worst_constraint_date": daily_constraint_summary["worst_constraint_date"],
        "worst_constraint_rejected_orders": daily_constraint_summary["worst_constraint_rejected_orders"],
        "worst_constraint_rejected_target_shares": daily_constraint_summary["worst_constraint_rejected_target_shares"],
        "worst_constraint_dominant_category": daily_constraint_summary["worst_constraint_dominant_category"],
    }
    return {"rows": rows, "summary": summary}


def _execution_quality_row(
    category: str,
    key: str,
    trades: list[TradeRecord],
    attempts: list[TradeAttemptRecord],
) -> dict[str, str | int | float]:
    orders = len(trades) + len(attempts)
    gross_value = sum(trade.gross_value for trade in trades)
    total_cost = sum(trade.total_cost for trade in trades)
    return {
        "category": category,
        "key": key,
        "orders": orders,
        "filled_orders": len(trades),
        "rejected_orders": len(attempts),
        "fill_rate": 0.0 if orders == 0 else len(trades) / orders,
        "filled_shares": sum(trade.shares for trade in trades),
        "rejected_target_shares": sum(attempt.target_shares for attempt in attempts),
        "gross_value": gross_value,
        "total_cost": total_cost,
        "cost_bps": 0.0 if gross_value == 0 else total_cost / gross_value * 10_000,
        "average_trade_value": 0.0 if not trades else gross_value / len(trades),
    }


def _constraint_category_counts(attempts: list[TradeAttemptRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        category = _constraint_category(attempt.reason)
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _daily_constraint_summary(attempts: list[TradeAttemptRecord]) -> dict[str, str | int]:
    if not attempts:
        return {
            "constraint_days": 0,
            "worst_constraint_date": "",
            "worst_constraint_rejected_orders": 0,
            "worst_constraint_rejected_target_shares": 0,
            "worst_constraint_dominant_category": "",
        }
    dates = sorted({attempt.date for attempt in attempts})
    daily_rows: list[tuple[str, int, int, str]] = []
    for attempt_date in dates:
        date_attempts = [attempt for attempt in attempts if attempt.date == attempt_date]
        category_counts = _constraint_category_counts(date_attempts)
        daily_rows.append(
            (
                attempt_date.isoformat(),
                len(date_attempts),
                sum(attempt.target_shares for attempt in date_attempts),
                _dominant_constraint_category(category_counts),
            )
        )
    worst_day = max(
        daily_rows,
        key=lambda row: (row[1], row[2], row[0]),
    )
    return {
        "constraint_days": len(daily_rows),
        "worst_constraint_date": worst_day[0],
        "worst_constraint_rejected_orders": worst_day[1],
        "worst_constraint_rejected_target_shares": worst_day[2],
        "worst_constraint_dominant_category": worst_day[3],
    }


def _dominant_constraint_category(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def _constraint_category(reason: str) -> str:
    normalized = reason.lower()
    if "t+1" in normalized or "t_plus" in normalized or "same_day" in normalized:
        return "t_plus_one"
    if "suspend" in normalized or "停牌" in normalized:
        return "suspension"
    if "limit_up" in normalized or "limit_down" in normalized or "涨停" in normalized or "跌停" in normalized:
        return "limit"
    if "volume" in normalized or "participation" in normalized or "capacity" in normalized:
        return "capacity"
    if "cash" in normalized or "insufficient" in normalized:
        return "cash"
    if "lot" in normalized or "odd" in normalized:
        return "lot"
    if "tradable" in normalized or "buyable" in normalized or "sellable" in normalized:
        return "tradability"
    return "other"
