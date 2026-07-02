"""
threshold_suggester.py — EcohTangoFoxtra v3.3
自适应阈值建议器：根据市场状态建议最优 BUY/HOLD 阈值。

封版原则：只输出建议，不修改任何核心逻辑。
核心逻辑中的阈值（75/50）作为常量引用，绝不修改。
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")

# 当前封版阈值（核心逻辑中使用）
BUY_THRESHOLD_DEFAULT = 75
HOLD_THRESHOLD_DEFAULT = 50


def _conn():
    return sqlite3.connect(DB_PATH)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_snapshots(days: int = 365) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM snapshots LIMIT 1").description]
        rows = c.execute(
            "SELECT * FROM snapshots WHERE date >= ? ORDER BY date", (cutoff,)
        ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _classify_regime_for_threshold(snaps: list[dict]) -> str:
    """从快照收益趋势判断市场状态（用于阈值分析）。"""
    if len(snaps) < 20:
        return "unknown"
    recent_20 = [s["total_value"] for s in snaps[-20:]]
    slope = (recent_20[-1] / recent_20[0] - 1) / 20 * 100  # 日均收益%
    if slope > 0.1:
        return "bull"
    elif slope < -0.05:
        return "bear"
    else:
        return "sideways"


def _simulate_threshold_performance(
    snaps: list[dict],
    buy_th: int,
    hold_th: int,
) -> dict:
    """
    给定一组快照，模拟使用指定阈值的组合表现。

    简化模拟：快照 value 变化即代表策略效果。
    仅用波动率和收益方向评估阈值适配性。
    """
    if len(snaps) < 2:
        return {"return_pct": 0, "volatility": 0, "win_days": 0}

    values = [s["total_value"] for s in snaps]
    daily_returns = []
    for i in range(1, len(values)):
        r = (values[i] / values[i - 1] - 1) * 100
        daily_returns.append(r)

    total_ret = (values[-1] / values[0] - 1) * 100
    avg_ret = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    vol = (sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
    win_days = sum(1 for r in daily_returns if r > 0)

    # 阈值适配性评分（越高越好）
    # 高阈值（>75）适合熊市（减少交易）；低阈值（<70）适合牛市（抓住机会）
    score = total_ret  # 简化为总收益
    if buy_th > 80:
        score *= 1.1  # 高阈值在低波动/熊市时略好
    if buy_th < 70:
        score *= 1.05  # 低阈值在牛市中略好

    return {
        "return_pct": round(total_ret, 2),
        "volatility": round(vol, 3),
        "win_days": win_days,
        "total_days": len(daily_returns),
        "win_rate": round(win_days / max(len(daily_returns), 1) * 100, 1),
        "score": round(score, 2),
    }


# ── main suggester ────────────────────────────────────────────────────────────

def suggest_thresholds(snaps: Optional[list[dict]] = None) -> dict:
    """
    根据历史数据为各市场状态推荐最优阈值。

    原则：
      Bull      → 降低买入阈值（70），更多持仓享受上涨
      Bear      → 提高买入阈值（80），只在极强信号时入场
      Sideways  → 维持默认值（75），平衡信号质量与频率

    返回字段：
      suggestions : {regime: {buy, hold, rationale}}
      current     : 当前阈值
      active_regime : 检测到的当前状态
    """
    if snaps is None:
        snaps = _get_snapshots(365)

    active = _classify_regime_for_threshold(snaps)

    # ── 各状态的建议阈值 ──
    # 基于回测经验值，非自动优化（封版原则）
    suggestions = {
        "bull": {
            "buy": 70,
            "hold": 48,
            "rationale": "牛市提高持仓，减少踏空风险",
            "delta_buy": -5,
            "delta_hold": -2,
        },
        "sideways": {
            "buy": 75,
            "hold": 50,
            "rationale": "震荡市维持标准阈值",
            "delta_buy": 0,
            "delta_hold": 0,
        },
        "bear": {
            "buy": 80,
            "hold": 55,
            "rationale": "熊市提高信号门槛，减少错误买入",
            "delta_buy": +5,
            "delta_hold": +5,
        },
        "high_volatility": {
            "buy": 78,
            "hold": 52,
            "rationale": "高波动市场增加确认，等待更强信号",
            "delta_buy": +3,
            "delta_hold": +2,
        },
        "unknown": {
            "buy": 75,
            "hold": 50,
            "rationale": "数据不足，使用默认阈值",
            "delta_buy": 0,
            "delta_hold": 0,
        },
    }

    # ── 当前状态适用的阈值 ──
    active_suggestion = suggestions.get(active, suggestions["unknown"])

    # ── 如果有足够数据，做简单的阈值敏感性分析 ──
    perf_by_threshold = {}
    for th in [68, 72, 75, 78, 82]:
        perf = _simulate_threshold_performance(snaps, th, th - 25)
        perf_by_threshold[th] = perf

    # 找出历史上表现最好的阈值
    best_th = max(perf_by_threshold, key=lambda k: perf_by_threshold[k]["score"])

    result = {
        "current": {
            "buy": BUY_THRESHOLD_DEFAULT,
            "hold": HOLD_THRESHOLD_DEFAULT,
        },
        "active_regime": active,
        "suggestions": suggestions,
        "active_suggestion": active_suggestion,
        "historical_best_threshold": best_th,
        "performance_by_threshold": {
            k: {"return_pct": v["return_pct"], "win_rate": v["win_rate"]}
            for k, v in perf_by_threshold.items()
        },
    }
    return result


def format_threshold_report(th_data: dict) -> str:
    """格式化阈值建议报告。"""
    active = th_data["active_regime"]
    sugg = th_data["active_suggestion"]
    cur = th_data["current"]

    lines = [
        f"📊 阈值建议 (当前状态: **{active}**)",
        "",
        f"当前阈值 → 建议阈值:",
        f"  BUY  : {cur['buy']} → **{sugg['buy']}** (delta {sugg['delta_buy']:+d})",
        f"  HOLD : {cur['hold']} → **{sugg['hold']}** (delta {sugg['delta_hold']:+d})",
        "",
        f"理由: {sugg['rationale']}",
        "",
        f"各状态建议:",
        f"  Bull       BUY=70  HOLD=48",
        f"  Sideways   BUY=75  HOLD=50 (默认)",
        f"  Bear       BUY=80  HOLD=55",
        f"  HighVol    BUY=78  HOLD=52",
    ]
    return "\n".join(lines)


def get_suggestion() -> dict:
    """快捷函数。"""
    return suggest_thresholds()
