from __future__ import annotations

from typing import Iterable


class PortfolioOptimizer:
    """Applies constraints to unconstrained target weights."""

    def __init__(
        self,
        max_position_weight: float | None = None,
        max_group_positions: int | None = None,
        target_cash_weight: float = 0.0,
        symbol_groups: dict[str, str] | None = None,
    ):
        self.max_position_weight = max_position_weight
        self.max_group_positions = max_group_positions
        self.target_cash_weight = target_cash_weight
        self.symbol_groups = symbol_groups or {}

    def optimize(
        self,
        unconstrained_weights: dict[str, float],
        locked_symbols: Iterable[str] = (),
    ) -> dict[str, float]:
        """
        Takes unconstrained weights and locked symbols, returns constrained target weights.
        """
        weights: dict[str, float] = {}
        group_counts: dict[str, int] = {}
        
        for symbol in locked_symbols:
            weights[symbol] = unconstrained_weights.get(symbol, 0.0)
            group_key = self._group_key(symbol)
            group_counts[group_key] = group_counts.get(group_key, 0) + 1

        sorted_requests = sorted(
            [s for s in unconstrained_weights if s not in locked_symbols],
            key=lambda x: unconstrained_weights[x],
            reverse=True,
        )

        for symbol in sorted_requests:
            group_key = self._group_key(symbol)
            if self.max_group_positions is not None and group_counts.get(group_key, 0) >= self.max_group_positions:
                continue
            
            w = unconstrained_weights[symbol]
            if self.max_position_weight is not None:
                w = min(w, self.max_position_weight)
            
            weights[symbol] = w
            group_counts[group_key] = group_counts.get(group_key, 0) + 1

        investable_ratio = max(0.0, 1.0 - self.target_cash_weight)
        
        total_weight = sum(weights.values())
        if total_weight > investable_ratio and total_weight > 0:
            scale_factor = investable_ratio / total_weight
            for symbol in weights:
                weights[symbol] *= scale_factor
                
        return weights

    def _group_key(self, symbol: str) -> str:
        return self.symbol_groups.get(symbol, f"__symbol__:{symbol}")
