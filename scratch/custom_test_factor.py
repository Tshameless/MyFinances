from python_quant.factor_registry import register_factor
from python_quant.config import BacktestConfig

@register_factor("custom_momentum")
def compute_custom_momentum(closes: list[float], config: BacktestConfig) -> float:
    if len(closes) < 11:
        return 0.0
    return closes[-1] / closes[-11] - 1.0
