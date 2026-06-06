from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from .models import PriceBar

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
)


def load_price_bars_from_csv(csv_path: str | Path) -> list[PriceBar]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    bars: list[PriceBar] = []
    seen_keys: set[tuple[date, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                raise ValueError(f"Line {line_number}: symbol is empty.")

            parsed_date = _parse_date(row.get("date"), line_number)
            close_value = _parse_positive_float(row.get("close"), "close", line_number)

            key = (parsed_date, symbol)
            if key in seen_keys:
                raise ValueError(
                    f"Line {line_number}: duplicate bar for {symbol} on {parsed_date.isoformat()}."
                )
            seen_keys.add(key)

            adjusted_close = _parse_optional_float(
                _pick_first_present(row, "adjusted_close", "adj_close"),
                "adjusted_close",
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
                _pick_first_present(row, "can_buy", "buyable"),
                line_number,
                default=tradable,
            )
            can_sell = _parse_boolean(
                _pick_first_present(row, "can_sell", "sellable"),
                line_number,
                default=tradable,
            )
            bars.append(
                PriceBar(
                    date=parsed_date,
                    symbol=symbol,
                    close=close_value,
                    adjusted_close=adjusted_close,
                    volume=volume,
                    tradable=tradable,
                    can_buy=can_buy,
                    can_sell=can_sell,
                )
            )

    bars.sort(key=lambda item: (item.date, item.symbol))
    return bars


def load_benchmark_bars_from_csv(
    csv_path: str | Path,
    *,
    default_symbol: str = "BENCHMARK",
) -> list[PriceBar]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark CSV file not found: {path}")

    bars: list[PriceBar] = []
    seen_dates: set[date] = set()
    detected_symbol: str | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"Benchmark CSV missing required columns: {missing_str}")

        for line_number, row in enumerate(reader, start=2):
            parsed_date = _parse_date(row.get("date"), line_number)
            if parsed_date in seen_dates:
                raise ValueError(
                    f"Line {line_number}: duplicate benchmark bar on {parsed_date.isoformat()}."
                )
            seen_dates.add(parsed_date)

            symbol = (row.get("symbol") or default_symbol).strip().upper() or default_symbol
            if detected_symbol is None:
                detected_symbol = symbol
            elif symbol != detected_symbol:
                raise ValueError("Benchmark CSV must contain exactly one symbol series.")

            bars.append(
                PriceBar(
                    date=parsed_date,
                    symbol=symbol,
                    close=_parse_positive_float(row.get("close"), "close", line_number),
                    adjusted_close=_parse_optional_float(
                        _pick_first_present(row, "adjusted_close", "adj_close"),
                        "adjusted_close",
                        line_number,
                    ),
                )
            )

    bars.sort(key=lambda item: item.date)
    return bars


def _parse_date(raw_value: str | None, line_number: int) -> date:
    value = (raw_value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Line {line_number}: unsupported date format '{value}'.")


def _parse_positive_float(
    raw_value: str | None,
    field_name: str,
    line_number: int,
    *,
    allow_zero: bool = False,
) -> float:
    value = (raw_value or "").strip()
    if not value:
        raise ValueError(f"Line {line_number}: {field_name} is empty.")

    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"Line {line_number}: invalid {field_name} '{value}'.") from exc

    if allow_zero:
        if parsed < 0:
            raise ValueError(f"Line {line_number}: {field_name} must be >= 0.")
    elif parsed <= 0:
        raise ValueError(f"Line {line_number}: {field_name} must be > 0.")
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


def _parse_boolean(raw_value: str | None, line_number: int, *, default: bool) -> bool:
    value = (raw_value or "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Line {line_number}: unsupported tradable flag '{raw_value}'.")


def _pick_first_present(row: dict[str, str], *field_names: str) -> str | None:
    for field_name in field_names:
        if field_name in row:
            return row.get(field_name)
    return None
