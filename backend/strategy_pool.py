"""
strategy_pool.py — EcohTangoFoxtra v3.5
多策略注册池：Trend / Mean Reversion / Momentum

封版原则：只定义策略元数据与资产映射，不修改信号生成逻辑。
"""

from typing import Optional

# 策略 → 资产映射（对应设计文档 VOO/QQQ/VXUS 的 A 股 ETF 等价物）
STRATEGY_DEFINITIONS = {
    "trend": {
        "id": "trend",
        "name": "Trend Following",
        "name_cn": "趋势跟踪",
        "description": "宽基 + 跨境趋势跟踪（510300/513100）",
        "assets": [
            {"code": "510300", "name": "沪深300ETF", "weight_hint": 0.6},
            {"code": "513100", "name": "纳指ETF", "weight_hint": 0.4},
        ],
        "regime_fit": {
            "Bull": 1.0, "Sideways": 0.6, "Bear": 0.3,
            "HighVolatility": 0.5, "Unknown": 0.5,
        },
    },
    "mean_reversion": {
        "id": "mean_reversion",
        "name": "Mean Reversion",
        "name_cn": "均值回归",
        "description": "跨境 + 消费均值回归（513050/512690）",
        "assets": [
            {"code": "513050", "name": "中概互联ETF", "weight_hint": 0.55},
            {"code": "512690", "name": "酒ETF", "weight_hint": 0.45},
        ],
        "regime_fit": {
            "Bull": 0.5, "Sideways": 1.0, "Bear": 0.7,
            "HighVolatility": 0.8, "Unknown": 0.6,
        },
    },
    "momentum": {
        "id": "momentum",
        "name": "Momentum",
        "name_cn": "动量突破",
        "description": "创业板 + 科创50 动量（159915/588000）",
        "assets": [
            {"code": "159915", "name": "创业板ETF", "weight_hint": 0.55},
            {"code": "588000", "name": "科创50ETF", "weight_hint": 0.45},
        ],
        "regime_fit": {
            "Bull": 1.0, "Sideways": 0.4, "Bear": 0.2,
            "HighVolatility": 0.6, "Unknown": 0.4,
        },
    },
}

# 防守资产（不参与策略竞争，由组合构建层分配）
DEFENSIVE_ASSETS = [
    {"code": "518880", "name": "黄金ETF"},
    {"code": "510880", "name": "红利ETF"},
]


def get_strategy(strategy_id: str) -> Optional[dict]:
    return STRATEGY_DEFINITIONS.get(strategy_id)


def list_strategies() -> list[dict]:
    return list(STRATEGY_DEFINITIONS.values())


def get_all_asset_codes() -> list[str]:
    codes = set()
    for s in STRATEGY_DEFINITIONS.values():
        for a in s["assets"]:
            codes.add(a["code"])
    for a in DEFENSIVE_ASSETS:
        codes.add(a["code"])
    return sorted(codes)


def get_regime_fit(strategy_id: str, regime: str) -> float:
    s = STRATEGY_DEFINITIONS.get(strategy_id, {})
    return s.get("regime_fit", {}).get(regime, 0.5)
