#!/usr/bin/env python3
"""
main_lite.py — EcohTangoFoxtra v3-lite
========================================
极简管线：数据 → 打分 → 排序 → 决策 → 模拟盘 → 飞书

用法:
  python main_lite.py                # 仅运行管线（打印摘要）
  python main_lite.py --feishu       # + 发送到飞书
  python main_lite.py --paper         # + 执行模拟盘交易
  python main_lite.py --report       # + 生成静态网页
  python main_lite.py --all          # 全部执行
  python main_lite.py --reset        # 重置模拟账户

所有计算在本地完成，飞书只接收最终决策卡（约 300–500 字）。
"""

import argparse
import json
import os
import sys
from datetime import datetime

# ── Path Setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)


def log(msg: str) -> None:
    if os.environ.get("LITE_VERBOSE", "1") != "0":
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ── Step 1: Data ─────────────────────────────────────────────────────────────

def step_data() -> tuple[list[dict], dict]:
    """L1: Fetch all quotes and macro data. Returns (quotes, macro)."""
    log("📥 L1 拉取行情数据...")
    from data_engine import fetch_all_assets, fetch_macro
    # fetch_all_assets = real-time quotes + K-line + MA/MACD/RSI indicators
    assets = fetch_all_assets(progress=True)
    macro = fetch_macro()
    log(f"   行情 {len(assets)} 条 OK | 沪深300: {macro.get('price', 'N/A')}")
    return assets, macro


# ── Step 2: Score ────────────────────────────────────────────────────────────

def step_score(assets: list[dict]) -> list[dict]:
    """L2: Score all assets. Returns scored list."""
    log("🧮 L2 计算信号评分...")
    from signal_engine import rate_scores
    scored = []
    for a in assets:
        try:
            s = rate_scores(a)
            if s:
                scored.append(s)
        except Exception:
            continue
    log(f"   评分完成 {len(scored)}/{len(assets)} 条")
    return scored


# ── Step 3: Regime ────────────────────────────────────────────────────────────

def step_regime(scored: list[dict], macro: dict = None) -> dict:
    """L3: Detect market regime. Returns regime dict."""
    log("🌐 L3 判断市场状态...")
    from market_regime import detect_regime
    regime = detect_regime(scored, macro)
    regime_cn = {"bull": "主升 🟢", "rotation": "轮动 🟡", "defensive": "防守 🔴"}.get(
        regime["regime"], regime.get("regime_cn", "未知")
    )
    log(f"   {regime_cn} | 趋势均值 {regime.get('avg_trend', 0)} | 主线: {regime.get('leading_groups', [])}")
    return regime


# ── Step 4: Rotation ─────────────────────────────────────────────────────────

def step_rotation(scored: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """L4: Rank assets, detect sector rotation. Returns (ranked, rotation_signals, arrows)."""
    log("🔄 L4 轮动分析...")
    from rotation_engine import rank_assets, detect_rotation

    ranked = rank_assets(scored)
    rotation_signals = detect_rotation(ranked)

    # Build rotation arrows
    arrows = []
    for s in sorted(rotation_signals, key=lambda x: x.get("avg_score", 50), reverse=True):
        if s.get("direction") == "up" and s.get("avg_score", 0) >= 55:
            arrows.append(f"{s['name']} ↑")
        elif s.get("direction") == "down" and s.get("avg_score", 0) <= 45:
            arrows.append(f"{s['name']} ↓")

    core = [a for a in ranked if a.get("tier") == "core"]
    watch = [a for a in ranked if a.get("tier") == "watch"]
    reduce_pool = [a for a in ranked if a.get("tier") == "reduce"]

    log(f"   主线 {len(core)} | 观察 {len(watch)} | 淘汰 {len(reduce_pool)}")
    log(f"   轮动: {' | '.join(arrows[:3]) or '暂无'}")
    return ranked, rotation_signals, arrows


# ── Step 5: Portfolio Decision ───────────────────────────────────────────────

def step_portfolio(ranked: list[dict], regime: dict) -> tuple[dict, list[dict], dict]:
    """L5: Build portfolio, extract top-5 actions. Returns (portfolio, top5, summary)."""
    log("💰 L5 组合决策...")
    from portfolio_engine import build_portfolio

    portfolio = build_portfolio(ranked, regime)

    # Top 5 actions: buys first, then holds, then reduces
    buy_a = [a for a in portfolio["actions"] if a["action"] == "BUY"]
    hold_a = [a for a in portfolio["actions"] if a["action"] == "HOLD"]
    reduce_a = [a for a in portfolio["actions"] if a["action"] == "REDUCE"]
    top5 = (buy_a + hold_a + reduce_a)[:5]

    # Attach scores from ranked
    score_map = {a["code"]: a["final_score"] for a in ranked}
    for t in top5:
        t["score"] = score_map.get(t["code"], 50)

    portfolio_summary = {
        "equity": regime.get("equity_allocation", 0.6),
        "defensive": portfolio.get("defensive_weight", 0.2),
        "cash": portfolio.get("cash_allocation", 0.4),
    }

    log(f"   加仓 {portfolio['buy_count']} | 持有 {portfolio['hold_count']} | 减仓 {portfolio['reduce_count']}")
    return portfolio, top5, portfolio_summary


# ── Step 6: Paper Trading ─────────────────────────────────────────────────────

def step_paper(
    ranked: list[dict],
    regime: dict,
    assets: list[dict],
) -> dict:
    """Execute paper trades based on ranked decisions. Returns snapshot."""
    log("📈 模拟盘执行...")
    from paper_trading import (
        execute_decisions, update_prices, get_total_value,
    )

    prices = {a["code"]: a["price"] for a in assets}
    update_prices(prices)
    total_value = get_total_value(prices)

    # Build decisions from ranked assets
    decisions = []
    buy_assets = [a for a in ranked if a.get("tier") == "core"][:6]
    hold_assets = [a for a in ranked if a.get("tier") == "watch"][:4]

    equity = regime.get("equity_allocation", 0.6)
    target_value = total_value * equity

    if buy_assets:
        per_asset = target_value / len(buy_assets)
        for a in buy_assets:
            price = prices.get(a["code"])
            if price:
                decisions.append({
                    "code": a["code"], "name": a["name"],
                    "action": "BUY", "target_weight": per_asset / total_value,
                })

    for a in hold_assets:
        price = prices.get(a["code"])
        if price:
            decisions.append({
                "code": a["code"], "name": a["name"],
                "action": "HOLD", "target_weight": 0.05,
            })

    # Reduce bottom 3
    reduce_assets = [a for a in ranked if a.get("tier") == "reduce"][:3]
    for a in reduce_assets:
        price = prices.get(a["code"])
        if price:
            decisions.append({
                "code": a["code"], "name": a["name"],
                "action": "REDUCE", "target_weight": 0,
            })

    result = execute_decisions(decisions, prices, total_value)
    snap = result["snapshot"]

    log(f"   总资产 ¥{snap['total_value']:,.0f} | "
        f"今日{'+' if snap['daily_pnl'] >= 0 else ''}¥{snap['daily_pnl']:,.2f} "
        f"({snap['daily_pnl_pct']:+.2f}%) | "
        f"累计{'+' if snap['total_pnl_pct'] >= 0 else ''}{snap['total_pnl_pct']:.2f}%")
    for t in result["trades"]:
        log(f"   {t}")

    return snap


def step_paper_snapshot_only(assets: list[dict]) -> dict:
    """Get snapshot without executing trades."""
    from paper_trading import get_snapshot, update_prices
    prices = {a["code"]: a["price"] for a in assets}
    update_prices(prices)
    return get_snapshot(prices)


# ── Step 7: Feishu ──────────────────────────────────────────────────────────

def step_feishu(
    regime: dict,
    top5: list[dict],
    arrows: list[str],
    portfolio_summary: dict,
    paper_snap: dict,
) -> dict:
    """Send lite card to Feishu webhook (if configured)."""
    log("📡 发送飞书卡片...")
    from feishu_lite import send_lite_card
    result = send_lite_card(
        regime=regime, top_actions=top5,
        rotation_arrows=arrows, portfolio_summary=portfolio_summary,
        paper_snapshot=paper_snap,
    )
    if result["sent"]:
        log("   ✅ 飞书发送成功")
    elif result["webhook_configured"]:
        log(f"   ⚠️ 飞书发送失败: {result.get('response', result.get('error', 'unknown'))}")
    else:
        log("   ℹ️ 未配置飞书 webhook（设置 FEISHU_WEBHOOK_URL 环境变量）")
    return result


# ── Step 8: Save lite card ───────────────────────────────────────────────────

def step_save(
    regime: dict, top5: list[dict], arrows: list[str],
    portfolio_summary: dict, paper_snap: dict,
) -> str:
    """Save lite card to docs/lite_card.md."""
    log("💾 保存决策卡...")
    from feishu_lite import save_lite_card
    path = save_lite_card(
        regime=regime, top_actions=top5,
        rotation_arrows=arrows, portfolio_summary=portfolio_summary,
        paper_snapshot=paper_snap,
        path="docs/lite_card.md",
    )
    log(f"   → {path}")
    return path


# ── Step 9: HTML Report ─────────────────────────────────────────────────────

def step_report(
    regime: dict, ranked: list[dict],
    rotation_signals: list[dict],
    portfolio: dict, paper_snap: dict,
) -> str:
    """Generate static HTML report."""
    log("🌐 生成静态网页...")
    sys.path.insert(0, ROOT)
    from build_report import generate_v2_html
    from portfolio_engine import generate_advice

    advice = generate_advice(regime, rotation_signals)
    # Get macro-like data from regime
    macro = {
        "price": regime.get("hs300_price", "N/A"),
        "diff_ma60_pct": regime.get("diff_pct", 0),
    }

    path = generate_v2_html(
        regime, ranked, rotation_signals, portfolio,
        macro, advice
    )
    log(f"   → {path}")
    return path


# ── Main Pipeline ───────────────────────────────────────────────────────────

def run_pipeline(
    feishu: bool = False,
    paper: bool = False,
    report: bool = False,
) -> dict:
    """Run full v3-lite pipeline. Returns results."""
    today = datetime.now().strftime("%Y-%m-%d")
    log("=" * 50)
    log(f"EcohTangoFoxtra v3-lite 管线 {today}")
    log("=" * 50)

    t0 = datetime.now()

    # L1
    assets, macro = step_data()

    # L2
    scored = step_score(assets)
    if not scored:
        log("❌ L2: 无有效评分数据")
        return {"success": False, "error": "no_scored_data"}

    # L3
    regime = step_regime(scored, macro)

    # L4
    ranked, rotation_signals, arrows = step_rotation(scored)

    # L5
    portfolio, top5, portfolio_summary = step_portfolio(ranked, regime)

    # L6: Paper
    if paper:
        paper_snap = step_paper(ranked, regime, assets)
    else:
        paper_snap = step_paper_snapshot_only(assets)

    # L7–L9: Output
    if feishu:
        step_feishu(regime, top5, arrows, portfolio_summary, paper_snap)

    lite_path = step_save(regime, top5, arrows, portfolio_summary, paper_snap)

    report_path = None
    if report:
        report_path = step_report(regime, ranked, rotation_signals, portfolio, paper_snap)

    elapsed = (datetime.now() - t0).total_seconds()
    log(f"✅ 完成，耗时 {elapsed:.1f}s")

    _print_summary(regime, portfolio, paper_snap, arrows, top5)

    return {
        "success": True,
        "regime": regime,
        "ranked": ranked[:10],
        "portfolio": portfolio,
        "top5": top5,
        "paper_snapshot": paper_snap,
        "rotation_arrows": arrows,
        "lite_card_path": lite_path,
        "report_path": report_path,
        "elapsed_seconds": elapsed,
    }


def _print_summary(
    regime: dict, portfolio: dict,
    paper_snap: dict, arrows: list[str], top5: list[dict],
) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    eq = int(portfolio.get("equity_allocation", 0.6) * 100)
    regime_cn = {"bull": "🟢 主升", "rotation": "🟡 轮动", "defensive": "🔴 防守"}.get(
        regime.get("regime", ""), regime.get("regime_cn", "未知")
    )
    print()
    print("════════════════════════════════════════════")
    print(f"  📊 ETF决策卡  {today}")
    print(f"  市场: {regime_cn}")
    print(f"  轮动: {' | '.join(arrows[:3]) or '暂无'}")
    print()
    print("  🎯 操作建议:")
    for a in top5:
        action_word = {"BUY": "加仓", "HOLD": "持有", "REDUCE": "减仓"}.get(a["action"], a["action"])
        print(f"    {action_word:4s}  {a.get('name', a.get('code', ''))[:8]}")
    print()
    print(f"  💰 仓位: {eq}%权益 / {100-eq}%防御现金")
    if paper_snap:
        total = paper_snap["total_value"]
        total_pct = paper_snap["total_pnl_pct"]
        daily = paper_snap["daily_pnl_pct"]
        print(f"  📈 模拟盘: ¥{total:,.0f}  "
              f"今日{'+' if daily >= 0 else ''}{daily:.2f}%  "
              f"累计{'+' if total_pct >= 0 else ''}{total_pct:.2f}%")
    print("════════════════════════════════════════════")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="EcohTangoFoxtra v3-lite")
    parser.add_argument("--feishu", action="store_true", help="发送飞书卡片")
    parser.add_argument("--paper", action="store_true", help="执行模拟盘交易")
    parser.add_argument("--report", action="store_true", help="生成静态网页")
    parser.add_argument("--all", action="store_true", help="执行全部")
    parser.add_argument("--reset", action="store_true", help="重置模拟账户")
    args = parser.parse_args()

    if args.reset:
        from paper_trading import reset_account
        result = reset_account()
        print(f"✅ 模拟账户已重置，初始资金 ¥{result['initial_cash']:,.0f}")
        return

    feishu = args.feishu or args.all
    paper = args.paper or args.all
    report = args.report or args.all

    result = run_pipeline(feishu=feishu, paper=paper, report=report)
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
