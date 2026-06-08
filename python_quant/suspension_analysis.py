from __future__ import annotations

from collections import defaultdict

from .models import PriceBar


def build_suspension_analysis(price_bars: list[PriceBar] | None) -> dict[str, object]:
    bars = price_bars or []
    suspended_bars = [bar for bar in bars if bar.is_suspended]
    bars_by_symbol: defaultdict[str, list[PriceBar]] = defaultdict(list)
    bars_by_date: defaultdict[str, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        if bar.is_suspended:
            bars_by_symbol[bar.symbol].append(bar)
            bars_by_date[bar.date.isoformat()].append(bar)

    symbol_rows = [
        {
            "symbol": symbol,
            "suspended_days": len(symbol_bars),
            "first_suspended_date": symbol_bars[0].date.isoformat(),
            "last_suspended_date": symbol_bars[-1].date.isoformat(),
        }
        for symbol, symbol_bars in sorted(bars_by_symbol.items())
    ]
    daily_rows = [
        {
            "date": trading_date,
            "suspended_symbol_count": len(date_bars),
            "symbols": "|".join(sorted(bar.symbol for bar in date_bars)),
        }
        for trading_date, date_bars in sorted(bars_by_date.items())
    ]
    row_count = len(bars)
    summary = {
        "row_count": row_count,
        "suspended_bar_count": len(suspended_bars),
        "suspended_bar_ratio": 0.0 if row_count == 0 else len(suspended_bars) / row_count,
        "suspended_symbol_count": len(bars_by_symbol),
        "suspended_date_count": len(bars_by_date),
        "max_daily_suspended_symbol_count": max(
            (len(date_bars) for date_bars in bars_by_date.values()),
            default=0,
        ),
    }
    return {"summary": summary, "symbols": symbol_rows, "daily": daily_rows}
