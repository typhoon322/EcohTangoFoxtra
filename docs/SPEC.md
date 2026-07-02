# EcohTangoFoxtra v3.1 + v3.2 系统规格说明书（封版版）

> 📅 封版日期: 2026-07-02
> 版本: v3.1 + v3.2
> 状态: **FROZEN — 核心逻辑已冻结，唯一可修改层为 UI/展示层**

---

## 🔒 封版声明

从本版本起，**核心策略逻辑已完全冻结**。
任何对以下模块的修改必须经过完整评审流程（issue → review → approval），
除非是 bug fix。

---

## 📐 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   UI / 展示层                         │  ✅ 唯一可修改层
│         docs/          frontend/       feishu_lite.py │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│              运行层（v3.1 Paper Trading）              │  🔒 FROZEN
│           paper_trading.py  (v3.1 封版规则)            │
│  · 单标最大仓位 25%  · 单日变动上限 10%  · 最低现金 10% │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               分析层（v3.2 回测 + 评估）               │  🔒 FROZEN
│       backtest_engine.py  strategy_evaluation.py      │
│  · 历史回测  · Walk-Forward  · 策略评分  · 信号漂移    │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               决策层（v3.1 L5）                        │  🔒 FROZEN
│            portfolio_engine.py                        │
│  · BUY ≥75 / HOLD 50-74 / REDUCE <50                  │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               轮动层（v3.1 L4）                        │  🔒 FROZEN
│              rotation_engine.py                       │
│  · 主线池 / 观察池 / 淘汰池  · 板块轮动信号           │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               状态层（v3.1 L3）                        │  🔒 FROZEN
│              market_regime.py                         │
│  · BULL ≥60% / ROTATION / DEFENSIVE <40%             │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               信号层（v3.1 L2）                        │  🔒 FROZEN
│              signal_engine.py                         │
│  · trend_score  · flow_score  · risk_score            │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│               数据层（v3.1 L1）                        │  🔒 FROZEN
│              data_engine.py                           │
│  · AKShare 实时行情  · Sina K线  · 指标计算           │
└─────────────────────────────────────────────────────┘
```

---

## 🔒 冻结模块清单

| 模块 | 文件 | 冻结内容 |
|------|------|---------|
| L1 数据层 | `backend/data_engine.py` | 全部逻辑（数据源、指标计算） |
| L2 信号评分 | `backend/signal_engine.py` | trend_score / flow_score / risk_score 公式 |
| L3 市场状态 | `backend/market_regime.py` | BULL / ROTATION / DEFENSIVE 判定规则 |
| L4 轮动分析 | `backend/rotation_engine.py` | 池划分（主线/观察/淘汰）比例 |
| L5 组合决策 | `backend/portfolio_engine.py` | BUY/HOLD/REDUCE 阈值、权重计算 |
| 模拟盘引擎 | `backend/paper_trading.py` | **最大仓位25% / 单日10% / 最低现金10%** 三规则 |
| 回测引擎 | `backend/backtest_engine.py` | 回测引擎核心逻辑 |
| 策略评估 | `backend/strategy_evaluation.py` | 评分卡维度、信号漂移阈值 |
| 数据存储 | `backend/backtest_store.py` | SQLite schema |

---

## ✅ 允许修改的层（UI / 展示层）

| 目录/文件 | 允许操作 |
|---------|---------|
| `docs/` | 页面样式、图表展示、排版、字段重组 |
| `frontend/` | 任何展示层改动 |
| `backend/feishu_lite.py` | 飞书卡片样式、格式 |
| `backend/feishu_reporter.py` | 飞书消息格式 |
| `main_lite.py` | 新增命令行参数（仅添加，不修改已有逻辑调用） |

---

## 🚫 禁止修改的规则（即使看起来不合理）

1. **单标最大仓位 = 25%**（`MAX_POSITION_PCT = 0.25`）
2. **单日变动上限 = 10%**（`MAX_DAILY_CHANGE = 0.10`）
3. **最低现金 = 10%**（`MIN_CASH_PCT = 0.10`）
4. **趋势评分权重**：MA结构 40% / MACD 30% / RSI 20% / 方向 10%
5. **信号漂移阈值**：评分差 < -8 → HIGH / < -4 → MEDIUM
6. **市场状态阈值**：趋势比 > 60% → BULL / < 40% → DEFENSIVE
7. **买入/持有/卖出阈值**：≥75 BUY / 50-74 HOLD / <50 SELL

---

## 📊 v3.1 模拟盘规则（冻结）

```python
# backend/paper_trading.py
MAX_POSITION_PCT = 0.25    # 单标的最大仓位 25%
MAX_DAILY_CHANGE = 0.10    # 单日变动上限 10%
MIN_CASH_PCT = 0.10        # 最低现金 10%
```

### 交易规则

- **BUY**: 达到目标仓位，每次最多投入 gap（受限每日上限）
- **HOLD**: 不操作
- **REDUCE**: 卖出50%；盈利>5%时清仓
- **整手**: 100股/手
- **评分强度**: 分配仓位时参考 final_score

### 评分维度（冻结）

```
final_score = 0.5 * trend_score + 0.3 * flow_score - 0.2 * risk_score
```

| 维度 | 权重 | 说明 |
|------|------|------|
| trend_score | 50% | MA结构 + MACD + RSI |
| flow_score | 30% | 成交量 + 波动扩张 + 连涨 |
| risk_score | -20% | 回撤 + 偏离度 + 波动率 |

---

## 📊 v3.2 回测 + 评估规则（冻结）

### BacktestEngine

```text
回测区间: 可配置（默认最近1年）
基准: HS300 (510300)
输出:
  - Total Return (%)
  - CAGR (%)
  - Max Drawdown (%)
  - Sharpe Ratio
  - Sortino Ratio
  - Annual Volatility (%)
  - Win Rate (%)
  - Benchmark Comparison (alpha %)
```

### WalkForwardEngine

```text
训练窗口: 504 交易日 (~2年)
测试窗口: 63 交易日 (~3个月)
滚动步长: 21 交易日 (~1个月)
输出:
  - Consistency Score (0-10)
  - Stable Periods count
  - Overfit Risk: LOW / MEDIUM / HIGH
  - Avg Test Return / Sharpe
```

### StrategyScoreCard

| 维度 | 满分 | 评分依据 |
|------|------|---------|
| Return Quality | 10 | 年化超额收益 vs 基准 |
| Stability | 10 | 月度收益波动率 |
| Drawdown Control | 10 | 最大回撤 + 恢复速度 |
| Robustness | 10 | 跨市场状态胜率一致性 |

### SignalDriftDetector

```text
触发条件:
  - score_trend < -8 → HIGH alert
  - score_trend < -4 → MEDIUM alert
  - buy_ratio > 80% AND score_trend < 0 → MEDIUM alert

建议操作:
  - reduce_exposure: 降低仓位
  - watch: 密切关注
  - review_buys: 审视买入逻辑
```

---

## 🖥️ UI 页面结构（未来唯一工作区）

```
docs/
├── index.html          ← 主仪表盘（GitHub Pages 入口）
├── lite_card.md        ← 飞书决策卡（每日输出）
├── decision_card.md   ← 完整决策卡（可选）
└── SPEC.md             ← 本文件（系统宪法）
```

### Dashboard 建议布局

```
/dashboard     总资产 + 收益曲线 + 市场状态
/paper         模拟盘组合 + 每日交易记录
/strategy      评分展示 + 信号历史 + 轮动箭头
/backtest      收益曲线 + 风险指标 + Walk-Forward 结果
/evaluate      策略评分卡 + 信号漂移警报
```

---

## 🚀 使用方式

### 每日运行（16:00 自动）
```bash
python main_lite.py --paper --report
```

### 策略评估（按需）
```bash
python main_lite.py --evaluate      # 策略评分 + 信号漂移
python main_lite.py --backtest      # 历史回测
python main_lite.py --walkforward   # Walk-Forward
```

### 模拟盘重置
```bash
python main_lite.py --reset
```

---

## 📁 文件结构

```
EcohTangoFoxtra/
├── backend/
│   ├── data_engine.py           🔒 L1 数据层
│   ├── signal_engine.py          🔒 L2 信号评分
│   ├── market_regime.py         🔒 L3 市场状态
│   ├── rotation_engine.py        🔒 L4 轮动分析
│   ├── portfolio_engine.py       🔒 L5 组合决策
│   ├── paper_trading.py          🔒 v3.1 模拟盘
│   ├── backtest_engine.py        🔒 v3.2 回测引擎
│   ├── backtest_store.py         🔒 v3.2 数据存储
│   ├── strategy_evaluation.py    🔒 v3.2 策略评估
│   ├── feishu_lite.py            ✅ 飞书卡片（展示层）
│   ├── feishu_reporter.py       ✅ 飞书消息（展示层）
│   └── paper_state.json          ← 模拟盘状态（gitignored）
├── frontend/
│   └── index.html                ✅ 展示层
├── docs/
│   ├── index.html                ✅ GitHub Pages 入口
│   ├── lite_card.md              ✅ 飞书决策卡
│   └── SPEC.md                   ← 系统宪法
├── main_lite.py                  ← 统一入口
├── run_pipeline.py               ← v2 旧入口
└── build_report.py               ← 静态报告构建
```

---

## 🔄 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 | 2026-06 | 静态报告 + AKShare 实时行情 |
| v2 | 2026-06 | 5层完整管线 + 飞书集成 |
| v3-lite | 2026-07 | 极简管线 + 模拟盘 + Token节省 |
| **v3.1** | **2026-07-02** | **封版：冻结核心逻辑 + v3.1 模拟盘三规则** |
| **v3.2** | **2026-07-02** | **新增：回测引擎 + Walk-Forward + 策略评分 + 信号漂移检测** |

---

*本文件为系统宪法，所有代码修改必须与本规格保持一致。*
*如有疑问，先看 SPEC.md。*
