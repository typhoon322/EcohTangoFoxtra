"""
strategy_weight_allocator.py — EcohTangoFoxtra v3.6 Final
策略权重分配：score × stability × regime_fit → strategy weights

封版原则：只读策略评分与 regime，不修改信号生成逻辑。
v3.6：低质量信号过滤。
"""

from strategy_pool import STRATEGY_DEFINITIONS, get_regime_fit

# v3.6 稳定层参数
STABILITY_PARAMS = {
    "default_min_score": 45,
}


def _stability_from_sharpe(sharpe: float) -> float:
    """Sharpe → 稳定性系数 [0.5, 1.0]。"""
    if sharpe >= 1.5:
        return 1.0
    if sharpe >= 1.0:
        return 0.85
    if sharpe >= 0.5:
        return 0.70
    return 0.55


def _recent_performance_factor(recent_return: float) -> float:
    """近期表现调节 [0.6, 1.2]。"""
    if recent_return > 5:
        return 1.2
    if recent_return > 0:
        return 1.0
    if recent_return > -5:
        return 0.85
    return 0.6


def allocate_strategy_weights(
    strategy_scores: dict[str, float],
    regime: str,
    sharpe_ratios: dict[str, float] | None = None,
    recent_returns: dict[str, float] | None = None,
    min_score: float | None = None,
) -> dict:
    """
    计算策略权重。

    weight ∝ strategy_score × stability × regime_fit × recent_perf

    输入:
      strategy_scores : {"trend": 72, "mean_reversion": 55, "momentum": 68}
      regime          : Bull | Sideways | Bear | HighVolatility
      sharpe_ratios   : 各策略历史 Sharpe（可选）
      recent_returns  : 各策略近期收益 %（可选）

    输出:
      {"trend": 0.5, "mean_reversion": 0.2, "momentum": 0.3, ...}
    """
    sharpe_ratios = sharpe_ratios or {}
    recent_returns = recent_returns or {}
    min_score = min_score if min_score is not None else STABILITY_PARAMS["default_min_score"]

    raw = {}
    filtered_out = []
    for sid in STRATEGY_DEFINITIONS:
        raw_score = strategy_scores.get(sid, 50.0)
        if raw_score < min_score:
            filtered_out.append(sid)
            continue
        score = raw_score / 100.0
        stability = _stability_from_sharpe(sharpe_ratios.get(sid, 0.8))
        regime_fit = get_regime_fit(sid, regime)
        recent = _recent_performance_factor(recent_returns.get(sid, 0.0))
        raw[sid] = score * stability * regime_fit * recent

    if not raw:
        # 全部被过滤时回退到等权，避免空组合
        raw = {sid: 1.0 for sid in STRATEGY_DEFINITIONS}

    total = sum(raw.values()) or 1.0
    weights = {k: round(v / total, 3) for k, v in raw.items()}

    return {
        "weights": weights,
        "raw_scores": {k: round(v, 4) for k, v in raw.items()},
        "regime": regime,
        "filtered_strategies": filtered_out,
    }
