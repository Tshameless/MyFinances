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

            volume = None
            if row.get("volume") not in (None, ""):
                volume = _parse_positive_float(
                    row.get("volume"),
                    "volume",
                    line_number,
                    allow_zero=True,
                )

            tradable = _parse_tradable(row.get("tradable"), line_number)
            bars.append(
                PriceBar(
                    date=parsed_date,
                    symbol=symbol,
                    close=close_value,
                    volume=volume,
                    tradable=tradable,
                )
            )

    bars.sort(key=lambda item: (item.date, item.symbol))
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


def _parse_tradable(raw_value: str | None, line_number: int) -> bool:
    value = (raw_value or "").strip().lower()
    if not value:
        return True
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Line {line_number}: unsupported tradable flag '{raw_value}'.")
