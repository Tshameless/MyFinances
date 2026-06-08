from __future__ import annotations

import csv
import hashlib
import pickle
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any

from .exceptions import DataValidationError
from .market import BENCHMARK_SYMBOL, is_a_share_symbol
from .models import PriceBar

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
)


def _get_cache_path(csv_path: Path) -> Path:
    stat = csv_path.stat()
    key = f"{csv_path.absolute()}_{stat.st_size}_{stat.st_mtime}"
    hash_str = hashlib.md5(key.encode("utf-8")).hexdigest()
    cache_dir = csv_path.parent / ".cache" / "data_loader"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{csv_path.name}_{hash_str}.pkl"


def _load_from_cache(cache_path: Path) -> Any | None:
    try:
        if cache_path.exists():
            with cache_path.open("rb") as f:
                return pickle.load(f)
    except Exception:
        pass
    return None


def _save_to_cache(cache_path: Path, data: Any) -> None:
    try:
        with cache_path.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def load_price_bars_from_csv(csv_path: str | Path) -> list[PriceBar]:
    path = Path(csv_path)
    if _is_sqlite_path(path):
        from .data_store import load_price_bars_from_sqlite

        return load_price_bars_from_sqlite(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    cache_path = _get_cache_path(path)
    cached_data = _load_from_cache(cache_path)
    if cached_data is not None:
        return cached_data

    bars: list[PriceBar] = []
    seen_keys: set[tuple[date, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "close"}

        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise DataValidationError(f"CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                raise DataValidationError(f"Line {line_number}: symbol is empty.")
            if not is_a_share_symbol(symbol):
                raise DataValidationError(
                    f"Line {line_number}: unsupported A-share symbol format '{symbol}'."
                )

            parsed_date = _parse_date(row.get("date"), line_number)
            close_value = _parse_positive_float(row.get("close"), "close", line_number)

            key = (parsed_date, symbol)
            if key in seen_keys:
                raise DataValidationError(
                    f"Line {line_number}: duplicate bar for {symbol} on {parsed_date.isoformat()}."
                )
            seen_keys.add(key)

            adjusted_close = _parse_optional_float(
                row.get("adjusted_close"),
                "adjusted_close",
                line_number,
            )
            open_price = _parse_optional_float(
                row.get("open"),
                "open",
                line_number,
            )
            vwap = _parse_optional_float(
                row.get("vwap"),
                "vwap",
                line_number,
            )
            volume = None
            if row.get("volume") not in (None, ""):
                volume = _parse_positive_float(
                    row.get("volume"),
                    "volume",
                    line_number,
                    allow_zero=True,
                )

            tradable = _parse_boolean(row.get("tradable"), line_number, default=True)
            can_buy = _parse_boolean(
                row.get("can_buy"),
                line_number,
                default=tradable,
            )
            can_sell = _parse_boolean(
                row.get("can_sell"),
                line_number,
                default=tradable,
            )
            is_suspended = _parse_boolean(
                row.get("is_suspended") or row.get("suspended"),
                line_number,
                default=False,
            )
            is_limit_up = _parse_boolean(row.get("is_limit_up"), line_number, default=False)
            is_limit_down = _parse_boolean(row.get("is_limit_down"), line_number, default=False)
            is_st = _parse_boolean(row.get("is_st"), line_number, default=False)
            limit_rate = _parse_optional_rate(row.get("limit_rate"), "limit_rate", line_number)
            bars.append(
                PriceBar(
                    date=parsed_date,
                    symbol=symbol,
                    close=close_value,
                    adjusted_close=adjusted_close,
                    open=open_price,
                    vwap=vwap,
                    volume=volume,
                    tradable=tradable,
                    can_buy=can_buy,
                    can_sell=can_sell,
                    is_suspended=is_suspended,
                    is_limit_up=is_limit_up,
                    is_limit_down=is_limit_down,
                    is_st=is_st,
                    limit_rate=limit_rate,
                )
            )

    bars.sort(key=lambda item: (item.date, item.symbol))
    _save_to_cache(cache_path, bars)
    return bars


def load_benchmark_bars_from_csv(
    csv_path: str | Path,
) -> list[PriceBar]:
    path = Path(csv_path)
    if _is_sqlite_path(path):
        from .data_store import load_benchmark_bars_from_sqlite

        return load_benchmark_bars_from_sqlite(path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark CSV file not found: {path}")

    cache_path = _get_cache_path(path)
    cached_data = _load_from_cache(cache_path)
    if cached_data is not None:
        return cached_data

    bars: list[PriceBar] = []
    seen_dates: set[date] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise DataValidationError(f"Benchmark CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            parsed_date = _parse_date(row.get("date"), line_number)
            if parsed_date in seen_dates:
                raise DataValidationError(
                    f"Line {line_number}: duplicate benchmark bar on {parsed_date.isoformat()}."
                )
            seen_dates.add(parsed_date)

            bars.append(
                PriceBar(
                    date=parsed_date,
                    symbol=BENCHMARK_SYMBOL,
                    close=_parse_positive_float(row.get("close"), "close", line_number),
                    adjusted_close=_parse_optional_float(
                        row.get("adjusted_close"),
                        "adjusted_close",
                        line_number,
                    ),
                    open=_parse_optional_float(row.get("open"), "open", line_number),
                    vwap=_parse_optional_float(row.get("vwap"), "vwap", line_number),
                    is_limit_up=_parse_boolean(row.get("is_limit_up"), line_number, default=False),
                    is_limit_down=_parse_boolean(row.get("is_limit_down"), line_number, default=False),
                )
            )

    bars.sort(key=lambda item: item.date)
    _save_to_cache(cache_path, bars)
    return bars


def load_stock_pool_from_csv(csv_path: str | Path) -> dict[date, set[str]]:
    path = Path(csv_path)
    if _is_sqlite_path(path):
        from .data_store import load_stock_pool_from_sqlite

        return load_stock_pool_from_sqlite(path)
    if not path.exists():
        raise FileNotFoundError(f"Stock pool CSV file not found: {path}")

    cache_path = _get_cache_path(path)
    cached_data = _load_from_cache(cache_path)
    if cached_data is not None:
        return cached_data

    stock_pool: dict[date, set[str]] = {}
    seen_keys: set[tuple[date, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise DataValidationError(f"Stock pool CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            parsed_date = _parse_date(row.get("date"), line_number)
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                raise DataValidationError(f"Line {line_number}: symbol is empty.")
            if not is_a_share_symbol(symbol):
                raise DataValidationError(
                    f"Line {line_number}: unsupported A-share symbol format '{symbol}'."
                )
            key = (parsed_date, symbol)
            if key in seen_keys:
                raise DataValidationError(
                    "Line "
                    f"{line_number}: duplicate stock pool symbol {symbol} "
                    f"on {parsed_date.isoformat()}."
                )
            seen_keys.add(key)
            stock_pool.setdefault(parsed_date, set()).add(symbol)

    if not stock_pool:
        raise DataValidationError("Stock pool CSV does not contain any symbols.")
    result = dict(sorted(stock_pool.items()))
    _save_to_cache(cache_path, result)
    return result


def load_factor_scores_from_csv(csv_path: str | Path) -> dict[date, dict[str, float]]:
    path = Path(csv_path)
    if _is_sqlite_path(path):
        from .data_store import load_factor_scores_from_sqlite

        return load_factor_scores_from_sqlite(path)
    if not path.exists():
        raise FileNotFoundError(f"Factor score CSV file not found: {path}")

    cache_path = _get_cache_path(path)
    cached_data = _load_from_cache(cache_path)
    if cached_data is not None:
        return cached_data

    scores: dict[date, dict[str, float]] = {}
    seen_keys: set[tuple[date, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "score"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise DataValidationError(f"Factor score CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            parsed_date = _parse_date(row.get("date"), line_number)
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                raise DataValidationError(f"Line {line_number}: symbol is empty.")
            if not is_a_share_symbol(symbol):
                raise DataValidationError(
                    f"Line {line_number}: unsupported A-share symbol format '{symbol}'."
                )
            key = (parsed_date, symbol)
            if key in seen_keys:
                raise DataValidationError(
                    "Line "
                    f"{line_number}: duplicate factor score for {symbol} "
                    f"on {parsed_date.isoformat()}."
                )
            seen_keys.add(key)
            scores.setdefault(parsed_date, {})[symbol] = _parse_float(
                row.get("score"),
                "score",
                line_number,
            )

    if not scores:
        raise DataValidationError("Factor score CSV does not contain any scores.")
    result = dict(sorted(scores.items()))
    _save_to_cache(cache_path, result)
    return result


def _parse_date(raw_value: str | None, line_number: int) -> date:
    value = (raw_value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise DataValidationError(f"Line {line_number}: unsupported date format '{value}'.")


def _parse_positive_float(
    raw_value: str | None,
    field_name: str,
    line_number: int,
    *,
    allow_zero: bool = False,
) -> float:
    value = (raw_value or "").strip()
    if not value:
        raise DataValidationError(f"Line {line_number}: {field_name} is empty.")

    try:
        parsed = float(value)
    except ValueError as exc:
        raise DataValidationError(f"Line {line_number}: invalid {field_name} '{value}'.") from exc

    if allow_zero:
        if parsed < 0:
            raise DataValidationError(f"Line {line_number}: {field_name} must be >= 0.")
    elif parsed <= 0:
        raise DataValidationError(f"Line {line_number}: {field_name} must be > 0.")
    if not isfinite(parsed):
        raise DataValidationError(f"Line {line_number}: {field_name} must be finite.")
    return parsed


def _parse_float(
    raw_value: str | None,
    field_name: str,
    line_number: int,
) -> float:
    value = (raw_value or "").strip()
    if not value:
        raise DataValidationError(f"Line {line_number}: {field_name} is empty.")

    try:
        parsed = float(value)
    except ValueError as exc:
        raise DataValidationError(f"Line {line_number}: invalid {field_name} '{value}'.") from exc
    if not isfinite(parsed):
        raise DataValidationError(f"Line {line_number}: {field_name} must be finite.")
    return parsed


def _parse_optional_float(
    raw_value: str | None,
    field_name: str,
    line_number: int,
) -> float | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    return _parse_positive_float(value, field_name, line_number)


def _parse_optional_rate(
    raw_value: str | None,
    field_name: str,
    line_number: int,
) -> float | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    parsed = _parse_positive_float(value, field_name, line_number)
    if parsed >= 1:
        raise DataValidationError(f"Line {line_number}: {field_name} must be between 0 and 1.")
    return parsed


def _parse_boolean(raw_value: str | None, line_number: int, *, default: bool) -> bool:
    value = (raw_value or "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise DataValidationError(f"Line {line_number}: unsupported tradable flag '{raw_value}'.")


def _is_sqlite_path(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}
