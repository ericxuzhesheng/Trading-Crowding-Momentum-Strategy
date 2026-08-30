<h1 align="left">凸优化的交易拥挤度动量策略 | Convex Trading-Crowding Momentum Strategy</h1>

---

<p align="center">
  <a href="#中文说明"><img src="https://img.shields.io/badge/CN-%E4%B8%AD%E6%96%87-ff4b3e?style=for-the-badge&labelColor=343a46" alt="中文"></a>
  <a href="#english-description"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2f73c9?style=for-the-badge&labelColor=343a46" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Universe-30%20Multi--Asset%20ETFs-f3c63f?style=for-the-badge&labelColor=4a4f59" alt="Universe">
  <img src="https://img.shields.io/badge/Period-2018%E2%80%932026%20%C2%B7%2054821%20obs-4caf50?style=for-the-badge&labelColor=4a4f59" alt="Period">
  <img src="https://img.shields.io/badge/Main%20Strategy-Sharpe%201.19%20%7C%20MaxDD%20--11.54%25-9853e6?style=for-the-badge&labelColor=4a4f59" alt="Main Strategy">
  <img src="https://img.shields.io/badge/PYTHON-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=4a4f59" alt="Python">
  <img src="https://img.shields.io/badge/LICENSE-MIT-111111?style=for-the-badge&labelColor=4a4f59" alt="MIT">
</p>

<p align="center">
  <strong>English Description:</strong>
  A reproducible multi-asset ETF strategy that converts crowding-adjusted momentum into long-only weights with a convex risk-and-turnover optimizer, adjusted-price validation, weekly rebalancing, and temporal holdout reporting.
</p>

---

## 中文说明

### 项目简介

本项目实现一个多资产 ETF 层面的“交易拥挤度 + 动量 + 凸组合优化”研究框架。项目读取前复权 ETF 日频行情，构建动量、拥挤度和波动率信号，每周求解长仓凸优化问题，并输出绩效、权重、求解诊断、图表和时间切分验证。

核心思想不是把拥挤度直接当作买入 alpha，而是先形成“动量减拥挤度”的预期收益排序，再由组合层同时权衡完整协方差风险、持仓上限和 L1 换手正则。原 top-quantile 等权策略全部保留为对照。

### 结果怎么样

本次前复权数据运行覆盖 2018-01-02 至 2026-08-28，共 30 只 ETF，合计 54821 条日频记录。

推荐主策略为 `momentum_crowding_convex`：对所有信号有效且历史充足的 ETF 连续求权重，单 ETF 上限 15%，使用 120 日收缩协方差和较强的 L1 换手正则。价格由 Tushare `fund_daily + fund_adj` 前复权，AKShare `adjust="qfq"` 作为回退，并对超过 30% 的未解释单日跳变直接报错，防止基金拆分被误算为投资收益。

文中 Sharpe 采用标准日频超额收益口径：`sqrt(252) * mean(daily_return - daily_rf) / std(daily_return)`；默认年化无风险利率为 0%，同时在结果表保留 CAGR/波动率比值以便核对旧口径。

| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |
|:--|--:|--:|--:|--:|--:|
| 全 ETF 等权 | 8.60% | 12.57% | 0.74 | -15.95% | 2.042 |
| 纯拥挤度 top30 对照组 | 13.64% | 14.43% | 0.99 | -15.82% | 3.022 |
| 沪深300 ETF 买入持有 | 3.31% | 19.63% | 0.27 | -42.16% | 1.325 |
| 凸优化动量 - 拥挤度 | 14.13% | 12.11% | 1.19 | -11.54% | 3.139 |
| 凸优化动量 - 拥挤度 + 趋势过滤 | 9.59% | 10.81% | 0.93 | -13.12% | 2.209 |
| 动量 - 拥挤度惩罚 | 10.52% | 14.39% | 0.79 | -16.08% | 2.376 |
| 动量 - 拥挤度惩罚 + 趋势过滤 | 7.95% | 12.78% | 0.69 | -19.23% | 1.938 |
| 纯 5 日动量 top30 | 6.19% | 15.00% | 0.49 | -18.36% | 1.681 |

解读要点：

<!-- OPTIMIZED_SUMMARY_ZH_START -->
- 推荐主策略「凸优化动量 - 拥挤度」全样本年化 14.13%、标准 Sharpe 1.19、最大回撤 -11.54%，周均 L1 换手 0.403。
- 相比原等权组合构建，Sharpe 从 0.79 提高到 1.19，最大回撤从 -16.08% 收窄到 -11.54%。
- 时间切分结果：2018–2022 参数选择段 Sharpe 1.13；2023 年起时间留出段 Sharpe 1.28。分阶段表现仍有差异，不能把 Sharpe 1 视为承诺。
- 优化器使用 15% 单 ETF 上限与 750 bp-equivalent 的 L1 换手正则；后者是控制交易稳定性的正则强度，不是实际交易费率。
<!-- OPTIMIZED_SUMMARY_ZH_END -->

### 交易成本敏感性

<!-- COST_SENSITIVITY_ZH_START -->
以下情景保持信号和目标权重不变，仅按计划调仓日的完整 L1 成交名义本金重算成本。

| 每单位成交成本 | 口径 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |
|---:|:---|---:|---:|---:|---:|---:|
| 0 bps | 情景 | 14.84% | 12.12% | 1.246 | -11.36% | 3.311 |
| 1 bps | 情景 | 14.60% | 12.11% | 1.229 | -11.42% | 3.252 |
| 2 bps | 情景 | 14.37% | 12.11% | 1.211 | -11.48% | 3.195 |
| 3 bps | 基准 | 14.13% | 12.11% | 1.194 | -11.54% | 3.139 |
| 5 bps | 情景 | 13.67% | 12.11% | 1.159 | -11.67% | 3.029 |
| 10 bps | 情景 | 12.50% | 12.10% | 1.071 | -11.98% | 2.771 |
<!-- COST_SENSITIVITY_ZH_END -->

成本率按每单位模拟成交名义本金收取，而换手采用完整 L1 口径 `sum(abs(w_target - w_previous))`。因此从现金建仓至 100% 仓位的换手为 1，从一个满仓组合完全切换到另一个满仓组合的换手为 2，后者会同时计入卖出和买入两侧成本。3 bps 是基准回测假设，不是券商佣金报价，也不同于优化器的 750 bp-equivalent 换手正则。

### 策略逻辑

默认资产池来自 Relaxed Risk Parity 项目的 30 只 ETF，包括可转债、国债、信用债、货币、沪深300、中证500、中证1000、创业板、红利、半导体、人工智能、机器人、新能源、中韩半导体、科创50、云计算、证券、军工、消费、恒生、白银、纳指、标普500、日经225、欧洲、黄金、有色、豆粕、煤炭、原油。

因子定义：

- 动量：`ret_5d = close / close.shift(5) - 1`，`ret_20d = close / close.shift(20) - 1`
- 拥挤度：`turnover_z`、`amount_z`、`volume_z` 的 60 日滚动异常程度
- 波动率风险：`vol_20d = rolling_std(daily_return, 20)`
- 复合拥挤度：`rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- 最终得分：`1.0 * rank(ret_5d) + 1.0 * rank(ret_20d) - 0.65 * rank(crowding_score) - 0.1 * rank(vol_20d)`

所有 rank 均为同一天不同指数之间的横截面 percentile rank，并且所有交易信号滞后一日，避免未来函数。

### 凸优化组合构建

推荐策略 `momentum_crowding_convex` 不做硬 top-k 筛选，而是在所有信号有效且历史长度足够的 ETF 上连续求权重。旧 top30% 规则只选 9 只 ETF，配合旧版 10% 上限时会强制每只都是 10%，优化器没有自由度。凸优化器因此使用独立的 15% 上限，让 alpha、风险和换手之间存在真实取舍。

每个调仓日求解以下凸二次规划：

```text
minimize  -alpha' w
          + (risk_aversion / 2) * w' Sigma w
          + (crowding_aversion / 2) * sum(q_i * w_i^2)
          + turnover_penalty * ||w - w_prev||_1

subject to  sum(w) = target_exposure
            0 <= w_i <= max_weight
            ||w - w_prev||_1 <= max_turnover  (可选)
            w' Sigma w <= volatility_limit^2 (允许现金时可选)
```

- `alpha` 是横截面标准化后的滞后综合得分，保留“动量减拥挤度”的经济含义。
- `Sigma` 只使用信号日及以前的滚动收益估计，并经过对角收缩和特征值下限处理，保证数值上半正定。
- `q_i` 是可选的拥挤集中度项；默认设为 0，因为综合 alpha 已经包含 `-0.65 * crowding`，避免双重惩罚。
- 默认 750 bp-equivalent 的 L1 系数是换手正则强度，不是交易费假设；基准回测按每单位成交名义本金 3 bps 扣费。
- `allow_cash`、硬换手上限和事前波动率上限均为可选凸约束；它们能进一步降风险，但当前验证中没有提高 Sharpe，因此默认关闭。
- 当有效资产不足时，目标暴露自动取 `min(exposure, n_valid * max_weight)`；求解失败时确定性回退到原等权选择器，并在 `turnover.csv` 留下状态。

参数集中在 `strategy.convex_optimizer`。`turnover.csv` 同时输出求解状态、目标暴露、目标函数分解、事前波动率和迭代次数，便于区分 alpha、风险、拥挤度和换手成本的贡献。

### 数据来源

数据层优先使用 Tushare Pro 的基金行情与复权因子：

- `fund_daily + fund_adj`：生成连续的前复权 ETF OHLC；不再把拆分和份额合并当作收益
- 环境变量：`TUSHARE_TOKEN`
- 失败处理：token 缺失、复权因子权限不足或接口异常时，回退到 AKShare `fund_etf_hist_em(adjust="qfq")`
- 质量门槛：默认拒绝绝对值超过 30% 的 ETF 单日收益，并输出具体日期和标的

代码不会把 token 写入源码。当前跟踪数据已通过复权连续性检查；最大单日绝对收益为 20%。
AKShare 对复权必要性和 `qfq` 参数的说明见其[官方 ETF 行情文档](https://akshare.akfamily.xyz/data/fund/fund_public.html)。

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
- `outputs/tables/turnover.csv`：完整 L1 换手、交易成本、求解状态、目标函数分解、事前波动率和约束松弛量
- `outputs/tables/performance_summary.csv`：绩效汇总
- `outputs/tables/transaction_cost_sensitivity.csv`：固定信号和目标权重下的交易成本敏感性
- `outputs/tables/yearly_returns.csv`：年度收益
- `outputs/tables/monthly_returns.csv`：月度收益
- `outputs/reports/backtest_report.md`：自动生成的回测报告

### 主要图表

![NAV comparison](outputs/figures/nav_comparison.png)

![Drawdown](outputs/figures/drawdown.png)

![Transaction-cost sensitivity](outputs/figures/transaction_cost_sensitivity.png)

更多图表：

- `outputs/figures/yearly_returns.png`
- `outputs/figures/monthly_return_heatmap.png`
- `outputs/figures/holding_count.png`
- `outputs/figures/turnover.png`
- `outputs/figures/transaction_cost_sensitivity.png`
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
│   ├── optimizer.py
│   └── strategy_metadata.py
├── scripts/update_readme.py
├── data/
├── outputs/
└── tests/
```

### 局限性

- ETF 换手率仍然不是完美的拥挤度代理，因此拥挤度会同时使用成交额、成交量异常作为替代。
- 当前资产池有 30 只 ETF，比最初指数版本更宽，但对横截面研究来说仍然不算大。
- 基准成本为每单位成交名义本金 3 bps；0/1/2/3/5/10 bps 情景只重算计划调仓成本，尚未用逐笔盘口数据建模价差、冲击和容量。
- 当前向量化回测把目标权重视为调仓间的固定日度暴露，并按计划目标权重变化计费；它不是持仓份额自然漂移后的逐笔成交模拟。
- 2018–2022 参数选择段和 2023+ 时间留出段的聚合 Sharpe 均超过 1，但较短市场阶段仍可能显著低于 1，统计证据并不等于实盘保证。
- 750 bp-equivalent 是基于历史稳定性选择的换手正则，不应解释为可观测的真实交易成本。
- 30 只 ETF 的横截面仍较小，且拥挤度代理主要来自成交数据；未来应加入份额、资金流和融资数据。

### 后续优化方向

- 扩展行业、主题和 ETF 可交易池。
- 引入 ETF 份额、资金流、融资融券、北向资金等更直接的拥挤度代理变量。
- 做滚动 walk-forward、参数漂移监控和分市场状态报告。
- 加入容量约束、冲击成本、ETF 份额变化和真实成交映射。

---

## English Description

### Overview

This project implements a multi-asset ETF research framework for crowding-adjusted momentum with convex portfolio construction. It uses forward-adjusted prices, solves long-only risk-and-turnover problems weekly, and exports performance, weights, solver diagnostics, figures, and temporal validation.

Crowding is not treated as standalone alpha. It reduces the momentum forecast, after which the optimizer balances that forecast against the full covariance matrix, position limits, and L1 turnover regularization. Original top-quantile equal-weight rules remain as baselines.

### Results

The latest forward-adjusted run covers 2018-01-02 to 2026-08-28, with 30 ETFs and 54821 daily observations.

The recommended `momentum_crowding_convex` strategy optimizes over every ETF with a valid signal and sufficient history, using a 15% ETF cap, a 120-day shrunk covariance matrix, and strong L1 turnover regularization. Tushare `fund_daily + fund_adj` produces forward-adjusted prices, AKShare `adjust="qfq"` is the fallback, and an unexplained daily move above 30% fails the data pipeline instead of becoming a false strategy return.

Sharpe uses the standard daily excess-return definition: `sqrt(252) * mean(daily_return - daily_rf) / std(daily_return)`. The default annual risk-free rate is 0%; CAGR divided by volatility remains a separate output column for continuity with earlier reports.

| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |
|:--|--:|--:|--:|--:|--:|
| All-ETF Equal Weight | 8.60% | 12.57% | 0.74 | -15.95% | 2.042 |
| Pure Crowding | 13.64% | 14.43% | 0.99 | -15.82% | 3.022 |
| CSI 300 Buy & Hold | 3.31% | 19.63% | 0.27 | -42.16% | 1.325 |
| Convex Mom-Crowding | 14.13% | 12.11% | 1.19 | -11.54% | 3.139 |
| Convex Mom-Crowding + Trend | 9.59% | 10.81% | 0.93 | -13.12% | 2.209 |
| Mom-Crowding Equal Weight | 10.52% | 14.39% | 0.79 | -16.08% | 2.376 |
| Mom-Crowding Equal Weight + Trend | 7.95% | 12.78% | 0.69 | -19.23% | 1.938 |
| Pure 5D Momentum | 6.19% | 15.00% | 0.49 | -18.36% | 1.681 |

Takeaways:

<!-- OPTIMIZED_SUMMARY_EN_START -->
- The recommended Convex Mom-Crowding strategy delivers 14.13% annualized return, a standard Sharpe of 1.19, -11.54% max drawdown, and 0.403 average weekly L1 turnover over the full sample.
- Versus the original equal-weight portfolio construction, Sharpe rises from 0.79 to 1.19, while max drawdown improves from -16.08% to -11.54%.
- Temporal validation: Sharpe is 1.13 for the 2018–2022 parameter-selection period and 1.28 for the 2023+ holdout. Regime results vary, so Sharpe 1 is not a promise.
- The optimizer uses a 15% ETF cap and 750 bp-equivalent L1 turnover regularizer. The latter is a stability penalty, not the realized transaction-cost assumption.
<!-- OPTIMIZED_SUMMARY_EN_END -->

### Transaction-Cost Sensitivity

<!-- COST_SENSITIVITY_EN_START -->
These scenarios hold signals and target weights fixed and only reprice gross L1 traded notional on scheduled rebalance dates.

| Cost per Traded Notional | Case | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |
|---:|:---|---:|---:|---:|---:|---:|
| 0 bps | Scenario | 14.84% | 12.12% | 1.246 | -11.36% | 3.311 |
| 1 bps | Scenario | 14.60% | 12.11% | 1.229 | -11.42% | 3.252 |
| 2 bps | Scenario | 14.37% | 12.11% | 1.211 | -11.48% | 3.195 |
| 3 bps | Base | 14.13% | 12.11% | 1.194 | -11.54% | 3.139 |
| 5 bps | Scenario | 13.67% | 12.11% | 1.159 | -11.67% | 3.029 |
| 10 bps | Scenario | 12.50% | 12.10% | 1.071 | -11.98% | 2.771 |
<!-- COST_SENSITIVITY_EN_END -->

The rate is charged per unit of traded notional, while turnover uses the full L1 definition `sum(abs(w_target - w_previous))`. Moving from cash to a fully invested portfolio has turnover 1; completely replacing one fully invested portfolio with another has turnover 2 and charges both sell and buy legs. The 3 bps base case is a backtest assumption, not a broker quote, and is separate from the optimizer's 750 bp-equivalent turnover regularizer.

### Strategy Logic

The default universe comes from the Relaxed Risk Parity project and includes 30 ETFs: convertible bond, government bond, credit bond, money market, CSI 300, CSI 500, CSI 1000, ChiNext, dividend, semiconductor, AI, robotics, new energy, China-Korea semiconductor, STAR 50, cloud computing, securities, defense, consumption, Hang Seng, silver, Nasdaq 100, S&P 500, Nikkei 225, Europe, gold, nonferrous metals, soybean meal, coal, and crude oil.

Signals:

- Momentum: `ret_5d = close / close.shift(5) - 1`, `ret_20d = close / close.shift(20) - 1`
- Crowding proxies: 60-day rolling abnormality in turnover, amount, and volume
- Volatility risk: `vol_20d = rolling_std(daily_return, 20)`
- Composite crowding: `rank(turnover_z) * 0.4 + rank(amount_z) * 0.3 + rank(ret_20d) * 0.3`
- Final score: `1.0 * rank(ret_5d) + 1.0 * rank(ret_20d) - 0.65 * rank(crowding_score) - 0.1 * rank(vol_20d)`

All ranks are same-day cross-sectional percentile ranks. Tradable signals are shifted by one trading day to avoid look-ahead bias.

### Convex Portfolio Construction

The recommended `momentum_crowding_convex` strategy solves for continuous weights over all ETFs with valid signals and sufficient trailing history. The legacy top-30% screen leaves nine names under its 10% cap, forcing equal 10% weights and making optimization degenerate. The convex strategy therefore uses a separate 15% cap.

At each rebalance, the convex variants solve:

```text
minimize  -alpha' w
          + (risk_aversion / 2) * w' Sigma w
          + (crowding_aversion / 2) * sum(q_i * w_i^2)
          + turnover_penalty * ||w - w_prev||_1

subject to  sum(w) = target_exposure
            0 <= w_i <= max_weight
            ||w - w_prev||_1 <= max_turnover  (optional)
            w' Sigma w <= volatility_limit^2  (optional with cash)
```

`alpha` is the standardized lagged crowding-adjusted momentum score. `Sigma` uses only trailing returns available
on the signal date and is made numerically positive semidefinite through diagonal shrinkage and an eigenvalue floor.
The `q_i` concentration term is optional and defaults to zero because crowding already enters alpha. The 750
bp-equivalent L1 coefficient is a stability regularizer, not the realized fee assumption; the base backtest charges
3 bps per unit of traded notional. Cash, hard turnover, and ex-ante volatility limits remain optional convex controls. Capacity is handled with
`min(exposure, n_valid * max_weight)`, and deterministic fallbacks plus objective diagnostics are recorded in `turnover.csv`.

### Data Sources

The data layer prioritizes adjusted Tushare fund data:

- `fund_daily + fund_adj`: continuous forward-adjusted ETF OHLC
- Environment variable: `TUSHARE_TOKEN`
- Fallback: AKShare `fund_etf_hist_em(adjust="qfq")`
- Quality gate: reject unexplained absolute daily ETF returns above 30%

The token is never hard-coded. The tracked panel passes the adjusted-price continuity gate; its largest absolute daily return is 20%.
See the [official AKShare ETF history documentation](https://akshare.akfamily.xyz/data/fund/fund_public.html) for why adjusted prices are required and how `qfq` is requested.

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
- `outputs/tables/turnover.csv`: gross L1 turnover, costs, solver status, objective components, ex-ante volatility, and constraint slack
- `outputs/tables/performance_summary.csv`: performance summary
- `outputs/tables/transaction_cost_sensitivity.csv`: fixed-signal, fixed-target transaction-cost scenarios
- `outputs/tables/yearly_returns.csv`: annual returns
- `outputs/tables/monthly_returns.csv`: monthly returns
- `outputs/reports/backtest_report.md`: generated backtest report

### Figures

![NAV comparison](outputs/figures/nav_comparison.png)

![Drawdown](outputs/figures/drawdown.png)

![Transaction-cost sensitivity](outputs/figures/transaction_cost_sensitivity.png)

More figures:

- `outputs/figures/yearly_returns.png`
- `outputs/figures/monthly_return_heatmap.png`
- `outputs/figures/holding_count.png`
- `outputs/figures/turnover.png`
- `outputs/figures/transaction_cost_sensitivity.png`
- `outputs/figures/factor_ic.png`

### Limitations

- ETF turnover is still an imperfect crowding proxy, so traded value and volume abnormality are used alongside turnover.
- The current universe has 30 ETFs, which is broader than the first index-only version but still limited for cross-sectional research.
- The base cost is 3 bps per unit of traded notional. The 0/1/2/3/5/10 bps scenarios only reprice scheduled target changes; bid-ask spread, market impact, and capacity are not estimated from order-book data.
- The vectorized backtest treats target weights as constant daily exposures between scheduled changes and charges changes in target weights; it is not a drift-aware share-level execution simulation.
- Aggregate Sharpe exceeds 1 in both the 2018–2022 selection period and the 2023+ temporal holdout, but shorter regimes can remain well below 1. This is backtest evidence, not a live-performance promise.
- The 750 bp-equivalent turnover coefficient is a historical regularization choice, not an observable trading fee.
- The 30-ETF cross-section and turnover-based crowding proxies remain limited; ETF shares, flows, financing, and richer capacity data are natural extensions.

### License

This project is licensed under the MIT License.
