"""
regime_detector.py — EcohTangoFoxtra v3.3
市场状态识别器：Bull / Bear / Sideways / HighVolatility

封版原则：只读 price_history，从不修改任何策略逻辑。
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")

# ── helpers ──────────────────────────────────────────────────────────────────

def _conn():
    return sqlite3.connect(DB_PATH)


def _latest_date():
    """返回 price_history 最近一条记录日期。"""
    with _conn() as c:
        row = c.execute("SELECT MAX(date) FROM price_history").fetchone()
        return row[0] if row else None


def _price_window(days: int = 120) -> list[dict]:
    """取最近 N 个交易日的 OHLCV 数据，按日期升序。"""
    cutoff = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    with _conn() as c:
        rows = c.execute(
            "SELECT date, code, close, ma20, ma60 FROM price_history "
            "WHERE date >= ? ORDER BY date",
            (cutoff,),
        ).fetchall()
    cols = ["date", "code", "close", "ma20", "ma60"]
    return [dict(zip(cols, r)) for r in rows]


def _compute_volatility(closes: list[float], window: int = 20) -> float:
    """从收盘价计算日收益率波动率（标准差）。"""
    if len(closes) < window + 1:
        return 0.0
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append((closes[i] / closes[i - 1] - 1))
    if len(rets) < window:
        return 0.0
    import statistics
    recent = rets[-window:]
    return statistics.stdev(recent) if len(recent) > 1 else 0.0


def _compute_max_drawdown(closes: list[float]) -> float:
    """计算当前最大回撤（从历史高点）。"""
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _aggregate_by_date(rows: list[dict]) -> list[dict]:
    """按日期聚合：同一天多只ETF时取等权平均。"""
    by_date = {}
    for r in rows:
        d = r["date"]
        by_date.setdefault(d, []).append(r)
    result = []
    for d in sorted(by_date.keys()):
        group = by_date[d]
        result.append({
            "date": d,
            "close": sum(x["close"] for x in group) / len(group),
            "ma20": sum((x["ma20"] or 0) for x in group) / len(group),
            "ma60": sum((x["ma60"] or 0) for x in group) / len(group),
        })
    return result


def _ma_slope(series: list[float], window: int = 20) -> float:
    """计算均线的线性回归斜率（% per day）。"""
    if len(series) < window:
        return 0.0
    recent = series[-window:]
    x = list(range(len(recent)))
    n = len(recent)
    x_mean = sum(x) / n
    y_mean = sum(recent) / n
    num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, recent))
    den = sum((xi - x_mean) ** 2 for xi in x)
    if den == 0:
        return 0.0
    slope = num / den
    return slope / y_mean * 100  # % per day


def _momentum_divergence(rows: list[dict]) -> float:
    """动量背离：短期 vs 长期均线方向是否一致。负值=顶背离，正值=底背离。"""
    if len(rows) < 60:
        return 0.0
    recent_20 = [r["ma20"] for r in rows[-20:] if r["ma20"]]
    older_20 = [r["ma20"] for r in rows[-60:-20] if r["ma20"]]
    if not recent_20 or not older_20:
        return 0.0
    # 最近20天均线趋势 vs 之前20天
    slope_recent = _ma_slope(recent_20, len(recent_20))
    slope_older = _ma_slope(older_20, len(older_20))
    return slope_recent - slope_older  # 正=加速，负=减速/背离


# ── main detector ─────────────────────────────────────────────────────────────

def detect_regime(days: int = 120) -> dict:
    """
    返回市场状态及置信度。

    输出字段：
      regime      : Bull | Bear | Sideways | HighVolatility
      confidence  : 0.0–1.0
      indicators  : 诊断指标字典
    """
    latest = _latest_date()
    if not latest:
        return _default_regime("No data available")

    rows = _price_window(days)
    if len(rows) < 30:
        return _default_regime(f"Insufficient data ({len(rows)} rows)")

    agg = _aggregate_by_date(rows)

    # ── 计算指标 ──
    closes = [r["close"] for r in agg]
    ma20s = [r["ma20"] for r in agg if r["ma20"]]
    ma60s = [r["ma60"] for r in agg if r["ma60"]]

    # 收益率
    ret_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0.0
    ret_60d = (closes[-1] / closes[-60] - 1) * 100 if len(closes) >= 60 else 0.0

    # 均线斜率
    slope_20 = _ma_slope(ma20s, 20) * 20  # % per month
    slope_60 = _ma_slope(ma60s, 20) * 20 if len(ma60s) >= 20 else 0.0

    # 动量背离
    divergence = _momentum_divergence(agg)

    # 波动率（月均值，从收盘价计算）
    closes_all = [r["close"] for r in agg]
    avg_vol = _compute_volatility(closes_all, 20)
    vol_high = avg_vol > 0.015  # 日波动率 > 1.5% 为高波动（月化约 5%）

    # 最大回撤（近期）
    dd_recent = _compute_max_drawdown(closes_all[-60:])
    dd_prev = _compute_max_drawdown(closes_all[-80:-20]) if len(closes_all) >= 80 else 0
    dd_worsening = dd_recent > dd_prev + 0.03  # 回撤扩大 > 3%

    indicators = {
        "ret_20d": round(ret_20d, 2),
        "ret_60d": round(ret_60d, 2),
        "slope_20d_monthly": round(slope_20, 2),
        "slope_60d_monthly": round(slope_60, 2),
        "avg_volatility": round(avg_vol * 100, 3),
        "momentum_divergence": round(divergence, 4),
        "drawdown_worsening": dd_worsening,
        "current_drawdown_pct": round(dd_recent * 100, 2),
        "latest_price": round(closes[-1], 3) if closes else 0,
        "latest_date": latest,
    }

    # ── 规则判决 ──
    scores = {"Bull": 0, "Bear": 0, "Sideways": 0, "HighVolatility": 0}

    # Bull: 20日均线向上 + 近期正收益 + MA20 > MA60
    if slope_20 > 0.3:
        scores["Bull"] += 1
    if ret_20d > 1.0:
        scores["Bull"] += 1
    if ma20s and ma60s and ma20s[-1] > ma60s[-1]:
        scores["Bull"] += 1
    if divergence > 0.01:  # 动量加速
        scores["Bull"] += 0.5

    # Bear: 均线向下 + 近期负收益 + 回撤扩大
    if slope_20 < -0.3:
        scores["Bear"] += 1
    if ret_20d < -1.0:
        scores["Bear"] += 1
    if dd_worsening:
        scores["Bear"] += 1
    if divergence < -0.01:  # 动量背离
        scores["Bear"] += 0.5

    # Sideways: 均线走平（斜率接近0）
    if abs(slope_20) < 0.3:
        scores["Sideways"] += 1
    if abs(slope_60) < 0.2:
        scores["Sideways"] += 1
    if abs(ret_20d) < 1.5:
        scores["Sideways"] += 1

    # HighVolatility: 高波动（与方向无关）
    if vol_high:
        scores["HighVolatility"] += 1
    if abs(slope_20) > 0.5:
        scores["HighVolatility"] += 0.5  # 波动大的市场往往趋势也强
    if abs(divergence) > 0.02:
        scores["HighVolatility"] += 0.5

    # 找最高分
    regime = max(scores, key=scores.get)
    raw_score = scores[regime]
    # 归一化置信度（最高4分）
    confidence = min(raw_score / 3.5, 1.0)
    confidence = round(confidence, 2)

    # ── 次要标签（当置信度低时混合标注） ──
    secondary = sorted(
        [(k, v) for k, v in scores.items() if k != regime],
        key=lambda x: x[1],
        reverse=True,
    )
    tags = []
    if secondary and secondary[0][1] >= 1.5:
        tags.append(f"incl.{secondary[0][0]}")

    result = {
        "regime": regime,
        "confidence": confidence,
        "indicators": indicators,
        "regime_scores": {k: round(v, 1) for k, v in scores.items()},
        "tags": tags,
        "latest_date": latest,
        "days_analyzed": len(agg),
    }
    return result


def _default_regime(reason: str) -> dict:
    return {
        "regime": "Unknown",
        "confidence": 0.0,
        "indicators": {"reason": reason},
        "regime_scores": {"Bull": 0, "Bear": 0, "Sideways": 0, "HighVolatility": 0},
        "tags": [],
        "latest_date": None,
        "days_analyzed": 0,
    }


def format_regime_report(regime_data: dict) -> str:
    """格式化 regime 检测结果（供终端/飞书输出）。"""
    regime = regime_data.get("regime", "Unknown")
    conf = regime_data.get("confidence", 0)
    ind = regime_data.get("indicators", {})
    scores = regime_data.get("regime_scores", {})

    emoji = {"Bull": "🐂", "Bear": "🐻", "Sideways": "↔️", "HighVolatility": "⚡"}.get(regime, "??")

    lines = [
        f"{emoji} 市场状态: **{regime}** (置信度 {conf:.0%})",
        f"",
        f"关键指标:",
        f"  20日收益: {ind.get('ret_20d', 0):+.2f}%",
        f"  60日收益: {ind.get('ret_60d', 0):+.2f}%",
        f"  MA20月斜率: {ind.get('slope_20d_monthly', 0):+.2f}%",
        f"  MA60月斜率: {ind.get('slope_60d_monthly', 0):+.2f}%",
        f"  月均波动率: {ind.get('avg_volatility', 0):.3f}%",
        f"  动量背离: {ind.get('momentum_divergence', 0):+.4f}",
        f"",
        f"各状态得分: Bull={scores.get('Bull',0):.1f} Bear={scores.get('Bear',0):.1f} "
        f"Sideways={scores.get('Sideways',0):.1f} HV={scores.get('HighVolatility',0):.1f}",
    ]
    return "\n".join(lines)


def get_current_regime() -> dict:
    """快捷函数：返回当前市场状态（用于 main_lite.py）。"""
    return detect_regime()
