"""
portfolio_constructor.py — EcohTangoFoxtra v3.5
组合构建：strategy weights × risk budget × inverse volatility → 最终仓位

封版原则：纯组合层，不修改 L5 portfolio_engine 逻辑。
"""

import sqlite3
import os
import statistics
from typing import Optional

from strategy_pool import STRATEGY_DEFINITIONS, DEFENSIVE_ASSETS

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")


def _conn():
    return sqlite3.connect(DB_PATH)


def _asset_volatility(code: str, days: int = 60) -> float:
    with _conn() as c:
        rows = c.execute(
            "SELECT close FROM price_history WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, days + 1),
        ).fetchall()
    if len(rows) < 10:
        return 0.015
    closes = [r[0] for r in reversed(rows)]
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]
    return statistics.stdev(rets) if len(rets) > 1 else 0.015


def construct_portfolio(
    strategy_weights: dict[str, float],
    risk_budget: dict,
    defensive_pct: float = 0.10,
) -> dict:
    """
    合成最终组合权重。

    final_weight = strategy_weight × asset_hint × inverse_vol × risk_budget_scale

    输入:
      strategy_weights : {"trend": 0.5, "mean_reversion": 0.2, "momentum": 0.3}
      risk_budget      : compute_risk_budget() 输出
      defensive_pct    : 防守资产占比（默认 10%）

    输出:
      {"510300": 0.35, "513100": 0.25, ...}
    """
    total_risk = risk_budget.get("total_risk_budget", 0.05)
    equity_budget = 1.0 - defensive_pct

    raw_weights: dict[str, float] = {}

    for sid, sw in strategy_weights.items():
        strat = STRATEGY_DEFINITIONS.get(sid)
        if not strat:
            continue
        for asset in strat["assets"]:
            code = asset["code"]
            vol = _asset_volatility(code)
            inv_vol = 1.0 / max(vol, 0.001)
            hint = asset.get("weight_hint", 0.5)
            raw_weights[code] = raw_weights.get(code, 0.0) + sw * hint * inv_vol

    if not raw_weights:
        return {"weights": {}, "volatilities": {}, "cash_pct": 1.0}

    total_raw = sum(raw_weights.values()) or 1.0
    scaled = {
        c: (v / total_raw) * equity_budget * (total_risk / 0.05)
        for c, v in raw_weights.items()
    }

    # 归一化到 equity_budget
    total_scaled = sum(scaled.values()) or 1.0
    if total_scaled > equity_budget:
        factor = equity_budget / total_scaled
        scaled = {c: v * factor for c, v in scaled.items()}

    # 防守资产
    def_vol = _asset_volatility(DEFENSIVE_ASSETS[0]["code"])
    for da in DEFENSIVE_ASSETS:
        code = da["code"]
        if code not in scaled:
            scaled[code] = defensive_pct / len(DEFENSIVE_ASSETS)
        else:
            scaled[code] += defensive_pct / len(DEFENSIVE_ASSETS)

    total_w = sum(scaled.values())
    if total_w > 1.0:
        scaled = {c: v / total_w for c, v in scaled.items()}

    vols = {c: round(_asset_volatility(c), 5) for c in scaled}
    names = {}
    for s in STRATEGY_DEFINITIONS.values():
        for a in s["assets"]:
            names[a["code"]] = a["name"]
    for da in DEFENSIVE_ASSETS:
        names[da["code"]] = da["name"]

    return {
        "weights": {c: round(v, 3) for c, v in sorted(scaled.items(), key=lambda x: -x[1])},
        "names": names,
        "volatilities": vols,
        "cash_pct": round(max(0, 1.0 - sum(scaled.values())), 3),
        "equity_budget": round(equity_budget, 3),
        "defensive_pct": defensive_pct,
    }
