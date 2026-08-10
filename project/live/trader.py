"""Live trading loop.

Live is deliberately *the paper loop plus friction*: the same scan, the same ladder,
the same risk stack, with a guard between the strategy and the venue and a preflight
that refuses to start when the setup looks wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.execution.broker import Broker, PaperBroker
from project.live.guardrails import GuardedBroker, LiveGuard, LiveLimits
from project.paper.trader import CycleReport, PaperTrader
from project.scanner.engine import ScannerEngine

log = logging.getLogger(__name__)


@dataclass
class PreflightResult:
    checks: List[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append((name, ok, detail))

    def summary(self) -> str:
        lines = ["Live preflight"]
        for name, ok, detail in self.checks:
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        lines.append("  READY" if self.passed else "  NOT READY — resolve the failures above")
        return "\n".join(lines)


class LiveTrader(PaperTrader):
    """Portfolio trading against a real venue, behind a guard.

    Defaults are intentionally inert: dry-run on, not armed. Sending a real order takes
    two deliberate acts — `guard.limits.dry_run = False` and `arm("TRADE LIVE")`.
    """

    def __init__(
        self,
        engine: ScannerEngine,
        settings: Optional[Settings] = None,
        broker: Optional[Broker] = None,
        limits: Optional[LiveLimits] = None,
        state_path: str = ".state/live_state.json",
    ) -> None:
        settings = settings or DEFAULT_SETTINGS
        venue = broker or PaperBroker(settings.starting_cash)
        self.guard = LiveGuard(limits=limits or LiveLimits())
        guarded = GuardedBroker(venue, self.guard)
        super().__init__(engine, settings, guarded, state_path=state_path)
        self.venue = venue

    # -- operator surface ----------------------------------------------------------
    def arm(self, confirmation: str) -> bool:
        return self.guard.arm(confirmation)

    def disarm(self) -> None:
        self.guard.disarm()

    def kill(self, reason: str = "manual kill switch") -> None:
        self.guard.halt(reason)

    @property
    def is_live(self) -> bool:
        return self.guard.armed and not self.guard.limits.dry_run and not self.guard.halted

    # -- preflight -------------------------------------------------------------------
    def preflight(self, at: Optional[datetime] = None) -> PreflightResult:
        now = at or datetime.now(timezone.utc)
        out = PreflightResult()
        out.add("mode", self.settings.mode == "live",
                f"settings.mode is '{self.settings.mode}'")

        open_universes = self.engine.active_universes(now)
        out.add("market session", bool(open_universes),
                f"{len(open_universes)} universe(s) tradeable right now")

        probe = None
        for universe in open_universes:
            if universe.symbols:
                probe = universe.symbols[0].ticker
                break
        if probe is None:
            out.add("market data", False, "no symbol available to probe")
        else:
            bars = self.engine.provider.fetch(probe, 60)
            out.add("market data", bars is not None and bars.is_usable(30),
                    f"probe {probe}: {'fresh bars received' if bars else 'no data'}")

        out.add("capital", self.broker.cash > 0, f"cash ${self.broker.cash:,.0f}")
        out.add("risk config", self.settings.risk.max_risk_per_trade <= 0.02,
                f"{self.settings.risk.max_risk_per_trade:.1%} risk per trade")
        out.add("kill switch", not self.guard.halted,
                self.guard.halt_reason or "not engaged")
        out.add("order caps", self.guard.limits.max_order_notional > 0,
                f"max ${self.guard.limits.max_order_notional:,.0f} per order, "
                f"${self.guard.limits.max_daily_notional:,.0f} per day")
        out.add("execution mode", True,
                "DRY RUN — nothing is transmitted" if self.guard.limits.dry_run
                else ("ARMED — real orders will be sent" if self.guard.armed
                      else "live but not armed; orders will be refused"))
        return out

    # -- cycle -------------------------------------------------------------------------
    def run_cycle(self, at: Optional[datetime] = None) -> CycleReport:
        now = at or datetime.now(timezone.utc)
        self.guard.start_cycle(now)
        before = len(self.guard.blocked)
        report = super().run_cycle(now)
        for message in self.guard.blocked[before:]:
            report.blocked.append(f"guard: {message}")
        state = self.portfolio_state({})
        breaker = self.risk.circuit_breaker(state)
        if breaker and self.guard.armed:
            self.kill(f"circuit breaker tripped — {breaker}")
            report.blocked.append(f"guard: kill switch engaged ({breaker})")
        return report

    def snapshot(self) -> dict:
        data = super().snapshot()
        data.update({
            "armed": self.guard.armed,
            "dry_run": self.guard.limits.dry_run,
            "halted": self.guard.halted,
            "halt_reason": self.guard.halt_reason,
            "orders_today": self.guard.orders_today,
            "notional_today": round(self.guard.notional_today, 2),
            "guard_blocks": self.guard.blocked[-50:],
        })
        return data


__all__ = ["LiveTrader", "PreflightResult"]
