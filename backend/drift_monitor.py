"""
drift_monitor.py — EcohTangoFoxtra v3.3
策略漂移检测器：监控策略近期表现是否落后于基准。

封版原则：只读数据，从不修改策略逻辑。
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")


def _conn():
    return sqlite3.connect(DB_PATH)


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_recent_snapshots(days: int = 30) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM snapshots LIMIT 1").description]
        rows = c.execute(
            "SELECT * FROM snapshots WHERE date >= ? ORDER BY date", (cutoff,)
        ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _get_benchmark_return(days: int = 30) -> float:
    """基准（沪深300）区间收益。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        rows = c.execute(
            "SELECT close FROM price_history WHERE code='510300' AND date >= ? ORDER BY date",
            (cutoff,),
        ).fetchall()
    if len(rows) >= 2:
        return (rows[-1][0] / rows[0][0] - 1) * 100
    return 0.0


def _get_trades(days: int = 30) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as c:
        cols = [d[0] for d in c.execute("SELECT * FROM trades LIMIT 1").description]
        rows = c.execute(
            "SELECT * FROM trades WHERE date >= ? ORDER BY date", (cutoff,)
        ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _get_win_rate(trades: list[dict]) -> float:
    """已实现交易胜率（按交易盈亏）。"""
    buys = {}
    for t in trades:
        if t.get("action") == "BUY":
            buys[t["code"]] = t.get("price", 0)
        elif t.get("action") in ("SELL", "REDUCE"):
            code = t.get("code")
            if code in buys and buys[code] > 0:
                pnl_pct = (t.get("price", 0) / buys[code] - 1) * 100
                buys[code] = 0  # 已结算
                if pnl_pct > 0:
                    return 1.0  # 有盈利就记为胜
    return 0.0


# ── main monitor ─────────────────────────────────────────────────────────────

def detect_drift(days: int = 30, win_rate_window: int = 20) -> dict:
    """
    检测策略是否漂移（近期表现落后）。

    判断条件（同时满足才触发警告）：
      1. 策略区间收益 < 基准区间收益 - 2%
      2. 胜率 < 45%（或交易次数太少无法判断）

    返回字段：
      drifting    : bool
      severity    : none | mild | moderate | severe
      underperformance : float (% 落后基准)
      win_rate    : float
      recommendation : str
      details     : dict
    """
    # ── 获取数据 ──
    snaps = _get_recent_snapshots(days)
    bench_ret = _get_benchmark_return(days)
    trades = _get_trades(days)

    if len(snaps) < 3:
        return {
            "drifting": False,
            "severity": "none",
            "underperformance": 0.0,
            "win_rate": 0.0,
            "recommendation": "数据不足，无法判断（需至少3个快照）",
            "details": {"snapshots": len(snaps), "trades": len(trades)},
        }

    # ── 策略区间收益 ──
    strategy_ret = snaps[-1]["total_value"] / snaps[0]["total_value"] - 1
    strategy_ret_pct = strategy_ret * 100
    underperformance = strategy_ret_pct - bench_ret  # 负=落后

    # ── 胜率 ──
    win_rate = _get_win_rate(trades[-win_rate_window:]) if len(trades) >= 5 else None

    # ── 判决 ──
    # 落后且胜率低
    drifting = underperformance < -2.0 and (win_rate is None or win_rate < 0.45)
    # 仅落后（温和警告）
    mild_drift = underperformance < -1.0 and (win_rate is None or win_rate < 0.50)

    if drifting:
        severity = "severe" if underperformance < -5.0 else "moderate"
    elif mild_drift:
        severity = "mild"
        drifting = True
    else:
        severity = "none"

    # ── 建议 ──
    if severity == "severe":
        rec = "⚠️ 策略严重失效，建议：①降低仓位至50% ②等待市场状态切换 ③重新验证参数"
    elif severity == "moderate":
        rec = "⚠️ 策略表现落后，建议：①关注市场状态切换 ②适当提高买入阈值至80 ③减少交易频率"
    elif severity == "mild":
        rec = "📊 策略轻微落后，建议：持续监控，关注市场状态变化"
    else:
        rec = "✅ 策略表现正常，无需调整"

    return {
        "drifting": drifting,
        "severity": severity,
        "underperformance": round(underperformance, 2),  # % 落后基准
        "strategy_return_pct": round(strategy_ret_pct, 2),
        "benchmark_return_pct": round(bench_ret, 2),
        "win_rate": win_rate,
        "recommendation": rec,
        "details": {
            "snapshots": len(snaps),
            "trades": len(trades),
            "window_days": days,
        },
    }


def format_drift_report(drift_data: dict) -> str:
    severity = drift_data.get("severity", "none")
    icon = {"none": "✅", "mild": "📊", "moderate": "⚠️", "severe": "🚨"}.get(severity, "??")

    lines = [
        f"{icon} 策略漂移检测 (近{drift_data['details']['window_days']}天)",
        "",
        f"  策略收益: {drift_data.get('strategy_return_pct', 0):+.2f}%",
        f"  基准收益: {drift_data.get('benchmark_return_pct', 0):+.2f}%",
        f"  超额: {drift_data.get('underperformance', 0):+.2f}%",
        f"  胜率: {drift_data.get('win_rate') or 'N/A'}",
        "",
        f"  状态: **{severity.upper()}**",
        f"  建议: {drift_data['recommendation']}",
    ]
    return "\n".join(lines)


def get_drift_status() -> dict:
    """快捷函数。"""
    return detect_drift()
