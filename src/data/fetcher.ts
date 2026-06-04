// ============================================================
// 数据获取模块 — 腾讯财经 + 新浪财经 公开接口
// 无需 API Key，直接 fetch 调用
// ============================================================

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import {
  CACHE_DIR,
  USE_CACHE,
  REQUEST_DELAY_MS,
  STOCK_UNIVERSE,
  DATA_TRADING_DAYS,
} from "../config.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cacheDir = path.resolve(__dirname, "../..", CACHE_DIR);
fs.mkdirSync(cacheDir, { recursive: true });

// ── 工具函数 ────────────────────────────────────────────────

/** 带重试的 fetch */
async function fetchWithRetry(
  url: string,
  options?: RequestInit,
  retries = 3
): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, {
        ...options,
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          Referer: "https://finance.qq.com/",
          ...options?.headers,
        },
      });
      if (res.ok) return res;
    } catch (e) {
      if (i === retries - 1) throw e;
      await sleep(2 ** i * 1000);
    }
  }
  throw new Error("fetch failed after retries");
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function cachePath(name: string) {
  return path.join(cacheDir, `${name}.csv`);
}

function readCache(name: string): string | null {
  const p = cachePath(name);
  if (USE_CACHE && fs.existsSync(p)) {
    const content = fs.readFileSync(p, "utf-8");
    if (content.trim().split("\n").length > 1) return content;
    fs.unlinkSync(p); // 删除空缓存
  }
  return null;
}

function writeCache(name: string, csv: string) {
  fs.writeFileSync(cachePath(name), csv, "utf-8");
}

// ── 接口实现 ────────────────────────────────────────────────

/**
 * 获取沪深300/中证500成分股列表
 * 使用东方财富公开接口（无需 key）
 */
export async function getStockUniverse(
  universe = STOCK_UNIVERSE
): Promise<string[]> {
  const cacheKey = `${universe}_stocks`;
  const cached = readCache(cacheKey);
  if (cached) return cached.split("\n").slice(1).map((l) => l.split(",")[0]);

  // 沪深300 = b.MK0024, 中证500 = b.MK0035
  const fsMap: Record<string, string> = {
    csi300: "b:MK0024",
    csi500: "b:MK0035",
    csi800: "b:MK0024,b:MK0035",
    all: "", // 全市场后面单独处理
  };

  const fs = fsMap[universe] || fsMap.csi300;
  const url =
    `https://push2.eastmoney.com/api/qt/clist/get?` +
    `pn=1&pz=500&np=1&fltt=2&invt=2&fid=f3&fs=${fs}` +
    `&fields=f12,f14`;

  try {
    const res = await fetchWithRetry(url);
    const j = (await res.json()) as any;
    const stocks: string[] =
      j?.data?.diff?.map((d: any) => {
        const code = String(d.f12);
        return code.startsWith("6") ? `sh${code}` : `sz${code}`;
      }) || [];
    writeCache(cacheKey, "code\n" + stocks.join("\n"));
    return stocks;
  } catch {
    // fallback：手动硬编码前20只沪深300
    return [
      "sh601318", "sh600519", "sh600036", "sh601166", "sh600900",
      "sh603288", "sh600276", "sh601888", "sh600309", "sh601012",
      "sz000858", "sz002594", "sz000333", "sz002475", "sz300750",
      "sz000651", "sz002415", "sz300059", "sz000568", "sz002304",
    ];
  }
}

/**
 * 获取单只股票日线数据（腾讯财经接口）
 * 返回 [{date, open, close, high, low, volume}, ...]
 */
export async function fetchDailyPrices(
  code: string,
  start: string,
  end: string
): Promise<Record<string, any>[]> {
  const url =
    `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?` +
    `_var=kline_day&param=${code},day,,,${DATA_TRADING_DAYS},qfq`;

  try {
    const res = await fetchWithRetry(url);
    const text = await res.text();
    const jsonStr = text.replace(/^kline_day=/, "");
    const j = JSON.parse(jsonStr) as any;
    const rawData = j?.data?.[code]?.qfqday || j?.data?.[code]?.day || [];
    return rawData.map((d: any[]) => ({
      date: d[0],
      open: Number(d[1]),
      close: Number(d[2]),
      high: Number(d[3]),
      low: Number(d[4]),
      volume: Number(d[5]),
    }));
  } catch {
    return [];
  }
}

/**
 * 批量获取多只股票日线，返回 code → K线数组
 */
export async function fetchBatchPrices(
  codes: string[],
  start: string,
  end: string
): Promise<Record<string, Record<string, any>[]>> {
  const result: Record<string, Record<string, any>[]> = {};
  let done = 0;
  for (const code of codes) {
    const klines = await fetchDailyPrices(code, start, end);
    if (klines.length > 0) result[code] = klines;
    done++;
    if (done % 10 === 0) {
      console.log(`  获取日线行情 [${done}/${codes.length}]`);
    }
    await sleep(REQUEST_DELAY_MS);
  }
  return result;
}

/**
 * 获取财务快照（PE/PB/市值等）
 * 使用新浪财经接口
 */
export async function fetchFinancialSnapshot(
  codes?: string[]
): Promise<Record<string, any>[]> {
  const cacheKey = "a_share_snapshot";
  const cached = readCache(cacheKey);
  if (cached) {
    return cached.split("\n").slice(1).map((l) => {
      const [code, name, pe, pb, cap] = l.split(",");
      return { code, name, pe_ttm: +pe, pb: +pb, market_cap: +cap };
    });
  }

  // 新浪 hq 接口，批量查询
  if (!codes || codes.length === 0) return [];
  const batchSize = 50;
  const rows: Record<string, any>[] = [];

  for (let i = 0; i < codes.length; i += batchSize) {
    const batch = codes.slice(i, i + batchSize);
    const symbols = batch.map((c) => c.replace(/^(sh|sz|bj)/, "").toUpperCase());
    const url = `https://hq.sinajs.cn/list=${symbols.join(",")}`;
    try {
      const res = await fetchWithRetry(url);
      const text = await res.text();
      const lines = text.split("\n").filter(Boolean);
      for (const line of lines) {
        const m = line.match(/var hq_str_(.*?)="(.*?)";/);
        if (!m) continue;
        const fields = m[2].split(",");
        if (fields.length < 32) continue;
        rows.push({
          code: batch[symbols.indexOf(m[1].toUpperCase())] || m[1],
          name: fields[0],
          pe_ttm: parseFloat(fields[39]) || NaN,
          pb: parseFloat(fields[46]) || NaN,
          market_cap: parseFloat(fields[45]) * parseFloat(fields[3]) || NaN,
        });
      }
    } catch {}
    await sleep(REQUEST_DELAY_MS);
  }

  const csv = "code,name,pe_ttm,pb,market_cap\n" +
    rows.map((r) => `${r.code},${r.name},${r.pe_ttm},${r.pb},${r.market_cap}`).join("\n");
  writeCache(cacheKey, csv);
  return rows;
}

/**
 * 获取指数日线（用于计算基准收益）
 */
export async function fetchIndexPrices(
  indexCode: string,
  start: string,
  end: string
): Promise<Record<string, any>[]> {
  const url =
    `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?` +
    `_var=kline_day&param=${indexCode},day,,,${DATA_TRADING_DAYS},`;
  try {
    const res = await fetchWithRetry(url);
    const text = await res.text();
    const jsonStr = text.replace(/^kline_day=/, "");
    const j = JSON.parse(jsonStr) as any;
    const rawData = j?.data?.[indexCode]?.qfqday || j?.data?.[indexCode]?.day || [];
    return rawData.map((d: any[]) => ({
      date: d[0],
      close: Number(d[2]),
    }));
  } catch {
    return [];
  }
}
