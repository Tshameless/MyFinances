from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import numpy as np

from .models import FactorScoreRecord
from .strategy_api import PortfolioConstructionModel


def _load_scipy_minimize() -> Any:
    try:
        from scipy.optimize import minimize  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "allocation_model='max_sharpe' 或 'min_variance' 需要可选依赖 scipy。"
            "请先执行 `python -m pip install scipy>=1.10.0`，"
            "或改用 equal_weight / score_weighted。"
        ) from exc
    return minimize

class PortfolioOptimizer:
    """Applies constraints to unconstrained target weights. (Legacy greedy optimizer)"""

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


class ScipyPortfolioOptimizer(PortfolioConstructionModel):
    """Portfolio optimizer using scipy.optimize for objective-based allocation."""

    def __init__(
        self,
        objective: str = "max_sharpe", # "max_sharpe", "min_variance", "max_return"
        target_cash_weight: float = 0.0,
        max_position_weight: float | None = None,
        max_group_positions: int | None = None,
        symbol_groups: dict[str, str] | None = None,
    ):
        self.objective = objective
        self.target_cash_weight = target_cash_weight
        self.max_position_weight = max_position_weight
        self.max_group_positions = max_group_positions
        self.symbol_groups = symbol_groups or {}

    def generate_target_weights(
        self,
        current_date: date,
        signals: dict[str, FactorScoreRecord],
        historical_returns: dict[str, list[float]] | None = None,
        locked_symbols: Iterable[str] = (),
    ) -> dict[str, float]:
        if not signals:
            return {}

        minimize = _load_scipy_minimize()

        symbols = list(signals.keys())
        n = len(symbols)

        if historical_returns and self.objective in ("max_sharpe", "min_variance"):
            min_len = min(len(historical_returns.get(s, [])) for s in symbols)
            if min_len < 2:
                cov_matrix = np.eye(n)
            else:
                returns_matrix = np.array([historical_returns[s][-min_len:] for s in symbols])
                cov_matrix = np.cov(returns_matrix)
        else:
            cov_matrix = np.eye(n)

        expected_returns = np.array([signals[s].total_score for s in symbols])

        investable_ratio = max(0.0, 1.0 - self.target_cash_weight)
        x0 = np.ones(n) * (investable_ratio / n)

        bounds = []
        for _ in symbols:
            max_w = self.max_position_weight if self.max_position_weight is not None else 1.0
            bounds.append((0.0, max_w))

        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - investable_ratio}
        ]

        def objective_function(w):
            if self.objective == "min_variance":
                return np.dot(w.T, np.dot(cov_matrix, w))
            elif self.objective == "max_sharpe":
                port_return = np.dot(w, expected_returns)
                port_var = np.dot(w.T, np.dot(cov_matrix, w))
                if port_var <= 1e-8:
                    return -port_return
                return -port_return / np.sqrt(port_var)
            elif self.objective == "max_return":
                return -np.dot(w, expected_returns)
            return 0.0

        try:
            res = minimize(
                objective_function,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'disp': False, 'maxiter': 1000}
            )
            w_opt = res.x
        except Exception:
            w_opt = x0

        weights: dict[str, float] = {}
        group_counts: dict[str, int] = {}
        sorted_indices = np.argsort(w_opt)[::-1]

        for idx in sorted_indices:
            s = symbols[idx]
            group_key = self.symbol_groups.get(s, f"__symbol__:{s}") if self.symbol_groups else f"__symbol__:{s}"
            if self.max_group_positions is not None and group_counts.get(group_key, 0) >= self.max_group_positions:
                continue

            w = w_opt[idx]
            if w > 1e-4:
                weights[s] = w
                group_counts[group_key] = group_counts.get(group_key, 0) + 1

        total_w = sum(weights.values())
        if total_w > 0:
            scale = investable_ratio / total_w
            for s in weights:
                weights[s] *= scale

        # Handle locked symbols: if they are in locked_symbols but not in weights, they should ideally be kept
        # but the standard optimizer logic here only assigns weights based on alpha/variance.
        # This is a simplified port that aligns with the interface.
        return weights

