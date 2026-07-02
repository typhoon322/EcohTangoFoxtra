"""
Feishu Reporter — Format and send daily ETF decision card.
Supports: Lark webhook (simple) or lark-im skill (interactive).
"""

import json
import os
from datetime import datetime

# --- Card Formatting ---

def build_decision_card(
    regime: dict,
    ranked_assets: list[dict],
    rotation_signals: list[dict],
    portfolio: dict,
    macro: dict,
    advice: list[str],
) -> str:
    """Build the full daily decision card as a formatted string."""

    now = datetime.now().strftime("%Y-%m-%d")
    risk_emoji = {"bull": "🟢", "rotation": "🟡", "bear": "🔴"}

    lines = []
    lines.append(f"# 📊 ETF / 基金交易决策卡 ({now})")
    lines.append("")

    # --- 1. Market State ---
    emoji = risk_emoji.get(regime["regime"], "⚪")
    leading = " + ".join([_group_name(g) for g in regime.get("leading_groups", [])])
    appetite_cn = {"high": "积极", "neutral": "中性偏谨慎", "low": "防御"}

    lines.append("## 🧭 1. 市场状态")
    lines.append("")
    lines.append(f"- 市场类型：{emoji} {regime['regime_cn']}")
    lines.append(f"- 主线：{leading or '暂无明确主线'}")
    lines.append(f"- 风险偏好：{appetite_cn.get(regime.get('risk_appetite', 'neutral'), '中性')}")
    lines.append(f"- 趋势均值：{regime.get('avg_trend', 0)}分 | 离散度：{regime.get('std_trend', 0)}")
    if macro:
        lines.append(f"- 沪深300：{macro['price']} (距MA60: {'+' if macro['diff_ma60_pct'] > 0 else ''}{macro['diff_ma60_pct']}%)")
    lines.append("")

    # --- 2. Rotation Signals ---
    lines.append("## 🔥 2. 今日轮动信号")
    lines.append("")
    for s in rotation_signals:
        lines.append(f"- {s['name']}：{s['signal']} ({s['avg_score']}分)")
    lines.append("")

    # --- 3. Asset Rankings ---
    lines.append("## 📈 3. 资产评分排行 (Top 10)")
    lines.append("")
    lines.append("| 排名 | 资产 | 综合分 | 趋势 | 资金 | 风险 | 操作 |")
    lines.append("|------|------|--------|------|------|------|------|")
    for a in ranked_assets[:10]:
        ts = a["trend_score"]; fs = a["flow_score"]; rs = a["risk_score"]
        trend_icon = "🟢" if ts >= 65 else ("🟡" if ts >= 40 else "🔴")
        risk_icon = "🟢" if rs <= 30 else ("🟡" if rs <= 60 else "🔴")
        action = _get_action_for_asset(a["code"], portfolio)
        lines.append(f"| {a['rank']} | {a['name']} | {a['final_score']} | {trend_icon}{ts} | {fs} | {risk_icon}{rs} | {action} |")
    lines.append("")

    # --- 4. Position Advice ---
    eq = portfolio.get("equity_allocation", 0.6)
    cash = portfolio.get("cash_allocation", 0.4)
    defensive = portfolio.get("defensive_weight", 0)
    growth = portfolio.get("growth_weight", 0)

    lines.append("## 💰 4. 仓位建议")
    lines.append("")
    lines.append(f"- 股票ETF：{int(eq*100)}%")
    lines.append(f"- 防守类（红利/黄金）：{int(defensive*100)}%")
    lines.append(f"- 成长类：{int(growth*100)}%")
    lines.append(f"- 现金：{int(cash*100)}%")
    lines.append(f"- 买入：{portfolio['buy_count']} 只 | 持有：{portfolio['hold_count']} 只 | 减仓：{portfolio['reduce_count']} 只")
    lines.append("")

    # --- 5. Today's Advice ---
    lines.append("## 🎯 5. 今日操作建议")
    lines.append("")
    for a in advice:
        lines.append(a)
    lines.append("")

    # --- 6. Risk Note ---
    lines.append("## ⚠️ 6. 风险提示")
    lines.append("")
    lines.append("- 本决策卡基于量化模型自动生成，不构成投资建议")
    lines.append("- 所有信号均基于历史数据，不代表未来表现")
    lines.append("- 投资有风险，入市需谨慎")
    lines.append("")

    return "\n".join(lines)


def build_card_json(regime, ranked_assets, rotation_signals, portfolio, macro, advice):
    """Build interactive Lark card payload (for webhook/bot)."""
    now = datetime.now().strftime("%Y-%m-%d")
    risk_color = {"bull": "green", "rotation": "yellow", "bear": "red"}

    # Build top assets list
    asset_lines = []
    for a in ranked_assets[:8]:
        asset_lines.append(f"  • {a['rank']}. {a['name']} — {a['final_score']}分 [{a.get('tier_cn', '')}]")

    text = build_decision_card(regime, ranked_assets, rotation_signals, portfolio, macro, advice)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 ETF 交易决策卡 ({now})"},
                "template": risk_color.get(regime["regime"], "blue"),
            },
            "elements": [
                {"tag": "markdown", "content": text},
                {
                    "tag": "action",
                    "actions": [
                        {"tag": "button", "text": {"tag": "plain_text", "content": "📖 查看完整报告"},
                         "url": "https://typhoon322.github.io/EcohTangoFoxtra/",
                         "type": "default"},
                    ]
                }
            ],
        },
    }


def _group_name(g: str) -> str:
    from data_engine import GROUP_NAMES
    return GROUP_NAMES.get(g, g)


def _get_action_for_asset(code: str, portfolio: dict) -> str:
    for a in portfolio.get("actions", []):
        if a["code"] == code:
            return a["action_cn"]
    return "—"


# --- Delivery ---

def send_to_feishu_webhook(webhook_url: str, payload: dict) -> bool:
    """Send card to Feishu bot webhook."""
    import requests
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def save_card_to_file(card_text: str, path: str = "docs/decision_card.md") -> str:
    """Save decision card as markdown file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(card_text)
    return os.path.abspath(path)


def get_feishu_webhook_url() -> str:
    """Get Feishu webhook URL from env or default."""
    return os.environ.get("FEISHU_WEBHOOK_URL", "")
