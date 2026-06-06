# MyFinances Python Quant

`MyFinances` 目前提供一个可本地运行的日频多因子回测工具，适合用标准 CSV 做策略研究、参数试验和结果导出。

## 功能

- 支持内置演示数据和本地 CSV 行情数据。
- 对 CSV 做日期解析、重复行检查、价格校验和可交易标记解析。
- 使用交集交易日对齐所有标的，避免按数组下标错位回测。
- 支持复权价回测、基准比较、买卖受限持仓处理。
- 支持等权选股、固定周期调仓、基于换手的交易成本扣减。
- 输出净值曲线 CSV、调仓日志 CSV 和绩效摘要 CSV。
- 内置 `unittest` 回归测试。

## CSV 格式

必填列：

- `date`
- `symbol`
- `close`

可选列：

- `adjusted_close` 或 `adj_close`
- `volume`
- `tradable`
- `can_buy` 或 `buyable`
- `can_sell` 或 `sellable`

日期支持 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYYMMDD`。

## 运行示例

```bash
python -m python_quant.main --demo
python -m python_quant.main --csv data/sample_prices.csv --top-n 5 --rebalance-days 10
python -m python_quant.main --csv data/sample_prices.csv --benchmark-csv data/benchmark.csv --price-field adjusted_close
```

也可以安装后直接运行：

```bash
myfinances-quant --demo
```

## 测试

```bash
python -m unittest discover -s tests
```

## 输出

默认输出目录：`output/python`

- `equity_curve.csv`：日期、权益、单期收益、持仓、基准和超额收益。
- `rebalance_log.csv`：调仓日期、持仓、换手率、交易成本。
- `performance_summary.csv`：核心绩效指标和基准对比。
