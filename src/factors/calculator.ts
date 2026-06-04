// ============================================================
// 因子计算模块
// 计算 7 个因子，Z-score 标准化，合成综合得分
// ============================================================

import { readFileSync } from "fs";
import { join } from "path";
import { fileURLToPath, URL } from "url";

const __dirname = join(fileURLToPath(import.meta.url), "..");

export interface StockData {
  code: string;
  name: string;
  prices: Record<string, number>[];   // {date, close, ...}
  pe_ttm?: number;
  pb?: number;
  roe_ttm?: number;
  market_cap?: number;
}

export interface FactorScores {
  code: string;
  name: string;
  factors: Record<string, number>;  // raw factor values
  zscores: Record<string, number>;  // z-scores
  totalScore: number;
}

// ── 因子计算 ─────────────────────────────────────────────

function calcReturns(prices: Record<string, number>[], days: number): number {
  if (prices.length < days + 1) return NaN;
  const start = prices[prices.length - days - 1].close;
  const end = prices[prices.length - 1].close;
  return (end - start) / start;
}

function calcVolatility(prices: Record<string, number>[], days = 20): number {
  if (prices.length < days) return NaN;
  const slice = prices.slice(-days);
  const rets = slice.slice(1).map((p, i) => Math.log(p.close / slice[i].close));
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const varr = rets.reduce((a, r) => a + (r - mean) ** 2, 0) / rets.length;
  return Math.sqrt(varr * 252); // annualized
}

// ── 主函数 ─────────────────────────────────────────────

export function calculateFactors(
  stocks: StockData[],
  factorWeights: Record<string, number>
): FactorScores[] {
  const scores: FactorScores[] = [];

  for (const stock of stocks) {
    if (!stock.prices || stock.prices.length === 0) continue;

    const f: Record<string, number> = {};

    // 估值因子（越低越好 → 取负号）
    f.value_pe = stock.pe_ttm ? -stock.pe_ttm : NaN;
    f.value_pb = stock.pb ? -stock.pb : NaN;

    // 质量因子（越高越好）
    f.quality_roe = stock.roe_ttm ?? NaN;

    // 动量因子
    f.momentum_20 = calcReturns(stock.prices, 20);
    f.momentum_60 = calcReturns(stock.prices, 60);

    // 低波因子（越低越好 → 取负号）
    f.volatility = -calcVolatility(stock.prices, 20);

    // 规模因子（小盘 → 取负号，市值越小越好）
    f.size = stock.market_cap ? -Math.log(stock.market_cap) : NaN;

    scores.push({
      code: stock.code,
      name: stock.name,
      factors: f,
      zscores: {},
      totalScore: 0,
    });
  }

  // Z-score 标准化
  const factorNames = Object.keys(factorWeights);
  for (const fname of factorNames) {
    const values = scores
      .map((s) => s.factors[fname])
      .filter((v) => !isNaN(v));
    if (values.length === 0) continue;

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const std = Math.sqrt(
      values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length
    );

    for (const s of scores) {
      const v = s.factors[fname];
      s.zscores[fname] = isNaN(v) || std === 0 ? 0 : (v - mean) / std;
    }
  }

  // 合成综合得分
  for (const s of scores) {
    s.totalScore = factorNames.reduce(
      (sum, fname) => sum + (s.zscores[fname] || 0) * (factorWeights[fname] || 0),
      0
    );
  }

  return scores;
}

// ── 调试：打印因子分布 ──────────────────────────────────

export function printFactorStats(scores: FactorScores[]): void {
  const factorNames = Object.keys(scores[0]?.factors || {});
  console.log("\n  📊 因子统计摘要：");
  for (const fname of factorNames) {
    const vals = scores.map((s) => s.factors[fname]).filter((v) => !isNaN(v));
    if (vals.length === 0) continue;
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    console.log(
      `    ${fname.padEnd(18)} mean=${mean.toFixed(4).padStart(10)}  ` +
      `min=${min.toFixed(4).padStart(10)}  max=${max.toFixed(4).padStart(10)}  ` +
      `valid=${vals.length}`
    );
  }
}
