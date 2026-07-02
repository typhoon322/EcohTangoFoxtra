"""
feishu_lite.py — 极简飞书卡片
v3-lite 核心：只输出「可执行决策」，不输出分析过程。

卡片原则：
  1. 总长度 < 600 字
  2. 市场状态：1 个词（BULL / ROTATION / DEFENSIVE）
  3. 轮动：最多 3 个箭头
  4. 操作：最多 5 条
  5. 持仓：只说仓位比例，不说理由
"""

import json
import os
from datetime import datetime

from feishu_config import get_webhook_url, is_configured, keyword_footer, ensure_keyword, KEYWORD_TAG

# ── 词表 ────────────────────────────────────────────────────────────────────

_REGIME_CN = {
    "bull": "🟢 主升",
    "rotation": "🟡 轮动",
    "defensive": "🔴 防守",
}

_ACTION_ICON = {"BUY": "➕", "HOLD": "➖", "REDUCE": "➖"}


# ── 卡片构建 ────────────────────────────────────────────────────────────────

def build_lite_card(
    regime: dict,        # {"regime": "rotation", "leading_groups": [...], "equity_allocation": 0.6}
    top_actions: list,   # [{name, action, score}] sorted by score desc, max 5
    rotation_arrows: list,  # ["AI → 红利", "消费 → 弱"]  max 3
    portfolio_summary: dict, # {"equity": 0.6, "cash": 0.4, "defensive": 0.2}
    paper_snapshot: dict = None,  # optional: paper trading snapshot
    regime_summary: str = "",     # optional: ultra-short 1-line regime description
) -> str:
    """
    构建极简决策卡文字（用于飞书 / 微信 / 文件输出）。
    """
    now = datetime.now().strftime("%m/%d %H:%M")
    regime_key = regime.get("regime", "rotation")
    regime_word = _REGIME_CN.get(regime_key, "⚪ 中性")
    leading = " + ".join(regime.get("leading_groups", [])[:2]) or "暂无明确主线"
    equity = int(portfolio_summary.get("equity", 0.6) * 100)
    defensive = int(portfolio_summary.get("defensive", 0.2) * 100)

    lines = []
    lines.append(f"📊 ETF决策卡 {now}")
    lines.append(f"【{regime_word}】市场主线:{leading}")
    lines.append(f"仓位 {equity}%权益 / {defensive}%防御 / {100-equity-defensive}%现金")
    lines.append("")

    # Rotation arrows
    if rotation_arrows:
        lines.append("轮动 " + " | ".join(rotation_arrows[:3]))
        lines.append("")

    # Top actions
    if top_actions:
        lines.append("操作:")
        for item in top_actions[:5]:
            icon = _ACTION_ICON.get(item["action"], "•")
            name = item.get("name", item.get("code", ""))[:8]
            score = item.get("score", 0)
            # action word
            if item["action"] == "BUY":
                act_word = "加"
            elif item["action"] == "REDUCE":
                act_word = "减"
            else:
                act_word = "持"
            lines.append(f"{icon} {name} {act_word}({score:.0f})")

    # Paper trading snapshot
    if paper_snapshot:
        total = paper_snapshot.get("total_value", 0)
        daily = paper_snapshot.get("daily_pnl_pct", 0)
        total_pct = paper_snapshot.get("total_pnl_pct", 0)
        marker = "+" if total_pct >= 0 else ""
        lines.append("")
        lines.append(
            f"📈 模拟盘 ¥{total:,.0f} "
            f"今日{'+' if daily >= 0 else ''}{daily:.2f}% "
            f"累计{marker}{total_pct:.2f}%"
        )

    lines.append("")
    lines.append(keyword_footer())

    return "\n".join(lines)


def build_lite_card_json(regime: dict, top_actions: list,
                          rotation_arrows: list, portfolio_summary: dict,
                          paper_snapshot: dict = None) -> dict:
    """
    构建飞书交互卡片 JSON（使用飞书 card element 格式）。
    极简布局：header + 2个横向分组 + 操作列表 + 模拟盘摘要。
    """
    now = datetime.now().strftime("%Y-%m-%d")
    regime_key = regime.get("regime", "rotation")
    risk_color = {"bull": "green", "rotation": "yellow", "defensive": "red"}
    color = risk_color.get(regime_key, "blue")

    leading = " + ".join(regime.get("leading_groups", [])[:2]) or "暂无"
    equity = int(portfolio_summary.get("equity", 0.6) * 100)
    defensive = int(portfolio_summary.get("defensive", 0.2) * 100)
    rotation_text = " | ".join(rotation_arrows[:3]) if rotation_arrows else "暂无"

    # Build action rows
    action_rows = []
    for item in top_actions[:5]:
        name = (item.get("name") or item.get("code") or "")[:8]
        score = int(item.get("score", 0))
        act = item.get("action", "HOLD")
        if act == "BUY":
            emoji, color_action = "➕", "green"
        elif act == "REDUCE":
            emoji, color_action = "➖", "red"
        else:
            emoji, color_action = "➖", "grey"

        action_rows.append({
            "tag": "column_set",
            "flex_mode": "center",
            "weight": 1,
            "fields": [
                {
                    "tag": "markdown",
                    "content": f"**{emoji} {name}**\n{act} ({score})",
                }
            ],
        })

    # Paper section
    paper_note = ""
    if paper_snapshot:
        total = paper_snapshot.get("total_value", 0)
        daily = paper_snapshot.get("daily_pnl_pct", 0)
        total_pct = paper_snapshot.get("total_pnl_pct", 0)
        paper_note = (
            f"| 模拟盘: ¥{total:,.0f} "
            f"今日{'+' if daily >= 0 else ''}{daily:.2f}% "
            f"累计{'+' if total_pct >= 0 else ''}{total_pct:.2f}%"
        )

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 ETF决策卡 {now}"},
                "template": color,
            },
            "elements": [
                # Status row
                {
                    "tag": "div",
                    "text": {
                        "tag": "markdown",
                        "content": (
                            f"**【{regime_key.upper()}】** 市场主线: {leading}\n"
                            f"仓位: {equity}%权益 / {defensive}%防御 / {100-equity-defensive}%现金"
                        ),
                    },
                },
                # Rotation
                {
                    "tag": "div",
                    "text": {"tag": "markdown", "content": f"🔄 {rotation_text}"},
                },
                {"tag": "hr"},
                # Action header
                {"tag": "markdown", "content": "**🎯 操作建议 (score)**"},
                # Action items
                *([
                    {
                        "tag": "div",
                        "text": {
                            "tag": "markdown",
                            "content": " | ".join(
                                f"{_ACTION_ICON.get(a['action'], '•')} **{a.get('name', a.get('code',''))[:6]}** {a['action']}({int(a.get('score',0))})"
                                for a in top_actions[:5]
                            )
                        }
                    }
                ] if top_actions else []),
                # Paper
                *([{"tag": "markdown", "content": paper_note}] if paper_note else []),
                {"tag": "hr"},
                # Footer
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": keyword_footer()}
                    ],
                },
            ],
        },
    }


# ── 发送 ───────────────────────────────────────────────────────────────────

def _post_feishu(payload: dict) -> dict:
    """POST 到飞书（URL 从混淆配置解析，日志不输出 URL）。"""
    webhook_url = get_webhook_url()
    result = {"sent": False, "webhook_configured": is_configured()}
    if not webhook_url:
        return result
    try:
        import requests
        r = requests.post(webhook_url, json=payload, timeout=10)
        result["sent"] = r.status_code == 200
        result["response"] = r.text[:100]
        if not result["sent"]:
            result["error"] = r.text[:200]
    except Exception as e:
        result["error"] = str(e)
    return result


def send_lite_card(
    regime: dict,
    top_actions: list,
    rotation_arrows: list,
    portfolio_summary: dict,
    paper_snapshot: dict = None,
) -> dict:
    """
    发送极简卡片到飞书（如果已配置 LARK_PUSH_CFG）。
    返回发送结果和卡片文字。
    """
    card_text = build_lite_card(
        regime, top_actions, rotation_arrows,
        portfolio_summary, paper_snapshot
    )

    result = {"sent": False, "text": card_text, "webhook_configured": is_configured()}

    if is_configured():
        card_json = build_lite_card_json(
            regime, top_actions, rotation_arrows,
            portfolio_summary, paper_snapshot
        )
        post = _post_feishu(card_json)
        result.update(post)

    return result


def save_lite_card(
    regime: dict,
    top_actions: list,
    rotation_arrows: list,
    portfolio_summary: dict,
    paper_snapshot: dict = None,
    path: str = "docs/lite_card.md",
) -> str:
    """保存极简卡片到文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = build_lite_card(
        regime, top_actions, rotation_arrows,
        portfolio_summary, paper_snapshot
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.abspath(path)


# ── v3.4+v3.5 Fund Report ───────────────────────────────────────────────────

def build_fund_card(report: dict) -> str:
    """构建 Daily Fund Report 文字卡片。"""
    from fund_manager import format_fund_report
    return format_fund_report(report)


def build_fund_card_json(report: dict) -> dict:
    """构建飞书基金日报交互卡片 JSON。"""
    s = report.get("summary", {})
    rb = report.get("risk_budget", {})
    sa = report.get("strategy_allocation", {}).get("weights", {})
    regime = s.get("regime", "Unknown")
    now = datetime.now().strftime("%Y-%m-%d")

    regime_color = {
        "Bull": "green", "Sideways": "yellow",
        "Bear": "red", "HighVolatility": "orange",
    }.get(regime, "blue")

    strat_lines = "\n".join(
        f"• **{k.replace('_', ' ').title()}**: {v:.0%}"
        for k, v in sa.items()
    )
    holdings_lines = "\n".join(
        f"• {h['name']} **{h['weight']:.0%}** ({h.get('risk_level', 'MED')})"
        for h in s.get("top_holdings", [])
    )
    risk_lines = "\n".join(
        f"• {report['portfolio']['names'].get(c, c)}: **{lvl}**"
        for c, lvl in report.get("risk_parity", {}).get("risk_levels", {}).items()
    )
    stab = report.get("stability", {})
    stab_status = report.get("summary", {}).get("stability_status", "normal")
    stab_lines = f"**Status**: {stab_status.upper()}"
    if stab.get("consecutive_loss", {}).get("triggered"):
        stab_lines += f"\n⚠️ 连亏保护 {stab['consecutive_loss']['streak']} 天"
    if stab.get("rebalance_gated"):
        stab_lines += "\n🔒 再平衡已节流"
    for note in stab.get("stability_notes", []):
        stab_lines += f"\n• {note}"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🏦 市场 Fund Report {now}"},
                "template": regime_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "markdown",
                        "content": (
                            f"**Portfolio Risk (score)**: {s.get('portfolio_risk_pct', 0):.1f}%\n"
                            f"**Regime / 市场**: {regime}"
                        ),
                    },
                },
                {"tag": "hr"},
                {"tag": "markdown", "content": f"**🛡️ Stability (v3.6)**\n{stab_lines}"},
                {"tag": "markdown", "content": f"**Strategy Allocation**\n{strat_lines}"},
                {"tag": "markdown", "content": f"**Top Holdings**\n{holdings_lines}"},
                {"tag": "markdown", "content": f"**Risk Contribution**\n{risk_lines}"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "markdown",
                        "content": f"**Recommendation**\n→ {s.get('recommendation', 'hold')}",
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": keyword_footer()}
                    ],
                },
            ],
        },
    }


def send_fund_card(report: dict) -> dict:
    """发送基金日报到飞书。"""
    card_text = ensure_keyword(build_fund_card(report))
    result = {"sent": False, "text": card_text, "webhook_configured": is_configured()}

    if is_configured():
        post = _post_feishu(build_fund_card_json(report))
        result.update(post)
    return result


def save_fund_card(report: dict, path: str = "docs/fund_report.md") -> str:
    """保存基金日报到文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = build_fund_card(report)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.abspath(path)
