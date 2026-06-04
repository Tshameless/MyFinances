// ============================================================
// 全局配置 — 改它就改全局
// ============================================================

// 选股范围：csi300 / csi500 / csi800 / all
export const STOCK_UNIVERSE = "csi300";

// 数据回溯交易日天数：30 / 60 / 90 / 120 / 180
// 值越小数据量越少、运行越快，但动量因子(60日)需要 >=60 天数据才有效
export const DATA_TRADING_DAYS = 30;

// 持仓数量（选前 N 名）
export const TOP_N_STOCKS = 30;

// 回测参数
export const INITIAL_CASH = 1_000_000;      // 初始资金（元）
export const REBALANCE_FREQ = "monthly";     // 调仓频率：monthly / weekly
export const COMMISION_RATE = 0.0003;      // 券商佣金（万三）
export const STAMP_TAX_RATE = 0.001;       // 印花税（千一，仅卖出）
export const SLIPPAGE_RATE  = 0.001;       // 滑点（千一）
export const MAX_POSITION_RATIO = 0.05;     // 单只股票最大仓位 5%
export const STOP_LOSS_PCT = 0.10;          // 个股止损线 10%

// 因子权重（合计 = 1）
export const FACTOR_WEIGHTS: Record<string, number> = {
    value_pe:     0.20,   // 估值：PE_TTM（越低越好，取负号）
    value_pb:     0.15,   // 估值：PB（越低越好，取负号）
    quality_roe:  0.20,   // 质量：ROE（越高越好）
    momentum_20:  0.15,   // 动量：20日收益率
    momentum_60:  0.15,   // 动量：60日收益率
    volatility:   0.10,   // 低波：波动率（越低越好，取负号）
    size:         0.05,   // 规模：市值（小盘因子，取负号）
};

// API 请求间隔（毫秒）
export const REQUEST_DELAY_MS = 200;

// 缓存设置
export const CACHE_DIR = "output/cache";
export const USE_CACHE = true;
