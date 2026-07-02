"""
risk_parity_engine.py — EcohTangoFoxtra v3.5
风险平价层：使各资产风险贡献近似相等。

封版原则：纯组合数学层，不修改策略信号。
"""

from typing import Optional


def _risk_level(vol: float) -> str:
    if vol >= 0.025:
        return "HIGH"
    if vol >= 0.015:
        return "MED"
    return "LOW"


def apply_risk_parity(
    weights: dict[str, float],
    volatilities: dict[str, float],
    max_iterations: int = 50,
) -> dict:
    """
    迭代调整权重使 risk contribution ≈ equal。

    risk_contribution_i = weight_i × vol_i / sum(weight_j × vol_j)

    输入:
      weights      : {"510300": 0.35, "513100": 0.25, ...}
      volatilities : {"510300": 0.018, "513100": 0.022, ...}

    输出:
      adjusted_weights, risk_contributions, risk_levels
    """
    if not weights:
        return {"adjusted_weights": {}, "risk_contributions": {}, "risk_levels": {}}

    codes = list(weights.keys())
    w = {c: max(weights[c], 0.001) for c in codes}
    vols = {c: max(volatilities.get(c, 0.015), 0.001) for c in codes}

    for _ in range(max_iterations):
        risk_budgets = {c: w[c] * vols[c] for c in codes}
        total_risk = sum(risk_budgets.values()) or 1.0
        target = total_risk / len(codes)

        converged = True
        for c in codes:
            current = risk_budgets[c]
            if current > 0:
                adjustment = target / current
                new_w = w[c] * (0.5 + 0.5 * adjustment)
                if abs(new_w - w[c]) > 0.0001:
                    converged = False
                w[c] = new_w

        total_w = sum(w.values()) or 1.0
        w = {c: v / total_w for c, v in w.items()}
        if converged:
            break

    risk_budgets = {c: w[c] * vols[c] for c in codes}
    total_risk = sum(risk_budgets.values()) or 1.0
    contributions = {c: round(risk_budgets[c] / total_risk, 3) for c in codes}
    levels = {c: _risk_level(vols[c]) for c in codes}

    return {
        "adjusted_weights": {c: round(w[c], 3) for c in codes},
        "risk_contributions": contributions,
        "risk_levels": levels,
        "volatilities": {c: round(vols[c], 5) for c in codes},
    }
