<h1 align="left">交易拥挤度惩罚的动量轮动策略 | Trading-Crowding Penalized Momentum Rotation</h1>

---

<p align="center">
  <a href="#中文说明"><img src="https://img.shields.io/badge/语言-中文-ff4b3e?style=for-the-badge&labelColor=343a46" alt="中文"></a>
  <a href="#english-description"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2f73c9?style=for-the-badge&labelColor=343a46" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/PYTHON-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=4a4f59" alt="Python">
  <img src="https://img.shields.io/badge/资产池-30只A股ETF-f3c63f?style=for-the-badge&labelColor=4a4f59" alt="Universe">
  <img src="https://img.shields.io/badge/评估区间-2020--2026 · 45531条日频记录-4caf50?style=for-the-badge&labelColor=4a4f59" alt="Period">
  <img src="https://img.shields.io/badge/主策略-Sharpe%200.43%20%7C%20MaxDD%20--23.01%25-9853e6?style=for-the-badge&labelColor=4a4f59" alt="Performance">
  <img src="https://img.shields.io/badge/LICENSE-MIT-111111?style=for-the-badge&labelColor=4a4f59" alt="MIT">
</p>

---

## 中文说明

### 项目简介

本项目从零实现一个 A 股 ETF 层面的“交易拥挤度 + 动量轮动”策略研究框架。项目自动读取 ETF/指数日频行情，构建动量、拥挤度和波动率风险指标，进行每周调仓回测，并输出绩效表格、图表和诊断报告。

核心思想不是把拥挤度直接当作买入 alpha，而是把它作为动量策略的风险惩罚项：优先选择短期动量较强、但交易拥挤度和波动率不过高的指数。

### 结果怎么样

本次真实数据运行覆盖 2020-01-02 至 2026-06-05，共 30 只 A 股宽基、行业、主题与商品 ETF，45531 条日频记录，数据由 Tushare 成功下载。

本轮优化先修复了一个关键回测问题：旧版本在调仓时把 0 权重当作缺失值向前填充，导致已卖出的标的继续保留旧仓位，风险暴露被高估。修复后，卖出标的权重会正确归零；随后把资产池从 15 个指数扩展到 30 只 ETF，使 10% 单标的上限不再天然压低仓位，并将默认组合设为 top30%、MA200 趋势过滤和“短动量 + 中期动量确认 - 拥挤度惩罚 - 波动率惩罚”。

| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |
|:--|--:|--:|--:|--:|--:|
| 全 ETF 等权 | 7.30% | 20.78% | 0.35 | -40.51% | 1.572 |
| 纯拥挤度 top30 对照组 | 4.05% | 20.83% | 0.19 | -36.79% | 1.291 |
| 沪深300 ETF 买入持有 | 2.44% | 19.02% | 0.13 | -45.10% | 1.167 |
| 动量 - 拥挤度惩罚 | 10.29% | 23.48% | 0.44 | -40.97% | 1.876 |
| 动量 - 拥挤度惩罚 + 趋势过滤 | 7.22% | 16.96% | 0.43 | -23.01% | 1.565 |
| 纯 5 日动量 top30 | 6.29% | 22.82% | 0.28 | -40.50% | 1.479 |

解读要点：

- 30 ETF 版本解决了原 15 指数池仓位不足的问题，策略能在 10% 单标的上限下接近满仓运行。
- 未加趋势过滤的惩罚动量版本年化 10.29%、Sharpe 0.44，显著高于纯 5 日动量和沪深300 ETF。
- 加入 MA200 趋势过滤后，年化为 7.22%、Sharpe 0.43，最大回撤从未过滤版的 -40.97% 降至 -23.01%，更适合作为稳健默认配置。
- 相比全 ETF 等权，趋势过滤主策略收益相近但回撤明显更低。
- 纯拥挤度仍只作为对照组，不作为推荐 alpha；拥挤度在主策略中继续作为风险惩罚项使用。

### 策略逻辑

默认资产池包括沪深300ETF、中证500ETF、中证1000ETF、上证50ETF、创业板ETF、科创50ETF、红利ETF、证券、银行、医药、消费、酒、半导体、芯片、5G、新能源车、光伏、军工、地产、传媒、游戏、有色、黄金等 30 只代表性 ETF。

因子定义：

- 动量：`ret_5d = close / close.shift(5) - 1`，`ret_20d = close / close.shift(20) - 1`
- 拥挤度：`turnover_z`、`amount_z`、`volume_z` 的 60 日滚动异常程度
- 波动率风险：`vol_20d = rolling_std(daily_return, 20)`
- 复合拥挤度：`rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- 最终得分：`1.0 * rank(ret_5d) + 0.6 * rank(ret_20d) - 0.5 * rank(crowding_score) - 0.1 * rank(vol_20d)`

所有 rank 均为同一天不同指数之间的横截面 percentile rank，并且所有交易信号滞后一日，避免未来函数。

### 数据来源

数据层优先使用 Tushare Pro：

- `pro_bar` / `fund_daily` / `index_daily`：ETF 与指数日行情
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

- ETF 换手率仍然不是完美的拥挤度代理，因此拥挤度会同时使用成交额、成交量异常作为替代。
- 当前资产池有 30 只 ETF，比最初指数版本更宽，但对横截面研究来说仍然不算大。
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

This project implements a from-scratch A-share ETF research framework for a trading-crowding penalized momentum rotation strategy. It downloads daily ETF/index data, builds momentum, crowding, and volatility-risk signals, runs weekly rebalancing backtests, and exports performance tables, figures, and diagnostics.

The key idea is not to use crowding directly as alpha. Crowding is used as a risk penalty inside a momentum strategy, favoring indices with positive short-term momentum but less excessive trading activity and volatility.

### Results

The latest real-data run covers 2020-01-02 to 2026-06-05, with 30 representative A-share broad-market, sector, thematic, and commodity ETFs and 45531 daily observations downloaded from Tushare.

This optimization first fixed a critical backtest issue: the old implementation treated zero rebalance weights as missing values and forward-filled them, so sold positions could keep stale weights. After the fix, sold positions correctly reset to zero. The universe was then expanded from 15 indices to 30 tradable ETFs, so the 10% single-name cap no longer forces the portfolio into a low-exposure state. The default strategy uses top30% selection, an MA200 trend filter, and a final score based on short momentum plus medium-term confirmation minus crowding and volatility penalties.

| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |
|:--|--:|--:|--:|--:|--:|
| All-ETF equal weight | 7.30% | 20.78% | 0.35 | -40.51% | 1.572 |
| Pure crowding top30 ablation | 4.05% | 20.83% | 0.19 | -36.79% | 1.291 |
| CSI 300 ETF buy and hold | 2.44% | 19.02% | 0.13 | -45.10% | 1.167 |
| Momentum minus crowding penalty | 10.29% | 23.48% | 0.44 | -40.97% | 1.876 |
| Momentum minus crowding penalty plus trend filter | 7.22% | 16.96% | 0.43 | -23.01% | 1.565 |
| Pure 5-day momentum top30 | 6.29% | 22.82% | 0.28 | -40.50% | 1.479 |

Takeaways:

- The 30-ETF universe fixes the low-exposure problem caused by combining a 15-name universe with a 10% single-name cap.
- The unfiltered penalized momentum strategy earns 10.29% annualized with a 0.44 Sharpe, outperforming pure 5-day momentum and CSI 300 ETF buy-and-hold.
- The MA200 trend filter lowers annual return to 7.22%, but reduces max drawdown from -40.97% to -23.01%, making it the more conservative default.
- Compared with all-ETF equal weight, the trend-filtered main strategy delivers similar annual return with materially lower drawdown.
- Pure crowding remains an ablation only; crowding is used as a risk penalty in the main strategy, not as standalone alpha.

### Strategy Logic

The default universe includes 30 representative ETFs covering CSI 300, CSI 500, CSI 1000, SSE 50, ChiNext, STAR 50, dividend, securities, banks, healthcare, consumption, alcohol, semiconductors, chips, 5G, new energy vehicles, photovoltaic, defense, real estate, media, gaming, nonferrous metals, and gold.

Signals:

- Momentum: `ret_5d = close / close.shift(5) - 1`, `ret_20d = close / close.shift(20) - 1`
- Crowding proxies: 60-day rolling abnormality in turnover, amount, and volume
- Volatility risk: `vol_20d = rolling_std(daily_return, 20)`
- Composite crowding: `rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- Final score: `1.0 * rank(ret_5d) + 0.6 * rank(ret_20d) - 0.5 * rank(crowding_score) - 0.1 * rank(vol_20d)`

All ranks are same-day cross-sectional percentile ranks. Tradable signals are shifted by one trading day to avoid look-ahead bias.

### Data Sources

The data layer prioritizes Tushare Pro:

- `pro_bar` / `fund_daily` / `index_daily`: daily ETF and index prices
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

- ETF turnover is still an imperfect crowding proxy, so traded value and volume abnormality are used alongside turnover.
- The current universe has 30 ETFs, which is broader than the first index-only version but still limited for cross-sectional research.
- Transaction cost is approximated with 3 bps one-way cost; market impact and ETF tradability are not fully modeled.
- Drawdowns remain deep, so more risk controls and out-of-sample validation are needed.
- The current trend filter is simple and did not improve this sample.

### License

This project is licensed under the MIT License.
