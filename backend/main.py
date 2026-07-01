"""
FastAPI backend for ETF Analysis Dashboard.
Serves both the API endpoints and the static frontend.
"""

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import sys

# Ensure backend module is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    ETF_POOL, _sina_code, get_all_etf_quotes, get_etf_ma,
    get_etf_kline, get_index_kline,
)
from signals import (
    get_dashboard, get_rotation_ranking, scan_all_etf_signals,
    scan_all_dca_signals, calc_ma_signal,
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    print("ETF Analyzer Backend started.")
    yield

app = FastAPI(
    title="ETF Analyzer",
    description="Free ETF analysis dashboard with momentum rotation, MA signals, and DCA enhancement.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Endpoints ────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ETF Analyzer"}


@app.get("/api/etf/pool")
async def etf_pool():
    """Return the ETF candidate pool metadata."""
    return {"pool": ETF_POOL, "count": len(ETF_POOL)}


@app.get("/api/etf/quotes")
async def etf_quotes():
    """Real-time quotes for all ETFs in the pool."""
    quotes = get_all_etf_quotes()
    return {"count": len(quotes), "quotes": quotes}


@app.get("/api/etf/kline/{etf_code:path}")
async def etf_kline(etf_code: str, days: int = Query(200, ge=20, le=500)):
    """K-line with moving averages for a single ETF."""
    data = get_etf_ma(etf_code, "daily", days)
    if data is None:
        return {"error": f"No data for {etf_code}", "code": etf_code}
    return data


@app.get("/api/signals/rotation")
async def rotation(top_n: int = Query(5, ge=1, le=15)):
    """ETF momentum rotation ranking."""
    ranking = get_rotation_ranking(top_n)
    return {"top_n": top_n, "ranking": ranking}


@app.get("/api/signals/ma")
async def ma_signals():
    """MA crossover signals for all ETFs."""
    signals = scan_all_etf_signals()
    return {"count": len(signals), "signals": signals}


@app.get("/api/signals/ma/{etf_code:path}")
async def ma_signal_single(etf_code: str):
    """MA signal for a single ETF."""
    signal = calc_ma_signal(etf_code)
    if signal is None:
        return {"error": f"No signal data for {etf_code}"}
    return signal


@app.get("/api/signals/dca")
async def dca_signals(amount: float = Query(5000, ge=100, le=100000)):
    """DCA enhancement signals for all ETFs."""
    signals = scan_all_dca_signals(amount)
    return {"count": len(signals), "base_amount": amount, "signals": signals}


@app.get("/api/market/state")
async def market_state():
    """Current market state (bull/bear/range)."""
    state = get_index_kline()
    return state or {"error": "Unable to determine market state"}


@app.get("/api/dashboard")
async def dashboard():
    """Unified dashboard: quotes + all signals + market state."""
    return get_dashboard()


# ── Static Frontend ──────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# Mount frontend static assets if any
assets_dir = os.path.join(FRONTEND_DIR, "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8765, reload=True)
