"""
模拟盘引擎 — EcohTangoFoxtra v3-lite
纯本地计算，零 token 消耗

功能：
  - 初始资金 ¥100,000
  - 每日根据决策卡执行模拟买卖
  - 跟踪持仓、成本价、市值、P&L
  - 输出每日账户快照
"""

import json
import os
from datetime import datetime
from typing import Optional

STATE_FILE = os.path.join(os.path.dirname(__file__), "paper_state.json")
INITIAL_CASH = 100_000.0  # 初始模拟资金


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _init_state()


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _init_state() -> dict:
    return {
        "initialized": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "initial_cash": INITIAL_CASH,
        "cash": INITIAL_CASH,
        "positions": {},      # {code: {name, shares, avg_cost, current_price}}
        "daily_pnl": 0.0,
        "total_pnl_pct": 0.0,
        "history": [],        # [{date, cash, total_value, daily_pnl_pct}]
    }


# ── 基础查询 ────────────────────────────────────────────────────────────────

def get_positions() -> dict:
    """Return current positions dict."""
    return _load_state()["positions"]


def get_cash() -> float:
    return _load_state()["cash"]


def get_total_value(prices: dict[str, float]) -> float:
    """
    计算当前总资产（含现金+持仓市值）。
    prices: {code: current_price}
    """
    state = _load_state()
    pos_value = sum(
        p["shares"] * prices.get(code, p["current_price"])
        for code, p in state["positions"].items()
    )
    return state["cash"] + pos_value


def get_snapshot(prices: dict[str, float]) -> dict:
    """Return current account snapshot."""
    state = _load_state()
    total_value = get_total_value(prices)
    total_cost = sum(
        p["shares"] * p["avg_cost"]
        for p in state["positions"].values()
    )
    pos_value = total_value - state["cash"]
    unrealized_pnl = pos_value - total_cost if total_cost > 0 else 0.0
    unrealized_pnl_pct = unrealized_pnl / total_cost * 100 if total_cost > 0 else 0.0

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "cash": round(state["cash"], 2),
        "positions_value": round(pos_value, 2),
        "total_value": round(total_value, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
        "total_pnl_pct": round((total_value / INITIAL_CASH - 1) * 100, 2),
        "position_count": len(state["positions"]),
    }


# ── 交易执行 ────────────────────────────────────────────────────────────────

def update_prices(prices: dict[str, float]) -> None:
    """
    更新持仓的当前价格（每日收盘后调用）。
    同时计算今日浮动盈亏。
    """
    state = _load_state()

    for code, price in prices.items():
        if code in state["positions"]:
            state["positions"][code]["current_price"] = price

    _save_state(state)


def execute_decisions(
    decisions: list[dict],
    prices: dict[str, float],
    total_value: Optional[float] = None,
) -> dict:
    """
    根据每日决策执行模拟交易。

    decisions: [{code, name, action, target_weight}]
               action: BUY | HOLD | REDUCE
               target_weight: 0.0–1.0 (相对于总资产的目标仓位)
    prices: {code: current_price}

    策略：
      - 每只 ETF 的目标市值 = total_value × target_weight
      - BUY → 买入到目标市值（每次最多用 20% 现金，分批建仓）
      - HOLD → 不操作
      - REDUCE → 卖出 50% 持仓
    """
    if total_value is None:
        total_value = get_total_value(prices)

    state = _load_state()
    state["daily_pnl"] = 0.0

    trade_log = []
    cash = state["cash"]

    # 先更新持仓价格并计算浮动盈亏
    for code in state["positions"]:
        p = state["positions"][code]
        prev_price = p.get("current_price", p["avg_cost"])
        curr_price = prices.get(code, prev_price)
        p["current_price"] = curr_price
        p["unrealized"] = (curr_price - p["avg_cost"]) * p["shares"]

    # 执行决策
    for dec in decisions:
        code = dec["code"]
        name = dec["name"]
        action = dec["action"]
        target_weight = dec.get("target_weight", 0)
        price = prices.get(code)

        if price is None:
            continue

        pos = state["positions"].get(code)
        target_value = total_value * target_weight
        max_invest = cash * 0.15  # 单次最多投入 15% 现金

        if action == "BUY":
            # 目标：达到 target_weight
            if pos is None:
                # 新建仓：最多投入 min(target_value, max_invest)
                invest = min(target_value, max_invest, cash)
                shares = int(invest / price / 100) * 100  # 整手
                cost = shares * price
                if shares > 0 and cost <= cash:
                    state["positions"][code] = {
                        "name": name,
                        "shares": shares,
                        "avg_cost": price,
                        "current_price": price,
                        "unrealized": 0.0,
                    }
                    cash -= cost
                    trade_log.append(f"BUY {name} {shares}股 @{price} = ¥{cost:.2f}")
            else:
                # 加仓
                current_value = pos["shares"] * price
                gap = target_value - current_value
                invest = min(gap, max_invest, cash)
                shares = int(invest / price / 100) * 100
                cost = shares * price
                if shares > 0 and cost <= cash:
                    total_shares = pos["shares"] + shares
                    total_cost = pos["shares"] * pos["avg_cost"] + cost
                    pos["shares"] = total_shares
                    pos["avg_cost"] = total_cost / total_shares
                    pos["current_price"] = price
                    cash -= cost
                    trade_log.append(f"ADD {name} +{shares}股 @{price} = ¥{cost:.2f}")

        elif action == "REDUCE" and pos:
            # 减仓 50%
            sell_shares = int(pos["shares"] * 0.5 / 100) * 100
            sell_shares = max(sell_shares, 0)
            if sell_shares >= 100:
                proceeds = sell_shares * price
                avg_cost_reduce = sell_shares * pos["avg_cost"]
                pos["shares"] -= sell_shares
                pos["current_price"] = price
                if pos["shares"] == 0:
                    del state["positions"][code]
                cash += proceeds
                trade_log.append(f"REDUCE {name} -{sell_shares}股 @{price} = +¥{proceeds:.2f}")
            elif pos["shares"] > 0 and pos["current_price"] > pos["avg_cost"] * 1.05:
                # 盈利超 5%，清仓
                proceeds = pos["shares"] * price
                trade_log.append(f"EXIT {name} -{pos['shares']}股 @{price} = +¥{proceeds:.2f}")
                cash += proceeds
                del state["positions"][code]

    # 记录快照
    pos_value = sum(p["shares"] * p["current_price"] for p in state["positions"].values())
    new_total = cash + pos_value
    daily_pnl = new_total - total_value
    daily_pnl_pct = daily_pnl / total_value * 100 if total_value > 0 else 0

    state["cash"] = round(cash, 2)
    state["daily_pnl"] = round(daily_pnl, 2)
    state["total_pnl_pct"] = round((new_total / INITIAL_CASH - 1) * 100, 2)

    snapshot = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "cash": round(cash, 2),
        "positions_value": round(pos_value, 2),
        "total_value": round(new_total, 2),
        "daily_pnl": round(daily_pnl, 2),
        "daily_pnl_pct": round(daily_pnl_pct, 2),
        "total_pnl_pct": round((new_total / INITIAL_CASH - 1) * 100, 2),
        "position_count": len(state["positions"]),
    }
    state["history"].append(snapshot)
    # 只保留最近 90 天历史
    if len(state["history"]) > 90:
        state["history"] = state["history"][-90:]

    _save_state(state)

    return {
        "snapshot": snapshot,
        "trades": trade_log,
    }


def reset_account() -> dict:
    """重置模拟账户到初始状态。"""
    state = _init_state()
    _save_state(state)
    return {"status": "reset", "initial_cash": INITIAL_CASH}


def get_history(days: int = 30) -> list[dict]:
    """返回最近 N 天的账户历史。"""
    state = _load_state()
    return state["history"][-days:]


# ── 格式化输出 ──────────────────────────────────────────────────────────────

def format_snapshot_text(snapshot: dict, prices: dict) -> str:
    """生成模拟账户的文字快照（用于飞书）。"""
    lines = [
        f"📊 模拟账户 {snapshot['date']}",
        f"总资产 ¥{snapshot['total_value']:,.2f}",
        f"  现金 ¥{snapshot['cash']:,.2f}",
        f"  持仓 ¥{snapshot['positions_value']:,.2f}",
        f"  今日 {'+' if snapshot['daily_pnl'] >= 0 else ''}¥{snapshot['daily_pnl']:,.2f} ({snapshot['daily_pnl_pct']:+.2f}%)",
        f"  累计 {'+' if snapshot['total_pnl_pct'] >= 0 else ''}{snapshot['total_pnl_pct']:.2f}%",
    ]
    return "\n".join(lines)


def format_positions_text(prices: dict) -> str:
    """生成持仓明细文字。"""
    state = _load_state()
    if not state["positions"]:
        return "📦 空仓"

    lines = ["", "📦 当前持仓:"]
    for code, p in sorted(state["positions"].items(), key=lambda x: x[1]["shares"] * x[1]["current_price"], reverse=True):
        curr = prices.get(code, p["current_price"])
        value = p["shares"] * curr
        pnl = (curr - p["avg_cost"]) / p["avg_cost"] * 100
        marker = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{marker} {p['name'][:6]} {p['shares']}股"
            f" 成本¥{p['avg_cost']:.3f} 现¥{curr:.3f}"
            f" {'+' if pnl >= 0 else ''}{pnl:.1f}%"
        )
    return "\n".join(lines)
