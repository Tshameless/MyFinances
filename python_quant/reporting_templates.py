def get_single_run_html_template() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>回测报告</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; background: #f8fafc; }
    h1, h2 { margin: 0 0 16px; }
    .grid { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 24px; align-items: start; }
    .card { background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 8px 0; border-bottom: 1px solid #eef2f7; }
    th { width: 55%; color: #52606d; font-weight: 600; }
    ul { margin: 0; padding-left: 20px; }
    img { width: 100%; border: 1px solid #d9e2ec; border-radius: 10px; background: white; }
    .muted { color: #52606d; margin-bottom: 16px; }
    .wide { grid-column: 1 / -1; }
    .hero { background: linear-gradient(135deg, #ffffff 0%, #eef6ff 100%); }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-top: 20px; }
    .summary-tile { border: 1px solid #d9e2ec; border-radius: 12px; padding: 14px; background: #fff; }
    .summary-label { color: #52606d; font-size: 12px; margin-bottom: 6px; }
    .summary-value { font-size: 24px; font-weight: 700; color: #102a43; }
    .lead { font-size: 16px; line-height: 1.7; color: #243b53; }
    .compact td, .compact th { font-size: 14px; }
  </style>
</head>
<body>
  <h1>回测报告</h1>
  <p class="muted">生成时间：{generation_time}</p>
  <div class="grid">
    <div class="card wide hero">
      <h2>核心结论</h2>
      <p class="lead">{conclusion}</p>
      <div class="summary-grid">{summary_cards}</div>
    </div>
    <div class="card">
      <h2>{chart_title}</h2>
      <div id="echarts-container" style="width: 100%; height: 400px;"></div>
    </div>
    <div class="card">
      <h2>当前持仓</h2>
      <table>
        <tr><th>持仓概览</th><td>{holdings_summary}</td></tr>
        <tr><th>持仓数量</th><td>{holdings_count}</td></tr>
        <tr><th>平均换手</th><td>{turnover_summary}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>调仓摘要</h2>
      <table>{rebalance_rows}</table>
    </div>
    {benchmark_section}
    <div class="card">
      <h2>指标明细</h2>
      <table>{metrics_rows}</table>
    </div>
    <div class="card">
      <h2>复盘摘要</h2>
      <table class="compact">{review_table_rows}</table>
    </div>
    <div class="card">
      <h2>Trading Behavior Diagnostics</h2>
      <table class="compact">{trading_behavior_table_rows}</table>
    </div>
    <div class="card">
      <h2>Data Quality Diagnostics</h2>
      <table class="compact">{data_quality_table_rows}</table>
    </div>
    <div class="card">
      <h2>配置摘要</h2>
      <table>
{config_rows}
      </table>
      <h2 style="margin-top:20px;">因子权重</h2>
      <table>{factor_rows}</table>
    </div>
    <div class="card">
      <h2>产物清单</h2>
      <ul>{artifact_links}</ul>
    </div>
    <div class="card wide">
      <h2>指标怎么看</h2>
      <table>{explanation_rows}</table>
    </div>
    <div class="card wide">
      <h2>持仓代码说明</h2>
      <table>{holdings_rows}</table>
    </div>
    </div>
  </div>
  {echarts_script_tag}
  {echarts_init_script}
</body>
</html>
"""

def get_echarts_init_script() -> str:
    return """<script>
  (function() {{
    if (typeof echarts !== 'undefined') {{
      var dates = {json_dates};
      var portfolio = {json_portfolio};
      var benchmark = {json_benchmark};
      
      var container = document.getElementById('echarts-container');
      if (container) {{
        var chart = echarts.init(container);
        
        var series = [{{
          name: '策略净值',
          type: 'line',
          data: portfolio,
          showSymbol: false,
          smooth: true,
          lineStyle: {{ width: 2, color: '#1890ff' }},
          itemStyle: {{ color: '#1890ff' }}
        }}];
        
        var legendData = ['策略净值'];
        if (benchmark && benchmark.length > 0) {{
          series.push({{
            name: '基准净值',
            type: 'line',
            data: benchmark,
            showSymbol: false,
            smooth: true,
            lineStyle: {{ width: 1.5, color: '#ff4d4f', type: 'dashed' }},
            itemStyle: {{ color: '#ff4d4f' }}
          }});
          legendData.push('基准净值');
        }}
        
        var option = {{
          tooltip: {{
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#d9e2ec',
            borderWidth: 1,
            textStyle: {{ color: '#1f2933' }},
            formatter: function(params) {{
              var res = '<div style="font-weight:600;margin-bottom:4px;">' + params[0].name + '</div>';
              params.forEach(function(item) {{
                res += '<div style="display:flex;justify-content:space-between;align-items:center;min-width:120px;margin:2px 0;">' +
                       '<span>' + item.marker + ' ' + item.seriesName + ':</span>' +
                       '<span style="font-weight:600;margin-left:8px;">' + Number(item.value).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + '</span>' +
                       '</div>';
              }});
              return res;
            }}
          }},
          legend: {{
            data: legendData,
            bottom: 0,
            textStyle: {{ color: '#52606d' }}
          }},
          grid: {{
            left: '3%',
            right: '4%',
            top: '5%',
            bottom: '12%',
            containLabel: true
          }},
          xAxis: {{
            type: 'category',
            boundaryGap: false,
            data: dates,
            axisLine: {{ lineStyle: {{ color: '#d9e2ec' }} }},
            axisLabel: {{ color: '#52606d' }}
          }},
          yAxis: {{
            type: 'value',
            scale: true,
            axisLine: {{ show: false }},
            axisTick: {{ show: false }},
            splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }},
            axisLabel: {{ color: '#52606d' }}
          }},
          series: series
        }};
        
        chart.setOption(option);
        window.addEventListener('resize', function() {{
          chart.resize();
        }});
      }}
    }}
  }})();
  </script>"""
