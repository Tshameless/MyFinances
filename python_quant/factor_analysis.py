from __future__ import annotations

from math import sqrt

from .models import FactorScoreRecord, PositionPoint, PriceBar


def build_factor_ic_analysis(
    factor_scores: list[FactorScoreRecord],
    positions: list[PositionPoint],
    price_bars: list[PriceBar] | None = None,
    price_field: str = "adjusted_close",
) -> dict[str, object]:
    if not factor_scores or (not positions and not price_bars):
        return {"rows": [], "summary": {}}

    dates = sorted({record.date for record in factor_scores})
    next_date_by_date = {
        current_date: dates[index + 1]
        for index, current_date in enumerate(dates[:-1])
    }
    rows: list[dict[str, str | float | int]] = []
    factor_names = ("momentum", "mean_reversion", "low_volatility", "total_score")

    for current_date, next_date in next_date_by_date.items():
        current_records = [record for record in factor_scores if record.date == current_date]
        returns_by_symbol = _next_period_returns(
            positions,
            current_date,
            next_date,
            price_bars=price_bars,
            price_field=price_field,
        )
        if len(returns_by_symbol) < 2:
            continue
        for factor_name in factor_names:
            paired = [
                (float(getattr(record, factor_name)), returns_by_symbol[record.symbol])
                for record in current_records
                if record.symbol in returns_by_symbol
            ]
            if len(paired) < 2:
                continue
            factor_values = [item[0] for item in paired]
            forward_returns = [item[1] for item in paired]
            rows.append(
                {
                    "date": current_date.isoformat(),
                    "next_date": next_date.isoformat(),
                    "factor": factor_name,
                    "ic": _correlation(factor_values, forward_returns),
                    "rank_ic": _correlation(_ranks(factor_values), _ranks(forward_returns)),
                    "sample_size": len(paired),
                }
            )

    summary: dict[str, dict[str, float | int]] = {}
    for factor_name in factor_names:
        factor_rows = [row for row in rows if row["factor"] == factor_name]
        if not factor_rows:
            continue
        ic_values = [float(row["ic"]) for row in factor_rows]
        rank_ic_values = [float(row["rank_ic"]) for row in factor_rows]
        ic_std = _sample_std(ic_values)
        rank_ic_std = _sample_std(rank_ic_values)
        mean_ic = sum(ic_values) / len(ic_values)
        mean_rank_ic = sum(rank_ic_values) / len(rank_ic_values)
        summary[factor_name] = {
            "periods": len(factor_rows),
            "mean_ic": mean_ic,
            "median_ic": _median(ic_values),
            "ic_std": ic_std,
            "ic_ir": 0.0 if ic_std == 0.0 else mean_ic / ic_std,
            "ic_t_stat": 0.0 if ic_std == 0.0 else mean_ic / (ic_std / sqrt(len(ic_values))),
            "mean_rank_ic": mean_rank_ic,
            "median_rank_ic": _median(rank_ic_values),
            "rank_ic_std": rank_ic_std,
            "rank_ic_ir": 0.0 if rank_ic_std == 0.0 else mean_rank_ic / rank_ic_std,
            "rank_ic_t_stat": 0.0 if rank_ic_std == 0.0 else mean_rank_ic / (rank_ic_std / sqrt(len(rank_ic_values))),
            "positive_ic_rate": sum(1 for value in ic_values if value > 0) / len(ic_values),
            "negative_ic_rate": sum(1 for value in ic_values if value < 0) / len(ic_values),
        }
    return {"rows": rows, "summary": summary}


def build_factor_group_return_analysis(
    factor_scores: list[FactorScoreRecord],
    positions: list[PositionPoint],
    *,
    group_count: int = 5,
    price_bars: list[PriceBar] | None = None,
    price_field: str = "adjusted_close",
) -> dict[str, object]:
    if group_count < 2:
        raise ValueError("group_count must be at least 2.")
    if not factor_scores or (not positions and not price_bars):
        return {"rows": [], "summary": {"group_count": group_count}}

    dates = sorted({record.date for record in factor_scores})
    next_date_by_date = {
        current_date: dates[index + 1]
        for index, current_date in enumerate(dates[:-1])
    }
    factor_names = ("momentum", "mean_reversion", "low_volatility", "total_score")
    rows: list[dict[str, str | float | int]] = []

    for current_date, next_date in next_date_by_date.items():
        current_records = [record for record in factor_scores if record.date == current_date]
        returns_by_symbol = _next_period_returns(
            positions,
            current_date,
            next_date,
            price_bars=price_bars,
            price_field=price_field,
        )
        if len(returns_by_symbol) < 2:
            continue
        for factor_name in factor_names:
            paired = [
                (record.symbol, float(getattr(record, factor_name)), returns_by_symbol[record.symbol])
                for record in current_records
                if record.symbol in returns_by_symbol
            ]
            if len(paired) < 2:
                continue
            for group_index, group_items in enumerate(_factor_groups(paired, group_count), start=1):
                if not group_items:
                    continue
                forward_returns = [item[2] for item in group_items]
                factor_values = [item[1] for item in group_items]
                rows.append(
                    {
                        "date": current_date.isoformat(),
                        "next_date": next_date.isoformat(),
                        "factor": factor_name,
                        "group": group_index,
                        "group_count": group_count,
                        "sample_size": len(group_items),
                        "average_factor_value": sum(factor_values) / len(factor_values),
                        "average_forward_return": sum(forward_returns) / len(forward_returns),
                    }
                )

    return {
        "rows": rows,
        "summary": _factor_group_summary(rows, factor_names, group_count),
    }


def build_factor_decay_analysis(factor_scores: list[FactorScoreRecord]) -> dict[str, object]:
    if not factor_scores:
        return {"rows": [], "summary": {}}

    dates = sorted({record.date for record in factor_scores})
    factor_names = ("momentum", "mean_reversion", "low_volatility", "total_score")
    rows: list[dict[str, str | float | int]] = []

    for current_date, next_date in zip(dates, dates[1:], strict=False):
        current_by_symbol = {
            record.symbol: record
            for record in factor_scores
            if record.date == current_date
        }
        next_by_symbol = {
            record.symbol: record
            for record in factor_scores
            if record.date == next_date
        }
        common_symbols = sorted(set(current_by_symbol) & set(next_by_symbol))
        if len(common_symbols) < 2:
            continue
        selected_symbols = {
            symbol
            for symbol, record in current_by_symbol.items()
            if record.selected
        }
        next_selected_symbols = {
            symbol
            for symbol, record in next_by_symbol.items()
            if record.selected
        }
        selected_retention_rate = (
            0.0
            if not selected_symbols
            else len(selected_symbols & next_selected_symbols) / len(selected_symbols)
        )
        selected_turnover_rate = 1.0 - selected_retention_rate
        for factor_name in factor_names:
            current_values = [float(getattr(current_by_symbol[symbol], factor_name)) for symbol in common_symbols]
            next_values = [float(getattr(next_by_symbol[symbol], factor_name)) for symbol in common_symbols]
            rows.append(
                {
                    "date": current_date.isoformat(),
                    "next_date": next_date.isoformat(),
                    "factor": factor_name,
                    "score_correlation": _correlation(current_values, next_values),
                    "rank_correlation": _correlation(_ranks(current_values), _ranks(next_values)),
                    "sample_size": len(common_symbols),
                    "selected_count": len(selected_symbols),
                    "selected_retention_rate": selected_retention_rate,
                    "selected_turnover_rate": selected_turnover_rate,
                }
            )

    summary: dict[str, object] = {}
    for factor_name in factor_names:
        factor_rows = [row for row in rows if row["factor"] == factor_name]
        if not factor_rows:
            continue
        score_correlations = [float(row["score_correlation"]) for row in factor_rows]
        rank_correlations = [float(row["rank_correlation"]) for row in factor_rows]
        retention_rates = [float(row["selected_retention_rate"]) for row in factor_rows]
        turnover_rates = [float(row["selected_turnover_rate"]) for row in factor_rows]
        summary[factor_name] = {
            "periods": len(factor_rows),
            "average_score_correlation": sum(score_correlations) / len(score_correlations),
            "average_rank_correlation": sum(rank_correlations) / len(rank_correlations),
            "min_score_correlation": min(score_correlations),
            "min_rank_correlation": min(rank_correlations),
            "average_selected_retention_rate": sum(retention_rates) / len(retention_rates),
            "average_selected_turnover_rate": sum(turnover_rates) / len(turnover_rates),
        }
    return {"rows": rows, "summary": summary}


def build_factor_correlation_analysis(factor_scores: list[FactorScoreRecord]) -> dict[str, object]:
    if not factor_scores:
        return {"rows": [], "summary": {}}

    factor_names = ("momentum", "mean_reversion", "low_volatility", "total_score")
    rows: list[dict[str, str | float | int]] = []
    dates = sorted({record.date for record in factor_scores})

    for current_date in dates:
        records = [record for record in factor_scores if record.date == current_date]
        if len(records) < 2:
            continue
        values_by_factor = {
            factor_name: [float(getattr(record, factor_name)) for record in records]
            for factor_name in factor_names
        }
        for left_factor in factor_names:
            for right_factor in factor_names:
                rows.append(
                    {
                        "date": current_date.isoformat(),
                        "factor": left_factor,
                        "compared_factor": right_factor,
                        "correlation": _correlation(
                            values_by_factor[left_factor],
                            values_by_factor[right_factor],
                        ),
                        "rank_correlation": _correlation(
                            _ranks(values_by_factor[left_factor]),
                            _ranks(values_by_factor[right_factor]),
                        ),
                        "sample_size": len(records),
                    }
                )

    summary: dict[str, object] = {"factor_count": len(factor_names)}
    pair_correlations: list[tuple[str, str, float, float]] = []
    for left_index, left_factor in enumerate(factor_names):
        for right_factor in factor_names[left_index + 1:]:
            pair_rows = [
                row
                for row in rows
                if row["factor"] == left_factor and row["compared_factor"] == right_factor
            ]
            if not pair_rows:
                continue
            correlations = [float(row["correlation"]) for row in pair_rows]
            rank_correlations = [float(row["rank_correlation"]) for row in pair_rows]
            average_correlation = sum(correlations) / len(correlations)
            average_rank_correlation = sum(rank_correlations) / len(rank_correlations)
            pair_key = f"{left_factor}__{right_factor}"
            pair_summary = {
                "periods": len(pair_rows),
                "average_correlation": average_correlation,
                "average_rank_correlation": average_rank_correlation,
                "average_abs_correlation": sum(abs(value) for value in correlations) / len(correlations),
                "max_abs_correlation": max(abs(value) for value in correlations),
            }
            summary[pair_key] = pair_summary
            pair_correlations.append((left_factor, right_factor, average_correlation, average_rank_correlation))

    if pair_correlations:
        strongest = max(pair_correlations, key=lambda item: abs(item[2]))
        strongest_rank = max(pair_correlations, key=lambda item: abs(item[3]))
        summary["strongest_pair"] = {
            "factor": strongest[0],
            "compared_factor": strongest[1],
            "average_correlation": strongest[2],
        }
        summary["strongest_rank_pair"] = {
            "factor": strongest_rank[0],
            "compared_factor": strongest_rank[1],
            "average_rank_correlation": strongest_rank[3],
        }

    return {"rows": rows, "summary": summary}


def _factor_groups(
    paired: list[tuple[str, float, float]],
    group_count: int,
) -> list[list[tuple[str, float, float]]]:
    ordered = sorted(paired, key=lambda item: item[1])
    total = len(ordered)
    groups: list[list[tuple[str, float, float]]] = []
    for group_index in range(group_count):
        start = group_index * total // group_count
        end = (group_index + 1) * total // group_count
        groups.append(ordered[start:end])
    return groups


def _factor_group_summary(
    rows: list[dict[str, str | float | int]],
    factor_names: tuple[str, ...],
    group_count: int,
) -> dict[str, object]:
    summary: dict[str, object] = {"group_count": group_count}
    for factor_name in factor_names:
        factor_rows = [row for row in rows if row["factor"] == factor_name]
        if not factor_rows:
            continue
        average_by_group = {}
        for group_index in range(1, group_count + 1):
            group_rows = [row for row in factor_rows if row["group"] == group_index]
            if not group_rows:
                continue
            returns = [float(row["average_forward_return"]) for row in group_rows]
            average_by_group[str(group_index)] = sum(returns) / len(returns)
        if not average_by_group:
            continue
        low_return = average_by_group.get("1")
        high_return = average_by_group.get(str(group_count))
        values_in_order = [
            average_by_group[str(group_index)]
            for group_index in range(1, group_count + 1)
            if str(group_index) in average_by_group
        ]
        monotonic_up = all(
            left <= right for left, right in zip(values_in_order, values_in_order[1:], strict=False)
        )
        monotonic_down = all(
            left >= right for left, right in zip(values_in_order, values_in_order[1:], strict=False)
        )
        summary[factor_name] = {
            "periods": len({row["date"] for row in factor_rows}),
            "average_by_group": average_by_group,
            "high_minus_low": (
                None
                if low_return is None or high_return is None
                else high_return - low_return
            ),
            "is_monotonic": monotonic_up or monotonic_down,
            "direction": (
                "higher_is_better"
                if monotonic_up
                else "lower_is_better"
                if monotonic_down
                else "mixed"
            ),
        }
    return summary


def _next_period_returns(
    positions: list[PositionPoint],
    current_date,
    next_date,
    *,
    price_bars: list[PriceBar] | None = None,
    price_field: str = "adjusted_close",
) -> dict[str, float]:
    if price_bars is not None:
        by_key = {
            (bar.date, bar.symbol): _analysis_price_for_bar(bar, price_field)
            for bar in price_bars
        }
        return _returns_from_price_lookup(by_key, current_date, next_date)

    by_key = {
        (point.date, point.symbol): point.price
        for point in positions
        if point.symbol != "CASH"
    }
    return _returns_from_price_lookup(by_key, current_date, next_date)


def _returns_from_price_lookup(
    by_key,
    current_date,
    next_date,
) -> dict[str, float]:
    symbols = {
        symbol
        for trading_date, symbol in by_key
        if trading_date in {current_date, next_date}
    }
    returns = {}
    for symbol in symbols:
        current_price = by_key.get((current_date, symbol))
        next_price = by_key.get((next_date, symbol))
        if current_price and next_price:
            returns[symbol] = next_price / current_price - 1.0
    return returns


def _analysis_price_for_bar(bar: PriceBar, price_field: str) -> float:
    if price_field == "close":
        return bar.close
    return bar.adjusted_close if bar.adjusted_close is not None else bar.close


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = sqrt(left_var * right_var)
    return 0.0 if denominator == 0 else numerator / denominator


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = sum(values) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
    return sqrt(max(variance, 0.0))


def _ranks(values: list[float]) -> list[float]:
    sorted_pairs = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    for rank, (_value, index) in enumerate(sorted_pairs, start=1):
        ranks[index] = float(rank)
    return ranks
