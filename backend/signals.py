"""
Signal Computation — momentum ranking, MA crossover, DCA enhancement.
Pure calculation layer; does NOT fetch data itself.
"""

import numpy as np
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

# Reuse data_fetcher for the K-line data
try:
    from . import data_fetcher as df
except ImportError:
    import data_fetcher as df

import logging
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
#  Strategy 1: ETF Momentum Rotation
# ──────────────────────────────────────────────────────────────────────

def calc_momentum_score(etf: dict, top_n: int = 5) -> Optional[dict]:
    """
    Compute momentum score from 3-month and 6-month returns (50/50 weight).
    Returns dict with scores, or None if data is insufficient.
    """
    sina_code = df._sina_code(etf)
    kline = df.get_etf_kline(sina_code, "daily", 180)

    if kline is None or len(kline) < 120:
        return None

    closes = kline["close"].values

    ret_1m = (closes[-1] / closes[-21] - 1) if len(closes) >= 21 else None
    ret_3m = (closes[-1] / closes[-63] - 1) if len(closes) >= 63 else None
    ret_6m = (closes[-1] / closes[-126] - 1) if len(closes) >= 126 else None

    if ret_3m is None or ret_6m is None:
        return None

    momentum = ret_3m * 0.5 + ret_6m * 0.5

    return {
        "code": etf["code"],
        "name": etf["name"],
        "category": etf["category"],
        "ret_1m": round(ret_1m * 100, 2) if ret_1m is not None else None,
        "ret_3m": round(ret_3m * 100, 2),
        "ret_6m": round(ret_6m * 100, 2),
        "momentum_score": round(momentum * 100, 2),
    }


def get_rotation_ranking(top_n: int = 5) -> list[dict]:
    """Rank all ETF pool by momentum and return top N."""
    scores = []
    for etf in df.ETF_POOL:
        s = calc_momentum_score(etf, top_n)
        if s is not None:
            scores.append(s)

    scores.sort(key=lambda x: x["momentum_score"], reverse=True)
    return scores[:top_n]


# ──────────────────────────────────────────────────────────────────────
#  Strategy 2: MA Crossover Trend Signals
# ──────────────────────────────────────────────────────────────────────

def calc_ma_signal(etf_code: str) -> Optional[dict]:
    """
    Compute MA crossover signals: golden cross, death cross, etc.
    """
    kline = df.get_etf_kline(etf_code, "daily", 200)
    if kline is None or len(kline) < 80:
        return None

    kline["ma20"] = kline["close"].rolling(20).mean()
    kline["ma60"] = kline["close"].rolling(60).mean()
    kline["volume_ma20"] = kline["volume"].rolling(20).mean()

    last = kline.iloc[-1]
    prev = kline.iloc[-2]
    early = kline.iloc[-6]

    price = float(last["close"])
    ma20_now = float(last["ma20"])
    ma60_now = float(last["ma60"])
    ma20_prev = float(prev["ma20"])
    ma60_prev = float(prev["ma60"])
    vol_now = float(last["volume"])
    vol_ma20_now = float(last["volume_ma20"])
    ma20_early = float(early["ma20"])
    ma60_early = float(early["ma60"])

    if any(pd.isna(x) for x in [ma20_now, ma60_now, ma20_prev, ma60_prev, vol_ma20_now]):
        return None

    # Golden cross: MA20 crosses above MA60
    is_golden_cross = (
        ma20_prev <= ma60_prev
        and ma20_now > ma60_now
    )

    # Death cross: MA20 crosses below MA60
    is_death_cross = (
        ma20_prev >= ma60_prev
        and ma20_now < ma60_now
    )

    # Quality filter for golden cross
    ma20_slope = (ma20_now - ma20_early) / ma20_early  # rough slope over ~5 days
    vol_ratio = vol_now / vol_ma20_now if vol_ma20_now > 0 else 1.0
    golden_quality = is_golden_cross and ma20_slope > 0 and vol_ratio > 1.2

    # Determine overall signal
    if price > ma20_now > ma60_now:
        signal = "strong_hold"
        signal_cn = "强势持有"
        direction = "hold"
    elif price > ma60_now:
        signal = "hold"
        signal_cn = "持有"
        direction = "hold"
    elif golden_quality:
        signal = "golden_cross"
        signal_cn = "金叉买入"
        direction = "buy"
    elif is_golden_cross:
        signal = "weak_golden"
        signal_cn = "弱金叉(观望)"
        direction = "watch"
    elif is_death_cross:
        signal = "death_cross"
        signal_cn = "死叉卖出"
        direction = "sell"
    elif abs(ma20_now - ma60_now) / ma60_now < 0.02:
        signal = "consolidation"
        signal_cn = "震荡观望"
        direction = "watch"
    else:
        signal = "wait"
        signal_cn = "空仓等待"
        direction = "wait"

    return {
        "code": etf_code,
        "signal": signal,
        "signal_cn": signal_cn,
        "direction": direction,
        "price": round(price, 3),
        "ma20": round(ma20_now, 3),
        "ma60": round(ma60_now, 3),
        "ma_diff_pct": round((ma20_now - ma60_now) / ma60_now * 100, 2),
        "vol_ratio": round(vol_ratio, 2),
        "ma20_slope_pct": round(ma20_slope * 100, 2),
    }


def scan_all_etf_signals() -> list[dict]:
    """Scan all ETFs in the pool for MA crossover signals."""
    results = []
    for etf in df.ETF_POOL:
        sina_code = df._sina_code(etf)
        signal = calc_ma_signal(sina_code)
        if signal:
            signal["name"] = etf["name"]
            signal["category"] = etf["category"]
        results.append(signal)
    return [r for r in results if r is not None]


# ──────────────────────────────────────────────────────────────────────
#  Strategy 3: DCA Enhancement (定投增强)
# ──────────────────────────────────────────────────────────────────────

def calc_dca_signal(etf_code: str, amount: float = 5000) -> Optional[dict]:
    """
    Determine DCA (dollar-cost averaging) enhancement signal:
    - Price < MA60 → invest 1.5x
    - Price near MA60 ±3% → invest 1.0x
    - Price > MA60 × 1.1 → invest 0.5x
    - Price > MA60 × 1.2 → skip
    """
    kline = df.get_etf_kline(etf_code, "daily", 120)
    if kline is None or len(kline) < 60:
        return None

    kline["ma60"] = kline["close"].rolling(60).mean()
    last = kline.iloc[-1]

    price = float(last["close"])
    ma60 = float(last["ma60"])

    if pd.isna(ma60):
        return None

    ratio = price / ma60

    if ratio < 1.0:
        action = "double_down"
        action_cn = "低位加投"
        multiplier = 1.5
        invest_amount = amount * multiplier
    elif 0.97 <= ratio <= 1.03:
        action = "normal"
        action_cn = "正常定投"
        multiplier = 1.0
        invest_amount = amount
    elif ratio > 1.2:
        action = "skip"
        action_cn = "跳过定投"
        multiplier = 0
        invest_amount = 0
    elif ratio > 1.1:
        action = "reduce"
        action_cn = "高位少投"
        multiplier = 0.5
        invest_amount = amount * multiplier
    else:
        action = "normal"
        action_cn = "正常定投"
        multiplier = 1.0
        invest_amount = amount

    return {
        "code": etf_code,
        "price": round(price, 3),
        "ma60": round(ma60, 3),
        "ratio": round(ratio, 4),
        "action": action,
        "action_cn": action_cn,
        "multiplier": multiplier,
        "base_amount": amount,
        "invest_amount": round(invest_amount, 2),
    }


def scan_all_dca_signals(amount: float = 5000) -> list[dict]:
    """Scan all ETFs for DCA signals."""
    results = []
    for etf in df.ETF_POOL:
        sina_code = df._sina_code(etf)
        s = calc_dca_signal(sina_code, amount)
        if s:
            s["name"] = etf["name"]
            s["category"] = etf["category"]
        results.append(s)
    return [r for r in results if r is not None]


# ──────────────────────────────────────────────────────────────────────
#  Composite Dashboard
# ──────────────────────────────────────────────────────────────────────

def get_dashboard() -> dict:
    """
    Aggregate all signals into a unified dashboard response.
    This is the main endpoint the frontend calls.
    """
    quotes = df.get_all_etf_quotes()
    rotation = get_rotation_ranking(top_n=5)
    ma_signals = scan_all_etf_signals()
    dca_signals = scan_all_dca_signals(amount=5000)
    market_state = df.get_index_kline()

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_state": market_state,
        "quotes": quotes,
        "rotation": rotation,
        "ma_signals": ma_signals,
        "dca_signals": dca_signals,
    }
