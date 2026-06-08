from __future__ import annotations


def select_symbols(scores: dict[str, float], top_n: int, *, mode: str = "top") -> list[str]:
    if top_n <= 0:
        raise ValueError("top_n must be greater than 0.")
    if mode not in {"top", "bottom"}:
        raise ValueError("mode must be one of: top, bottom.")
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=mode == "top")
    return [symbol for symbol, _score in ranked[:top_n]]
