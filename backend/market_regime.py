"""
L3 — Market Regime Engine: Detects bull/rotation/bear from asset score distribution.
"""

import statistics
from typing import Optional

REGIME_THRESHOLDS = {
    "bull_threshold": 65,       # assets with trend > 65
    "bull_fraction": 0.5,       # >50% of assets strong = bull
    "bear_threshold": 40,       # assets with trend < 40
    "bear_fraction": 0.6,       # >60% assets weak = bear
    "dispersion_low": 12,       # std < 12 = concentrated (bull/bear)
    "dispersion_high": 20,      # std > 20 = rotation
}


def detect_regime(scored_assets: list[dict], macro: Optional[dict] = None) -> dict:
    """
    Determine market regime from scored asset distribution.

    Returns:
      {
        "regime": "bull" | "rotation" | "bear",
        "regime_cn": "主升" | "震荡轮动" | "风险调整",
        "confidence": 0-100,
        "leading_groups": ["ai", "dividend"],
        "lagging_groups": ["consumer"],
        "risk_appetite": "high" | "neutral" | "low",
        "equity_allocation": 0.8 | 0.6 | 0.4,
        "details": {...}
      }
    """
    if not scored_assets:
        return _default_regime()

    trend_scores = [a["trend_score"] for a in scored_assets]
    avg_trend = statistics.mean(trend_scores)
    std_trend = statistics.stdev(trend_scores) if len(trend_scores) > 1 else 0

    strong_count = sum(1 for s in trend_scores if s > REGIME_THRESHOLDS["bull_threshold"])
    weak_count = sum(1 for s in trend_scores if s < REGIME_THRESHOLDS["bear_threshold"])
    total = len(trend_scores)

    strong_pct = strong_count / total
    weak_pct = weak_count / total

    # Determine regime
    if strong_pct >= REGIME_THRESHOLDS["bull_fraction"]:
        regime, regime_cn = "bull", "主升"
        risk_appetite = "high"
        equity_alloc = 0.80
        confidence = int(min(strong_pct * 100, 100))
    elif weak_pct >= REGIME_THRESHOLDS["bear_fraction"]:
        regime, regime_cn = "bear", "风险调整"
        risk_appetite = "low"
        equity_alloc = 0.40
        confidence = int(min(weak_pct * 100, 100))
    elif std_trend > REGIME_THRESHOLDS["dispersion_high"]:
        regime, regime_cn = "rotation", "震荡轮动"
        risk_appetite = "neutral"
        equity_alloc = 0.60
        confidence = 70
    else:
        regime, regime_cn = "rotation", "震荡轮动"
        risk_appetite = "neutral"
        equity_alloc = 0.60
        confidence = 50

    # Identify leading/lagging groups
    groups = {}
    for a in scored_assets:
        g = a.get("group", "other")
        if g not in groups:
            groups[g] = []
        groups[g].append(a["trend_score"])

    group_avg = {g: statistics.mean(s) for g, s in groups.items()}
    sorted_groups = sorted(group_avg.items(), key=lambda x: x[1], reverse=True)

    leading = [g for g, _ in sorted_groups[:3]]
    lagging = [g for g, _ in sorted_groups[-3:]]

    # Macro adjustment
    if macro:
        hs300_diff = macro.get("diff_ma60_pct", 0)
        if hs300_diff < -8 and regime != "bear":
            regime, regime_cn = "bear", "风险调整"
            equity_alloc = 0.40
            risk_appetite = "low"

    return {
        "regime": regime,
        "regime_cn": regime_cn,
        "confidence": confidence,
        "avg_trend": round(avg_trend, 1),
        "std_trend": round(std_trend, 1),
        "strong_pct": round(strong_pct * 100, 1),
        "weak_pct": round(weak_pct * 100, 1),
        "leading_groups": leading,
        "lagging_groups": lagging,
        "risk_appetite": risk_appetite,
        "equity_allocation": equity_alloc,
    }


def _default_regime() -> dict:
    return {
        "regime": "rotation", "regime_cn": "震荡轮动",
        "confidence": 30, "avg_trend": 50, "std_trend": 15,
        "strong_pct": 0, "weak_pct": 0,
        "leading_groups": [], "lagging_groups": [],
        "risk_appetite": "neutral", "equity_allocation": 0.60,
    }
