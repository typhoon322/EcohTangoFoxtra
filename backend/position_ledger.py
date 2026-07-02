"""
position_ledger.py — 持仓账本（手动交易录入）

写入 backend/paper_state.json，与模拟盘共用同一持仓格式。
不修改 paper_trading.py 封版逻辑，供真实/手动交易同步使用。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_state.json")
TRADE_LOG_FILE = os.path.join(os.path.dirname(__file__), "manual_trades.jsonl")


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "initialized": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "initial_cash": 100_000.0,
        "cash": 100_000.0,
        "positions": {},
        "daily_pnl": 0.0,
        "total_pnl_pct": 0.0,
        "history": [],
    }


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _append_trade_log(record: dict) -> None:
    record["recorded_at"] = datetime.now().isoformat(timespec="seconds")
    with open(TRADE_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _resolve_name(code: str, name: str = "") -> str:
    if name:
        return name
    try:
        from data_engine import ASSET_POOL
        for a in ASSET_POOL:
            if a["code"] == code:
                return a["name"]
    except Exception:
        pass
    return code


def record_buy(
    code: str,
    shares: int,
    price: float,
    name: str = "",
    fee: float = 0.0,
) -> dict:
    """录入买入（整手 100 股）。"""
    if shares <= 0 or shares % 100 != 0:
        raise ValueError("股数须为正整数且为 100 的整数倍")
    if price <= 0:
        raise ValueError("价格须 > 0")

    state = _load_state()
    cost = shares * price + fee
    if cost > state["cash"]:
        raise ValueError(f"现金不足: 需要 ¥{cost:.2f}, 可用 ¥{state['cash']:.2f}")

    name = _resolve_name(code, name)
    pos = state["positions"].get(code)

    if pos is None:
        state["positions"][code] = {
            "name": name,
            "shares": shares,
            "avg_cost": round(price, 4),
            "current_price": round(price, 4),
            "unrealized": 0.0,
        }
    else:
        total_shares = pos["shares"] + shares
        total_cost = pos["shares"] * pos["avg_cost"] + shares * price
        pos["shares"] = total_shares
        pos["avg_cost"] = round(total_cost / total_shares, 4)
        pos["current_price"] = round(price, 4)
        pos["name"] = name

    state["cash"] = round(state["cash"] - cost, 2)
    _save_state(state)

    rec = {
        "action": "BUY", "code": code, "name": name,
        "shares": shares, "price": price, "fee": fee, "amount": -cost,
    }
    _append_trade_log(rec)
    return {"success": True, "trade": rec, "cash": state["cash"]}


def record_sell(
    code: str,
    shares: int,
    price: float,
    fee: float = 0.0,
) -> dict:
    """录入卖出。"""
    if shares <= 0 or shares % 100 != 0:
        raise ValueError("股数须为正整数且为 100 的整数倍")
    if price <= 0:
        raise ValueError("价格须 > 0")

    state = _load_state()
    pos = state["positions"].get(code)
    if not pos or pos["shares"] < shares:
        held = pos["shares"] if pos else 0
        raise ValueError(f"持仓不足: 持有 {held} 股, 欲卖 {shares} 股")

    proceeds = shares * price - fee
    pos["shares"] -= shares
    pos["current_price"] = round(price, 4)
    name = pos["name"]

    if pos["shares"] == 0:
        del state["positions"][code]

    state["cash"] = round(state["cash"] + proceeds, 2)
    _save_state(state)

    rec = {
        "action": "SELL", "code": code, "name": name,
        "shares": shares, "price": price, "fee": fee, "amount": proceeds,
    }
    _append_trade_log(rec)
    return {"success": True, "trade": rec, "cash": state["cash"]}


def set_cash(amount: float) -> dict:
    """设置当前现金余额（对账用）。"""
    if amount < 0:
        raise ValueError("现金不能为负")
    state = _load_state()
    state["cash"] = round(amount, 2)
    _save_state(state)
    _append_trade_log({"action": "SET_CASH", "amount": amount})
    return {"success": True, "cash": state["cash"]}


def list_positions(prices: dict[str, float] | None = None) -> dict:
    """列出当前持仓与权重。"""
    state = _load_state()
    positions = state["positions"]
    if not positions:
        return {"cash": state["cash"], "positions": [], "total_value": state["cash"]}

    if prices is None:
        prices = {c: p["current_price"] for c, p in positions.items()}

    rows = []
    pos_value = 0.0
    for code, p in positions.items():
        curr = prices.get(code, p.get("current_price", p["avg_cost"]))
        value = p["shares"] * curr
        pos_value += value
        pnl_pct = (curr / p["avg_cost"] - 1) * 100 if p["avg_cost"] > 0 else 0
        rows.append({
            "code": code,
            "name": p["name"],
            "shares": p["shares"],
            "avg_cost": p["avg_cost"],
            "current_price": curr,
            "value": round(value, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total = state["cash"] + pos_value
    for r in rows:
        r["weight"] = round(r["value"] / total, 3) if total > 0 else 0

    rows.sort(key=lambda x: -x["value"])
    return {
        "cash": state["cash"],
        "positions": rows,
        "positions_value": round(pos_value, 2),
        "total_value": round(total, 2),
    }


def format_positions_table(data: dict) -> str:
    lines = [
        f"现金 ¥{data['cash']:,.2f} | 持仓 ¥{data.get('positions_value', 0):,.2f} | "
        f"总资产 ¥{data['total_value']:,.2f}",
        "",
        f"{'代码':<8} {'名称':<10} {'股数':>6} {'成本':>8} {'现价':>8} {'盈亏':>7} {'权重':>5}",
        "-" * 60,
    ]
    for r in data.get("positions", []):
        lines.append(
            f"{r['code']:<8} {r['name'][:8]:<10} {r['shares']:>6} "
            f"{r['avg_cost']:>8.3f} {r['current_price']:>8.3f} "
            f"{r['pnl_pct']:>+6.1f}% {r['weight']:>4.0%}"
        )
    if not data.get("positions"):
        lines.append("(空仓)")
    return "\n".join(lines)
