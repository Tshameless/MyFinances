"""
可视化报告生成器 — ReportGenerator
=====================================
基于 Plotly 生成交互式 HTML 回测报告。
包含：净值曲线、回撤区、年度收益、因子暴露等。
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from jinja2 import Template
from rich.console import Console

console = Console(force_terminal=False)

# 配色方案：薄荷绿主色调
COLORS = {
    "primary": "#4CAF50",
    "secondary": "#FF9800",
    "benchmark": "#888888",
    "profit": "#FF4444",     # A股涨红
    "loss": "#4CAF50",       # A股跌绿
    "bg": "#FAFAFA",
    "text": "#333333",
}


class ReportGenerator:
    """回测报告生成器"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        result_df: pd.DataFrame,
        metrics: dict,
        benchmark_df: pd.DataFrame | None = None,
        trade_records: list | None = None,
        output_name: str = "backtest_report.html",
    ) -> str:
        """
        生成完整 HTML 报告。
        返回报告文件路径。
        """
        console.print("[bold cyan]📊 生成可视化报告...[/]")

        charts_html = ""

        # 1. 净值曲线
        charts_html += self._nav_curve_chart(result_df, benchmark_df)

        # 2. 回撤曲线
        charts_html += self._drawdown_chart(result_df, benchmark_df)

        # 3. 年度收益
        charts_html += self._annual_returns_chart(result_df)

        # 4. 月度收益热力图（补）
        # 5. 滚动夏普
        charts_html += self._rolling_sharpe_chart(result_df)

        # 渲染模板
        template = self._load_template()
        html = template.render(
            title="A股多因子选股回测报告",
            metrics=metrics,
            charts=charts_html,
            colors=COLORS,
        )

        output_path = self.output_dir / output_name
        output_path.write_text(html, encoding="utf-8")
        console.print(f"  ✅ 报告已生成: [bold green]{output_path}[/]")
        return str(output_path)

    # ------------------------------------------------------------------
    # 图表生成
    # ------------------------------------------------------------------
    def _nav_curve_chart(self, df: pd.DataFrame, bench: pd.DataFrame | None) -> str:
        """净值曲线"""
        fig = go.Figure()

        df["date"] = pd.to_datetime(df["date"])
        df["cum_return"] = (df["nav"] / df["nav"].iloc[0] - 1) * 100

        fig.add_trace(go.Scatter(
            x=df["date"], y=df["cum_return"],
            mode="lines", name="策略组合",
            line=dict(color=COLORS["primary"], width=2.5),
            fill="tozeroy", fillcolor="rgba(76, 175, 80, 0.1)",
        ))

        if bench is not None and not bench.empty:
            bench["date"] = pd.to_datetime(bench["date"])
            bench["cum_return"] = (bench["close"] / bench["close"].iloc[0] - 1) * 100
            # 对齐日期
            bench_aligned = bench[bench["date"].isin(df["date"])]
            fig.add_trace(go.Scatter(
                x=bench_aligned["date"], y=bench_aligned["cum_return"],
                mode="lines", name="沪深300",
                line=dict(color=COLORS["benchmark"], width=1.5, dash="dot"),
            ))

        fig.update_layout(
            title="累计收益率曲线",
            xaxis_title="日期",
            yaxis_title="累计收益率 (%)",
            hovermode="x unified",
            template="plotly_white",
            height=400,
            margin=dict(l=40, r=40, t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def _drawdown_chart(self, df: pd.DataFrame, bench: pd.DataFrame | None = None) -> str:
        """回撤曲线"""
        fig = go.Figure()

        df["date"] = pd.to_datetime(df["date"])
        cummax = df["nav"].cummax()
        df["drawdown"] = (df["nav"] - cummax) / cummax * 100

        fig.add_trace(go.Scatter(
            x=df["date"], y=df["drawdown"],
            mode="lines", name="策略回撤",
            line=dict(color=COLORS["secondary"], width=2),
            fill="tozeroy", fillcolor="rgba(255, 152, 0, 0.15)",
        ))

        fig.update_layout(
            title="回撤曲线",
            xaxis_title="日期",
            yaxis_title="回撤 (%)",
            hovermode="x unified",
            template="plotly_white",
            height=350,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

        # 标注最大回撤
        max_dd_idx = df["drawdown"].idxmin()
        if not pd.isna(max_dd_idx):
            fig.add_annotation(
                x=df.loc[max_dd_idx, "date"],
                y=df.loc[max_dd_idx, "drawdown"],
                text=f"最大回撤 {df.loc[max_dd_idx, 'drawdown']:.1f}%",
                showarrow=True,
                arrowhead=1,
                font=dict(color="red"),
            )

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def _annual_returns_chart(self, df: pd.DataFrame) -> str:
        """年度收益柱状图"""
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["daily_return"] = pd.to_numeric(df["daily_return"], errors="coerce")

        annual = df.groupby("year").apply(
            lambda g: (1 + g["daily_return"]).prod() - 1, include_groups=False
        ).dropna() * 100

        if annual.empty:
            return ""

        colors_bar = [COLORS["profit"] if v >= 0 else COLORS["loss"] for v in annual.values]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=annual.index.astype(str),
            y=annual.values,
            marker_color=colors_bar,
            text=[f"{v:.1f}%" for v in annual.values],
            textposition="outside",
        ))

        fig.update_layout(
            title="年度收益率",
            xaxis_title="年份",
            yaxis_title="收益率 (%)",
            template="plotly_white",
            height=300,
            margin=dict(l=40, r=40, t=50, b=40),
            showlegend=False,
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def _rolling_sharpe_chart(self, df: pd.DataFrame) -> str:
        """滚动 252 日夏普比率"""
        df["date"] = pd.to_datetime(df["date"])
        window = 252
        if len(df) < window:
            return ""

        rolling_ret = df["daily_return"].rolling(window).mean() * 252
        rolling_vol = df["daily_return"].rolling(window).std() * np.sqrt(252)
        rolling_sharpe = (rolling_ret - 0.03) / rolling_vol

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=rolling_sharpe,
            mode="lines", name="滚动夏普",
            line=dict(color=COLORS["primary"], width=2),
            fill="tozeroy", fillcolor="rgba(76, 175, 80, 0.08)",
        ))

        fig.update_layout(
            title="滚动年化夏普比率 (252日)",
            xaxis_title="日期",
            yaxis_title="夏普比率",
            hovermode="x unified",
            template="plotly_white",
            height=300,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig.add_hline(y=1, line_dash="dot", line_color="green", opacity=0.3,
                      annotation_text="夏普=1")

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def _load_template(self) -> Template:
        """HTML 模板"""
        template_str = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #FAFAFA;
      color: #333;
      line-height: 1.6;
    }
    .header {
      background: linear-gradient(135deg, {{ colors.primary }}, #2E7D32);
      color: white;
      padding: 40px 20px;
      text-align: center;
    }
    .header h1 { font-size: 2em; margin-bottom: 8px; }
    .header p { opacity: 0.9; font-size: 0.95em; }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px;
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .metric-card {
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      text-align: center;
      transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    .metric-card .label {
      font-size: 0.85em;
      color: #888;
      margin-bottom: 6px;
    }
    .metric-card .value {
      font-size: 1.6em;
      font-weight: 700;
      color: {{ colors.primary }};
    }
    .metric-card .value.negative { color: #FF5252; }
    .metric-card .value.warn { color: {{ colors.secondary }}; }

    .charts-section {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 24px 40px;
    }
    .chart-container {
      background: white;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }

    .footer {
      text-align: center;
      padding: 20px;
      color: #bbb;
      font-size: 0.85em;
    }
  </style>
</head>
<body>

<div class="header">
  <h1>📊 {{ title }}</h1>
  <p>多因子策略 · 日频回测 · 月度调仓</p>
</div>

<div class="metrics-grid">
  {% macro val_class(v) %}{% if v is number and v < 0 %}negative{% endif %}{% endmacro %}
  <div class="metric-card">
    <div class="label">累计收益率</div>
    <div class="value">{{ "%.2f%%"|format(metrics.total_return * 100) if metrics.total_return else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">年化收益率</div>
    <div class="value {{ val_class(metrics.annual_return) }}">{{ "%.2f%%"|format(metrics.annual_return * 100) if metrics.annual_return else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">年化波动率</div>
    <div class="value">{{ "%.2f%%"|format(metrics.annual_volatility * 100) if metrics.annual_volatility else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">夏普比率</div>
    <div class="value {{ val_class(metrics.sharpe_ratio) }}">{{ "%.2f"|format(metrics.sharpe_ratio) if metrics.sharpe_ratio else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">最大回撤</div>
    <div class="value negative">{{ "%.2f%%"|format(metrics.max_drawdown * 100) if metrics.max_drawdown else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">卡玛比率</div>
    <div class="value">{{ "%.2f"|format(metrics.calmar_ratio) if metrics.calmar_ratio else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">日胜率</div>
    <div class="value">{{ "%.1f%%"|format(metrics.win_rate * 100) if metrics.win_rate else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">盈亏比</div>
    <div class="value">{{ "%.2f"|format(metrics.profit_loss_ratio) if metrics.profit_loss_ratio else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">总交易次数</div>
    <div class="value">{{ metrics.total_trades if metrics.total_trades is defined else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">交易成本</div>
    <div class="value warn">¥{{ "%0.0f"|format(metrics.total_commission + metrics.total_stamp_duty) if metrics.total_commission is defined else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">最终净值</div>
    <div class="value">¥{{ "%0.0f"|format(metrics.final_nav) if metrics.final_nav else '-' }}</div>
  </div>
  <div class="metric-card">
    <div class="label">回测年数</div>
    <div class="value">{{ "%.1f"|format(metrics.years) if metrics.years else '-' }}</div>
  </div>
</div>

<div class="charts-section">
  {{ charts }}
</div>

<div class="footer">
  量化回测系统 · 数据来源: akshare · 报告仅供研究参考，不构成投资建议
</div>

</body>
</html>
"""
        return Template(template_str)
