from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

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
    zero_volume_days: int
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


def build_price_data_quality_report(
    bars: list[PriceBar],
    *,
    abnormal_return_threshold: float = 0.11,
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
            },
            symbols=[],
            daily_counts=[],
        )

    bars_by_symbol: dict[str, list[PriceBar]] = defaultdict(list)
    bars_by_date: dict[object, list[PriceBar]] = defaultdict(list)
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
                zero_volume_days=sum(1 for bar in ordered if bar.volume == 0),
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
        }
        for trading_date in all_dates
    ]
    summary = {
        "row_count": len(bars),
        "symbol_count": len(bars_by_symbol),
        "date_count": len(all_dates),
        "start_date": all_dates[0].isoformat(),
        "end_date": all_dates[-1].isoformat(),
        "abnormal_return_threshold": abnormal_return_threshold,
        "symbols_with_missing_common_dates": sum(
            1 for row in symbol_rows if row.missing_common_dates > 0
        ),
        "symbols_with_missing_adjusted_close": sum(
            1 for row in symbol_rows if row.missing_adjusted_close > 0
        ),
        "symbols_with_abnormal_returns": sum(
            1 for row in symbol_rows if row.abnormal_return_days > 0
        ),
        "min_daily_symbol_count": min(item["symbol_count"] for item in daily_counts),
        "max_daily_symbol_count": max(item["symbol_count"] for item in daily_counts),
    }
    return DataQualityReport(summary=summary, symbols=symbol_rows, daily_counts=daily_counts)


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
                "zero_volume_days",
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


def _daily_returns(bars: list[PriceBar]) -> list[float]:
    returns: list[float] = []
    ordered = sorted(bars, key=lambda item: item.date)
    for index in range(1, len(ordered)):
        previous = ordered[index - 1].adjusted_close or ordered[index - 1].close
        current = ordered[index].adjusted_close or ordered[index].close
        returns.append(current / previous - 1.0)
    return returns
