// ===========================================================
// 回测引擎 — 日频调仓回测
// ===========================================================

import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { fileURLToPath } from "url";
import {
  INITIAL_CASH,
  COMMISION_RATE,
  STAMP_TAX_RATE,
  SLIPPAGE_RATE,
  MAX_POSITION_RATIO,
  STOP_LOSS_PCT,
  REBALANCE_FREQ,
} from "../config.js";

const __dirname = join(fileURLToPath(import.meta.url), "..");

export interface Position {
  code: string;
  name: string;
  shares: number;
  cost: number;      // 买入均价
  value: number;      // 当前市值
}

export interface DailyNav {
  date: string;
  nav: number;       // 总资产
  cash: number;
  positions: number;  // 持仓数量
  return: number;     // 当日收益率
}

export interface BacktestResult {
  dailyNav: DailyNav[];
  finalNav: number;
  totalReturn: number;
  annualReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  profitLossRatio: number;
}

// ── 工具函数 ─────────────────────────────────────────

function calcDrawdown(navSeries: number[]): number {
  let max = navSeries[0];
  let dd = 0;
  for (const v of navSeries) {
    if (v > max) max = v;
    const cur = (max - v) / max;
    if (cur > dd) dd = cur;
  }
  return dd;
}

function calcSharpe(returns: number[], riskFree = 0.0): number {
  if (returns.length < 2) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const std = Math.sqrt(
    returns.reduce((a, r) => a + (r - mean) ** 2, 0) / returns.length
  );
  if (std === 0) return 0;
  return ((mean - riskFree) / std) * Math.sqrt(252);
}

// ── 主回测函数 ─────────────────────────────────────

export function runBacktest(
  selectedStocks: { code: string; name: string; score: number }[][],
  priceData: Record<string, { date: string; close: number }[]>,
  startDate: string,
  endDate: string
): BacktestResult {
  let cash = INITIAL_CASH;
  const positions: Record<string, Position> = {};
  const dailyNav: DailyNav[] = [];
  let prevNav = INITIAL_CASH;

  // 收集所有交易日
  const allDates = new Set<string>();
  for (const prices of Object.values(priceData)) {
    for (const p of prices) allDates.add(p.date);
  }
  const dates = [...allDates].sort().filter(
    (d) => d >= startDate && d <= endDate
  );

  // 按月调仓的月份记录
  let lastRebalanceMonth = "";

  for (let i = 0; i < dates.length; i++) {
    const date = dates[i];
    const month = date.slice(0, 7);

    // ── 调仓日 ─────────────────────
    if (
      (REBALANCE_FREQ === "monthly" && month !== lastRebalanceMonth) ||
      (REBALANCE_FREQ === "weekly" && i % 5 === 0)
    ) {
      lastRebalanceMonth = month;
      rebalance(selectedStocks, priceData, date, positions, cash);
      // 重新计算 cash（rebalance 会修改 positions 和 cash）
      cash = INITIAL_CASH - Object.values(positions).reduce(
        (a, p) => a + p.shares * p.cost, 0
      );
    }

    // ── 更新持仓市值 + 止损 ────────
    let posValue = 0;
    for (const code of Object.keys(positions)) {
      const pos = positions[code];
      const prices = priceData[code];
      if (!prices) continue;
      const today = [...prices].reverse().find((p) => p.date <= date);
      if (!today) continue;
      const curPrice = today.close;

      // 止损
      if (curPrice < pos.cost * (1 - STOP_LOSS_PCT)) {
        cash += curPrice * pos.shares * (1 - COMMISION_RATE - SLIPPAGE_RATE);
        delete positions[code];
        continue;
      }
      pos.value = curPrice * pos.shares;
      posValue += pos.value;
    }

    const totalNav = cash + posValue;
    const dailyReturn = prevNav > 0 ? (totalNav - prevNav) / prevNav : 0;
    prevNav = totalNav;

    dailyNav.push({
      date,
      nav: totalNav,
      cash,
      positions: Object.keys(positions).length,
      return: dailyReturn,
    });
  }

  // ── 计算评估指标 ──────────────────
  const navValues = dailyNav.map((d) => d.nav);
  const returns = dailyNav.map((d) => d.return).filter((r) => r !== 0);
  const totalReturn = (navValues[navValues.length - 1] - INITIAL_CASH) / INITIAL_CASH;
  const tradingDays = dailyNav.length;
  const annualReturn =
    tradingDays > 0
      ? Math.pow(1 + totalReturn, 252 / tradingDays) - 1
      : 0;

  return {
    dailyNav,
    finalNav: navValues[navValues.length - 1],
    totalReturn,
    annualReturn,
    sharpe: calcSharpe(returns),
    maxDrawdown: calcDrawdown(navValues),
    winRate: returns.filter((r) => r > 0).length / returns.length || 0,
    profitLossRatio: calcProfitLossRatio(returns),
  };
}

function calcProfitLossRatio(returns: number[]): number {
  const wins = returns.filter((r) => r > 0);
  const losses = returns.filter((r) => r < 0).map(Math.abs);
  if (losses.length === 0) return wins.length > 0 ? 99 : 0;
  const avgWin = wins.reduce((a, b) => a + b, 0) / wins.length;
  const avgLoss = losses.reduce((a, b) => a + b, 0) / losses.length;
  return avgLoss > 0 ? avgWin / avgLoss : 99;
}

// ── 调仓逻辑 ─────────────────────────────────────
function rebalance(
  selectedStocks: { code: string; name: string; score: number }[][],
  priceData: Record<string, { date: string; close: number }[]>,
  date: string,
  positions: Record<string, Position>,
  cash: number
): void {
  // 找到当前日期对应的选股列表
  const target = selectedStocks.find(
    (batch) => batch[0]?.code && priceData[batch[0].code]
  );
  if (!target || target.length === 0) return;

  const targetCodes = new Set(target.map((s) => s.code));

  // 卖出不在目标列表中的持仓
  for (const code of Object.keys(positions)) {
    if (!targetCodes.has(code)) {
      const pos = positions[code];
      const prices = priceData[code];
      const today = prices ? [...prices].reverse().find((p) => p.date <= date) : undefined;
      const price = today?.close || pos.cost;
      const proceeds =
        price * pos.shares * (1 - COMMISION_RATE - STAMP_TAX_RATE - SLIPPAGE_RATE);
      cash += proceeds;
      delete positions[code];
    }
  }

  // 计算目标仓位
  const totalValue = cash + Object.values(positions).reduce((a, p) => a + p.value, 0);
  const targetValuePerStock = totalValue / target.length;

  // 买入/调整持仓
  for (const stock of target) {
    const prices = priceData[stock.code];
    if (!prices) continue;
    const today = [...prices].reverse().find((p) => p.date <= date);
    if (!today) continue;
    const price = today.close;
    const targetShares = Math.floor(targetValuePerStock / price / 100) * 100;
    const curShares = positions[stock.code]?.shares || 0;
    const diff = targetShares - curShares;

    if (diff > 0) {
      const cost = diff * price * (1 + COMMISION_RATE + SLIPPAGE_RATE);
      if (cost <= cash) {
        if (positions[stock.code]) {
          positions[stock.code].shares = targetShares;
          positions[stock.code].cost = price;
        } else {
          positions[stock.code] = {
            code: stock.code,
            name: stock.name,
            shares: targetShares,
            cost: price,
            value: targetShares * price,
          };
        }
        cash -= cost;
      }
    } else if (diff < 0) {
      const proceeds =
        -diff * price * (1 - COMMISION_RATE - STAMP_TAX_RATE - SLIPPAGE_RATE);
      positions[stock.code].shares = targetShares;
      positions[stock.code].value = targetShares * price;
      cash += proceeds;
    }
  }
}
