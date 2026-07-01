#!/usr/bin/env python3
"""
Build a static, standalone ETF analysis report with live data embedded.
Output: frontend/report.html — open in any browser, no server needed.

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
from data_fetcher import get_index_kline
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

# Write data as JSON
data_json = json.dumps(payload, ensure_ascii=False, indent=2)
data_path = os.path.join(os.path.dirname(__file__), "frontend", "report_data.json")
with open(data_path, "w", encoding="utf-8") as f:
    f.write(data_json)
print(f"\n📦 数据已保存到 {data_path}")

# Read the template HTML
template_path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
with open(template_path, "r", encoding="utf-8") as f:
    html = f.read()

# Inject data into the HTML — replace the API fetch with embedded data
# Strategy: find `document.addEventListener('DOMContentLoaded', () => refreshAll());`
# and replace with embedded data loading

embedded_init = f"""
// ── Embedded Data (static report, no server needed) ──
const EMBEDDED_DATA = {data_json};
let dashboardData = EMBEDDED_DATA;

document.addEventListener('DOMContentLoaded', () => {{
    document.getElementById('refreshBtn').style.display = 'none';
    document.getElementById('lastUpdate').textContent = '静态报告 · ' + EMBEDDED_DATA.timestamp;
    renderAll();
    // If a chart ETF is selected, load it from embedded data
    if (selectedChartETF) {{
        loadChartFromEmbedded(selectedChartETF);
    }}
}});
"""

# Remove the original init and replace with embedded
html = html.replace(
    "document.addEventListener('DOMContentLoaded', () => refreshAll());",
    embedded_init
)

# Replace the API_BASE to point to embedded data (just in case)
html = html.replace(
    "const API = '/api';",
    "const API = '/api'; // not used in static mode"
)

# Add a function to load chart from embedded data
chart_from_embedded = """
async function loadChartFromEmbedded(code) {
    const data = EMBEDDED_DATA.kline_data?.[code];
    if (!data) {
        console.warn('No embedded kline for', code);
        return;
    }
    if (klineChart) klineChart.destroy();

    const dates = data.dates;
    const close = data.close;
    const ma20 = data.ma20;
    const ma60 = data.ma60;
    const colors = close.map((v, i) => i === 0 ? '#888' : v >= close[i-1] ? '#ef4444' : '#22c55e');

    const ctx = document.getElementById('klineChart').getContext('2d');
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
            plugins: { legend: { labels: { color: '#8b8fa3', usePointStyle: true, padding: 20 } } },
            scales: {
                x: { ticks: { color: '#8b8fa3', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: '#2a2d3a33' } },
                y: { position: 'right', ticks: { color: '#8b8fa3', font: { size: 10 }, callback: v => v.toFixed(2) }, grid: { color: '#2a2d3a33' } },
            }
        }
    });
}

// Override selectETF for static mode
const _origSelectETF = selectETF;
selectETF = async function(code) {
    selectedChartETF = code;
    document.querySelectorAll('.etf-chip').forEach(c => c.classList.toggle('active', c.textContent.includes(code)));
    const pool = EMBEDDED_DATA.quotes || [];
    const etf = pool.find(q => q.code === code);
    document.getElementById('chartSubtitle').textContent = etf ? etf.name + ' (' + code + ')' : code;
    await loadChartFromEmbedded(code);
};
"""

html = html.replace(
    "async function selectETF(code) {",
    chart_from_embedded + "\n\nasync function selectETF_old(code) {"
)

# Write the final report
report_path = os.path.join(os.path.dirname(__file__), "frontend", "report.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(report_path) / 1024
print(f"📄 静态报告已生成: {report_path} ({size_kb:.0f} KB)")
print(f"🔗 直接用浏览器打开 file://{report_path} 即可查看！")
