# A股量化回测工具

这是一个面向 A 股研究场景的日频多因子回测工具，适合用标准 CSV 做策略研究、参数试验和中文报告导出。

## 功能

- 支持内置演示数据和本地 CSV 行情数据。
- 对 A 股 CSV 做日期解析、重复行检查、价格校验和可交易标记解析。
- 使用交集交易日对齐所有标的，避免按数组下标错位回测。
- 支持收盘价或复权价回测、基准比较、买卖受限持仓处理。
- 支持估值价格和成交价格分离，可用 `close`/`adjusted_close` 做估值，并用 `close`/`adjusted_close`/`open`/`vwap` 做交易执行价。
- 支持信号日和成交日分离，可配置延迟若干个交易 bar 后执行，便于模拟收盘后出信号、次日开盘或 VWAP 成交。
- 支持动态股票池 CSV，调仓时只在当前有效股票池内开新仓，便于模拟指数成分、行业池或自定义可投池。
- 支持等权选股、固定周期调仓、现金/股数持仓账本、A 股整手买入和基于实际成交的交易成本扣减。
- 支持内置因子评分或外部 `date,symbol,score` 评分 CSV，并可选择高分优先或低分优先。
- 支持目标现金权重，便于模拟保留现金缓冲或降低整体仓位。
- 支持单票目标权重上限，降低可买标的不足或高集中组合导致的风险暴露。
- 支持每个行业/分组最多入选数量，降低同一板块过度集中。
- 支持按成交量参与率限制单日最大成交股数，减少小成交量标的的容量高估。
- 支持对缺失行情用前值补不可交易停牌估值条，减少停牌缺行导致的全市场日历丢失。
- 支持 CSV 显式 `is_suspended`/`suspended` 停牌标记，并输出停牌审计分析，便于核对停牌估值和受影响股票。
- 支持 TOML 配置文件、因子权重覆盖、卖出印花税建模。
- 支持通过 `symbol_name_csv` 给 A 股代码补充中文名映射，提升表格、图表和网页报告可读性。
- 支持通过 `symbol_group_csv` 给 A 股代码补充行业、板块或自定义分组，用于持仓分组暴露分析。
- 输出净值曲线 CSV、调仓日志 CSV、绩效摘要 CSV 和绩效摘要 JSON。
- 输出每日持仓账本 CSV，便于核对每只股票的股数、市值、权重和现金余额。
- 输出逐笔交易明细 CSV，便于核对每次买卖的股数、成交金额、成本拆分和现金变化。
- 输出未成交原因 CSV，解释现金不足、不够一手、T+1 锁定、停牌、不可交易、涨停不可买、跌停不可卖等跳过原因。
- 输出执行质量分析，汇总成交率、拒单原因、真实交易约束类别、买卖方向、日级阻塞强度、成本 bps 和平均成交金额。
- 输出换手与持仓周期分析，按调仓日拆解进入、退出、留存标的，并统计已实现持仓天数。
- 输出持仓暴露分析，汇总每日现金权重、股票仓位、持仓数量、HHI 集中度和最大风险贡献标的。
- 输出分组暴露分析，在提供代码分组映射时汇总行业/板块权重、最大分组权重、分组风险贡献和未映射权重。
- 输出收益归因分析，按上一期持仓权重和下一期价格收益拆解个股贡献、分组贡献、残差和成本拖累。
- 输出成本归因分析，按日期、标的、分组、买卖方向、交易原因和成本分项拆解佣金、滑点、过户费与印花税。
- 输出盈亏对账账本，逐日核对期初/期末权益、交易现金流、成本、现金、市值和对账差异。
- 输出策略健康诊断和风险闸门，把收益、回撤、滚动稳定性、执行、集中度、成本、换手、持仓周期、归因和对账合成为评分、等级、上线闸门和风险预警。
- 输出停牌审计分析，按股票和日期汇总停牌估值条数量、停牌比例和受影响股票。
- 输出因子评分明细 CSV，记录每次调仓时的原始因子、标准化因子、总分和入选状态。
- 输出基于全可用价格序列的因子 IC / Rank IC 分析，帮助判断因子方向和下一期收益的横截面关系。
- 输出基于全可用价格序列的因子分组收益分析，观察低分组到高分组的下一期收益差和单调性。
- 输出因子衰减分析，跟踪相邻调仓期的因子排序稳定性、入选留存率和入选换手率，帮助识别信号过快衰减或组合过度翻仓。
- 输出因子相关性矩阵，识别动量、反转、低波和总分之间的冗余度，避免把高度相关的信号误当作独立 alpha 来源。
- 支持基于涨跌幅自动推断涨停不可买、跌停不可卖。
- 支持 ST、创业板、科创板、北交所等不同涨跌停阈值，也可用 CSV 行级 `limit_rate` 覆盖。
- 绩效 JSON 包含样本内/样本外半段切分指标，辅助观察结果稳定性。
- 输出回撤序列、回撤持续期、月度收益表和滚动风险分析，方便定位回撤发生区间、水下天数、收益月份分布和阶段性风险稳定性。
- 输出相对基准表现分析，在提供基准时展示主动收益、主动净值、主动回撤、主动胜率、最佳/最差主动日、跟踪误差和信息比率。
- `--validate-csv` 会生成数据质量报告，检查缺失交易日、复权价缺失、实际执行价字段覆盖率、基准日期对齐、异常收益、每日股票数量变化、股票池质量、分组映射质量和外部评分覆盖率。
- 自动写出 `run_manifest.json`，记录本次配置、输入和产物路径。
- 支持基于 TOML `sweep` 配置的批量参数扫描与结果汇总。
- 支持 walk-forward 滚动窗口验证，按多个连续时间窗口输出稳定性汇总。
- 支持 walk-forward 参数优化：每个训练窗口从 `[sweep]` 参数网格中选最优参数，再在后续测试窗口验证，并输出训练/测试退化、测试效率和过拟合风险诊断。
- 自动输出中文化 SVG 图表和批量排行榜，减少手工读表。
- 支持 `--rank-by` 自定义批量排序指标；双参数 sweep 会自动输出热力图。
- 批量扫描会输出参数稳定性、综合评分、参数敏感度、推荐参数档位、健康闸门失败原因分布和可行动调参建议，提示最佳方案是否可能是参数孤岛，以及常见参数组合为什么被风险闸门淘汰。
- 单次和批量运行都会生成网页报告（HTML），方便直接浏览结果。
- 回测内核、执行撮合模型、交易规则、风险分析、因子分析、执行分析、暴露分析、批量稳定性分析、CSV/HTML 报告和运行产物编排已经拆分为独立模块，便于继续扩展。
- 内置 `unittest` 回归测试。

## CSV 格式

必填列：

- `date`
- `symbol`
- `close`

可选列：

- `adjusted_close`
- `open`
- `vwap`
- `volume`
- `tradable`
- `can_buy`
- `can_sell`
- `is_suspended` 或 `suspended`
- `is_limit_up`
- `is_limit_down`
- `is_st`
- `limit_rate`

`symbol` 必须使用 6 位 A 股代码，例如 `600519`、`000001`。

日期支持 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD`。

## 运行示例

```bash
python -m python_quant.main --demo
python -m python_quant.main --csv data/sample_prices.csv --validate-csv
python -m python_quant.main --csv data/sample_prices.csv --benchmark-csv data/benchmark.csv --validate-csv
python -m python_quant.main --stock-pool-csv data/stock_pool.csv --validate-csv
python -m python_quant.main --symbol-group-csv data/symbol_groups.csv --validate-csv
python -m python_quant.main --csv data/sample_prices.csv --factor-score-csv data/factor_scores.csv --validate-csv
python -m python_quant.main --csv data/sample_prices.csv --top-n 5 --rebalance-days 10
python -m python_quant.main --csv data/sample_prices.csv --selection-mode bottom
python -m python_quant.main --csv data/sample_prices.csv --factor-score-csv data/factor_scores.csv
python -m python_quant.main --csv data/sample_prices.csv --benchmark-csv data/benchmark.csv --price-field adjusted_close
python -m python_quant.main --csv data/sample_prices.csv --lot-size 1 --initial-cash 10000
python -m python_quant.main --csv data/sample_prices.csv --start-date 2020-01-01 --end-date 2024-12-31
python -m python_quant.main --csv data/sample_prices.csv --infer-limit-flags --limit-up-down-rate 0.10
python -m python_quant.main --csv data/sample_prices.csv --max-volume-participation 0.1
python -m python_quant.main --csv data/sample_prices.csv --stock-pool-csv data/stock_pool.csv
python -m python_quant.main --config backtest.example.toml --csv data/sample_prices.csv
python -m python_quant.main --config backtest.example.toml --demo --sweep
python -m python_quant.main --config backtest.example.toml --demo --sweep --rank-by sharpe
```

## 配置文件

可以使用 TOML 配置文件集中管理参数，再用命令行覆盖局部值。

示例见：`backtest.example.toml`

当前版本要求把回测参数放在 `[backtest]` 配置段中，不再兼容顶层同名参数直写。

当前回测默认使用 A 股 100 股整手交易：

```toml
lot_size = 100
```

如果只是做小资金或教学样例，可以把 `lot_size` 设为 `1`，让回测允许按单股成交。回测内部会维护现金和持仓股数，买入按整手向下取整，卖出会检查 `tradable`、`can_sell` 和同日新买入的 T+1 限制。

也可以用命令行临时覆盖：

```bash
python -m python_quant.main --demo --lot-size 1
```

默认策略会按因子总分从高到低选择 `top_n` 只股票。如果要做因子方向压力测试或反向信号对照，可以把选股方向改成低分优先：

```toml
selection_mode = "bottom"
```

```bash
python -m python_quant.main --demo --selection-mode bottom
```

`selection_mode` 可选 `top` 或 `bottom`，默认 `top`。这个字段也可以放进 `[sweep]`，用于批量比较高分组合和低分组合的表现差异。

如果你已经在外部完成因子工程或模型打分，可以提供一个评分 CSV，让回测直接使用外部分数：

```csv
date,symbol,score
2024-01-04,000001,0.82
2024-01-04,600519,1.15
2024-01-04,000333,-0.20
```

```toml
factor_score_csv = "data/factor_scores.csv"
score_source = "auto"
```

```bash
python -m python_quant.main --csv prices.csv --factor-score-csv data/factor_scores.csv
```

`score_source` 可选 `auto`、`builtin`、`external`。默认 `auto` 会在调仓日存在外部评分时优先使用外部分数，缺失时回退到内置三因子；`builtin` 会忽略外部评分，只使用内置三因子；`external` 要求每个调仓日都必须有外部评分，缺失会直接报错。`selection_mode = "top"` 会选择高分标的，`selection_mode = "bottom"` 会选择低分标的，便于做 alpha 方向验证。运行清单会记录 `factor_score_csv` 的路径、大小和 SHA256；单次运行还会输出外部评分质量报告并把评分覆盖率纳入策略健康诊断。

费用模型支持比例费率、最低佣金和过户费：

```toml
commission_rate = 0.0003
buy_commission_rate = 0.00025
sell_commission_rate = 0.00035
slippage_rate = 0.0005
stamp_duty_rate = 0.001
min_commission = 5.0
transfer_fee_rate = 0.00001
```

`buy_commission_rate` 和 `sell_commission_rate` 不填时会沿用 `commission_rate`，适合券商买卖费率不同或需要做压力测试的场景。最低佣金仍按单笔成交额在买卖两侧分别生效。

滚动风险分析窗口可以在配置文件或命令行中调整：

```toml
rolling_risk_window = 20
```

```bash
python -m python_quant.main --demo --rolling-risk-window 10
```

窗口越短，越容易暴露阶段性风险变化；窗口越长，结果更平滑，适合观察中期稳定性。

如果行情 CSV 在停牌日缺少某些股票行，可以启用前值补停牌估值：

```toml
forward_fill_suspended_bars = true
```

```bash
python -m python_quant.main --csv prices.csv --forward-fill-suspended-bars
```

启用后，缺失行会用该股票上一条价格补一条 `tradable=false`、`can_buy=false`、`can_sell=false`、`volume=0`、`is_suspended=true` 的估值条。该股票仍会参与持仓估值，但当天不能买入或卖出。单次回测会额外输出 `suspension_analysis.csv`、`suspension_daily.csv` 和 `suspension_analysis.json`。

默认情况下，成交价字段沿用 `price_field`。如果希望估值使用复权价、成交更接近真实执行，可以单独设置成交价字段：

```toml
price_field = "adjusted_close"
execution_price_field = "open"
execution_delay_days = 1
```

```bash
python -m python_quant.main --csv prices.csv --price-field adjusted_close --execution-price-field vwap --execution-delay-days 1
```

`execution_price_field` 可选 `close`、`adjusted_close`、`open`、`vwap`；使用 `open` 或 `vwap` 时，行情 CSV 必须提供对应列。持仓估值、收益曲线和因子收益仍使用 `price_field`。

`execution_delay_days = 1` 表示在信号日后一根对齐交易 bar 执行交易，常用于模拟“收盘后生成信号、下一交易日执行”。默认值为 `0`，保持信号日执行的兼容行为。

策略风险闸门阈值也可以配置，不同策略可以使用不同上线/复核标准：

```toml
max_allowed_drawdown = 0.20
max_allowed_daily_var = 0.05
min_allowed_rolling_return = -0.10
min_allowed_fill_rate = 0.70
min_allowed_execution_price_coverage = 1.00
max_allowed_market_constraint_rate = 0.50
max_allowed_position_weight = 0.50
max_allowed_group_weight = 0.60
max_allowed_attribution_residual = 0.05
max_allowed_factor_correlation = 0.90
```

对应的命令行覆盖示例：

```bash
python -m python_quant.main --demo --max-allowed-drawdown 0.15 --max-allowed-daily-var 0.04 --min-allowed-fill-rate 0.85 --min-allowed-execution-price-coverage 0.99 --max-allowed-market-constraint-rate 0.40 --max-allowed-group-weight 0.55 --max-allowed-factor-correlation 0.85
```

如果 CSV 没有维护 `can_buy/can_sell`，可以让程序按涨跌幅自动收紧买卖限制：

```toml
infer_limit_flags = true
limit_up_down_rate = 0.10
st_limit_up_down_rate = 0.05
growth_limit_up_down_rate = 0.20
bse_limit_up_down_rate = 0.30
infer_limit_rate_by_symbol = true
```

推断优先级为：CSV 行级 `limit_rate` > `is_st` 的 ST 阈值 > 按代码识别的创业板/科创板/北交所阈值 > 普通 A 股阈值。常见代码段按 `300/301`、`688/689`、`43/83/87/88/92` 做近似识别；如果你的数据源能直接提供 `limit_rate`，优先使用数据源字段更稳。

涨跌停推断会使用 `execution_price_field` 对应的成交价与上一交易日收盘价比较。比如设置 `execution_price_field = "open"` 时，程序会判断开盘价是否相对前收盘触及涨跌停，从而决定当天开盘是否可买/可卖；默认未设置时沿用 `price_field`。

如果数据源已经提供涨跌停状态，可以直接写 `is_limit_up` 和 `is_limit_down`。程序会用这些显式字段区分 `limit_up_blocked` / `limit_down_blocked` 和普通的 `not_buyable` / `not_sellable`，避免把风控禁买、停牌、数据源不可交易等原因误报成涨跌停。

如果 CSV 提供了 `volume`，可以控制单日最大成交容量：

```toml
max_volume_participation = 0.10
```

表示单日买入或卖出股数最多为该股票成交量的 10%，并继续按 `lot_size` 向下取整。买入容量不足会缩小成交股数；卖出容量不足会部分卖出并保留剩余持仓。

如果希望保留现金缓冲，可以设置：

```toml
target_cash_weight = 0.10
```

表示调仓时只把约 90% 的账户权益作为目标可投资资金。默认值为 `0.0`，保持原始满仓倾向。

如果希望限制新开仓的单票目标权重，可以设置：

```toml
max_position_weight = 0.20
```

表示单只股票的新开仓目标市值不超过调仓前账户权益的 20%。默认值为 `1.0`，保持原始等权 top N 行为。

如果提供了 `symbol_group_csv`，还可以限制每个分组最多入选几只：

```toml
max_group_positions = 1
```

表示每次调仓同一行业/板块/自定义分组最多保留 1 只新目标持仓。已因 T+1 或不可卖规则锁定的持仓会计入分组数量。

可以用日期范围做分阶段回测：

```toml
start_date = "2020-01-01"
end_date = "2024-12-31"
```

如果希望在导出结果中显示“A 股代码 + 中文名”，可以在配置里指定：

```toml
symbol_name_csv = "symbols.csi300.csv"
```

该 CSV 需包含两列，且 `symbol` 使用 6 位 A 股代码：

- `symbol`
- `name`

仓库自带两个可直接改写的模板文件：

- `symbols.example.csv`：常用 A 股代码与中文简称模板
- `symbols.csi300.csv`：沪深300成分股代码与中文简称模板

默认更推荐直接从 `symbols.csi300.csv` 开始，再按你的持仓池继续增删。

如果需要控制策略的可投范围，可以在配置里指定动态股票池：

```toml
stock_pool_csv = "stock_pool.csv"
```

股票池 CSV 需包含两列：

- `date`
- `symbol`

同一个 `date` 可以写多行，表示该生效日的完整可投股票池。回测在调仓时会使用不晚于当前日期的最近一份股票池；新开仓只能来自股票池，已经持有但因 T+1 或不可卖而锁定的旧仓位会继续保留到可卖。

当前版本只支持这 3 个固定因子权重名称：

- `momentum`
- `mean_reversion`
- `low_volatility`

基准 CSV 只读取价格序列本身，实际需要的列为：

- `date`
- `close`
- `adjusted_close`（可选）

代码分组 CSV 用于行业、板块或自定义分组暴露分析，必填列为：

- `symbol`
- `group`

示例：

```csv
symbol,group
000001,银行
600519,消费
300750,新能源
```

如果配置文件包含 `[sweep]`，可以配合 `--sweep` 一次运行多组参数。批量结果默认输出到 `output_dir/batch_runs/`。

也可以执行 walk-forward 滚动窗口验证：

```bash
python -m python_quant.main --demo --walk-forward --walk-window 30 --walk-step 10
```

其中 `--walk-window` 表示每个窗口包含的交易日数量，`--walk-step` 表示每次向前滚动的交易日步长。结果默认输出到 `output_dir/walk_forward/`。

如果希望模拟更严格的“训练选参、测试验证”，可以配合 TOML `[sweep]` 使用：

```bash
python -m python_quant.main --demo --config backtest.example.toml --walk-optimize --walk-train-window 40 --walk-test-window 20 --walk-step 20 --rank-by annualized_return
```

该流程会在每个训练窗口内运行 `[sweep]` 参数网格，按 `--rank-by` 选择最佳参数，再把该参数应用到紧随其后的测试窗口。结果默认输出到 `output_dir/walk_forward_optimization/`。

也可以安装后直接运行：

```bash
myfinances-quant --demo
```

## 测试

```bash
python -m unittest discover -s tests
```

## 开发检查

```bash
python -m pip install -e ".[dev]"
python scripts/dev_check.py
```

`scripts/dev_check.py` 会顺序执行 `ruff`、`mypy`、`unittest` 和一次 demo smoke。smoke 阶段会校验 `run_manifest.json`、`report.html`、风险、因子、停牌、换手和策略健康等关键产物，并逐项检查 manifest 声明的所有 artifact 是否真实存在、非空且带有文件元数据。CI 中默认使用：

```bash
python scripts/dev_check.py --skip-smoke
```

如果本地暂时没有安装 `ruff` 或 `mypy`，可以先运行：

```bash
python scripts/dev_check.py --skip-static
```

完整静态检查需要先安装开发依赖：

```bash
python -m pip install -e .[dev]
```

## 输出

默认输出目录：`output/runs/<timestamp>-<config_hash>/`，避免多次回测互相覆盖。

如果在 TOML 的 `[backtest]` 中配置 `output_dir`，或通过命令行传入 `--output-dir`，则会精确使用指定目录。

- `equity_curve.csv`：日期、权益、单期收益、持仓、基准和超额收益。
- `rebalance_log.csv`：调仓日期、持仓、买入换手、卖出换手、总换手、交易成本。
- `positions.csv`：每日持仓账本，包含代码、股数、价格、市值、权重、现金和总权益。
- `trades.csv`：逐笔交易明细，包含买卖方向、股数、成交价、成交金额、佣金、滑点、印花税、现金变化和交易原因。
- `trade_attempts.csv`：未成交原因，记录因为 T+1、停牌、不可交易、涨停不可买、跌停不可卖、成交量限制、现金不足或不够一手导致的跳过交易。
- `execution_quality.csv` / `execution_quality.json`：执行质量分析，按总体、买卖方向、拒单原因、约束类别和日级阻塞强度汇总成交率、成本 bps、成交股数和平均成交金额；JSON 摘要会标出主要约束类别、停牌/涨跌停/T+1/容量等市场约束拒单占比，以及最严重阻塞交易日、当日拒单数、受阻目标股数和主导约束类别。
- `turnover_analysis.csv` / `turnover_analysis.json`：换手分析，按调仓日记录进入、退出、留存数量和标的列表，并汇总平均进入/退出数量、已实现持仓周期和未平仓数量。
- `holding_periods.csv`：已实现持仓周期明细，按实际买入/卖出交易配对记录每只股票的进入日期、退出日期、股数、价格、持仓天数和退出原因。
- `exposure.csv` / `exposure.json`：持仓暴露分析，按日汇总股票仓位、现金权重、最大单票权重、HHI 集中度、有效持仓数量、最大风险贡献标的和最大风险贡献占比。
- `group_exposure.csv` / `group_exposure.json`：行业/板块/自定义分组暴露分析，按日和分组汇总权重、市值、持仓数量和分组风险贡献占比，并在 JSON 摘要中记录最大分组权重、最大分组风险贡献与未映射权重。
- `return_attribution.csv` / `return_attribution.json`：收益归因分析，按日期和股票记录上一期权重、资产收益和收益贡献，并在 JSON 摘要中汇总个股贡献、分组贡献、残差和成本拖累。
- `cost_attribution.csv` / `cost_attribution.json`：成本归因分析，按日期、股票、分组、买卖方向、交易原因和成本分项记录成本金额与成本 bps，并在 JSON 摘要中汇总分项、方向、原因、个股、分组和每日成本。
- `pnl_ledger.csv` / `pnl_ledger.json`：盈亏对账账本，逐日记录期初权益、期末权益、权益变化、交易现金流、成本、期末现金、期末持仓市值和对账差异。
- `strategy_health.csv` / `strategy_health.json`：策略健康诊断，输出总分、等级、状态、闸门状态、预警数量和分项检查结果，覆盖收益、风险、滚动稳定性、执行质量、集中度、成本、换手、持仓周期、归因和对账。
- `strategy_health_gates.csv`：策略风险闸门，单独列出对账、最大回撤、日 VaR 尾部损失、最差滚动收益、成交率、执行价字段覆盖率、市场约束拒单占比、单票集中度、分组集中度、收益归因残差、换手/持仓周期和因子相关性等上线/复核条件是否通过。
- `factor_scores.csv`：因子评分明细，记录调仓时每只股票的因子值、标准化因子、总分和入选状态。
- `factor_ic.csv` / `factor_ic.json`：基础 IC / Rank IC 分析，基于对齐后的全价格序列衡量因子与下一期收益的关系。
- `factor_group_returns.csv` / `factor_group_returns.json`：因子分组收益分析，基于对齐后的全价格序列展示各分组平均下一期收益、高低组差和单调性。
- `factor_decay.csv` / `factor_decay.json`：因子衰减分析，按相邻调仓期记录分数相关性、排序相关性、入选留存率和入选换手率；JSON 摘要可用于判断 `total_score` 是否稳定、信号是否过快翻转。
- `factor_correlation.csv` / `factor_correlation.json`：因子相关性矩阵，逐调仓日记录因子两两 Pearson 相关和 Rank 相关；JSON 摘要会标出平均相关性最强的因子对，辅助判断信号拥挤和冗余。
- `performance_summary.csv`：核心绩效指标和基准对比。
- `performance_summary.json`：机器可读的绩效摘要，包含样本内/样本外切分表现。
- `drawdown.csv` / `drawdown.json`：逐日回撤序列，包含当前权益、历史峰值、峰值日期、回撤、水下标记、连续水下天数、最长回撤持续期、95% 日 VaR、Expected Shortfall 和最差单日收益；JSON 摘要会标出最终是否已修复回撤。
- `monthly_returns.csv` / `monthly_returns.json`：月度收益表，包含每月起止日期、月度收益和最佳/最差月份摘要。
- `rolling_risk.csv` / `rolling_risk.json`：默认 20 期滚动风险分析，可通过 `rolling_risk_window` 或 `--rolling-risk-window` 调整，包含窗口收益、年化收益、年化波动、滚动夏普、窗口最大回撤、窗口胜率和最差窗口摘要。
- `relative_performance.csv` / `relative_performance.json`：相对基准表现分析，包含主动收益、主动净值、主动回撤、主动胜率、最佳/最差主动日、跟踪误差和信息比率；未提供基准时保留空摘要。
- `run_manifest.json`：本次运行的配置、输入、产物路径和指标快照。
- `equity_curve.svg`：单次回测净值图。
- `report.html`：单次回测网页报告。
- `batch_runs/batch_summary.csv`：批量扫描汇总表。
- `batch_runs/batch_summary.json`：批量扫描汇总 JSON。
- `batch_runs/batch_leaderboard.csv`：按指标排序的批量排行榜。
- `batch_runs/best_run.json`：当前批量结果中的最佳运行。
- `batch_runs/batch_annualized_return.svg`：批量结果对比图。
- `batch_runs/batch_<metric>_heatmap.svg`：双参数 sweep 的热力图。
- `batch_runs/batch_stability.csv/json`：参数稳定性、综合评分、参数敏感度、各参数取值平均表现/通过率、推荐参数档位及推荐依据、健康闸门通过/失败数量、失败闸门类别/名称分布、可行动建议和参数孤岛提示。
- `batch_runs/parameter_sensitivity.csv`：参数敏感度长表，每行对应一个参数取值，包含样本数、平均排序指标、最佳排序指标、平均综合分、闸门通过率、最差回撤、推荐档位标记，以及“排序指标最优 / 综合分最优”标记。
- `batch_runs/batch_report.html`：批量扫描网页报告。
- `walk_forward/walk_forward.csv/json`：walk-forward 滚动窗口验证汇总，包含每个窗口的起止日期、收益、回撤、夏普、胜率和稳定性摘要。
- `walk_forward_optimization/walk_forward_optimization.csv/json`：walk-forward 训练/测试优化汇总，包含每个训练窗口选出的参数、训练表现、测试表现、训练/测试年化差距、测试效率、退化窗口占比、参数漂移、主导参数集、样本外稳定等级和过拟合风险摘要。
- `price_data_quality_report.csv/json`：`--validate-csv` 生成的行情数据质量报告，JSON 摘要会按本次 `execution_price_field` 统计缺失执行价行数和覆盖率。
- `benchmark_quality_report.csv/json`：`--validate-csv --benchmark-csv ...` 生成的基准数据质量报告，检查基准日期是否覆盖行情日期、复权价缺失、异常日收益和最大单日波动。
- `stock_pool_quality_report.csv/json`：`--validate-csv --stock-pool-csv ...` 生成的股票池质量报告，检查空日期、空代码、非法代码、重复日期-代码组合，以及在同时提供行情 CSV 时的缺失/多余股票池标的。
- `symbol_group_quality_report.csv/json`：`--validate-csv --symbol-group-csv ...` 生成的分组映射质量报告，检查缺列、空代码、空分组、重复代码，以及在同时提供行情 CSV 时的缺失/多余映射。
- `factor_score_quality_report.csv/json`：`--validate-csv --factor-score-csv ...` 生成的外部评分质量报告，检查空日期、非法日期、空代码、非法代码、空分数、非法分数、重复日期-代码组合，以及在同时提供行情 CSV 时的评分日期/标的覆盖率。

当前版本的输出风格已经按 A 股中文阅读场景做过收缩：

- CSV 表头默认使用“中文 / 英文代码”顺序，例如 `日期 / date`、`方案编号 / scheme_label`、`内部编号 / run_id`。
- 单次网页报告会展示核心结论、当前持仓、调仓摘要、基准复盘和持仓代码说明。
- 批量网页报告会展示研究结论、最优参数、结果观察、最优结果和中文图表。
- 批量 JSON 会额外提供 `reader_friendly` 摘要块，方便直接读取最佳方案、最弱方案和排序指标。
