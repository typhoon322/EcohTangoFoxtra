"""
strategy_health.py — EcohTangoFoxtra v3.3
策略健康评分 + 市场状态分段表现 + 综合智能报告

整合 regime_detector, drift_monitor, threshold_suggester 的输出，
生成统一 Strategy Health Score 和 Intelligence Report。

封版原则：只读数据，只输出建议，从不修改核心策略逻辑。
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")


def _conn():
    return sqlite3.connect(DB_PATH)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_snapshots(days: int = 730) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM snapshots LIMIT 1").description]
        rows = c.execute(
            "SELECT * FROM snapshots WHERE date >= ? ORDER BY date", (cutoff,)
        ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _get_trades(days: int = 730) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM trades LIMIT 1").description]
        rows = c.execute(
            "SELECT * FROM trades WHERE date >= ? ORDER BY date", (cutoff,)
        ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _get_benchmark_returns(days: int = 730) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        rows = c.execute(
            "SELECT date, close FROM price_history "
            "WHERE code='510300' AND date >= ? ORDER BY date",
            (cutoff,),
        ).fetchall()
    return [{"date": r[0], "close": r[1]} for r in rows]


def _monthly_returns(values: list[float]) -> list[float]:
    """按月聚合收益率（近似）。"""
    if len(values) < 20:
        return []
    monthly = []
    i = 20
    while i < len(values):
        monthly.append((values[i] / values[i - 20] - 1) * 100)
        i += 20
    return monthly


def _classify_regime_for_period(start_val: float, end_val: float) -> str:
    """根据区间收益率判断市场状态。"""
    ret = (end_val / start_val - 1) * 100
    if ret > 10:
        return "Bull"
    elif ret < -5:
        return "Bear"
    else:
        return "Sideways"


# ── Regime-Aware Breakdown ────────────────────────────────────────────────────

def get_regime_breakdown(snaps: Optional[list[dict]] = None) -> dict:
    """
    将回测收益按市场状态分段。

    输出：
      breakdown: {Bull: {days, return_pct, weight}, Bear: {...}, Sideways: {...}}
      total_return_pct: 总收益
      regime_weights: 各状态占时间比例
    """
    if snaps is None:
        snaps = _get_snapshots(730)

    if len(snaps) < 60:
        return {"error": "数据不足（需至少60个快照）", "breakdown": {}, "total_return_pct": 0}

    values = [s["total_value"] for s in snaps]
    dates = [s["date"] for s in snaps]
    total_return_pct = (values[-1] / values[0] - 1) * 100

    breakdown = {"Bull": [], "Bear": [], "Sideways": []}

    # 滑动窗口分类（每20天一段）
    i = 20
    while i < len(snaps):
        seg_values = values[i - 20:i]
        regime = _classify_regime_for_period(seg_values[0], seg_values[-1])
        ret = (seg_values[-1] / seg_values[0] - 1) * 100
        breakdown[regime].append(ret)
        i += 20

    result = {}
    for regime, rets in breakdown.items():
        if rets:
            result[regime] = {
                "episodes": len(rets),
                "avg_return_pct": round(sum(rets) / len(rets), 2),
                "best": round(max(rets), 2),
                "worst": round(min(rets), 2),
                "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
            }
        else:
            result[regime] = {
                "episodes": 0,
                "avg_return_pct": 0,
                "best": 0,
                "worst": 0,
                "win_rate": 0,
            }

    return {
        "breakdown": result,
        "total_return_pct": round(total_return_pct, 2),
        "regime_weights": {
            k: round(len(v) / max(sum(len(vv) for vv in breakdown.values()), 1) * 100, 1)
            for k, v in breakdown.items()
        },
    }


def format_regime_breakdown(breakdown: dict) -> str:
    """格式化分段报告。"""
    result = breakdown.get("breakdown", {})
    total = breakdown.get("total_return_pct", 0)
    weights = breakdown.get("regime_weights", {})

    emoji = {"Bull": "🐂", "Bear": "🐻", "Sideways": "↔️"}
    lines = [
        f"📊 分状态回测收益 (总 +{total:.2f}%):",
        "",
    ]
    for regime in ["Bull", "Bear", "Sideways"]:
        if regime in result:
            d = result[regime]
            e = emoji.get(regime, "??")
            w = weights.get(regime, 0)
            lines.append(
                f"  {e} {regime:10s} 均{d['avg_return_pct']:+.2f}% "
                f"(胜率{d['win_rate']:.0f}%) "
                f"区间{w:.0f}% Episodes:{d['episodes']}"
            )
    return "\n".join(lines)


# ── Strategy Health Score ─────────────────────────────────────────────────────

def compute_health_score(
    snaps: Optional[list[dict]] = None,
    bench_rows: Optional[list[dict]] = None,
) -> dict:
    """
    计算策略健康评分（4个维度，0-10分）。

    维度：
      Alpha         : 年化超额收益 vs 基准
      Stability     : 月度收益波动率
      Drawdown Ctrl : 最大回撤控制
      Robustness    : 跨状态胜率一致性
    """
    if snaps is None:
        snaps = _get_snapshots(730)
    if bench_rows is None:
        bench_rows = _get_benchmark_returns(730)

    if len(snaps) < 60:
        return {"error": "数据不足", "dimensions": {}, "total_score": 0}

    values = [s["total_value"] for s in snaps]
    dates = [s["date"] for s in snaps]

    # ── Alpha ──
    strategy_cagr = (values[-1] / values[0]) ** (252 / max(len(values), 1)) - 1
    if bench_rows:
        bench_cagr = (bench_rows[-1]["close"] / bench_rows[0]["close"]) ** (
            252 / max(len(bench_rows), 1)
        ) - 1
        alpha = strategy_cagr - bench_cagr
        alpha_pct = alpha * 100
    else:
        alpha_pct = 0

    # Alpha 评分：每 1% alpha 得 1 分，上限 10
    alpha_score = min(max(alpha_pct / 1.0, 0) + 5, 10)

    # ── Stability ──
    monthly_rets = _monthly_returns(values)
    if monthly_rets:
        import statistics

        std_dev = statistics.stdev(monthly_rets) if len(monthly_rets) > 1 else 0
        avg_ret = statistics.mean(monthly_rets)
        stability_score = 10 - min(std_dev / 2, 9) if std_dev < 20 else 1
    else:
        stability_score = 5

    # ── Drawdown Control ──
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    max_dd_pct = max_dd * 100
    # 最大回撤评分：-5% = 10分，-20% = 1分
    dd_score = max(10 - (max_dd_pct / 2.5), 1)

    # ── Robustness ──
    breakdown = get_regime_breakdown(snaps)
    b = breakdown.get("breakdown", {})
    # 各状态胜率是否均衡
    win_rates = [b.get(r, {}).get("win_rate", 50) for r in ["Bull", "Bear", "Sideways"] if b.get(r, {}).get("episodes", 0) > 0]
    if win_rates:
        avg_wr = sum(win_rates) / len(win_rates)
        # 均衡高分（各状态胜率都高）vs 偏科（只有牛市好）
        consistency = 10 - abs(max(win_rates) - min(win_rates)) / 10
        robustness_score = (avg_wr / 10) * consistency
        robustness_score = min(max(robustness_score, 1), 10)
    else:
        robustness_score = 5

    total_score = round((alpha_score + stability_score + dd_score + robustness_score) / 4, 1)

    dimensions = {
        "alpha": round(alpha_score, 1),
        "stability": round(stability_score, 1),
        "drawdown_control": round(dd_score, 1),
        "robustness": round(robustness_score, 1),
    }

    grade = "A+" if total_score >= 9 else "A" if total_score >= 8 else "B" if total_score >= 7 else "C" if total_score >= 6 else "D"

    return {
        "total_score": total_score,
        "grade": grade,
        "dimensions": dimensions,
        "metrics": {
            "alpha_pct": round(alpha_pct, 2),
            "strategy_cagr_pct": round(strategy_cagr * 100, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "monthly_volatility": round(statistics.stdev(monthly_rets), 2) if len(monthly_rets) > 1 else 0,
        },
    }


def format_health_report(health: dict) -> str:
    """格式化健康评分报告。"""
    dims = health.get("dimensions", {})
    metrics = health.get("metrics", {})
    grade = health.get("grade", "?")
    total = health.get("total_score", 0)

    bar = "█" * int(total) + "░" * (10 - int(total))

    lines = [
        f"🏥 策略健康评分 **{total:.1f}/10 [{grade}]** {bar}",
        "",
        f"  Alpha (超额收益)       {dims.get('alpha', 0):.1f}  ({metrics.get('alpha_pct', 0):+.2f}% 年化)",
        f"  Stability (稳定性)     {dims.get('stability', 0):.1f}",
        f"  Drawdown Control (回撤) {dims.get('drawdown_control', 0):.1f}  (最大回撤 {metrics.get('max_drawdown_pct', 0):.1f}%)",
        f"  Robustness (鲁棒性)    {dims.get('robustness', 0):.1f}",
    ]
    return "\n".join(lines)


# ── Full Intelligence Report ──────────────────────────────────────────────────

def build_intelligence_report() -> dict:
    """
    综合报告：Regime + Drift + Thresholds + Health + Breakdown。

    这是 v3.3 的主输出函数，每日管线调用。
    """
    from backend import regime_detector, drift_monitor, threshold_suggester

    regime = regime_detector.detect_regime()
    drift = drift_monitor.detect_drift()
    thresholds = threshold_suggester.suggest_thresholds()
    snaps = _get_snapshots(730)
    health = compute_health_score(snaps)
    breakdown = get_regime_breakdown(snaps)

    # 综合建议
    suggestions = []
    if regime.get("regime") in ("Bear", "HighVolatility"):
        suggestions.append(f"→ 市场{regime['regime']}，建议提高买入阈值至 {thresholds['suggestions']['bear']['buy']}")
    if drift.get("severity") in ("moderate", "severe"):
        suggestions.append(f"→ 策略漂移[{drift['severity']}]，{drift['recommendation'].split('建议：')[1] if '建议：' in drift['recommendation'] else ''}")

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "regime": regime,
        "drift": drift,
        "thresholds": thresholds,
        "health": health,
        "breakdown": breakdown,
        "suggestions": suggestions,
    }


def format_intelligence_report(report: dict) -> str:
    """格式化完整的 Intelligence Report（飞书/终端输出）。"""
    regime = report.get("regime", {})
    drift = report.get("drift", {})
    health = report.get("health", {})
    breakdown = report.get("breakdown", {})
    thresholds = report.get("thresholds", {})

    regime_emoji = {"Bull": "🐂", "Bear": "🐻", "Sideways": "↔️", "HighVolatility": "⚡"}.get(
        regime.get("regime", ""), "??"
    )
    drift_icon = {"none": "✅", "mild": "📊", "moderate": "⚠️", "severe": "🚨"}.get(
        drift.get("severity", "none"), "?"
    )

    lines = [
        "🧠 Strategy Intelligence Report",
        f"生成时间: {report.get('generated_at', '')}",
        "",
        f"{regime_emoji} 市场状态: **{regime.get('regime', 'Unknown')}** "
        f"(置信度 {regime.get('confidence', 0):.0%})",
        "",
        f"{drift_icon} 策略状态: **{drift.get('severity', 'none').upper()}** "
        f"超额{drift.get('underperformance', 0):+.1f}% | "
        f"胜率{drift.get('win_rate') or 'N/A'}",
        "",
        "📊 分状态收益:",
    ]

    breakdown_data = breakdown.get("breakdown", {})
    for r in ["Bull", "Bear", "Sideways"]:
        if r in breakdown_data:
            d = breakdown_data[r]
            lines.append(
                f"  {r:10s} 均{d['avg_return_pct']:+.1f}% "
                f"胜率{d['win_rate']:.0f}% Episodes:{d['episodes']}"
            )

    health_dims = health.get("dimensions", {})
    grade = health.get("grade", "?")
    total = health.get("total_score", 0)
    lines += [
        "",
        f"🏥 健康评分 {total:.1f}/10 [{grade}]",
        f"  Alpha={health_dims.get('alpha',0):.1f} "
        f"Stability={health_dims.get('stability',0):.1f} "
        f"DD={health_dims.get('drawdown_control',0):.1f} "
        f"Robust={health_dims.get('robustness',0):.1f}",
    ]

    sugg = thresholds.get("active_suggestion", {})
    cur = thresholds.get("current", {})
    if sugg:
        lines += [
            "",
            f"📌 阈值建议 (当前:{cur.get('buy',75)})",
            f"  {regime.get('regime','?')} → BUY={sugg.get('buy', cur.get('buy', 75))}",
            f"  {sugg.get('rationale', '')}",
        ]

    if report.get("suggestions"):
        lines += ["", "💡 综合建议:"]
        for s in report["suggestions"]:
            lines.append(f"  {s}")

    return "\n".join(lines)
