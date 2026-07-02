# EcohTangoFoxtra v3.6 Final 系统规格说明书（稳定化收敛版）

> 📅 封版日期: 2026-07-02
> 版本: v3.1 + v3.2 + v3.3 + v3.4 + v3.5 + **v3.6 Final**
> 状态: **FROZEN — 功能冻结，仅允许参数微调 / 稳定性抑制 / UI 展示**

---

## 🔒 封版声明

从本版本起，**核心策略逻辑 + 功能模块已完全冻结**。
v3.6 Final 进入稳定化收敛模式：**不再新增功能/模块/策略/指标**。

### v3.6 Final 收敛规则

| ❌ 永久禁止 | ✅ 唯一允许 |
|-----------|-----------|
| 新策略 / 新指标 / 新模块 | 参数微调（threshold, risk multiplier, smoothing α, rebalance frequency） |
| 新回测框架 / 新资产类别 | 稳定性抑制（降频、过滤、连亏保护、高波动减仓） |
| 核心逻辑修改 | UI / 飞书 / Streamlit 展示 |

---

## 📐 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                   UI / 展示层                            │  ✅ 唯一可修改层
│    docs/   frontend/streamlit_app.py   feishu_lite.py   │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│         基金管理层（v3.4 + v3.5 + v3.6 Stability）       │  ✅ 仅参数微调
│  risk_budget_engine  strategy_pool  strategy_weight_    │
│  allocator  portfolio_constructor  risk_parity_engine   │
│  rebalance_engine  fund_manager (稳定层编排)              │
│  · 风险预算  · 多策略组合  · 风险平价  · 稳定抑制     │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│         策略外挂层（v3.3 Strategy Intelligence）        │  ✅ 可调整参数
│  regime_detector.py  drift_monitor.py                  │
│  threshold_suggester.py  strategy_health.py             │
│  · 市场状态识别  · 策略漂移检测  · 阈值建议  · 健康评分│
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               运行层（v3.1 Paper Trading）              │  🔒 FROZEN
│           paper_trading.py  (v3.1 封版规则)             │
│  · 单标最大仓位 25%  · 单日变动上限 10%  · 最低现金 10% │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               分析层（v3.2 回测 + 评估）                 │  🔒 FROZEN
│       backtest_engine.py  strategy_evaluation.py        │
│  · 历史回测  · Walk-Forward  · 策略评分  · 信号漂移    │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               决策层（v3.1 L5）                          │  🔒 FROZEN
│            portfolio_engine.py                            │
│  · BUY ≥75 / HOLD 50-74 / REDUCE <50                  │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               轮动层（v3.1 L4）                          │  🔒 FROZEN
│              rotation_engine.py                           │
│  · 主线池 / 观察池 / 淘汰池  · 板块轮动信号            │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               状态层（v3.1 L3）                          │  🔒 FROZEN
│              market_regime.py                             │
│  · BULL ≥60% / ROTATION / DEFENSIVE <40%             │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               信号层（v3.1 L2）                          │  🔒 FROZEN
│              signal_engine.py                             │
│  · trend_score / flow_score / risk_score               │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               数据层（v3.1 L1）                          │  🔒 FROZEN
│              data_engine.py                               │
│  · AKShare 实时行情  · Sina K线  · 指标计算           │
└──────────────────────────────────────────────────────────┘
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
| 数据回填 | `backend/backfill_engine.py` | Sina API 数据拉取逻辑 |
| 回测数据 | `backend/backtest.db` | 价格历史数据库 |

---

## ✅ 允许修改的层（UI / 展示层 + 策略外挂层）

| 目录/文件 | 允许操作 |
|---------|---------|
| `docs/` | 页面样式、图表展示、排版、字段重组 |
| `frontend/` | 任何展示层改动（Streamlit 页面、图表等） |
| `backend/feishu_lite.py` | 飞书卡片样式、格式 |
| `backend/feishu_reporter.py` | 飞书消息格式 |
| `backend/regime_detector.py` | v3.3：指标阈值调整（只读数据，不改核心） |
| `backend/drift_monitor.py` | v3.3：漂移检测参数（只读数据，不改核心） |
| `backend/threshold_suggester.py` | v3.3：阈值建议参数（只输出建议，不改核心） |
| `backend/strategy_health.py` | v3.3：评分维度权重（只读数据，不改核心） |
| `backend/risk_budget_engine.py` | v3.4：风险预算参数（只读数据，不改核心） |
| `backend/strategy_pool.py` | v3.5：策略池定义（元数据，不改信号） |
| `backend/strategy_weight_allocator.py` | v3.5：策略权重分配参数 |
| `backend/portfolio_constructor.py` | v3.5：组合构建参数 |
| `backend/risk_parity_engine.py` | v3.5：风险平价参数 |
| `backend/rebalance_engine.py` | v3.5：再平衡阈值 |
| `backend/fund_manager.py` | v3.4+v3.5：编排层 |
| `main_lite.py` | 新增命令行参数（仅添加，不修改已有逻辑调用） |

> ⚠️ **v3.3 策略外挂层虽可调整参数，但不得修改核心策略逻辑。**
> 实际交易仍使用封版的 BUY ≥75 / HOLD 50-74 / REDUCE <50 规则。

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

---

## 📊 v3.2 回测 + 评估规则（冻结）

### BacktestEngine

```
回测区间: 可配置（默认最近1年）
基准: HS300 (510300)
输出:
  - Total Return (%)
  - CAGR (%)
  - Max Drawdown (%)
  - Sharpe Ratio / Sortino Ratio
  - Annual Volatility (%)
  - Win Rate (%)
  - Benchmark Comparison (alpha %)
```

### WalkForwardEngine

```
训练窗口: 504 交易日 (~2年)
测试窗口: 63 交易日 (~3个月)
滚动步长: 21 交易日 (~1个月)
输出:
  - Consistency Score (0-10)
  - Stable Periods count
  - Overfit Risk: LOW / MEDIUM / HIGH
  - Avg Test Return / Sharpe
```

---

## 📊 v3.3 策略外挂层（Strategy Intelligence）

### 模块说明

| 模块 | 功能 | 原则 |
|------|------|------|
| `regime_detector.py` | 市场状态分类：Bull / Bear / Sideways / HighVolatility | 只读数据 |
| `drift_monitor.py` | 策略漂移检测：落后基准触发警告 | 只读数据 |
| `threshold_suggester.py` | 自适应阈值建议：按市场状态建议 BUY/HOLD 阈值 | 只输出建议 |
| `strategy_health.py` | 健康评分 + 分状态回测 + Intelligence Report | 只读数据 |

### Regime Detector（市场状态识别）

```
输入: price_history (close, ma20, ma60)
指标: MA斜率 / 收益率 / 波动率 / 动量背离 / 最大回撤
输出: {regime, confidence, indicators, regime_scores}
```

| 市场状态 | 特征 |
|---------|------|
| Bull | MA20向上 + 正收益 + MA20>MA60 + 动量加速 |
| Bear | MA20向下 + 负收益 + 回撤扩大 + 动量背离 |
| Sideways | 均线走平 + 收益接近零 |
| HighVolatility | 高波动率（与方向无关） |

### Drift Monitor（策略漂移检测）

```
触发条件:
  - 策略收益 < 基准收益 - 2% AND 胜率 < 45% → 漂移警告
  - 仅落后但幅度较小 → 轻微漂移

输出: {drifting, severity, underperformance, recommendation}
```

### Adaptive Threshold Suggester（自适应阈值建议）

| 市场状态 | BUY 阈值 | HOLD 阈值 | 理由 |
|---------|---------|---------|------|
| Bull 🐂 | 70 | 48 | 牛市降低门槛，更多持仓 |
| Sideways ↔️ | 75 | 50 | 维持标准（默认） |
| Bear 🐻 | 80 | 55 | 提高门槛，减少错误买入 |
| HighVol ⚡ | 78 | 52 | 高波动增加确认 |

### Strategy Health Score（策略健康评分）

| 维度 | 满分 | 评分依据 |
|------|------|---------|
| Alpha (超额收益) | 10 | 年化超额 vs 基准，每1% alpha +1分 |
| Stability (稳定性) | 10 | 月度收益波动率，越低越好 |
| Drawdown Control (回撤) | 10 | 最大回撤，-5% = 10分 |
| Robustness (鲁棒性) | 10 | 跨状态胜率均衡性 |

等级：A+ (≥9) / A (≥8) / B (≥7) / C (≥6) / D (<6)

---

## 📊 v3.4 风险预算层（Risk Budget Engine）

### 核心目标

> 决定组合最多允许承担多少风险，而非"买什么"

### 输入 / 输出

```
输入: portfolio volatility, drawdown trend, regime, strategy confidence
输出: {total_risk_budget, regime_multiplier, max_single_asset_risk}
```

| 市场状态 | 风险预算 |
|---------|---------|
| Bull | 6–8% |
| Sideways | 4–6% |
| Bear | 2–3% |
| HighVolatility | 3–4% |

---

## 📊 v3.5 组合构建层（Portfolio Construction）

### Strategy Pool

| 策略 | 资产 | 逻辑 |
|------|------|------|
| Trend Following | 510300, 513100 | 宽基 + 跨境趋势 |
| Mean Reversion | 513050, 512690 | 跨境 + 消费回归 |
| Momentum | 159915, 588000 | 创业板 + 科创动量 |

### Strategy Weight Allocator

```
weight ∝ strategy_score × stability × regime_fit × recent 近期表现
```

### Portfolio Constructor

```
final_weight = strategy_weight × asset_hint × inverse_volatility × risk_budget_scale
```

### Risk Parity Layer

```
risk_contribution per asset ≈ equal
```

### Rebalance Engine

```
触发: 权重偏离 ≥5% (v3.6) / regime shift / 最短间隔 5 天
输出: increase / reduce / hold 信号 + recommendation
```

---

## 📊 v3.6 稳定层（Final — 降噪 + 长期运行）

### 核心目标

> 提高长期稳定性，而非追求短期收益

### 稳定层机制（嵌入 fund_manager，无新模块）

| 机制 | 参数 | 作用 |
|------|------|------|
| 低质量信号过滤 | min_strategy_score=45 | 抑制弱策略权重 |
| 权重 EMA 平滑 | α=0.30 | 降低调仓频率 |
| 再平衡节流 | min_rebalance_days=5, drift≥5% | 最多周频再平衡 |
| 连亏保护 | 3天连亏 → ×0.85 | 自动缩减风险预算 |
| 高波动减仓 | vol>1.8% → ×0.90 | 波动过高时降暴露 |

### 预期效果

| 指标 | v3.6 预期 |
|------|----------|
| 收益 | 略降或持平 |
| 回撤 | 明显下降 |
| Win rate | 上升 |
| Sharpe | 上升（目标 >1） |
| 交易频率 | 明显下降 |

### 日常运营节奏

```
每日: Paper Portfolio + Risk Report + Health Score
每周: 回撤 / Sharpe / Regime 表现
每月: 参数微调（唯一允许动作）
```

### 每日运行管线（最终形态）

```
每日数据 → 信号 → 过滤 → 风险预算 → 组合调整 → 模拟盘 → 记录 → 日报
```

---

## 🖥️ UI / Streamlit Dashboard

### 启动方式

```bash
# 方式1: 默认端口 8501
streamlit run frontend/streamlit_app.py

# 方式2: 指定端口
streamlit run frontend/streamlit_app.py --server.port 8502
```

### Dashboard 页面

```
/intelligence    ← 策略智能报告（Regime + Drift + 阈值建议）
/fund            ← 基金组合管理（v3.4+v3.5：风险预算 + 策略权重 + 再平衡）
/health          ← 策略健康评分（雷达图 + 四维评分）
/backtest        ← 历史回测（收益曲线 + 交易记录）
/signals         ← 实时信号（评分排名 + 操作建议）
```

---

## 🚀 CLI 命令总览

```bash
# ── 每日运行（自动化保持不变）─────────────────────────────
python main_lite.py --paper --report      # 每日收盘运行

# ── v3.2 回测系统 ───────────────────────────────────────
python main_lite.py --backfill            # 回填历史数据（一次性）
python main_lite.py --backtest            # 历史回测（秒级）
python main_lite.py --walkforward         # Walk-Forward 验证
python main_lite.py --evaluate            # 策略评分 + 信号漂移

# ── v3.4+v3.5 基金组合管理 ─────────────────────────────
python main_lite.py --fund               # 基金组合日报
python main_lite.py --fund --feishu      # + 飞书基金日报

# ── v3.3 智能监控 ───────────────────────────────────────
python main_lite.py --intelligence        # 轻量智能报告
python main_lite.py --intelligence-full   # 完整智能报告
streamlit run frontend/streamlit_app.py    # Web Dashboard

# ── v3.6 每日自动化 ───────────────────────────────────────
python3 scripts/daily_run.py                  # 每日一次（本地）
./scripts/daily_run_retry.sh                  # 失败每小时重试直到成功
python3 scripts/daily_run.py --check-only     # 检查今日是否已成功

# GitHub Actions: .github/workflows/daily-report.yml
#   工作日 16:30–22:30 北京时间，每小时触发，成功后自动跳过
#   需在 repo Secrets 配置 FEISHU_WEBHOOK_URL

# 本地开发后务必 push 到 GitHub，Actions 才能跑到最新代码:
#   git add -A && git commit -m "..." && git push origin main

# ── 其他 ────────────────────────────────────────────────
python main_lite.py --reset               # 重置模拟账户
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
│   ├── backfill_engine.py        🔒 v3.2 历史数据回填
│   ├── strategy_evaluation.py    🔒 v3.2 策略评估
│   ├── regime_detector.py        ✅ v3.3 市场状态识别
│   ├── drift_monitor.py          ✅ v3.3 策略漂移检测
│   ├── threshold_suggester.py    ✅ v3.3 自适应阈值建议
│   ├── strategy_health.py         ✅ v3.3 健康评分 + 综合报告
│   ├── risk_budget_engine.py      ✅ v3.4 风险预算引擎
│   ├── strategy_pool.py           ✅ v3.5 多策略注册池
│   ├── strategy_weight_allocator.py ✅ v3.5 策略权重分配
│   ├── portfolio_constructor.py   ✅ v3.5 组合构建
│   ├── risk_parity_engine.py      ✅ v3.5 风险平价
│   ├── rebalance_engine.py        ✅ v3.5 再平衡引擎
│   ├── fund_manager.py            ✅ v3.4+v3.5 编排层
│   ├── feishu_lite.py            ✅ 飞书卡片（展示层）
│   ├── feishu_reporter.py        ✅ 飞书消息（展示层）
│   └── backtest.db               🔒 SQLite 历史数据
├── frontend/
│   └── streamlit_app.py          ✅ v3.5 Streamlit Dashboard（含 /fund）
├── docs/
│   ├── index.html                ✅ GitHub Pages 入口
│   ├── lite_card.md              ✅ 飞书决策卡
│   ├── backtest_report.html      ✅ 回测可视化报告
│   ├── fund_report.md            ✅ 基金组合日报
│   └── SPEC.md                   ← 系统宪法
├── main_lite.py                  ← 统一入口（v3.5）
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
| **v3.3** | **2026-07-02** | **新增：Regime Detector + Drift Monitor + Threshold Suggester + Strategy Health + Streamlit Dashboard** |
| **v3.4** | **2026-07-02** | **新增：Risk Budget Engine — regime → 风险预算映射** |
| **v3.5** | **2026-07-02** | **新增：Strategy Pool + Weight Allocator + Portfolio Constructor + Risk Parity + Rebalance + /fund Dashboard** |
| **v3.6 Final** | **2026-07-02** | **稳定化收敛：信号过滤 + 权重平滑 + 再平衡节流 + 连亏保护 + 功能冻结** |

---

*本文件为系统宪法，所有代码修改必须与本规格保持一致。*
*如有疑问，先看 SPEC.md。*
