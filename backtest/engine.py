"""
回测引擎 — BacktestEngine
============================
日频运行，月度调仓，等权配置。
严格记录每日组合净值、持仓明细、换手率。
自动计算夏普比率、最大回撤、年化收益等核心指标。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from factors.calculator import FactorCalculator

console = Console(force_terminal=False)


@dataclass
class DailyRecord:
    """每日组合快照"""
    date: str
    nav: float               # 组合净值
    daily_return: float      # 日收益率
    cash: float              # 现金余额
    positions: dict[str, float] = field(default_factory=dict)  # {code: market_value}


@dataclass
class TradeRecord:
    """交易记录"""
    date: str
    code: str
    action: str              # "buy" | "sell"
    price: float
    shares: int
    amount: float
    commission: float
    stamp_duty: float


class BacktestEngine:
    """多因子选股回测引擎"""

    def __init__(
        self,
        factor_calc: FactorCalculator,
        price_dict: dict[str, pd.DataFrame],
        df_snapshot: pd.DataFrame,
        roe_dict: dict[str, float],
        start_date: str,
        end_date: str,
        initial_cash: float = 1_000_000,
        top_n: int = 30,
        rebalance_freq: str = "monthly",
        rebalance_day: int = 1,
        commission_rate: float = 0.0003,
        stamp_duty_rate: float = 0.001,
        slippage_rate: float = 0.0001,
        max_position_weight: float = 0.10,
        stop_loss_ratio: float = 0.15,
        exclude_st: bool = True,
        exclude_new_ipo: bool = True,
    ):
        self.factor_calc = factor_calc
        self.price_dict = price_dict
        self.df_snapshot = df_snapshot
        self.roe_dict = roe_dict
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.initial_cash = initial_cash
        self.top_n = top_n
        self.rebalance_freq = rebalance_freq
        self.rebalance_day = rebalance_day
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate
        self.max_position_weight = max_position_weight
        self.stop_loss_ratio = stop_loss_ratio
        self.exclude_st = exclude_st
        self.exclude_new_ipo = exclude_new_ipo

        # 运行时状态
        self.cash: float = initial_cash
        self.positions: dict[str, dict] = {}  # {code: {shares, avg_cost}}
        self.daily_records: list[DailyRecord] = []
        self.trade_records: list[TradeRecord] = []
        self._trading_calendar: list[str] = []

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def run(self) -> pd.DataFrame:
        """执行回测，返回每日净值 DataFrame"""
        self._build_trading_calendar()
        self._run_loop()
        return self._build_result_df()

    # ------------------------------------------------------------------
    # 交易日历
    # ------------------------------------------------------------------
    def _build_trading_calendar(self):
        """从价格数据中提取所有交易日并排序"""
        all_dates = set()
        for df in self.price_dict.values():
            if df is not None and not df.empty:
                dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
                all_dates.update(dates)
        self._trading_calendar = sorted(all_dates)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _run_loop(self):
        """逐日遍历"""
        console.print("[bold cyan]🚀 开始回测...[/]")
        console.print(
            f"  区间: {self.start_date.date()} → {self.end_date.date()}  "
            f"交易日: {len(self._trading_calendar)} 天"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]回测进行中", total=len(self._trading_calendar))

            for i, date_str in enumerate(self._trading_calendar):
                date = pd.Timestamp(date_str)
                if date < self.start_date:
                    progress.advance(task)
                    continue
                if date > self.end_date:
                    break

                # 月度调仓检查
                if self._is_rebalance_day(date, date_str):
                    self._rebalance(date_str)

                # 止损检查
                if self.stop_loss_ratio > 0:
                    self._check_stop_loss(date_str)

                # 记录当日净值
                self._record_daily(date_str)
                progress.advance(task)

        console.print("  ✅ 回测完成")

    def _is_rebalance_day(self, date: pd.Timestamp, date_str: str) -> bool:
        """判断是否为调仓日"""
        if self.rebalance_freq == "weekly":
            return date.dayofweek == 0  # 周一调仓

        if self.rebalance_freq == "monthly":
            # 找出当月第 N 个交易日
            month = date.strftime("%Y-%m")
            month_dates = [d for d in self._trading_calendar if d.startswith(month)]
            if len(month_dates) < self.rebalance_day:
                return False
            return date_str == month_dates[self.rebalance_day - 1]

        return False

    def _rebalance(self, date_str: str):
        """执行调仓"""
        # 先卖出不在新选股列表中的持仓
        new_picks = self._get_top_picks(date_str)
        new_codes = set(new_picks["code"].tolist()) if not new_picks.empty else set()

        # 清仓不在列表中的股票
        for code in list(self.positions.keys()):
            if code not in new_codes:
                self._sell(code, date_str, reason="调仓卖出")

        if new_picks.empty:
            return

        # 计算每只目标仓位
        target_weight = 1.0 / min(len(new_picks), self.top_n)
        target_weight = min(target_weight, self.max_position_weight)

        total_value = self._total_value(date_str)
        for _, row in new_picks.iterrows():
            code = row["code"]
            target_value = total_value * target_weight

            price_info = self._get_price(code, date_str)
            if price_info is None:
                continue
            price = price_info["close"] * (1 + self.slippage_rate)

            current_mv = self._position_market_value(code, date_str)
            diff = target_value - current_mv

            if diff > 100:  # 买入（至少100元）
                shares = int(diff / price / 100) * 100  # A股100股整数倍
                if shares > 0:
                    self._buy(code, shares, price, date_str)
            elif diff < -100:  # 卖出
                shares = int(abs(diff) / price / 100) * 100
                if code in self.positions and shares > 0:
                    actual_sell = min(shares, self.positions[code]["shares"])
                    if actual_sell > 0:
                        self._sell_partial(code, actual_sell, price, date_str, reason="调仓减仓")

    def _get_top_picks(self, date_str: str) -> pd.DataFrame:
        """获取当天综合得分最高的 N 只股票"""
        df = self.factor_calc.calc_composite_score(
            self.df_snapshot, self.price_dict, self.roe_dict, date_str
        )
        if df.empty:
            return df

        # ST 过滤
        if self.exclude_st:
            st_codes = self.df_snapshot[self.df_snapshot["is_st"]]["code"].tolist()
            df = df[~df["code"].isin(st_codes)]

        # 新股过滤（上市 < 250 个交易日）
        if self.exclude_new_ipo:
            df = df[df["code"].apply(lambda c: self._has_enough_history(c, 250))]

        return df.head(self.top_n)

    # ------------------------------------------------------------------
    # 买入 / 卖出
    # ------------------------------------------------------------------
    def _buy(self, code: str, shares: int, price: float, date_str: str):
        amount = shares * price
        commission = max(5, amount * self.commission_rate)  # 最低5元
        total_cost = amount + commission

        if total_cost > self.cash:
            shares = int((self.cash - 5) / (price * (1 + self.commission_rate)) / 100) * 100
            if shares <= 0:
                return
            amount = shares * price
            commission = max(5, amount * self.commission_rate)
            total_cost = amount + commission

        if total_cost > self.cash:
            return

        self.cash -= total_cost
        if code in self.positions:
            pos = self.positions[code]
            total_shares = pos["shares"] + shares
            pos["avg_cost"] = (pos["avg_cost"] * pos["shares"] + amount) / total_shares
            pos["shares"] = total_shares
        else:
            self.positions[code] = {"shares": shares, "avg_cost": amount / shares}

        self.trade_records.append(TradeRecord(
            date=date_str, code=code, action="buy", price=price,
            shares=shares, amount=amount, commission=commission, stamp_duty=0,
        ))

    def _sell(self, code: str, date_str: str, reason: str = ""):
        """全仓卖出"""
        if code not in self.positions:
            return
        shares = self.positions[code]["shares"]
        price_info = self._get_price(code, date_str)
        if price_info is None:
            return
        price = price_info["close"] * (1 - self.slippage_rate)
        self._sell_partial(code, shares, price, date_str, reason)

    def _sell_partial(self, code: str, shares: int, price: float, date_str: str, reason: str = ""):
        if code not in self.positions or self.positions[code]["shares"] < shares:
            shares = self.positions.get(code, {}).get("shares", 0)
        if shares <= 0:
            return

        amount = shares * price
        commission = max(5, amount * self.commission_rate)
        stamp_duty = amount * self.stamp_duty_rate
        net_proceed = amount - commission - stamp_duty

        self.cash += net_proceed
        pos = self.positions[code]
        pos["shares"] -= shares
        if pos["shares"] <= 0:
            del self.positions[code]

        self.trade_records.append(TradeRecord(
            date=date_str, code=code, action="sell", price=price,
            shares=shares, amount=amount, commission=commission, stamp_duty=stamp_duty,
        ))

    def _check_stop_loss(self, date_str: str):
        """止损检查"""
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            price_info = self._get_price(code, date_str)
            if price_info is None:
                continue
            current_px = price_info["close"]
            loss_ratio = (current_px - pos["avg_cost"]) / pos["avg_cost"]
            if loss_ratio < -self.stop_loss_ratio:
                self._sell(code, date_str, reason="止损")

    # ------------------------------------------------------------------
    # 每日记录
    # ------------------------------------------------------------------
    def _record_daily(self, date_str: str):
        total_mv = self.cash
        pos_snapshot = {}
        for code, pos in self.positions.items():
            price_info = self._get_price(code, date_str)
            if price_info is None:
                mv = pos["shares"] * pos["avg_cost"]  # fallback
            else:
                mv = pos["shares"] * price_info["close"]
            total_mv += mv
            pos_snapshot[code] = mv

        if not self.daily_records:
            prev_nav = self.initial_cash
        else:
            prev_nav = self.daily_records[-1].nav

        daily_ret = (total_mv / prev_nav) - 1 if prev_nav > 0 else 0

        self.daily_records.append(DailyRecord(
            date=date_str,
            nav=total_mv,
            daily_return=daily_ret,
            cash=self.cash,
            positions=pos_snapshot,
        ))

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _total_value(self, date_str: str) -> float:
        total = self.cash
        for code, pos in self.positions.items():
            px = self._get_price(code, date_str)
            total += pos["shares"] * (px["close"] if px else pos["avg_cost"])
        return total

    def _position_market_value(self, code: str, date_str: str) -> float:
        if code not in self.positions:
            return 0.0
        px = self._get_price(code, date_str)
        return self.positions[code]["shares"] * (px["close"] if px else self.positions[code]["avg_cost"])

    def _get_price(self, code: str, date_str: str) -> dict | None:
        df = self.price_dict.get(code)
        if df is None or df.empty:
            return None
        match = df[df["date"] <= date_str]
        if match.empty:
            return None
        return match.iloc[-1].to_dict()

    def _has_enough_history(self, code: str, min_days: int) -> bool:
        df = self.price_dict.get(code)
        return df is not None and len(df) >= min_days

    # ------------------------------------------------------------------
    # 结果导出
    # ------------------------------------------------------------------
    def _build_result_df(self) -> pd.DataFrame:
        rows = []
        for rec in self.daily_records:
            rows.append({
                "date": rec.date,
                "nav": rec.nav,
                "daily_return": rec.daily_return,
                "cash": rec.cash,
                "positions": len(rec.positions),
            })
        return pd.DataFrame(rows)

    def get_performance_metrics(self) -> dict:
        """计算核心绩效指标"""
        df = self._build_result_df()
        if df.empty:
            return {}

        n_days = len(df)
        n_years = n_days / 252

        # 日收益率序列
        returns = df["daily_return"].values

        total_return = (df["nav"].iloc[-1] / self.initial_cash) - 1
        annual_return = (1 + total_return) ** (1 / max(n_years, 0.5)) - 1
        annual_vol = np.std(returns) * np.sqrt(252)
        sharpe = (annual_return - 0.03) / annual_vol if annual_vol > 0 else 0

        # 最大回撤
        cummax = df["nav"].cummax()
        drawdowns = (df["nav"] - cummax) / cummax
        max_dd = drawdowns.min()

        # 胜率
        win_days = (returns > 0).sum()
        win_rate = win_days / n_days if n_days > 0 else 0

        # 盈亏比
        avg_win = returns[returns > 0].mean() if (returns > 0).any() else 0
        avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0

        # 卡玛比率
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        # 交易统计
        buy_count = sum(1 for t in self.trade_records if t.action == "buy")
        sell_count = sum(1 for t in self.trade_records if t.action == "sell")
        total_commission = sum(t.commission for t in self.trade_records)
        total_stamp = sum(t.stamp_duty for t in self.trade_records)

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "annual_volatility": annual_vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "calmar_ratio": calmar,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "total_trades": buy_count + sell_count,
            "total_commission": total_commission,
            "total_stamp_duty": total_stamp,
            "final_nav": df["nav"].iloc[-1],
            "trading_days": n_days,
            "years": n_years,
        }

    def print_summary(self):
        """打印回测摘要"""
        m = self.get_performance_metrics()
        if not m:
            console.print("[red]无回测数据[/]")
            return

        table = Table(title="📊 回测绩效摘要", title_style="bold cyan")
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="green", justify="right")

        table.add_row("累计收益率", f"{m['total_return']:.2%}")
        table.add_row("年化收益率", f"{m['annual_return']:.2%}")
        table.add_row("年化波动率", f"{m['annual_volatility']:.2%}")
        table.add_row("夏普比率", f"{m['sharpe_ratio']:.2f}")
        table.add_row("最大回撤", f"{m['max_drawdown']:.2%}")
        table.add_row("卡玛比率", f"{m['calmar_ratio']:.2f}")
        table.add_row("日胜率", f"{m['win_rate']:.2%}")
        table.add_row("盈亏比", f"{m['profit_loss_ratio']:.2f}")
        table.add_row("总交易次数", str(m['total_trades']))
        table.add_row("总佣金", f"¥{m['total_commission']:,.0f}")
        table.add_row("总印花税", f"¥{m['total_stamp_duty']:,.0f}")
        table.add_row("最终净值", f"¥{m['final_nav']:,.0f}")
        table.add_row("交易天数", str(m['trading_days']))

        console.print(table)
