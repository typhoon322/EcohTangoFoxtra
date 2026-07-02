#!/usr/bin/env python3
"""
record_trade.py — 手动录入交易 / 查看持仓

用法:
  python3 scripts/record_trade.py list
  python3 scripts/record_trade.py buy  510300 1000 4.850 [--name 沪深300ETF]
  python3 scripts/record_trade.py sell 510300 500 4.900
  python3 scripts/record_trade.py cash 50000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from position_ledger import (
    record_buy, record_sell, set_cash, list_positions, format_positions_table,
)


def cmd_list(_args) -> int:
    data = list_positions()
    print(format_positions_table(data))
    return 0


def cmd_buy(args) -> int:
    try:
        r = record_buy(args.code, args.shares, args.price, name=args.name or "")
        t = r["trade"]
        print(f"✅ 买入 {t['name']} {t['shares']}股 @{t['price']:.3f} = ¥{abs(t['amount']):,.2f}")
        print(f"   剩余现金 ¥{r['cash']:,.2f}")
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    return 0


def cmd_sell(args) -> int:
    try:
        r = record_sell(args.code, args.shares, args.price)
        t = r["trade"]
        print(f"✅ 卖出 {t['name']} {t['shares']}股 @{t['price']:.3f} = ¥{t['amount']:,.2f}")
        print(f"   剩余现金 ¥{r['cash']:,.2f}")
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    return 0


def cmd_cash(args) -> int:
    try:
        r = set_cash(args.amount)
        print(f"✅ 现金已设为 ¥{r['cash']:,.2f}")
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EcohTangoFoxtra 持仓录入")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="查看当前持仓")

    p_buy = sub.add_parser("buy", help="录入买入")
    p_buy.add_argument("code", help="ETF 代码，如 510300")
    p_buy.add_argument("shares", type=int, help="股数（100 整数倍）")
    p_buy.add_argument("price", type=float, help="成交价")
    p_buy.add_argument("--name", default="", help="名称（可选）")

    p_sell = sub.add_parser("sell", help="录入卖出")
    p_sell.add_argument("code", help="ETF 代码")
    p_sell.add_argument("shares", type=int, help="股数（100 整数倍）")
    p_sell.add_argument("price", type=float, help="成交价")

    p_cash = sub.add_parser("cash", help="设置现金余额（对账）")
    p_cash.add_argument("amount", type=float, help="现金金额")

    args = parser.parse_args()
    handlers = {"list": cmd_list, "buy": cmd_buy, "sell": cmd_sell, "cash": cmd_cash}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
