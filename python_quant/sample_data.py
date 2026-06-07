from __future__ import annotations

from datetime import date, timedelta
from math import sin

from .models import PriceBar


def generate_demo_bars(days: int = 80) -> list[PriceBar]:
    symbols = ["000001", "600036", "600519", "601318", "300750"]
    start = date(2024, 1, 2)
    bars: list[PriceBar] = []

    for day_index in range(days):
        current_date = start + timedelta(days=day_index)
        if current_date.weekday() >= 5:
            continue

        trading_index = len({bar.date for bar in bars})
        for symbol_index, symbol in enumerate(symbols):
            base = 90 + symbol_index * 12
            trend = (symbol_index - 1) * 0.35 * trading_index
            seasonal = sin((trading_index + symbol_index * 3) / 4.0) * (2.0 + symbol_index * 0.3)
            mean_shift = ((trading_index + symbol_index) % 11 - 5) * 0.18
            close = round(base + trend + seasonal + mean_shift, 2)
            bars.append(
                PriceBar(
                    date=current_date,
                    symbol=symbol,
                    close=max(close, 1.0),
                    adjusted_close=max(close, 1.0),
                )
            )

    return bars
