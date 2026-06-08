from __future__ import annotations

from datetime import date


def build_walk_forward_windows(
    dates: list[date],
    *,
    window_size: int,
    step_size: int,
) -> list[tuple[date, date]]:
    if window_size <= 0:
        raise ValueError("walk-forward window size must be greater than 0.")
    if step_size <= 0:
        raise ValueError("walk-forward step size must be greater than 0.")
    unique_dates = sorted(set(dates))
    if len(unique_dates) < window_size:
        return []

    windows = []
    start_index = 0
    while start_index + window_size <= len(unique_dates):
        end_index = start_index + window_size - 1
        windows.append((unique_dates[start_index], unique_dates[end_index]))
        start_index += step_size
    return windows


def build_walk_forward_train_test_windows(
    dates: list[date],
    *,
    train_size: int,
    test_size: int,
    step_size: int,
) -> list[dict[str, date | str]]:
    if train_size <= 0:
        raise ValueError("walk-forward train size must be greater than 0.")
    if test_size <= 0:
        raise ValueError("walk-forward test size must be greater than 0.")
    if step_size <= 0:
        raise ValueError("walk-forward step size must be greater than 0.")
    unique_dates = sorted(set(dates))
    total_size = train_size + test_size
    if len(unique_dates) < total_size:
        return []

    windows: list[dict[str, date | str]] = []
    start_index = 0
    window_number = 1
    while start_index + total_size <= len(unique_dates):
        train_start = unique_dates[start_index]
        train_end = unique_dates[start_index + train_size - 1]
        test_start = unique_dates[start_index + train_size]
        test_end = unique_dates[start_index + total_size - 1]
        windows.append(
            {
                "window_id": f"window_{window_number:03d}",
                "train_start_date": train_start,
                "train_end_date": train_end,
                "test_start_date": test_start,
                "test_end_date": test_end,
            }
        )
        start_index += step_size
        window_number += 1
    return windows


def build_walk_forward_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {"rows": [], "summary": {"windows": 0}}

    annualized_returns = [_float_value(row, "annualized_return") for row in rows]
    total_returns = [_float_value(row, "total_return") for row in rows]
    sharpe_values = [_float_value(row, "sharpe") for row in rows]
    drawdowns = [_float_value(row, "max_drawdown") for row in rows]
    positive_windows = sum(1 for value in total_returns if value > 0)
    summary = {
        "windows": len(rows),
        "positive_windows": positive_windows,
        "positive_window_rate": positive_windows / len(rows),
        "average_total_return": sum(total_returns) / len(total_returns),
        "average_annualized_return": sum(annualized_returns) / len(annualized_returns),
        "average_sharpe": sum(sharpe_values) / len(sharpe_values),
        "worst_max_drawdown": min(drawdowns),
        "best_window_id": max(rows, key=lambda row: _float_value(row, "annualized_return")).get("window_id"),
        "worst_window_id": min(rows, key=lambda row: _float_value(row, "annualized_return")).get("window_id"),
    }
    return {"rows": rows, "summary": summary}


def build_walk_forward_optimization_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {"rows": [], "summary": {"windows": 0}}

    enriched_rows: list[dict[str, object]] = []
    for row in rows:
        train_return = _float_value(row, "train_annualized_return")
        test_return = _float_value(row, "test_annualized_return")
        degradation = train_return - test_return
        enriched = dict(row)
        enriched["train_test_annualized_gap"] = degradation
        enriched["test_to_train_efficiency"] = _test_to_train_efficiency(train_return, test_return)
        enriched["is_degraded_out_of_sample"] = degradation > 0.0
        enriched_rows.append(enriched)

    train_returns = [_float_value(row, "train_annualized_return") for row in enriched_rows]
    test_returns = [_float_value(row, "test_annualized_return") for row in enriched_rows]
    test_total_returns = [_float_value(row, "test_total_return") for row in rows]
    test_drawdowns = [_float_value(row, "test_max_drawdown") for row in rows]
    train_health_scores = [_float_value(row, "train_health_score") for row in rows]
    positive_test_windows = sum(1 for value in test_total_returns if value > 0)
    gate_passing_train_windows = sum(1 for row in enriched_rows if str(row.get("train_gate_status", "")).lower() == "pass")
    gaps = [_float_value(row, "train_test_annualized_gap") for row in enriched_rows]
    degraded_windows = sum(1 for value in gaps if value > 0.0)
    worst_degradation_row = max(enriched_rows, key=lambda row: _float_value(row, "train_test_annualized_gap"))
    parameter_stability = _selected_parameter_stability(enriched_rows)
    parameter_drift_counts = _parameter_drift_counts(enriched_rows)
    degraded_parameter_sets = _degraded_parameter_sets(enriched_rows)
    parameter_drift_rate = _numeric_object(parameter_stability["parameter_drift_rate"])
    summary = {
        "windows": len(enriched_rows),
        "selection_policy": "gate_pass_first_then_metric",
        "gate_passing_train_windows": gate_passing_train_windows,
        "gate_passing_train_window_rate": gate_passing_train_windows / len(enriched_rows),
        "positive_test_windows": positive_test_windows,
        "positive_test_window_rate": positive_test_windows / len(enriched_rows),
        "average_selected_train_health_score": sum(train_health_scores) / len(train_health_scores),
        "average_train_annualized_return": sum(train_returns) / len(train_returns),
        "average_test_annualized_return": sum(test_returns) / len(test_returns),
        "average_test_total_return": sum(test_total_returns) / len(test_total_returns),
        "worst_test_max_drawdown": min(test_drawdowns),
        "average_train_test_annualized_gap": sum(gaps) / len(gaps),
        "degraded_test_windows": degraded_windows,
        "degraded_test_window_rate": degraded_windows / len(enriched_rows),
        "worst_degradation_window_id": worst_degradation_row.get("window_id"),
        "worst_train_test_annualized_gap": _float_value(worst_degradation_row, "train_test_annualized_gap"),
        "best_test_window_id": max(enriched_rows, key=lambda row: _float_value(row, "test_annualized_return")).get("window_id"),
        "worst_test_window_id": min(enriched_rows, key=lambda row: _float_value(row, "test_annualized_return")).get("window_id"),
        "selected_parameter_sets": parameter_stability["selected_parameter_sets"],
        "selected_parameter_set_counts": parameter_stability["selected_parameter_set_counts"],
        "dominant_parameter_set": parameter_stability["dominant_parameter_set"],
        "dominant_parameter_set_rate": parameter_stability["dominant_parameter_set_rate"],
        "parameter_drift_count": parameter_stability["parameter_drift_count"],
        "parameter_drift_rate": parameter_stability["parameter_drift_rate"],
        "parameter_drift_counts": parameter_drift_counts,
        "most_drifting_parameter": _top_count_key(parameter_drift_counts),
        "degraded_parameter_sets": degraded_parameter_sets,
        "parameter_selection_counts": parameter_stability["parameter_selection_counts"],
        "oos_stability_grade": _oos_stability_grade(
            positive_test_window_rate=positive_test_windows / len(enriched_rows),
            degraded_test_window_rate=degraded_windows / len(enriched_rows),
            parameter_drift_rate=parameter_drift_rate,
        ),
        "overfit_risk": _overfit_risk_label(
            degraded_test_window_rate=degraded_windows / len(enriched_rows),
            average_efficiency=sum(
                _float_value(row, "test_to_train_efficiency")
                for row in enriched_rows
            ) / len(enriched_rows),
            parameter_drift_rate=parameter_drift_rate,
        ),
    }
    return {"rows": enriched_rows, "summary": summary}


def build_batch_stability_analysis(
    rows: list[dict[str, object]],
    *,
    rank_by: str,
) -> dict[str, object]:
    if not rows:
        return {"rows": [], "summary": {"rank_by": rank_by, "best_run_id": None}}

    scored_rows = []
    for row in rows:
        total_return = _float_value(row, "total_return")
        annualized_return = _float_value(row, "annualized_return")
        sharpe = _float_value(row, "sharpe")
        max_drawdown = abs(_float_value(row, "max_drawdown"))
        total_cost = _float_value(row, "total_cost")
        composite_score = (
            annualized_return * 0.40
            + total_return * 0.20
            + sharpe * 0.25
            - max_drawdown * 0.10
            - total_cost / 1_000_000.0 * 0.05
        )
        scored = dict(row)
        scored["composite_score"] = composite_score
        scored["risk_penalty"] = max_drawdown + total_cost / 1_000_000.0
        scored_rows.append(scored)

    ranked_by_metric = sorted(scored_rows, key=lambda item: _float_value(item, rank_by), reverse=True)
    best_row = ranked_by_metric[0]
    robust_region = _robust_region_rows(scored_rows, rank_by)
    robust_run_ids = {row.get("run_id") for row in robust_region}
    for row in scored_rows:
        row["is_robust_region"] = row.get("run_id") in robust_run_ids
    neighbors = _neighbor_rows(best_row, scored_rows)
    best_metric = _float_value(best_row, rank_by)
    neighbor_average = (
        sum(_float_value(row, rank_by) for row in neighbors) / len(neighbors)
        if neighbors
        else best_metric
    )
    isolation_gap = best_metric - neighbor_average
    isolation_threshold = max(abs(best_metric) * 0.25, 0.05)
    failed_gate_category_counts = _delimited_value_counts(scored_rows, "failed_gate_categories")
    failed_gate_name_counts = _delimited_value_counts(scored_rows, "failed_gate_names")
    parameter_sensitivity = _parameter_sensitivity(scored_rows, rank_by)
    best_parameter_values = _best_parameter_values(parameter_sensitivity)
    strongest_parameter = _strongest_parameter(parameter_sensitivity)
    parameter_recommendation_rationale = _parameter_recommendation_rationale(
        parameter_sensitivity,
        best_parameter_values,
    )
    _attach_parameter_value_context(scored_rows, parameter_sensitivity, rank_by)
    summary = {
        "rank_by": rank_by,
        "best_run_id": best_row.get("run_id"),
        "best_metric": best_metric,
        "neighbor_count": len(neighbors),
        "neighbor_average": neighbor_average,
        "isolation_gap": isolation_gap,
        "is_parameter_island": bool(neighbors and isolation_gap > isolation_threshold),
        "robust_region_threshold": _robust_region_threshold(_robust_region_candidate_rows(scored_rows), rank_by),
        "robust_region_run_count": len(robust_region),
        "robust_region_rate": len(robust_region) / len(scored_rows),
        "robust_region_average_metric": (
            0.0
            if not robust_region
            else sum(_float_value(row, rank_by) for row in robust_region) / len(robust_region)
        ),
        "robust_region_parameter_ranges": _parameter_ranges(robust_region),
        "gate_passing_run_count": sum(1 for row in scored_rows if str(row.get("gate_status", "")).lower() == "pass"),
        "gate_failing_run_count": sum(1 for row in scored_rows if str(row.get("gate_status", "")).lower() == "fail"),
        "failed_gate_category_counts": failed_gate_category_counts,
        "failed_gate_name_counts": failed_gate_name_counts,
        "parameter_sensitivity": parameter_sensitivity,
        "strongest_parameter": strongest_parameter,
        "best_parameter_values": best_parameter_values,
        "parameter_recommendation_rationale": parameter_recommendation_rationale,
        "parameter_recommendation_summary": _parameter_recommendation_summary(parameter_recommendation_rationale),
        "recommended_actions": _recommended_actions(failed_gate_category_counts, failed_gate_name_counts),
        "best_composite_run_id": max(
            scored_rows,
            key=lambda item: _float_value(item, "composite_score"),
        ).get("run_id"),
    }
    return {"rows": scored_rows, "summary": summary}


def _robust_region_rows(
    rows: list[dict[str, object]],
    rank_by: str,
) -> list[dict[str, object]]:
    candidate_rows = _robust_region_candidate_rows(rows)
    threshold = _robust_region_threshold(candidate_rows, rank_by)
    return [
        row
        for row in candidate_rows
        if _float_value(row, rank_by) >= threshold
    ]


def _robust_region_threshold(
    rows: list[dict[str, object]],
    rank_by: str,
) -> float:
    if not rows:
        return 0.0
    best_metric = max(_float_value(row, rank_by) for row in rows)
    return best_metric * 0.80 if best_metric > 0 else best_metric


def _robust_region_candidate_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    gated_rows = [row for row in rows if str(row.get("gate_status", "")).lower() == "pass"]
    return gated_rows if gated_rows else rows


def _parameter_ranges(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    param_keys = sorted({key for row in rows for key in row if _is_parameter_key(key)})
    ranges: dict[str, dict[str, object]] = {}
    for key in param_keys:
        values = [row[key] for row in rows if key in row]
        numeric_values = [
            float(value)
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if numeric_values and len(numeric_values) == len(values):
            ranges[key] = {
                "min": min(numeric_values),
                "max": max(numeric_values),
                "values": sorted(set(numeric_values)),
            }
        else:
            ranges[key] = {"values": sorted({str(value) for value in values})}
    return ranges


def _parameter_sensitivity(
    rows: list[dict[str, object]],
    rank_by: str,
) -> dict[str, dict[str, object]]:
    param_keys = sorted({key for row in rows for key in row if _is_parameter_key(key)})
    sensitivity: dict[str, dict[str, object]] = {}
    for key in param_keys:
        grouped_rows: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            if key not in row:
                continue
            value_key = str(row[key])
            grouped_rows.setdefault(value_key, []).append(row)
        if not grouped_rows:
            continue
        value_stats = {
            value: _parameter_value_stats(value_rows, rank_by)
            for value, value_rows in sorted(grouped_rows.items(), key=lambda item: item[0])
        }
        average_metrics = [
            _numeric_object(stats["average_metric"])
            for stats in value_stats.values()
        ]
        average_composites = [
            _numeric_object(stats["average_composite_score"])
            for stats in value_stats.values()
        ]
        sensitivity[key] = {
            "value_count": len(value_stats),
            "metric_range": max(average_metrics) - min(average_metrics) if average_metrics else 0.0,
            "composite_range": max(average_composites) - min(average_composites) if average_composites else 0.0,
            "best_value_by_metric": max(
                value_stats,
                key=lambda value: _numeric_object(value_stats[value]["average_metric"]),
            ),
            "best_value_by_composite": max(
                value_stats,
                key=lambda value: _numeric_object(value_stats[value]["average_composite_score"]),
            ),
            "values": value_stats,
        }
    return sensitivity


def _selected_parameter_stability(rows: list[dict[str, object]]) -> dict[str, object]:
    labels = [_parameter_set_label(row) for row in rows]
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    drift_count = sum(
        1
        for index in range(1, len(labels))
        if labels[index] != labels[index - 1]
    )
    dominant_label = max(counts, key=lambda label: counts[label]) if counts else ""
    parameter_selection_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        for key, value in row.items():
            if not _is_parameter_key(key):
                continue
            parameter_selection_counts.setdefault(key, {})
            value_key = str(value)
            parameter_selection_counts[key][value_key] = (
                parameter_selection_counts[key].get(value_key, 0) + 1
            )
    return {
        "selected_parameter_sets": len(counts),
        "selected_parameter_set_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "dominant_parameter_set": dominant_label,
        "dominant_parameter_set_rate": 0.0 if not rows else counts.get(dominant_label, 0) / len(rows),
        "parameter_drift_count": drift_count,
        "parameter_drift_rate": 0.0 if len(rows) <= 1 else drift_count / (len(rows) - 1),
        "parameter_selection_counts": {
            key: dict(sorted(values.items(), key=lambda item: (-item[1], item[0])))
            for key, values in sorted(parameter_selection_counts.items())
        },
    }


def _parameter_drift_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for previous, current in zip(rows, rows[1:], strict=False):
        parameter_keys = sorted(
            {
                key
                for row in (previous, current)
                for key in row
                if _is_parameter_key(key)
            }
        )
        for key in parameter_keys:
            if previous.get(key) != current.get(key):
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _degraded_parameter_sets(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    degraded_rows = [
        row
        for row in rows
        if bool(row.get("is_degraded_out_of_sample"))
    ]
    return [
        {
            "window_id": row.get("window_id", ""),
            "parameter_set": _parameter_set_label(row),
            "train_test_annualized_gap": _float_value(row, "train_test_annualized_gap"),
            "test_annualized_return": _float_value(row, "test_annualized_return"),
            "test_total_return": _float_value(row, "test_total_return"),
        }
        for row in sorted(
            degraded_rows,
            key=lambda item: _float_value(item, "train_test_annualized_gap"),
            reverse=True,
        )
    ]


def _parameter_set_label(row: dict[str, object]) -> str:
    items = [
        (key, str(value))
        for key, value in row.items()
        if _is_parameter_key(key)
    ]
    if not items:
        return "<none>"
    return ";".join(f"{key}={value}" for key, value in sorted(items))


def _oos_stability_grade(
    *,
    positive_test_window_rate: float,
    degraded_test_window_rate: float,
    parameter_drift_rate: float,
) -> str:
    if positive_test_window_rate >= 0.70 and degraded_test_window_rate <= 0.50 and parameter_drift_rate <= 0.50:
        return "stable"
    if positive_test_window_rate >= 0.50 and degraded_test_window_rate <= 0.75:
        return "mixed"
    return "unstable"


def _overfit_risk_label(
    *,
    degraded_test_window_rate: float,
    average_efficiency: float,
    parameter_drift_rate: float,
) -> str:
    if degraded_test_window_rate >= 0.75 and average_efficiency < 0.50:
        return "high"
    if degraded_test_window_rate >= 0.50 or parameter_drift_rate > 0.75:
        return "medium"
    return "low"


def _attach_parameter_value_context(
    rows: list[dict[str, object]],
    sensitivity: dict[str, dict[str, object]],
    rank_by: str,
) -> None:
    for row in rows:
        for param_key, analysis in sensitivity.items():
            if param_key not in row:
                continue
            value = str(row[param_key])
            values = analysis.get("values")
            if not isinstance(values, dict):
                continue
            stats = values.get(value)
            if not isinstance(stats, dict):
                continue
            metric_suffix = _metric_suffix(rank_by)
            row[f"{param_key}_value_run_count"] = stats["run_count"]
            row[f"{param_key}_value_average_{metric_suffix}"] = stats["average_metric"]
            row[f"{param_key}_value_gate_passing_rate"] = stats["gate_passing_rate"]


def _metric_suffix(metric_name: str) -> str:
    return "".join(
        character if character.isalnum() else "_"
        for character in metric_name
    ).strip("_") or "metric"


def _parameter_value_stats(
    rows: list[dict[str, object]],
    rank_by: str,
) -> dict[str, object]:
    metrics = [_float_value(row, rank_by) for row in rows]
    composite_scores = [_float_value(row, "composite_score") for row in rows]
    drawdowns = [_float_value(row, "max_drawdown") for row in rows]
    gate_passing = sum(1 for row in rows if str(row.get("gate_status", "")).lower() == "pass")
    return {
        "run_count": len(rows),
        "average_metric": sum(metrics) / len(metrics),
        "best_metric": max(metrics),
        "average_composite_score": sum(composite_scores) / len(composite_scores),
        "gate_passing_run_count": gate_passing,
        "gate_passing_rate": gate_passing / len(rows),
        "worst_max_drawdown": min(drawdowns),
    }


def _best_parameter_values(
    sensitivity: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        key: value["best_value_by_composite"]
        for key, value in sensitivity.items()
        if "best_value_by_composite" in value
    }


def _parameter_recommendation_rationale(
    sensitivity: dict[str, dict[str, object]],
    best_parameter_values: dict[str, object],
) -> dict[str, dict[str, object]]:
    rationale: dict[str, dict[str, object]] = {}
    for parameter, recommended_value in best_parameter_values.items():
        analysis = sensitivity.get(parameter)
        if not isinstance(analysis, dict):
            continue
        values = analysis.get("values")
        if not isinstance(values, dict):
            continue
        stats = values.get(str(recommended_value))
        if not isinstance(stats, dict):
            continue
        rationale[parameter] = {
            "recommended_value": recommended_value,
            "reason": "highest_average_composite_score",
            "is_also_best_by_metric": str(recommended_value) == str(analysis.get("best_value_by_metric", "")),
            "best_value_by_metric": analysis.get("best_value_by_metric", ""),
            "average_metric": stats.get("average_metric", 0.0),
            "best_metric": stats.get("best_metric", 0.0),
            "average_composite_score": stats.get("average_composite_score", 0.0),
            "gate_passing_rate": stats.get("gate_passing_rate", 0.0),
            "run_count": stats.get("run_count", 0),
            "worst_max_drawdown": stats.get("worst_max_drawdown", 0.0),
        }
    return rationale


def _parameter_recommendation_summary(rationale: dict[str, dict[str, object]]) -> str:
    if not rationale:
        return "No scanned parameters were available for recommendation."
    parts = []
    divergent_parameters = []
    for parameter, payload in sorted(rationale.items()):
        recommended_value = payload.get("recommended_value", "-")
        gate_rate = _numeric_object(payload.get("gate_passing_rate", 0.0))
        composite = _numeric_object(payload.get("average_composite_score", 0.0))
        parts.append(
            f"{parameter}={recommended_value} (composite {composite:.3f}, gate pass {gate_rate:.2%})"
        )
        if not bool(payload.get("is_also_best_by_metric", False)):
            divergent_parameters.append(
                f"{parameter} metric-best={payload.get('best_value_by_metric', '-')}"
            )
    summary = "Recommended parameter values by average composite score: " + "; ".join(parts) + "."
    if divergent_parameters:
        summary += " Metric and composite recommendations diverge for: " + "; ".join(divergent_parameters) + "."
    return summary


def _strongest_parameter(
    sensitivity: dict[str, dict[str, object]],
) -> str | None:
    if not sensitivity:
        return None
    return max(
        sensitivity,
        key=lambda key: _numeric_object(sensitivity[key].get("metric_range", 0.0)),
    )


def _delimited_value_counts(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value in (None, ""):
            continue
        for item in str(value).split(";"):
            item = item.strip()
            if not item:
                continue
            counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_count_key(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    return next(iter(counts))


def _recommended_actions(
    failed_gate_category_counts: dict[str, int],
    failed_gate_name_counts: dict[str, int],
) -> list[str]:
    if not failed_gate_category_counts and not failed_gate_name_counts:
        return ["Most parameter sets passed health gates; focus on robustness, live trading assumptions, and out-of-sample validation."]

    actions: list[str] = []
    category_actions = {
        "risk": "Risk gates fail often: reduce position concentration, raise cash buffer, shorten rebalance exposure, or add drawdown-aware filters.",
        "stability": "Stability gates fail often: prefer parameter regions with smoother rolling returns and validate on longer walk-forward windows.",
        "execution": "Execution gates fail often: reduce volume participation, avoid illiquid names, increase cash buffer, or relax target turnover.",
        "exposure": "Exposure gates fail often: tighten max_position_weight or add group constraints to reduce concentration.",
        "attribution": "Attribution gates fail often: inspect return attribution residuals before trusting parameter rankings.",
        "turnover": "Turnover gates fail often: lengthen rebalance interval, require stronger signal changes, or raise holding-period constraints.",
        "factor": "Factor gates fail often: remove redundant factors, lower highly correlated factor weights, or add orthogonal signals.",
        "ledger": "Ledger gates fail often: resolve accounting reconciliation issues before comparing parameter performance.",
    }
    for category, _count in failed_gate_category_counts.items():
        action = category_actions.get(category)
        if action is not None:
            actions.append(action)

    if failed_gate_name_counts:
        top_gate = next(iter(failed_gate_name_counts))
        actions.append(f"Most common failed gate is '{top_gate}'; review the single-run strategy_health_gates.csv files for affected runs first.")

    return actions[:5]


def _neighbor_rows(
    target: dict[str, object],
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    param_keys = sorted(key for key in target if _is_parameter_key(key))
    if not param_keys:
        return []
    neighbors = []
    for row in rows:
        if row is target or row.get("run_id") == target.get("run_id"):
            continue
        same_values = 0
        comparable = 0
        for key in param_keys:
            if key not in row:
                continue
            comparable += 1
            if row[key] == target[key]:
                same_values += 1
        if comparable and same_values >= comparable - 1:
            neighbors.append(row)
    return neighbors


def _float_value(row: dict[str, object], key: str) -> float:
    value = row.get(key, 0.0)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


def _numeric_object(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return 0.0


def _is_parameter_key(key: str) -> bool:
    return key.startswith("param_") and "_value_" not in key


def _test_to_train_efficiency(train_return: float, test_return: float) -> float:
    if train_return == 0.0:
        return 0.0 if test_return == 0.0 else -1.0
    return test_return / abs(train_return)
