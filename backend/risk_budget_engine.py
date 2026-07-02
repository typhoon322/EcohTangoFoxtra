"""
risk_budget_engine.py — EcohTangoFoxtra v3.6 Final
风险预算引擎：决定组合最多允许承担多少风险。

封版原则：只读 regime / 波动率 / 回撤数据，不修改任何策略逻辑。
v3.6：参数微调 + 波动抑制，不改核心映射逻辑。
"""

import statistics
import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")

# v3.6 稳定层参数（可微调旋钮）
STABILITY_PARAMS = {
    "high_vol_threshold": 0.018,   # 日波动 >1.8% 视为高波动
    "high_vol_multiplier": 0.82,     # v3.6: 略强于 v3.4 的 0.85
    "med_vol_threshold": 0.015,
    "med_vol_multiplier": 0.90,      # v3.6: 略强于 v3.4 的 0.92
    "dd_worsening_cut": 0.75,        # v3.6: 略强于 v3.4 的 0.80
    "dd_mild_cut": 0.88,             # v3.6: 略强于 v3.4 的 0.90
}

# regime → (min, max) total risk budget
REGIME_RISK_MAP = {
    "Bull": (0.06, 0.08),
    "Sideways": (0.04, 0.06),
    "Bear": (0.02, 0.03),
    "HighVolatility": (0.03, 0.04),
    "Unknown": (0.04, 0.05),
}


def _conn():
    return sqlite3.connect(DB_PATH)


def _portfolio_volatility(days: int = 60) -> float:
    """从 snapshots 表计算组合日收益率波动率。"""
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT total_value FROM snapshots ORDER BY date DESC LIMIT ?",
                (days,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if len(rows) < 10:
        return 0.015  # 默认 1.5% 日波动
    vals = [r[0] for r in reversed(rows)]
    rets = [(vals[i] / vals[i - 1] - 1) for i in range(1, len(vals)) if vals[i - 1] > 0]
    return statistics.stdev(rets) if len(rets) > 1 else 0.015


def _drawdown_trend(days: int = 60) -> float:
    """回撤趋势：正值=回撤扩大，负值=回撤收窄。"""
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT total_value FROM snapshots ORDER BY date DESC LIMIT ?",
                (days,),
            ).fetchall()
        except sqlite3.OperationalError:
            return 0.0
    if len(rows) < 20:
        return 0.0
    vals = [r[0] for r in reversed(rows)]
    mid = len(vals) // 2

    def _max_dd(series):
        peak = series[0]
        dd = 0.0
        for v in series:
            if v > peak:
                peak = v
            dd = max(dd, (peak - v) / peak)
        return dd

    return _max_dd(vals[mid:]) - _max_dd(vals[:mid])


def compute_risk_budget(
    regime: str,
    confidence: float = 0.5,
    portfolio_vol: Optional[float] = None,
    drawdown_trend: Optional[float] = None,
    strategy_confidence: float = 0.5,
) -> dict:
    """
    计算风险预算。

    输入:
      regime              : Bull | Sideways | Bear | HighVolatility
      confidence          : regime 置信度 0–1
      portfolio_vol       : 组合波动率（可选，自动计算）
      drawdown_trend      : 回撤趋势（可选，自动计算）
      strategy_confidence : 策略健康置信度 0–1

    输出:
      total_risk_budget, regime_multiplier, max_single_asset_risk
    """
    lo, hi = REGIME_RISK_MAP.get(regime, REGIME_RISK_MAP["Unknown"])
    base_budget = lo + (hi - lo) * confidence

    if portfolio_vol is None:
        portfolio_vol = _portfolio_volatility()
    if drawdown_trend is None:
        drawdown_trend = _drawdown_trend()

    # 高波动 → 缩减预算（v3.6 更保守）
    vol_multiplier = 1.0
    if portfolio_vol > STABILITY_PARAMS["high_vol_threshold"]:
        vol_multiplier = STABILITY_PARAMS["high_vol_multiplier"]
    elif portfolio_vol > STABILITY_PARAMS["med_vol_threshold"]:
        vol_multiplier = STABILITY_PARAMS["med_vol_multiplier"]

    # 回撤扩大 → 缩减预算（v3.6 更保守）
    dd_multiplier = 1.0
    if drawdown_trend > 0.03:
        dd_multiplier = STABILITY_PARAMS["dd_worsening_cut"]
    elif drawdown_trend > 0.01:
        dd_multiplier = STABILITY_PARAMS["dd_mild_cut"]

    # 策略置信度调节
    strat_multiplier = 0.7 + 0.3 * strategy_confidence

    regime_multiplier = round(vol_multiplier * dd_multiplier * strat_multiplier, 3)
    total_risk_budget = round(base_budget * regime_multiplier, 4)
    max_single_asset_risk = round(min(total_risk_budget / 3, 0.02), 4)

    return {
        "total_risk_budget": total_risk_budget,
        "regime_multiplier": regime_multiplier,
        "max_single_asset_risk": max_single_asset_risk,
        "base_budget": round(base_budget, 4),
        "regime": regime,
        "portfolio_volatility": round(portfolio_vol, 5),
        "drawdown_trend": round(drawdown_trend, 4),
        "strategy_confidence": round(strategy_confidence, 2),
    }
