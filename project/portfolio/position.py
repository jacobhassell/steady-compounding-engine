"""Mastermind position management.

Framework-independent by design: Backtrader (or a live broker adapter) feeds bars in,
this module decides what to do. No I/O, no globals, fully deterministic — so the exact
same logic can be unit tested, backtested and traded live without divergence.

Lifecycle of every trade:
    INITIAL   -> hard ATR stop below entry, full size
    +1R hit   -> sell `partial_one_r`, stop moves to breakeven          (BREAKEVEN)
    +2R hit   -> sell `partial_two_r`, switch to ATR trailing stop      (TRAILING)
    exit      -> stop hit, score decay, or max holding days reached     (CLOSED)

Risk always wins: a stop never moves down, and every exit reason is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

from project.config.settings import RiskConfig, ScanConfig


class Stage(str, Enum):
    INITIAL = "initial"
    BREAKEVEN = "breakeven"
    TRAILING = "trailing"
    CLOSED = "closed"


@dataclass(frozen=True)
class PositionEvent:
    """One auditable thing that happened to a position."""

    day: int
    kind: str            # partial | stop_move | exit
    detail: str
    price: float
    shares: float = 0.0


@dataclass
class ManagedPosition:
    ticker: str
    entry: float
    initial_stop: float
    shares: float
    opened_day: int = 0
    sector: str = "UNKNOWN"
    country: str = "US"

    stage: Stage = Stage.INITIAL
    stop: float = 0.0
    remaining: float = 0.0
    highest_close: float = 0.0
    realized_pnl: float = 0.0
    exit_reason: Optional[str] = None
    events: List[PositionEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.entry <= 0:
            raise ValueError("entry price must be positive")
        if self.initial_stop >= self.entry:
            raise ValueError("initial stop must sit below entry")
        if self.shares <= 0:
            raise ValueError("share count must be positive")
        self.stop = self.initial_stop
        self.remaining = self.shares
        self.highest_close = self.entry

    # -- geometry -----------------------------------------------------------------
    @property
    def r_value(self) -> float:
        """One unit of risk, in price terms."""
        return self.entry - self.initial_stop

    @property
    def risk_at_open(self) -> float:
        return self.r_value * self.shares

    @property
    def is_open(self) -> bool:
        return self.stage is not Stage.CLOSED and self.remaining > 0

    def r_multiple(self, price: float) -> float:
        return (price - self.entry) / self.r_value if self.r_value else 0.0

    def open_risk(self, price: float) -> float:
        """Money still exposed if the current stop is hit. Never negative."""
        if not self.is_open:
            return 0.0
        return max(0.0, (price - self.stop) * 0.0 + (self.entry - self.stop) * self.remaining)

    def unrealized(self, price: float) -> float:
        return (price - self.entry) * self.remaining if self.is_open else 0.0

    def total_pnl(self, price: float) -> float:
        return self.realized_pnl + self.unrealized(price)

    # -- mutations ----------------------------------------------------------------
    def _log(self, day: int, kind: str, detail: str, price: float, shares: float = 0.0) -> None:
        self.events.append(PositionEvent(day, kind, detail, round(price, 4), round(shares, 4)))

    def raise_stop(self, new_stop: float, day: int, detail: str) -> bool:
        """Stops ratchet one way only."""
        if new_stop <= self.stop:
            return False
        self.stop = round(new_stop, 4)
        self._log(day, "stop_move", detail, self.stop)
        return True

    def _sell(self, fraction: float, price: float, day: int, detail: str) -> float:
        qty = min(self.remaining, round(self.shares * fraction, 6))
        if qty <= 0:
            return 0.0
        self.remaining = round(self.remaining - qty, 6)
        self.realized_pnl += (price - self.entry) * qty
        self._log(day, "partial", detail, price, qty)
        return qty

    def close(self, price: float, day: int, reason: str) -> float:
        qty = self.remaining
        if qty > 0:
            self.realized_pnl += (price - self.entry) * qty
            self.remaining = 0.0
        self.stage = Stage.CLOSED
        self.exit_reason = reason
        self._log(day, "exit", reason, price, qty)
        return qty


@dataclass
class ManagementAction:
    """What the manager decided on this bar — the caller executes it."""

    ticker: str
    closed: bool = False
    sold_shares: float = 0.0
    stop_moved: bool = False
    stop: float = 0.0
    stage: Stage = Stage.INITIAL
    notes: List[str] = field(default_factory=list)

    @property
    def acted(self) -> bool:
        return self.closed or self.sold_shares > 0 or self.stop_moved


class MastermindPositionManager:
    """Scales out of winners, cuts losers at a pre-defined line, lets runners run."""

    def __init__(self, risk: RiskConfig, scan: Optional[ScanConfig] = None) -> None:
        self.risk = risk
        self.scan = scan

    def open_position(
        self,
        ticker: str,
        entry: float,
        stop: float,
        shares: float,
        day: int = 0,
        sector: str = "UNKNOWN",
        country: str = "US",
    ) -> ManagedPosition:
        return ManagedPosition(
            ticker=ticker, entry=entry, initial_stop=stop, shares=shares,
            opened_day=day, sector=sector, country=country,
        )

    def on_bar(
        self,
        pos: ManagedPosition,
        *,
        day: int,
        high: float,
        low: float,
        close: float,
        atr: Optional[float] = None,
        score: Optional[float] = None,
    ) -> ManagementAction:
        """Process one completed bar. Order of checks mirrors real-world fill priority."""
        action = ManagementAction(pos.ticker, stop=pos.stop, stage=pos.stage)
        if not pos.is_open:
            return action

        c = self.risk

        # 1. Stop always evaluated first — a gap through the stop is not a winner.
        if low <= pos.stop:
            fill = min(pos.stop, high if high < pos.stop else pos.stop)
            pos.close(fill, day, f"stop hit at {pos.stop:.2f}")
            action.closed = True
            action.stage = pos.stage
            action.notes.append(f"stopped out at {fill:.2f} ({pos.r_multiple(fill):+.2f}R)")
            return action

        pos.highest_close = max(pos.highest_close, close)

        # 2. Scale out at +1R, move to breakeven.
        if pos.stage is Stage.INITIAL and high >= pos.entry + pos.r_value:
            target = pos.entry + pos.r_value
            qty = pos._sell(c.partial_one_r, target, day, f"+1R partial at {target:.2f}")
            pos.stage = Stage.BREAKEVEN
            if qty:
                action.sold_shares += qty
                action.notes.append(f"sold {qty:g} at +1R")
            if pos.raise_stop(pos.entry, day, "stop to breakeven after +1R"):
                action.stop_moved = True
                action.notes.append("stop moved to breakeven — trade is now free")

        # 3. Scale out at +2R, hand the runner to the ATR trail.
        if pos.stage is Stage.BREAKEVEN and high >= pos.entry + 2 * pos.r_value:
            target = pos.entry + 2 * pos.r_value
            qty = pos._sell(c.partial_two_r, target, day, f"+2R partial at {target:.2f}")
            pos.stage = Stage.TRAILING
            if qty:
                action.sold_shares += qty
                action.notes.append(f"sold {qty:g} at +2R")
            if pos.raise_stop(pos.entry + pos.r_value, day, "stop to +1R after +2R"):
                action.stop_moved = True

        # 4. Trail the runner on ATR.
        if pos.stage is Stage.TRAILING and atr and atr > 0:
            trail = close - c.atr_trail_multiple * atr
            if pos.raise_stop(trail, day, f"ATR trail ({c.atr_trail_multiple:g}x)"):
                action.stop_moved = True
                action.notes.append(f"trailing stop raised to {pos.stop:.2f}")

        # 5. Setup decay — tighten before the thesis fully breaks.
        if score is not None and self.scan is not None and pos.is_open:
            if score < self.scan.exit_score_threshold:
                pos.close(close, day, f"score {score:.0f} below exit threshold")
                action.closed = True
                action.notes.append("thesis invalidated — exited on score collapse")
            elif score < self.scan.score_decay_tighten and atr:
                tighten = close - atr
                if pos.raise_stop(tighten, day, f"score decay {score:.0f} — stop tightened"):
                    action.stop_moved = True
                    action.notes.append("score decaying — stop tightened to 1 ATR")

        # 6. Time stop: capital parked in a stalled trade is capital not compounding.
        if pos.is_open and (day - pos.opened_day) >= c.max_holding_days:
            pos.close(close, day, f"max holding period of {c.max_holding_days} days reached")
            action.closed = True
            action.notes.append("time stop — recycling capital")

        action.stop = pos.stop
        action.stage = pos.stage
        return action
