from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date

from .models import FactorScoreRecord, PriceBar


class AlphaModel(ABC):
    """
    Generates alpha signals (factor scores) for symbols.
    """

    @abstractmethod
    def generate_signals(
        self,
        current_date: date,
        aligned_history: dict[str, list[PriceBar]],
        index: int,
        allowed_symbols: set[str] | None,
    ) -> dict[str, FactorScoreRecord]:
        """
        Evaluate market history up to `index` and return factor scores.
        """
        pass


class PortfolioConstructionModel(ABC):
    """
    Takes alpha signals and outputs target portfolio weights.
    """

    @abstractmethod
    def generate_target_weights(
        self,
        current_date: date,
        signals: dict[str, FactorScoreRecord],
        historical_returns: dict[str, list[float]] | None = None,
        locked_symbols: Iterable[str] = (),
    ) -> dict[str, float]:
        """
        Generate constrained target weights.
        """
        pass

