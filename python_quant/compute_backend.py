from __future__ import annotations

from math import sqrt
from typing import Any

import numpy as np  # numpy is a required dependency (via scipy)


def _optional_numpy() -> Any:
    """Return numpy module. Always available since numpy is a required dependency."""
    return np


def _optional_pandas() -> Any | None:
    try:
        import pandas as pd  # type: ignore[import-untyped]
    except Exception:
        return None
    return pd


def vector_backend_available() -> bool:
    return _optional_numpy() is not None and _optional_pandas() is not None


def minmax_normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    np = _optional_numpy()
    if np is None or len(values) < 32:
        return _minmax_normalize_python(values)

    symbols = list(values)
    array = np.asarray([values[symbol] for symbol in symbols], dtype=float)
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    spread = maximum - minimum
    if spread == 0:
        return {symbol: 0.5 for symbol in symbols}
    normalized = (array - minimum) / spread
    return {
        symbol: float(value)
        for symbol, value in zip(symbols, normalized, strict=True)
    }


def sample_stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    np = _optional_numpy()
    if np is None or len(values) < 64:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return sqrt(max(variance, 0.0))
    return float(np.std(np.asarray(values, dtype=float), ddof=1))


def tail_risk(values: list[float], *, confidence: float) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    np = _optional_numpy()
    if np is None or len(values) < 64:
        sorted_returns = sorted(values)
        tail_count = max(1, int(round(len(sorted_returns) * (1.0 - confidence))))
        tail_returns = sorted_returns[:tail_count]
        var_return = tail_returns[-1]
        return (
            abs(min(var_return, 0.0)),
            abs(min(sum(tail_returns) / len(tail_returns), 0.0)),
            sorted_returns[0],
        )
    array = np.sort(np.asarray(values, dtype=float))
    tail_count = max(1, int(round(len(array) * (1.0 - confidence))))
    tail = array[:tail_count]
    var_return = float(tail[-1])
    return (
        abs(min(var_return, 0.0)),
        abs(min(float(np.mean(tail)), 0.0)),
        float(array[0]),
    )


def compound_return(values: list[float]) -> float:
    if not values:
        return 0.0
    np = _optional_numpy()
    if np is None or len(values) < 64:
        result = 1.0
        for value in values:
            result *= 1.0 + value
        return result - 1.0
    return float(np.prod(1.0 + np.asarray(values, dtype=float)) - 1.0)


def daily_returns(closes: list[float]) -> list[float]:
    if len(closes) < 2:
        return []
    np = _optional_numpy()
    if np is None or len(closes) < 64:
        returns: list[float] = []
        for index in range(1, len(closes)):
            previous = closes[index - 1]
            current = closes[index]
            returns.append(0.0 if previous == 0 else current / previous - 1.0)
        return returns
    array = np.asarray(closes, dtype=float)
    previous = array[:-1]
    current = array[1:]
    returns = np.divide(
        current,
        previous,
        out=np.ones_like(current),
        where=previous != 0,
    ) - 1.0
    return [float(value) for value in returns]


def _minmax_normalize_python(values: dict[str, float]) -> dict[str, float]:
    minimum = min(values.values())
    maximum = max(values.values())
    spread = maximum - minimum
    if spread == 0:
        return {symbol: 0.5 for symbol in values}
    return {
        symbol: (value - minimum) / spread
        for symbol, value in values.items()
    }
