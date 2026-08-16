"""Paper trading loop — the same engine that will run live, with a simulated broker.

One cycle is: scan -> manage what is open -> risk-gate new entries -> journal.
State is persisted to disk so a restart resumes rather than forgets.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.execution.broker import Order, PaperBroker, Side
from project.portfolio.position import ManagedPosition, MastermindPositionManager
from project.reports.ledger import TradeLedger
from project.risk.manager import OpenPosition, PortfolioState, RiskManager
from project.scanner.engine import ScannerEngine
from project.scanner.scoring import ScoringEngine, build_snapshot

log = logging.getLogger(__name__)


@dataclass
class CycleReport:
    at: datetime
    scanned: int = 0
    candidates: int = 0
    entries: List[str] = field(default_factory=list)
    exits: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    journal: List[str] = field(default_factory=list)
    equity: float = 0.0
    cash: float = 0.0
    heat: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Paper cycle {self.at:%Y-%m-%d %H:%M UTC}",
            f"  scanned {self.scanned} | candidates {self.candidates}",
            f"  equity ${self.equity:,.0f} | cash ${self.cash:,.0f} | heat {self.heat:.1%}",
        ]
        for label, rows in (("entries", self.entries), ("exits", self.exits),
                            ("blocked", self.blocked)):
            for row in rows:
                lines.append(f"  {label[:-1]}: {row}")
        return "\n".join(lines)


class PaperTrader:
    """Portfolio-level paper trading built on the production scanner and risk stack."""

    def __init__(
        self,
        engine: ScannerEngine,
        settings: Optional[Settings] = None,
        broker: Optional[PaperBroker] = None,
        state_path: str = ".state/paper_state.json",
        ledger: Optional[TradeLedger] = None,
    ) -> None:
        self.settings = settings or DEFAULT_SETTINGS
        self.settings.validate()
        self.engine = engine
        self.broker = broker or PaperBroker(self.settings.starting_cash)
        self.risk = RiskManager(self.settings.risk)
        self.manager = MastermindPositionManager(self.settings.risk, self.settings.scan)
        self.scoring = ScoringEngine(self.settings.weights, self.settings.indicators)
        self.positions: Dict[str, ManagedPosition] = {}
        self.closed: List[ManagedPosition] = []
        self.journal: List[str] = []
        self.state_path = state_path
        self.ledger = ledger if ledger is not None else TradeLedger()
        self.cycles = 0

    # -- state -------------------------------------------------------------------
    def portfolio_state(self, marks: Dict[str, float]) -> PortfolioState:
        equity = self.broker.equity(marks)
        return PortfolioState(
            equity=equity,
            cash=self.broker.cash,
            positions=[
                OpenPosition(p.ticker, p.sector, p.country, p.remaining, p.entry, p.stop)
                for p in self.positions.values()
            ],
        )

    def _note(self, report: CycleReport, text: str) -> None:
        stamped = f"{report.at:%H:%M} {text}"
        report.journal.append(stamped)
        self.journal.append(stamped)
        log.info(text)

    # -- one cycle ---------------------------------------------------------------
    def run_cycle(self, at: Optional[datetime] = None) -> CycleReport:
        now = at or datetime.now(timezone.utc)
        report = CycleReport(at=now)
        self.cycles += 1

        result = self.engine.scan(at=now)
        report.scanned = result.scanned
        report.candidates = len(result.candidates)

        marks: Dict[str, float] = {}

        # 1. Manage everything already open before risking a single new dollar.
        for ticker in list(self.positions):
            pos = self.positions[ticker]
            bars = self.engine.provider.fetch(ticker, self.settings.scan.history_bars)
            if bars is None or not bars.is_usable(60):
                self._note(report, f"{ticker}: no fresh data this cycle — holding, stop unchanged")
                marks[ticker] = pos.entry
                continue
            snap = build_snapshot(bars, self.settings.indicators)
            score = self.scoring.score(snap).total
            marks[ticker] = snap.price
            before = pos.remaining
            action = self.manager.on_bar(
                pos, day=self.cycles, high=bars.highs[-1], low=bars.lows[-1],
                close=bars.closes[-1], open_=bars.opens[-1], atr=snap.atr, score=score,
            )
            sold = before - pos.remaining
            if sold > 0:
                reference = pos.stop if action.closed else snap.price
                exit_fill = self.broker.submit(
                    Order(ticker, Side.SELL, sold, reason=pos.exit_reason or "; ".join(action.notes)),
                    reference,
                )
                if exit_fill is not None:
                    self.ledger.record_fill(exit_fill, self.broker.cash, self.cycles)
            if action.closed:
                report.exits.append(
                    f"{ticker} — {pos.exit_reason} ({pos.realized_pnl:+,.0f}, "
                    f"{pos.realized_pnl / pos.risk_at_open if pos.risk_at_open else 0:+.2f}R)"
                )
                self._note(report, f"EXIT {ticker}: {pos.exit_reason}")
                self.ledger.record_trade(pos, cycle_closed=self.cycles, closed_at=now)
                self.closed.append(pos)
                del self.positions[ticker]
            elif action.notes:
                self._note(report, f"{ticker}: {'; '.join(action.notes)}")

        # 2. New entries, strictly risk-gated.
        state = self.portfolio_state(marks)
        halt = self.risk.circuit_breaker(state)
        if halt:
            self._note(report, f"No new risk this cycle — {halt}")
        else:
            for candidate in result.candidates:
                ready, why = self.engine.entry_ready(candidate)
                if not ready:
                    report.blocked.append(f"{candidate.ticker} — {why}")
                    continue
                allowed, risk_why = self.risk.can_open(
                    state, candidate.symbol.sector, candidate.symbol.country, candidate.ticker)
                if not allowed:
                    report.blocked.append(f"{candidate.ticker} — {risk_why}")
                    continue
                price = candidate.snapshot.price
                sizing = self.risk.size(state, price, candidate.snapshot.atr or 0.0)
                if not sizing.allowed:
                    report.blocked.append(f"{candidate.ticker} — {sizing.reason}")
                    continue
                fill = self.broker.submit(
                    Order(candidate.ticker, Side.BUY, sizing.shares,
                          reason=f"score {candidate.total:.0f}"),
                    price,
                )
                if fill is None:
                    report.blocked.append(f"{candidate.ticker} — order rejected by broker")
                    continue
                self.ledger.record_fill(fill, self.broker.cash, self.cycles)
                pos = self.manager.open_position(
                    ticker=candidate.ticker, entry=fill.price, stop=sizing.stop,
                    shares=sizing.shares, day=self.cycles,
                    sector=candidate.symbol.sector, country=candidate.symbol.country,
                )
                self.positions[candidate.ticker] = pos
                marks[candidate.ticker] = fill.price
                state = self.portfolio_state(marks)
                report.entries.append(
                    f"{candidate.ticker} {sizing.shares:g} @ {fill.price:.2f} "
                    f"stop {sizing.stop:.2f} (score {candidate.total:.0f})"
                )
                self._note(report, f"ENTRY {candidate.ticker} — {', '.join(candidate.score.top_reasons())}")

        final = self.portfolio_state(marks)
        report.equity = final.equity
        report.cash = final.cash
        report.heat = final.heat
        self.save()
        return report

    # -- persistence -------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "cycles": self.cycles,
            "cash": self.broker.cash,
            "realized_pnl": round(self.broker.realized_pnl, 2),
            "open_positions": [
                {
                    "ticker": p.ticker, "entry": p.entry, "stop": p.stop,
                    "shares": p.shares, "remaining": p.remaining, "stage": p.stage.value,
                    "sector": p.sector, "country": p.country,
                }
                for p in self.positions.values()
            ],
            "closed_positions": [
                {"ticker": p.ticker, "pnl": round(p.realized_pnl, 2), "reason": p.exit_reason}
                for p in self.closed
            ],
            "journal": self.journal[-200:],
        }

    def save(self) -> None:
        try:
            directory = os.path.dirname(self.state_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self.snapshot(), fh, indent=2)
        except OSError as exc:  # never let bookkeeping kill the trading loop
            log.warning("Could not persist paper state: %s", exc)


__all__ = ["CycleReport", "PaperTrader"]
