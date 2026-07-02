"""
rebalance_engine.py — EcohTangoFoxtra v3.6 Final
组合再平衡：drift / risk deviation / regime shift 检测

封版原则：只输出 rebalance 建议，不自动执行交易。
v3.6：提高 drift 阈值，降低交易频率。
"""

from typing import Optional

# v3.6 稳定层参数（可微调旋钮）
STABILITY_PARAMS = {
    "drift_threshold": 0.05,         # v3.5: 3% → v3.6: 5%（降噪）
    "risk_deviation_threshold": 0.15,
}

DRIFT_THRESHOLD = STABILITY_PARAMS["drift_threshold"]
RISK_DEVIATION_THRESHOLD = STABILITY_PARAMS["risk_deviation_threshold"]


def detect_rebalance(
    target_weights: dict[str, float],
    current_weights: dict[str, float],
    risk_contributions: dict[str, str] | dict[str, float] | None = None,
    prev_regime: str = "",
    current_regime: str = "",
) -> dict:
    """
    检测是否需要再平衡。

    输出:
      needs_rebalance, signals[], recommendation
    """
    signals = []
    all_codes = set(target_weights) | set(current_weights)

    for code in all_codes:
        target = target_weights.get(code, 0.0)
        current = current_weights.get(code, 0.0)
        drift = target - current

        if abs(drift) >= DRIFT_THRESHOLD:
            name = code
            if drift > 0:
                signals.append({
                    "code": code, "action": "increase",
                    "delta_pct": round(drift * 100, 1),
                    "message": f"increase {code} {drift * 100:.1f}%",
                })
            else:
                signals.append({
                    "code": code, "action": "reduce",
                    "delta_pct": round(abs(drift) * 100, 1),
                    "message": f"reduce {code} {abs(drift) * 100:.1f}%",
                })
        elif abs(drift) < 0.005:
            signals.append({
                "code": code, "action": "hold",
                "delta_pct": 0,
                "message": f"hold {code}",
            })

    regime_shift = prev_regime and current_regime and prev_regime != current_regime

    needs = any(s["action"] in ("increase", "reduce") for s in signals) or regime_shift

    if regime_shift:
        recommendation = f"regime shift {prev_regime} → {current_regime}, rebalance toward defensive"
    elif needs:
        increases = [s for s in signals if s["action"] == "increase"]
        reduces = [s for s in signals if s["action"] == "reduce"]
        if reduces and not increases:
            recommendation = "slight rebalance toward defensive assets"
        elif increases and not reduces:
            recommendation = "slight rebalance toward growth assets"
        else:
            recommendation = "rebalance to target allocation"
    else:
        recommendation = "hold current allocation"

    return {
        "needs_rebalance": needs,
        "signals": signals,
        "recommendation": recommendation,
        "regime_shift": regime_shift,
        "drift_threshold_pct": DRIFT_THRESHOLD * 100,
    }
