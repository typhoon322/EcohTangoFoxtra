"""
L4 — Rotation Engine: Unified scoring, tiered pools, sector rotation signals.
"""

import statistics
from data_engine import ASSET_POOL, GROUP_NAMES

# Weights for unified score
W_TREND = 0.5
W_FLOW = 0.3
W_RISK = 0.2  # subtracted


def unified_score(asset: dict) -> float:
    """
    Composite score: 0.5 * trend + 0.3 * flow - 0.2 * risk
    Risk is inverted because higher risk = worse.
    Returns 0-100.
    """
    raw = (
        W_TREND * asset["trend_score"]
        + W_FLOW * asset["flow_score"]
        - W_RISK * asset["risk_score"]
    )
    return max(raw, 0)


def rank_assets(scored_assets: list[dict]) -> list[dict]:
    """Rank all assets by unified score, add rank and tier."""
    for a in scored_assets:
        a["final_score"] = round(unified_score(a), 1)

    ranked = sorted(scored_assets, key=lambda x: x["final_score"], reverse=True)
    total = len(ranked)

    for i, a in enumerate(ranked):
        a["rank"] = i + 1
        percentile = (i + 1) / total

        if percentile <= 0.20:
            a["tier"] = "core"
            a["tier_cn"] = "🟢 主线池"
        elif percentile <= 0.80:
            a["tier"] = "watch"
            a["tier_cn"] = "🟡 观察池"
        else:
            a["tier"] = "reduce"
            a["tier_cn"] = "🔴 淘汰池"

    return ranked


def detect_rotation(ranked_assets: list[dict]) -> list[dict]:
    """
    Detect sector rotation signals by comparing group averages.
    Returns list of group rotation signals.
    """
    groups = {}
    for a in ranked_assets:
        g = a.get("group", "other")
        if g not in groups:
            groups[g] = {"trend": [], "flow": [], "score": []}
        groups[g]["trend"].append(a["trend_score"])
        groups[g]["flow"].append(a["flow_score"])
        groups[g]["score"].append(a["final_score"])

    group_scores = {}
    for g, data in groups.items():
        group_scores[g] = {
            "group": g,
            "name": GROUP_NAMES.get(g, g),
            "avg_trend": round(statistics.mean(data["trend"]), 1),
            "avg_flow": round(statistics.mean(data["flow"]), 1),
            "avg_score": round(statistics.mean(data["score"]), 1),
            "asset_count": len(data["score"]),
        }

    sorted_groups = sorted(group_scores.values(), key=lambda x: x["avg_score"], reverse=True)
    all_avg = statistics.mean([g["avg_score"] for g in sorted_groups]) if sorted_groups else 50

    for g in sorted_groups:
        diff = g["avg_score"] - all_avg
        if diff > 8:
            g["signal"] = "↑ 增强"
            g["direction"] = "up"
        elif diff < -8:
            g["signal"] = "↓ 弱势"
            g["direction"] = "down"
        elif abs(diff) <= 3:
            g["signal"] = "→ 稳定"
            g["direction"] = "flat"
        elif diff > 0:
            g["signal"] = "↗ 偏强"
            g["direction"] = "up"
        else:
            g["signal"] = "↘ 偏弱"
            g["direction"] = "down"

    return sorted_groups
