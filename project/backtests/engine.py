"""Event-driven, portfolio-level backtester.

Deliberately independent of Backtrader: it reuses the exact production components —
`ScoringEngine`, `RiskManager` and `MastermindPositionManager` — so what is measured
here is what runs live. Backtrader remains available for cross-validation.

Rules of the simulation (pessimistic on purpose):
    * Signals are computed on bar N using only bars 0..N, and filled on bar N+1's open.
    * Commission and slippage are charged on every fill.
    * Stops are evaluated before targets on the same bar; gaps fill at the worse price.
    * Equity is marked to market on every bar's close.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.data.provider import Bars
from project.portfolio.position import ManagedPosition, MastermindPositionManager
from project.reports.performance import PerformanceReport, TradeRecord, build_report
from project.risk.manager import OpenPosition, PortfolioState, RiskManager
from project.scanner.scoring import ScoringEngine, build_snapshot

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    commission: float = 0.0005        # 5 bps per side
    slippage: float = 0.0005          # 5 bps per side
    warmup_bars: int = 60             # indicators need history before they mean anything
    bars_per_year: int = 252
    max_new_positions_per_bar: int = 3


@dataclass
class BacktestResult:
    report: PerformanceReport
    equity_curve: List[float] = field(default_factory=list)
    trades: List[TradeRecord] = field(default_factory=list)
    journal: List[str] = field(default_factory=list)
    bars_tested: int = 0
    symbols_tested: int = 0

    def summary(self) -> str:
        from project.reports.performance import format_report, verdict

        return format_report(self.report, "Backtest") + "\n" + verdict(self.report)


def _slice(bars: Bars, end: int) -> Bars:
    """History as it was known at the close of bar `end` — no lookahead."""
    return Bars(
        ticker=bars.ticker,
        dates=bars.dates[: end + 1],
        opens=bars.opens[: end + 1],
        highs=bars.highs[: end + 1],
        lows=bars.lows[: end + 1],
        closes=bars.closes[: end + 1],
        volumes=bars.volumes[: end + 1],
    )


class Backtester:
    def __init__(self, settings: Optional[Settings] = None, config: Optional[BacktestConfig] = None) -> None:
        self.settings = settings or DEFAULT_SETTINGS
        self.settings.validate()
        self.config = config or BacktestConfig()
        self.scoring = ScoringEngine(self.settings.weights, self.settings.indicators)
        self.risk = RiskManager(self.settings.risk)
        self.manager = MastermindPositionManager(self.settings.risk, self.settings.scan)

    # -- costs ---------------------------------------------------------------------
    def _buy_price(self, price: float) -> float:
        return price * (1 + self.config.slippage + self.config.commission)

    def _sell_price(self, price: float) -> float:
        return price * (1 - self.config.slippage - self.config.commission)

    # -- main loop -----------------------------------------------------------------
    def run(self, history: Dict[str, Bars], sectors: Optional[Dict[str, str]] = None) -> BacktestResult:
        sectors = sectors or {}
        tickers = [t for t, b in history.items() if len(b) > self.config.warmup_bars + 2]
        if not tickers:
            raise ValueError("No symbol has enough history to backtest.")

        length = min(len(history[t]) for t in tickers)
        cash = equity = self.settings.starting_cash
        open_positions: Dict[str, ManagedPosition] = {}
        trades: List[TradeRecord] = []
        journal: List[str] = []
        curve: List[float] = []
        scores: Dict[str, float] = {}
        pending: List[tuple[str, float, float, int]] = []   # ticker, stop, shares, day

        for day in range(self.config.warmup_bars, length):
            # 1. Fill yesterday's signals at today's open.
            for ticker, stop, shares, signal_day in pending:
                price = self._buy_price(history[ticker].opens[day])
                cost = price * shares
                if cost > cash or stop >= price:
                    journal.append(f"day {day}: {ticker} entry cancelled (cash or stop invalid at open)")
                    continue
                cash -= cost
                open_positions[ticker] = self.manager.open_position(
                    ticker=ticker, entry=price, stop=stop, shares=shares, day=day,
                    sector=sectors.get(ticker, "UNKNOWN"),
                )
                journal.append(
                    f"day {day}: ENTRY {ticker} {shares:g} @ {price:.2f} stop {stop:.2f} "
                    f"(score {scores.get(ticker, 0):.0f})"
                )
            pending = []

            # 2. Manage everything already open.
            for ticker in list(open_positions):
                pos = open_positions[ticker]
                bars = history[ticker]
                snap = build_snapshot(_slice(bars, day), self.settings.indicators)
                score = self.scoring.score(snap).total
                scores[ticker] = score
                before = pos.remaining
                action = self.manager.on_bar(
                    pos, day=day, high=bars.highs[day], low=bars.lows[day],
                    close=bars.closes[day], atr=snap.atr, score=score,
                )
                sold = before - pos.remaining
                if sold > 0:
                    # Approximate the fill at the level the manager acted on.
                    exit_px = self._sell_price(pos.stop if action.closed else bars.closes[day])
                    cash += exit_px * sold
                if action.closed:
                    exit_px = pos.events[-1].price
                    trades.append(TradeRecord(
                        ticker=ticker, entry_day=pos.opened_day, exit_day=day,
                        entry=pos.entry, exit=exit_px, shares=pos.shares,
                        pnl=round(pos.realized_pnl, 2),
                        r_multiple=round(pos.realized_pnl / pos.risk_at_open, 3) if pos.risk_at_open else 0.0,
                        reason=pos.exit_reason or "closed",
                    ))
                    journal.append(f"day {day}: EXIT {ticker} — {pos.exit_reason} "
                                   f"({pos.realized_pnl:+,.0f})")
                    del open_positions[ticker]
                elif action.notes:
                    journal.append(f"day {day}: {ticker} — {'; '.join(action.notes)}")

            # 3. Mark to market.
            equity = cash + sum(
                p.remaining * history[p.ticker].closes[day] for p in open_positions.values()
            )
            curve.append(round(equity, 2))

            # 4. Hunt for new entries with tomorrow's open in mind.
            state = PortfolioState(
                equity=equity, cash=cash,
                positions=[OpenPosition(p.ticker, p.sector, p.country, p.remaining, p.entry, p.stop)
                           for p in open_positions.values()],
            )
            if day + 1 >= length:
                continue

            ranked: List[tuple[float, str, float]] = []
            for ticker in tickers:
                if ticker in open_positions:
                    continue
                snap = build_snapshot(_slice(history[ticker], day), self.settings.indicators)
                if snap.atr is None or snap.atr <= 0 or snap.price < self.settings.scan.min_price:
                    continue
                total = self.scoring.score(snap).total
                scores[ticker] = total
                if total >= self.settings.scan.min_entry_score:
                    ranked.append((total, ticker, snap.atr))
            ranked.sort(reverse=True)

            for total, ticker, atr in ranked[: self.config.max_new_positions_per_bar]:
                allowed, why = self.risk.can_open(
                    state, sectors.get(ticker, "UNKNOWN"), "US", ticker)
                if not allowed:
                    journal.append(f"day {day}: {ticker} scored {total:.0f} but blocked — {why}")
                    continue
                sizing = self.risk.size(state, history[ticker].closes[day], atr)
                if not sizing.allowed:
                    continue
                pending.append((ticker, sizing.stop, sizing.shares, day))
                state.positions.append(OpenPosition(
                    ticker, sectors.get(ticker, "UNKNOWN"), "US",
                    sizing.shares, history[ticker].closes[day], sizing.stop))

        # Close survivors at the final close so the report covers all capital.
        final_day = length - 1
        for ticker, pos in list(open_positions.items()):
            price = self._sell_price(history[ticker].closes[final_day])
            pos.close(price, final_day, "backtest ended — marked out at last close")
            trades.append(TradeRecord(
                ticker=ticker, entry_day=pos.opened_day, exit_day=final_day,
                entry=pos.entry, exit=price, shares=pos.shares, pnl=round(pos.realized_pnl, 2),
                r_multiple=round(pos.realized_pnl / pos.risk_at_open, 3) if pos.risk_at_open else 0.0,
                reason=pos.exit_reason or "end of test",
            ))
            cash += price * pos.shares * 0  # already realised in pos.realized_pnl accounting

        report = build_report(curve or [self.settings.starting_cash], trades,
                              bars_per_year=self.config.bars_per_year)
        return BacktestResult(
            report=report, equity_curve=curve, trades=trades, journal=journal,
            bars_tested=max(0, length - self.config.warmup_bars), symbols_tested=len(tickers),
        )


__all__ = ["Backtester", "BacktestConfig", "BacktestResult"]
