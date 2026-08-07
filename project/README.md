# Mastermind — Institutional-Grade Algorithmic Trading Platform

Backtrader-powered strategy framework. Backtrader owns execution, accounting,
analyzers and backtesting; this repository owns the *strategy intelligence*:
market-session awareness, universe management, indicators, the weighted scoring
engine, risk gates and (next slice) Mastermind position management.

## Decision hierarchy

1. Protect capital
2. Control risk
3. Pursue profit
4. Maximize returns

When profit and risk conflict, risk wins.

## Layout

```
project/
  config/      settings.py — weights, risk limits, scan params, data config
  indicators/  technical.py — TTM squeeze, BB, RSI, MACD, ATR, EMA, RVOL, S/R
  scanner/     scoring.py (0-100 weighted engine), engine.py (scan cycle)
  universe/    exchanges.py (sessions), registry.py (SP500, TSX60, ASX200, ...)
  risk/        manager.py — sizing, heat, exposure, circuit breakers
  data/        provider.py — DataProvider ABC + Yahoo + ResilientProvider
  strategy/ portfolio/ execution/ paper/ live/ reports/ optimization/ backtests/
  tests/       deterministic, network-free
  main.py      CLI entry point
```

## Run

```bash
pip install -r project/requirements.txt
python -m project.main scan            # one cycle
python -m project.main run             # continuous, session-aware
pytest project/tests -q
```

## Scoring engine

| Component | Weight |
|---|---|
| TTM Squeeze fired | 35 |
| Lower Bollinger opportunity | 20 |
| RSI oversold | 10 |
| MACD bullish cross | 10 |
| Volume confirmation | 10 |
| Trend alignment | 5 |
| Volatility quality | 5 |
| Support proximity | 5 |

Each component is a pure `(snapshot, config) -> 0..1` callable registered in
`COMPONENTS`. Add one, give it a weight, rebalance to 100 — no other code changes.
This is the hook for future optimization and ML-learned weights.

## Extending

- **New data provider**: subclass `DataProvider`, register in `build_provider`.
- **New market**: add an `Exchange` to `EXCHANGES` and a `Universe` to `UNIVERSES`.
- **New indicator**: add to `indicators/technical.py`, expose on `IndicatorSnapshot`.
- **Live trading**: a config change (`--mode live`) plus a Backtrader broker store.

## Status

- [x] Config, exchanges/sessions, universes
- [x] Indicators, snapshot builder
- [x] Weighted scoring + ranking, scan cycle, fault isolation
- [x] Risk sizing and portfolio gates
- [ ] Mastermind position management (ATR stops, 1R/2R partials, trailing, score decay)
- [ ] Backtrader strategy adapter, walk-forward, Monte Carlo, reports
