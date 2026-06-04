// ===========================================================
// 主入口 — 串联：数据获取 → 因子计算 → 回测 → 报告
// 用法：npx tsx src/main.ts [--days N] [--top N] [--skip-fetch]
// ===========================================================

import { fileURLToPath } from "url";
import { join, resolve } from "path";
import { parseArgs } from "util";
import * as config from "./config.js";
const {
  STOCK_UNIVERSE,
  DATA_TRADING_DAYS,
  TOP_N_STOCKS,
  INITIAL_CASH,
  REBALANCE_FREQ,
} = config;
import {
  getStockUniverse,
  fetchBatchPrices,
  fetchFinancialSnapshot,
  fetchIndexPrices,
} from "./data/fetcher.js";
import { calculateFactors, printFactorStats } from "./factors/calculator.js";
import { runBacktest } from "./backtest/engine.js";
import { printSummary, printAnnualReturns, saveCSV } from "./report/generator.js";

const __dirname = resolve(fileURLToPath(import.meta.url), "..");

// ── 日期工具 ────────────────────────────────
function calcDateRange(tradingDays: number): { start: string; end: string } {
  const end = new Date();
  const calDays = Math.ceil(tradingDays * 2);
  const start = new Date(end);
  start.setDate(start.getDate() - calDays);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

// ── 主流程 ──────────────────────────────────
async function main() {
  const args = parseArgs({
    options: {
      days: { type: "string" },
      top: { type: "string" },
      "skip-fetch": { type: "boolean" },
      start: { type: "string" },
      end: { type: "string" },
    },
  });

  const tradingDays = parseInt(args.values["days"] ?? "") || DATA_TRADING_DAYS;
  const topN = parseInt(args.values["top"] ?? "") || TOP_N_STOCKS;
  const skipFetch = args.values["skip-fetch"] ?? false;

  let startDate: string, endDate: string;
  if (args.values["start"] && args.values["end"]) {
    startDate = args.values["start"]!;
    endDate = args.values["end"]!;
  } else {
    const range = calcDateRange(tradingDays);
    startDate = range.start;
    endDate = range.end;
  }

  console.log("=".repeat(60));
  console.log("  🚀 A股多因子选股量化系统（TypeScript版）");
  console.log(`  选股范围: ${STOCK_UNIVERSE.toUpperCase()}  ·  持仓数: ${topN}`);
  console.log(`  调仓: ${REBALANCE_FREQ}  ·  回溯交易日: ${tradingDays}天`);
  console.log(`  ${startDate} → ${endDate}`);
  console.log("=".repeat(60));

  // ── 1. 获取成分股 ────────────────────
  console.log("\n📡 阶段一：数据获取");
  console.log("  获取成分股列表...");
  const codes = await getStockUniverse(STOCK_UNIVERSE);
  if (!codes || codes.length === 0) {
    console.error("  ❌ 未获取到成分股，退出。");
    process.exit(1);
  }
  console.log(`  ✅ 共 ${codes.length} 只成分股`);

  // ── 2. 获取日线行情 ─────────────────
  console.log(`\n  获取日线行情（最近 ${tradingDays} 个交易日）...`);
  const priceDict = await fetchBatchPrices(codes, startDate, endDate);
  const validCodes = Object.keys(priceDict).filter(
    (c) => priceDict[c].length > 0
  );
  console.log(`  ✅ 成功获取 ${validCodes.length}/${codes.length} 只股票日线`);

  if (validCodes.length === 0) {
    console.error("  ❌ 未获取到任何日线数据，退出。");
    process.exit(1);
  }

  // ── 3. 获取财务快照 ─────────────────
  console.log("\n  获取财务快照（PE/PB/市值）...");
  const snapshot = await fetchFinancialSnapshot(validCodes);
  console.log(`  ✅ 获取 ${snapshot.length} 只股票财务指标`);

  // ── 4. 组装股票数据 ─────────────────
  const stocks = validCodes.map((code) => {
    const snap = snapshot.find((s: any) => s.code === code) || {};
    return {
      code,
      name: snap.name || code,
      prices: priceDict[code],
      pe_ttm: snap.pe_ttm,
      pb: snap.pb,
      market_cap: snap.market_cap,
    };
  });

  // ── 5. 因子计算 ─────────────────────
  console.log("\n🧮 阶段二：因子计算");
  const scores = calculateFactors(stocks, config.FACTOR_WEIGHTS);
  printFactorStats(scores);

  // ── 6. 选股（每月调仓信号）───────
  console.log(`\n📈 阶段三：选股（Top ${topN}）`);
  const sorted = scores
    .filter((s) => !isNaN(s.totalScore))
    .sort((a, b) => b.totalScore - a.totalScore);
  const selected = sorted.slice(0, topN);
  console.log("  选中股票：");
  selected.slice(0, 10).forEach((s, i) => {
    console.log(`    ${i + 1}. ${s.code} ${s.name}  得分:${s.totalScore.toFixed(3)}`);
  });
  if (selected.length > 10) console.log(`    ... 共 ${selected.length} 只`);

  // ── 7. 回测 ─────────────────────────
  console.log("\n⚙️  阶段四：回测引擎");
  const priceForBacktest: Record<string, { date: string; close: number }[]> = {};
  for (const s of selected) {
    const prices = priceDict[s.code];
    if (!prices) continue;
    priceForBacktest[s.code] = prices.map((p: any) => ({
      date: p.date,
      close: p.close,
    }));
  }

  const result = runBacktest(
    [selected.map((s) => ({ code: s.code, name: s.name, score: s.totalScore }))],
    priceForBacktest,
    startDate,
    endDate
  );

  // ── 8. 输出报告 ────────────────────
  console.log("\n📊 阶段五：生成报告");
  printSummary(result);
  printAnnualReturns(result);
  const csvPath = saveCSV(result);
  console.log(`\n  ✅ 回测完成！净值曲线已保存至：${csvPath}`);
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("❌ 运行出错：", err);
  process.exit(1);
});
