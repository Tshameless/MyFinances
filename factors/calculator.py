"""
因子计算引擎 — FactorCalculator
==================================
计算五大类因子，Z-score 截面标准化，加权合成综合得分。
严格避免未来函数：每个调仓日只使用截止当日已知的数据。
"""

import numpy as np
import pandas as pd
from rich.console import Console

console = Console(force_terminal=False)


class FactorCalculator:
    """多因子计算器"""

    def __init__(self, factor_weights: dict[str, float]):
        # 归一化权重
        total = sum(factor_weights.values())
        self.weights = {k: v / total for k, v in factor_weights.items()}

    # ------------------------------------------------------------------
    # 一、估值因子
    # ------------------------------------------------------------------
    @staticmethod
    def calc_value_pe(df_snapshot: pd.DataFrame) -> pd.Series:
        """PE 倒数因子：PE 越低得分越高（排除 <=0 的无效 PE）"""
        pe = df_snapshot.set_index("code")["pe_ttm"].copy()
        pe = pe[pe > 0]
        value = 1.0 / pe
        return FactorCalculator._zscore(value)

    @staticmethod
    def calc_value_pb(df_snapshot: pd.DataFrame) -> pd.Series:
        """PB 倒数因子"""
        pb = df_snapshot.set_index("code")["pb"].copy()
        pb = pb[pb > 0]
        value = 1.0 / pb
        return FactorCalculator._zscore(value)

    # ------------------------------------------------------------------
    # 二、质量因子
    # ------------------------------------------------------------------
    @staticmethod
    def calc_quality_roe(df_snapshot: pd.DataFrame, roe_dict: dict[str, float]) -> pd.Series:
        """ROE 因子：ROE 越高越好"""
        if not roe_dict:
            roe_series = df_snapshot.set_index("code").get("roe_ttm", pd.Series(dtype=float))
        else:
            roe_series = pd.Series(roe_dict, name="roe_ttm")
        roe_series = pd.to_numeric(roe_series, errors="coerce").dropna()
        return FactorCalculator._zscore(roe_series)

    # ------------------------------------------------------------------
    # 三、动量因子
    # ------------------------------------------------------------------
    @staticmethod
    def calc_momentum(
        price_dict: dict[str, pd.DataFrame],
        lookback: int,
        date: str,
    ) -> pd.Series:
        """
        计算动量因子。
        lookback=20 → 20 日收益率
        """
        returns = {}
        target = pd.Timestamp(date)

        for code, df in price_dict.items():
            if df is None or df.empty:
                continue
            df_sorted = df[df["date"] <= target].tail(lookback + 1)
            if len(df_sorted) < lookback + 1:
                continue
            # 确认最后一条数据的日期是 date 当天或之前最近一个交易日
            start_price = df_sorted["close"].iloc[0]
            end_price = df_sorted["close"].iloc[-1]
            if start_price <= 0:
                continue
            returns[code] = (end_price / start_price) - 1.0

        return FactorCalculator._zscore(pd.Series(returns))

    # ------------------------------------------------------------------
    # 四、低波动率因子
    # ------------------------------------------------------------------
    @staticmethod
    def calc_volatility(
        price_dict: dict[str, pd.DataFrame],
        lookback: int,
        date: str,
    ) -> pd.Series:
        """波动率因子：波动越低越好（取负值）"""
        vols = {}
        target = pd.Timestamp(date)

        for code, df in price_dict.items():
            if df is None or df.empty:
                continue
            df_sorted = df[df["date"] <= target].tail(lookback + 1)
            if len(df_sorted) < lookback + 1:
                continue
            returns = df_sorted["close"].pct_change().dropna()
            if len(returns) < 5:
                continue
            vols[code] = returns.std()

        vol_series = pd.Series(vols)
        # 低波得分高 → 取负
        return FactorCalculator._zscore(-vol_series)

    # ------------------------------------------------------------------
    # 五、规模因子
    # ------------------------------------------------------------------
    @staticmethod
    def calc_size(df_snapshot: pd.DataFrame) -> pd.Series:
        """规模因子：负对数市值（偏好中小盘）"""
        mc = df_snapshot.set_index("code")["market_cap"].copy()
        mc = pd.to_numeric(mc, errors="coerce")
        mc = mc[mc > 0]
        log_mc = np.log(mc)
        # 负对数市值：小盘得分高
        return FactorCalculator._zscore(-log_mc)

    # ------------------------------------------------------------------
    # 六、综合打分
    # ------------------------------------------------------------------
    def calc_composite_score(
        self,
        df_snapshot: pd.DataFrame,
        price_dict: dict[str, pd.DataFrame],
        roe_dict: dict[str, float],
        date: str,
    ) -> pd.DataFrame:
        """
        计算综合因子得分，返回 DataFrame：
        code | value_pe | value_pb | quality_roe | momentum_20 | momentum_60 | volatility | size | composite
        """
        console.print(f"[dim]  📐 计算因子得分 — {date}[/]")

        factors = {}

        # 估值因子（直接从快照取）
        if "value_pe" in self.weights:
            factors["value_pe"] = self.calc_value_pe(df_snapshot)
        if "value_pb" in self.weights:
            factors["value_pb"] = self.calc_value_pb(df_snapshot)

        # 质量因子
        if "quality_roe" in self.weights:
            factors["quality_roe"] = self.calc_quality_roe(df_snapshot, roe_dict)

        # 动量因子
        if "momentum_20" in self.weights:
            factors["momentum_20"] = self.calc_momentum(price_dict, 20, date)
        if "momentum_60" in self.weights:
            factors["momentum_60"] = self.calc_momentum(price_dict, 60, date)

        # 低波因子
        if "volatility" in self.weights:
            factors["volatility"] = self.calc_volatility(price_dict, 20, date)

        # 规模因子
        if "size" in self.weights:
            factors["size"] = self.calc_size(df_snapshot)

        # 合并所有因子
        df_factors = pd.DataFrame(factors)

        # 计算综合得分
        composite = pd.Series(0.0, index=df_factors.index)
        for name, weight in self.weights.items():
            if name in df_factors.columns:
                composite += df_factors[name].fillna(0) * weight

        df_factors["composite"] = composite
        df_factors = df_factors.sort_values("composite", ascending=False)
        df_factors["rank"] = range(1, len(df_factors) + 1)

        return df_factors.reset_index().rename(columns={"index": "code"})

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _zscore(series: pd.Series) -> pd.Series:
        """Z-score 标准化，去极值（±3 倍标准差截尾）"""
        series = series.dropna()
        if len(series) < 3:
            return series
        mean, std = series.mean(), series.std()
        if std == 0:
            return pd.Series(0.0, index=series.index)
        z = (series - mean) / std
        z = z.clip(-3, 3)
        return z
