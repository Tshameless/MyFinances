"""
数据获取层 — DataFetcher
=========================
基于 akshare 获取 A 股全市场数据，支持本地缓存加速。
涵盖：成分股列表、日线行情、财务指标、ETF 行情。
"""

import os
import time
from pathlib import Path

import akshare as ak
import pandas as pd
import numpy as np
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.console import Console

console = Console(force_terminal=False)


class DataFetcher:
    """A股 & 跨境 ETF 数据获取器"""

    def __init__(self, cache_dir: str = "output/cache", use_cache: bool = True):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self._price_cache: dict[str, pd.DataFrame] = {}

    # ----------------------------------------------------------------
    # 一、成分股列表
    # ----------------------------------------------------------------
    def get_stock_universe(self, universe: str) -> list[str]:
        """获取选股池股票代码列表，返回 [sh600000, sz000001, ...] 格式"""
        if isinstance(universe, list):
            return universe

        cache_file = self.cache_dir / f"{universe}_stocks.csv"
        if self.use_cache and cache_file.exists():
            df = pd.read_csv(cache_file)
            return df["code"].tolist()

        console.print(f"[bold cyan]📡 正在获取 {universe.upper()} 成分股列表...[/]")

        if universe == "csi300":
            df = ak.index_stock_cons_csindex(symbol="000300")
        elif universe == "csi500":
            df = ak.index_stock_cons_csindex(symbol="000905")
        elif universe == "csi800":
            df300 = ak.index_stock_cons_csindex(symbol="000300")
            df500 = ak.index_stock_cons_csindex(symbol="000905")
            df = pd.concat([df300, df500], ignore_index=True)
        elif universe == "all":
            df = ak.stock_zh_a_spot_em()
            df = df[["代码", "名称"]].rename(columns={"代码": "成分券代码", "名称": "成分券名称"})
        else:
            raise ValueError(f"不支持的选股范围: {universe}")

        codes = self._format_codes(df)
        pd.DataFrame({"code": codes}).to_csv(cache_file, index=False)
        console.print(f"  ✅ 共 {len(codes)} 只股票")
        return codes

    @staticmethod
    def _format_codes(df: pd.DataFrame) -> list[str]:
        """将 akshare 返回的代码转换为标准格式 sh600000 / sz000001 / bj8xxxxx"""
        codes = []
        for _, row in df.iterrows():
            raw = str(row.get("成分券代码", row.get("代码", "")))
            if raw.startswith("6"):
                codes.append(f"sh{raw}")
            elif raw.startswith(("0", "3")):
                codes.append(f"sz{raw}")
            elif raw.startswith(("4", "8")):
                codes.append(f"bj{raw}")
            else:
                codes.append(raw)
        return codes

    # ----------------------------------------------------------------
    # 二、日线行情
    # ----------------------------------------------------------------
    def fetch_daily_prices(
        self,
        codes: list[str],
        start: str,
        end: str,
        adjust: str = "qfq",
    ) -> dict[str, pd.DataFrame]:
        """
        批量获取日线行情。
        返回 {code: DataFrame}，DataFrame 含 date/open/high/low/close/volume/amount
        """
        result = {}
        total = len(codes)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]获取日线行情", total=total)

            for code in codes:
                df = self._fetch_single_stock(code, start, end, adjust)
                if df is not None and not df.empty:
                    result[code] = df
                progress.advance(task)
                time.sleep(0.08)  # 控制请求频率

        console.print(f"  ✅ 成功获取 {len(result)}/{total} 只股票日线数据")
        return result

    def _fetch_single_stock(
        self, code: str, start: str, end: str, adjust: str
    ) -> pd.DataFrame | None:
        """获取单只股票日线"""
        cache_file = self.cache_dir / f"daily_{code}_{start}_{end}.csv"
        if self.use_cache and cache_file.exists():
            return pd.read_csv(cache_file, parse_dates=["date"])

        raw = code.replace("sh", "").replace("sz", "").replace("bj", "")
        try:
            df = ak.stock_zh_a_hist(
                symbol=raw,
                period="daily",
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adjust=adjust,
            )
            if df is None or df.empty:
                return None

            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "换手率": "turnover",
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
            df.sort_values("date", inplace=True)
            df.reset_index(drop=True, inplace=True)

            if self.use_cache:
                df.to_csv(cache_file, index=False)
            return df
        except Exception:
            return None

    # ----------------------------------------------------------------
    # 三、基础财务指标快照
    # ----------------------------------------------------------------
    def fetch_financial_snapshot(self, codes: list[str] | None = None) -> pd.DataFrame:
        """
        获取 A 股全市场实时财务快照。
        包含：PE_TTM、PB、总市值、流通市值等。

        优选全市场快照接口（一次拉取）；失败时降级为按 codes 列表逐批获取。
        """
        cache_file = self.cache_dir / "a_share_snapshot.csv"
        if self.use_cache and cache_file.exists():
            df = pd.read_csv(cache_file)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            return df

        # --- 方案 A：全市场快照（带重试） ---
        console.print("[bold cyan]📡 正在获取 A 股全市场快照数据...[/]")
        df = self._fetch_snapshot_with_retry()
        if df is not None:
            df = self._format_snapshot(df)
            if self.use_cache:
                df.to_csv(cache_file, index=False)
            console.print(f"  ✅ 共 {len(df)} 只 A 股快照数据")
            return df

        # --- 方案 B：降级 — 仅拉取目标股票池的关键指标 ---
        if codes:
            console.print("[yellow]  ⚠ 全市场快照获取失败，降级为按股票池逐只拉取 PE/PB/市值...[/]")
            df = self._fetch_snapshot_by_codes(codes)
            if self.use_cache:
                df.to_csv(cache_file, index=False)
            console.print(f"  ✅ 降级获取 {len(df)} 只股票关键指标")
            return df

        # --- 完全失败：返回空壳 ---
        console.print("[red]  ❌ 无法获取任何财务快照数据[/]")
        return pd.DataFrame(columns=["code", "name", "pe_ttm", "pb",
                                      "market_cap", "float_cap", "is_st", "date"])

    def _fetch_snapshot_with_retry(self, max_retries: int = 3) -> pd.DataFrame | None:
        """带指数退避重试的全市场快照"""
        import time as _time
        for attempt in range(max_retries):
            try:
                return ak.stock_zh_a_spot_em()
            except Exception as e:
                wait = (2 ** attempt) * 2  # 2s → 4s → 8s
                if attempt < max_retries - 1:
                    console.print(f"    第 {attempt + 1} 次请求失败，{wait}s 后重试...")
                    _time.sleep(wait)
                else:
                    console.print(f"    [yellow]3 次重试均失败: {e}[/]")
        return None

    def _fetch_snapshot_by_codes(self, codes: list[str]) -> pd.DataFrame:
        """降级方案：逐个股票获取 PE/PB/市值（仅拉取目标池）"""
        rows = []
        total = len(codes)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("[yellow]降级获取财务指标", total=total)
            for code in codes:
                raw = code.replace("sh", "").replace("sz", "").replace("bj", "")
                try:
                    info = ak.stock_individual_info_em(symbol=raw)
                    if info is not None and not info.empty:
                        info_dict = dict(zip(info["item"], info["value"]))
                        rows.append({
                            "code": code,
                            "name": info_dict.get("股票简称", raw),
                            "pe_ttm": pd.to_numeric(info_dict.get("市盈率-动态", None), errors="coerce"),
                            "pb": pd.to_numeric(info_dict.get("市净率", None), errors="coerce"),
                            "market_cap": pd.to_numeric(info_dict.get("总市值", None), errors="coerce"),
                            "float_cap": pd.to_numeric(info_dict.get("流通市值", None), errors="coerce"),
                            "is_st": False,
                        })
                except Exception:
                    pass
                progress.advance(task)
                time.sleep(0.15)

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["date"] = pd.Timestamp.now().strftime("%Y-%m-%d")
        return df

    def _format_snapshot(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一快照格式"""
        df = df.rename(columns={
            "代码": "code", "名称": "name",
            "市盈率-动态": "pe_ttm", "市净率": "pb",
            "总市值": "market_cap", "流通市值": "float_cap",
            "市销率": "ps_ttm",
        })
        df["code"] = df["code"].apply(lambda x: (
            f"sh{x}" if x.startswith("6")
            else f"sz{x}" if x.startswith(("0", "3"))
            else f"bj{x}" if x.startswith(("4", "8"))
            else x
        ))
        df["is_st"] = df["name"].str.contains("ST|\\*ST", na=False)
        for col in ["pe_ttm", "pb", "market_cap", "float_cap", "ps_ttm"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.Timestamp.now().strftime("%Y-%m-%d")
        return df

    # ----------------------------------------------------------------
    # 四、ROE — 从财务报表提取
    # ----------------------------------------------------------------
    def fetch_roe_data(self, codes: list[str]) -> dict[str, float]:
        """批量获取个股最新 ROE（TTM），拉取最近4个季度财报估算"""
        cache_file = self.cache_dir / "roe_data.csv"
        if self.use_cache and cache_file.exists():
            df = pd.read_csv(cache_file)
            return dict(zip(df["code"], df["roe_ttm"]))

        console.print("[bold cyan]📡 正在获取 ROE 数据...[/]")
        result = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]获取 ROE", total=len(codes))
            for code in codes:
                roe = self._fetch_single_roe(code)
                if roe is not None and not np.isnan(roe):
                    result[code] = roe
                progress.advance(task)
                time.sleep(0.06)

        pd.DataFrame(
            [{"code": k, "roe_ttm": v} for k, v in result.items()]
        ).to_csv(cache_file, index=False)

        console.print(f"  ✅ 成功获取 {len(result)} 只股票 ROE 数据")
        return result

    def _fetch_single_roe(self, code: str) -> float | None:
        raw = code.replace("sh", "").replace("sz", "").replace("bj", "")
        try:
            df = ak.stock_financial_abstract_ths(symbol=raw, indicator="按年度")
            if df is None or df.empty:
                return None
            # 取最新一期净资产收益率
            if "净资产收益率" in df.columns:
                latest = pd.to_numeric(df["净资产收益率"].iloc[0], errors="coerce")
                return float(latest) if not pd.isna(latest) else None
            return None
        except Exception:
            return None

    # ----------------------------------------------------------------
    # 五、指数 & ETF 行情
    # ----------------------------------------------------------------
    def fetch_index_data(
        self, index_code: str, start: str, end: str
    ) -> pd.DataFrame | None:
        """获取指数日线数据（作为基准）"""
        cache_file = self.cache_dir / f"index_{index_code}_{start}_{end}.csv"
        if self.use_cache and cache_file.exists():
            return pd.read_csv(cache_file, parse_dates=["date"])

        raw = index_code.replace(".SH", "").replace(".SZ", "")
        try:
            df = ak.stock_zh_index_daily(symbol=f"sh{raw}")
            if df is None or df.empty:
                return None
            df = df.rename(columns={"date": "date", "close": "close"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= start) & (df["date"] <= end)]
            df.sort_values("date", inplace=True)
            df.reset_index(drop=True, inplace=True)
            df.to_csv(cache_file, index=False)
            return df[["date", "close"]]
        except Exception:
            return None

    def fetch_etf_data(
        self, etf_codes: list[str], start: str, end: str
    ) -> dict[str, pd.DataFrame]:
        """获取 ETF 日线数据"""
        result = {}
        for code in etf_codes:
            cache_file = self.cache_dir / f"etf_{code}_{start}_{end}.csv"
            if self.use_cache and cache_file.exists():
                result[code] = pd.read_csv(cache_file, parse_dates=["date"])
                continue
            try:
                df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                         start_date=start.replace("-", ""),
                                         end_date=end.replace("-", ""),
                                         adjust="qfq")
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        "日期": "date", "开盘": "open", "收盘": "close",
                        "最高": "high", "最低": "low", "成交量": "volume",
                    })
                    df["date"] = pd.to_datetime(df["date"])
                    df = df[["date", "open", "close", "high", "low", "volume"]]
                    df.sort_values("date", inplace=True)
                    df.to_csv(cache_file, index=False)
                    result[code] = df
                time.sleep(0.1)
            except Exception:
                pass
        return result
