from __future__ import annotations

from .models import EquityPoint, PositionPoint, PriceBar, TradeRecord


def build_return_attribution_analysis(
    *,
    equity_curve: list[EquityPoint],
    positions: list[PositionPoint],
    price_bars: list[PriceBar] | None,
    trades: list[TradeRecord],
    symbol_groups: dict[str, str] | None = None,
    price_field: str = "adjusted_close",
) -> dict[str, object]:
    if len(equity_curve) < 2 or not positions:
        return {"rows": [], "summary": {"periods": 0}}

    symbol_groups = symbol_groups or {}
    curve_by_date = {point.date: point for point in equity_curve}
    sorted_dates = sorted(curve_by_date)
    positions_by_date: dict[object, list[PositionPoint]] = {}
    for point in positions:
        positions_by_date.setdefault(point.date, []).append(point)
    prices_by_key = _price_lookup(price_bars, positions, price_field)
    costs_by_date: dict[object, float] = {}
    for trade in trades:
        costs_by_date[trade.date] = costs_by_date.get(trade.date, 0.0) + trade.total_cost

    rows: list[dict[str, str | float]] = []
    residual_by_date: dict[str, float] = {}
    cost_drag_by_date: dict[str, float] = {}
    for previous_date, current_date in zip(sorted_dates, sorted_dates[1:]):
        previous_positions = [
            point
            for point in positions_by_date.get(previous_date, [])
            if point.symbol != "CASH" and point.market_value > 0 and point.weight > 0
        ]
        daily_contribution = 0.0
        for point in previous_positions:
            previous_price = prices_by_key.get((previous_date, point.symbol), point.price)
            current_price = prices_by_key.get((current_date, point.symbol))
            if previous_price is None or current_price is None or previous_price <= 0:
                continue
            asset_return = current_price / previous_price - 1.0
            contribution = point.weight * asset_return
            daily_contribution += contribution
            rows.append(
                {
                    "date": current_date.isoformat(),
                    "previous_date": previous_date.isoformat(),
                    "symbol": point.symbol,
                    "group": symbol_groups.get(point.symbol, "UNMAPPED"),
                    "previous_weight": point.weight,
                    "asset_return": asset_return,
                    "return_contribution": contribution,
                }
            )
        portfolio_return = curve_by_date[current_date].daily_return
        previous_equity = _previous_equity(curve_by_date[current_date])
        cost_drag = 0.0 if previous_equity == 0 else costs_by_date.get(current_date, 0.0) / previous_equity
        residual_by_date[current_date.isoformat()] = portfolio_return - daily_contribution
        cost_drag_by_date[current_date.isoformat()] = cost_drag

    summary = _build_attribution_summary(
        rows,
        residual_by_date=residual_by_date,
        cost_drag_by_date=cost_drag_by_date,
    )
    return {"rows": rows, "summary": summary}


def _price_lookup(
    price_bars: list[PriceBar] | None,
    positions: list[PositionPoint],
    price_field: str,
) -> dict[tuple[object, str], float]:
    if price_bars is not None:
        return {
            (bar.date, bar.symbol): _price_for_bar(bar, price_field)
            for bar in price_bars
        }
    return {
        (point.date, point.symbol): point.price
        for point in positions
        if point.symbol != "CASH"
    }


def _price_for_bar(bar: PriceBar, price_field: str) -> float:
    if price_field == "close":
        return bar.close
    return bar.adjusted_close if bar.adjusted_close is not None else bar.close


def _previous_equity(point: EquityPoint) -> float:
    return point.equity / (1.0 + point.daily_return)


def _build_attribution_summary(
    rows: list[dict[str, str | float]],
    *,
    residual_by_date: dict[str, float],
    cost_drag_by_date: dict[str, float],
) -> dict[str, object]:
    symbol_contributions: dict[str, float] = {}
    group_contributions: dict[str, float] = {}
    for row in rows:
        symbol = str(row["symbol"])
        group = str(row["group"])
        contribution = float(row["return_contribution"])
        symbol_contributions[symbol] = symbol_contributions.get(symbol, 0.0) + contribution
        group_contributions[group] = group_contributions.get(group, 0.0) + contribution

    return {
        "periods": len(residual_by_date),
        "total_attributed_return": sum(symbol_contributions.values()),
        "total_residual_return": sum(residual_by_date.values()),
        "total_cost_drag": sum(cost_drag_by_date.values()),
        "top_symbol_contributors": _top_contributors(symbol_contributions),
        "bottom_symbol_contributors": _bottom_contributors(symbol_contributions),
        "group_contributions": dict(sorted(group_contributions.items())),
        "residual_by_date": residual_by_date,
        "cost_drag_by_date": cost_drag_by_date,
    }


def _top_contributors(values: dict[str, float]) -> list[dict[str, str | float]]:
    return [
        {"name": name, "contribution": contribution}
        for name, contribution in sorted(values.items(), key=lambda item: item[1], reverse=True)[:10]
    ]


def _bottom_contributors(values: dict[str, float]) -> list[dict[str, str | float]]:
    return [
        {"name": name, "contribution": contribution}
        for name, contribution in sorted(values.items(), key=lambda item: item[1])[:10]
    ]
