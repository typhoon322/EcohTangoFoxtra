"""
backtest_store.py — EcohTangoFoxtra v3.2
SQLite-backed historical data store for backtesting.
Stores: daily signal records, portfolio snapshots, trade log.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "backtest.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema() -> None:
    with _conn() as c:
        # Daily signal records — one row per (date, code)
        c.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                code        TEXT NOT NULL,
                name        TEXT,
                group_name  TEXT,
                price       REAL,
                ma5         REAL,
                ma20        REAL,
                ma60        REAL,
                ma120       REAL,
                macd        REAL,
                rsi         REAL,
                volatility  REAL,
                max_drawdown REAL,
                trend_score INTEGER,
                flow_score  INTEGER,
                risk_score  INTEGER,
                final_score REAL,
                tier        TEXT,
                action      TEXT,
                target_weight REAL,
                UNIQUE(date, code)
            )
        """)

        # Portfolio snapshots per date
        c.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT NOT NULL UNIQUE,
                cash          REAL,
                positions_value REAL,
                total_value   REAL,
                daily_pnl     REAL,
                daily_pnl_pct REAL,
                total_pnl_pct REAL,
                position_count INTEGER,
                regime        TEXT,
                regime_equity REAL
            )
        """)

        # Trade log
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                code        TEXT NOT NULL,
                name        TEXT,
                action      TEXT NOT NULL,
                price       REAL NOT NULL,
                shares      INTEGER,
                amount      REAL,
                total_value_before REAL,
                tier        TEXT,
                signal_score REAL
            )
        """)

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS ix_signals_date ON signals(date)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_snapshots_date ON snapshots(date)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_trades_date ON trades(date)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_signals_code ON signals(code)")


# ── Signal Records ──────────────────────────────────────────────────────────────

def save_signal_record(date: str, asset: dict) -> None:
    """Save one asset's daily signal (upsert)."""
    init_schema()
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO signals
            (date, code, name, group_name, price, ma5, ma20, ma60, ma120,
             macd, rsi, volatility, max_drawdown, trend_score, flow_score,
             risk_score, final_score, tier, action, target_weight)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            asset["code"],
            asset.get("name"),
            asset.get("group"),
            asset.get("price"),
            asset.get("ma5"),
            asset.get("ma20"),
            asset.get("ma60"),
            asset.get("ma120"),
            asset.get("macd"),
            asset.get("rsi"),
            asset.get("volatility"),
            asset.get("max_drawdown"),
            asset.get("trend_score"),
            asset.get("flow_score"),
            asset.get("risk_score"),
            asset.get("final_score"),
            asset.get("tier"),
            asset.get("action"),
            asset.get("target_weight"),
        ))


def save_signals_batch(date: str, assets: list[dict]) -> None:
    """Save all assets for a given date."""
    init_schema()
    with _conn() as c:
        rows = [
            (
                date, a["code"], a.get("name"), a.get("group"),
                a.get("price"), a.get("ma5"), a.get("ma20"), a.get("ma60"),
                a.get("ma120"), a.get("macd"), a.get("rsi"),
                a.get("volatility"), a.get("max_drawdown"),
                a.get("trend_score"), a.get("flow_score"),
                a.get("risk_score"), a.get("final_score"),
                a.get("tier"), a.get("action"), a.get("target_weight"),
            )
            for a in assets
        ]
        c.executemany("""
            INSERT OR REPLACE INTO signals
            (date, code, name, group_name, price, ma5, ma20, ma60, ma120,
             macd, rsi, volatility, max_drawdown, trend_score, flow_score,
             risk_score, final_score, tier, action, target_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def get_signals_for_date(date: str) -> list[dict]:
    """Load all signal records for a given date."""
    init_schema()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM signals WHERE date = ? ORDER BY final_score DESC",
            (date,)
        ).fetchall()
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in rows]


def get_signal_history(code: str, days: int = 365) -> list[dict]:
    """Get historical signal records for one asset."""
    init_schema()
    with _conn() as conn:
        cur = conn.execute("""
            SELECT date, price, trend_score, flow_score, risk_score, final_score, tier, action
            FROM signals
            WHERE code = ? AND date >= date('now', ?)
            ORDER BY date
        """, (code, f"-{days} days"))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


def get_dates_range(start_date: str, end_date: str) -> list[str]:
    """Get all dates in range that have signal records."""
    init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT DISTINCT date FROM signals
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (start_date, end_date)).fetchall()
        return [r[0] for r in rows]


# ── Snapshot Records ───────────────────────────────────────────────────────────

def save_snapshot(date: str, snap: dict, regime: dict = None) -> None:
    """Save a portfolio snapshot."""
    init_schema()
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO snapshots
            (date, cash, positions_value, total_value, daily_pnl, daily_pnl_pct,
             total_pnl_pct, position_count, regime, regime_equity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            snap.get("cash"),
            snap.get("positions_value"),
            snap.get("total_value"),
            snap.get("daily_pnl"),
            snap.get("daily_pnl_pct"),
            snap.get("total_pnl_pct"),
            snap.get("position_count"),
            regime.get("regime") if regime else None,
            regime.get("equity_allocation") if regime else None,
        ))


def get_snapshots(start_date: str = None, end_date: str = None) -> list[dict]:
    """Load portfolio snapshots in range."""
    init_schema()
    with _conn() as conn:
        if start_date and end_date:
            cur = conn.execute("""
                SELECT * FROM snapshots WHERE date >= ? AND date <= ? ORDER BY date
            """, (start_date, end_date))
        elif start_date:
            cur = conn.execute("""
                SELECT * FROM snapshots WHERE date >= ? ORDER BY date
            """, (start_date,))
        else:
            cur = conn.execute("SELECT * FROM snapshots ORDER BY date")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


# ── Trade Records ──────────────────────────────────────────────────────────────

def save_trade(trade: dict, date: str, total_value_before: float) -> None:
    """Save one trade."""
    init_schema()
    with _conn() as conn:
        conn.execute("""
            INSERT INTO trades
            (date, code, name, action, price, shares, amount,
             total_value_before, tier, signal_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            trade.get("code"),
            trade.get("name"),
            trade.get("action"),
            trade.get("price"),
            trade.get("shares"),
            trade.get("amount"),
            total_value_before,
            trade.get("tier"),
            trade.get("score"),
        ))


def get_trades(start_date: str = None, end_date: str = None) -> list[dict]:
    """Load trades in range."""
    init_schema()
    with _conn() as conn:
        if start_date and end_date:
            cur = conn.execute("""
                SELECT * FROM trades WHERE date >= ? AND date <= ? ORDER BY date
            """, (start_date, end_date))
        else:
            cur = conn.execute("SELECT * FROM trades ORDER BY date")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


# ── Price History ──────────────────────────────────────────────────────────────

def init_price_history_schema() -> None:
    """Create the price_history table for backfill."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                code        TEXT NOT NULL,
                name        TEXT,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                volume      REAL,
                ma5         REAL,
                ma20        REAL,
                ma60        REAL,
                ma120       REAL,
                macd        REAL,
                macd_signal REAL,
                macd_hist   REAL,
                rsi         REAL,
                UNIQUE(date, code)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS ix_ph_date ON price_history(date)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_ph_code ON price_history(code)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_ph_date_code ON price_history(date, code)")


def save_price_row(row: dict) -> None:
    """Save one daily OHLCV + indicators row."""
    init_price_history_schema()
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO price_history
            (date, code, name, open, high, low, close, volume,
             ma5, ma20, ma60, ma120, macd, macd_signal, macd_hist, rsi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["date"], row["code"], row.get("name"),
            row.get("open"), row.get("high"), row.get("low"), row.get("close"),
            row.get("volume"),
            row.get("ma5"), row.get("ma20"), row.get("ma60"), row.get("ma120"),
            row.get("macd"), row.get("macd_signal"), row.get("macd_hist"),
            row.get("rsi"),
        ))


def save_price_batch(rows: list[dict]) -> None:
    """Batch save price rows."""
    if not rows:
        return
    init_price_history_schema()
    with _conn() as c:
        c.executemany("""
            INSERT OR REPLACE INTO price_history
            (date, code, name, open, high, low, close, volume,
             ma5, ma20, ma60, ma120, macd, macd_signal, macd_hist, rsi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                r["date"], r["code"], r.get("name"),
                r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                r.get("volume"),
                r.get("ma5"), r.get("ma20"), r.get("ma60"), r.get("ma120"),
                r.get("macd"), r.get("macd_signal"), r.get("macd_hist"),
                r.get("rsi"),
            )
            for r in rows
        ])


def get_price_series(code: str) -> list[dict]:
    """Get full price series for one ETF, oldest first."""
    init_price_history_schema()
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM price_history WHERE code = ? ORDER BY date",
            (code,)
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


def get_prices_for_date(date: str) -> dict[str, dict]:
    """Get all ETF prices for a given date, keyed by code."""
    init_price_history_schema()
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM price_history WHERE date = ?",
            (date,)
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return {r[2]: dict(zip(cols, r)) for r in rows}  # index by code


def get_all_dates() -> list[str]:
    """Get all dates that have price data, sorted."""
    init_price_history_schema()
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT date FROM price_history ORDER BY date"
        ).fetchall()
        return [r[0] for r in rows]


def get_price_record_count() -> int:
    """Count total price_history rows."""
    init_price_history_schema()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]


# ── Benchmark helpers ───────────────────────────────────────────────────────────

def save_benchmark(date: str, code: str, price: float) -> None:
    """Store benchmark price (e.g. 510300 for HS300)."""
    init_schema()
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS benchmark (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                code TEXT NOT NULL,
                price REAL NOT NULL,
                UNIQUE(date, code)
            )
        """)
        c.execute("""
            INSERT OR REPLACE INTO benchmark (date, code, price) VALUES (?, ?, ?)
        """, (date, code, price))


def get_benchmark(code: str, days: int = 365) -> list[dict]:
    """Get benchmark price series."""
    init_schema()
    with _conn() as c:
        rows = c.execute("""
            SELECT date, price FROM benchmark
            WHERE code = ? AND date >= date('now', ?)
            ORDER BY date
        """, (code, f"-{days} days")).fetchall()
        return [{"date": r[0], "price": r[1]} for r in rows]


# ── Meta ───────────────────────────────────────────────────────────────────────

def get_record_count() -> dict:
    """Return record counts for each table."""
    init_schema()
    with _conn() as c:
        return {
            "signals":  c.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
            "snapshots": c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
            "trades":   c.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
            "dates":    c.execute("SELECT COUNT(DISTINCT date) FROM signals").fetchone()[0],
        }
