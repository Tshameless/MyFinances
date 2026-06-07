from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "python"

DEFAULT_FACTOR_WEIGHTS = {
    "momentum": 0.5,
    "mean_reversion": 0.2,
    "low_volatility": 0.3,
}
SUPPORTED_FACTORS = frozenset(DEFAULT_FACTOR_WEIGHTS)


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    top_n: int = 3
    lookback_momentum: int = 20
    lookback_mean_reversion: int = 5
    lookback_volatility: int = 20
    rebalance_every_n_days: int = 5
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0005
    stamp_duty_rate: float = 0.0
    price_field: str = "adjusted_close"
    output_dir: Path = OUTPUT_DIR
    symbol_name_csv: Path | None = None
    factor_weights: dict[str, float] = field(
        default_factory=lambda: DEFAULT_FACTOR_WEIGHTS.copy()
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", self.output_dir.resolve())
        if self.symbol_name_csv is not None:
            object.__setattr__(self, "symbol_name_csv", self.symbol_name_csv.resolve())
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than 0.")
        if self.top_n <= 0:
            raise ValueError("top_n must be greater than 0.")
        if self.rebalance_every_n_days <= 0:
            raise ValueError("rebalance_every_n_days must be greater than 0.")
        if min(
            self.lookback_momentum,
            self.lookback_mean_reversion,
            self.lookback_volatility,
        ) <= 0:
            raise ValueError("All lookback windows must be greater than 0.")
        if min(self.commission_rate, self.slippage_rate, self.stamp_duty_rate) < 0:
            raise ValueError("Cost rates cannot be negative.")
        if self.price_field not in {"close", "adjusted_close"}:
            raise ValueError("price_field must be one of: close, adjusted_close.")
        if not self.factor_weights:
            raise ValueError("factor_weights cannot be empty.")
        unsupported_factors = sorted(set(self.factor_weights) - SUPPORTED_FACTORS)
        if unsupported_factors:
            unsupported_text = ", ".join(unsupported_factors)
            raise ValueError(
                f"factor_weights contains unsupported factors: {unsupported_text}."
            )
        if any(weight < 0 for weight in self.factor_weights.values()):
            raise ValueError("factor_weights cannot contain negative values.")
        if sum(self.factor_weights.values()) <= 0:
            raise ValueError("factor_weights must sum to a positive value.")

    @property
    def per_side_cost_rate(self) -> float:
        return self.commission_rate + self.slippage_rate

    @property
    def max_lookback(self) -> int:
        return max(
            self.lookback_momentum,
            self.lookback_mean_reversion,
            self.lookback_volatility,
        )

    @property
    def normalized_factor_weights(self) -> dict[str, float]:
        total_weight = sum(self.factor_weights.values())
        return {
            factor_name: weight / total_weight
            for factor_name, weight in self.factor_weights.items()
        }


def load_config_overrides_from_toml(config_path: str | Path) -> dict[str, object]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    raw_config = payload.get("backtest")
    if not isinstance(raw_config, dict):
        raise ValueError("Config file must contain a [backtest] table.")

    normalized: dict[str, object] = {}
    simple_fields = [
        "initial_cash",
        "top_n",
        "lookback_momentum",
        "lookback_mean_reversion",
        "lookback_volatility",
        "rebalance_every_n_days",
        "commission_rate",
        "slippage_rate",
        "stamp_duty_rate",
        "price_field",
    ]
    for field_name in simple_fields:
        if field_name in raw_config:
            normalized[field_name] = raw_config[field_name]

    if "output_dir" in raw_config:
        output_dir = Path(str(raw_config["output_dir"]))
        if not output_dir.is_absolute():
            output_dir = (path.parent / output_dir).resolve()
        normalized["output_dir"] = output_dir

    if "symbol_name_csv" in raw_config and raw_config["symbol_name_csv"] not in ("", None):
        symbol_name_csv = Path(str(raw_config["symbol_name_csv"]))
        if not symbol_name_csv.is_absolute():
            symbol_name_csv = (path.parent / symbol_name_csv).resolve()
        normalized["symbol_name_csv"] = symbol_name_csv

    if "factor_weights" in raw_config:
        factor_weights = raw_config["factor_weights"]
        if not isinstance(factor_weights, dict):
            raise ValueError("factor_weights must be a TOML table.")
        normalized["factor_weights"] = {
            str(name): float(value)
            for name, value in factor_weights.items()
        }

    return normalized


def load_sweep_overrides_from_toml(config_path: str | Path) -> dict[str, list[object]]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    raw_sweep = payload.get("sweep")
    if raw_sweep is None:
        return {}
    if not isinstance(raw_sweep, dict):
        raise ValueError("Config file [sweep] section must be a TOML table.")

    allowed_fields = {
        "top_n",
        "lookback_momentum",
        "lookback_mean_reversion",
        "lookback_volatility",
        "rebalance_every_n_days",
        "commission_rate",
        "slippage_rate",
        "stamp_duty_rate",
        "price_field",
    }
    normalized: dict[str, list[object]] = {}
    for field_name, values in raw_sweep.items():
        if field_name not in allowed_fields:
            raise ValueError(f"Unsupported sweep field: {field_name}")
        if not isinstance(values, list) or not values:
            raise ValueError(f"Sweep field '{field_name}' must be a non-empty TOML array.")
        normalized[field_name] = list(values)

    return normalized
