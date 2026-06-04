// ===========================================================
// 报告生成模块 — 输出 CSV 净值曲线 + 控制台摘要
// ===========================================================

import { writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { fileURLToPath } from "url";
import type { BacktestResult } from "../backtest/engine.js";

const __dirname = join(fileURLToPath(import.meta.url), "..");

export function printSummary(result: BacktestResult): void {
  const r = result;
  console.log("\n" + "=".repeat(60));
  console.log("  📊 回测结果摘要");
  console.log("=".repeat(60));
  console.log(`  累计收益率:   ${(r.totalReturn * 100).toFixed(2)}%`);
  console.log(`  年化收益率:   ${(r.annualReturn * 100).toFixed(2)}%`);
  console.log(`  夏普比率:     ${r.sharpe.toFixed(2)}`);
  console.log(`  最大回撤:     ${(r.maxDrawdown * 100).toFixed(2)}%`);
  console.log(`  日胜率:       ${(r.winRate * 100).toFixed(2)}%`);
  console.log(`  盈亏比:       ${r.profitLossRatio.toFixed(2)}`);
  console.log(`  期末净值:     ¥${r.finalNav.toLocaleString("zh-CN")}`);
  console.log("=".repeat(60) + "\n");
}

export function saveCSV(result: BacktestResult, filepath?: string): string {
  const outDir = join(fileURLToPath(import.meta.url), "../../../output");
  mkdirSync(outDir, { recursive: true });
  const outPath = filepath || join(outDir, "nav.csv");

  const header = "date,nav,cash,positions,daily_return";
  const rows = result.dailyNav.map(
    (d) =>
      `${d.date},${d.nav.toFixed(2)},${d.cash.toFixed(2)},${d.positions},${(d.return * 100).toFixed(4)}`
  );
  writeFileSync(outPath, [header, ...rows].join("\n"), "utf-8");
  console.log(`  ✅ 净值已保存至 ${outPath}`);
  return outPath;
}

/** 年度收益表 */
export function printAnnualReturns(result: BacktestResult): void {
  const byYear: Record<string, { nav: number[] }> = {};
  for (const d of result.dailyNav) {
    const year = d.date.slice(0, 4);
    if (!byYear[year]) byYear[year] = { nav: [] };
    byYear[year].nav.push(d.nav);
  }

  console.log("\n  年度收益：");
  console.log("  年份    收益率");
  console.log("  " + "-".repeat(30));
  for (const [year, data] of Object.entries(byYear)) {
    const ret =
      (data.nav[data.nav.length - 1] - data.nav[0]) / data.nav[0];
    console.log(`  ${year}   ${(ret * 100).toFixed(2).padStart(8)}%`);
  }
}
