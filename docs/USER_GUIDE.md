# EcohTangoFoxtra 使用说明书（v3.6）

> 面向日常使用者：每天该买什么、该卖什么、怎么录入自己的交易。

---

## 一、这个系统能帮你回答什么？

| 你的问题 | 看哪里 | 核心结论 |
|---------|--------|---------|
| **现在适合买哪个板块？** | 决策卡 `lite_card.md` / 飞书 | 市场状态 + 主线板块 + 加仓名单 |
| **具体买哪几只 ETF？** | 决策卡「操作」+ Streamlit `/signals` | 评分最高的 BUY 标的 |
| **我持有的要不要卖？** | 决策卡 + `/fund` 再平衡 | REDUCE / 淘汰池 + Rebalance Signal |
| **组合层面怎么配？** | `fund_report.md` / Streamlit `/fund` | 策略权重 + Top Holdings + 风险 |
| **我的真实持仓在哪？** | Streamlit `/持仓录入` 或 CLI | 手动录入后系统会对账 |

**重要：** 这是 **研究/模拟框架**，输出是「模型建议」，不是自动下单。

---

## 二、每天 3 分钟流程（推荐）

### 收盘后（16:30 以后）

**1. 看飞书消息**（GitHub Actions 自动推送）

或本地运行：

```bash
cd EcohTangoFoxtra
python3 main_lite.py --paper --report --feishu
python3 main_lite.py --fund --feishu
```

**2. 打开决策卡** — `docs/lite_card.md`

示例：

```text
【🟡 轮动】市场主线:broad + ai
仓位 60%权益 / 18%防御 / 22%现金

操作:
➕ 中证500ETF 加(48)
➕ 游戏ETF 加(39)
```

**3. 打开基金日报** — `docs/fund_report.md`

看 Regime、Top Holdings、Rebalance Signal。

**4. 对照你的持仓** — 决定是否跟单

```bash
python3 scripts/record_trade.py list
```

**5. 若实际交易了，录入系统**

```bash
python3 scripts/record_trade.py buy 510500 1000 8.85
python3 scripts/record_trade.py sell 159869 900 1.10
```

---

## 三、怎么读「该买哪个板块」

### 3.1 三层信息

```text
L3 市场状态  →  今天整体偏进攻还是防守？
L4 板块轮动  →  哪个 sector 在走强/走弱？
L5 个股决策  →  具体哪只 ETF 加/减/持？
```

### 3.2 市场状态（决策卡第一行）

| 显示 | 含义 | 板块策略 |
|------|------|---------|
| 🟢 **主升** (bull) | 趋势向上 | 偏宽基、科技，可积极加仓 |
| 🟡 **轮动** (rotation) | 震荡分化 | 只加「主线」，不追弱势 |
| 🔴 **防守** (defensive) | 风险期 | 减成长，加红利/黄金 |

**主线** 如 `broad + ai` 表示当前模型认为 **宽基 + AI/科技** 相对最强。

### 3.3 板块中英文对照

| 代码 | 中文 | 代表 ETF |
|------|------|---------|
| broad | 宽基 | 沪深300、中证500、创业板 |
| ai | AI/科技 | 游戏、软件、人工智能、5G |
| health | 医药 | 医疗、恒生医疗 |
| consumer | 消费 | 酒、消费、家电 |
| dividend | 红利/防守 | 红利、银行 |
| energy | 新能源 | 光伏、新能源车 |
| overseas | 跨境 | 纳指、中概互联 |
| commodity | 商品 | 黄金、豆粕 |

### 3.4 轮动箭头

```text
轮动 跨境 ↓ | 消费 ↓ | 新能源 ↓
```

→ 这些板块相对走弱，**不宜新开仓或应减仓**。

### 3.5 三层池子（Streamlit `/signals` 更全）

| 层级 | 含义 | 你该怎么做 |
|------|------|-----------|
| 🟢 **主线池** (core) | 评分前 20% | **优先考虑买入** |
| 🟡 **观察池** (watch) | 中间 60% | 持有观望 |
| 🔴 **淘汰池** (reduce) | 后 20% | **考虑卖出** |

---

## 四、怎么读「该卖什么」

### 4.1 决策卡里的信号

| 操作 | 含义 |
|------|------|
| **加** (BUY) | 模型建议增仓 |
| **持** (HOLD) | 维持 |
| **减** (REDUCE) | 模型建议减仓或卖出 |

出现在「操作」里的 **减**，或你在 `/signals` 看到 **🔴 淘汰池** 的标的 → 优先检查是否卖出。

### 4.2 基金日报里的 Rebalance Signal

`docs/fund_report.md` 末尾：

```text
Rebalance Signal:
  → reduce 159869 9.9%    # 游戏ETF 减 9.9%
  → increase 510880 20.1% # 红利ETF 加 20.1%
```

这是 **组合层面** 的建议：对比「目标仓位」与「你当前持仓」（需先录入真实持仓）。

### 4.3 结合 Regime 判断

| Regime | 卖出倾向 |
|--------|---------|
| Bear | 减成长、减高波动（游戏、科创、新能源） |
| Sideways | 卖弱势板块，保留主线 |
| Bull | 仅卖淘汰池，主线可留 |

---

## 五、基金层（组合视角）

打开 `docs/fund_report.md` 或 Streamlit **🏦 Fund**：

| 字段 | 含义 |
|------|------|
| Portfolio Risk | 当前允许的组合风险预算 |
| Regime | Bull / Bear / Sideways（与 L3 不同口径，偏长期） |
| Strategy Allocation | 趋势 / 均值回归 / 动量 三策略权重 |
| Top Holdings | 模型理想持仓比例 |
| Risk Contribution | HIGH/MED/LOW 风险贡献 |
| Recommendation | 是否需再平衡 |

**用法：** 当你已录入真实持仓，Rebalance 会告诉你「相对目标偏多了什么、偏少了什么」。

---

## 六、所有入口一览

### 6.1 命令行

| 命令 | 作用 |
|------|------|
| `python3 main_lite.py` | 仅跑分析，打印摘要 |
| `python3 main_lite.py --paper --report --feishu` | 完整日报 + 模拟盘 + 飞书 |
| `python3 main_lite.py --fund --feishu` | 基金组合日报 |
| `python3 scripts/daily_run.py` | 一键每日全流程 |
| `python3 scripts/record_trade.py list` | **查看我的持仓** |
| `python3 scripts/record_trade.py buy CODE 股数 价格` | **录入买入** |
| `python3 scripts/record_trade.py sell CODE 股数 价格` | **录入卖出** |
| `python3 main_lite.py --reset` | 重置模拟账户（慎用） |

### 6.2 网页 / 可视化

```bash
streamlit run frontend/streamlit_app.py
```

| Tab | 路径概念 | 内容 |
|-----|---------|------|
| Intelligence | /intelligence | 市场 Regime、漂移、健康分 |
| Fund | /fund | 组合、风险、再平衡 |
| 健康评分 | /health | 策略四维评分 |
| 回测 | /backtest | 历史曲线 |
| 信号 | /signals | 全 ETF 排名与 BUY/HOLD/REDUCE |
| **持仓录入** | /portfolio | **买入/卖出/现金对账** |

### 6.3 静态报告（GitHub Pages / 本地文件）

| 文件 | 内容 |
|------|------|
| `docs/lite_card.md` | 每日决策卡（买卖什么） |
| `docs/fund_report.md` | 基金组合日报 |
| `docs/index.html` | 可视化决策面板 |

### 6.4 飞书

配置 `.env` 中 `LARK_PUSH_CFG` 后，每日自动收 text 版决策卡。

---

## 七、录入交易（更新持仓）— 详细步骤

系统默认跑的是 **模拟盘**（`paper_state.json`）。你可以用同一文件记录 **真实持仓**，供再平衡对比。

### 7.1 方式 A：网页（推荐）

1. `streamlit run frontend/streamlit_app.py`
2. 打开 **📝 持仓录入**
3. 买入：选 ETF → 股数 → 价格 → 确认买入
4. 卖出：选持仓 → 股数 → 价格 → 确认卖出
5. 现金对账：输入券商账户实际现金 → 更新现金

### 7.2 方式 B：命令行

```bash
# 查看持仓
python3 scripts/record_trade.py list

# 买入 510300 沪深300ETF，1000股，成交价 4.850
python3 scripts/record_trade.py buy 510300 1000 4.850

# 卖出 159869 游戏ETF，900股，成交价 1.100
python3 scripts/record_trade.py sell 159869 900 1.100

# 设置现金为 50000（与券商对账）
python3 scripts/record_trade.py cash 50000
```

**规则：**

- 股数必须是 **100 的整数倍**（A 股 ETF 整手）
- 买入会扣减现金；卖出会增加现金
- 多次买入同一标的会自动算 **加权平均成本**
- 交易记录追加到 `backend/manual_trades.jsonl`（本地，不进 git）

### 7.3 录入后如何影响建议？

下次运行 `python3 main_lite.py --fund` 时：

- `fund_manager` 读取 `paper_state.json` 作为 **当前持仓**
- 与 **目标组合** 对比 → 生成 Rebalance Signal
- 你会看到类似 `reduce 159869`（你游戏 ETF 超配了）

### 7.4 模拟盘 vs 真实录入

| | 模拟盘 `--paper` | 手动录入 |
|--|-----------------|---------|
| 触发 | 每日自动按模型买卖 | 你按真实成交录入 |
| 文件 | 同 `paper_state.json` | 同 `paper_state.json` |
| 建议 | 二选一为主：要么跟模拟，要么只用手动录入 |

**推荐：** 真实投资 → **只用手动录入**，不要同时跑 `--paper` 自动交易，避免覆盖你的持仓。

```bash
# 真实用户推荐每日命令（不自动模拟买卖）
python3 main_lite.py --report --feishu
python3 main_lite.py --fund --feishu
```

---

## 八、实战解读示例

### 场景：决策卡显示

```text
【🟡 轮动】主线:broad + ai
➕ 中证500ETF 加(48)
➕ 游戏ETF 加(39)
轮动 跨境 ↓ | 消费 ↓
```

**解读：**

1. 市场震荡，不要满仓追单一赛道
2. **可考虑买入**：宽基（中证500）+ 科技（游戏）— 评分相对高
3. **暂不碰 / 考虑减仓**：跨境、消费相关 ETF
4. 打开 `/signals` 确认游戏 ETF 是否在主线池；若在淘汰池则不要买

### 场景：你持有游戏 ETF，日报写

```text
→ reduce 159869 9.9%
Regime: Bear
```

**解读：** 模型认为游戏 ETF 相对目标超配 9.9%，且市场偏 Bear → **优先考虑减仓或卖出**。

---

## 九、自动化（可选）

| 方式 | 命令 / 配置 |
|------|------------|
| GitHub Actions | 工作日 16:30–22:30 自动跑，飞书推送 |
| 本地 cron | `./scripts/daily_run_retry.sh` |
| 手动 | `python3 scripts/daily_run.py` |

详见 `docs/SPEC.md` CLI 章节。

---

## 十、常见问题

**Q: 飞书没收到消息？**  
A: 检查 `LARK_PUSH_CFG`；日志须显示 `飞书发送成功 (text)`。

**Q: 决策卡和 Fund 报告 Regime 不一致？**  
A: 正常。决策卡用 L3（bull/rotation/defensive），Fund 用 v3.3  detector（Bull/Bear/Sideways），口径不同。

**Q: 录入持仓后 Rebalance 没变化？**  
A: 需再跑 `python3 main_lite.py --fund`；且偏离 <5% 时 v3.6 可能节流不提示。

**Q: 会被 Sina 封 IP 吗？**  
A: 已默认每次请求间隔 0.8s；可在 `.env` 设 `SINA_REQUEST_DELAY=1.2` 加大间隔。

**Q: 如何从零初始化持仓？**  
A: 用 `record_trade.py buy` 逐笔录入，或 `cash` 设现金后分批 buy。

---

## 十一、文件速查

```
docs/lite_card.md      ← 今天买什么/卖什么（必看）
docs/fund_report.md    ← 组合与再平衡（必看）
docs/USER_GUIDE.md     ← 本说明书
docs/SPEC.md           ← 技术规格（开发者）

scripts/record_trade.py   ← 交易录入 CLI
scripts/daily_run.py      ← 每日一键运行
frontend/streamlit_app.py   ← 可视化 + 持仓录入

backend/paper_state.json  ← 你的持仓（本地，gitignore）
.env                      ← 飞书等配置（本地，gitignore）
```

---

## 十二、一句话总结

> **每天看决策卡定方向，看 Fund 报告定比例，用持仓录入对齐 reality，再按 Rebalance 决定卖什么。**

⚠️ 本系统所有输出仅供参考，不构成投资建议。实盘决策请结合你自己的风险承受能力。
