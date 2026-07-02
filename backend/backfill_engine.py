"""
backfill_engine.py — EcohTangoFoxtra v3.2
从 Sina 批量拉取历史 K 线，计算技术指标，存入 SQLite price_history 表。
"""

import math
import os
import time
import requests
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from data_engine import ASSET_POOL, SINA_KLINE_URL
from backtest_store import save_price_batch, get_price_series, init_price_history_schema

SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
FETCH_DAYS = 800          # 尝试拉取天数（Sina 上限约 700交易日）
REQUEST_DELAY = float(os.environ.get("SINA_REQUEST_DELAY", "0.8"))  # 请求间隔（秒），防限速
MAX_RETRIES = 3


def _fetch_raw(sina_code: str, days: int = FETCH_DAYS) -> list[dict] | None:
    """从 Sina 拉取原始 K 线数据。"""
    for attempt in range(MAX_RETRIES):
        try:
            params = {"symbol": sina_code, "scale": "240", "ma": "no", "datalen": str(days)}
            r = requests.get(SINA_KLINE_URL, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
            elif r.status_code == 403 or r.status_code == 429:
                wait = (attempt + 1) * 2
                print(f"  ⚠ rate-limit, waiting {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"  ⚠ HTTP {r.status_code}")
        except Exception as e:
            print(f"  ⚠ error: {e}")
            time.sleep(1)
    return None


def compute_indicators(raw: list[dict]) -> list[dict]:
    """
    给 raw K线数据批量计算技术指标。
    返回带 ma5/ma20/ma60/ma120/macd/rsi 的行列表。
    """
    if not raw:
        return []

    df = pd.DataFrame(raw)
    df = df.rename(columns={
        "day": "date", "open": "open", "high": "high",
        "low": "low", "close": "close", "volume": "volume",
    })
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)

    close = df["close"]
    vol = df["volume"]

    # ── Moving Averages ──
    df["ma5"]   = close.rolling(5).mean()
    df["ma20"]  = close.rolling(20).mean()
    df["ma60"]  = close.rolling(60).mean()
    df["ma120"] = close.rolling(120).mean()

    # ── MACD (12, 26, 9) ──
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    df["macd"]        = ((dif - dea) * 2).round(6)   # MACD 柱 = (DIF-DEA)*2
    df["macd_signal"] = dea.round(6)
    df["macd_hist"]   = ((dif - dea) * 2).round(6)

    # ── RSI (14) ──
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).round(2)

    # 只保留有完整指标的行（dropna 之前先填小缺失）
    result = []
    for _, row in df.iterrows():
        result.append({
            "date":        str(row["date"])[:10],
            "open":        round(float(row["open"]), 3)   if pd.notna(row["open"])   else None,
            "high":        round(float(row["high"]), 3)   if pd.notna(row["high"])   else None,
            "low":         round(float(row["low"]), 3)    if pd.notna(row["low"])    else None,
            "close":       round(float(row["close"]), 3)  if pd.notna(row["close"])  else None,
            "volume":      round(float(row["volume"]), 2) if pd.notna(row["volume"]) else None,
            "ma5":         round(float(row["ma5"]), 4)    if pd.notna(row["ma5"])    else None,
            "ma20":        round(float(row["ma20"]), 4)   if pd.notna(row["ma20"])   else None,
            "ma60":        round(float(row["ma60"]), 4)   if pd.notna(row["ma60"])   else None,
            "ma120":       round(float(row["ma120"]), 4)  if pd.notna(row["ma120"])  else None,
            "macd":        float(row["macd"])             if pd.notna(row["macd"])   else None,
            "macd_signal": float(row["macd_signal"])     if pd.notna(row["macd_signal"]) else None,
            "macd_hist":   float(row["macd_hist"])       if pd.notna(row["macd_hist"])   else None,
            "rsi":         float(row["rsi"])              if pd.notna(row["rsi"])    else None,
        })
    return result


def backfill_one(code: str, sina: str, name: str) -> int:
    """拉取并存储单只 ETF 的历史数据。返回新增行数。"""
    print(f"  ↳ {code} {name}...", end=" ", flush=True)
    raw = _fetch_raw(sina)
    if not raw:
        print("❌ 拉取失败")
        return 0

    rows = compute_indicators(raw)
    # 只保留有 ma20/ma60 的行（指标足够用于回测）
    valid = [r for r in rows if r["ma60"] is not None]
    for r in valid:
        r["code"] = code
        r["name"] = name

    if valid:
        save_price_batch(valid)
    print(f"✅ {len(valid)} 条（含指标）")
    return len(valid)


def backfill_all(show_progress: bool = True) -> dict:
    """
    批量回填所有 ASSET_POOL ETF。
    返回统计：total_rows / failed / date_range
    """
    init_price_history_schema()
    total_rows = 0
    failed = []

    if show_progress:
        print(f"\n📥 开始回填 {len(ASSET_POOL)} 只 ETF...")
        print(f"   目标：{FETCH_DAYS} 交易日历史 + MA/MACD/RSI 指标\n")

    for etf in ASSET_POOL:
        code = etf["code"]
        sina = etf["sina"]
        name = etf["name"]
        n = backfill_one(code, sina, name)
        total_rows += n
        if n == 0:
            failed.append(code)
        time.sleep(REQUEST_DELAY)

    # 统计日期范围
    from backtest_store import get_all_dates
    dates = get_all_dates()
    date_range = f"{dates[0]} → {dates[-1]}" if dates else "无数据"

    result = {
        "total_rows": total_rows,
        "etfs_backfilled": len(ASSET_POOL) - len(failed),
        "failed": failed,
        "date_range": date_range,
        "trading_days": len(dates),
    }

    if show_progress:
        print(f"\n{'='*50}")
        print(f"✅ 回填完成")
        print(f"   总记录数：{total_rows} 条")
        print(f"   ETF 数量：{len(ASSET_POOL) - len(failed)} / {len(ASSET_POOL)}")
        print(f"   日期范围：{date_range}")
        print(f"   交易天数：{len(dates)} 天")
        if failed:
            print(f"   ❌ 失败：{failed}")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = backfill_all()
    print(f"\n回填结果: {result}")
