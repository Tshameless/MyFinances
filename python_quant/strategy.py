from __future__ import annotations


def select_symbols(scores: dict[str, float], top_n: int) -> list[str]:
    if top_n <= 0:
        raise ValueError("top_n must be greater than 0.")
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _score in ranked[:top_n]]
