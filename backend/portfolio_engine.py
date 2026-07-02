"""
L5 — Portfolio Decision Engine: BUY/HOLD/REDUCE actions, position sizing.
Pure decision layer; no data fetching.
"""

import statistics
from typing import Optional


def decide_action(asset: dict, regime: dict) -> dict:
    """
    Determine action for a single asset.
    Returns action dict: {action, action_cn, target_weight, reason}
    """
    score = asset["final_score"]
    trend = asset["trend_score"]
    risk = asset["risk_score"]
    tier = asset.get("tier", "watch")

    # Base action from tier
    if tier == "core":
        action, action_cn = "BUY", "加仓"
    elif tier == "reduce":
        action, action_cn = "REDUCE", "减仓"
    else:
        # Watch tier: check trend/risk combo
        if trend > 60 and risk < 50:
            action, action_cn = "BUY", "加仓"
        elif trend < 40 or risk > 70:
            action, action_cn = "REDUCE", "减仓"
        else:
            action, action_cn = "HOLD", "持有"

    # Reason
    reasons = []
    if trend >= 70: reasons.append("趋势强劲")
    elif trend >= 50: reasons.append("趋势中性")
    else: reasons.append("趋势偏弱")

    if risk <= 30: reasons.append("低风险")
    elif risk <= 60: reasons.append("风险适中")
    else: reasons.append("高风险")

    if asset.get("vol_expanding"): reasons.append("放量")
    if asset.get("up_streak", 0) >= 3: reasons.append("连涨")

    reason = " · ".join(reasons)

    # Target weight
    target_weight = _calc_weight(asset, regime)

    return {
        "code": asset["code"],
        "name": asset["name"],
        "group": asset.get("group", ""),
        "action": action,
        "action_cn": action_cn,
        "target_weight": round(target_weight, 3),
        "reason": reason,
    }


def _calc_weight(asset: dict, regime: dict) -> float:
    """Calculate individual asset target weight within portfolio."""
    tier = asset.get("tier", "watch")
    base = 1.0  # placeholder relative weight

    if tier == "core":
        base = 1.0
    elif tier == "watch":
        base = 0.5
    else:
        base = 0.2

    return base


def build_portfolio(ranked_assets: list[dict], regime: dict) -> dict:
    """
    Build full portfolio: actions for all assets + allocation summary.
    """
    actions = [decide_action(a, regime) for a in ranked_assets]

    # Normalize weights
    total_weight = sum(a["target_weight"] for a in actions)
    if total_weight > 0:
        for a in actions:
            a["target_weight"] = round(a["target_weight"] / total_weight, 3)

    # Summary
    buy_count = sum(1 for a in actions if a["action"] == "BUY")
    hold_count = sum(1 for a in actions if a["action"] == "HOLD")
    reduce_count = sum(1 for a in actions if a["action"] == "REDUCE")

    equity = regime.get("equity_allocation", 0.6)
    cash = round(1 - equity, 2)
    defensive = round(equity * 0.35, 2)  # ~35% of equity in defensive

    # Defense allocation by group
    defensive_weight = 0
    growth_weight = 0
    for a in actions:
        g = a.get("group", "")
        if g in ("dividend", "commodity"):
            defensive_weight += a["target_weight"]
        else:
            growth_weight += a["target_weight"]

    return {
        "actions": actions,
        "buy_count": buy_count,
        "hold_count": hold_count,
        "reduce_count": reduce_count,
        "equity_allocation": equity,
        "cash_allocation": cash,
        "defensive_weight": round(defensive_weight, 3),
        "growth_weight": round(growth_weight, 3),
        "suggested_positions": build_position_summary(actions, equity),
    }


def build_position_summary(actions: list[dict], equity_alloc: float) -> list[dict]:
    """Build readable position summary by action type."""
    buy_list = [a for a in actions if a["action"] == "BUY"]
    reduce_list = [a for a in actions if a["action"] == "REDUCE"]
    hold_list = [a for a in actions if a["action"] == "HOLD"]

    positions = []

    # Top buys
    for a in buy_list[:5]:
        positions.append({
            "name": a["name"], "action": "加仓",
            "weight": a["target_weight"], "reason": a["reason"],
            "priority": "high",
        })

    # Top holds
    for a in hold_list[:5]:
        positions.append({
            "name": a["name"], "action": "持有",
            "weight": a["target_weight"], "reason": a["reason"],
            "priority": "normal",
        })

    # Reduce list
    for a in reduce_list[:5]:
        positions.append({
            "name": a["name"], "action": "减仓",
            "weight": 0, "reason": a["reason"],
            "priority": "reduce",
        })

    return positions


def generate_advice(regime: dict, rotation_signals: list[dict]) -> list[str]:
    """Generate actionable day-trading advice bullets."""
    advice = []

    if regime["regime"] == "bull":
        advice.append("✔ 主升市，积极持仓，可适度追强")
    elif regime["regime"] == "rotation":
        advice.append("✔ 震荡轮动，只在主线加仓，不追弱势")
        advice.append("✔ 弱势板块逐步降权，保留弹药")
    else:
        advice.append("✔ 风险调整期，减仓防守为主")
        advice.append("✔ 关注红利、黄金等防守资产")

    # Rotation-specific
    up_signals = [s for s in rotation_signals if s["direction"] == "up"]
    down_signals = [s for s in rotation_signals if s["direction"] == "down"]

    if up_signals:
        names = "、".join([s["name"] for s in up_signals[:3]])
        advice.append(f"📈 主线方向: {names}")
    if down_signals:
        names = "、".join([s["name"] for s in down_signals[:3]])
        advice.append(f"📉 弱势方向: {names}")

    advice.append("⚠️ 避免单一赛道重仓，注意高波动ETF回撤风险")

    return advice
