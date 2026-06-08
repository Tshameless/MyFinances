from __future__ import annotations

import tomllib
from collections.abc import KeysView, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import cast

from .exceptions import ConfigValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "python"

DEFAULT_FACTOR_WEIGHTS = {
    "momentum": 0.5,
    "mean_reversion": 0.2,
    "low_volatility": 0.3,
}
class DynamicSupportedFactors:
    def __contains__(self, item: object) -> bool:
        from .factor_registry import get_registered_factors
        return item in get_registered_factors()

    def __sub__(self, other: object) -> set[str]:
        from .factor_registry import get_registered_factors
        return set(get_registered_factors()) - set(other)  # type: ignore

    def __rsub__(self, other: object) -> set[str]:
        from .factor_registry import get_registered_factors
        return set(other) - set(get_registered_factors())  # type: ignore

SUPPORTED_FACTORS = DynamicSupportedFactors()
_BACKTEST_SIMPLE_FIELDS = frozenset(
    {
        "initial_cash",
        "top_n",
        "selection_mode",
        "score_source",
        "lot_size",
        "max_group_positions",
        "lookback_momentum",
        "lookback_mean_reversion",
        "lookback_volatility",
        "rolling_risk_window",
        "execution_delay_days",
        "max_allowed_drawdown",
        "max_allowed_daily_var",
        "min_allowed_rolling_return",
        "min_allowed_information_ratio",
        "min_allowed_fill_rate",
        "min_allowed_execution_price_coverage",
        "min_allowed_factor_score_coverage",
        "max_allowed_market_constraint_rate",
        "max_allowed_position_weight",
        "max_allowed_group_weight",
        "max_allowed_attribution_residual",
        "max_allowed_factor_correlation",
        "max_allowed_rebalance_changes",
        "min_allowed_holding_days",
        "rebalance_every_n_days",
        "commission_rate",
        "buy_commission_rate",
        "sell_commission_rate",
        "slippage_rate",
        "market_impact_coefficient",
        "market_impact_exponent",
        "stamp_duty_rate",
        "min_commission",
        "transfer_fee_rate",
        "target_cash_weight",
        "max_position_weight",
        "limit_up_down_rate",
        "st_limit_up_down_rate",
        "growth_limit_up_down_rate",
        "bse_limit_up_down_rate",
        "infer_limit_rate_by_symbol",
        "max_volume_participation",
        "infer_limit_flags",
        "forward_fill_suspended_bars",
        "price_field",
        "execution_price_field",
        "start_date",
        "end_date",
    }
)
_BACKTEST_PATH_FIELDS = frozenset(
    {"output_dir", "symbol_name_csv", "stock_pool_csv", "symbol_group_csv", "factor_score_csv"}
)
_BACKTEST_ALLOWED_FIELDS = _BACKTEST_SIMPLE_FIELDS | _BACKTEST_PATH_FIELDS | {"factor_weights"}
_CONFIG_ALLOWED_TOP_LEVEL_TABLES = frozenset({"backtest", "sweep"})
_SWEEP_ALLOWED_FIELDS = _BACKTEST_SIMPLE_FIELDS - {"initial_cash"}
_INT_FIELDS = frozenset(
    {
        "top_n",
        "lot_size",
        "max_group_positions",
        "lookback_momentum",
        "lookback_mean_reversion",
        "lookback_volatility",
        "rolling_risk_window",
        "execution_delay_days",
        "rebalance_every_n_days",
    }
)
_OPTIONAL_INT_FIELDS = frozenset({"max_group_positions"})
_FLOAT_FIELDS = frozenset(
    {
        "initial_cash",
        "commission_rate",
        "buy_commission_rate",
        "sell_commission_rate",
        "slippage_rate",
        "market_impact_coefficient",
        "market_impact_exponent",
        "stamp_duty_rate",
        "min_commission",
        "transfer_fee_rate",
        "target_cash_weight",
        "max_position_weight",
        "limit_up_down_rate",
        "st_limit_up_down_rate",
        "growth_limit_up_down_rate",
        "bse_limit_up_down_rate",
        "max_volume_participation",
        "max_allowed_drawdown",
        "max_allowed_daily_var",
        "min_allowed_rolling_return",
        "min_allowed_information_ratio",
        "min_allowed_fill_rate",
        "min_allowed_execution_price_coverage",
        "min_allowed_factor_score_coverage",
        "max_allowed_market_constraint_rate",
        "max_allowed_position_weight",
        "max_allowed_group_weight",
        "max_allowed_attribution_residual",
        "max_allowed_factor_correlation",
        "max_allowed_rebalance_changes",
        "min_allowed_holding_days",
    }
)
_OPTIONAL_FLOAT_FIELDS = frozenset({"buy_commission_rate", "sell_commission_rate"})
_STRING_FIELDS = frozenset({"selection_mode", "score_source", "price_field", "execution_price_field"})
_OPTIONAL_STRING_FIELDS = frozenset({"execution_price_field"})
_DATE_FIELDS = frozenset({"start_date", "end_date"})
_BOOL_FIELDS = frozenset({"infer_limit_flags", "infer_limit_rate_by_symbol", "forward_fill_suspended_bars"})


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    top_n: int = 3
    selection_mode: str = "top"
    score_source: str = "auto"
    lot_size: int = 100
    max_group_positions: int | None = None
    lookback_momentum: int = 20
    lookback_mean_reversion: int = 5
    lookback_volatility: int = 20
    rolling_risk_window: int = 20
    execution_delay_days: int = 0
    max_allowed_drawdown: float = 0.20
    max_allowed_daily_var: float = 0.05
    min_allowed_rolling_return: float = -0.10
    min_allowed_information_ratio: float = 0.0
    min_allowed_fill_rate: float = 0.70
    min_allowed_execution_price_coverage: float = 1.0
    min_allowed_factor_score_coverage: float = 0.95
    max_allowed_market_constraint_rate: float = 0.50
    max_allowed_position_weight: float = 0.50
    max_allowed_group_weight: float = 0.60
    max_allowed_attribution_residual: float = 0.05
    max_allowed_factor_correlation: float = 0.90
    max_allowed_rebalance_changes: float = 3.0
    min_allowed_holding_days: float = 3.0
    rebalance_every_n_days: int = 5
    commission_rate: float = 0.0003
    buy_commission_rate: float | None = None
    sell_commission_rate: float | None = None
    slippage_rate: float = 0.0005
    market_impact_coefficient: float = 0.0
    market_impact_exponent: float = 1.0
    stamp_duty_rate: float = 0.0
    min_commission: float = 0.0
    transfer_fee_rate: float = 0.0
    target_cash_weight: float = 0.0
    max_position_weight: float = 1.0
    limit_up_down_rate: float = 0.10
    st_limit_up_down_rate: float = 0.05
    growth_limit_up_down_rate: float = 0.20
    bse_limit_up_down_rate: float = 0.30
    infer_limit_rate_by_symbol: bool = False
    max_volume_participation: float = 1.0
    infer_limit_flags: bool = False
    forward_fill_suspended_bars: bool = False
    price_field: str = "adjusted_close"
    execution_price_field: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    output_dir: Path = OUTPUT_DIR
    symbol_name_csv: Path | None = None
    stock_pool_csv: Path | None = None
    symbol_group_csv: Path | None = None
    factor_score_csv: Path | None = None
    factor_weights: dict[str, float] = field(
        default_factory=lambda: DEFAULT_FACTOR_WEIGHTS.copy()
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", self.output_dir.resolve())
        if self.symbol_name_csv is not None:
            object.__setattr__(self, "symbol_name_csv", self.symbol_name_csv.resolve())
        if self.stock_pool_csv is not None:
            object.__setattr__(self, "stock_pool_csv", self.stock_pool_csv.resolve())
        if self.symbol_group_csv is not None:
            object.__setattr__(self, "symbol_group_csv", self.symbol_group_csv.resolve())
        if self.factor_score_csv is not None:
            object.__setattr__(self, "factor_score_csv", self.factor_score_csv.resolve())
        if self.initial_cash <= 0:
            raise ConfigValidationError("initial_cash must be greater than 0.")
        if self.top_n <= 0:
            raise ConfigValidationError("top_n must be greater than 0.")
        if self.selection_mode not in {"top", "bottom"}:
            raise ConfigValidationError("selection_mode must be one of: top, bottom.")
        if self.score_source not in {"auto", "builtin", "external"}:
            raise ConfigValidationError("score_source must be one of: auto, builtin, external.")
        if self.lot_size <= 0:
            raise ConfigValidationError("lot_size must be greater than 0.")
        if self.max_group_positions is not None and self.max_group_positions <= 0:
            raise ConfigValidationError("max_group_positions must be greater than 0.")
        if self.rebalance_every_n_days <= 0:
            raise ConfigValidationError("rebalance_every_n_days must be greater than 0.")
        if min(
            self.lookback_momentum,
            self.lookback_mean_reversion,
            self.lookback_volatility,
            self.rolling_risk_window,
        ) <= 0:
            raise ConfigValidationError("All lookback and rolling windows must be greater than 0.")
        if self.execution_delay_days < 0:
            raise ConfigValidationError("execution_delay_days must be greater than or equal to 0.")
        if min(
            self.commission_rate,
            0.0 if self.buy_commission_rate is None else self.buy_commission_rate,
            0.0 if self.sell_commission_rate is None else self.sell_commission_rate,
            self.slippage_rate,
            self.market_impact_coefficient,
            self.market_impact_exponent,
            self.stamp_duty_rate,
            self.min_commission,
            self.transfer_fee_rate,
            self.max_position_weight,
            self.max_allowed_drawdown,
            self.max_allowed_daily_var,
            self.min_allowed_fill_rate,
            self.min_allowed_execution_price_coverage,
            self.min_allowed_factor_score_coverage,
            self.max_allowed_market_constraint_rate,
            self.max_allowed_position_weight,
            self.max_allowed_group_weight,
            self.max_allowed_attribution_residual,
            self.max_allowed_factor_correlation,
            self.limit_up_down_rate,
            self.st_limit_up_down_rate,
            self.growth_limit_up_down_rate,
            self.bse_limit_up_down_rate,
            self.max_volume_participation,
        ) < 0:
            raise ConfigValidationError("Cost rates cannot be negative.")
        if min(
            self.limit_up_down_rate,
            self.st_limit_up_down_rate,
            self.growth_limit_up_down_rate,
            self.bse_limit_up_down_rate,
        ) <= 0:
            raise ConfigValidationError("Limit rates must be greater than 0.")
        if max(
            self.limit_up_down_rate,
            self.st_limit_up_down_rate,
            self.growth_limit_up_down_rate,
            self.bse_limit_up_down_rate,
        ) >= 1:
            raise ConfigValidationError("Limit rates must be less than 1.")
        if self.max_volume_participation > 1:
            raise ConfigValidationError("max_volume_participation must be between 0 and 1.")
        if self.market_impact_exponent <= 0:
            raise ConfigValidationError("market_impact_exponent must be greater than 0.")
        if self.target_cash_weight < 0 or self.target_cash_weight >= 1:
            raise ConfigValidationError("target_cash_weight must be between 0 and 1.")
        if self.max_position_weight <= 0 or self.max_position_weight > 1:
            raise ConfigValidationError("max_position_weight must be between 0 and 1.")
        if self.max_allowed_drawdown <= 0 or self.max_allowed_drawdown > 1:
            raise ConfigValidationError("max_allowed_drawdown must be between 0 and 1.")
        if self.max_allowed_daily_var < 0 or self.max_allowed_daily_var > 1:
            raise ConfigValidationError("max_allowed_daily_var must be between 0 and 1.")
        if self.min_allowed_rolling_return < -1 or self.min_allowed_rolling_return > 1:
            raise ConfigValidationError("min_allowed_rolling_return must be between -1 and 1.")
        if self.min_allowed_information_ratio < -10 or self.min_allowed_information_ratio > 10:
            raise ConfigValidationError("min_allowed_information_ratio must be between -10 and 10.")
        if self.min_allowed_fill_rate < 0 or self.min_allowed_fill_rate > 1:
            raise ConfigValidationError("min_allowed_fill_rate must be between 0 and 1.")
        if self.min_allowed_execution_price_coverage < 0 or self.min_allowed_execution_price_coverage > 1:
            raise ConfigValidationError("min_allowed_execution_price_coverage must be between 0 and 1.")
        if self.min_allowed_factor_score_coverage < 0 or self.min_allowed_factor_score_coverage > 1:
            raise ConfigValidationError("min_allowed_factor_score_coverage must be between 0 and 1.")
        if self.max_allowed_market_constraint_rate < 0 or self.max_allowed_market_constraint_rate > 1:
            raise ConfigValidationError("max_allowed_market_constraint_rate must be between 0 and 1.")
        if self.max_allowed_position_weight <= 0 or self.max_allowed_position_weight > 1:
            raise ConfigValidationError("max_allowed_position_weight must be between 0 and 1.")
        if self.max_allowed_group_weight <= 0 or self.max_allowed_group_weight > 1:
            raise ConfigValidationError("max_allowed_group_weight must be between 0 and 1.")
        if self.max_allowed_attribution_residual < 0 or self.max_allowed_attribution_residual > 1:
            raise ConfigValidationError("max_allowed_attribution_residual must be between 0 and 1.")
        if self.max_allowed_factor_correlation < 0 or self.max_allowed_factor_correlation > 1:
            raise ConfigValidationError("max_allowed_factor_correlation must be between 0 and 1.")
        if self.max_allowed_rebalance_changes < 0:
            raise ConfigValidationError("max_allowed_rebalance_changes must be greater than or equal to 0.")
        if self.min_allowed_holding_days < 0:
            raise ConfigValidationError("min_allowed_holding_days must be greater than or equal to 0.")
        if self.price_field not in {"close", "adjusted_close"}:
            raise ConfigValidationError("price_field must be one of: close, adjusted_close.")
        if self.execution_price_field_effective not in {"close", "adjusted_close", "open", "vwap"}:
            raise ConfigValidationError(
                "execution_price_field must be one of: close, adjusted_close, open, vwap."
            )
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ConfigValidationError("start_date must be earlier than or equal to end_date.")
        if not self.factor_weights:
            raise ConfigValidationError("factor_weights cannot be empty.")
        unsupported_factors = sorted(set(self.factor_weights) - SUPPORTED_FACTORS)
        if unsupported_factors:
            unsupported_text = ", ".join(unsupported_factors)
            raise ConfigValidationError(
                f"factor_weights contains unsupported factors: {unsupported_text}."
            )
        if any(weight < 0 for weight in self.factor_weights.values()):
            raise ConfigValidationError("factor_weights cannot contain negative values.")
        if sum(self.factor_weights.values()) <= 0:
            raise ConfigValidationError("factor_weights must sum to a positive value.")

    @property
    def per_side_cost_rate(self) -> float:
        return self.buy_commission_rate_effective + self.slippage_rate

    @property
    def execution_price_field_effective(self) -> str:
        return self.execution_price_field or self.price_field

    @property
    def buy_commission_rate_effective(self) -> float:
        return self.commission_rate if self.buy_commission_rate is None else self.buy_commission_rate

    @property
    def sell_commission_rate_effective(self) -> float:
        return (
            self.commission_rate
            if self.sell_commission_rate is None
            else self.sell_commission_rate
        )

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

    def to_dict(self) -> dict[str, object]:
        """将当前配置序列化为字典，适合 JSON 或重建配置。"""
        return {
            "initial_cash": self.initial_cash,
            "top_n": self.top_n,
            "selection_mode": self.selection_mode,
            "score_source": self.score_source,
            "lot_size": self.lot_size,
            "max_group_positions": self.max_group_positions,
            "lookback_momentum": self.lookback_momentum,
            "lookback_mean_reversion": self.lookback_mean_reversion,
            "lookback_volatility": self.lookback_volatility,
            "rolling_risk_window": self.rolling_risk_window,
            "execution_delay_days": self.execution_delay_days,
            "max_allowed_drawdown": self.max_allowed_drawdown,
            "max_allowed_daily_var": self.max_allowed_daily_var,
            "min_allowed_rolling_return": self.min_allowed_rolling_return,
            "min_allowed_information_ratio": self.min_allowed_information_ratio,
            "min_allowed_fill_rate": self.min_allowed_fill_rate,
            "min_allowed_execution_price_coverage": self.min_allowed_execution_price_coverage,
            "min_allowed_factor_score_coverage": self.min_allowed_factor_score_coverage,
            "max_allowed_market_constraint_rate": self.max_allowed_market_constraint_rate,
            "max_allowed_position_weight": self.max_allowed_position_weight,
            "max_allowed_group_weight": self.max_allowed_group_weight,
            "max_allowed_attribution_residual": self.max_allowed_attribution_residual,
            "max_allowed_factor_correlation": self.max_allowed_factor_correlation,
            "max_allowed_rebalance_changes": self.max_allowed_rebalance_changes,
            "min_allowed_holding_days": self.min_allowed_holding_days,
            "rebalance_every_n_days": self.rebalance_every_n_days,
            "commission_rate": self.commission_rate,
            "buy_commission_rate": self.buy_commission_rate,
            "sell_commission_rate": self.sell_commission_rate,
            "slippage_rate": self.slippage_rate,
            "market_impact_coefficient": self.market_impact_coefficient,
            "market_impact_exponent": self.market_impact_exponent,
            "stamp_duty_rate": self.stamp_duty_rate,
            "min_commission": self.min_commission,
            "transfer_fee_rate": self.transfer_fee_rate,
            "target_cash_weight": self.target_cash_weight,
            "max_position_weight": self.max_position_weight,
            "limit_up_down_rate": self.limit_up_down_rate,
            "st_limit_up_down_rate": self.st_limit_up_down_rate,
            "growth_limit_up_down_rate": self.growth_limit_up_down_rate,
            "bse_limit_up_down_rate": self.bse_limit_up_down_rate,
            "infer_limit_rate_by_symbol": self.infer_limit_rate_by_symbol,
            "max_volume_participation": self.max_volume_participation,
            "infer_limit_flags": self.infer_limit_flags,
            "forward_fill_suspended_bars": self.forward_fill_suspended_bars,
            "price_field": self.price_field,
            "execution_price_field": self.execution_price_field,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "output_dir": self.output_dir,
            "symbol_name_csv": self.symbol_name_csv,
            "stock_pool_csv": self.stock_pool_csv,
            "symbol_group_csv": self.symbol_group_csv,
            "factor_score_csv": self.factor_score_csv,
            "factor_weights": self.factor_weights.copy(),
        }

    @classmethod
    def from_dict(cls, mapping: Mapping[str, object]) -> BacktestConfig:
        """从字典创建 BacktestConfig 实例。"""
        return cls(
            initial_cash=cast(float, mapping["initial_cash"]),
            top_n=cast(int, mapping["top_n"]),
            selection_mode=cast(str, mapping["selection_mode"]),
            score_source=cast(str, mapping["score_source"]),
            lot_size=cast(int, mapping["lot_size"]),
            max_group_positions=cast(int | None, mapping["max_group_positions"]),
            lookback_momentum=cast(int, mapping["lookback_momentum"]),
            lookback_mean_reversion=cast(int, mapping["lookback_mean_reversion"]),
            lookback_volatility=cast(int, mapping["lookback_volatility"]),
            rolling_risk_window=cast(int, mapping["rolling_risk_window"]),
            execution_delay_days=cast(int, mapping["execution_delay_days"]),
            max_allowed_drawdown=cast(float, mapping["max_allowed_drawdown"]),
            max_allowed_daily_var=cast(float, mapping["max_allowed_daily_var"]),
            min_allowed_rolling_return=cast(float, mapping["min_allowed_rolling_return"]),
            min_allowed_information_ratio=cast(float, mapping["min_allowed_information_ratio"]),
            min_allowed_fill_rate=cast(float, mapping["min_allowed_fill_rate"]),
            min_allowed_execution_price_coverage=cast(float, mapping["min_allowed_execution_price_coverage"]),
            min_allowed_factor_score_coverage=cast(float, mapping["min_allowed_factor_score_coverage"]),
            max_allowed_market_constraint_rate=cast(float, mapping["max_allowed_market_constraint_rate"]),
            max_allowed_position_weight=cast(float, mapping["max_allowed_position_weight"]),
            max_allowed_group_weight=cast(float, mapping["max_allowed_group_weight"]),
            max_allowed_attribution_residual=cast(float, mapping["max_allowed_attribution_residual"]),
            max_allowed_factor_correlation=cast(float, mapping["max_allowed_factor_correlation"]),
            max_allowed_rebalance_changes=cast(float, mapping["max_allowed_rebalance_changes"]),
            min_allowed_holding_days=cast(float, mapping["min_allowed_holding_days"]),
            rebalance_every_n_days=cast(int, mapping["rebalance_every_n_days"]),
            commission_rate=cast(float, mapping["commission_rate"]),
            buy_commission_rate=cast(float | None, mapping["buy_commission_rate"]),
            sell_commission_rate=cast(float | None, mapping["sell_commission_rate"]),
            slippage_rate=cast(float, mapping["slippage_rate"]),
            market_impact_coefficient=cast(float, mapping["market_impact_coefficient"]),
            market_impact_exponent=cast(float, mapping["market_impact_exponent"]),
            stamp_duty_rate=cast(float, mapping["stamp_duty_rate"]),
            min_commission=cast(float, mapping["min_commission"]),
            transfer_fee_rate=cast(float, mapping["transfer_fee_rate"]),
            target_cash_weight=cast(float, mapping["target_cash_weight"]),
            max_position_weight=cast(float, mapping["max_position_weight"]),
            limit_up_down_rate=cast(float, mapping["limit_up_down_rate"]),
            st_limit_up_down_rate=cast(float, mapping["st_limit_up_down_rate"]),
            growth_limit_up_down_rate=cast(float, mapping["growth_limit_up_down_rate"]),
            bse_limit_up_down_rate=cast(float, mapping["bse_limit_up_down_rate"]),
            infer_limit_rate_by_symbol=cast(bool, mapping["infer_limit_rate_by_symbol"]),
            max_volume_participation=cast(float, mapping["max_volume_participation"]),
            infer_limit_flags=cast(bool, mapping["infer_limit_flags"]),
            forward_fill_suspended_bars=cast(bool, mapping["forward_fill_suspended_bars"]),
            price_field=cast(str, mapping["price_field"]),
            execution_price_field=cast(str | None, mapping["execution_price_field"]),
            start_date=cast(date | None, mapping["start_date"]),
            end_date=cast(date | None, mapping["end_date"]),
            output_dir=cast(Path, mapping["output_dir"]),
            symbol_name_csv=cast(Path | None, mapping["symbol_name_csv"]),
            stock_pool_csv=cast(Path | None, mapping["stock_pool_csv"]),
            symbol_group_csv=cast(Path | None, mapping["symbol_group_csv"]),
            factor_score_csv=cast(Path | None, mapping["factor_score_csv"]),
            factor_weights=cast(dict[str, float], mapping["factor_weights"]).copy(),
        )


def load_config_overrides_from_toml(config_path: str | Path) -> dict[str, object]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    raw_config = payload.get("backtest")
    if not isinstance(raw_config, dict):
        raise ValueError("Config file must contain a [backtest] table.")
    _reject_unknown_keys(
        table_name="config",
        keys=payload.keys(),
        allowed=_CONFIG_ALLOWED_TOP_LEVEL_TABLES,
    )
    _reject_unknown_keys(
        table_name="backtest",
        keys=raw_config.keys(),
        allowed=_BACKTEST_ALLOWED_FIELDS,
    )

    normalized: dict[str, object] = {}
    for field_name in _INT_FIELDS:
        if field_name in raw_config:
            if field_name in _OPTIONAL_INT_FIELDS and raw_config[field_name] in ("", None):
                continue
            normalized[field_name] = _require_int(raw_config[field_name], field_name)

    for field_name in _FLOAT_FIELDS:
        if field_name in raw_config:
            if field_name in _OPTIONAL_FLOAT_FIELDS and raw_config[field_name] in ("", None):
                continue
            normalized[field_name] = _require_number(raw_config[field_name], field_name)

    for field_name in _STRING_FIELDS:
        if field_name in raw_config:
            if field_name in _OPTIONAL_STRING_FIELDS and raw_config[field_name] in ("", None):
                continue
            normalized[field_name] = _require_str(raw_config[field_name], field_name)

    for field_name in _DATE_FIELDS:
        if field_name in raw_config and raw_config[field_name] not in ("", None):
            normalized[field_name] = _require_date(raw_config[field_name], field_name)

    for field_name in _BOOL_FIELDS:
        if field_name in raw_config:
            normalized[field_name] = _require_bool(raw_config[field_name], field_name)

    if "output_dir" in raw_config:
        output_dir = Path(_require_str(raw_config["output_dir"], "output_dir"))
        if not output_dir.is_absolute():
            output_dir = (path.parent / output_dir).resolve()
        normalized["output_dir"] = output_dir

    if "symbol_name_csv" in raw_config and raw_config["symbol_name_csv"] not in ("", None):
        symbol_name_csv = Path(_require_str(raw_config["symbol_name_csv"], "symbol_name_csv"))
        if not symbol_name_csv.is_absolute():
            symbol_name_csv = (path.parent / symbol_name_csv).resolve()
        normalized["symbol_name_csv"] = symbol_name_csv

    if "stock_pool_csv" in raw_config and raw_config["stock_pool_csv"] not in ("", None):
        stock_pool_csv = Path(_require_str(raw_config["stock_pool_csv"], "stock_pool_csv"))
        if not stock_pool_csv.is_absolute():
            stock_pool_csv = (path.parent / stock_pool_csv).resolve()
        normalized["stock_pool_csv"] = stock_pool_csv

    if "symbol_group_csv" in raw_config and raw_config["symbol_group_csv"] not in ("", None):
        symbol_group_csv = Path(_require_str(raw_config["symbol_group_csv"], "symbol_group_csv"))
        if not symbol_group_csv.is_absolute():
            symbol_group_csv = (path.parent / symbol_group_csv).resolve()
        normalized["symbol_group_csv"] = symbol_group_csv

    if "factor_score_csv" in raw_config and raw_config["factor_score_csv"] not in ("", None):
        factor_score_csv = Path(_require_str(raw_config["factor_score_csv"], "factor_score_csv"))
        if not factor_score_csv.is_absolute():
            factor_score_csv = (path.parent / factor_score_csv).resolve()
        normalized["factor_score_csv"] = factor_score_csv

    if "factor_weights" in raw_config:
        factor_weights = raw_config["factor_weights"]
        if not isinstance(factor_weights, dict):
            raise ValueError("factor_weights must be a TOML table.")
        normalized["factor_weights"] = {
            str(name): _require_number(value, f"factor_weights.{name}")
            for name, value in factor_weights.items()
        }

    return normalized


def load_sweep_overrides_from_toml(config_path: str | Path) -> dict[str, list[object]]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    _reject_unknown_keys(
        table_name="config",
        keys=payload.keys(),
        allowed=_CONFIG_ALLOWED_TOP_LEVEL_TABLES,
    )
    raw_sweep = payload.get("sweep")
    if raw_sweep is None:
        return {}
    if not isinstance(raw_sweep, dict):
        raise ValueError("Config file [sweep] section must be a TOML table.")

    normalized: dict[str, list[object]] = {}
    for field_name, values in raw_sweep.items():
        if field_name not in _SWEEP_ALLOWED_FIELDS:
            raise ValueError(f"Unsupported sweep field: {field_name}")
        if not isinstance(values, list) or not values:
            raise ValueError(f"Sweep field '{field_name}' must be a non-empty TOML array.")
        normalized[field_name] = [
            _validate_sweep_value(field_name, value)
            for value in values
        ]

    return normalized


def _reject_unknown_keys(
    *,
    table_name: str,
    keys: KeysView[str],
    allowed: frozenset[str],
) -> None:
    unknown = sorted(set(keys) - allowed)
    if unknown:
        unknown_text = ", ".join(unknown)
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"Unsupported {table_name} field(s): {unknown_text}. "
            f"Allowed fields: {allowed_text}."
        )


def _validate_sweep_value(field_name: str, value: object) -> object:
    if field_name in _INT_FIELDS:
        return _require_int(value, field_name)
    if field_name in _FLOAT_FIELDS:
        return _require_number(value, field_name)
    if field_name in _STRING_FIELDS:
        return _require_str(value, field_name)
    if field_name in _BOOL_FIELDS:
        return _require_bool(value, field_name)
    raise ValueError(f"Unsupported sweep field: {field_name}")


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return value


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    return float(value)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def _require_date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a date string.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc
