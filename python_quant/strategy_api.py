from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .config import BacktestConfig
from .models import FactorScoreRecord, PriceBar


@dataclass(frozen=True)
class StrategyContext:
    """Encapsulates all runtime data needed for a strategy execution step."""
    current_date: date
    aligned_history: dict[str, list[PriceBar]]
    index: int
    allowed_symbols: set[str] | None
    locked_symbols: list[str]
    current_holdings: tuple[str, ...]
    current_weights: dict[str, float]
    config: BacktestConfig
    external_scores: dict[str, float] | None
    symbol_groups: dict[str, str] | None


class AbstractStrategy(ABC):
    """
    Standard plugin interface for strategies.
    Strategies should implement this to provide target weights and factor score records.
    """

    @abstractmethod
    def execute(
        self,
        context: StrategyContext,
    ) -> tuple[dict[str, float], dict[str, FactorScoreRecord]]:
        """
        Execute the strategy logic for the current bar context.
        Returns:
            - target_weights: A dictionary mapping symbol to target weight (summing up to <= 1.0).
            - factor_records: A dictionary mapping symbol to FactorScoreRecord.
        """
        pass


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
        current_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """
        Generate constrained target weights.
        """
        pass

