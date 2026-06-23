from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .exceptions import InsufficientDataError
from .factors import calculate_factor_score_records
from .market import price_for_bar
from .models import FactorScoreRecord
from .portfolio_optimizer import PortfolioOptimizer, ScipyPortfolioOptimizer
from .strategy_api import AbstractStrategy, StrategyContext


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies (Legacy)."""

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


class DefaultBuiltinStrategy(AbstractStrategy):
    """
    The default builtin strategy encapsulating TopN selection, external scores handling, 
    and Scipy-based allocations.
    """

    def execute(
        self,
        context: StrategyContext,
    ) -> tuple[dict[str, float], dict[str, FactorScoreRecord]]:
        
        # 1. Generate or load factor score records
        all_factor_records = self._factor_records_for_date(context)

        # 2. Filter by allowed stock pool and basic tradability rules
        available_records = {
            sym: rec for sym, rec in all_factor_records.items()
            if self._is_in_allowed_stock_pool(sym, context.allowed_symbols) 
            and self._can_be_selected(sym, context)
        }

        config = context.config
        
        # 3. Allocation logic
        if config.allocation_model in {"max_sharpe", "min_variance"}:
            historical_returns = {}
            lookback = 60
            for sym in available_records:
                bars = context.aligned_history[sym][max(0, context.index-lookback):context.index+1]
                if len(bars) > 1:
                    rets = []
                    for i in range(1, len(bars)):
                        prev_p = price_for_bar(bars[i-1], config)
                        curr_p = price_for_bar(bars[i], config)
                        rets.append(curr_p / prev_p - 1.0 if prev_p > 0 else 0.0)
                    historical_returns[sym] = rets

            # Filter top N before giving it to optimizer to avoid OOM or slow solving
            strategy = TopNFactorStrategy(top_n=config.top_n, mode=config.selection_mode, allocation_model="equal")
            unconstrained = strategy.generate_target_weights(context.current_date, available_records)
            filtered_records = {s: available_records[s] for s in unconstrained}
            for s in context.locked_symbols:
                if s in available_records:
                    filtered_records[s] = available_records[s]

            scipy_optimizer = ScipyPortfolioOptimizer(
                objective=config.allocation_model,
                target_cash_weight=config.target_cash_weight,
                max_position_weight=config.max_position_weight,
                max_group_positions=config.max_group_positions,
                symbol_groups=context.symbol_groups,
                target_turnover=config.target_turnover,
                target_volatility=config.target_volatility,
            )
            target_weights = scipy_optimizer.generate_target_weights(
                current_date=context.current_date,
                signals=filtered_records,
                historical_returns=historical_returns,
                locked_symbols=context.locked_symbols,
                current_weights=context.current_weights,
            )
        else:
            strategy = TopNFactorStrategy(
                top_n=config.top_n,
                mode=config.selection_mode,
                allocation_model=config.allocation_model,
            )
            unconstrained_weights = strategy.generate_target_weights(context.current_date, available_records)
            constrained_optimizer = PortfolioOptimizer(
                max_position_weight=config.max_position_weight,
                max_group_positions=config.max_group_positions,
                target_cash_weight=config.target_cash_weight,
                symbol_groups=context.symbol_groups,
            )
            target_weights = constrained_optimizer.optimize(unconstrained_weights, context.locked_symbols)

        # 4. Generate final score records for the selected symbols for reporting
        selected = set(target_weights.keys())
        final_records = self._factor_records_for_date(context, selected_symbols=selected)
        
        return target_weights, final_records

    def _factor_records_for_date(
        self,
        context: StrategyContext,
        selected_symbols: set[str] | None = None,
    ) -> dict[str, FactorScoreRecord]:
        config = context.config
        current_date = context.current_date
        external_scores = context.external_scores

        if config.score_source == "builtin":
            external_scores = None
            
        if config.score_source == "external" and external_scores is None:
            raise InsufficientDataError(
                f"External factor scores are required for {current_date.isoformat()} "
                "when score_source is 'external'."
            )
            
        if external_scores is None:
            return calculate_factor_score_records(
                context.aligned_history,
                context.index,
                config,
                selected_symbols=selected_symbols,
            )

        selected_symbols_set = selected_symbols or set()
        return {
            symbol: FactorScoreRecord(
                date=current_date,
                symbol=symbol,
                total_score=score,
                selected=symbol in selected_symbols_set,
                raw_scores={"external": score},
                normalized_scores={"external": score},
            )
            for symbol, score in external_scores.items()
            if symbol in context.aligned_history and context.index < len(context.aligned_history[symbol])
        }

    def _is_in_allowed_stock_pool(self, symbol: str, allowed_symbols: set[str] | None) -> bool:
        return allowed_symbols is None or symbol in allowed_symbols

    def _can_be_selected(self, symbol: str, context: StrategyContext) -> bool:
        bar = context.aligned_history[symbol][context.index]
        if symbol in context.current_holdings:
            return bar.tradable or bar.can_buy or bar.can_sell
        from .execution_model import is_buyable
        return is_buyable(bar)
