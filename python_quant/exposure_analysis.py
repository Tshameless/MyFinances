from __future__ import annotations

from datetime import date

from .models import PositionPoint


def build_exposure_analysis(positions: list[PositionPoint]) -> dict[str, object]:
    if not positions:
        return {"rows": [], "summary": {}}

    by_date: dict[date, list[PositionPoint]] = {}
    for point in positions:
        by_date.setdefault(point.date, []).append(point)

    rows: list[dict[str, str | int | float]] = []
    for position_date, date_positions in sorted(by_date.items()):
        stock_positions = [
            point
            for point in date_positions
            if point.symbol != "CASH" and point.shares > 0 and point.market_value > 0
        ]
        cash_weight = sum(point.weight for point in date_positions if point.symbol == "CASH")
        stock_weight = sum(point.weight for point in stock_positions)
        largest_position_weight = max((point.weight for point in stock_positions), default=0.0)
        hhi_concentration = sum(point.weight**2 for point in stock_positions)
        largest_risk_contribution_symbol, largest_risk_contribution_share = _largest_risk_contribution(
            stock_positions,
            hhi_concentration,
        )
        rows.append(
            {
                "date": position_date.isoformat(),
                "holding_count": len(stock_positions),
                "stock_weight": stock_weight,
                "cash_weight": cash_weight,
                "largest_position_weight": largest_position_weight,
                "hhi_concentration": hhi_concentration,
                "effective_position_count": 0.0 if hhi_concentration == 0 else 1.0 / hhi_concentration,
                "largest_risk_contribution_symbol": largest_risk_contribution_symbol,
                "largest_risk_contribution_share": largest_risk_contribution_share,
                "total_equity": max((point.total_equity for point in date_positions), default=0.0),
            }
        )

    stock_weights = [float(row["stock_weight"]) for row in rows]
    cash_weights = [float(row["cash_weight"]) for row in rows]
    concentration_values = [float(row["hhi_concentration"]) for row in rows]
    effective_position_counts = [float(row["effective_position_count"]) for row in rows]
    largest_risk_contribution_rows = [
        row
        for row in rows
        if float(row["largest_risk_contribution_share"]) > 0.0
    ]
    max_risk_contribution_row = (
        None
        if not largest_risk_contribution_rows
        else max(
            largest_risk_contribution_rows,
            key=lambda row: (
                float(row["largest_risk_contribution_share"]),
                str(row["largest_risk_contribution_symbol"]),
            ),
        )
    )
    summary = {
        "periods": len(rows),
        "average_holding_count": sum(int(row["holding_count"]) for row in rows) / len(rows),
        "average_stock_weight": sum(stock_weights) / len(stock_weights),
        "average_cash_weight": sum(cash_weights) / len(cash_weights),
        "max_cash_weight": max(cash_weights),
        "max_largest_position_weight": max(float(row["largest_position_weight"]) for row in rows),
        "average_hhi_concentration": sum(concentration_values) / len(concentration_values),
        "max_hhi_concentration": max(concentration_values),
        "average_effective_position_count": sum(effective_position_counts) / len(effective_position_counts),
        "min_effective_position_count": min(effective_position_counts),
        "max_largest_risk_contribution_share": (
            0.0
            if max_risk_contribution_row is None
            else float(max_risk_contribution_row["largest_risk_contribution_share"])
        ),
        "max_largest_risk_contribution_symbol": (
            ""
            if max_risk_contribution_row is None
            else str(max_risk_contribution_row["largest_risk_contribution_symbol"])
        ),
    }
    return {"rows": rows, "summary": summary}


def _largest_risk_contribution(
    stock_positions: list[PositionPoint],
    hhi_concentration: float,
) -> tuple[str, float]:
    if not stock_positions or hhi_concentration == 0.0:
        return "", 0.0
    largest = max(stock_positions, key=lambda point: (point.weight**2, point.symbol))
    return largest.symbol, largest.weight**2 / hhi_concentration


def build_group_exposure_analysis(
    positions: list[PositionPoint],
    symbol_groups: dict[str, str],
) -> dict[str, object]:
    if not positions:
        return {"rows": [], "summary": {"has_group_mapping": bool(symbol_groups)}}

    by_date: dict[date, list[PositionPoint]] = {}
    for point in positions:
        by_date.setdefault(point.date, []).append(point)

    rows: list[dict[str, str | int | float]] = []
    for position_date, date_positions in sorted(by_date.items()):
        group_weights: dict[str, float] = {}
        group_market_values: dict[str, float] = {}
        group_counts: dict[str, int] = {}
        for point in date_positions:
            if point.symbol == "CASH" or point.shares <= 0 or point.market_value <= 0:
                continue
            group_name = symbol_groups.get(point.symbol, "UNMAPPED")
            group_weights[group_name] = group_weights.get(group_name, 0.0) + point.weight
            group_market_values[group_name] = group_market_values.get(group_name, 0.0) + point.market_value
            group_counts[group_name] = group_counts.get(group_name, 0) + 1
        group_hhi_concentration = sum(weight**2 for weight in group_weights.values())
        for group_name in sorted(group_weights):
            weight = group_weights[group_name]
            rows.append(
                {
                    "date": position_date.isoformat(),
                    "group": group_name,
                    "holding_count": group_counts[group_name],
                    "weight": weight,
                    "market_value": group_market_values[group_name],
                    "risk_contribution_share": (
                        0.0
                        if group_hhi_concentration == 0.0
                        else weight**2 / group_hhi_concentration
                    ),
                }
            )

    if not rows:
        return {"rows": [], "summary": {"has_group_mapping": bool(symbol_groups)}}

    by_date_rows: dict[str, list[dict[str, str | int | float]]] = {}
    for row in rows:
        by_date_rows.setdefault(str(row["date"]), []).append(row)
    largest_group_weights = [
        max(float(row["weight"]) for row in date_rows)
        for date_rows in by_date_rows.values()
    ]
    group_hhi_values = [
        sum(float(row["weight"]) ** 2 for row in date_rows)
        for date_rows in by_date_rows.values()
    ]
    effective_group_counts = [
        0.0 if hhi_value == 0.0 else 1.0 / hhi_value
        for hhi_value in group_hhi_values
    ]
    unmapped_weights = [
        sum(float(row["weight"]) for row in date_rows if row["group"] == "UNMAPPED")
        for date_rows in by_date_rows.values()
    ]
    max_group_risk_contribution_row = max(
        rows,
        key=lambda row: (float(row["risk_contribution_share"]), str(row["group"])),
    )
    summary = {
        "has_group_mapping": bool(symbol_groups),
        "periods": len(by_date_rows),
        "groups": sorted({str(row["group"]) for row in rows}),
        "average_group_count": sum(len(date_rows) for date_rows in by_date_rows.values()) / len(by_date_rows),
        "average_largest_group_weight": sum(largest_group_weights) / len(largest_group_weights),
        "max_largest_group_weight": max(largest_group_weights),
        "average_group_hhi_concentration": sum(group_hhi_values) / len(group_hhi_values),
        "max_group_hhi_concentration": max(group_hhi_values),
        "average_effective_group_count": sum(effective_group_counts) / len(effective_group_counts),
        "min_effective_group_count": min(effective_group_counts),
        "average_unmapped_weight": sum(unmapped_weights) / len(unmapped_weights),
        "max_unmapped_weight": max(unmapped_weights),
        "max_group_risk_contribution_group": str(max_group_risk_contribution_row["group"]),
        "max_group_risk_contribution_share": float(max_group_risk_contribution_row["risk_contribution_share"]),
    }
    return {"rows": rows, "summary": summary}
