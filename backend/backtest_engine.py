"""
backtest_engine.py — EcohTangoFoxtra v3.2
Historical backtesting + Walk-Forward validation.
Frozen core: uses same signal_engine, portfolio_engine, paper_trading rules.
"""

import math
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

# Local imports (frozen core — DO NOT MODIFY)
sys.path.insert(0, os.path.dirname(__file__))
from data_engine import ASSET_POOL, fetch_kline_df, fetch_macro
from signal_engine import rate_scores
from market_regime import detect_regime
from rotation_engine import rank_assets
from portfolio_engine import build_portfolio
from backtest_store import (
    init_schema, save_signals_batch, save_snapshot, save_trade,
    get_snapshots, get_trades, get_dates_range,
    save_benchmark, get_benchmark, get_record_count,
)

INITIAL_CASH = 100_000.0

# ── Frozen Rules (v3.1 spec — DO NOT MODIFY) ──────────────────────────────────
MAX_POSITION_PCT = 0.25     # 单标的最大仓位 25%
MAX_DAILY_CHANGE = 0.10     # 单日变动上限 10%
MIN_CASH_PCT = 0.10         # 最低现金 10%


# ── Backtest Engine ────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Run historical simulation using the frozen strategy rules.
    Outputs: total return, max drawdown, Sharpe, win rate, benchmark comparison.
    """

    def __init__(self, start_date: str, end_date: str, benchmark_code: str = "510300"):
        self.start_date = start_date
        self.end_date = end_date
        self.benchmark_code = benchmark_code
        self.dates: list[str] = []
        self.equity_curve: list[float] = []
        self.benchmark_curve: list[float] = []
        self.trades: list[dict] = []
        self.regimes: list[dict] = []
        self.stats: Optional[dict] = None

    def run(self, dry: bool = False) -> dict:
        """Execute full backtest. Returns stats dict."""
        init_schema()

        if dry:
            return self._run_dry()
        return self._run_full()

    def _run_dry(self) -> dict:
        """Dry run: use already-stored signal records."""
        self.dates = get_dates_range(self.start_date, self.end_date)
        if not self.dates:
            return {"error": f"No stored signals for {self.start_date}–{self.end_date}"}

        cash = INITIAL_CASH
        equity_curve = [INITIAL_CASH]
        trades = []

        for date in self.dates:
            snap = get_snapshots(date, date)
            if snap:
                cash = snap[0].get("total_value", cash)
            equity_curve.append(cash)

        self.equity_curve = equity_curve[1:]  # drop initial
        self._compute_stats()
        return self.stats

    def _run_full(self) -> dict:
        """Full historical simulation from scratch."""
        # 1. Collect all historical data
        self.dates = self._collect_dates()
        if len(self.dates) < 20:
            return {"error": f"Only {len(self.dates)} trading days — need at least 20"}

        # 2. Build daily signal snapshots (store to DB)
        cash = INITIAL_CASH
        equity_curve = [INITIAL_CASH]
        benchmark_curve = [1.0]
        benchmark_base = None
        trades = []

        for i, date in enumerate(self.dates):
            # Fetch data up to this date (lookback)
            assets = self._fetch_assets_as_of(date)
            if not assets or len(assets) < 10:
                equity_curve.append(equity_curve[-1])
                continue

            # Score & rank
            scored = [rate_scores(a) for a in assets if a]
            scored = [s for s in scored if s.get("final_score")]

            # Simple percentile rank (frozen final_score formula)
            scores = [s["final_score"] for s in scored]
            mn, mx = min(scores), max(scores)
            rng = max(mx - mn, 1)
            for s in scored:
                s["final_score"] = 50 + (s["final_score"] - mn) / rng * 50

            # Regime
            macro = {"price": assets[0].get("price", 1) if assets else 1}
            regime = detect_regime(scored, macro)
            self.regimes.append({"date": date, "regime": regime})

            # Rank & decide
            ranked = rank_assets(scored)
            portfolio = build_portfolio(ranked, regime)

            # Build virtual portfolio state
            cash, new_trades = self._simulate_trades(
                date, cash, ranked, regime, portfolio, assets
            )
            trades.extend(new_trades)

            # Record snapshot
            snap = {
                "date": date,
                "cash": round(cash, 2),
                "positions_value": 0,
                "total_value": round(cash, 2),
                "daily_pnl": 0,
                "daily_pnl_pct": 0,
                "total_pnl_pct": round((cash / INITIAL_CASH - 1) * 100, 2),
                "position_count": 0,
            }
            save_snapshot(date, snap, regime)

            equity_curve.append(cash)

            # Benchmark
            bm = self._fetch_benchmark_price(date)
            if bm:
                if benchmark_base is None:
                    benchmark_base = bm
                benchmark_curve.append(bm / benchmark_base)

        self.equity_curve = equity_curve[1:]
        self.benchmark_curve = benchmark_curve[1:]
        self.trades = trades
        self._compute_stats()
        return self.stats

    def _collect_dates(self) -> list[str]:
        """Collect trading dates available in DB or generate from calendar."""
        stored = get_dates_range(self.start_date, self.end_date)
        if stored:
            return stored
        # Generate every trading day (weekdays only)
        dates = []
        d = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        while d <= end:
            if d.weekday() < 5:  # Mon–Fri
                dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        return dates

    def _fetch_assets_as_of(self, date: str) -> list[dict]:
        """Fetch asset data as if we only know history up to this date."""
        assets = []
        for asset_def in ASSET_POOL:
            try:
                df = fetch_kline_df(asset_def["sina"], 250)
                if df is None or len(df) < 60:
                    continue
                # Only use data up to this date
                cutoff = datetime.strptime(date, "%Y-%m-%d")
                df = df[df["date"] <= cutoff]
                if len(df) < 60:
                    continue

                close = df["close"].values
                high = df["high"].values
                low = df["low"].values
                vol = df["volume"].values

                price_now = float(close[-1])
                ma5 = float(pd_Series(close).rolling(5).mean().iloc[-1])
                ma20 = float(pd_Series(close).rolling(20).mean().iloc[-1])
                ma60 = float(pd_Series(close).rolling(60).mean().iloc[-1])
                ma120 = float(pd_Series(close).rolling(120).mean().iloc[-1]) if len(close) >= 120 else ma60

                dif = pd_Series(close).ewm(span=12, adjust=False).mean() - pd_Series(close).ewm(span=26, adjust=False).mean()
                dea = dif.ewm(span=9, adjust=False).mean()
                macd_val = float((dif - dea).iloc[-1]) * 2

                delta_s = pd_Series(close).diff()
                gain = delta_s.clip(lower=0).rolling(14).mean()
                loss = (-delta_s.clip(upper=0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                rsi = float(100 - (100 / (1 + rs.iloc[-1])))

                vol_series = pd_Series(vol)
                vol_ma20 = float(vol_series.tail(20).mean())
                vol_ma60 = float(vol_series.tail(60).mean()) if len(vol) >= 60 else vol_ma20
                vol_ratio = vol[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
                vol_expanding = vol_ma20 > vol_ma60 * 1.1

                peak_s = pd_Series(close).tail(120).expanding().max()
                dd = (pd_Series(close).tail(120).values / peak_s.values - 1)
                max_drawdown = float(dd.min())

                above_ma5 = close > ma5
                streak = 0
                for v in above_ma5[::-1]:
                    if v: streak += 1
                    else: break

                rets = pd_Series(close).pct_change().dropna().tail(20)
                volatility = float(rets.std() * math.sqrt(252)) if len(rets) >= 5 else 0.2

                assets.append({
                    "code": asset_def["code"],
                    "name": asset_def["name"],
                    "group": asset_def["group"],
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
                })
            except Exception:
                continue
        return assets

    def _fetch_benchmark_price(self, date: str) -> Optional[float]:
        """Fetch benchmark close price as of date."""
        try:
            bench_def = next((a for a in ASSET_POOL if a["code"] == self.benchmark_code), None)
            if not bench_def:
                return None
            df = fetch_kline_df(bench_def["sina"], 250)
            if df is None:
                return None
            cutoff = datetime.strptime(date, "%Y-%m-%d")
            df = df[df["date"] <= cutoff]
            return float(df["close"].iloc[-1]) if len(df) > 0 else None
        except Exception:
            return None

    def _simulate_trades(
        self, date: str, cash: float,
        ranked: list[dict], regime: dict,
        portfolio: dict, assets: list[dict],
    ) -> tuple[float, list[dict]]:
        """Simulate one day of trades using frozen v3.1 rules."""
        new_trades = []
        total_value = cash  # simplified: no open positions in backtest

        equity = regime.get("equity_allocation", 0.6)
        target_equity_value = total_value * equity
        min_cash = total_value * MIN_CASH_PCT

        price_map = {a["code"]: a["price"] for a in assets}

        # Top 6 core positions
        core = [a for a in ranked if a.get("tier") == "core"][:6]
        watch = [a for a in ranked if a.get("tier") == "watch"][:4]
        reduce_pool = [a for a in ranked if a.get("tier") == "reduce"][:3]

        # BUY core
        if core and cash > min_cash:
            per_asset = min(target_equity_value / len(core), cash * 0.15)
            for a in core:
                price = price_map.get(a["code"])
                if not price or per_asset < price * 100:
                    continue
                max_shares = int(per_asset / price / 100) * 100
                max_cost = max_shares * price
                if max_cost > cash * MAX_DAILY_CHANGE:  # single-day limit
                    max_shares = int(cash * MAX_DAILY_CHANGE / price / 100) * 100
                if max_shares >= 100 and max_shares * price <= cash:
                    cash -= max_shares * price
                    new_trades.append({
                        "date": date, "code": a["code"], "name": a["name"],
                        "action": "BUY", "price": price,
                        "shares": max_shares, "amount": max_shares * price,
                        "tier": "core", "score": a.get("final_score", 50),
                    })

        # REDUCE bottom 3
        for a in reduce_pool:
            # No position in backtest dry-run, but log the signal
            new_trades.append({
                "date": date, "code": a["code"], "name": a["name"],
                "action": "REDUCE", "price": price_map.get(a["code"]),
                "shares": 0, "amount": 0,
                "tier": "reduce", "score": a.get("final_score", 50),
            })

        return cash, new_trades

    def _compute_stats(self) -> None:
        """Compute all backtest metrics."""
        curve = np.array(self.equity_curve)
        if len(curve) < 2:
            self.stats = {"error": "Not enough data points"}
            return

        # Returns
        returns = np.diff(curve) / curve[:-1]
        total_return = (curve[-1] / curve[0] - 1) * 100

        # Max drawdown
        peak = np.maximum.accumulate(curve)
        drawdowns = (curve - peak) / peak * 100
        max_drawdown = float(drawdowns.min())

        # Sharpe (annualized, risk-free = 0 for simplicity)
        daily_rf = 0.0
        excess = returns - daily_rf
        if np.std(excess) > 1e-9:
            sharpe = float(np.mean(excess) / np.std(excess) * math.sqrt(252))
        else:
            sharpe = 0.0

        # Win rate
        win_rate = float(np.sum(returns > 0) / len(returns) * 100) if len(returns) > 0 else 0

        # Benchmark comparison
        bm_return = 0.0
        if len(self.benchmark_curve) >= 2:
            bm_return = (self.benchmark_curve[-1] / self.benchmark_curve[0] - 1) * 100
        alpha = total_return - bm_return

        # Days / years
        years = len(curve) / 252
        cagr = float((curve[-1] / curve[0]) ** (1 / max(years, 0.01)) - 1) * 100

        # Volatility
        ann_vol = float(np.std(returns) * math.sqrt(252) * 100)

        # Sortino
        downside_returns = returns[returns < 0]
        downside_std = float(np.std(downside_returns)) if len(downside_returns) > 1 else 1e-9
        sortino = float(np.mean(returns) / downside_std * math.sqrt(252)) if downside_std > 1e-9 else 0

        self.stats = {
            "start_date": self.dates[0] if self.dates else self.start_date,
            "end_date": self.dates[-1] if self.dates else self.end_date,
            "trading_days": len(curve),
            "initial_value": float(curve[0]),
            "final_value": float(curve[-1]),
            "total_return_pct": round(total_return, 2),
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "annual_volatility_pct": round(ann_vol, 2),
            "win_rate_pct": round(win_rate, 1),
            "benchmark_return_pct": round(bm_return, 2),
            "alpha_pct": round(alpha, 2),
            "total_trades": len(self.trades),
        }


# ── Fast Backtest from price_history DB ───────────────────────────────────────

def run_backtest_from_db(
    start_date: str = None,
    end_date: str = None,
    benchmark_code: str = "510300",
) -> dict:
    """
    高效回测：从 price_history 表读取数据，无需实时拉 Sina。
    每天计算信号 + 模拟交易，输出完整指标。
    """
    import pandas as pd
    from backtest_store import (
        get_all_dates, get_prices_for_date,
        save_signals_batch, save_snapshot, init_schema,
    )

    # ── 1. 加载日期列表 ──
    all_dates = get_all_dates()
    if not all_dates:
        return {"error": "price_history 为空，请先运行 --backfill"}

    # 过滤到回测区间
    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d <= end_date]

    if len(all_dates) < 30:
        return {"error": f"回测区间仅 {len(all_dates)} 天，需要至少 30 天"}

    print(f"\n📊 回测区间: {all_dates[0]} → {all_dates[-1]} ({len(all_dates)} 交易日)")

    # ── 2. 预加载所有价格数据 ──
    # price_series: {code: {date: row}}  方便快速查询
    from backtest_store import get_price_series, init_price_history_schema
    init_price_history_schema()

    from data_engine import ASSET_POOL
    price_series: dict[str, dict[str, dict]] = {}
    for etf in ASSET_POOL:
        code = etf["code"]
        rows = get_price_series(code)
        price_series[code] = {r["date"]: r for r in rows}

    bench_rows = price_series.get(benchmark_code, {})

    # ── 3. 回测主循环 ──
    cash = INITIAL_CASH
    # positions: {code: {"shares": int, "avg_cost": float}}
    positions: dict[str, dict] = {}

    equity_curve: list[float] = []
    bench_curve: list[float] = []
    trades_log: list[dict] = []
    regimes_log: list[dict] = []

    bench_base: float | None = None

    for i, date in enumerate(all_dates):
        # 收集当日的所有ETF价格
        prices_today: dict[str, dict] = {}
        for code in price_series:
            if date in price_series[code]:
                prices_today[code] = price_series[code][date]

        if len(prices_today) < 10:
            # 数据不足，跳过
            equity_curve.append(equity_curve[-1] if equity_curve else cash)
            continue

        # 构建 assets 列表（用于 signal_engine）
        assets = []
        for code, row in prices_today.items():
            close = row.get("close")
            if close is None:
                continue
            etf = next((e for e in ASSET_POOL if e["code"] == code), None)
            if not etf:
                continue

            # 仓位市值
            pos = positions.get(code)
            unrealized = 0.0
            if pos:
                unrealized = (close - pos["avg_cost"]) * pos["shares"]

            assets.append({
                "code": code,
                "name": etf.get("name", code),
                "group": etf.get("group", "other"),
                "price": float(close),
                "ma5": float(row["ma5"]) if row.get("ma5") else None,
                "ma20": float(row["ma20"]) if row.get("ma20") else None,
                "ma60": float(row["ma60"]) if row.get("ma60") else None,
                "ma120": float(row["ma120"]) if row.get("ma120") else None,
                "macd": float(row["macd"]) if row.get("macd") else 0.0,
                "rsi": float(row["rsi"]) if row.get("rsi") else 50.0,
                "volatility": 0.15,   # 历史波动率已在ma60窗口隐含
                "max_drawdown": 0.0,
                "vol_ratio": 1.0,
                "vol_expanding": False,
                "up_streak": 0,
                "unrealized": unrealized,
            })

        if len(assets) < 10:
            equity_curve.append(equity_curve[-1] if equity_curve else cash)
            continue

        # ── 评分 ──
        scored = []
        for a in assets:
            try:
                s = rate_scores(a)
                if s:
                    scored.append(s)
            except Exception:
                continue

        if not scored:
            equity_curve.append(equity_curve[-1] if equity_curve else cash)
            continue

        # ── 市场状态 ──
        macro = {"price": assets[0]["price"] if assets else 1}
        try:
            regime = detect_regime(scored, macro)
        except Exception:
            regime = {"regime": "rotation", "equity_allocation": 0.6}

        # ── 排序 + 决策 ──
        try:
            ranked = rank_assets(scored)
        except Exception:
            ranked = sorted(scored, key=lambda x: x.get("final_score", 0), reverse=True)
            for i2, r in enumerate(ranked):
                r["tier"] = "core" if i2 < 3 else "watch" if i2 < 8 else "reduce"

        # ── 计算总市值（含持仓）──
        total_value = cash + sum(
            positions.get(a["code"], {}).get("shares", 0) * a["price"]
            for a in assets if a["code"] in positions
        )

        equity_alloc = regime.get("equity_allocation", 0.6)
        target_equity = total_value * equity_alloc
        min_cash = total_value * MIN_CASH_PCT
        daily_chg_limit = total_value * MAX_DAILY_CHANGE

        # ── 执行交易（冻结规则）──
        price_map = {a["code"]: a["price"] for a in assets}

        # BUY: core 标的（top ranked）
        core = [r for r in ranked if r.get("tier") in ("core", "watch")][:6]
        for a in core:
            code = a["code"]
            price = price_map.get(code)
            if not price or code in positions:
                continue
            # 目标仓位：equity 部分均分
            target_val = target_equity / len(core) if core else 0
            invest = min(target_val, daily_chg_limit, cash - min_cash)
            if invest < price * 100:
                continue
            shares = int(invest / price / 100) * 100
            cost = shares * price
            if shares >= 100 and cost <= cash:
                positions[code] = {"name": a.get("name", code), "shares": shares, "avg_cost": price}
                cash -= cost
                trades_log.append({
                    "date": date, "code": code, "name": a.get("name", code),
                    "action": "BUY", "price": price, "shares": shares,
                    "amount": cost, "tier": a.get("tier"), "score": a.get("final_score"),
                })

        # REDUCE: bottom ranked
        reduce_list = [r for r in ranked if r.get("tier") == "reduce"][:3]
        for a in reduce_list:
            code = a["code"]
            if code not in positions:
                continue
            pos = positions[code]
            price = price_map.get(code)
            if not price:
                continue
            sell_shares = int(pos["shares"] * 0.5 / 100) * 100
            if sell_shares < 100:
                # < 100股 → 清仓
                proceeds = pos["shares"] * price
                cash += proceeds
                trades_log.append({
                    "date": date, "code": code, "name": pos["name"],
                    "action": "REDUCE", "price": price,
                    "shares": pos["shares"], "amount": proceeds,
                    "tier": "reduce", "score": a.get("final_score"),
                })
                del positions[code]
            else:
                proceeds = sell_shares * price
                pos["shares"] -= sell_shares
                cash += proceeds
                trades_log.append({
                    "date": date, "code": code, "name": pos["name"],
                    "action": "REDUCE", "price": price,
                    "shares": sell_shares, "amount": proceeds,
                    "tier": "reduce", "score": a.get("final_score"),
                })

        # ── 记录快照 ──
        pos_value = sum(p["shares"] * price_map.get(code, p["avg_cost"]) for code, p in positions.items())
        daily_value = cash + pos_value
        equity_curve.append(daily_value)

        # 基准曲线
        if benchmark_code in prices_today:
            bm_close = float(prices_today[benchmark_code]["close"])
            if bench_base is None:
                bench_base = bm_close
            bench_curve.append(bm_close / bench_base)

        # 保存快照
        snap = {
            "cash": round(cash, 2),
            "positions_value": round(pos_value, 2),
            "total_value": round(daily_value, 2),
            "daily_pnl": 0,
            "daily_pnl_pct": 0,
            "total_pnl_pct": round((daily_value / INITIAL_CASH - 1) * 100, 2),
            "position_count": len(positions),
        }
        save_snapshot(date, snap, regime)
        regimes_log.append({"date": date, "regime": regime})

        # 进度
        if (i + 1) % 100 == 0:
            pct = (i + 1) / len(all_dates) * 100
            print(f"   进度 {pct:.0f}% ({i+1}/{len(all_dates)} 天) ...")

    # ── 4. 计算统计指标 ──
    curve = np.array(equity_curve)
    returns = np.diff(curve) / curve[:-1] if len(curve) > 1 else np.array([])

    total_return = float((curve[-1] / curve[0] - 1) * 100) if curve[-1] > 0 else 0
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak * 100
    max_dd = float(dd.min())
    years = len(curve) / 252
    cagr = float((curve[-1] / curve[0]) ** (1 / max(years, 0.01)) - 1) * 100
    ann_vol = float(np.std(returns) * math.sqrt(252) * 100) if len(returns) > 0 else 0

    excess = returns  # rf=0
    sharpe = float(np.mean(excess) / np.std(excess) * math.sqrt(252)) if np.std(excess) > 1e-9 else 0
    downside = returns[returns < 0]
    sortino = float(np.mean(excess) / np.std(downside) * math.sqrt(252)) if len(downside) > 1 else 0

    win_rate = float(np.sum(returns > 0) / max(len(returns), 1) * 100)
    bm_ret = float((bench_curve[-1] / bench_curve[0] - 1) * 100) if len(bench_curve) > 1 else 0

    # Save benchmark curve
    from backtest_store import save_benchmark
    for i, date in enumerate(all_dates):
        if benchmark_code in price_series and date in price_series[benchmark_code]:
            save_benchmark(date, benchmark_code, float(price_series[benchmark_code][date]["close"]))

    # Regime summary
    from collections import Counter
    regime_counts = Counter(r["regime"].get("regime", "rotation") for r in regimes_log)

    stats = {
        "start_date": all_dates[0],
        "end_date": all_dates[-1],
        "trading_days": len(curve),
        "initial_value": float(curve[0]),
        "final_value": float(curve[-1]),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "annual_volatility_pct": round(ann_vol, 2),
        "win_rate_pct": round(win_rate, 1),
        "benchmark_return_pct": round(bm_ret, 2),
        "alpha_pct": round(total_return - bm_ret, 2),
        "total_trades": len(trades_log),
        "position_days": sum(1 for v in equity_curve if v > cash),
        "regime_distribution": dict(regime_counts),
        "equity_curve": [round(v, 2) for v in equity_curve],
    }

    return stats


# ── CLI wrapper for run_backtest ───────────────────────────────────────────────

def run_backtest() -> dict:
    """CLI entry point: auto-detect date range from price_history."""
    from backtest_store import get_all_dates, get_price_record_count
    dates = get_all_dates()
    n = get_price_record_count()
    if n == 0:
        return {"error": "数据库为空，请先运行: python main_lite.py --backfill"}
    if len(dates) < 30:
        return {"error": f"仅 {len(dates)} 个交易日，需要至少 30 天"}
    # Use full available range
    return run_backtest_from_db(start_date=dates[0], end_date=dates[-1])


def format_backtest_report(stats: dict) -> str:
    if "error" in stats:
        return f"❌ {stats['error']}"
    reg_dist = stats.get("regime_distribution", {})
    reg_str = " | ".join(f"{k}:{v}天" for k, v in reg_dist.items())
    return f"""
  📊 回测报告  {stats['start_date']} → {stats['end_date']}
  ─────────────────────────────────────────
  总收益率    {stats['total_return_pct']:+.2f}%
  年化收益    {stats['cagr_pct']:+.2f}%   (CAGR)
  基准收益    {stats['benchmark_return_pct']:+.2f}%   (沪深300)
  Alpha      {stats['alpha_pct']:+.2f}%
  ─────────────────────────────────────────
  最大回撤    {stats['max_drawdown_pct']:.2f}%
  年化波动    {stats['annual_volatility_pct']:.2f}%
  Sharpe     {stats['sharpe_ratio']:.2f}
  Sortino    {stats['sortino_ratio']:.2f}
  胜率        {stats['win_rate_pct']:.1f}%
  ─────────────────────────────────────────
  交易次数    {stats['total_trades']}
  持仓天数    {stats['position_days']} / {stats['trading_days']}
  市场状态    {reg_str or 'N/A'}
  ─────────────────────────────────────────
  初始资金    ¥{stats['initial_value']:,.0f}
  最终资金    ¥{stats['final_value']:,.0f}
"""


def run_walkforward() -> dict:
    """Run walk-forward from price_history DB."""
    from backtest_store import get_all_dates
    dates = get_all_dates()
    if len(dates) < 300:
        return {"error": f"Walk-Forward 需要至少 300 天数据，当前 {len(dates)} 天"}

    total_start = dates[0]
    total_end = dates[-1]

    # Windows: 2yr train / 3m test / 1m step
    wf = WalkForwardEngine(total_start, total_end, train_days=504, test_days=63, step_days=21)
    result = wf.run()

    # Compute summary
    windows_data = wf.results
    if not windows_data:
        return {"error": "无有效窗口", "windows": []}

    test_rets = [w["test_return_pct"] for w in windows_data]
    stable = sum(1 for r in test_rets if r > 0)
    consistency = (stable / len(windows_data)) * 10 if windows_data else 0
    overfit = "LOW" if consistency >= 7 else "MEDIUM" if consistency >= 5 else "HIGH"

    result.update({
        "consistency_score": round(consistency, 1),
        "stable_periods": stable,
        "overfit_risk": overfit,
        "avg_test_return_pct": round(sum(test_rets) / len(test_rets), 2),
    })
    return result


def format_wf_report(wf_result: dict) -> str:
    if "error" in wf_result:
        return f"❌ {wf_result['error']}"
    windows = wf_result.get("windows", [])
    if not windows:
        return "❌ 无有效窗口"
    avg = wf_result.get("avg_test_return_pct", 0)
    stable = wf_result.get("stable_periods", 0)
    consistency = wf_result.get("consistency_score", 0)
    overfit = wf_result.get("overfit_risk", "N/A")
    return f"""
  📊 Walk-Forward 验证  ({len(windows)} 个窗口)
  ─────────────────────────────────────────
  一致性评分  {consistency:.1f} / 10
  稳定周期    {stable}/{len(windows)}
  过拟合风险  {overfit}
  ─────────────────────────────────────────
  各窗口结果:
""" + "\n".join(
        f"  [{w['test_start']}→{w['test_end']}] "
        f"Train:{w['train_return_pct']:+.1f}% "
        f"Test:{w['test_return_pct']:+.1f}% "
        f"Alpha:{w['test_alpha_pct']:+.1f}%"
        for w in windows
    )


# ── Walk-Forward Engine ────────────────────────────────────────────────────────

class WalkForwardEngine:
    """
    Rolling window validation.
    Train period → Test period → Next window.
    Outputs: Consistency Score, overfit risk, stable periods.
    """

    def __init__(
        self,
        total_start: str,
        total_end: str,
        train_days: int = 504,   # ~2 years
        test_days: int = 63,      # ~3 months
        step_days: int = 21,      # ~1 month
    ):
        self.total_start = total_start
        self.total_end = total_end
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.results: list[dict] = []
        self.overall: Optional[dict] = None

    def run(self) -> dict:
        """Run full walk-forward analysis using price_history DB."""
        d = datetime.strptime(self.total_start, "%Y-%m-%d")
        end = datetime.strptime(self.total_end, "%Y-%m-%d")
        train_end = d + timedelta(days=self.train_days)
        test_end = train_end + timedelta(days=self.test_days)

        windows = 0
        stable = 0

        while test_end <= end:
            train_start_str = d.strftime("%Y-%m-%d")
            train_end_str = train_end.strftime("%Y-%m-%d")
            test_start_str = train_end.strftime("%Y-%m-%d")
            test_end_str = test_end.strftime("%Y-%m-%d")

            # Train: backtest on train window (use DB-backed version)
            train_stats = run_backtest_from_db(train_start_str, train_end_str)

            # Test: backtest on test window
            test_stats = run_backtest_from_db(test_start_str, test_end_str)

            if "error" not in train_stats and "error" not in test_stats:
                windows += 1
                # A stable window: test return > 0
                if test_stats.get("total_return_pct", 0) > 0:
                    stable += 1

                self.results.append({
                    "train_start": train_start_str,
                    "train_end": train_end_str,
                    "test_start": test_start_str,
                    "test_end": test_end_str,
                    "train_return_pct": train_stats.get("total_return_pct", 0),
                    "test_return_pct": test_stats.get("total_return_pct", 0),
                    "test_alpha_pct": test_stats.get("alpha_pct", 0),
                    "train_sharpe": train_stats.get("sharpe_ratio"),
                    "test_sharpe": test_stats.get("sharpe_ratio"),
                    "test_max_dd": test_stats.get("max_drawdown_pct"),
                    "test_win_rate": test_stats.get("win_rate_pct"),
                    "stable": test_stats.get("total_return_pct", 0) > 0,
                })

            d += timedelta(days=self.step_days)
            train_end = d + timedelta(days=self.train_days)
            test_end = train_end + timedelta(days=self.test_days)

        if windows == 0:
            return {"error": "No valid windows — check date range"}

        stable_ratio = stable / windows
        consistency = round(stable_ratio * 10, 1)

        # Overfit: train sharpe >> test sharpe consistently
        overfit_score = 0
        for r in self.results:
            diff = (r.get("train_sharpe") or 0) - (r.get("test_sharpe") or 0)
            if diff > 1.0:
                overfit_score += 1

        overfit_risk = "HIGH" if overfit_score >= windows * 0.6 else \
                       "MEDIUM" if overfit_score >= windows * 0.3 else "LOW"

        avg_test_return = round(
            sum(r["test_return_pct"] for r in self.results) / len(self.results), 2
        )
        avg_test_sharpe = round(
            sum(r["test_sharpe"] for r in self.results) / len(self.results), 2
        )

        self.overall = {
            "windows": windows,
            "stable_periods": stable,
            "consistency_score": consistency,
            "overfit_risk": overfit_risk,
            "avg_test_return_pct": avg_test_return,
            "avg_test_sharpe": avg_test_sharpe,
            "periods_detail": self.results,
        }
        return self.overall


# ── Helper (avoid pandas import conflict) ─────────────────────────────────────

def pd_Series(data):
    """Minimal pd.Series replacement using builtins."""
    return _PandasLike(data)


class _PandasLike:
    """Lightweight pandas-like wrapper using numpy for rolling operations."""
    def __init__(self, data):
        self._data = np.array(data, dtype=float)

    def rolling(self, window: int):
        return _Rolling(self._data, window)

    def ewm(self, span: int, adjust: bool = False):
        alpha = 2.0 / (span + 1)
        result = [self._data[0]]
        for v in self._data[1:]:
            result.append(alpha * v + (1 - alpha) * result[-1])
        return _PandasLike(np.array(result))

    def diff(self):
        return _PandasLike(np.diff(self._data))

    def clip(self, lower=None, upper=None):
        data = self._data.copy()
        if lower is not None:
            data = np.maximum(data, lower)
        if upper is not None:
            data = np.minimum(data, upper)
        return _PandasLike(data)

    def pct_change(self):
        returns = np.diff(self._data) / self._data[:-1]
        return _PandasLike(np.concatenate([[0], returns]))

    def tail(self, n: int):
        return _PandasLike(self._data[-n:])

    def expanding(self):
        return _Expanding(self._data)

    @property
    def iloc(self):
        return _ILoc(self._data)

    def values(self):
        return self._data

    def mean(self):
        return float(np.nanmean(self._data))

    def std(self):
        return float(np.nanstd(self._data))

    def sum(self):
        return float(np.nansum(self._data))

    def __getitem__(self, key):
        result = self._data[key]
        return float(result) if np.isscalar(result) else result


class _Rolling:
    def __init__(self, data, window: int):
        self._data = data
        self._w = window

    def mean(self):
        n = len(self._data)
        result = np.full(n, np.nan)
        for i in range(self._w - 1, n):
            result[i] = float(np.mean(self._data[i - self._w + 1:i + 1]))
        return _PandasLike(result)

    def max(self):
        n = len(self._data)
        result = np.full(n, np.nan)
        for i in range(self._w - 1, n):
            result[i] = float(np.max(self._data[i - self._w + 1:i + 1]))
        return _PandasLike(result)


class _Expanding:
    def __init__(self, data):
        self._data = data

    def max(self):
        n = len(self._data)
        result = np.full(n, np.nan)
        cur = self._data[0]
        for i in range(n):
            cur = max(cur, self._data[i])
            result[i] = cur
        return _PandasLike(result)


class _ILoc:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        result = self._data[key]
        return float(result) if np.isscalar(result) else result


# ── CLI helper ─────────────────────────────────────────────────────────────────

def run_backtest(
    start: str = None,
    end: str = None,
    benchmark: str = "510300",
    dry: bool = True,
) -> dict:
    """One-command backtest run."""
    if start is None:
        # Default: last 1 year
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    be = BacktestEngine(start, end, benchmark)
    return be.run(dry=dry)


def run_walkforward(
    start: str = None,
    end: str = None,
    train_days: int = 504,
    test_days: int = 63,
) -> dict:
    """One-command walk-forward run."""
    if start is None:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=900)).strftime("%Y-%m-%d")

    wf = WalkForwardEngine(start, end, train_days, test_days)
    return wf.run()


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_backtest_report(stats: dict) -> str:
    """Format backtest stats as readable text."""
    if "error" in stats:
        return f"❌ Backtest error: {stats['error']}"

    lines = [
        "📊 Backtest Report",
        f"  Period: {stats.get('start_date')} → {stats.get('end_date')} ({stats.get('trading_days')} days)",
        f"  Initial: ¥{stats.get('initial_value'):,.0f}  Final: ¥{stats.get('final_value'):,.0f}",
        f"",
        f"  Total Return:    {'+' if stats.get('total_return_pct', 0) >= 0 else ''}{stats.get('total_return_pct')}%",
        f"  CAGR:            {'+' if stats.get('cagr_pct', 0) >= 0 else ''}{stats.get('cagr_pct')}%",
        f"  Benchmark:       {'+' if stats.get('benchmark_return_pct', 0) >= 0 else ''}{stats.get('benchmark_return_pct')}%",
        f"  Alpha:           {'+' if stats.get('alpha_pct', 0) >= 0 else ''}{stats.get('alpha_pct')}%",
        f"",
        f"  Max Drawdown:    {stats.get('max_drawdown_pct')}%",
        f"  Sharpe Ratio:    {stats.get('sharpe_ratio')}",
        f"  Sortino Ratio:   {stats.get('sortino_ratio')}",
        f"  Ann. Volatility: {stats.get('annual_volatility_pct')}%",
        f"  Win Rate:        {stats.get('win_rate_pct')}%",
        f"  Total Trades:    {stats.get('total_trades')}",
    ]
    return "\n".join(lines)


def format_wf_report(wf: dict) -> str:
    """Format walk-forward results."""
    if "error" in wf:
        return f"❌ Walk-Forward error: {wf['error']}"

    risk_color = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(wf.get("overfit_risk", ""), "⚪")
    lines = [
        "🔄 Walk-Forward Report",
        f"  Windows:         {wf['windows']}",
        f"  Stable Periods:  {wf['stable_periods']}/{wf['windows']}",
        f"  Consistency:     {wf['consistency_score']} / 10  {'✅' if wf['consistency_score'] >= 7 else '⚠️'}",
        f"  Overfit Risk:    {risk_color} {wf['overfit_risk']}",
        f"  Avg Test Return: {'+' if wf.get('avg_test_return_pct', 0) >= 0 else ''}{wf.get('avg_test_return_pct')}%",
        f"  Avg Test Sharpe: {wf.get('avg_test_sharpe')}",
    ]
    return "\n".join(lines)
