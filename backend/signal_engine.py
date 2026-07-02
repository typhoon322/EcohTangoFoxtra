"""
L2 — Signal Engine: Trend Score, Flow Score, Risk Score.
Pure computation; takes asset data dicts, returns scored dicts.
"""

import math
from typing import Optional


def trend_score(asset: dict) -> int:
    """
    Trend Score (0-100).
    Components:
      - MA Structure (40%): price vs MA20/MA60 alignment
      - MACD Momentum (30%): signal strength
      - Price Position (20%): distance from MA60
      - MA Direction (10%): slope of MA20
    """
    price = asset["price"]
    ma20 = asset["ma20"]
    ma60 = asset["ma60"]
    ma120 = asset.get("ma120", ma60)
    macd = asset["macd"]
    rsi = asset["rsi"]

    score = 0

    # ── MA Structure (40 pts) ──
    # Perfect: price > ma20 > ma60 > ma120
    alignment = 0
    if price > ma20: alignment += 10
    if ma20 > ma60: alignment += 10
    if ma60 > ma120: alignment += 10
    if price > ma200_check(price, ma120): alignment += 10
    score += alignment

    # ── MACD Momentum (30 pts) ──
    if macd > 0.05:        score += 30
    elif macd > 0.02:      score += 24
    elif macd > 0:         score += 18
    elif macd > -0.02:     score += 10
    elif macd > -0.05:     score += 5
    else:                   score += 0

    # ── Price Position (20 pts) ──
    dev = (price - ma60) / ma60 * 100
    if dev > 10:            score += 20  # strong uptrend
    elif dev > 5:           score += 16
    elif dev > 0:           score += 12
    elif dev > -5:          score += 8
    elif dev > -10:         score += 4
    else:                   score += 0

    # ── MA Direction (10 pts) ──
    # Use close price series if available (we calculate slope from RSI as proxy)
    # Simple: RSI > 50 means upward bias
    if rsi >= 60:           score += 10
    elif rsi >= 50:         score += 7
    elif rsi >= 40:         score += 4
    else:                   score += 2

    return min(score, 100)


def flow_score(asset: dict) -> int:
    """
    Flow Score (0-100): money flow & momentum quality.
    Components:
      - Volume Change (40%): vol vs average
      - Volatility Expansion (30%): increasing vol = attention
      - Streak Continuity (30%): consecutive up days
    """
    vol_ratio = asset["vol_ratio"]
    vol_expanding = asset.get("vol_expanding", False)
    streak = asset.get("up_streak", 0)
    change_pct = asset.get("change_pct") or 0

    score = 0

    # ── Volume (40 pts) ──
    if vol_ratio >= 2.0:    score += 40
    elif vol_ratio >= 1.5:  score += 32
    elif vol_ratio >= 1.2:  score += 24
    elif vol_ratio >= 1.0:  score += 16
    elif vol_ratio >= 0.8:  score += 8
    else:                   score += 4

    # ── Volatility Expansion (30 pts) ──
    if vol_expanding:       score += 30
    else:                   score += 10

    # ── Streak (30 pts) ──
    if streak >= 5:         score += 30
    elif streak >= 3:       score += 22
    elif streak >= 1:       score += 14
    elif change_pct > 0:    score += 8
    else:                   score += 2

    return min(score, 100)


def risk_score(asset: dict) -> int:
    """
    Risk Score (0-100, HIGHER = MORE RISK).
    Components:
      - Max Drawdown (40%): recent - drawdown depth
      - Price Deviation (30%): how far above MA60
      - Volatility (30%): raw volatility level
    """
    dd = abs(asset.get("max_drawdown", 0))
    vol = asset.get("volatility", 0.3)
    price = asset["price"]
    ma60 = asset["ma60"]
    dev = abs((price - ma60) / ma60)

    score = 0

    # ── Drawdown (40 pts) ──
    if dd > 0.30:           score += 40
    elif dd > 0.20:         score += 32
    elif dd > 0.15:         score += 24
    elif dd > 0.10:         score += 16
    elif dd > 0.05:         score += 8
    else:                   score += 3

    # ── Deviation (30 pts): higher above MA60 = more risk
    if dev > 0.40:          score += 30
    elif dev > 0.25:        score += 24
    elif dev > 0.15:        score += 18
    elif dev > 0.08:        score += 12
    elif dev > 0.03:        score += 6
    else:                   score += 2

    # ── Volatility (30 pts) ──
    if vol > 0.40:          score += 30
    elif vol > 0.30:        score += 24
    elif vol > 0.25:        score += 18
    elif vol > 0.20:        score += 12
    elif vol > 0.15:        score += 6
    else:                   score += 2

    return min(score, 100)


def rate_scores(asset: dict) -> dict:
    """
    Compute all three scores and add them to the asset dict.
    """
    ts = trend_score(asset)
    fs = flow_score(asset)
    rs = risk_score(asset)

    return {
        **asset,
        "trend_score": ts,
        "flow_score": fs,
        "risk_score": rs,
    }


def ma200_check(price: float, ma_long: float, eps: float = 0.01) -> bool:
    """Check if price is meaningfully above long-term MA."""
    return price > ma_long * (1 + eps)
