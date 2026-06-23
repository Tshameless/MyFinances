from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any
from datetime import date

from .models import PriceBar, FactorScoreRecord
from .config import BacktestConfig

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class FactorPipeline:
    """
    A unified pipeline to transform PriceBars into factor scores using Pandas vectorization.
    It takes raw PriceBars, converts them into a DataFrame, calculates multiple cross-sectional
    or time-series factors, and outputs a dictionary of scores by date and symbol.
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.factors: List[Dict[str, Any]] = []
        
    def add_factor(self, factor_func: Callable, name: str, weight: float = 1.0) -> None:
        """
        Register a pandas-based factor function.
        factor_func should have signature (df: pd.DataFrame, config: BacktestConfig) -> pd.Series
        """
        self.factors.append({"func": factor_func, "name": name, "weight": weight})
        
    def run(self, bars: List[PriceBar]) -> Dict[date, Dict[str, float]]:
        """
        Runs the pipeline and outputs normalized factor scores.
        Returns: {date: {symbol: score}}
        """
        if not HAS_PANDAS:
            raise ImportError("Pandas is required to run FactorPipeline.")
            
        if not bars:
            return {}
            
        df = pd.DataFrame([
            {
                "date": b.date,
                "symbol": b.symbol,
                "close": b.close,
                "open": b.open,
                "volume": b.volume,
            } for b in bars
        ])
        
        df = df.sort_values(["symbol", "date"]).set_index(["symbol", "date"])
        
        results = {}
        for factor_info in self.factors:
            name = factor_info["name"]
            func = factor_info["func"]
            # Apply factor calculation
            series = func(df, self.config)
            results[name] = series * factor_info["weight"]
            
        if not results:
            return {}
            
        # Sum weighted scores
        combined = pd.DataFrame(results).sum(axis=1)
        
        # Cross-sectional normalization function
        def _normalize(s):
            s_min = s.min()
            s_max = s.max()
            if s_max == s_min:
                return s - s_min
            return (s - s_min) / (s_max - s_min)
            
        # Swap levels to groupby date for cross-sectional normalization
        combined = combined.swaplevel().sort_index()
        normalized = combined.groupby(level='date', group_keys=False).apply(_normalize)
        
        output: Dict[date, Dict[str, float]] = {}
        for (d, sym), val in normalized.items():
            if pd.isna(val):
                continue
            output.setdefault(d, {})[sym] = float(val)
            
        return output

# --- Builtin Pandas factor implementations ---

def pd_momentum(df: pd.DataFrame, config: BacktestConfig) -> pd.Series:
    lookback = config.lookback_momentum
    return df.groupby(level='symbol')['close'].pct_change(periods=lookback)

def pd_mean_reversion(df: pd.DataFrame, config: BacktestConfig) -> pd.Series:
    lookback = config.lookback_mean_reversion
    return -df.groupby(level='symbol')['close'].pct_change(periods=lookback)

def pd_low_volatility(df: pd.DataFrame, config: BacktestConfig) -> pd.Series:
    lookback = config.lookback_volatility
    daily_ret = df.groupby(level='symbol')['close'].pct_change()
    # Dropping level 0 because groupby+rolling returns a multi-index with an extra symbol level
    return -daily_ret.groupby(level='symbol').rolling(window=lookback).std().droplevel(0)
