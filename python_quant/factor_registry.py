from __future__ import annotations
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import BacktestConfig

# A factor calculation function signature:
# (closes: list[float], config: BacktestConfig) -> float
FactorCalculator = Callable[[list[float], "BacktestConfig"], float]

_registry: dict[str, FactorCalculator] = {}

def register_factor(name: str) -> Callable[[FactorCalculator], FactorCalculator]:
    """Decorator to register a custom factor calculation function."""
    def decorator(func: FactorCalculator) -> FactorCalculator:
        _registry[name] = func
        return func
    return decorator

def get_registered_factors() -> dict[str, FactorCalculator]:
    """Retrieve all registered factor calculation functions, dynamically loading built-ins on first call."""
    if not _registry:
        # Dynamically import factors to trigger registration of built-ins
        from . import factors  # noqa: F401
    return _registry
