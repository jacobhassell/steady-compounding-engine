"""Backtrader adapter for the Mastermind strategy.

Backtrader is an optional dependency: importing this module without it installed is
safe, and every decision still lives in the framework-independent core
(`project.portfolio.position`, `project.risk.manager`, `project.scanner.scoring`).
The strategy class below is glue — bars in, orders out — nothing more.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.portfolio.position import ManagedPosition, MastermindPositionManager, Stage
from project.risk.manager import OpenPosition, PortfolioState, RiskManager

log = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only when backtrader is installed
    import backtrader as bt

    BACKTRADER_AVAILABLE = True
except Exception:  # noqa: BLE001
    bt = None  # type: ignore[assignment]
    BACKTRADER_AVAILABLE = False


def _require_backtrader() -> None:
    if not BACKTRADER_AVAILABLE:
        raise ImportError(
            "backtrader is not installed. Run `pip install -r project/requirements.txt` "
            "to backtest; the scanner and risk engine work without it."
        )


if BACKTRADER_AVAILABLE:  # pragma: no cover - requires the optional dependency

    class MastermindStrategy(bt.Strategy):
        """Entry on scanner score, exit on the Mastermind position ladder."""

        params = dict(settings=None, min_score=None)

        def __init__(self) -> None:
            self.settings: Settings = self.p.settings or DEFAULT_SETTINGS
            self.settings.validate()
            self.risk = RiskManager(self.settings.risk)
            self.manager = MastermindPositionManager(self.settings.risk, self.settings.scan)
            self.min_score = self.p.min_score or self.settings.scan.min_entry_score
            self.managed: Dict[str, ManagedPosition] = {}
            self.bar_index = 0

            ind = self.settings.indicators
            self.atr = {d._name: bt.indicators.ATR(d, period=ind.atr_period) for d in self.datas}
            self.rsi = {d._name: bt.indicators.RSI(d, period=ind.rsi_period) for d in self.datas}
            self.ema_fast = {d._name: bt.indicators.EMA(d, period=ind.ema_fast) for d in self.datas}
            self.boll = {
                d._name: bt.indicators.BollingerBands(d, period=ind.bb_period, devfactor=ind.bb_stddev)
                for d in self.datas
            }

        # -- helpers -----------------------------------------------------------
        def _portfolio_state(self) -> PortfolioState:
            equity = self.broker.getvalue()
            positions = [
                OpenPosition(
                    ticker=p.ticker, sector=p.sector, country=p.country,
                    shares=p.remaining, entry=p.entry, stop=p.stop,
                )
                for p in self.managed.values() if p.is_open
            ]
            return PortfolioState(equity=equity, cash=self.broker.getcash(), positions=positions)

        def _bar_score(self, data) -> float:
            """Lightweight in-strategy proxy score; the full engine scores pre-trade."""
            name = data._name
            score = 0.0
            if self.rsi[name][0] < self.settings.indicators.rsi_oversold:
                score += 35.0
            if data.close[0] <= self.boll[name].lines.bot[0]:
                score += 30.0
            if data.close[0] > self.ema_fast[name][0]:
                score += 20.0
            if data.volume[0] > 0:
                score += 15.0
            return score

        # -- the loop ----------------------------------------------------------
        def next(self) -> None:
            self.bar_index += 1
            for data in self.datas:
                name = data._name
                atr = float(self.atr[name][0] or 0.0)
                pos = self.managed.get(name)

                if pos and pos.is_open:
                    action = self.manager.on_bar(
                        pos, day=self.bar_index,
                        high=float(data.high[0]), low=float(data.low[0]),
                        close=float(data.close[0]), open_=float(data.open[0]), atr=atr, score=self._bar_score(data),
                    )
                    if action.closed:
                        self.close(data=data)
                    elif action.sold_shares > 0:
                        self.sell(data=data, size=action.sold_shares)
                    for note in action.notes:
                        log.info("[%s] %s", name, note)
                    continue

                if atr <= 0:
                    continue
                if self._bar_score(data) < self.min_score:
                    continue

                state = self._portfolio_state()
                allowed, why = self.risk.can_open(state, "UNKNOWN", "US", name)
                if not allowed:
                    log.debug("[%s] entry blocked: %s", name, why)
                    continue

                sizing = self.risk.size(state, float(data.close[0]), atr)
                if not sizing.allowed:
                    log.debug("[%s] no size: %s", name, sizing.reason)
                    continue

                self.buy(data=data, size=sizing.shares)
                self.managed[name] = self.manager.open_position(
                    ticker=name, entry=float(data.close[0]), stop=sizing.stop,
                    shares=sizing.shares, day=self.bar_index,
                )
                log.info("[%s] ENTRY %s shares @ %.2f stop %.2f — %s",
                         name, sizing.shares, data.close[0], sizing.stop, sizing.reason)

        def stop(self) -> None:
            open_trades = sum(1 for p in self.managed.values() if p.is_open)
            log.info("Run complete. Equity %.2f | %d positions still open.",
                     self.broker.getvalue(), open_trades)


def build_cerebro(settings: Optional[Settings] = None, cash: Optional[float] = None):
    """Cerebro wired with realistic-ish frictions. Optimism in backtests is expensive."""
    _require_backtrader()
    cfg = settings or DEFAULT_SETTINGS
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(cash if cash is not None else cfg.starting_cash)
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.broker.set_slippage_perc(0.0005)
    cerebro.addstrategy(MastermindStrategy, settings=cfg)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    return cerebro


__all__ = ["BACKTRADER_AVAILABLE", "build_cerebro", "Stage"]
if BACKTRADER_AVAILABLE:  # pragma: no cover
    __all__.append("MastermindStrategy")
