"""Broker abstraction and a deterministic paper broker.

Live trading is a swap of the `Broker` implementation, not a rewrite of the
strategy. Every fill carries commission and slippage so paper results are
directly comparable to the backtester's assumptions.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


_ids = itertools.count(1)


@dataclass
class Order:
    ticker: str
    side: Side
    shares: float
    type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    reason: str = ""
    id: str = field(default_factory=lambda: f"ORD-{next(_ids):06d}")
    status: OrderStatus = OrderStatus.PENDING
    reject_reason: str = ""

    def __post_init__(self) -> None:
        if self.shares <= 0:
            raise ValueError("Order size must be positive")


@dataclass(frozen=True)
class Fill:
    order_id: str
    ticker: str
    side: Side
    shares: float
    price: float
    commission: float
    slippage: float
    at: datetime
    reason: str = ""

    @property
    def notional(self) -> float:
        return self.shares * self.price

    @property
    def cash_delta(self) -> float:
        """Signed effect on cash, costs included."""
        gross = -self.notional if self.side is Side.BUY else self.notional
        return round(gross - self.commission, 2)


@dataclass
class BrokerPosition:
    ticker: str
    shares: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_price


class Broker:
    """Interface every execution venue must satisfy."""

    def submit(self, order: Order, reference_price: float) -> Optional[Fill]:  # pragma: no cover
        raise NotImplementedError

    @property
    def cash(self) -> float:  # pragma: no cover
        raise NotImplementedError

    def position(self, ticker: str) -> Optional[BrokerPosition]:  # pragma: no cover
        raise NotImplementedError


class PaperBroker(Broker):
    """Simulated venue: instant fills at the reference price plus realistic costs.

    Pessimistic on purpose — buys fill above the reference, sells fill below it,
    and an order that cannot be paid for is rejected rather than silently shrunk.
    """

    def __init__(
        self,
        starting_cash: float,
        commission: float = 0.0005,
        slippage: float = 0.0005,
        clock=None,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("Starting cash must be positive")
        self.starting_cash = starting_cash
        self._cash = starting_cash
        self.commission_rate = commission
        self.slippage_rate = slippage
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.positions: Dict[str, BrokerPosition] = {}
        self.fills: List[Fill] = []
        self.rejected: List[Order] = []
        self.realized_pnl: float = 0.0

    # -- helpers ---------------------------------------------------------------
    @property
    def cash(self) -> float:
        return round(self._cash, 2)

    def position(self, ticker: str) -> Optional[BrokerPosition]:
        return self.positions.get(ticker)

    def equity(self, marks: Dict[str, float]) -> float:
        held = sum(p.shares * marks.get(t, p.avg_price) for t, p in self.positions.items())
        return round(self._cash + held, 2)

    def fill_price(self, side: Side, reference_price: float) -> float:
        drift = 1 + self.slippage_rate if side is Side.BUY else 1 - self.slippage_rate
        return round(reference_price * drift, 4)

    def _reject(self, order: Order, why: str) -> None:
        order.status = OrderStatus.REJECTED
        order.reject_reason = why
        self.rejected.append(order)
        log.info("Order %s rejected: %s", order.id, why)

    # -- execution -------------------------------------------------------------
    def submit(self, order: Order, reference_price: float) -> Optional[Fill]:
        if reference_price <= 0:
            self._reject(order, "no valid reference price")
            return None

        if order.type is OrderType.LIMIT and order.limit_price is not None:
            if order.side is Side.BUY and reference_price > order.limit_price:
                self._reject(order, f"limit {order.limit_price:.2f} not marketable")
                return None
            if order.side is Side.SELL and reference_price < order.limit_price:
                self._reject(order, f"limit {order.limit_price:.2f} not marketable")
                return None

        price = self.fill_price(order.side, reference_price)
        commission = round(price * order.shares * self.commission_rate, 4)
        slippage = round(abs(price - reference_price) * order.shares, 4)

        if order.side is Side.BUY:
            cost = price * order.shares + commission
            if cost > self._cash + 1e-9:
                self._reject(order, "insufficient cash")
                return None
            existing = self.positions.get(order.ticker)
            if existing:
                total = existing.shares + order.shares
                existing.avg_price = round(
                    (existing.cost_basis + price * order.shares) / total, 4)
                existing.shares = total
            else:
                self.positions[order.ticker] = BrokerPosition(order.ticker, order.shares, price)
            self._cash -= cost
        else:
            held = self.positions.get(order.ticker)
            if held is None or held.shares + 1e-9 < order.shares:
                self._reject(order, "cannot sell more than is held")
                return None
            self.realized_pnl += round((price - held.avg_price) * order.shares - commission, 4)
            held.shares = round(held.shares - order.shares, 6)
            if held.shares <= 1e-9:
                del self.positions[order.ticker]
            self._cash += price * order.shares - commission

        fill = Fill(order.id, order.ticker, order.side, order.shares, price,
                    commission, slippage, self._clock(), order.reason)
        order.status = OrderStatus.FILLED
        self.fills.append(fill)
        log.info("FILL %s %s %g @ %.2f (%s)", order.side.value.upper(), order.ticker,
                 order.shares, price, order.reason or "no reason given")
        return fill


__all__ = [
    "Broker", "BrokerPosition", "Fill", "Order", "OrderStatus", "OrderType",
    "PaperBroker", "Side",
]
