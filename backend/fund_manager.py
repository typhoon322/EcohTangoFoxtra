"""
fund_manager.py — EcohTangoFoxtra v3.6 Final
基金组合管理层编排器：risk budget → allocation → portfolio → stability → rebalance

v3.6 稳定层：只做降噪/抑制，不修改 v3.1–v3.3 核心策略逻辑。
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from regime_detector import detect_regime, format_regime_report
from risk_budget_engine import compute_risk_budget, STABILITY_PARAMS as RISK_STABILITY
from strategy_pool import STRATEGY_DEFINITIONS, list_strategies
from strategy_weight_allocator import allocate_strategy_weights, STABILITY_PARAMS as ALLOC_STABILITY
from portfolio_constructor import construct_portfolio
from risk_parity_engine import apply_risk_parity
from rebalance_engine import detect_rebalance, STABILITY_PARAMS as REBAL_STABILITY

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")
STATE_FILE = os.path.join(os.path.dirname(__file__), "fund_state.json")

# ── v3.6 稳定层参数（唯一允许微调的旋钮）────────────────────────────────────
STABILITY_PARAMS = {
    "min_strategy_score": 45,        # 低于此分的策略降权
    "weight_smoothing_alpha": 0.30,  # 新权重占比（越小越平滑）
    "min_rebalance_days": 5,         # 最短再平衡间隔（交易日近似）
    "consecutive_loss_days": 3,      # 连亏天数触发保护
    "consecutive_loss_cut": 0.85,    # 连亏时风险预算 ×0.85
    "high_vol_cut": 0.90,            # 高波动时风险预算 ×0.90
}


def _conn():
    return sqlite3.connect(DB_PATH)


def _load_fund_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "prev_regime": "",
        "prev_weights": {},
        "prev_strategy_weights": {},
        "last_rebalance_date": "",
    }


def _save_fund_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _strategy_scores_from_signals(scored_assets: list[dict] | None = None) -> dict[str, float]:
    """从 L2 评分或 DB 推导各策略 score。"""
    if scored_assets:
        code_scores = {a["code"]: a.get("final_score", 50) for a in scored_assets}
    else:
        code_scores = {}

    scores = {}
    for sid, strat in STRATEGY_DEFINITIONS.items():
        asset_codes = [a["code"] for a in strat["assets"]]
        vals = [code_scores[c] for c in asset_codes if c in code_scores]
        scores[sid] = sum(vals) / len(vals) if vals else 55.0
    return scores


def _current_holdings_weights() -> dict[str, float]:
    """从 paper_state.json 读取当前持仓权重。"""
    paper_path = os.path.join(os.path.dirname(__file__), "paper_state.json")
    if not os.path.exists(paper_path):
        return {}
    with open(paper_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    positions = state.get("positions", {})
    total = state.get("cash", 0) + sum(
        p.get("shares", 0) * p.get("current_price", 0) for p in positions.values()
    )
    if total <= 0:
        return {}
    weights = {}
    for code, p in positions.items():
        val = p.get("shares", 0) * p.get("current_price", 0)
        if val > 0:
            weights[code] = val / total
    return weights


def _strategy_health_confidence() -> float:
    try:
        from strategy_health import build_intelligence_report
        report = build_intelligence_report()
        return min(report.get("health", {}).get("total_score", 5) / 10, 1.0)
    except Exception:
        return 0.5


def _consecutive_loss_state(days: int | None = None) -> dict:
    """从 snapshots 检测连亏天数。"""
    n = days or STABILITY_PARAMS["consecutive_loss_days"]
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT daily_pnl_pct FROM snapshots ORDER BY date DESC LIMIT ?",
                (n + 2,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    streak = 0
    for r in rows:
        if r[0] is not None and r[0] < 0:
            streak += 1
        else:
            break
    triggered = streak >= STABILITY_PARAMS["consecutive_loss_days"]
    return {"streak": streak, "triggered": triggered}


def _filter_strategy_scores(scores: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    """过滤低质量策略信号，返回过滤后分数 + 被抑制列表。"""
    min_score = STABILITY_PARAMS["min_strategy_score"]
    filtered = {}
    suppressed = []
    for sid, score in scores.items():
        if score < min_score:
            filtered[sid] = min_score * 0.5
            suppressed.append(sid)
        else:
            filtered[sid] = score
    return filtered, suppressed


def _smooth_weights(
    new_weights: dict[str, float],
    prev_weights: dict[str, float],
) -> dict[str, float]:
    """EMA 平滑组合权重，降低交易频率。"""
    alpha = STABILITY_PARAMS["weight_smoothing_alpha"]
    if not prev_weights:
        return new_weights
    all_codes = set(new_weights) | set(prev_weights)
    smoothed = {}
    for c in all_codes:
        nw = new_weights.get(c, 0.0)
        pw = prev_weights.get(c, 0.0)
        smoothed[c] = alpha * nw + (1 - alpha) * pw
    total = sum(smoothed.values()) or 1.0
    return {c: round(v / total, 3) for c, v in smoothed.items()}


def _apply_stability_to_risk_budget(risk_budget: dict, loss_state: dict) -> dict:
    """连亏保护 + 高波动减仓（抑制层，不改核心逻辑）。"""
    rb = dict(risk_budget)
    multipliers = []
    notes = []

    if loss_state.get("triggered"):
        cut = STABILITY_PARAMS["consecutive_loss_cut"]
        rb["total_risk_budget"] = round(rb["total_risk_budget"] * cut, 4)
        multipliers.append(("consecutive_loss", cut))
        notes.append(f"连亏{loss_state['streak']}天 → 风险预算×{cut}")

    vol = rb.get("portfolio_volatility", 0)
    if vol > RISK_STABILITY.get("high_vol_threshold", 0.018):
        cut = STABILITY_PARAMS["high_vol_cut"]
        rb["total_risk_budget"] = round(rb["total_risk_budget"] * cut, 4)
        multipliers.append(("high_volatility", cut))
        notes.append(f"高波动({vol:.3f}) → 风险预算×{cut}")

    rb["stability_multipliers"] = multipliers
    rb["stability_notes"] = notes
    return rb


def _gate_rebalance(
    rebalance: dict,
    fund_state: dict,
    force_regime_shift: bool = False,
) -> dict:
    """再平衡频率节流：最短间隔内只允许 regime shift 触发。"""
    reb = dict(rebalance)
    last = fund_state.get("last_rebalance_date", "")
    min_days = STABILITY_PARAMS["min_rebalance_days"]

    if last and not force_regime_shift:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d")
            days_since = (datetime.now() - last_dt).days
            if days_since < min_days and reb.get("needs_rebalance"):
                reb["needs_rebalance"] = False
                reb["gated"] = True
                reb["recommendation"] = f"hold (rebalance gated, {days_since}d < {min_days}d min)"
                reb["signals"] = [
                    s for s in reb.get("signals", []) if s.get("action") == "hold"
                ] or reb.get("signals", [])
        except ValueError:
            pass

    if reb.get("needs_rebalance") and not reb.get("gated"):
        reb["last_rebalance_date"] = datetime.now().strftime("%Y-%m-%d")

    return reb


def build_fund_report(scored_assets: list[dict] | None = None) -> dict:
    """
    构建完整 Daily Fund Report。

    输出结构:
      regime, risk_budget, strategy_allocation, portfolio,
      risk_parity, rebalance, summary
    """
    regime_data = detect_regime()
    regime = regime_data.get("regime", "Unknown")
    confidence = regime_data.get("confidence", 0.5)

    strat_conf = _strategy_health_confidence()
    loss_state = _consecutive_loss_state()

    risk_budget = compute_risk_budget(
        regime=regime,
        confidence=confidence,
        strategy_confidence=strat_conf,
    )
    risk_budget = _apply_stability_to_risk_budget(risk_budget, loss_state)

    raw_scores = _strategy_scores_from_signals(scored_assets)
    strategy_scores, suppressed_strategies = _filter_strategy_scores(raw_scores)
    allocation = allocate_strategy_weights(
        strategy_scores, regime,
        min_score=STABILITY_PARAMS["min_strategy_score"],
    )
    strategy_weights = allocation["weights"]

    fund_state = _load_fund_state()
    prev_strat = fund_state.get("prev_strategy_weights", {})
    if prev_strat:
        alpha = STABILITY_PARAMS["weight_smoothing_alpha"]
        smoothed = {}
        for sid in strategy_weights:
            smoothed[sid] = round(
                alpha * strategy_weights[sid] + (1 - alpha) * prev_strat.get(sid, 0),
                3,
            )
        total = sum(smoothed.values()) or 1.0
        strategy_weights = {k: round(v / total, 3) for k, v in smoothed.items()}

    defensive_pct = 0.15 if regime in ("Bear", "HighVolatility") else 0.10
    portfolio = construct_portfolio(strategy_weights, risk_budget, defensive_pct)

    risk_parity = apply_risk_parity(
        portfolio["weights"],
        portfolio["volatilities"],
    )
    final_weights = _smooth_weights(
        risk_parity["adjusted_weights"],
        fund_state.get("prev_weights", {}),
    )

    current_weights = _current_holdings_weights()
    rebalance = detect_rebalance(
        target_weights=final_weights,
        current_weights=current_weights,
        risk_contributions=risk_parity["risk_levels"],
        prev_regime=fund_state.get("prev_regime", ""),
        current_regime=regime,
    )
    rebalance = _gate_rebalance(
        rebalance, fund_state,
        force_regime_shift=rebalance.get("regime_shift", False),
    )

    new_state = {
        "prev_regime": regime,
        "prev_weights": final_weights,
        "prev_strategy_weights": strategy_weights,
        "last_rebalance_date": rebalance.get(
            "last_rebalance_date",
            fund_state.get("last_rebalance_date", ""),
        ),
    }
    _save_fund_state(new_state)

    stability = {
        "mode": "v3.6_final",
        "params": STABILITY_PARAMS,
        "consecutive_loss": loss_state,
        "suppressed_strategies": suppressed_strategies,
        "rebalance_gated": rebalance.get("gated", False),
        "smoothing_applied": bool(fund_state.get("prev_weights")),
        "stability_notes": risk_budget.get("stability_notes", []),
    }

    top_holdings = sorted(final_weights.items(), key=lambda x: -x[1])[:6]
    names = portfolio.get("names", {})

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime_data,
        "risk_budget": risk_budget,
        "strategy_scores": strategy_scores,
        "strategy_allocation": {
            "weights": strategy_weights,
            "raw_scores": allocation.get("raw_scores", {}),
        },
        "portfolio": {
            "weights": final_weights,
            "names": names,
            "cash_pct": portfolio.get("cash_pct", 0),
        },
        "risk_parity": risk_parity,
        "rebalance": rebalance,
        "stability": stability,
        "summary": {
            "portfolio_risk_pct": round(risk_budget["total_risk_budget"] * 100, 1),
            "regime": regime,
            "top_holdings": [
                {"code": c, "name": names.get(c, c), "weight": w,
                 "risk_level": risk_parity["risk_levels"].get(c, "MED")}
                for c, w in top_holdings
            ],
            "strategy_weights": strategy_weights,
            "recommendation": rebalance["recommendation"],
            "stability_status": "protected" if loss_state.get("triggered") else "normal",
        },
    }


def format_fund_report(report: dict) -> str:
    """格式化 Daily Fund Report 供终端/飞书输出。"""
    s = report.get("summary", {})
    rb = report.get("risk_budget", {})
    sa = report.get("strategy_allocation", {}).get("weights", {})
    regime = s.get("regime", "Unknown")

    lines = [
        "════════════════════════════════════════════",
        "  🏦 Daily Fund Report",
        f"  {report.get('generated_at', '')}",
        "════════════════════════════════════════════",
        "",
        f"Portfolio Risk: {s.get('portfolio_risk_pct', 0):.1f}%",
        f"Regime: {regime}",
        "",
        "Strategy Allocation:",
    ]
    name_map = {"trend": "Trend", "mean_reversion": "Mean Reversion", "momentum": "Momentum"}
    for k, v in sa.items():
        lines.append(f"  - {name_map.get(k, k)}: {v:.0%}")

    lines.append("")
    lines.append("Top Holdings:")
    for h in s.get("top_holdings", []):
        lines.append(f"  - {h.get('name', h['code'])} {h['weight']:.0%}")

    lines.append("")
    lines.append("Risk Contribution:")
    rp = report.get("risk_parity", {})
    for code, level in rp.get("risk_levels", {}).items():
        name = report.get("portfolio", {}).get("names", {}).get(code, code)
        lines.append(f"  - {name}: {level}")

    lines.append("")
    lines.append(f"Recommendation:")
    lines.append(f"  → {s.get('recommendation', 'hold')}")

    reb = report.get("rebalance", {})
    if reb.get("needs_rebalance"):
        lines.append("")
        lines.append("Rebalance Signal:")
        for sig in reb.get("signals", []):
            if sig["action"] != "hold":
                lines.append(f"  → {sig['message']}")
    elif reb.get("gated"):
        lines.append("")
        lines.append(f"Rebalance: gated ({reb.get('recommendation', '')})")

    stab = report.get("stability", {})
    if stab:
        lines.append("")
        lines.append("Stability (v3.6):")
        status = report.get("summary", {}).get("stability_status", "normal")
        lines.append(f"  Status: {status.upper()}")
        loss = stab.get("consecutive_loss", {})
        if loss.get("triggered"):
            lines.append(f"  ⚠️ 连亏保护: {loss['streak']} 天")
        if stab.get("rebalance_gated"):
            lines.append("  🔒 再平衡已节流")
        for note in stab.get("stability_notes", []):
            lines.append(f"  • {note}")

    lines.append("")
    lines.append(f"Risk Budget Detail: total={rb.get('total_risk_budget', 0):.2%} "
                  f"multiplier={rb.get('regime_multiplier', 1):.2f} "
                  f"max_single={rb.get('max_single_asset_risk', 0):.2%}")
    lines.append("════════════════════════════════════════════")
    return "\n".join(lines)
