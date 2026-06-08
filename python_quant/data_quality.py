from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .market import is_a_share_symbol
from .models import PriceBar

_HUMAN_READABLE_ENCODING = "utf-8-sig"


@dataclass(frozen=True)
class SymbolQualityRow:
    symbol: str
    row_count: int
    start_date: str
    end_date: str
    missing_common_dates: int
    missing_adjusted_close: int
    missing_open: int
    missing_vwap: int
    zero_volume_days: int
    suspended_days: int
    limit_up_days: int
    limit_down_days: int
    st_days: int
    custom_limit_rate_days: int
    untradable_days: int
    cannot_buy_days: int
    cannot_sell_days: int
    max_abs_return: float
    abnormal_return_days: int


@dataclass(frozen=True)
class DataQualityReport:
    summary: dict[str, object]
    symbols: list[SymbolQualityRow]
    daily_counts: list[dict[str, object]]


@dataclass(frozen=True)
class MappingQualityReport:
    summary: dict[str, object]
    rows: list[dict[str, object]]


@dataclass(frozen=True)
class BenchmarkQualityRow:
    date: str
    close: float
    adjusted_close_missing: bool
    daily_return: float | None
    abnormal_return: bool


@dataclass(frozen=True)
class BenchmarkQualityReport:
    summary: dict[str, object]
    rows: list[BenchmarkQualityRow]


def build_price_data_quality_report(
    bars: list[PriceBar],
    *,
    abnormal_return_threshold: float = 0.11,
    execution_price_field: str | None = None,
) -> DataQualityReport:
    if not bars:
        return DataQualityReport(
            summary={
                "row_count": 0,
                "symbol_count": 0,
                "date_count": 0,
                "start_date": None,
                "end_date": None,
                "abnormal_return_threshold": abnormal_return_threshold,
                "execution_price_field": execution_price_field,
                "missing_execution_price_rows": 0,
                "execution_price_coverage_rate": 0.0,
            },
            symbols=[],
            daily_counts=[],
        )

    bars_by_symbol: dict[str, list[PriceBar]] = defaultdict(list)
    bars_by_date: dict[date, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        bars_by_symbol[bar.symbol].append(bar)
        bars_by_date[bar.date].append(bar)

    all_dates = sorted(bars_by_date)
    all_date_set = set(all_dates)
    symbol_rows: list[SymbolQualityRow] = []

    for symbol, symbol_bars in sorted(bars_by_symbol.items()):
        ordered = sorted(symbol_bars, key=lambda item: item.date)
        dates = {bar.date for bar in ordered}
        returns = _daily_returns(ordered)
        abnormal_returns = [
            value for value in returns if abs(value) > abnormal_return_threshold
        ]
        symbol_rows.append(
            SymbolQualityRow(
                symbol=symbol,
                row_count=len(ordered),
                start_date=ordered[0].date.isoformat(),
                end_date=ordered[-1].date.isoformat(),
                missing_common_dates=len(all_date_set - dates),
                missing_adjusted_close=sum(1 for bar in ordered if bar.adjusted_close is None),
                missing_open=sum(1 for bar in ordered if bar.open is None),
                missing_vwap=sum(1 for bar in ordered if bar.vwap is None),
                zero_volume_days=sum(1 for bar in ordered if bar.volume == 0),
                suspended_days=sum(1 for bar in ordered if bar.is_suspended),
                limit_up_days=sum(1 for bar in ordered if bar.is_limit_up),
                limit_down_days=sum(1 for bar in ordered if bar.is_limit_down),
                st_days=sum(1 for bar in ordered if bar.is_st),
                custom_limit_rate_days=sum(1 for bar in ordered if bar.limit_rate is not None),
                untradable_days=sum(1 for bar in ordered if not bar.tradable),
                cannot_buy_days=sum(1 for bar in ordered if not bar.can_buy),
                cannot_sell_days=sum(1 for bar in ordered if not bar.can_sell),
                max_abs_return=max((abs(value) for value in returns), default=0.0),
                abnormal_return_days=len(abnormal_returns),
            )
        )

    daily_counts = [
        {
            "date": trading_date.isoformat(),
            "symbol_count": len(bars_by_date[trading_date]),
            "suspended_count": sum(1 for bar in bars_by_date[trading_date] if bar.is_suspended),
            "limit_up_count": sum(1 for bar in bars_by_date[trading_date] if bar.is_limit_up),
            "limit_down_count": sum(1 for bar in bars_by_date[trading_date] if bar.is_limit_down),
            "st_count": sum(1 for bar in bars_by_date[trading_date] if bar.is_st),
            "missing_open_count": sum(1 for bar in bars_by_date[trading_date] if bar.open is None),
            "missing_vwap_count": sum(1 for bar in bars_by_date[trading_date] if bar.vwap is None),
            "untradable_count": sum(1 for bar in bars_by_date[trading_date] if not bar.tradable),
            "cannot_buy_count": sum(1 for bar in bars_by_date[trading_date] if not bar.can_buy),
            "cannot_sell_count": sum(1 for bar in bars_by_date[trading_date] if not bar.can_sell),
        }
        for trading_date in all_dates
    ]
    daily_symbol_counts = [len(bars_by_date[trading_date]) for trading_date in all_dates]
    missing_execution_price_rows = _missing_price_field_count(bars, execution_price_field)
    summary = {
        "row_count": len(bars),
        "symbol_count": len(bars_by_symbol),
        "date_count": len(all_dates),
        "start_date": all_dates[0].isoformat(),
        "end_date": all_dates[-1].isoformat(),
        "abnormal_return_threshold": abnormal_return_threshold,
        "execution_price_field": execution_price_field,
        "missing_execution_price_rows": missing_execution_price_rows,
        "execution_price_coverage_rate": 1.0 - missing_execution_price_rows / len(bars),
        "symbols_with_missing_common_dates": sum(
            1 for row in symbol_rows if row.missing_common_dates > 0
        ),
        "symbols_with_missing_adjusted_close": sum(
            1 for row in symbol_rows if row.missing_adjusted_close > 0
        ),
        "symbols_with_missing_open": sum(
            1 for row in symbol_rows if row.missing_open > 0
        ),
        "symbols_with_missing_vwap": sum(
            1 for row in symbol_rows if row.missing_vwap > 0
        ),
        "symbols_with_suspended_days": sum(
            1 for row in symbol_rows if row.suspended_days > 0
        ),
        "symbols_with_limit_up_days": sum(
            1 for row in symbol_rows if row.limit_up_days > 0
        ),
        "symbols_with_limit_down_days": sum(
            1 for row in symbol_rows if row.limit_down_days > 0
        ),
        "symbols_with_st_days": sum(
            1 for row in symbol_rows if row.st_days > 0
        ),
        "symbols_with_abnormal_returns": sum(
            1 for row in symbol_rows if row.abnormal_return_days > 0
        ),
        "missing_open_rows": sum(row.missing_open for row in symbol_rows),
        "missing_vwap_rows": sum(row.missing_vwap for row in symbol_rows),
        "suspended_days": sum(row.suspended_days for row in symbol_rows),
        "limit_up_days": sum(row.limit_up_days for row in symbol_rows),
        "limit_down_days": sum(row.limit_down_days for row in symbol_rows),
        "st_days": sum(row.st_days for row in symbol_rows),
        "custom_limit_rate_days": sum(row.custom_limit_rate_days for row in symbol_rows),
        "untradable_days": sum(row.untradable_days for row in symbol_rows),
        "cannot_buy_days": sum(row.cannot_buy_days for row in symbol_rows),
        "cannot_sell_days": sum(row.cannot_sell_days for row in symbol_rows),
        "min_daily_symbol_count": min(daily_symbol_counts),
        "max_daily_symbol_count": max(daily_symbol_counts),
    }
    return DataQualityReport(summary=summary, symbols=symbol_rows, daily_counts=daily_counts)


def build_benchmark_quality_report(
    bars: list[PriceBar],
    *,
    expected_dates: set[date] | None = None,
    abnormal_return_threshold: float = 0.11,
) -> BenchmarkQualityReport:
    if not bars:
        missing_expected_dates = sorted(expected_dates or set())
        return BenchmarkQualityReport(
            summary={
                "row_count": 0,
                "date_count": 0,
                "start_date": None,
                "end_date": None,
                "abnormal_return_threshold": abnormal_return_threshold,
                "missing_expected_dates": len(missing_expected_dates),
                "missing_expected_date_list": [
                    item.isoformat() for item in missing_expected_dates
                ],
                "missing_adjusted_close_rows": 0,
                "zero_or_negative_close_rows": 0,
                "abnormal_return_days": 0,
                "max_abs_return": 0.0,
            },
            rows=[],
        )

    ordered = sorted(bars, key=lambda item: item.date)
    dates = {bar.date for bar in ordered}
    missing_expected_dates = sorted((expected_dates or set()) - dates)
    rows: list[BenchmarkQualityRow] = []
    previous_close: float | None = None
    returns: list[float] = []
    for bar in ordered:
        daily_return = None
        if previous_close is not None and previous_close > 0:
            daily_return = bar.close / previous_close - 1.0
            returns.append(daily_return)
        rows.append(
            BenchmarkQualityRow(
                date=bar.date.isoformat(),
                close=bar.close,
                adjusted_close_missing=bar.adjusted_close is None,
                daily_return=daily_return,
                abnormal_return=(
                    daily_return is not None
                    and abs(daily_return) > abnormal_return_threshold
                ),
            )
        )
        previous_close = bar.close

    summary = {
        "row_count": len(ordered),
        "date_count": len(dates),
        "start_date": ordered[0].date.isoformat(),
        "end_date": ordered[-1].date.isoformat(),
        "abnormal_return_threshold": abnormal_return_threshold,
        "missing_expected_dates": len(missing_expected_dates),
        "missing_expected_date_list": [
            item.isoformat() for item in missing_expected_dates
        ],
        "missing_adjusted_close_rows": sum(1 for bar in ordered if bar.adjusted_close is None),
        "zero_or_negative_close_rows": sum(1 for bar in ordered if bar.close <= 0),
        "abnormal_return_days": sum(1 for row in rows if row.abnormal_return),
        "max_abs_return": max((abs(value) for value in returns), default=0.0),
    }
    return BenchmarkQualityReport(summary=summary, rows=rows)


def _missing_price_field_count(bars: list[PriceBar], price_field: str | None) -> int:
    if price_field in (None, "close"):
        return 0
    if price_field == "adjusted_close":
        return sum(1 for bar in bars if bar.adjusted_close is None)
    if price_field == "open":
        return sum(1 for bar in bars if bar.open is None)
    if price_field == "vwap":
        return sum(1 for bar in bars if bar.vwap is None)
    return 0


def build_symbol_group_quality_report(
    mapping_path: Path,
    *,
    expected_symbols: set[str] | None = None,
) -> MappingQualityReport:
    rows: list[dict[str, object]] = []
    symbol_counts: defaultdict[str, int] = defaultdict(int)
    mapped_symbols: set[str] = set()
    groups: set[str] = set()

    with mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"symbol", "group"} - fieldnames)
        if missing_columns:
            return MappingQualityReport(
                summary={
                    "row_count": 0,
                    "mapped_symbol_count": 0,
                    "group_count": 0,
                    "missing_columns": missing_columns,
                    "duplicate_symbols": 0,
                    "blank_symbol_rows": 0,
                    "blank_group_rows": 0,
                    "missing_expected_symbols": 0,
                    "extra_mapped_symbols": 0,
                },
                rows=[],
            )

        for row_index, raw_row in enumerate(reader, start=2):
            symbol = (raw_row.get("symbol") or "").strip()
            group = (raw_row.get("group") or "").strip()
            symbol_counts[symbol] += 1
            if symbol:
                mapped_symbols.add(symbol)
            if group:
                groups.add(group)
            rows.append(
                {
                    "row_number": row_index,
                    "symbol": symbol,
                    "group": group,
                    "blank_symbol": symbol == "",
                    "blank_group": group == "",
                    "duplicate_symbol": False,
                    "in_expected_symbols": None if expected_symbols is None or symbol == "" else symbol in expected_symbols,
                }
            )

    for row in rows:
        symbol = str(row["symbol"])
        row["duplicate_symbol"] = symbol != "" and symbol_counts[symbol] > 1

    missing_expected = sorted((expected_symbols or set()) - mapped_symbols)
    extra_mapped = sorted(mapped_symbols - (expected_symbols or set())) if expected_symbols is not None else []
    summary = {
        "row_count": len(rows),
        "mapped_symbol_count": len(mapped_symbols),
        "group_count": len(groups),
        "missing_columns": [],
        "duplicate_symbols": sum(1 for symbol, count in symbol_counts.items() if symbol and count > 1),
        "blank_symbol_rows": sum(1 for row in rows if row["blank_symbol"]),
        "blank_group_rows": sum(1 for row in rows if row["blank_group"]),
        "missing_expected_symbols": len(missing_expected),
        "extra_mapped_symbols": len(extra_mapped),
        "missing_expected_symbol_list": missing_expected,
        "extra_mapped_symbol_list": extra_mapped,
    }
    return MappingQualityReport(summary=summary, rows=rows)


def build_stock_pool_quality_report(
    stock_pool_path: Path,
    *,
    expected_symbols: set[str] | None = None,
) -> MappingQualityReport:
    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    dates: set[str] = set()
    mapped_symbols: set[str] = set()
    duplicate_keys = 0
    blank_date_rows = 0
    blank_symbol_rows = 0
    invalid_symbol_rows = 0

    with stock_pool_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"date", "symbol"} - fieldnames)
        if missing_columns:
            return MappingQualityReport(
                summary={
                    "row_count": 0,
                    "date_count": 0,
                    "mapped_symbol_count": 0,
                    "missing_columns": missing_columns,
                    "duplicate_date_symbol_rows": 0,
                    "blank_date_rows": 0,
                    "blank_symbol_rows": 0,
                    "invalid_symbol_rows": 0,
                    "missing_expected_symbols": 0,
                    "extra_mapped_symbols": 0,
                },
                rows=[],
            )

        for row_index, raw_row in enumerate(reader, start=2):
            raw_date = (raw_row.get("date") or "").strip()
            symbol = (raw_row.get("symbol") or "").strip()
            is_duplicate = (raw_date, symbol) in seen_keys
            is_blank_date = raw_date == ""
            is_blank_symbol = symbol == ""
            is_valid_symbol = symbol != "" and is_a_share_symbol(symbol)

            if not is_blank_date:
                dates.add(raw_date)
            if symbol:
                mapped_symbols.add(symbol)
            if is_duplicate:
                duplicate_keys += 1
            if is_blank_date:
                blank_date_rows += 1
            if is_blank_symbol:
                blank_symbol_rows += 1
            if symbol and not is_valid_symbol:
                invalid_symbol_rows += 1
            seen_keys.add((raw_date, symbol))

            rows.append(
                {
                    "row_number": row_index,
                    "date": raw_date,
                    "symbol": symbol,
                    "blank_date": is_blank_date,
                    "blank_symbol": is_blank_symbol,
                    "invalid_symbol": symbol != "" and not is_valid_symbol,
                    "duplicate_date_symbol": is_duplicate,
                    "in_expected_symbols": None if expected_symbols is None or symbol == "" else symbol in expected_symbols,
                }
            )

    missing_expected = sorted((expected_symbols or set()) - mapped_symbols)
    extra_mapped = sorted(mapped_symbols - (expected_symbols or set())) if expected_symbols is not None else []
    rows_by_date: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        row_date = str(row["date"])
        symbol = str(row["symbol"])
        if row_date and symbol and not row["invalid_symbol"]:
            rows_by_date[row_date].add(symbol)

    pool_sizes = [len(symbols) for symbols in rows_by_date.values()]
    summary = {
        "row_count": len(rows),
        "date_count": len(dates),
        "mapped_symbol_count": len(mapped_symbols),
        "missing_columns": [],
        "duplicate_date_symbol_rows": duplicate_keys,
        "blank_date_rows": blank_date_rows,
        "blank_symbol_rows": blank_symbol_rows,
        "invalid_symbol_rows": invalid_symbol_rows,
        "min_pool_size": min(pool_sizes, default=0),
        "max_pool_size": max(pool_sizes, default=0),
        "missing_expected_symbols": len(missing_expected),
        "extra_mapped_symbols": len(extra_mapped),
        "missing_expected_symbol_list": missing_expected,
        "extra_mapped_symbol_list": extra_mapped,
    }
    return MappingQualityReport(summary=summary, rows=rows)


def save_data_quality_report(
    report: DataQualityReport,
    output_dir: Path,
    *,
    prefix: str = "data_quality",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{prefix}_report.csv"
    json_path = output_dir / f"{prefix}_report.json"

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "row_count",
                "start_date",
                "end_date",
                "missing_common_dates",
                "missing_adjusted_close",
                "missing_open",
                "missing_vwap",
                "zero_volume_days",
                "suspended_days",
                "limit_up_days",
                "limit_down_days",
                "st_days",
                "custom_limit_rate_days",
                "untradable_days",
                "cannot_buy_days",
                "cannot_sell_days",
                "max_abs_return",
                "abnormal_return_days",
            ],
        )
        writer.writeheader()
        for row in report.symbols:
            writer.writerow(asdict(row))

    payload = {
        "summary": report.summary,
        "symbols": [asdict(row) for row in report.symbols],
        "daily_counts": report.daily_counts,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    return {
        f"{prefix}_report_csv": csv_path,
        f"{prefix}_report_json": json_path,
    }


def save_stock_pool_quality_report(
    report: MappingQualityReport,
    output_dir: Path,
    *,
    prefix: str = "stock_pool_quality",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{prefix}_report.csv"
    json_path = output_dir / f"{prefix}_report.json"

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_number",
                "date",
                "symbol",
                "blank_date",
                "blank_symbol",
                "invalid_symbol",
                "duplicate_date_symbol",
                "in_expected_symbols",
            ],
        )
        writer.writeheader()
        for row in report.rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"summary": report.summary, "rows": report.rows},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return {
        f"{prefix}_report_csv": csv_path,
        f"{prefix}_report_json": json_path,
    }


def save_benchmark_quality_report(
    report: BenchmarkQualityReport,
    output_dir: Path,
    *,
    prefix: str = "benchmark_quality",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{prefix}_report.csv"
    json_path = output_dir / f"{prefix}_report.json"

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "close",
                "adjusted_close_missing",
                "daily_return",
                "abnormal_return",
            ],
        )
        writer.writeheader()
        for row in report.rows:
            writer.writerow(asdict(row))

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"summary": report.summary, "rows": [asdict(row) for row in report.rows]},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return {
        f"{prefix}_report_csv": csv_path,
        f"{prefix}_report_json": json_path,
    }


def save_mapping_quality_report(
    report: MappingQualityReport,
    output_dir: Path,
    *,
    prefix: str = "symbol_group_quality",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{prefix}_report.csv"
    json_path = output_dir / f"{prefix}_report.json"

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_number",
                "symbol",
                "group",
                "blank_symbol",
                "blank_group",
                "duplicate_symbol",
                "in_expected_symbols",
            ],
        )
        writer.writeheader()
        for row in report.rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"summary": report.summary, "rows": report.rows},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return {
        f"{prefix}_report_csv": csv_path,
        f"{prefix}_report_json": json_path,
    }


def _daily_returns(bars: list[PriceBar]) -> list[float]:
    returns: list[float] = []
    ordered = sorted(bars, key=lambda item: item.date)
    for index in range(1, len(ordered)):
        previous = ordered[index - 1].adjusted_close or ordered[index - 1].close
        current = ordered[index].adjusted_close or ordered[index].close
        returns.append(current / previous - 1.0)
    return returns
