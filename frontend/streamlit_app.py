"""
streamlit_app.py — EcohTangoFoxtra v3.3 Intelligence Dashboard
================================================================
Streamlit 仪表盘：展示策略智能监控层的所有输出。

⚠️ 本文件属于 UI/展示层，根据封版原则，可以自由修改。

使用方式：
  cd EcohTangoFoxtra
  streamlit run frontend/streamlit_app.py
  # 或指定端口：
  streamlit run frontend/streamlit_app.py --server.port 8501
"""

import os
import sys
import json
from datetime import datetime

# ── Setup path ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcohTangoFoxtra v3.3",
    page_icon="🧠",
    layout="wide",
)

pio.templates.default = "plotly_white"

# ── Dark theme fix ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0e1117; color: #f0f2f6; }
.stMetric { background-color: #1c1e26 !important; border-radius: 8px; padding: 12px; }
.stMetricLabel { color: #8b949e !important; }
.stMetricValue { color: #f0f2f6 !important; font-size: 1.6rem !important; }
[data-testid="stMetricValue"] { color: #f0f2f6 !important; }
.stAlert { border-radius: 8px; }
section[data-testid="stSidebar"] { background-color: #161b22; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { background-color: #21262d; border-radius: 6px 6px 0 0; padding: 8px 16px; }
.stTabs .css-1q1s5c9 { gap: 4px; }
.stDataFrame { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

st.title("🧠 EcohTangoFoxtra v3.3 — Strategy Intelligence Dashboard")


# ── Load data ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_all():
    from backend.strategy_health import build_intelligence_report
    from backend.backtest_store import get_snapshots, get_trades, get_all_dates

    # Intelligence report
    intel = build_intelligence_report()

    # Backtest snapshots for chart
    snaps = get_snapshots()
    trades = get_trades()
    dates = get_all_dates()

    return intel, snaps, trades, dates


intel, snaps, trades, dates = load_all()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 控制")
    st.caption(f"数据更新: {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("**子系统状态**")
    regime = intel.get("regime", {})
    drift = intel.get("drift", {})
    health = intel.get("health", {})

    def status_dot(ok, label):
        color = "🟢" if ok else "🔴"
        return f"{color} {label}"

    st.markdown(status_dot(True, "Regime Detector"))
    st.markdown(status_dot(drift.get("severity") != "severe", "Drift Monitor"))
    st.markdown(status_dot(health.get("total_score", 0) >= 5, "Health Score"))
    st.markdown(status_dot(len(snaps) > 30, "Backtest Data"))

    st.divider()
    st.caption(f"**快照数**: {len(snaps)}")
    st.caption(f"**交易记录**: {len(trades)}")
    st.caption(f"**数据范围**: {dates[0] if dates else 'N/A'} → {dates[-1] if dates else 'N/A'}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: Strategy Intelligence
# ═══════════════════════════════════════════════════════════════════════════════
tab_intel, tab_health, tab_backtest, tab_signals = st.tabs(
    ["🧠 Intelligence", "🏥 健康评分", "📊 回测", "🎯 信号"]
)

with tab_intel:
    regime = intel.get("regime", {})
    drift = intel.get("drift", {})
    thresholds = intel.get("thresholds", {})

    # ── 4-col top metrics ──
    col1, col2, col3, col4 = st.columns(4)

    regime_emoji = {"Bull": "🐂", "Bear": "🐻", "Sideways": "↔️", "HighVolatility": "⚡"}.get(
        regime.get("regime", ""), "??"
    )
    col1.metric(
        "市场状态",
        f"{regime_emoji} {regime.get('regime', 'Unknown')}",
        f"置信度 {regime.get('confidence', 0):.0%}"
    )

    drift_icon = {"none": "✅", "mild": "📊", "moderate": "⚠️", "severe": "🚨"}.get(
        drift.get("severity", "none"), "?"
    )
    col2.metric(
        "策略状态",
        f"{drift_icon} {drift.get('severity', 'none').upper()}",
        f"超额 {drift.get('underperformance', 0):+.1f}%"
    )

    health = intel.get("health", {})
    grade = health.get("grade", "?")
    col3.metric(
        "健康评分",
        f"{health.get('total_score', 0):.1f} / 10",
        f"等级 [{grade}]"
    )

    breakdown = intel.get("breakdown", {})
    total_ret = breakdown.get("total_return_pct", 0)
    col4.metric(
        "回测总收益",
        f"{'+' if total_ret >= 0 else ''}{total_ret:.2f}%",
        f"{len(snaps)} 个快照"
    )

    st.divider()

    # ── Regime indicators ──
    ind = regime.get("indicators", {})
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("20日收益", f"{ind.get('ret_20d', 0):+.2f}%")
    c2.metric("60日收益", f"{ind.get('ret_60d', 0):+.2f}%")
    c3.metric("MA20月斜率", f"{ind.get('slope_20d_monthly', 0):+.2f}%")
    c4.metric("MA60月斜率", f"{ind.get('slope_60d_monthly', 0):+.2f}%")
    c5.metric("日均波动率", f"{ind.get('avg_volatility', 0):.3f}%")
    c6.metric("当前回撤", f"{ind.get('current_drawdown_pct', 0):.2f}%")

    st.divider()

    # ── Regime scores radar ──
    scores = regime.get("regime_scores", {})
    if scores:
        fig = go.Figure()
        categories = list(scores.keys())
        values = list(scores.values())
        # Close the loop
        categories += [categories[0]]
        values += [values[0]]

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            fillcolor='rgba(88,166,255,0.2)',
            line_color='#58a6ff',
            marker=dict(color='#58a6ff'),
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
            showlegend=False,
            height=280,
            margin=dict(l=40, r=40, t=40, b=40),
            title=dict(text="各状态得分", font_size=13),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 综合建议 ──
    suggestions = intel.get("suggestions", [])
    if suggestions:
        for s in suggestions:
            st.warning(s)

    # ── Regime breakdown table ──
    bd = breakdown.get("breakdown", {})
    weights = breakdown.get("regime_weights", {})

    st.subheader("📊 分状态回测表现")
    regime_tab_data = []
    for r in ["Bull", "Bear", "Sideways"]:
        if r in bd:
            d = bd[r]
            emoji = {"Bull": "🐂", "Bear": "🐻", "Sideways": "↔️"}.get(r, "??")
            regime_tab_data.append({
                "状态": emoji,
                "名称": r,
                "区间数": d["episodes"],
                "平均收益": f"{d['avg_return_pct']:+.2f}%",
                "最好": f"{d['best']:+.2f}%",
                "最差": f"{d['worst']:+.2f}%",
                "胜率": f"{d['win_rate']:.0f}%",
                "时间占比": f"{weights.get(r, 0):.1f}%",
            })
    if regime_tab_data:
        st.dataframe(regime_tab_data, use_container_width=True, hide_index=True)

    # ── Threshold suggestions ──
    st.subheader("📌 自适应阈值建议")
    sugg = thresholds.get("suggestions", {})
    if sugg:
        th_cols = st.columns(len(sugg))
        for i, (reg, s) in enumerate(sugg.items()):
            emoji = {"bull": "🐂", "bear": "🐻", "sideways": "↔️", "high_volatility": "⚡", "unknown": "??"}.get(reg, "??")
            with th_cols[i]:
                st.metric(
                    f"{emoji} {reg}",
                    f"BUY={s['buy']} HOLD={s['hold']}",
                    s.get("delta_buy", 0)
                )
                st.caption(s.get("rationale", "")[:40])

    # ── Drift alert ──
    st.subheader("🚨 策略漂移检测")
    drift = intel.get("drift", {})
    if drift.get("drifting"):
        sev = drift.get("severity", "none")
        sev_color = {"mild": "info", "moderate": "warning", "severe": "error"}.get(sev, "info")
        steval = getattr(st, sev_color, st.info)
        sev_label = {"mild": "📊 轻微漂移", "moderate": "⚠️ 中度漂移", "severe": "🚨 严重漂移"}.get(sev, sev.upper())
        steval(sev_label)
        st.write(f"**策略收益**: {drift.get('strategy_return_pct', 0):+.2f}%")
        st.write(f"**基准收益**: {drift.get('benchmark_return_pct', 0):+.2f}%")
        st.write(f"**胜率**: {drift.get('win_rate') or 'N/A'}")
        st.write(f"**建议**: {drift.get('recommendation', '')}")
    else:
        st.success("✅ 策略表现正常，无漂移")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: Strategy Health Score
# ═══════════════════════════════════════════════════════════════════════════════
with tab_health:
    health = intel.get("health", {})
    dims = health.get("dimensions", {})
    metrics = health.get("metrics", {})

    col1, col2 = st.columns([1, 2])

    with col1:
        total = health.get("total_score", 0)
        grade = health.get("grade", "?")
        grade_colors = {"A+": "#3fb950", "A": "#58a6ff", "B": "#d29922", "C": "#f85149", "D": "#f85149"}
        gcolor = grade_colors.get(grade, "#8b949e")

        fig = go.Figure()
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=total,
            number=dict(font_size=48, color=gcolor),
            gauge=dict(
                axis=dict(range=[0, 10], tickwidth=1, tickcolor="#30363d"),
                bar=dict(color=gcolor, thickness=0.2),
                bgcolor="#21262d",
                borderwidth=0,
                steps=[
                    dict(range=[0, 4, "#f85149"]),
                    dict(range=[4, 7, "#d29922"]),
                    dict(range=[7, 10, "#3fb950"]),
                ],
            ),
        ))
        fig.update_layout(
            height=260, margin=dict(l=20, r=20, t=20, b=20),
            title=dict(text=f"策略健康评分 [{grade}]", font_size=14),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        dim_names = {
            "alpha": "Alpha (超额收益)",
            "stability": "Stability (稳定性)",
            "drawdown_control": "Drawdown Control (回撤)",
            "robustness": "Robustness (鲁棒性)",
        }
        dim_colors = ["#58a6ff", "#3fb950", "#d29922", "#f0883e"]

        fig = go.Figure(go.Bar(
            x=list(dim_names.values()),
            y=[dims.get(k, 0) for k in dim_names.keys()],
            marker_color=dim_colors,
            text=[f"{dims.get(k, 0):.1f}" for k in dim_names.keys()],
            textposition="outside",
        ))
        fig.update_layout(
            height=260,
            yaxis=dict(range=[0, 10.5]),
            margin=dict(l=20, r=20, t=40, b=20),
            plot_bgcolor="transparent",
            paper_bgcolor="transparent",
            title=dict(text="四维评分详情", font_size=14),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Key metrics ──
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("年化超额 Alpha", f"{metrics.get('alpha_pct', 0):+.2f}%")
    m2.metric("策略年化收益", f"{metrics.get('strategy_cagr_pct', 0):+.2f}%")
    m3.metric("最大回撤", f"{metrics.get('max_drawdown_pct', 0):.1f}%")
    m4.metric("月波动率", f"{metrics.get('monthly_volatility', 0):.2f}%")

    # ── Health history (from snapshots) ──
    if len(snaps) > 10:
        vals = [s["total_value"] for s in snaps]
        dates_str = [s["date"] for s in snaps]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates_str,
            y=vals,
            mode="lines",
            line=dict(color="#58a6ff", width=2),
            fill="tozeroy",
            fillcolor="rgba(88,166,255,0.1)",
            name="组合价值",
        ))

        # Add benchmark line
        import sqlite3, os as _os
        db_path = _os.path.join(BACKEND, "backtest.db")
        with sqlite3.connect(db_path) as c:
            bench_rows = c.execute(
                "SELECT date, close FROM price_history WHERE code='510300' ORDER BY date"
            ).fetchall()
        if bench_rows and dates_str:
            bench_map = dict(bench_rows)
            base_val = vals[0] if vals else 100000
            bench_norm = [base_val * (bench_map.get(d, bench_map[list(bench_map.keys())[0]]) / bench_map[list(bench_map.keys())[0]]) for d in dates_str]
            fig.add_trace(go.Scatter(
                x=dates_str,
                y=bench_norm,
                mode="lines",
                line=dict(color="#8b949e", width=1, dash="dot"),
                name="沪深300（等权归一化）",
            ))

        fig.update_layout(
            height=320,
            xaxis=dict(showgrid=False, color="#8b949e"),
            yaxis=dict(showgrid=True, gridcolor="#21262d", color="#8b949e"),
            plot_bgcolor="transparent",
            paper_bgcolor="transparent",
            legend=dict(x=0, y=1.1, orientation="h"),
            margin=dict(l=40, r=20, t=40, b=40),
            title=dict(text="组合价值曲线 vs 基准", font_size=14),
        )
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: Backtest
# ═══════════════════════════════════════════════════════════════════════════════
with tab_backtest:
    st.subheader("📈 历史回测快照")
    if snaps:
        # Convert to display format
        snap_display = []
        for s in snaps[-90:]:  # Last 90 days
            snap_display.append({
                "日期": s["date"],
                "总价值": f"¥{s['total_value']:,.0f}",
                "现金": f"¥{s['cash']:,.0f}",
                "持仓市值": f"¥{s['positions_value']:,.0f}",
                "日收益": f"{s['daily_pnl_pct']:+.2f}%",
                "累计收益": f"{s['total_pnl_pct']:+.2f}%",
            })
        st.dataframe(snap_display[::-1], use_container_width=True, hide_index=True)

        # ── Daily PnL chart ──
        st.subheader("📉 每日收益率分布")
        daily_rets = [s["daily_pnl_pct"] for s in snaps if "daily_pnl_pct" in s]
        if daily_rets:
            fig = go.Figure()
            colors = ["#3fb950" if r >= 0 else "#f85149" for r in daily_rets]
            fig.add_trace(go.Histogram(
                x=daily_rets,
                nbinsx=40,
                marker_color=colors,
                opacity=0.8,
            ))
            fig.update_layout(
                height=250,
                xaxis_title="日收益率 (%)",
                yaxis_title="频次",
                plot_bgcolor="transparent",
                paper_bgcolor="transparent",
                margin=dict(l=40, r=20, t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无回测快照数据（请先运行 `python main_lite.py --backfill --backtest`）")

    # ── Recent trades ──
    st.subheader("📋 近期交易记录")
    if trades:
        trade_display = []
        for t in trades[-30:]:
            action = t.get("action", "?")
            emoji = {"BUY": "🟢", "SELL": "🔴", "REDUCE": "🟡"}.get(action, "??")
            trade_display.append({
                "日期": t["date"],
                "操作": emoji,
                "标的": t.get("name", t.get("code", "")),
                "价格": f"¥{t.get('price', 0):.3f}" if t.get('price') else "N/A",
                "股数": t.get("shares", 0) or "N/A",
                "金额": f"¥{abs(t.get('amount', 0)):,.0f}" if t.get('amount') else "N/A",
                "信号分": t.get("signal_score", "N/A"),
            })
        st.dataframe(trade_display, use_container_width=True, hide_index=True)
    else:
        st.info("暂无交易记录")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: Signals (Live)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_signals:
    st.subheader("🎯 实时信号（需运行 `python main_lite.py --paper` 生成）")

    # Try to load latest ranked data from cache
    cache_path = os.path.join(ROOT, "backend", "signal_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        ranked = cached.get("ranked", [])
        if ranked:
            display_rows = []
            for a in ranked[:20]:
                tier = a.get("tier", "watch")
                tier_emoji = {"core": "🟢", "watch": "🟡", "reduce": "🔴"}.get(tier, "🟡")
                action = a.get("action", "HOLD")
                act_emoji = {"BUY": "🟢", "HOLD": "🟡", "REDUCE": "🔴"}.get(action, "🟡")
                display_rows.append({
                    "层级": tier_emoji,
                    "名称": a.get("name", a.get("code", ""))[:8],
                    "代码": a.get("code", ""),
                    "总分": f"{a.get('final_score', 0):.1f}",
                    "趋势": f"{a.get('trend_score', 0):.1f}",
                    "资金": f"{a.get('flow_score', 0):.1f}",
                    "风险": f"{a.get('risk_score', 0):.1f}",
                    "操作": act_emoji,
                    "目标仓位": f"{a.get('target_weight', 0):.0%}",
                })
            st.dataframe(display_rows, use_container_width=True, hide_index=True)
        else:
            st.info("暂无缓存信号（运行 `python main_lite.py --paper` 即可生成）")
    else:
        st.info("暂无信号缓存（运行 `python main_lite.py --paper` 即可生成）")

    st.divider()
    st.caption("💡 信号数据由 `backend/signal_engine.py` 实时计算，缓存于 `backend/signal_cache.json`")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"EcohTangoFoxtra v3.3 | 数据时间: {intel.get('generated_at', 'N/A')} | "
    f"快照 {len(snaps)} 条 | 交易 {len(trades)} 笔"
)
