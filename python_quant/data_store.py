from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from .exceptions import DataValidationError
from .market import BENCHMARK_SYMBOL, is_a_share_symbol
from .models import CorporateAction, PriceBar

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")


def initialize_sqlite_store(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS price_bars (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                close REAL NOT NULL,
                adjusted_close REAL,
                adjustment_factor REAL,
                open REAL,
                vwap REAL,
                volume REAL,
                tradable INTEGER NOT NULL DEFAULT 1,
                can_buy INTEGER NOT NULL DEFAULT 1,
                can_sell INTEGER NOT NULL DEFAULT 1,
                is_suspended INTEGER NOT NULL DEFAULT 0,
                is_limit_up INTEGER NOT NULL DEFAULT 0,
                is_limit_down INTEGER NOT NULL DEFAULT 0,
                is_st INTEGER NOT NULL DEFAULT 0,
                limit_rate REAL,
                PRIMARY KEY (date, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_price_bars_symbol_date
                ON price_bars(symbol, date);

            CREATE TABLE IF NOT EXISTS corporate_actions (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action_type TEXT NOT NULL,
                value REAL,
                description TEXT,
                PRIMARY KEY (date, symbol, action_type)
            );
            CREATE INDEX IF NOT EXISTS idx_corporate_actions_symbol_date
                ON corporate_actions(symbol, date);

            CREATE TABLE IF NOT EXISTS benchmark_bars (
                date TEXT PRIMARY KEY,
                close REAL NOT NULL,
                adjusted_close REAL,
                open REAL,
                vwap REAL
            );

            CREATE TABLE IF NOT EXISTS stock_pool (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                PRIMARY KEY (date, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_stock_pool_date
                ON stock_pool(date);

            CREATE TABLE IF NOT EXISTS factor_scores (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                score REAL NOT NULL,
                PRIMARY KEY (date, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_factor_scores_date
                ON factor_scores(date);

            CREATE TABLE IF NOT EXISTS symbol_groups (
                symbol TEXT PRIMARY KEY,
                group_name TEXT NOT NULL
            );
            """
        )
    finally:
        conn.close()
    return path


def import_price_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataValidationError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip()
            if not is_a_share_symbol(symbol):
                raise DataValidationError(f"Line {line_number}: unsupported A-share symbol format '{symbol}'.")
            parsed_date = _parse_date(row.get("date"), line_number)
            rows.append(
                (
                    parsed_date.isoformat(),
                    symbol,
                    _required_float(row.get("close"), "close", line_number),
                    _optional_float(row.get("adjusted_close")),
                    _optional_float(row.get("adjustment_factor")),
                    _optional_float(row.get("open")),
                    _optional_float(row.get("vwap")),
                    _optional_float(row.get("volume")),
                    _bool_int(row.get("tradable"), default=True),
                    _bool_int(row.get("can_buy"), default=True),
                    _bool_int(row.get("can_sell"), default=True),
                    _bool_int(row.get("is_suspended") or row.get("suspended"), default=False),
                    _bool_int(row.get("is_limit_up"), default=False),
                    _bool_int(row.get("is_limit_down"), default=False),
                    _bool_int(row.get("is_st"), default=False),
                    _optional_float(row.get("limit_rate")),
                )
            )
    conn = sqlite3.connect(path)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO price_bars
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def import_benchmark_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader, {"date", "close"}, "Benchmark CSV")
        for line_number, row in enumerate(reader, start=2):
            parsed_date = _parse_date(row.get("date"), line_number)
            rows.append(
                (
                    parsed_date.isoformat(),
                    _required_float(row.get("close"), "close", line_number),
                    _optional_float(row.get("adjusted_close")),
                    _optional_float(row.get("open")),
                    _optional_float(row.get("vwap")),
                )
            )
    _execute_many(
        path,
        "INSERT OR REPLACE INTO benchmark_bars VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def import_stock_pool_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader, {"date", "symbol"}, "Stock pool CSV")
        for line_number, row in enumerate(reader, start=2):
            symbol = _require_a_share_symbol(row.get("symbol"), line_number)
            parsed_date = _parse_date(row.get("date"), line_number)
            rows.append((parsed_date.isoformat(), symbol))
    _execute_many(
        path,
        "INSERT OR REPLACE INTO stock_pool VALUES (?, ?)",
        rows,
    )
    return len(rows)


def import_factor_scores_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader, {"date", "symbol", "score"}, "Factor score CSV")
        for line_number, row in enumerate(reader, start=2):
            symbol = _require_a_share_symbol(row.get("symbol"), line_number)
            parsed_date = _parse_date(row.get("date"), line_number)
            rows.append(
                (
                    parsed_date.isoformat(),
                    symbol,
                    _required_float(row.get("score"), "score", line_number),
                )
            )
    _execute_many(
        path,
        "INSERT OR REPLACE INTO factor_scores VALUES (?, ?, ?)",
        rows,
    )
    return len(rows)


def import_symbol_groups_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader, {"symbol", "group"}, "Symbol group CSV")
        for line_number, row in enumerate(reader, start=2):
            symbol = _require_a_share_symbol(row.get("symbol"), line_number)
            group = (row.get("group") or "").strip()
            if not group:
                raise DataValidationError(f"Line {line_number}: group is empty.")
            rows.append((symbol, group))
    _execute_many(
        path,
        "INSERT OR REPLACE INTO symbol_groups VALUES (?, ?)",
        rows,
    )
    return len(rows)


def import_corporate_actions_csv_to_sqlite(csv_path: str | Path, db_path: str | Path) -> int:
    path = initialize_sqlite_store(db_path)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader, {"date", "symbol", "action_type"}, "Corporate actions CSV")
        for line_number, row in enumerate(reader, start=2):
            symbol = _require_a_share_symbol(row.get("symbol"), line_number)
            parsed_date = _parse_date(row.get("date"), line_number)
            action_type = (row.get("action_type") or "").strip()
            if not action_type:
                raise DataValidationError(f"Line {line_number}: action_type is empty.")
            rows.append(
                (
                    parsed_date.isoformat(),
                    symbol,
                    action_type,
                    _optional_float(row.get("value")),
                    (row.get("description") or "").strip() or None,
                )
            )
    _execute_many(
        path,
        "INSERT OR REPLACE INTO corporate_actions VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def load_price_bars_from_sqlite(
    db_path: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: Iterable[str] | None = None,
) -> list[PriceBar]:
    query = "SELECT * FROM price_bars"
    params: list[object] = []
    predicates: list[str] = []
    if start_date is not None:
        predicates.append("date >= ?")
        params.append(start_date.isoformat())
    if end_date is not None:
        predicates.append("date <= ?")
        params.append(end_date.isoformat())
    symbol_list = sorted(set(symbols or []))
    if symbol_list:
        predicates.append(f"symbol IN ({','.join('?' for _ in symbol_list)})")
        params.extend(symbol_list)
    if predicates:
        query += " WHERE " + " AND ".join(predicates)
    query += " ORDER BY date, symbol"
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [_price_bar_from_row(row) for row in rows]


def load_benchmark_bars_from_sqlite(
    db_path: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PriceBar]:
    query = "SELECT * FROM benchmark_bars"
    params: list[object] = []
    predicates: list[str] = []
    if start_date is not None:
        predicates.append("date >= ?")
        params.append(start_date.isoformat())
    if end_date is not None:
        predicates.append("date <= ?")
        params.append(end_date.isoformat())
    if predicates:
        query += " WHERE " + " AND ".join(predicates)
    query += " ORDER BY date"
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [
        PriceBar(
            date=_parse_iso_date(row["date"]),
            symbol=BENCHMARK_SYMBOL,
            close=float(row["close"]),
            adjusted_close=_row_float(row, "adjusted_close"),
            open=_row_float(row, "open"),
            vwap=_row_float(row, "vwap"),
        )
        for row in rows
    ]


def load_stock_pool_from_sqlite(db_path: str | Path) -> dict[date, set[str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT date, symbol FROM stock_pool ORDER BY date, symbol").fetchall()
    finally:
        conn.close()
    result: dict[date, set[str]] = {}
    for raw_date, symbol in rows:
        result.setdefault(_parse_iso_date(raw_date), set()).add(symbol)
    return result


def load_factor_scores_from_sqlite(db_path: str | Path) -> dict[date, dict[str, float]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT date, symbol, score FROM factor_scores ORDER BY date, symbol").fetchall()
    finally:
        conn.close()
    result: dict[date, dict[str, float]] = {}
    for raw_date, symbol, score in rows:
        result.setdefault(_parse_iso_date(raw_date), {})[symbol] = float(score)
    return result


def load_symbol_groups_from_sqlite(db_path: str | Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT symbol, group_name FROM symbol_groups ORDER BY symbol").fetchall()
    finally:
        conn.close()
    return {str(symbol): str(group_name) for symbol, group_name in rows}


def load_corporate_actions_from_sqlite(db_path: str | Path) -> list[CorporateAction]:
    query = "SELECT * FROM corporate_actions ORDER BY date, symbol"
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [
        CorporateAction(
            date=_parse_iso_date(row["date"]),
            symbol=str(row["symbol"]),
            action_type=str(row["action_type"]),
            value=_row_float(row, "value"),
            description=row["description"],
        )
        for row in rows
    ]


def _price_bar_from_row(row: sqlite3.Row) -> PriceBar:
    return PriceBar(
        date=_parse_iso_date(row["date"]),
        symbol=str(row["symbol"]),
        close=float(row["close"]),
        adjusted_close=_row_float(row, "adjusted_close"),
        adjustment_factor=_row_float(row, "adjustment_factor"),
        open=_row_float(row, "open"),
        vwap=_row_float(row, "vwap"),
        volume=_row_float(row, "volume"),
        tradable=bool(row["tradable"]),
        can_buy=bool(row["can_buy"]),
        can_sell=bool(row["can_sell"]),
        is_suspended=bool(row["is_suspended"]),
        is_limit_up=bool(row["is_limit_up"]),
        is_limit_down=bool(row["is_limit_down"]),
        is_st=bool(row["is_st"]),
        limit_rate=_row_float(row, "limit_rate"),
    )


def _parse_date(raw_value: str | None, line_number: int) -> date:
    value = (raw_value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise DataValidationError(f"Line {line_number}: unsupported date format '{value}'.")


def _parse_iso_date(raw_value: str) -> date:
    return datetime.strptime(raw_value, "%Y-%m-%d").date()


def _required_float(raw_value: str | None, field_name: str, line_number: int) -> float:
    value = (raw_value or "").strip()
    if not value:
        raise DataValidationError(f"Line {line_number}: {field_name} is empty.")
    return float(value)


def _require_a_share_symbol(raw_value: str | None, line_number: int) -> str:
    symbol = (raw_value or "").strip()
    if not is_a_share_symbol(symbol):
        raise DataValidationError(f"Line {line_number}: unsupported A-share symbol format '{symbol}'.")
    return symbol


def _require_columns(reader: csv.DictReader[str], required: set[str], label: str) -> None:
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise DataValidationError(f"{label} missing required columns: {', '.join(sorted(missing))}")


def _execute_many(path: Path, statement: str, rows: list[tuple[object, ...]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executemany(statement, rows)
        conn.commit()
    finally:
        conn.close()


def _optional_float(raw_value: str | None) -> float | None:
    value = (raw_value or "").strip()
    return None if not value else float(value)


def _row_float(row: sqlite3.Row, key: str) -> float | None:
    value = row[key]
    return None if value is None else float(value)


def _bool_int(raw_value: str | None, *, default: bool) -> int:
    value = (raw_value or "").strip().lower()
    if not value:
        return int(default)
    return int(value in {"1", "true", "yes", "y"})
