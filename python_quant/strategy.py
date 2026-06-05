from __future__ import annotations


def select_symbols(scores: dict[str, float], top_n: int) -> list[str]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _score in ranked[:top_n]]
