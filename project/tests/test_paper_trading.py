"""Deterministic tests for the paper broker and the paper trading loop. No network."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from project.config.settings import DEFAULT_SETTINGS
from project.execution.broker import Order, OrderStatus, OrderType, PaperBroker, Side
from project.paper.trader import PaperTrader


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.b = PaperBroker(100_000.0, commission=0.001, slippage=0.001)

    def test_buy_costs_more_than_the_reference_price(self):
        fill = self.b.submit(Order("AAPL", Side.BUY, 100), 100.0)
        self.assertIsNotNone(fill)
        self.assertGreater(fill.price, 100.0)
        self.assertLess(self.b.cash, 100_000.0 - 100 * 100.0)
        self.assertEqual(self.b.position("AAPL").shares, 100)

    def test_sell_fills_below_the_reference_price(self):
        self.b.submit(Order("AAPL", Side.BUY, 100), 100.0)
        fill = self.b.submit(Order("AAPL", Side.SELL, 100), 120.0)
        self.assertLess(fill.price, 120.0)
        self.assertIsNone(self.b.position("AAPL"))
        self.assertGreater(self.b.realized_pnl, 0)

    def test_cannot_spend_cash_it_does_not_have(self):
        order = Order("AAPL", Side.BUY, 10_000)
        self.assertIsNone(self.b.submit(order, 100.0))
        self.assertIs(order.status, OrderStatus.REJECTED)
        self.assertEqual(order.reject_reason, "insufficient cash")

    def test_cannot_sell_more_than_is_held(self):
        self.b.submit(Order("AAPL", Side.BUY, 10), 100.0)
        order = Order("AAPL", Side.SELL, 50)
        self.assertIsNone(self.b.submit(order, 100.0))
        self.assertIs(order.status, OrderStatus.REJECTED)

    def test_partial_sell_keeps_average_price(self):
        self.b.submit(Order("AAPL", Side.BUY, 100), 100.0)
        avg = self.b.position("AAPL").avg_price
        self.b.submit(Order("AAPL", Side.SELL, 40), 110.0)
        self.assertEqual(self.b.position("AAPL").shares, 60)
        self.assertEqual(self.b.position("AAPL").avg_price, avg)

    def test_averaging_up_blends_the_basis(self):
        self.b.submit(Order("AAPL", Side.BUY, 100), 100.0)
        self.b.submit(Order("AAPL", Side.BUY, 100), 200.0)
        self.assertAlmostEqual(self.b.position("AAPL").avg_price, 150.15, places=1)

    def test_unmarketable_limit_is_rejected(self):
        order = Order("AAPL", Side.BUY, 10, type=OrderType.LIMIT, limit_price=90.0)
        self.assertIsNone(self.b.submit(order, 100.0))
        self.assertIs(order.status, OrderStatus.REJECTED)

    def test_equity_marks_to_market(self):
        self.b.submit(Order("AAPL", Side.BUY, 100), 100.0)
        self.assertGreater(self.b.equity({"AAPL": 150.0}), 100_000.0)
        self.assertLess(self.b.equity({"AAPL": 50.0}), 100_000.0)

    def test_zero_size_order_is_impossible(self):
        with self.assertRaises(ValueError):
            Order("AAPL", Side.BUY, 0)


class _StubScan:
    def __init__(self):
        self.scanned = 0
        self.candidates = []


class _StubEngine:
    """Scanner stand-in: no network, no candidates, so the loop must simply stay flat."""

    def __init__(self):
        self.provider = self
        self.settings = DEFAULT_SETTINGS

    def scan(self, at=None, universes=None):
        return _StubScan()

    def entry_ready(self, candidate):
        return True, "ok"

    def fetch(self, ticker, bars, interval="1d"):
        return None


class PaperTraderTests(unittest.TestCase):
    def test_flat_cycle_preserves_capital_and_persists_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            trader = PaperTrader(_StubEngine(), state_path=path)
            report = trader.run_cycle(at=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc))
            self.assertEqual(report.equity, DEFAULT_SETTINGS.starting_cash)
            self.assertEqual(report.heat, 0.0)
            self.assertEqual(report.entries, [])
            self.assertTrue(os.path.exists(path))

    def test_snapshot_shape_is_stable(self):
        trader = PaperTrader(_StubEngine(), state_path=os.devnull)
        snap = trader.snapshot()
        for key in ("cycles", "cash", "realized_pnl", "open_positions",
                    "closed_positions", "journal"):
            self.assertIn(key, snap)


if __name__ == "__main__":
    unittest.main()
