import streamlit as st
import pandas as pd
import json
from pathlib import Path

st.set_page_config(page_title="MyFinances Quant Engine", layout="wide")

st.title("📈 Python Quant Backtest Dashboard")

output_dir = Path("d:/file/MyFinances/output")
if not output_dir.exists():
    st.error(f"Output directory not found: {output_dir}")
    st.stop()

# Find run folders
runs = [d.name for d in output_dir.iterdir() if d.is_dir()]
if not runs:
    st.info("No backtest runs found in output directory.")
    st.stop()

selected_run = st.sidebar.selectbox("Select Backtest Run", sorted(runs, reverse=True))

run_dir = output_dir / selected_run

# Load data
summary_file = run_dir / "summary.json"
equity_file = run_dir / "equity_curve.csv"
trades_file = run_dir / "trades.csv"
attempts_file = run_dir / "trade_attempts.csv"

if summary_file.exists():
    with open(summary_file, "r", encoding="utf-8") as f:
        summary_data = json.load(f)
    
    st.header("Metrics Overview")
    metrics = summary_data.get("metrics", {})
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Return", f"{metrics.get('total_return', 0):.2%}")
    col2.metric("Annualized", f"{metrics.get('annualized_return', 0):.2%}")
    col3.metric("Max Drawdown", f"{metrics.get('max_drawdown', 0):.2%}")
    col4.metric("Sharpe Ratio", f"{metrics.get('sharpe', 0):.2f}")
    col5.metric("Avg Turnover", f"{metrics.get('average_turnover', 0):.2f}")

st.divider()

if equity_file.exists():
    st.header("Equity Curve")
    equity_df = pd.read_csv(equity_file)
    if "date" in equity_df.columns:
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df.set_index("date", inplace=True)
    if "benchmark_equity" in equity_df.columns:
        st.line_chart(equity_df[["equity", "benchmark_equity"]])
    elif "equity" in equity_df.columns:
        st.line_chart(equity_df[["equity"]])
    else:
        st.write("Cannot find equity column in equity_curve.csv")

st.divider()

if attempts_file.exists() or trades_file.exists():
    st.header("Micro-Execution & Trade Analysis")
    tabs = st.tabs(["Trade Logs", "Order Attempts (Micro-queue)"])
    
    with tabs[0]:
        if trades_file.exists():
            trades_df = pd.read_csv(trades_file)
            st.dataframe(trades_df, use_container_width=True)
        else:
            st.write("No trades generated.")
            
    with tabs[1]:
        if attempts_file.exists():
            attempts_df = pd.read_csv(attempts_file)
            st.write("Visualizing Rejected/Partial Orders (Execution Realism):")
            
            if "reason" in attempts_df.columns:
                reasons = attempts_df["reason"].value_counts()
                st.bar_chart(reasons)
            
            st.dataframe(attempts_df, use_container_width=True)
        else:
            st.write("No order attempts logged.")
