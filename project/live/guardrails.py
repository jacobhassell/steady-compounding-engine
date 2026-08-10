"""Guardrails between the strategy and real money.

Everything here assumes the worst: that a data feed lies, that a loop runs twice, that
a fat-fingered config asks for a million-dollar order on a five-dollar stock. Nothing
reaches a real venue unless it passes every check and the operator has explicitly armed
the system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence

from project.execution.broker import Broker, Fill, Order, OrderStatus, Side

log = logging.getLogger(__name__)


class TradingHalted(RuntimeError):
    """Raised when the kill switch is engaged and an order is still attempted."""


@dataclass
class LiveLimits:
    """Hard operational ceilings. These are separate from strategy risk limits —
    they exist to contain bugs, not to express an opinion about the market."""

    max_order_notional: float = 25_000.0
    max_daily_notional: float = 150_000.0
    max_orders_per_day: int = 40
    max_orders_per_cycle: int = 5
    max_shares_per_order: float = 100_000.0
    min_order_notional: float = 100.0
    allowed_tickers: Optional[Sequence[str]] = None   # None = no whitelist
    require_arm: bool = True
    dry_run: bool = True


@dataclass
class GuardDecision:
    allowed: bool
    reason: str


@dataclass
class LiveGuard:
    """Stateful pre-trade risk checks with a manual kill switch."""

    limits: LiveLimits = field(default_factory=LiveLimits)
    armed: bool = False
    halted: bool = False
    halt_reason: str = ""
    day: Optional[date] = None
    orders_today: int = 0
    notional_today: float = 0.0
    cycle_orders: int = 0
    blocked: List[str] = field(default_factory=list)

    # -- operator controls --------------------------------------------------------
    def arm(self, confirmation: str) -> bool:
        """Arming requires typing the exact phrase — no accidental live trading."""
        if confirmation.strip().upper() != "TRADE LIVE":
            log.warning("Arm refused: confirmation phrase did not match.")
            return False
        self.armed = True
        self.halted = False
        self.halt_reason = ""
        log.warning("LIVE TRADING ARMED. Real orders may now be sent.")
        return True

    def disarm(self) -> None:
        self.armed = False
        log.warning("Live trading disarmed. Orders will be refused.")

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.armed = False
        log.error("KILL SWITCH: %s", reason)

    # -- daily bookkeeping ---------------------------------------------------------
    def start_cycle(self, at: Optional[datetime] = None) -> None:
        now = at or datetime.now(timezone.utc)
        today = now.date()
        if self.day != today:
            self.day = today
            self.orders_today = 0
            self.notional_today = 0.0
        self.cycle_orders = 0

    # -- the check ------------------------------------------------------------------
    def check(self, order: Order, reference_price: float) -> GuardDecision:
        lim = self.limits
        notional = order.shares * reference_price

        if self.halted:
            return self._no(order, f"trading halted — {self.halt_reason}")
        if lim.require_arm and not self.armed:
            return self._no(order, "system not armed for live trading")
        if reference_price <= 0:
            return self._no(order, "no valid reference price")
        if lim.allowed_tickers is not None and order.ticker not in lim.allowed_tickers:
            return self._no(order, f"{order.ticker} is not on the live whitelist")
        if order.shares > lim.max_shares_per_order:
            return self._no(order, f"{order.shares:g} shares exceeds per-order cap")
        if notional > lim.max_order_notional:
            return self._no(order, f"order notional {notional:,.0f} exceeds cap "
                                   f"{lim.max_order_notional:,.0f}")
        if order.side is Side.BUY and notional < lim.min_order_notional:
            return self._no(order, f"order notional {notional:,.0f} is below the "
                                   f"economic minimum")
        if self.cycle_orders >= lim.max_orders_per_cycle:
            return self._no(order, "per-cycle order limit reached — possible runaway loop")
        if self.orders_today >= lim.max_orders_per_day:
            return self._no(order, "daily order count limit reached")
        if self.notional_today + notional > lim.max_daily_notional:
            return self._no(order, f"daily traded notional cap "
                                   f"{lim.max_daily_notional:,.0f} would be breached")
        return GuardDecision(True, "passed all pre-trade checks")

    def _no(self, order: Order, why: str) -> GuardDecision:
        message = f"{order.ticker} {order.side.value} {order.shares:g} — {why}"
        self.blocked.append(message)
        log.warning("Pre-trade block: %s", message)
        return GuardDecision(False, why)

    def record(self, order: Order, reference_price: float) -> None:
        self.cycle_orders += 1
        self.orders_today += 1
        self.notional_today += order.shares * reference_price


class GuardedBroker(Broker):
    """Wraps any broker so that no order reaches it without passing `LiveGuard`.

    In dry-run mode orders are logged and rejected — the intended default until an
    operator has watched the same signals for a full session and armed the system.
    """

    def __init__(self, inner: Broker, guard: Optional[LiveGuard] = None) -> None:
        self.inner = inner
        self.guard = guard or LiveGuard()
        self.simulated: List[Order] = []

    @property
    def cash(self) -> float:
        return self.inner.cash

    def position(self, ticker: str):
        return self.inner.position(ticker)

    def equity(self, marks: Dict[str, float]) -> float:
        equity = getattr(self.inner, "equity", None)
        return equity(marks) if callable(equity) else self.inner.cash

    @property
    def realized_pnl(self) -> float:
        return getattr(self.inner, "realized_pnl", 0.0)

    def submit(self, order: Order, reference_price: float) -> Optional[Fill]:
        decision = self.guard.check(order, reference_price)
        if not decision.allowed:
            order.status = OrderStatus.REJECTED
            order.reject_reason = decision.reason
            return None
        if self.guard.limits.dry_run:
            order.status = OrderStatus.CANCELLED
            order.reject_reason = "dry run — order not transmitted"
            self.simulated.append(order)
            log.warning("DRY RUN would send: %s %s %g @ ~%.2f (%s)", order.side.value.upper(),
                        order.ticker, order.shares, reference_price, order.reason)
            return None
        fill = self.inner.submit(order, reference_price)
        if fill is not None:
            self.guard.record(order, reference_price)
        return fill


__all__ = ["GuardDecision", "GuardedBroker", "LiveGuard", "LiveLimits", "TradingHalted"]
