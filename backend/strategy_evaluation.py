"""
strategy_evaluation.py — EcohTangoFoxtra v3.2
Strategy quality scoring + signal drift detection.
Frozen core: uses stored backtest signals and snapshots only.

Outputs:
  - 4-dimension score card (each 0-10)
  - Signal drift alerts
  - Recommended threshold adjustments
"""

import math
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from backtest_store import (
    get_snapshots, get_trades, get_signal_history,
    get_record_count, init_schema,
)

INITIAL_CASH = 100_000.0


# ── Score Card ─────────────────────────────────────────────────────────────────

class StrategyScoreCard:
    """
    Evaluate strategy across 4 dimensions, each 0-10:
      1. Return Quality      — annualized return vs benchmark
      2. Stability          — volatility of monthly returns
      3. Drawdown Control   — max drawdown depth and recovery speed
      4. Robustness         — consistency across market regimes
    """

    def __init__(self, start_date: str = None, end_date: str = None):
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        self.start_date = start_date
        self.end_date = end_date
        self.snapshots: list[dict] = []
        self.trades: list[dict] = []
        self.scores: Optional[dict] = None

    def evaluate(self) -> dict:
        """Run full evaluation. Returns score card dict."""
        init_schema()
        self.snapshots = get_snapshots(self.start_date, self.end_date)
        self.trades = get_trades(self.start_date, self.end_date)

        if len(self.snapshots) < 5:
            return {
                "status": "insufficient_data",
                "message": f"Only {len(self.snapshots)} snapshots — need at least 5",
                "scores": {},
            }

        return self._compute_scores()

    def _compute_scores(self) -> dict:
        """Compute all four dimension scores."""
        values = [s["total_value"] for s in self.snapshots]
        daily_returns = np.diff(values) / values[:-1]

        # ── 1. Return Quality ────────────────────────────────────────────────
        total_ret = (values[-1] / values[0] - 1) * 100 if values[0] > 0 else 0
        years = len(self.snapshots) / 252
        cagr = ((values[-1] / values[0]) ** (1 / max(years, 0.01)) - 1) * 100 if years > 0 else 0

        # vs benchmark proxy (assume 5% annual for HS300 baseline)
        benchmark_annual = 5.0
        excess_cagr = cagr - benchmark_annual
        # Score: 5% excess → 8, 10%+ → 10, < -5% → 2
        rq = max(0, min(10, 5 + excess_cagr / 2))
        return_quality = round(rq, 1)

        # ── 2. Stability ─────────────────────────────────────────────────────
        # Monthly volatility of returns (lower = more stable)
        monthly_std = float(np.std(daily_returns) * math.sqrt(21)) if len(daily_returns) >= 5 else 0.3
        # Score: <5% monthly std → 9-10, <10% → 7, <15% → 5, <20% → 3, >20% → 1
        if monthly_std < 0.03:     st = 10
        elif monthly_std < 0.05:   st = 9
        elif monthly_std < 0.08:   st = 8
        elif monthly_std < 0.10:   st = 7
        elif monthly_std < 0.15:   st = 6
        elif monthly_std < 0.20:   st = 4
        else:                       st = 2
        stability = float(st)

        # ── 3. Drawdown Control ───────────────────────────────────────────────
        peak = np.maximum.accumulate(values)
        drawdowns = (values - peak) / peak * 100
        max_dd = float(drawdowns.min()) if len(drawdowns) > 0 else 0

        # Recovery speed: how many days from max_dd to new peak
        recovery_days = 0
        max_dd_idx = int(np.argmin(drawdowns)) if len(drawdowns) > 0 else -1
        if max_dd_idx >= 0 and max_dd_idx < len(drawdowns) - 1:
            for i in range(max_dd_idx + 1, len(drawdowns)):
                if drawdowns[i] == 0:
                    recovery_days = i - max_dd_idx
                    break

        # Score: max_dd -5% → 10, -10% → 8, -15% → 6, -20% → 4, -30% → 2
        if max_dd >= -5:       dd_score = 10
        elif max_dd >= -8:     dd_score = 9
        elif max_dd >= -12:    dd_score = 8
        elif max_dd >= -15:    dd_score = 7
        elif max_dd >= -20:    dd_score = 5
        elif max_dd >= -30:    dd_score = 3
        else:                   dd_score = 1

        drawdown_control = float(dd_score)

        # ── 4. Robustness ────────────────────────────────────────────────────
        # Check consistency across market regimes via snap regimes
        regimes = [s.get("regime") for s in self.snapshots if s.get("regime")]
        unique_regimes = len(set(regimes)) if regimes else 1

        # Consistency: how many positive return days
        pos_days = int(np.sum(daily_returns > 0))
        total_days = len(daily_returns)
        consistency_ratio = pos_days / max(total_days, 1)

        if unique_regimes >= 3 and consistency_ratio >= 0.55:  robust = 9
        elif unique_regimes >= 2 and consistency_ratio >= 0.50: robust = 8
        elif consistency_ratio >= 0.50:                           robust = 7
        elif consistency_ratio >= 0.45:                           robust = 5
        elif consistency_ratio >= 0.40:                           robust = 3
        else:                                                       robust = 1
        robustness = float(robust)

        # Weighted total (equal weight)
        total = round((return_quality + stability + drawdown_control + robustness) / 4, 1)

        self.scores = {
            "return_quality": return_quality,
            "stability": stability,
            "drawdown_control": drawdown_control,
            "robustness": robustness,
            "total_score": total,
            "details": {
                "cagr_pct": round(cagr, 2),
                "total_return_pct": round(total_ret, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "recovery_days": recovery_days,
                "monthly_vol_pct": round(monthly_std * 100, 2),
                "win_days": pos_days,
                "total_days": total_days,
                "win_rate_pct": round(consistency_ratio * 100, 1),
                "regimes_observed": unique_regimes,
                "snapshots_used": len(self.snapshots),
                "trades_used": len(self.trades),
            },
        }
        return self.scores


# ── Signal Drift Detection ──────────────────────────────────────────────────────

class SignalDriftDetector:
    """
    Detect when strategy signals are losing effectiveness.
    Rules (frozen):
      - Recent 10 trades underperform benchmark
      - Signal score effectiveness dropping (avg score declining)
      - Consistent action (BUY) leading to losses
    Output: alert level + recommended action.
    """

    def __init__(self, lookback_trades: int = 10):
        self.lookback_trades = lookback_trades
        self.alert: Optional[dict] = None

    def detect(self) -> dict:
        """Run drift detection. Returns alert dict."""
        init_schema()
        trades = get_trades()
        if not trades:
            return {"status": "no_trades", "alert_level": "NONE"}

        recent = trades[-self.lookback_trades:]

        # Metric 1: Avg signal score trend
        scores = [t.get("signal_score") for t in recent if t.get("signal_score") is not None]
        if len(scores) >= 3:
            half = len(scores) // 2
            recent_avg = sum(scores[-half:]) / max(half, 1)
            older_avg = sum(scores[:half]) / max(half, 1)
            score_trend = recent_avg - older_avg
        else:
            score_trend = 0.0

        # Metric 2: Recent BUY trade ratio
        buy_trades = [t for t in recent if t.get("action") == "BUY"]
        buy_ratio = len(buy_trades) / max(len(recent), 1)

        # Metric 3: Score decline severity
        score_drop_pct = abs(score_trend) / max(older_avg, 1) * 100 if older_avg > 0 else 0

        # Decision thresholds (frozen — DO NOT MODIFY)
        if score_trend < -8 and len(scores) >= 5:
            level = "HIGH"
            action = "reduce_exposure"
            reason = f"信号评分持续下滑（均分差 {score_trend:.1f}），建议降低仓位"
        elif score_trend < -4:
            level = "MEDIUM"
            action = "watch"
            reason = f"信号评分略有下降（均分差 {score_trend:.1f}），密切关注"
        elif buy_ratio > 0.8 and score_trend < 0:
            level = "MEDIUM"
            action = "review_buys"
            reason = f"连续买入信号过多（{len(buy_trades)}/{len(recent)}）但效果走弱，建议审视买入逻辑"
        else:
            level = "NONE"
            action = "none"
            reason = "信号有效性稳定"

        self.alert = {
            "status": "ok" if level == "NONE" else f"alert_{level.lower()}",
            "alert_level": level,
            "recommended_action": action,
            "reason": reason,
            "metrics": {
                "score_trend": round(score_trend, 2),
                "score_drop_pct": round(score_drop_pct, 1),
                "buy_ratio_pct": round(buy_ratio * 100, 1),
                "recent_trades_checked": len(recent),
                "recent_avg_score": round(sum(scores) / max(len(scores), 1), 1) if scores else 0.0,
            },
        }
        return self.alert


# ── Combined Evaluation ────────────────────────────────────────────────────────

def full_evaluation(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    Run complete v3.2 evaluation:
      1. Strategy Score Card
      2. Signal Drift Detection
    Returns combined report dict.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    card = StrategyScoreCard(start_date, end_date)
    scores = card.evaluate()

    drift = SignalDriftDetector()
    drift_result = drift.detect()

    counts = get_record_count()

    # Final verdict
    total_score = scores.get("total_score", 0) if isinstance(scores, dict) else 0
    if total_score >= 8:
        verdict = "EXCELLENT"
        verdict_cn = "优秀"
        emoji = "🏆"
    elif total_score >= 7:
        verdict = "GOOD"
        verdict_cn = "良好"
        emoji = "✅"
    elif total_score >= 5:
        verdict = "FAIR"
        verdict_cn = "一般"
        emoji = "⚠️"
    else:
        verdict = "WEAK"
        verdict_cn = "偏弱"
        emoji = "🔴"

    return {
        "period": {"start": start_date, "end": end_date},
        "verdict": verdict,
        "verdict_cn": verdict_cn,
        "emoji": emoji,
        "scores": scores,
        "drift": drift_result,
        "data_coverage": counts,
    }


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_score_card(scores: dict) -> str:
    """Format score card as readable text."""
    if not scores or not isinstance(scores, dict):
        return "❌ 暂无评分数据"

    total = scores.get("total_score", 0)
    grade = "🏆" if total >= 8 else "✅" if total >= 7 else "⚠️" if total >= 5 else "🔴"

    d = scores.get("details", {})
    lines = [
        f"{grade} Strategy Score: {total} / 10  ({scores.get('verdict_cn', '')})",
        f"",
        f"  Return Quality:      {scores.get('return_quality', 0):.1f} / 10  "
        f"(CAGR {d.get('cagr_pct', 0):+.1f}%, 总收益 {d.get('total_return_pct', 0):+.1f}%)",
        f"  Stability:          {scores.get('stability', 0):.1f} / 10  "
        f"(月波动 {d.get('monthly_vol_pct', 0):.1f}%, 胜率 {d.get('win_rate_pct', 0):.1f}%)",
        f"  Drawdown Control:   {scores.get('drawdown_control', 0):.1f} / 10  "
        f"(最大回撤 {d.get('max_drawdown_pct', 0):.1f}%, 恢复 {d.get('recovery_days', 0)}天)",
        f"  Robustness:         {scores.get('robustness', 0):.1f} / 10  "
        f"(市场状态 {d.get('regimes_observed', 0)}种)",
    ]
    return "\n".join(lines)


def format_drift_alert(drift: dict) -> str:
    """Format drift alert as readable text."""
    if not drift:
        return ""

    level = drift.get("alert_level", "NONE")
    if level == "NONE":
        return f"✅ 信号稳定性: {drift.get('reason', '正常')}"

    icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(level, "⚪")
    lines = [
        f"{icon} 信号漂移警报 [{level}]",
        f"  {drift.get('reason')}",
        f"  建议操作: {drift.get('recommended_action')}",
    ]
    m = drift.get("metrics", {})
    lines.append(f"  评分趋势 {m.get('score_trend', 0):+.1f} | "
                  f"买入占比 {m.get('buy_ratio_pct', 0):.0f}% | "
                  f"均分 {m.get('recent_avg_score', 0)}")
    return "\n".join(lines)


def format_full_report(report: dict) -> str:
    """Format complete evaluation report."""
    emoji = report.get("emoji", "📊")
    verdict = report.get("verdict_cn", "未知")
    period = report.get("period", {})

    lines = [
        f"{emoji} ETF策略评估报告",
        f"  评估区间: {period.get('start')} → {period.get('end')}",
        f"",
        format_score_card(report.get("scores", {})),
        f"",
        format_drift_alert(report.get("drift", {})),
        f"",
        f"  数据覆盖: {report.get('data_coverage', {})}",
    ]
    return "\n".join(lines)
