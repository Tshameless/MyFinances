from __future__ import annotations

import csv
from pathlib import Path

from .models import FactorScoreRecord, TradeAttemptRecord, TradeRecord

_HUMAN_READABLE_ENCODING = "utf-8-sig"


def save_trades_csv(
    trades: list[TradeRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
    format_money,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "trades.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("side"),
                display_label("shares"),
                display_label("price"),
                display_label("gross_value"),
                "成交金额展示 / gross_value_display",
                display_label("commission"),
                display_label("slippage"),
                display_label("transfer_fee"),
                display_label("stamp_duty"),
                display_label("total_cost"),
                "总成本展示 / total_cost_display",
                display_label("cash_change"),
                "现金变化展示 / cash_change_display",
                display_label("reason"),
            ]
        )
        for trade in trades:
            writer.writerow(
                [
                    trade.date.isoformat(),
                    trade.symbol,
                    format_symbol(trade.symbol),
                    trade.side,
                    str(trade.shares),
                    f"{trade.price:.4f}",
                    f"{trade.gross_value:.2f}",
                    format_money(trade.gross_value),
                    f"{trade.commission:.2f}",
                    f"{trade.slippage:.2f}",
                    f"{trade.transfer_fee:.2f}",
                    f"{trade.stamp_duty:.2f}",
                    f"{trade.total_cost:.2f}",
                    format_money(trade.total_cost),
                    f"{trade.cash_change:.2f}",
                    format_money(trade.cash_change),
                    trade.reason,
                ]
            )

    return target_path


def save_trade_attempts_csv(
    attempts: list[TradeAttemptRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
    format_money,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "trade_attempts.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("side"),
                display_label("target_shares"),
                display_label("price"),
                display_label("cash"),
                "现金展示 / cash_display",
                display_label("reason"),
            ]
        )
        for attempt in attempts:
            writer.writerow(
                [
                    attempt.date.isoformat(),
                    attempt.symbol,
                    format_symbol(attempt.symbol),
                    attempt.side,
                    str(attempt.target_shares),
                    f"{attempt.price:.4f}",
                    f"{attempt.cash:.2f}",
                    format_money(attempt.cash),
                    attempt.reason,
                ]
            )

    return target_path


def save_factor_scores_csv(
    records: list[FactorScoreRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "factor_scores.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("momentum"),
                display_label("mean_reversion"),
                display_label("low_volatility"),
                display_label("normalized_momentum"),
                display_label("normalized_mean_reversion"),
                display_label("normalized_low_volatility"),
                display_label("total_score"),
                display_label("selected"),
            ]
        )
        for record in records:
            writer.writerow(
                [
                    record.date.isoformat(),
                    record.symbol,
                    format_symbol(record.symbol),
                    f"{record.momentum:.8f}",
                    f"{record.mean_reversion:.8f}",
                    f"{record.low_volatility:.8f}",
                    f"{record.normalized_momentum:.8f}",
                    f"{record.normalized_mean_reversion:.8f}",
                    f"{record.normalized_low_volatility:.8f}",
                    f"{record.total_score:.8f}",
                    "1" if record.selected else "0",
                ]
            )

    return target_path
