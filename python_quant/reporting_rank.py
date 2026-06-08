from __future__ import annotations


def sort_rows_by_metric(rows: list[dict[str, object]], rank_by: str) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            _gate_rank_value(row),
            -float_metric(row, "gate_failures", default=0.0),
            -float_metric(row, "critical_warnings", default=0.0),
            -float_metric(row, "health_warnings", default=0.0),
            float_metric(row, rank_by, default=float("-inf")),
        ),
        reverse=True,
    )


def validate_rank_metric(rows: list[dict[str, object]], rank_by: str) -> None:
    if not rows:
        return

    available_metrics = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if _is_numeric_metric_value(value)
        }
    )
    if rank_by not in available_metrics:
        available_text = ", ".join(available_metrics) or "<none>"
        raise ValueError(
            f"Rank metric '{rank_by}' is not available. "
            f"Available numeric metrics: {available_text}."
        )


def float_metric(
    row: dict[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float:
    value = row.get(key)
    if value in ("", None):
        if default is not None:
            return default
        raise ValueError(f"Metric '{key}' is missing from row.")
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Metric '{key}' must be numeric, got {type(value).__name__}.")


def _gate_rank_value(row: dict[str, object]) -> float:
    gate_status = str(row.get("gate_status", "")).lower()
    if gate_status == "pass":
        return 1.0
    if gate_status == "":
        return 0.5
    return 0.0


def _is_numeric_metric_value(value: object) -> bool:
    if value in ("", None):
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False
