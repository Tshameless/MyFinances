# A股量化回测工具

这是一个面向 A 股研究场景的日频多因子回测工具，适合用标准 CSV 做策略研究、参数试验和中文报告导出。

## 功能

- 支持内置演示数据和本地 CSV 行情数据。
- 对 A 股 CSV 做日期解析、重复行检查、价格校验和可交易标记解析。
- 使用交集交易日对齐所有标的，避免按数组下标错位回测。
- 支持收盘价或复权价回测、基准比较、买卖受限持仓处理。
- 支持等权选股、固定周期调仓、基于换手的交易成本扣减。
- 支持 TOML 配置文件、因子权重覆盖、卖出印花税建模。
- 支持通过 `symbol_name_csv` 给 A 股代码补充中文名映射，提升表格、图表和网页报告可读性。
- 输出净值曲线 CSV、调仓日志 CSV、绩效摘要 CSV 和绩效摘要 JSON。
- 自动写出 `run_manifest.json`，记录本次配置、输入和产物路径。
- 支持基于 TOML `sweep` 配置的批量参数扫描与结果汇总。
- 自动输出中文化 SVG 图表和批量排行榜，减少手工读表。
- 支持 `--rank-by` 自定义批量排序指标；双参数 sweep 会自动输出热力图。
- 单次和批量运行都会生成网页报告（HTML），方便直接浏览结果。
- 内置 `unittest` 回归测试。

## CSV 格式

必填列：

- `date`
- `symbol`
- `close`

可选列：

- `adjusted_close`
- `volume`
- `tradable`
- `can_buy`
- `can_sell`

`symbol` 必须使用 6 位 A 股代码，例如 `600519`、`000001`。

日期支持 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD`。

## 运行示例

```bash
python -m python_quant.main --demo
python -m python_quant.main --csv data/sample_prices.csv --top-n 5 --rebalance-days 10
python -m python_quant.main --csv data/sample_prices.csv --benchmark-csv data/benchmark.csv --price-field adjusted_close
python -m python_quant.main --config backtest.example.toml --csv data/sample_prices.csv
python -m python_quant.main --config backtest.example.toml --demo --sweep
python -m python_quant.main --config backtest.example.toml --demo --sweep --rank-by sharpe
```

## 配置文件

可以使用 TOML 配置文件集中管理参数，再用命令行覆盖局部值。

示例见：`backtest.example.toml`

当前版本要求把回测参数放在 `[backtest]` 配置段中，不再兼容顶层同名参数直写。

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

当前版本只支持这 3 个固定因子权重名称：

- `momentum`
- `mean_reversion`
- `low_volatility`

基准 CSV 只读取价格序列本身，实际需要的列为：

- `date`
- `close`
- `adjusted_close`（可选）

如果配置文件包含 `[sweep]`，可以配合 `--sweep` 一次运行多组参数。批量结果默认输出到 `output_dir/batch_runs/`。

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
python -m ruff check .
python -m mypy python_quant
python -m unittest discover -s tests
```

## 输出

默认输出目录：`output/python`

- `equity_curve.csv`：日期、权益、单期收益、持仓、基准和超额收益。
- `rebalance_log.csv`：调仓日期、持仓、买入换手、卖出换手、总换手、交易成本。
- `performance_summary.csv`：核心绩效指标和基准对比。
- `performance_summary.json`：机器可读的绩效摘要。
- `run_manifest.json`：本次运行的配置、输入、产物路径和指标快照。
- `equity_curve.svg`：单次回测净值图。
- `report.html`：单次回测网页报告。
- `batch_runs/batch_summary.csv`：批量扫描汇总表。
- `batch_runs/batch_summary.json`：批量扫描汇总 JSON。
- `batch_runs/batch_leaderboard.csv`：按指标排序的批量排行榜。
- `batch_runs/best_run.json`：当前批量结果中的最佳运行。
- `batch_runs/batch_annualized_return.svg`：批量结果对比图。
- `batch_runs/batch_<metric>_heatmap.svg`：双参数 sweep 的热力图。
- `batch_runs/batch_report.html`：批量扫描网页报告。

当前版本的输出风格已经按 A 股中文阅读场景做过收缩：

- CSV 表头默认使用“中文 / 英文代码”顺序，例如 `日期 / date`、`方案编号 / scheme_label`、`内部编号 / run_id`。
- 单次网页报告会展示核心结论、当前持仓、调仓摘要、基准复盘和持仓代码说明。
- 批量网页报告会展示研究结论、最优参数、结果观察、最优结果和中文图表。
- 批量 JSON 会额外提供 `reader_friendly` 摘要块，方便直接读取最佳方案、最弱方案和排序指标。
