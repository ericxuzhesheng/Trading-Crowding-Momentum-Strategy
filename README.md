<h1 align="left">交易拥挤度惩罚的动量轮动策略 | Trading-Crowding Penalized Momentum Rotation</h1>

---

<p align="center">
  <a href="#中文说明"><img src="https://img.shields.io/badge/语言-中文-ff4b3e?style=for-the-badge&labelColor=343a46" alt="中文"></a>
  <a href="#english-description"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2f73c9?style=for-the-badge&labelColor=343a46" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/PYTHON-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=4a4f59" alt="Python">
  <img src="https://img.shields.io/badge/资产池-15个A股指数-f3c63f?style=for-the-badge&labelColor=4a4f59" alt="Universe">
  <img src="https://img.shields.io/badge/评估区间-2020--2026 · 1553日-4caf50?style=for-the-badge&labelColor=4a4f59" alt="Period">
  <img src="https://img.shields.io/badge/主策略-Sharpe%200.35%20%7C%20MaxDD%20--19.98%25-9853e6?style=for-the-badge&labelColor=4a4f59" alt="Performance">
  <img src="https://img.shields.io/badge/LICENSE-MIT-111111?style=for-the-badge&labelColor=4a4f59" alt="MIT">
</p>

---

## 中文说明

### 项目简介

本项目从零实现一个 A 股指数层面的“交易拥挤度 + 动量轮动”策略研究框架。项目自动读取指数日频行情，构建动量、拥挤度和波动率风险指标，进行每周调仓回测，并输出绩效表格、图表和诊断报告。

核心思想不是把拥挤度直接当作买入 alpha，而是把它作为动量策略的风险惩罚项：优先选择短期动量较强、但交易拥挤度和波动率不过高的指数。

### 结果怎么样

本次真实数据运行覆盖 2020-01-02 至 2026-06-05，共 15 个 A 股代表性指数、23325 条日频记录，数据由 Tushare 成功下载。

本轮优化先修复了一个关键回测问题：旧版本在调仓时把 0 权重当作缺失值向前填充，导致已卖出的标的继续保留旧仓位，风险暴露被高估。修复后，卖出标的权重会正确归零；随后将默认组合从 top20% 放宽到 top30%，把趋势过滤均线改为 MA200，并把最终得分参数化为“短动量 + 中期动量确认 - 拥挤度惩罚 - 波动率惩罚”。

| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |
|:--|--:|--:|--:|--:|--:|
| 全指数等权 | 6.31% | 20.22% | 0.31 | -38.93% | 1.482 |
| 纯拥挤度 top30 对照组 | 2.41% | 11.40% | 0.21 | -31.97% | 1.165 |
| 沪深300买入持有 | 2.34% | 18.76% | 0.12 | -45.60% | 1.160 |
| 动量 - 拥挤度惩罚 | 4.19% | 11.29% | 0.37 | -24.10% | 1.302 |
| 动量 - 拥挤度惩罚 + 趋势过滤 | 3.34% | 9.59% | 0.35 | -19.98% | 1.235 |
| 纯 5 日动量 top30 | 3.64% | 11.64% | 0.31 | -24.64% | 1.258 |

解读要点：

- 趋势过滤主策略的最大回撤从旧结果约 -54.6% 降到 -20.0%，风险暴露显著收敛。
- 未加趋势过滤的惩罚动量版本年化 4.19%、Sharpe 0.37，收益高于纯 5 日动量，同时回撤略低。
- 加入 MA200 趋势过滤后年化降至 3.34%，但波动降至 9.59%、最大回撤降至 -19.98%，更适合作为稳健默认配置。
- 全指数等权仍有更高年化收益，说明当前 15 个指数的小样本中，分散化本身仍是强基准。
- 纯拥挤度仍只作为对照组，不作为推荐 alpha；拥挤度在主策略中继续作为风险惩罚项使用。

### 策略逻辑

默认指数池包括沪深300、中证500、中证1000、创业板指、科创50、红利指数、消费、医药、半导体、新能源、军工、金融、地产、传媒、计算机等代表性指数。

因子定义：

- 动量：`ret_5d = close / close.shift(5) - 1`，`ret_20d = close / close.shift(20) - 1`
- 拥挤度：`turnover_z`、`amount_z`、`volume_z` 的 60 日滚动异常程度
- 波动率风险：`vol_20d = rolling_std(daily_return, 20)`
- 复合拥挤度：`rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- 最终得分：`1.0 * rank(ret_5d) + 0.6 * rank(ret_20d) - 0.5 * rank(crowding_score) - 0.1 * rank(vol_20d)`

所有 rank 均为同一天不同指数之间的横截面 percentile rank，并且所有交易信号滞后一日，避免未来函数。

### 数据来源

数据层优先使用 Tushare Pro：

- `pro_bar` / `index_daily`：指数日行情
- 环境变量：`TUSHARE_TOKEN`
- 失败处理：token 缺失、权限不足或接口异常时自动 fallback 到 AKShare

代码不会把 token 写入源码。AKShare fallback 使用指数历史行情接口，并对中英文字段名做统一映射。

### 安装方式

```bash
pip install -r requirements.txt
```

如使用 Tushare：

```bash
set TUSHARE_TOKEN=your_token
```

### 运行方式

```bash
python run_pipeline.py --config config.yaml
```

### 输出文件

- `data/processed/panel_daily.parquet`：统一后的日频 long-format 数据
- `outputs/tables/factor_values.csv`：因子与滞后信号
- `outputs/tables/portfolio_nav.csv`：各策略净值
- `outputs/tables/weekly_weights.csv`：每周调仓权重
- `outputs/tables/turnover.csv`：换手率与交易成本
- `outputs/tables/performance_summary.csv`：绩效汇总
- `outputs/tables/yearly_returns.csv`：年度收益
- `outputs/tables/monthly_returns.csv`：月度收益
- `outputs/reports/backtest_report.md`：自动生成的回测报告

### 主要图表

![NAV comparison](outputs/figures/nav_comparison.png)

![Drawdown](outputs/figures/drawdown.png)

更多图表：

- `outputs/figures/yearly_returns.png`
- `outputs/figures/monthly_return_heatmap.png`
- `outputs/figures/holding_count.png`
- `outputs/figures/turnover.png`
- `outputs/figures/factor_ic.png`

### 项目结构

```text
trading-crowding-momentum-strategy/
├── README.md
├── LICENSE
├── requirements.txt
├── config.yaml
├── run_pipeline.py
├── src/
├── data/
├── outputs/
└── tests/
```

### 局限性

- 指数换手率常常不可得，因此拥挤度会使用成交额、成交量异常作为替代。
- 当前指数池只有 15 个标的，横截面宽度有限。
- 交易成本用 3bp 单边成本近似，未建模冲击成本和真实 ETF 可交易性。
- 最大回撤仍然很深，说明该策略需要进一步风控和样本外验证。
- 趋势过滤规则较简单，在当前样本中没有改善结果。

### 后续优化方向

- 扩展行业、主题和 ETF 可交易池。
- 引入 ETF 份额、资金流、融资融券、北向资金等更直接的拥挤度代理变量。
- 对调仓频率、拥挤度窗口、权重上限和趋势过滤规则做样本外验证。
- 加入容量约束、冲击成本模型和真实 ETF 映射。

---

## English Description

### Overview

This project implements a from-scratch A-share index research framework for a trading-crowding penalized momentum rotation strategy. It downloads daily index data, builds momentum, crowding, and volatility-risk signals, runs weekly rebalancing backtests, and exports performance tables, figures, and diagnostics.

The key idea is not to use crowding directly as alpha. Crowding is used as a risk penalty inside a momentum strategy, favoring indices with positive short-term momentum but less excessive trading activity and volatility.

### Results

The latest real-data run covers 2020-01-02 to 2026-06-05, with 15 representative A-share indices and 23325 daily observations downloaded from Tushare.

This optimization first fixed a critical backtest issue: the old implementation treated zero rebalance weights as missing values and forward-filled them, so sold positions could keep stale weights. After the fix, sold positions correctly reset to zero. The default strategy was then made more robust by widening selection from top20% to top30%, using an MA200 trend filter, and parameterizing the final score as short momentum plus medium-term confirmation minus crowding and volatility penalties.

| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |
|:--|--:|--:|--:|--:|--:|
| All-index equal weight | 6.31% | 20.22% | 0.31 | -38.93% | 1.482 |
| Pure crowding top30 ablation | 2.41% | 11.40% | 0.21 | -31.97% | 1.165 |
| CSI 300 buy and hold | 2.34% | 18.76% | 0.12 | -45.60% | 1.160 |
| Momentum minus crowding penalty | 4.19% | 11.29% | 0.37 | -24.10% | 1.302 |
| Momentum minus crowding penalty plus trend filter | 3.34% | 9.59% | 0.35 | -19.98% | 1.235 |
| Pure 5-day momentum top30 | 3.64% | 11.64% | 0.31 | -24.64% | 1.258 |

Takeaways:

- The trend-filtered main strategy reduced max drawdown from the old roughly -54.6% result to about -20.0%.
- The unfiltered penalized momentum strategy earns 4.19% annualized with a 0.37 Sharpe, beating pure 5-day momentum while slightly reducing drawdown.
- The MA200 trend filter lowers annual return to 3.34%, but also lowers volatility to 9.59% and max drawdown to -19.98%, making it the more conservative default.
- Equal weight remains a strong benchmark in this small 15-index universe, confirming that diversification is valuable.
- Pure crowding remains an ablation only; crowding is used as a risk penalty in the main strategy, not as standalone alpha.

### Strategy Logic

The default universe includes CSI 300, CSI 500, CSI 1000, ChiNext, STAR 50, dividend, consumption, healthcare, semiconductor, new energy, defense, financials, real estate, media, and computer indices.

Signals:

- Momentum: `ret_5d = close / close.shift(5) - 1`, `ret_20d = close / close.shift(20) - 1`
- Crowding proxies: 60-day rolling abnormality in turnover, amount, and volume
- Volatility risk: `vol_20d = rolling_std(daily_return, 20)`
- Composite crowding: `rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- Final score: `1.0 * rank(ret_5d) + 0.6 * rank(ret_20d) - 0.5 * rank(crowding_score) - 0.1 * rank(vol_20d)`

All ranks are same-day cross-sectional percentile ranks. Tradable signals are shifted by one trading day to avoid look-ahead bias.

### Data Sources

The data layer prioritizes Tushare Pro:

- `pro_bar` / `index_daily`: daily index prices
- Environment variable: `TUSHARE_TOKEN`
- Fallback: AKShare when the token is missing, permission is insufficient, or the interface fails

The token is never hard-coded. AKShare fallback normalizes both Chinese and English field names.

### Installation

```bash
pip install -r requirements.txt
```

For Tushare:

```bash
set TUSHARE_TOKEN=your_token
```

### Running

```bash
python run_pipeline.py --config config.yaml
```

### Outputs

- `data/processed/panel_daily.parquet`: normalized long-format daily panel
- `outputs/tables/factor_values.csv`: factor values and lagged signals
- `outputs/tables/portfolio_nav.csv`: strategy NAV series
- `outputs/tables/weekly_weights.csv`: weekly rebalance weights
- `outputs/tables/turnover.csv`: turnover and transaction costs
- `outputs/tables/performance_summary.csv`: performance summary
- `outputs/tables/yearly_returns.csv`: annual returns
- `outputs/tables/monthly_returns.csv`: monthly returns
- `outputs/reports/backtest_report.md`: generated backtest report

### Figures

![NAV comparison](outputs/figures/nav_comparison.png)

![Drawdown](outputs/figures/drawdown.png)

More figures:

- `outputs/figures/yearly_returns.png`
- `outputs/figures/monthly_return_heatmap.png`
- `outputs/figures/holding_count.png`
- `outputs/figures/turnover.png`
- `outputs/figures/factor_ic.png`

### Limitations

- Index turnover is often unavailable, so traded value and volume abnormality are used as proxies.
- The current universe has only 15 indices, limiting cross-sectional breadth.
- Transaction cost is approximated with 3 bps one-way cost; market impact and ETF tradability are not fully modeled.
- Drawdowns remain deep, so more risk controls and out-of-sample validation are needed.
- The current trend filter is simple and did not improve this sample.

### License

This project is licensed under the MIT License.
