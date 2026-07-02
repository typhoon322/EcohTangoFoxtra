#!/usr/bin/env python3
"""
Static HTML report generator for EcohTangoFoxtra v2.
Can be called standalone or via run_pipeline.py --report.

Usage:
  python build_report.py          # standalone (runs pipeline internally)
  # or imported from run_pipeline.py
"""

import sys, os, json
from datetime import datetime


def build_report_from_data(
    regime: dict,
    ranked: list,
    sector_signals: list,
    portfolio: dict,
    paper_snapshot: dict = None,
) -> str:
    """
    Generate static HTML report from already-computed pipeline data.
    Called by main_lite.py --report to avoid re-fetching data.
    Returns the file path.
    """
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "ranked": ranked[:15],
        "sector_signals": sector_signals,
        "portfolio": {k: v for k, v in portfolio.items() if k != "actions"},
        "paper_snapshot": paper_snapshot,
    }
    return _generate_html(data)


def generate_v2_html(regime, ranked, rotation_signals, portfolio, macro, advice) -> str:
    """
    Generate a rich standalone HTML report with all v2 pipeline data.
    Returns the path to the generated file.
    """
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "ranked": ranked[:15],
        "rotation_signals": rotation_signals,
        "portfolio": {k: v for k, v in portfolio.items() if k != "actions"},
        "macro": macro,
        "advice": advice,
    }
    data_json = json.dumps(data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 决策面板 v2</title>
<style>
:root {{
  --bg: #0f1117; --surface: #1a1d28; --surface2: #212433; --border: #2a2d3a;
  --text: #e1e4ed; --text2: #8b8fa3; --red: #ef4444; --green: #22c55e;
  --blue: #3b82f6; --yellow: #f59e0b; --purple: #a855f7; --radius: 10px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; line-height:1.5; }}
.header {{ background:var(--surface); border-bottom:1px solid var(--border); padding:16px 24px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:100; }}
.header h1 {{ font-size:20px; font-weight:700; }}
.header .sub {{ font-size:12px; color:var(--text2); }}
.container {{ max-width:1200px; margin:0 auto; padding:24px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:20px; margin-bottom:20px; }}
.card-title {{ font-size:16px; font-weight:700; margin-bottom:12px; }}
.regime-card {{ border-left:4px solid var(--regimeColor,#f59e0b); }}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
.grid-3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 12px; color:var(--text2); font-weight:600; font-size:12px; border-bottom:1px solid var(--border); }}
td {{ padding:8px 12px; border-bottom:1px solid var(--border); }}
tr:hover td {{ background:rgba(255,255,255,.02); }}
.badge {{ display:inline-block; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:700; }}
.badge-buy {{ background:rgba(239,68,68,.15); color:var(--red); }}
.badge-hold {{ background:rgba(59,130,246,.15); color:var(--blue); }}
.badge-reduce {{ background:rgba(34,197,94,.15); color:var(--green); }}
.stat {{ text-align:center; }}
.stat-value {{ font-size:28px; font-weight:800; }}
.stat-label {{ font-size:11px; color:var(--text2); margin-top:4px; }}
.score-bar {{ height:8px; background:var(--surface2); border-radius:4px; overflow:hidden; }}
.score-fill {{ height:100%; border-radius:4px; }}
.advice-item {{ padding:8px 16px; margin:4px 0; border-radius:8px; background:var(--surface2); font-size:13px; }}
.rotation-up {{ color:var(--red); }}
.rotation-down {{ color:var(--green); }}
.rotation-flat {{ color:var(--text2); }}
.disclaimer {{ text-align:center; padding:24px; color:var(--text2); font-size:11px; border-top:1px solid var(--border); margin-top:40px; }}
@media (max-width:900px) {{ .grid-2,.grid-3 {{ grid-template-columns:1fr; }} .container {{ padding:12px; }} }}
</style>
</head>
<body>
<div class="header">
  <div><h1>📊 ETF 决策面板 v2</h1><div class="sub" id="timestamp">{data['timestamp']}</div></div>
</div>
<div class="container" id="app"></div>
<div class="disclaimer">
  <strong>⚠️ 免责声明：</strong>本页面基于量化模型自动生成（数据来源：AKShare + Sina），所有信号仅供参考，不构成投资建议。投资有风险，入市需谨慎。
</div>

<script>
const D = {data_json};

(function() {{
  "use strict";

  // Colors
  function trendColor(s) {{ return s >= 65 ? '#22c55e' : s >= 40 ? '#f59e0b' : '#ef4444'; }}
  function riskColor(s) {{ return s <= 30 ? '#22c55e' : s <= 60 ? '#f59e0b' : '#ef4444'; }}
  function scoreColor(s) {{ return s >= 50 ? '#ef4444' : s >= 30 ? '#f59e0b' : '#22c55e'; }}
  function scoreWidth(s) {{ return Math.min(Math.abs(s), 100); }}

  const regimeColor = {{bull:'#22c55e',rotation:'#f59e0b',bear:'#ef4444'}};
  const regimeEmoji = {{bull:'🟢',rotation:'🟡',bear:'🔴'}};
  const regimeCn = {{bull:'主升',rotation:'震荡轮动',bear:'风险调整'}};
  const appetiteCn = {{high:'积极',neutral:'中性偏谨慎',low:'防御'}};

  let html = '';

  // ── Market State ──
  html += '<div class="card regime-card" style="border-left-color:' + (regimeColor[D.regime.regime] || '#f59e0b') + '">';
  html += '<div class="card-title">🧭 市场状态：' + (regimeEmoji[D.regime.regime]||'') + ' ' + (regimeCn[D.regime.regime]||'') + '</div>';
  html += '<div class="grid-3">';
  html += statCard('置信度', D.regime.confidence + '%', 'var(--yellow)');
  html += statCard('趋势均值', D.regime.avg_trend + '分', 'var(--text)');
  html += statCard('离散度', D.regime.std_trend + '', 'var(--text2)');
  html += statCard('权益仓位', (D.regime.equity_allocation*100).toFixed(0) + '%', 'var(--red)');
  html += statCard('风险偏好', appetiteCn[D.regime.risk_appetite]||'中性', 'var(--yellow)');
  html += statCard('沪深300', D.macro.price + '', 'var(--blue)');
  html += '</div>';
  if (D.regime.leading_groups && D.regime.leading_groups.length) {{
    html += '<div style="margin-top:12px;font-size:13px;color:var(--text2)">📈 主线: ' + D.regime.leading_groups.map(g => g).join(' + ') + '</div>';
  }}
  html += '</div>';

  // ── Rotation Signals ──
  html += '<div class="card"><div class="card-title">🔥 行业轮动信号</div>';
  html += '<div class="grid-2">';
  D.rotation_signals.forEach(function(s) {{
    var cls = s.direction === 'up' ? 'rotation-up' : (s.direction === 'down' ? 'rotation-down' : 'rotation-flat');
    html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">';
    html += '<span>' + s.name + '</span>';
    html += '<span style="font-weight:600" class="' + cls + '">' + s.signal + ' (' + s.avg_score + '分)</span>';
    html += '</div>';
  }});
  html += '</div></div>';

  // ── Asset Rankings ──
  html += '<div class="card"><div class="card-title">📈 资产评分排行</div>';
  html += '<div style="overflow-x:auto"><table>';
  html += '<thead><tr><th>#</th><th>资产</th><th>分组</th><th>综合分</th><th>趋势</th><th>资金</th><th>风险</th><th>操作</th></tr></thead><tbody>';
  D.ranked.forEach(function(a) {{
    var tColor = trendColor(a.trend_score);
    var rColor = riskColor(a.risk_score);
    var action = a.tier === 'core' ? '加仓' : (a.tier === 'reduce' ? '减仓' : '持有');
    var actionCls = a.tier === 'core' ? 'badge-buy' : (a.tier === 'reduce' ? 'badge-reduce' : 'badge-hold');
    var sColor = scoreColor(a.final_score);
    html += '<tr>';
    html += '<td><strong>' + a.rank + '</strong></td>';
    html += '<td><strong>' + a.name + '</strong></td>';
    html += '<td style="font-size:11px;color:var(--text2)">' + (a.group||'') + '</td>';
    html += '<td style="color:' + sColor + ';font-weight:700">' + a.final_score + '</td>';
    html += '<td><span style="color:' + tColor + '">' + a.trend_score + '</span></td>';
    html += '<td>' + a.flow_score + '</td>';
    html += '<td><span style="color:' + rColor + '">' + a.risk_score + '</span></td>';
    html += '<td><span class="badge ' + actionCls + '">' + action + '</span></td>';
    html += '</tr>';
  }});
  html += '</tbody></table></div></div>';

  // ── Portfolio ──
  html += '<div class="card"><div class="card-title">💰 仓位建议</div>';
  html += '<div class="grid-3">';
  html += statCard('权益', (D.portfolio.equity_allocation*100).toFixed(0) + '%', 'var(--red)');
  html += statCard('现金', (D.portfolio.cash_allocation*100).toFixed(0) + '%', 'var(--text2)');
  html += statCard('防守', (D.portfolio.defensive_weight*100).toFixed(0) + '%', 'var(--green)');
  html += statCard('成长', (D.portfolio.growth_weight*100).toFixed(0) + '%', 'var(--blue)');
  html += statCard('买入', D.portfolio.buy_count + ' 只', 'var(--red)');
  html += statCard('持有', D.portfolio.hold_count + ' 只', 'var(--blue)');
  html += statCard('减仓', D.portfolio.reduce_count + ' 只', 'var(--green)');
  html += '</div></div>';

  // ── Advice ──
  html += '<div class="card"><div class="card-title">🎯 今日操作建议</div>';
  D.advice.forEach(function(a) {{
    html += '<div class="advice-item">' + a + '</div>';
  }});
  html += '</div>';

  document.getElementById('app').innerHTML = html;

  function statCard(label, value, color) {{
    return '<div class="stat"><div class="stat-value" style="color:' + color + '">' + value + '</div><div class="stat-label">' + label + '</div></div>';
  }}
}})();
</script>
</body>
</html>"""

    # Write to docs/
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    path = os.path.join(docs_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ── Standalone mode ───────────────────────────────────────────────────
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    print("🔄 Running standalone pipeline + report...")
    # Import and run the pipeline
    from data_engine import fetch_all_assets, fetch_macro, GROUP_NAMES
    from signal_engine import rate_scores
    from market_regime import detect_regime
    from rotation_engine import rank_assets, detect_rotation
    from portfolio_engine import build_portfolio, generate_advice

    print("📊 Fetching data...")
    assets = fetch_all_assets()
    macro = fetch_macro()
    print(f"   {len(assets)} assets ready")

    scored = [rate_scores(a) for a in assets]
    regime = detect_regime(scored, macro)
    ranked = rank_assets(scored)
    rotation_signals = detect_rotation(ranked)
    portfolio = build_portfolio(ranked, regime)
    advice = generate_advice(regime, rotation_signals)

    print("📄 Generating report...")
    path = generate_v2_html(regime, ranked, rotation_signals, portfolio, macro, advice)
    print(f"✅ Report: {path}")
