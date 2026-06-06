from __future__ import annotations

import csv
from pathlib import Path

from .models import PriceBar


def load_price_bars_from_csv(csv_path: str | Path) -> list[PriceBar]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    bars: list[PriceBar] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"CSV missing required columns: {missing_str}")

        for row in reader:
            bars.append(
                PriceBar(
                    date=row["date"].strip(),
                    symbol=row["symbol"].strip(),
                    close=float(row["close"]),
                )
            )

    bars.sort(key=lambda item: (item.date, item.symbol))
    return bars
