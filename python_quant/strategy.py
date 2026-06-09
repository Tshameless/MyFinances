from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .models import FactorScoreRecord


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def generate_target_weights(
        self,
        current_date: date,
        factor_scores: dict[str, FactorScoreRecord],
    ) -> dict[str, float]:
        """
        Generate unconstrained target weights for symbols.
        Returns a dictionary mapping symbol to target weight (summing up to <= 1.0).
        """
        pass


class TopNFactorStrategy(BaseStrategy):
    """A strategy that selects top N symbols based on factor scores."""

    def __init__(self, top_n: int, mode: str = "top", allocation_model: str = "equal"):
        if top_n <= 0:
            raise ValueError("top_n must be greater than 0.")
        if mode not in {"top", "bottom"}:
            raise ValueError("mode must be one of: top, bottom.")
        if allocation_model == "equal_weight":
            allocation_model = "equal"
        if allocation_model not in {"equal", "score_weighted"}:
            raise ValueError("allocation_model must be one of: equal, score_weighted.")
        self.top_n = top_n
        self.mode = mode
        self.allocation_model = allocation_model

    def generate_target_weights(
        self,
        current_date: date,
        factor_scores: dict[str, FactorScoreRecord],
    ) -> dict[str, float]:
        if not factor_scores:
            return {}

        ranked = sorted(
            factor_scores.values(),
            key=lambda record: record.total_score,
            reverse=(self.mode == "top"),
        )
        selected = ranked[:self.top_n]
        if not selected:
            return {}

        weights: dict[str, float] = {}
        if self.allocation_model == "equal":
            weight_per_symbol = 1.0 / len(selected)
            for record in selected:
                weights[record.symbol] = weight_per_symbol
        elif self.allocation_model == "score_weighted":
            total_positive_score = sum(r.total_score for r in selected if r.total_score > 0)
            if total_positive_score <= 0:
                weight_per_symbol = 1.0 / len(selected)
                for record in selected:
                    weights[record.symbol] = weight_per_symbol
            else:
                for record in selected:
                    if record.total_score > 0:
                        weights[record.symbol] = record.total_score / total_positive_score
                    else:
                        weights[record.symbol] = 0.0
        return weights
