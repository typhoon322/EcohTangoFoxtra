#!/usr/bin/env python3
"""
Build a static, standalone ETF analysis report with live data embedded.
Output: docs/index.html — for GitHub Pages, open in any browser, no server needed.

Usage: python build_report.py
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

print("🔄 正在拉取 ETF 实时行情...")
from data_fetcher import get_all_etf_quotes, get_etf_ma, get_index_kline, ETF_POOL, _sina_code
quotes = get_all_etf_quotes()
print(f"   ✅ {len(quotes)} 只 ETF 行情数据")

print("🔄 正在计算动量轮动信号...")
from signals import get_rotation_ranking
rotation = get_rotation_ranking(top_n=15)
print(f"   ✅ {len(rotation)} 只 ETF 动量排名")

print("🔄 正在计算均线趋势信号...")
from signals import scan_all_etf_signals
ma_signals = scan_all_etf_signals()
print(f"   ✅ {len(ma_signals)} 条均线信号")

print("🔄 正在计算定投增强信号...")
from signals import scan_all_dca_signals
dca_signals = scan_all_dca_signals(amount=5000)
print(f"   ✅ {len(dca_signals)} 条定投信号")

print("🔄 正在获取市场状态...")
market_state = get_index_kline("000300", 200)
print(f"   ✅ 市场状态: {market_state['state_cn'] if market_state else 'N/A'}")

# Build a lookup from code -> full ETF dict
etf_map = {e["code"]: e for e in ETF_POOL}

# Collect K-line data for chart (top 5 momentum)
print("🔄 正在拉取 Top 5 ETF K线数据...")
kline_data = {}
for r in rotation[:5]:
    code = r["code"]
    etf_info = etf_map.get(code, {"code": code})
    sina = _sina_code(etf_info)
    ma = get_etf_ma(sina, "daily", 200)
    if ma:
        kline_data[code] = {
            "name": r["name"],
            "dates": ma["dates"],
            "close": ma["close"],
            "ma20": ma["ma20"],
            "ma60": ma["ma60"],
        }
        print(f"   ✅ {code} ({sina}) {r['name']}: {len(ma['dates'])} 天")
    else:
        print(f"   ⚠️ {code} ({sina}) {r['name']}: 无K线数据")

# Build the data payload
from datetime import datetime
payload = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_state": market_state,
    "quotes": quotes,
    "rotation": rotation,
    "ma_signals": ma_signals,
    "dca_signals": dca_signals,
    "kline_data": kline_data,
}
data_json = json.dumps(payload, ensure_ascii=False)

# ── Build the static HTML ──

html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 智投分析面板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #0f1117;
  --surface: #1a1d28;
  --surface2: #212433;
  --border: #2a2d3a;
  --text: #e1e4ed;
  --text2: #8b8fa3;
  --red: #ef4444;
  --green: #22c55e;
  --blue: #3b82f6;
  --yellow: #f59e0b;
  --purple: #a855f7;
  --cyan: #06b6d4;
  --radius: 10px;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.5;
}
.app-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex; align-items: center; justify-content: space-between;
  position: sticky; top: 0; z-index: 100;
}
.app-header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.header-right { display: flex; align-items: center; gap: 16px; }
.market-badge {
  padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;
}
.market-badge.bull { background: rgba(239,68,68,.15); color: var(--red); }
.market-badge.bear { background: rgba(34,197,94,.15); color: var(--green); }
.market-badge.range { background: rgba(245,158,11,.15); color: var(--yellow); }
.last-update { font-size: 12px; color: var(--text2); }
.refresh-btn {
  background: var(--blue); color: #fff; border: none;
  padding: 6px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;
  transition: opacity .2s;
}
.refresh-btn:hover { opacity: .85; }
.main-content { max-width: 1400px; margin: 0 auto; padding: 24px; }
.tabs { display: flex; gap: 4px; margin-bottom: 24px; background: var(--surface); border-radius: var(--radius); padding: 4px; }
.tab-btn {
  flex: 1; padding: 10px 20px; border: none; background: transparent;
  color: var(--text2); font-size: 14px; font-weight: 600; cursor: pointer;
  border-radius: 8px; transition: all .2s;
}
.tab-btn.active { background: var(--surface2); color: var(--text); }
.tab-btn:hover:not(.active) { color: var(--text); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 20px;
}
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}
.card-title { font-size: 16px; font-weight: 700; }
.card-subtitle { font-size: 12px; color: var(--text2); margin-top: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--text2); font-weight: 600; font-size: 12px; border-bottom: 1px solid var(--border); }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
tr:hover td { background: rgba(255,255,255,.02); }
.price-up { color: var(--red); }
.price-down { color: var(--green); }
.price-neutral { color: var(--text2); }
.badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 700;
}
.badge-buy { background: rgba(239,68,68,.15); color: var(--red); }
.badge-sell { background: rgba(34,197,94,.15); color: var(--green); }
.badge-hold { background: rgba(59,130,246,.15); color: var(--blue); }
.badge-watch { background: rgba(245,158,11,.15); color: var(--yellow); }
.badge-wait { background: rgba(139,143,163,.15); color: var(--text2); }
.momentum-bar {
  height: 6px; background: var(--surface2); border-radius: 3px; overflow: hidden; min-width: 60px;
}
.momentum-fill { height: 100%; border-radius: 3px; transition: width .5s; }
.momentum-fill.positive { background: linear-gradient(90deg, var(--red), var(--red)); }
.momentum-fill.negative { background: linear-gradient(90deg, var(--green), var(--green)); }
.chart-wrapper { position: relative; width: 100%; height: 400px; }
.etf-selector { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.etf-chip {
  padding: 4px 12px; border-radius: 16px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text2); cursor: pointer;
  font-size: 12px; font-weight: 500; transition: all .2s;
}
.etf-chip:hover { border-color: var(--text2); color: var(--text); }
.etf-chip.active { border-color: var(--blue); color: var(--blue); background: rgba(59,130,246,.1); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
.stat-value { font-size: 28px; font-weight: 800; letter-spacing: -1px; }
.stat-label { font-size: 12px; color: var(--text2); margin-top: 4px; }
.loading {
  text-align: center; padding: 40px; color: var(--text2);
}
.spinner {
  width: 32px; height: 32px; border: 3px solid var(--border);
  border-top-color: var(--blue); border-radius: 50%; animation: spin .8s linear infinite;
  margin: 0 auto 12px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.disclaimer {
  text-align: center; padding: 24px; color: var(--text2); font-size: 11px;
  border-top: 1px solid var(--border); margin-top: 40px; max-width: 1400px;
  margin-left: auto; margin-right: auto;
}
@media (max-width: 900px) {
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  .main-content { padding: 12px; }
  .app-header { flex-wrap: wrap; gap: 8px; }
  .app-header h1 { font-size: 16px; }
  .header-right { flex-wrap: wrap; gap: 8px; }
  table { font-size: 11px; }
  th, td { padding: 6px 8px; }
  .chart-wrapper { height: 300px; }
}
</style>
</head>
<body>

<header class="app-header">
  <h1>ETF 智投分析面板</h1>
  <div class="header-right">
    <span id="marketBadge" class="market-badge">—</span>
    <span class="last-update" id="lastUpdate"></span>
  </div>
</header>

<div class="main-content">

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('overview')">概览</button>
    <button class="tab-btn" onclick="switchTab('rotation')">动量轮动</button>
    <button class="tab-btn" onclick="switchTab('trend')">均线趋势</button>
    <button class="tab-btn" onclick="switchTab('dca')">定投增强</button>
    <button class="tab-btn" onclick="switchTab('chart')">K线图表</button>
  </div>

  <div id="panel-overview" class="tab-panel active">
    <div class="grid-3" id="overviewStats"></div>
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">ETF 实时行情</div>
          <div class="card-subtitle">共 15 只 ETF · 免费数据源 (AKShare + Sina)</div>
        </div>
      </div>
      <div style="overflow-x:auto" id="quotesTable"></div>
    </div>
  </div>

  <div id="panel-rotation" class="tab-panel">
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">ETF 动量轮动排名</div>
          <div class="card-subtitle">3个月 + 6个月收益率各 50% 权重 · 全市场排名</div>
        </div>
      </div>
      <div style="overflow-x:auto" id="rotationTable"></div>
    </div>
  </div>

  <div id="panel-trend" class="tab-panel">
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">双均线趋势信号</div>
          <div class="card-subtitle">MA20 vs MA60 交叉判断 · 金叉买入 / 死叉卖出 / 持有 / 观望</div>
        </div>
      </div>
      <div style="overflow-x:auto" id="trendTable"></div>
    </div>
  </div>

  <div id="panel-dca" class="tab-panel">
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">定投增强建议</div>
          <div class="card-subtitle">基于价格 vs MA60 动态调整定投金额 · 默认 ¥5,000/次</div>
        </div>
      </div>
      <div style="overflow-x:auto" id="dcaTable"></div>
    </div>
  </div>

  <div id="panel-chart" class="tab-panel">
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">K线走势 & 均线</div>
          <div class="card-subtitle" id="chartSubtitle">选择 ETF 查看走势</div>
        </div>
      </div>
      <div class="etf-selector" id="etfChips"></div>
      <div class="chart-wrapper"><canvas id="klineChart"></canvas></div>
    </div>
  </div>

</div>

<div class="disclaimer">
  <strong>⚠️ 免责声明：</strong>本页面仅展示客观量化信号（动量得分、均线交叉、定投增强），不构成任何投资建议。
  数据来源：AKShare（实时行情）+ Sina 财经（K线历史），均为免费公开数据。
  投资有风险，入市需谨慎。历史信号不代表未来表现。
</div>

<script>
// ── Embedded Data ──
const EMBEDDED_DATA = """ + data_json + """;

(function() {
  'use strict';

  let klineChart = null;
  let selectedChartETF = null;

  // ── Init ──
  document.getElementById('lastUpdate').textContent = EMBEDDED_DATA.timestamp;
  renderAll();

  // ── Render ──
  function renderAll() {
    renderMarketState();
    renderOverviewStats();
    renderQuotesTable();
    renderRotation();
    renderTrend();
    renderDCA();
    renderChartSelector();
  }

  function renderMarketState() {
    const badge = document.getElementById('marketBadge');
    const ms = EMBEDDED_DATA.market_state;
    if (!ms) { badge.textContent = '—'; badge.className = 'market-badge'; return; }
    badge.textContent = ms.state_cn + ' ' + (ms.diff_pct >= 0 ? '+' : '') + ms.diff_pct + '%';
    badge.className = 'market-badge ' + ms.state;
  }

  function renderOverviewStats() {
    const quotes = EMBEDDED_DATA.quotes || [];
    const up = quotes.filter(function(q) { return q.change_pct > 0; }).length;
    const down = quotes.filter(function(q) { return q.change_pct < 0; }).length;

    const maSigs = EMBEDDED_DATA.ma_signals || [];
    const buySigs = maSigs.filter(function(s) { return s.direction === 'buy'; }).length;
    const sellSigs = maSigs.filter(function(s) { return s.direction === 'sell'; }).length;

    const ms = EMBEDDED_DATA.market_state;
    const marketStateCn = ms ? ms.state_cn : '—';

    document.getElementById('overviewStats').innerHTML =
      '<div class="card"><div class="stat-value" style="color:var(--red)">' + up + '</div><div class="stat-label">上涨 ETF 数</div></div>' +
      '<div class="card"><div class="stat-value" style="color:var(--green)">' + down + '</div><div class="stat-label">下跌 ETF 数</div></div>' +
      '<div class="card"><div class="stat-value">' + marketStateCn + '</div><div class="stat-label">市场状态（沪深300）</div></div>' +
      '<div class="card"><div class="stat-value" style="color:var(--red)">' + buySigs + '</div><div class="stat-label">金叉买入信号</div></div>' +
      '<div class="card"><div class="stat-value" style="color:var(--green)">' + sellSigs + '</div><div class="stat-label">死叉卖出信号</div></div>' +
      '<div class="card"><div class="stat-value">' + (EMBEDDED_DATA.rotation ? EMBEDDED_DATA.rotation.length : 0) + '</div><div class="stat-label">动量轮动 ETF</div></div>';
  }

  function renderQuotesTable() {
    var quotes = EMBEDDED_DATA.quotes || [];
    if (!quotes.length) { document.getElementById('quotesTable').innerHTML = '<div class="loading">暂无行情数据</div>'; return; }
    var rows = quotes.map(function(q, i) {
      var changeClass = q.change_pct > 0 ? 'price-up' : (q.change_pct < 0 ? 'price-down' : 'price-neutral');
      var changeSign = q.change_pct > 0 ? '+' : '';
      return '<tr><td>' + (i+1) + '</td><td>' + q.code + '</td><td><strong>' + q.name + '</strong></td><td>' + (q.price ? q.price.toFixed(3) : '—') + '</td><td class="' + changeClass + '">' + changeSign + (q.change_pct ? q.change_pct.toFixed(2) : '—') + '%</td><td>' + (q.high ? q.high.toFixed(3) : '—') + '</td><td>' + (q.low ? q.low.toFixed(3) : '—') + '</td><td>' + fmtVolume(q.volume) + '</td><td>' + fmtAmount(q.amount) + '</td></tr>';
    }).join('');
    document.getElementById('quotesTable').innerHTML = '<table><thead><tr><th>#</th><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>最高</th><th>最低</th><th>成交量</th><th>成交额</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderRotation() {
    var ranking = EMBEDDED_DATA.rotation || [];
    if (!ranking.length) { document.getElementById('rotationTable').innerHTML = '<div class="loading">暂无动量数据</div>'; return; }
    var maxScore = Math.max.apply(null, ranking.map(function(r) { return Math.abs(r.momentum_score); })) || 1;
    var rows = ranking.map(function(r, i) {
      var barWidth = Math.min(Math.abs(r.momentum_score) / maxScore * 100, 100);
      var barClass = r.momentum_score >= 0 ? 'positive' : 'negative';
      var color = r.momentum_score >= 0 ? 'var(--red)' : 'var(--green)';
      var sign = r.momentum_score >= 0 ? '+' : '';
      return '<tr><td><strong>#' + (i+1) + '</strong></td><td>' + r.code + '</td><td><strong>' + r.name + '</strong></td><td style="color:var(--text2)">' + r.category + '</td><td class="' + (r.momentum_score >= 0 ? 'price-up' : 'price-down') + '">' + sign + r.momentum_score + '%</td><td>' + fmtPct(r.ret_1m) + '</td><td>' + fmtPct(r.ret_3m) + '</td><td>' + fmtPct(r.ret_6m) + '</td><td><div class="momentum-bar"><div class="momentum-fill ' + barClass + '" style="width:' + barWidth + '%;background:' + color + '"></div></div></td></tr>';
    }).join('');
    document.getElementById('rotationTable').innerHTML = '<table><thead><tr><th>排名</th><th>代码</th><th>名称</th><th>类别</th><th>动量得分</th><th>1月收益</th><th>3月收益</th><th>6月收益</th><th>动量条</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderTrend() {
    var signals = EMBEDDED_DATA.ma_signals || [];
    if (!signals.length) { document.getElementById('trendTable').innerHTML = '<div class="loading">暂无均线数据</div>'; return; }
    var order = { buy: 0, hold: 1, watch: 2, wait: 3, sell: 4 };
    signals.sort(function(a, b) { return (order[a.direction] || 5) - (order[b.direction] || 5); });
    var rows = signals.map(function(s) {
      var badgeClass = 'badge-' + s.direction;
      var maColor = s.ma_diff_pct > 0 ? 'var(--red)' : 'var(--green)';
      var maSign = s.ma_diff_pct > 0 ? '+' : '';
      return '<tr><td>' + s.code + '</td><td><strong>' + s.name + '</strong></td><td style="color:var(--text2)">' + s.category + '</td><td>' + s.price + '</td><td>' + s.ma20 + '</td><td>' + s.ma60 + '</td><td style="color:' + maColor + '">' + maSign + s.ma_diff_pct + '%</td><td>' + (s.vol_ratio ? s.vol_ratio.toFixed(1) : '—') + 'x</td><td><span class="badge ' + badgeClass + '">' + s.signal_cn + '</span></td></tr>';
    }).join('');
    document.getElementById('trendTable').innerHTML = '<table><thead><tr><th>代码</th><th>名称</th><th>类别</th><th>价格</th><th>MA20</th><th>MA60</th><th>差值</th><th>量比</th><th>信号</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderDCA() {
    var signals = EMBEDDED_DATA.dca_signals || [];
    if (!signals.length) { document.getElementById('dcaTable').innerHTML = '<div class="loading">暂无定投数据</div>'; return; }
    var rows = signals.map(function(s) {
      var color = s.action === 'double_down' ? 'var(--red)' : (s.action === 'skip' ? 'var(--green)' : (s.action === 'reduce' ? 'var(--yellow)' : 'var(--text)'));
      return '<tr><td>' + s.code + '</td><td><strong>' + s.name + '</strong></td><td>' + s.price + '</td><td>' + s.ma60 + '</td><td>' + (s.ratio * 100).toFixed(1) + '%</td><td style="color:' + color + ';font-weight:700">' + s.action_cn + '</td><td>' + s.multiplier + 'x</td><td style="font-weight:700">¥' + s.invest_amount.toFixed(0) + '</td></tr>';
    }).join('');
    document.getElementById('dcaTable').innerHTML = '<table><thead><tr><th>代码</th><th>名称</th><th>价格</th><th>MA60</th><th>比率</th><th>操作</th><th>倍率</th><th>定投金额</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // ── Chart ──
  function renderChartSelector() {
    var pool = EMBEDDED_DATA.quotes || [];
    var chips = pool.map(function(q) {
      var active = selectedChartETF === q.code ? ' active' : '';
      return '<button class="etf-chip' + active + '" data-code="' + q.code + '">' + q.name + ' (' + q.code + ')</button>';
    }).join('');
    document.getElementById('etfChips').innerHTML = chips;
    // Attach click handlers
    document.querySelectorAll('.etf-chip').forEach(function(chip) {
      chip.addEventListener('click', function() {
        selectETF(this.getAttribute('data-code'));
      });
    });
  }

  function selectETF(code) {
    selectedChartETF = code;
    document.querySelectorAll('.etf-chip').forEach(function(c) {
      c.classList.toggle('active', c.getAttribute('data-code') === code);
    });
    var pool = EMBEDDED_DATA.quotes || [];
    var etf = pool.find(function(q) { return q.code === code; });
    document.getElementById('chartSubtitle').textContent = etf ? etf.name + ' (' + code + ')' : code;
    loadChart(code);
  }

  function loadChart(code) {
    var data = EMBEDDED_DATA.kline_data && EMBEDDED_DATA.kline_data[code];
    if (!data) {
      console.warn('No kline data for ' + code);
      return;
    }
    if (klineChart) klineChart.destroy();

    var dates = data.dates;
    var close = data.close;
    var ma20 = data.ma20;
    var ma60 = data.ma60;

    var ctx = document.getElementById('klineChart').getContext('2d');
    klineChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          { label: '收盘价', data: close, borderColor: '#e1e4ed', borderWidth: 1.5, pointRadius: 0, tension: 0, yAxisID: 'y' },
          { label: 'MA20', data: ma20, borderColor: '#f59e0b', borderWidth: 1.2, pointRadius: 0, tension: 0, yAxisID: 'y' },
          { label: 'MA60', data: ma60, borderColor: '#a855f7', borderWidth: 1.2, pointRadius: 0, tension: 0, yAxisID: 'y' },
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { labels: { color: '#8b8fa3', usePointStyle: true, padding: 20 } },
          tooltip: { backgroundColor: '#1a1d28', titleColor: '#e1e4ed', bodyColor: '#8b8fa3', borderColor: '#2a2d3a', borderWidth: 1 }
        },
        scales: {
          x: { ticks: { color: '#8b8fa3', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: '#2a2d3a33' } },
          y: { position: 'right', ticks: { color: '#8b8fa3', font: { size: 10 }, callback: function(v) { return v.toFixed(2); } }, grid: { color: '#2a2d3a33' } }
        }
      }
    });
  }

  // ── Tabs ──
  function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('panel-' + name).classList.add('active');
    // Highlight the matching tab button
    var btns = document.querySelectorAll('.tab-btn');
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.includes(name === 'overview' ? '概览' : name === 'rotation' ? '轮动' : name === 'trend' ? '趋势' : name === 'dca' ? '定投' : 'K线')) {
        btns[i].classList.add('active');
        break;
      }
    }
    if (name === 'chart' && !selectedChartETF) {
      var quotes = EMBEDDED_DATA.quotes || [];
      if (quotes.length) selectETF(quotes[0].code);
    }
  }

  // ── Helpers ──
  function fmtVolume(v) {
    if (!v) return '—';
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(1) + '万';
    return v.toFixed(0);
  }
  function fmtAmount(a) {
    if (!a) return '—';
    if (a >= 1e8) return (a / 1e8).toFixed(2) + '亿';
    if (a >= 1e4) return (a / 1e4).toFixed(1) + '万';
    return a.toFixed(0);
  }
  function fmtPct(v) {
    if (v == null) return '—';
    return (v >= 0 ? '+' : '') + v + '%';
  }

  // ── Expose to DOM ──
  window.switchTab = switchTab;

  // Auto-select first ETF in chart tab on first switch to chart tab
  (function() {
    var origSwitchTab = switchTab;
    switchTab = function(name) {
      origSwitchTab(name);
    };
  })();

})();
</script>
</body>
</html>"""

# Write to docs/ for GitHub Pages
docs_dir = os.path.join(os.path.dirname(__file__), "docs")
os.makedirs(docs_dir, exist_ok=True)
report_path = os.path.join(docs_dir, "index.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(report_path) / 1024
print(f"\n📄 报告已生成: {report_path} ({size_kb:.0f} KB)")
print(f"🔗 GitHub Pages: https://typhoon322.github.io/EcohTangoFoxtra/")
print(f"📱 用手机浏览器打开上面的链接即可查看")
