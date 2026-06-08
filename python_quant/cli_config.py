from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import cast

from .config import BacktestConfig, load_config_overrides_from_toml


def build_backtest_config(args: argparse.Namespace) -> BacktestConfig:
    default_config = BacktestConfig()
    config_kwargs: dict[str, object] = {
        "initial_cash": default_config.initial_cash,
        "top_n": default_config.top_n,
        "selection_mode": default_config.selection_mode,
        "score_source": default_config.score_source,
        "lot_size": default_config.lot_size,
        "max_group_positions": default_config.max_group_positions,
        "lookback_momentum": default_config.lookback_momentum,
        "lookback_mean_reversion": default_config.lookback_mean_reversion,
        "lookback_volatility": default_config.lookback_volatility,
        "rolling_risk_window": default_config.rolling_risk_window,
        "execution_delay_days": default_config.execution_delay_days,
        "max_allowed_drawdown": default_config.max_allowed_drawdown,
        "max_allowed_daily_var": default_config.max_allowed_daily_var,
        "min_allowed_rolling_return": default_config.min_allowed_rolling_return,
        "min_allowed_information_ratio": default_config.min_allowed_information_ratio,
        "min_allowed_fill_rate": default_config.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": default_config.min_allowed_execution_price_coverage,
        "min_allowed_factor_score_coverage": default_config.min_allowed_factor_score_coverage,
        "max_allowed_market_constraint_rate": default_config.max_allowed_market_constraint_rate,
        "max_allowed_position_weight": default_config.max_allowed_position_weight,
        "max_allowed_group_weight": default_config.max_allowed_group_weight,
        "max_allowed_attribution_residual": default_config.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": default_config.max_allowed_factor_correlation,
        "max_allowed_rebalance_changes": default_config.max_allowed_rebalance_changes,
        "min_allowed_holding_days": default_config.min_allowed_holding_days,
        "rebalance_every_n_days": default_config.rebalance_every_n_days,
        "commission_rate": default_config.commission_rate,
        "buy_commission_rate": default_config.buy_commission_rate,
        "sell_commission_rate": default_config.sell_commission_rate,
        "slippage_rate": default_config.slippage_rate,
        "market_impact_coefficient": default_config.market_impact_coefficient,
        "market_impact_exponent": default_config.market_impact_exponent,
        "stamp_duty_rate": default_config.stamp_duty_rate,
        "min_commission": default_config.min_commission,
        "transfer_fee_rate": default_config.transfer_fee_rate,
        "target_cash_weight": default_config.target_cash_weight,
        "max_position_weight": default_config.max_position_weight,
        "limit_up_down_rate": default_config.limit_up_down_rate,
        "st_limit_up_down_rate": default_config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": default_config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": default_config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": default_config.infer_limit_rate_by_symbol,
        "max_volume_participation": default_config.max_volume_participation,
        "infer_limit_flags": default_config.infer_limit_flags,
        "forward_fill_suspended_bars": default_config.forward_fill_suspended_bars,
        "price_field": default_config.price_field,
        "execution_price_field": default_config.execution_price_field,
        "start_date": default_config.start_date,
        "end_date": default_config.end_date,
        "output_dir": default_config.output_dir,
        "symbol_name_csv": default_config.symbol_name_csv,
        "stock_pool_csv": default_config.stock_pool_csv,
        "symbol_group_csv": default_config.symbol_group_csv,
        "factor_score_csv": default_config.factor_score_csv,
        "factor_weights": default_config.factor_weights.copy(),
    }

    has_explicit_output_dir = False
    if args.config:
        config_overrides = load_config_overrides_from_toml(args.config)
        has_explicit_output_dir = "output_dir" in config_overrides
        config_kwargs.update(config_overrides)

    cli_overrides = cli_config_overrides(args)
    for key, value in cli_overrides.items():
        if value is not None:
            config_kwargs[key] = value

    if args.output_dir is not None:
        config_kwargs["output_dir"] = Path(args.output_dir)
        has_explicit_output_dir = True

    if args.stock_pool_csv is not None:
        config_kwargs["stock_pool_csv"] = Path(args.stock_pool_csv)

    if args.symbol_group_csv is not None:
        config_kwargs["symbol_group_csv"] = Path(args.symbol_group_csv)

    factor_score_csv = getattr(args, "factor_score_csv", None)
    if factor_score_csv is not None:
        config_kwargs["factor_score_csv"] = Path(factor_score_csv)

    if args.factor_weight:
        factor_weights = cast(dict[str, float], config_kwargs["factor_weights"]).copy()
        factor_weights.update(parse_factor_weight_overrides(args.factor_weight))
        config_kwargs["factor_weights"] = factor_weights

    if not has_explicit_output_dir:
        config_kwargs["output_dir"] = build_default_run_output_dir(config_kwargs)

    return BacktestConfig.from_dict(config_kwargs)


def parse_factor_weight_overrides(entries: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(
                f"无效的因子权重配置：'{entry}'。请使用 factor_name=value 格式。"
            )
        name, raw_value = entry.split("=", 1)
        factor_name = name.strip()
        if not factor_name:
            raise ValueError("因子权重名称不能为空。")
        parsed[factor_name] = float(raw_value.strip())
    return parsed


def cli_config_overrides(args: argparse.Namespace) -> dict[str, object | None]:
    return {
        "initial_cash": args.initial_cash,
        "top_n": args.top_n,
        "selection_mode": getattr(args, "selection_mode", None),
        "score_source": getattr(args, "score_source", None),
        "lot_size": args.lot_size,
        "max_group_positions": args.max_group_positions,
        "lookback_momentum": args.lookback_momentum,
        "lookback_mean_reversion": args.lookback_mean_reversion,
        "lookback_volatility": args.lookback_volatility,
        "rolling_risk_window": args.rolling_risk_window,
        "execution_delay_days": args.execution_delay_days,
        "max_allowed_drawdown": args.max_allowed_drawdown,
        "max_allowed_daily_var": getattr(args, "max_allowed_daily_var", None),
        "min_allowed_rolling_return": args.min_allowed_rolling_return,
        "min_allowed_information_ratio": getattr(args, "min_allowed_information_ratio", None),
        "min_allowed_fill_rate": args.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": getattr(args, "min_allowed_execution_price_coverage", None),
        "min_allowed_factor_score_coverage": getattr(args, "min_allowed_factor_score_coverage", None),
        "max_allowed_market_constraint_rate": getattr(args, "max_allowed_market_constraint_rate", None),
        "max_allowed_position_weight": args.max_allowed_position_weight,
        "max_allowed_group_weight": getattr(args, "max_allowed_group_weight", None),
        "max_allowed_attribution_residual": args.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": getattr(args, "max_allowed_factor_correlation", None),
        "max_allowed_rebalance_changes": getattr(args, "max_allowed_rebalance_changes", None),
        "min_allowed_holding_days": getattr(args, "min_allowed_holding_days", None),
        "rebalance_every_n_days": args.rebalance_days,
        "commission_rate": args.commission_rate,
        "buy_commission_rate": args.buy_commission_rate,
        "sell_commission_rate": args.sell_commission_rate,
        "slippage_rate": args.slippage_rate,
        "market_impact_coefficient": getattr(args, "market_impact_coefficient", None),
        "market_impact_exponent": getattr(args, "market_impact_exponent", None),
        "stamp_duty_rate": args.stamp_duty_rate,
        "min_commission": args.min_commission,
        "transfer_fee_rate": args.transfer_fee_rate,
        "target_cash_weight": args.target_cash_weight,
        "max_position_weight": args.max_position_weight,
        "limit_up_down_rate": args.limit_up_down_rate,
        "st_limit_up_down_rate": args.st_limit_up_down_rate,
        "growth_limit_up_down_rate": args.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": args.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": True if args.infer_limit_rate_by_symbol else None,
        "max_volume_participation": args.max_volume_participation,
        "infer_limit_flags": True if args.infer_limit_flags else None,
        "forward_fill_suspended_bars": True if args.forward_fill_suspended_bars else None,
        "price_field": args.price_field,
        "execution_price_field": args.execution_price_field,
        "start_date": parse_cli_date(args.start_date, "start_date"),
        "end_date": parse_cli_date(args.end_date, "end_date"),
    }


def build_config_sources(
    args: argparse.Namespace,
    *,
    sweep_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    toml_overrides = load_config_overrides_from_toml(args.config) if args.config else {}
    cli_overrides = {
        key
        for key, value in cli_config_overrides(args).items()
        if value is not None
    }
    if args.output_dir is not None:
        cli_overrides.add("output_dir")
    if args.stock_pool_csv is not None:
        cli_overrides.add("stock_pool_csv")
    if args.symbol_group_csv is not None:
        cli_overrides.add("symbol_group_csv")
    if getattr(args, "factor_score_csv", None) is not None:
        cli_overrides.add("factor_score_csv")
    if args.factor_weight:
        cli_overrides.add("factor_weights")

    field_sources: dict[str, str] = {}
    field_names = sorted(set(BacktestConfig().to_dict().keys()) | set(toml_overrides) | cli_overrides)
    for field_name in field_names:
        if sweep_overrides and field_name in sweep_overrides:
            field_sources[field_name] = "sweep_override"
        elif field_name in cli_overrides:
            field_sources[field_name] = "cli"
        elif field_name in toml_overrides:
            field_sources[field_name] = "toml"
        else:
            field_sources[field_name] = "default"
    if args.output_dir is None and "output_dir" not in toml_overrides:
        field_sources["output_dir"] = "derived_default"
    return {
        "config_file": args.config,
        "field_sources": field_sources,
    }


def parse_cli_date(raw_value: str | None, field_name: str) -> date | None:
    if raw_value in ("", None):
        return None
    value = str(raw_value)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc


def build_config_from_mapping(config_kwargs: Mapping[str, object]) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=cast(float, config_kwargs["initial_cash"]),
        top_n=cast(int, config_kwargs["top_n"]),
        selection_mode=cast(str, config_kwargs["selection_mode"]),
        score_source=cast(str, config_kwargs["score_source"]),
        lot_size=cast(int, config_kwargs["lot_size"]),
        max_group_positions=cast(int | None, config_kwargs["max_group_positions"]),
        lookback_momentum=cast(int, config_kwargs["lookback_momentum"]),
        lookback_mean_reversion=cast(int, config_kwargs["lookback_mean_reversion"]),
        lookback_volatility=cast(int, config_kwargs["lookback_volatility"]),
        rolling_risk_window=cast(int, config_kwargs["rolling_risk_window"]),
        execution_delay_days=cast(int, config_kwargs["execution_delay_days"]),
        max_allowed_drawdown=cast(float, config_kwargs["max_allowed_drawdown"]),
        max_allowed_daily_var=cast(float, config_kwargs["max_allowed_daily_var"]),
        min_allowed_rolling_return=cast(float, config_kwargs["min_allowed_rolling_return"]),
        min_allowed_information_ratio=cast(float, config_kwargs["min_allowed_information_ratio"]),
        min_allowed_fill_rate=cast(float, config_kwargs["min_allowed_fill_rate"]),
        min_allowed_execution_price_coverage=cast(float, config_kwargs["min_allowed_execution_price_coverage"]),
        min_allowed_factor_score_coverage=cast(float, config_kwargs["min_allowed_factor_score_coverage"]),
        max_allowed_market_constraint_rate=cast(float, config_kwargs["max_allowed_market_constraint_rate"]),
        max_allowed_position_weight=cast(float, config_kwargs["max_allowed_position_weight"]),
        max_allowed_group_weight=cast(float, config_kwargs["max_allowed_group_weight"]),
        max_allowed_attribution_residual=cast(float, config_kwargs["max_allowed_attribution_residual"]),
        max_allowed_factor_correlation=cast(float, config_kwargs["max_allowed_factor_correlation"]),
        max_allowed_rebalance_changes=cast(float, config_kwargs["max_allowed_rebalance_changes"]),
        min_allowed_holding_days=cast(float, config_kwargs["min_allowed_holding_days"]),
        rebalance_every_n_days=cast(int, config_kwargs["rebalance_every_n_days"]),
        commission_rate=cast(float, config_kwargs["commission_rate"]),
        buy_commission_rate=cast(float | None, config_kwargs["buy_commission_rate"]),
        sell_commission_rate=cast(float | None, config_kwargs["sell_commission_rate"]),
        slippage_rate=cast(float, config_kwargs["slippage_rate"]),
        market_impact_coefficient=cast(float, config_kwargs["market_impact_coefficient"]),
        market_impact_exponent=cast(float, config_kwargs["market_impact_exponent"]),
        stamp_duty_rate=cast(float, config_kwargs["stamp_duty_rate"]),
        min_commission=cast(float, config_kwargs["min_commission"]),
        transfer_fee_rate=cast(float, config_kwargs["transfer_fee_rate"]),
        target_cash_weight=cast(float, config_kwargs["target_cash_weight"]),
        max_position_weight=cast(float, config_kwargs["max_position_weight"]),
        limit_up_down_rate=cast(float, config_kwargs["limit_up_down_rate"]),
        st_limit_up_down_rate=cast(float, config_kwargs["st_limit_up_down_rate"]),
        growth_limit_up_down_rate=cast(float, config_kwargs["growth_limit_up_down_rate"]),
        bse_limit_up_down_rate=cast(float, config_kwargs["bse_limit_up_down_rate"]),
        infer_limit_rate_by_symbol=cast(bool, config_kwargs["infer_limit_rate_by_symbol"]),
        max_volume_participation=cast(float, config_kwargs["max_volume_participation"]),
        infer_limit_flags=cast(bool, config_kwargs["infer_limit_flags"]),
        forward_fill_suspended_bars=cast(bool, config_kwargs["forward_fill_suspended_bars"]),
        price_field=cast(str, config_kwargs["price_field"]),
        execution_price_field=cast(str | None, config_kwargs["execution_price_field"]),
        start_date=cast(date | None, config_kwargs["start_date"]),
        end_date=cast(date | None, config_kwargs["end_date"]),
        output_dir=cast(Path, config_kwargs["output_dir"]),
        symbol_name_csv=cast(Path | None, config_kwargs["symbol_name_csv"]),
        stock_pool_csv=cast(Path | None, config_kwargs["stock_pool_csv"]),
        symbol_group_csv=cast(Path | None, config_kwargs["symbol_group_csv"]),
        factor_score_csv=cast(Path | None, config_kwargs["factor_score_csv"]),
        factor_weights=cast(dict[str, float], config_kwargs["factor_weights"]).copy(),
    )


def build_default_run_output_dir(config_kwargs: Mapping[str, object]) -> Path:
    timestamp = os.environ.get("MYFINANCES_RUN_TIMESTAMP")
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("output") / "runs" / f"{timestamp}-{config_hash(config_kwargs)}"


def config_hash(config_kwargs: Mapping[str, object]) -> str:
    payload = {
        key: jsonable_config_value(value)
        for key, value in sorted(config_kwargs.items())
        if key != "output_dir"
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:10]


def jsonable_config_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): jsonable_config_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def config_to_kwargs(config: BacktestConfig) -> dict[str, object]:
    return {
        "initial_cash": config.initial_cash,
        "top_n": config.top_n,
        "selection_mode": config.selection_mode,
        "score_source": config.score_source,
        "lot_size": config.lot_size,
        "max_group_positions": config.max_group_positions,
        "lookback_momentum": config.lookback_momentum,
        "lookback_mean_reversion": config.lookback_mean_reversion,
        "lookback_volatility": config.lookback_volatility,
        "rolling_risk_window": config.rolling_risk_window,
        "execution_delay_days": config.execution_delay_days,
        "max_allowed_drawdown": config.max_allowed_drawdown,
        "max_allowed_daily_var": config.max_allowed_daily_var,
        "min_allowed_rolling_return": config.min_allowed_rolling_return,
        "min_allowed_information_ratio": config.min_allowed_information_ratio,
        "min_allowed_fill_rate": config.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": config.min_allowed_execution_price_coverage,
        "min_allowed_factor_score_coverage": config.min_allowed_factor_score_coverage,
        "max_allowed_market_constraint_rate": config.max_allowed_market_constraint_rate,
        "max_allowed_position_weight": config.max_allowed_position_weight,
        "max_allowed_group_weight": config.max_allowed_group_weight,
        "max_allowed_attribution_residual": config.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": config.max_allowed_factor_correlation,
        "max_allowed_rebalance_changes": config.max_allowed_rebalance_changes,
        "min_allowed_holding_days": config.min_allowed_holding_days,
        "rebalance_every_n_days": config.rebalance_every_n_days,
        "commission_rate": config.commission_rate,
        "buy_commission_rate": config.buy_commission_rate,
        "sell_commission_rate": config.sell_commission_rate,
        "slippage_rate": config.slippage_rate,
        "market_impact_coefficient": config.market_impact_coefficient,
        "market_impact_exponent": config.market_impact_exponent,
        "stamp_duty_rate": config.stamp_duty_rate,
        "min_commission": config.min_commission,
        "transfer_fee_rate": config.transfer_fee_rate,
        "target_cash_weight": config.target_cash_weight,
        "max_position_weight": config.max_position_weight,
        "limit_up_down_rate": config.limit_up_down_rate,
        "st_limit_up_down_rate": config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": config.infer_limit_rate_by_symbol,
        "max_volume_participation": config.max_volume_participation,
        "infer_limit_flags": config.infer_limit_flags,
        "forward_fill_suspended_bars": config.forward_fill_suspended_bars,
        "price_field": config.price_field,
        "execution_price_field": config.execution_price_field,
        "start_date": config.start_date,
        "end_date": config.end_date,
        "output_dir": config.output_dir,
        "symbol_name_csv": config.symbol_name_csv,
        "stock_pool_csv": config.stock_pool_csv,
        "symbol_group_csv": config.symbol_group_csv,
        "factor_score_csv": config.factor_score_csv,
        "factor_weights": config.factor_weights.copy(),
    }
