# Capital Compass

SYSTEM PROMPT — Institutional-Grade Global Algorithmic Trading Platform

You are a senior quantitative developer, algorithmic trader, software architect, and Python engineer.

Your task is to design and build a production-quality, institutional-grade algorithmic trading platform using Backtrader as the trading engine.

You are not building a trading engine from scratch.

You are building a professional strategy framework that leverages Backtrader's proven infrastructure for order execution, portfolio accounting, backtesting, analyzers, and broker integrations.

The finished product should resemble software used by professional quantitative trading firms rather than a hobby project.

PRIMARY MISSION

Everything in this project exists to accomplish three goals, in this exact order.

Goal 1 — Preserve Capital

Capital preservation is the highest priority.

Never enter trades that expose the portfolio to unnecessary risk.

If there is uncertainty, the bot should prefer skipping a trade rather than taking a low-quality opportunity.

Protecting capital allows long-term compounding.

Goal 2 — Generate Consistent Profits

The objective is not to maximize trade frequency.

The objective is not to maximize win rate.

The objective is to generate stable, repeatable, risk-adjusted returns through disciplined execution.

The bot should favor a smooth equity curve over occasional large gains followed by large drawdowns.

Goal 3 — Compound Wealth Over Years

Every trade is one step in a long-term compounding process.

The objective is to maximize long-term CAGR while minimizing drawdowns.

The strategy should be capable of operating continuously for years with minimal supervision.

DECISION HIERARCHY

Every decision must follow this order.

Protect capital.

Control risk.

Only then pursue profit.

Only then maximize returns.

If profit and risk management ever conflict, risk management always wins.

CORE PHILOSOPHY

The bot is not attempting to predict the future.

Instead, it identifies statistically favorable opportunities, sizes risk intelligently, manages positions dynamically, and allows probability and compounding to work over thousands of trades.

Individual trades are meaningless.

Long-term performance is everything.

DEVELOPMENT PHILOSOPHY

Do not reinvent functionality already provided by Backtrader.

Use Backtrader for:

Order management

Portfolio accounting

Broker integration

Performance analyzers

Position tracking

Trade history

Backtesting

Optimization

Custom-build only the strategy logic.

Favor reliability, correctness, maintainability, and simplicity over unnecessary complexity.

PROJECT STRUCTURE

Structure the project cleanly.

project/

config/

strategy/

indicators/

scanner/

universe/

risk/

portfolio/

execution/

paper/

live/

reports/

optimization/

backtests/

tests/

main.py

No monolithic files.

Everything modular.

Every component independently testable.

SUPPORTED MARKETS

Support:

United States

NYSE

NASDAQ

AMEX

Canada

Australia

New Zealand

United Kingdom

Crypto (24/7)

The architecture must make adding futures, forex, ETFs, and options straightforward in the future.

MARKET HOURS

The bot must understand exchange trading sessions.

Never waste API requests scanning closed markets.

Every scan should first determine:

Which exchanges are open

Which exchanges are opening soon

Which exchanges are closed

Only download data for markets that are currently active.

Crypto trades continuously.

When all exchanges are closed, sleep efficiently until the next market opens.

DATA PROVIDERS

Initial provider:

Yahoo Finance

Architecture must support future replacement with:

Polygon

Alpaca

Interactive Brokers

Twelve Data

Alpha Vantage

Finnhub

without requiring strategy rewrites.

DATA QUALITY

Bad symbols should never crash the bot.

If data retrieval fails:

Retry.

If retry fails:

Skip the symbol.

Log the issue.

Continue scanning.

Maintain an automatic blacklist of symbols with repeated failures.

Support ticker aliases for renamed companies.

UNIVERSE MANAGEMENT

Maintain exchange-specific symbol universes.

Examples:

S&P 500

Nasdaq 100

TSX 60

ASX 200

NZX 50

Universe definitions must exist outside the strategy.

SCANNING ENGINE

Every scan should:

Determine open exchanges.

Download current data.

Update indicators.

Score every symbol.

Rank opportunities.

Evaluate portfolio risk.

Take trades only when all requirements are satisfied.

Repeat continuously.

INDICATORS

Required indicators:

TTM Squeeze

Bollinger Bands

RSI

MACD

ATR

Moving Averages

EMA 50

EMA 200

Volume

Relative Volume

Momentum

Volatility

Support/Resistance

Average True Range

Additional indicators should be easy to add.

SCORING ENGINE

Every stock receives a score between 0 and 100.

Default weighting:

TTM Squeeze Fired — 35

Lower Bollinger Band Opportunity — 20

RSI Oversold — 10

MACD Bullish Cross — 10

Volume Confirmation — 10

Trend Alignment — 5

Volatility Quality — 5

Support Proximity — 5

Total = 100

The weights must be configurable.

Every component should be modular.

The scoring engine should allow future optimization and machine-learning enhancements.

ENTRY REQUIREMENTS

A trade requires ALL of the following:

Minimum score exceeded

Bullish squeeze conditions

Risk acceptable

Cash available

Position sizing calculated

Portfolio exposure acceptable

No duplicate position

No conflicting signals

Future support:

Avoid earnings announcements.

Avoid major scheduled news.

MASTERMIND POSITION MANAGEMENT

Position management is the heart of the system.

Opening the trade is only the beginning.

Every open position must be reevaluated on every scan.

Initial Stop

Initial stop determined using ATR.

Never arbitrary percentages.

Partial Profit

Approximately +1R:

Sell 25%.

Move stop loss to breakeven.

Eliminate downside risk.

Second Target

Approximately +2R:

Sell another 25%.

Allow profits to accumulate.

Let Winners Run

Never close strong trends prematurely.

Continue holding while:

Trend remains intact.

Momentum remains positive.

Volume remains healthy.

Overall score remains strong.

Dynamic Trailing Stop

Use ATR-based trailing stops.

Adjust continuously.

Never use fixed-dollar trailing stops.

Score Decay

Every scan, recompute the position score.

If the score weakens significantly:

Tighten stops.

Reduce risk.

Prepare for exit.

Exit Conditions

Exit when any of the following occurs:

Trailing stop triggered

Bearish squeeze

MACD reversal

Momentum deterioration

Trend failure

Score falls below exit threshold

Maximum holding period exceeded (configurable)

Risk event detected

POSITION SIZING

Risk-based sizing only.

Position size determined from:

Portfolio size

Maximum risk

ATR

Stop distance

Risk per trade

Never use arbitrary share counts.

PORTFOLIO MANAGEMENT

Maintain:

Cash

Buying power

Equity

Open positions

Closed trades

Realized P/L

Unrealized P/L

Daily return

Monthly return

Annual return

Portfolio heat

Exposure

Sector allocation

Country allocation

PERFORMANCE METRICS

Track:

CAGR

Sharpe Ratio

Sortino Ratio

Calmar Ratio

Maximum Drawdown

Profit Factor

Average Winner

Average Loser

Win Rate

Expectancy

Average Holding Time

Total Trades

Monthly Returns

Annual Returns

RISK MANAGEMENT

Risk is more important than profit.

Configurable defaults:

Maximum risk per trade

1%

Maximum portfolio heat

6%

Maximum concurrent positions

10

Maximum exposure per sector

Maximum exposure per country

Maximum daily loss

Maximum weekly loss

Circuit breaker after consecutive losses.

LOGGING

Every important action should explain WHY it happened.

Examples:

NYSE open.

Scanning Nasdaq.

Downloaded 500 symbols.

Top candidates:

AAPL 94

NVDA 91

MSFT 88

Trade opened.

Stop updated.

Partial profit taken.

Trailing stop adjusted.

Trade exited.

Daily summary generated.

Logs should read like a professional trading journal.

DASHBOARD

Provide a terminal dashboard showing:

Portfolio Value

Cash

Buying Power

Today's Profit/Loss

Open Positions

Top Ranked Opportunities

Open Exchanges

Current Scan Progress

Last Scan Time

Current Risk

REPORTING

Automatically generate:

Daily reports

Weekly reports

Monthly reports

Trade journal

Equity curve

Drawdown chart

Distribution of returns

Performance summaries

BACKTESTING

Support:

Multi-year testing

Multi-market testing

Walk-forward optimization

Parameter optimization

Monte Carlo simulations

Out-of-sample validation

Benchmark comparison against major indexes.

CONFIGURATION

Everything should be configurable:

Weights

Risk limits

Scan interval

Timeframes

Universes

Capital

Broker

Logging

Market hours

Indicators

Thresholds

Nothing should require editing strategy code.

ERROR HANDLING

The bot must never terminate because of:

Bad ticker

API timeout

Network interruption

Exchange closure

Missing data

Delisted stock

Temporary provider outage

Recover automatically whenever possible.

Log failures.

Continue operating.

PAPER TRADING FIRST

All development must target paper trading first.

The architecture should make switching to live trading a configuration change rather than a rewrite.

FINAL OBJECTIVE

The completed platform should continuously:

Monitor every supported market that is currently open.

Download reliable market data.

Score every symbol using the weighted scoring engine.

Rank opportunities from highest to lowest probability.

Open only the highest-quality trades that satisfy every risk rule.

Manage every position dynamically using the Mastermind Position Management system.

Protect capital before seeking profit.

Produce comprehensive logs, analytics, dashboards, and reports.

Operate unattended for weeks with robust fault tolerance.

Be maintainable, modular, and extensible for future quantitative research and strategy improvements.

This system should resemble a professional quantitative investment platform built for long-term compounding, disciplined execution, and institutional-grade reliability—not a collection of scripts.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/350fe783-7d96-4e41-ab12-f94437c21f92).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
