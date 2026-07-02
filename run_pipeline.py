#!/usr/bin/env python3
"""
EcohTangoFoxtra v2 — Full Pipeline Runner.
Runs L1→L5 end-to-end: data → signals → regime → rotation → portfolio → output.

Usage:
  python run_pipeline.py              # Full run + generate report
  python run_pipeline.py --feishu     # Also send to Feishu
  python run_pipeline.py --dry-run    # Print summary only, no file output
"""

import sys, os, argparse, json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

# ── L1: Data ──────────────────────────────────────────────────────────
print("╔══════════════════════════════════════════╗")
print("║  EcohTangoFoxtra v2 · Pipeline Runner    ║")
print("╚══════════════════════════════════════════╝")
print(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print("═ L1: 数据采集 ══════════════════════════")
from data_engine import fetch_all_assets, fetch_macro, ASSET_POOL, GROUP_NAMES
assets = fetch_all_assets()
macro = fetch_macro()
print(f"   ✅ {len(assets)}/{len(ASSET_POOL)} 资产数据就绪")
print(f"   ✅ 宏观: 沪深300 {macro['price']} (距MA60: {macro['diff_ma60_pct']:+}%)")

# ── L2: Signals ──────────────────────────────────────────────────────
print("\n═ L2: 信号评分 ══════════════════════════")
from signal_engine import rate_scores
scored = [rate_scores(a) for a in assets]
avg_t = sum(a["trend_score"] for a in scored) / len(scored)
avg_f = sum(a["flow_score"] for a in scored) / len(scored)
avg_r = sum(a["risk_score"] for a in scored) / len(scored)
print(f"   ✅ 趋势均值: {avg_t:.1f} | 资金均值: {avg_f:.1f} | 风险均值: {avg_r:.1f}")

# ── L3: Market Regime ────────────────────────────────────────────────
print("\n═ L3: 市场状态 ══════════════════════════")
from market_regime import detect_regime
regime = detect_regime(scored, macro)
print(f"   ✅ {regime['regime_cn']} | 置信度: {regime['confidence']}% | 权益仓位: {int(regime['equity_allocation']*100)}%")
if regime["leading_groups"]:
    lead_names = [GROUP_NAMES.get(g, g) for g in regime["leading_groups"][:3]]
    print(f"   📈 主线: {' + '.join(lead_names)}")

# ── L4: Rotation ─────────────────────────────────────────────────────
print("\n═ L4: 轮动分析 ══════════════════════════")
from rotation_engine import rank_assets, detect_rotation
ranked = rank_assets(scored)
rotation_signals = detect_rotation(ranked)

print(f"   🟢 主线池: {sum(1 for a in ranked if a['tier'] == 'core')} 只")
print(f"   🟡 观察池: {sum(1 for a in ranked if a['tier'] == 'watch')} 只")
print(f"   🔴 淘汰池: {sum(1 for a in ranked if a['tier'] == 'reduce')} 只")
print("   轮动信号:")
for s in rotation_signals[:5]:
    print(f"     {s['signal']} {s['name']} ({s['avg_score']}分)")

# ── L5: Portfolio ────────────────────────────────────────────────────
print("\n═ L5: 组合决策 ══════════════════════════")
from portfolio_engine import build_portfolio, generate_advice
portfolio = build_portfolio(ranked, regime)
advice = generate_advice(regime, rotation_signals)
print(f"   📈 BUY: {portfolio['buy_count']} | HOLD: {portfolio['hold_count']} | REDUCE: {portfolio['reduce_count']}")
print(f"   💰 仓位: 权益{int(portfolio['equity_allocation']*100)}% / 现金{int(portfolio['cash_allocation']*100)}%")

# ── Output ───────────────────────────────────────────────────────────
print("\n═ 输出: 决策卡 ══════════════════════════")
from feishu_reporter import build_decision_card, save_card_to_file, get_feishu_webhook_url

card_text = build_decision_card(regime, ranked, rotation_signals, portfolio, macro, advice)
card_path = save_card_to_file(card_text)
print(f"   ✅ 决策卡已保存: {card_path}")

# ── Feishu ───────────────────────────────────────────────────────────
args = argparse.Namespace()
try:
    # manual parse for optional --feishu
    if "--feishu" in sys.argv:
        webhook = get_feishu_webhook_url()
        if webhook:
            from feishu_reporter import build_card_json, send_to_feishu_webhook
            card_json = build_card_json(regime, ranked, rotation_signals, portfolio, macro, advice)
            ok = send_to_feishu_webhook(webhook, card_json)
            print(f"   {'✅' if ok else '❌'} 飞书推送: {'成功' if ok else '失败'}")
        else:
            print("   ⚠️ 未设置 FEISHU_WEBHOOK_URL 环境变量，跳过飞书推送")
except Exception as e:
    print(f"   ⚠️ 飞书推送异常: {e}")

# ── Summary ──────────────────────────────────────────────────────────
print("\n════════════════════════════════════════════")
print("  📊 今日决策摘要")
print("════════════════════════════════════════════")
print(f"  市场: {regime['regime_cn']} / 仓位: {int(regime['equity_allocation']*100)}%")
print(f"  Top 3:")
for a in ranked[:3]:
    action = "加仓" if a["tier"] == "core" else ("减仓" if a["tier"] == "reduce" else "持有")
    print(f"    {a['rank']}. {a['name']}: {a['final_score']}分 → {action}")
print(f"  建议 ({len(advice)} 条)")
for a in advice[:2]:
    print(f"    {a}")
print("════════════════════════════════════════════\n")

# ── HTML Report Generation ───────────────────────────────────────────
if "--report" in sys.argv:
    print("═ 生成: 静态报告 ══════════════════════════")
    import build_report
    report_path = build_report.generate_v2_html(regime, ranked, rotation_signals, portfolio, macro, advice)
    print(f"   ✅ 静态报告: {report_path}")
