"""
ETF Data Fetcher — dual-source: AKShare (real-time) + Sina (K-line).
Both are free and require no API key.
"""

import akshare as ak
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── ETF Pool (default candidates for rotation) ──────────────────────
ETF_POOL = [
    {"code": "510300", "name": "沪深300ETF",      "category": "宽基", "sina_code": "sh510300"},
    {"code": "510500", "name": "中证500ETF",      "category": "宽基", "sina_code": "sh510500"},
    {"code": "159915", "name": "创业板ETF",       "category": "宽基", "sina_code": "sz159915"},
    {"code": "512100", "name": "中证1000ETF",     "category": "宽基", "sina_code": "sh512100"},
    {"code": "588000", "name": "科创50ETF",       "category": "宽基", "sina_code": "sh588000"},
    {"code": "510050", "name": "上证50ETF",       "category": "宽基", "sina_code": "sh510050"},
    {"code": "512880", "name": "证券ETF",         "category": "行业", "sina_code": "sh512880"},
    {"code": "512170", "name": "医疗ETF",         "category": "行业", "sina_code": "sh512170"},
    {"code": "515790", "name": "光伏ETF",         "category": "行业", "sina_code": "sh515790"},
    {"code": "512690", "name": "酒ETF",           "category": "行业", "sina_code": "sh512690"},
    {"code": "159869", "name": "游戏ETF",         "category": "行业", "sina_code": "sz159869"},
    {"code": "513060", "name": "恒生医疗ETF",     "category": "跨境", "sina_code": "sh513060"},
    {"code": "513100", "name": "纳指ETF",         "category": "跨境", "sina_code": "sh513100"},
    {"code": "518880", "name": "黄金ETF",         "category": "商品", "sina_code": "sh518880"},
    {"code": "159941", "name": "纳指ETF(深)",     "category": "跨境", "sina_code": "sz159941"},
]

# Sina K-line API
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


def _sina_code(etf: dict) -> str:
    """Get Sina-style code (sh510300 / sz159915)."""
    return etf.get("sina_code", f"sh{etf['code']}")


# ── Real-time Quotes (AKShare) ───────────────────────────────────────

def get_all_etf_quotes() -> list[dict]:
    """Fetch real-time quotes for all ETFs in the pool via AKShare."""
    try:
        df = ak.fund_etf_spot_em()
        codes_in_pool = {e["code"] for e in ETF_POOL}
        results = []
        for _, row in df.iterrows():
            if row["代码"] in codes_in_pool:
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]) if pd.notna(row["最新价"]) else None,
                    "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else None,
                    "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else None,
                    "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else None,
                    "high": float(row["最高价"]) if pd.notna(row["最高价"]) else None,
                    "low": float(row["最低价"]) if pd.notna(row["最低价"]) else None,
                    "open": float(row["开盘价"]) if pd.notna(row["开盘价"]) else None,
                    "pre_close": float(row["昨收"]) if pd.notna(row["昨收"]) else None,
                })
        return results
    except Exception as e:
        logger.error(f"Error fetching all ETF quotes: {e}")
        return []


# ── K-line Data (Sina API) ───────────────────────────────────────────

def get_etf_kline_raw(sina_symbol: str, days: int = 200) -> Optional[list[dict]]:
    """
    Fetch raw K-line data from Sina API.
    Returns list of dicts with: day, open, high, low, close, volume.
    """
    try:
        params = {"symbol": sina_symbol, "scale": "240", "ma": "no", "datalen": str(max(days, 20))}
        r = requests.get(SINA_KLINE_URL, params=params, timeout=15)
        if r.status_code != 200:
            logger.error(f"Sina API returned {r.status_code} for {sina_symbol}")
            return None
        data = r.json()
        if not data:
            logger.warning(f"No kline data for {sina_symbol}")
            return None
        return data[-days:]
    except Exception as e:
        logger.error(f"Error fetching kline for {sina_symbol}: {e}")
        return None


def get_etf_kline(etf_code: str, period: str = "daily", days: int = 200) -> Optional[pd.DataFrame]:
    """
    Fetch K-line as DataFrame. `etf_code` can be plain code (510300) or sina_code (sh510300).
    """
    # Resolve to sina_code
    if etf_code.startswith("sh") or etf_code.startswith("sz"):
        sina = etf_code
    else:
        match = [e for e in ETF_POOL if e["code"] == etf_code]
        if not match:
            sina = f"sh{etf_code}"
        else:
            sina = _sina_code(match[0])

    raw = get_etf_kline_raw(sina, days)
    if not raw:
        return None

    df = pd.DataFrame(raw)
    df = df.rename(columns={"day": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("date")
    return df


def get_etf_ma(etf_code: str, period: str = "daily", days: int = 200) -> Optional[dict]:
    """
    K-line with moving averages (MA20, MA60, MA120). Returns JSON-serializable dict.
    """
    df = get_etf_kline(etf_code, "daily", days)
    if df is None or df.empty:
        logger.warning(f"Empty kline for {etf_code}")
        return None

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["ma120"] = df["close"].rolling(120).mean()
    df = df.dropna(subset=["close"])

    if df.empty:
        return None

    return {
        "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
        "close": df["close"].round(3).tolist(),
        "ma20": df["ma20"].round(3).tolist(),
        "ma60": df["ma60"].round(3).tolist(),
        "ma120": df["ma120"].round(3).tolist(),
        "volume": df["volume"].tolist(),
        "latest_close": float(df["close"].iloc[-1]),
        "latest_ma20": float(df["ma20"].iloc[-1]) if pd.notna(df["ma20"].iloc[-1]) else None,
        "latest_ma60": float(df["ma60"].iloc[-1]) if pd.notna(df["ma60"].iloc[-1]) else None,
        "latest_ma120": float(df["ma120"].iloc[-1]) if pd.notna(df["ma120"].iloc[-1]) else None,
    }


# ── Index / Market State ─────────────────────────────────────────────

def get_index_kline(index_code: str = "000300", days: int = 200) -> Optional[dict]:
    """
    Fetch HS300 index K-line for market state detection via Sina.
    """
    sina_symbol = f"sh{index_code}"
    raw = get_etf_kline_raw(sina_symbol, days)
    if not raw:
        return None

    df = pd.DataFrame(raw)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["ma60"] = df["close"].rolling(60).mean()
    df = df.dropna(subset=["ma60"])

    if df.empty:
        return None

    latest_close = float(df["close"].iloc[-1])
    latest_ma60 = float(df["ma60"].iloc[-1])
    diff_pct = (latest_close - latest_ma60) / latest_ma60 * 100

    if latest_close > latest_ma60 and diff_pct > 5:
        state, state_cn = "bull", "牛市"
    elif latest_close < latest_ma60 and diff_pct < -5:
        state, state_cn = "bear", "熊市"
    else:
        state, state_cn = "range", "震荡市"

    return {
        "index": index_code,
        "price": round(latest_close, 2),
        "ma60": round(latest_ma60, 2),
        "diff_pct": round(diff_pct, 2),
        "state": state,
        "state_cn": state_cn,
    }
