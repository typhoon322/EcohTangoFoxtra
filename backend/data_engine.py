"""
L1 — Data Engine: Multi-asset pipeline (ETF + Sector + Macro).
Sources: AKShare (real-time quotes) + Sina API (K-line history).
All free, no API key required.
"""

import akshare as ak
import requests
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

# ── Asset Pool (expanded) ────────────────────────────────────────────
# ETFs by sector group for rotation analysis
ASSET_POOL = [
    # === 宽基 (Broad Market) ===
    {"code": "510300", "sina": "sh510300", "name": "沪深300ETF",    "group": "broad"},
    {"code": "510500", "sina": "sh510500", "name": "中证500ETF",    "group": "broad"},
    {"code": "159915", "sina": "sz159915", "name": "创业板ETF",     "group": "broad"},
    {"code": "512100", "sina": "sh512100", "name": "中证1000ETF",   "group": "broad"},
    {"code": "588000", "sina": "sh588000", "name": "科创50ETF",     "group": "broad"},
    {"code": "510050", "sina": "sh510050", "name": "上证50ETF",     "group": "broad"},

    # === AI/科技 (Tech & AI) ===
    {"code": "159869", "sina": "sz159869", "name": "游戏ETF",       "group": "ai"},
    {"code": "515230", "sina": "sh515230", "name": "软件ETF",       "group": "ai"},
    {"code": "159819", "sina": "sz159819", "name": "人工智能ETF",   "group": "ai"},
    {"code": "515050", "sina": "sh515050", "name": "5GETF",         "group": "ai"},
    {"code": "562500", "sina": "sh562500", "name": "机器人ETF",     "group": "ai"},

    # === 医药 (Healthcare) ===
    {"code": "512170", "sina": "sh512170", "name": "医疗ETF",       "group": "health"},
    {"code": "513060", "sina": "sh513060", "name": "恒生医疗ETF",   "group": "health"},
    {"code": "159883", "sina": "sz159883", "name": "医疗器械ETF",   "group": "health"},

    # === 消费 (Consumer) ===
    {"code": "512690", "sina": "sh512690", "name": "酒ETF",         "group": "consumer"},
    {"code": "159928", "sina": "sz159928", "name": "消费ETF",       "group": "consumer"},
    {"code": "159996", "sina": "sz159996", "name": "家电ETF",       "group": "consumer"},

    # === 红利/防守 (Dividend / Defensive) ===
    {"code": "510880", "sina": "sh510880", "name": "红利ETF",       "group": "dividend"},
    {"code": "515080", "sina": "sh515080", "name": "中证红利ETF",   "group": "dividend"},
    {"code": "512800", "sina": "sh512800", "name": "银行ETF",       "group": "dividend"},

    # === 新能源 (New Energy) ===
    {"code": "515790", "sina": "sh515790", "name": "光伏ETF",       "group": "energy"},
    {"code": "159875", "sina": "sz159875", "name": "新能源ETF",     "group": "energy"},
    {"code": "516160", "sina": "sh516160", "name": "新能源车ETF",   "group": "energy"},

    # === 跨境 (Overseas) ===
    {"code": "513100", "sina": "sh513100", "name": "纳指ETF",       "group": "overseas"},
    {"code": "159941", "sina": "sz159941", "name": "纳指ETF(深)",   "group": "overseas"},
    {"code": "513050", "sina": "sh513050", "name": "中概互联ETF",   "group": "overseas"},

    # === 商品 (Commodity) ===
    {"code": "518880", "sina": "sh518880", "name": "黄金ETF",       "group": "commodity"},
    {"code": "159985", "sina": "sz159985", "name": "豆粕ETF",       "group": "commodity"},
]

# Group display names
GROUP_NAMES = {
    "broad": "宽基", "ai": "AI/科技", "health": "医药",
    "consumer": "消费", "dividend": "红利/防守", "energy": "新能源",
    "overseas": "跨境", "commodity": "商品",
}


# ── Data Fetching ────────────────────────────────────────────────────

def _sina_code(asset: dict) -> str:
    return asset.get("sina", f"sh{asset['code']}")


def fetch_all_quotes() -> list[dict]:
    """Real-time quotes for all ETFs via AKShare."""
    try:
        df = ak.fund_etf_spot_em()
        codes = {a["code"] for a in ASSET_POOL}
        results = []
        for _, row in df.iterrows():
            if row["代码"] in codes:
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]) if pd.notna(row["最新价"]) else None,
                    "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else None,
                    "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else None,
                    "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else None,
                })
        return results
    except Exception as e:
        logger.error(f"fetch_all_quotes error: {e}")
        return []


def fetch_kline_raw(sina_symbol: str, days: int = 200) -> Optional[list[dict]]:
    """Raw K-line from Sina API."""
    try:
        params = {"symbol": sina_symbol, "scale": "240", "ma": "no", "datalen": str(max(days, 20))}
        r = requests.get(SINA_KLINE_URL, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        return data[-days:] if data else None
    except Exception as e:
        logger.error(f"fetch_kline_raw({sina_symbol}): {e}")
        return None


def fetch_kline_df(sina_symbol: str, days: int = 200) -> Optional[pd.DataFrame]:
    """K-line as DataFrame with OHLCV columns."""
    raw = fetch_kline_raw(sina_symbol, days)
    if not raw:
        return None
    df = pd.DataFrame(raw)
    df = df.rename(columns={"day": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").dropna(subset=["close"])


def fetch_asset_data(asset: dict) -> Optional[dict]:
    """
    Fetch complete data for one asset: K-line with MAs + MACD + RSI + drawdown.
    Returns standardized dict or None.
    """
    sina = _sina_code(asset)
    df = fetch_kline_df(sina, 250)
    if df is None or len(df) < 60:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values

    price_now = float(close[-1])
    ma5 = float(pd.Series(close).rolling(5).mean().iloc[-1])
    ma20 = float(pd.Series(close).rolling(20).mean().iloc[-1])
    ma60 = float(pd.Series(close).rolling(60).mean().iloc[-1])
    ma120 = float(pd.Series(close).rolling(120).mean().iloc[-1]) if len(close) >= 120 else ma60

    # MACD
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_val = float((dif - dea).iloc[-1]) * 2

    # RSI (14)
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = float(100 - (100 / (1 + rs.iloc[-1])))

    # Volatility (20-day annualized)
    rets = pd.Series(close).pct_change().dropna().tail(20)
    volatility = float(rets.std() * np.sqrt(252))

    # Max drawdown (120-day)
    peak = pd.Series(close).tail(120).expanding().max()
    dd = (pd.Series(close).tail(120).values / peak.values - 1)
    max_drawdown = float(dd.min())

    # Volume trend
    vol_ma20 = float(pd.Series(vol).tail(20).mean())
    vol_ma60 = float(pd.Series(vol).tail(60).mean()) if len(vol) >= 60 else vol_ma20
    vol_ratio = vol[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
    vol_expanding = vol_ma20 > vol_ma60 * 1.1  # volume expanding

    # Up-streak (consecutive days above MA5)
    above_ma5 = close > ma5
    streak = 0
    for v in above_ma5[::-1]:
        if v: streak += 1
        else: break

    # Returns
    ret_1w = float((close[-1] / close[-5] - 1) * 100) if len(close) >= 5 else 0
    ret_1m = float((close[-1] / close[-21] - 1) * 100) if len(close) >= 21 else 0
    ret_3m = float((close[-1] / close[-63] - 1) * 100) if len(close) >= 63 else 0

    return {
        "code": asset["code"],
        "name": asset["name"],
        "group": asset["group"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "price": round(price_now, 4),
        "ma5": round(ma5, 4),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "ma120": round(ma120, 4),
        "macd": round(macd_val, 6),
        "rsi": round(rsi, 1),
        "volatility": round(volatility, 4),
        "max_drawdown": round(max_drawdown, 4),
        "vol_ratio": round(vol_ratio, 2),
        "vol_expanding": vol_expanding,
        "up_streak": streak,
        "change_pct": None,  # filled later from quotes
        "ret_1w": round(ret_1w, 2),
        "ret_1m": round(ret_1m, 2),
        "ret_3m": round(ret_3m, 2),
    }


def fetch_macro() -> Optional[dict]:
    """Fetch macro-level indicators: HS300, market breadth."""
    df = fetch_kline_df("sh000300", 200)
    if df is None or len(df) < 60:
        return None

    close = df["close"].values
    ma20 = float(pd.Series(close).rolling(20).mean().iloc[-1])
    ma60 = float(pd.Series(close).rolling(60).mean().iloc[-1])
    price = float(close[-1])

    diff_ma60 = (price - ma60) / ma60 * 100
    ret_20d = float((close[-1] / close[-20] - 1) * 100) if len(close) >= 20 else 0

    return {
        "index": "000300",
        "price": round(price, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "diff_ma60_pct": round(diff_ma60, 2),
        "ret_20d_pct": round(ret_20d, 2),
    }


def fetch_all_assets(progress: bool = True) -> list[dict]:
    """
    Full pipeline: fetch K-line + compute indicators for all assets.
    Also merges real-time quotes for change_pct.
    """
    result = []

    # Get real-time quotes for change_pct
    quotes = fetch_all_quotes()
    quote_map = {q["code"]: q for q in quotes}

    total = len(ASSET_POOL)
    for i, asset in enumerate(ASSET_POOL):
        data = fetch_asset_data(asset)
        if data and asset["code"] in quote_map:
            data["change_pct"] = quote_map[asset["code"]].get("change_pct")
        if data:
            result.append(data)
        if progress and (i + 1) % 5 == 0:
            print(f"   📊 [{i+1}/{total}] {asset['name']} OK")
    return result
