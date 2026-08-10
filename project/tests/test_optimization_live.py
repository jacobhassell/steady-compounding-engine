"""Deterministic tests for walk-forward optimisation and live guardrails."""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.data.provider import Bars
from project.execution.broker import Order, PaperBroker, Side
from project.live.guardrails import GuardedBroker, LiveGuard, LiveLimits
from project.optimization.walkforward import (
    DEFAULT_GRID, Optimizer, apply_overrides, expand_grid, objective, slice_history,
)
from project.reports.performance import PerformanceReport


def make_bars(ticker: str, n: int = 400, seed: float = 1.0) -> Bars:
    """Trending series with periodic pullbacks — enough structure to trade."""
    start = datetime(2022, 1, 3, tzinfo=timezone.utc)
    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    price = 50.0 * seed
    for i in range(n):
        wave = math.sin(i / 11.0) * 1.5 + math.sin(i / 37.0) * 3.0
        price = max(5.0, price * (1 + 0.0012) + wave * 0.12)
        o = price * 0.997
        c = price
        dates.append(start + timedelta(days=i))
        opens.append(round(o, 4))
        highs.append(round(max(o, c) * 1.008, 4))
        lows.append(round(min(o, c) * 0.992, 4))
        closes.append(round(c, 4))
        volumes.append(2_000_000 + (i % 20) * 50_000)
    return Bars(ticker, dates, opens, highs, lows, closes, volumes)


def report(**kwargs) -> PerformanceReport:
    base = dict(
        starting_equity=100_000.0, ending_equity=110_000.0, total_return=0.1, cagr=0.1,
        max_drawdown=0.05, max_drawdown_days=10, sharpe=1.0, sortino=1.5, volatility=0.1,
        trades=20, wins=12, losses=8, win_rate=0.6, profit_factor=1.8, expectancy_r=0.4,
        avg_win_r=1.5, avg_loss_r=-0.9, largest_loss=-1000.0, avg_hold_days=12.0,
    )
    base.update(kwargs)
    return PerformanceReport(**base)


class OverrideTests(unittest.TestCase):
    def test_dotted_overrides_rebuild_frozen_config(self):
        tuned = apply_overrides(DEFAULT_SETTINGS, {"scan.min_entry_score": 80.0,
                                                   "risk.atr_stop_multiple": 3.0})
        self.assertEqual(tuned.scan.min_entry_score, 80.0)
        self.assertEqual(tuned.risk.atr_stop_multiple, 3.0)
        # original untouched
        self.assertEqual(DEFAULT_SETTINGS.scan.min_entry_score, 70.0)

    def test_unknown_setting_is_rejected_loudly(self):
        with self.assertRaises(KeyError):
            apply_overrides(DEFAULT_SETTINGS, {"scan.does_not_exist": 1})
        with self.assertRaises(KeyError):
            apply_overrides(DEFAULT_SETTINGS, {"nope.min_entry_score": 1})

    def test_grid_expansion_is_complete_and_stable(self):
        combos = expand_grid({"a": (1, 2), "b": ("x", "y", "z")})
        self.assertEqual(len(combos), 6)
        self.assertEqual(combos[0], {"a": 1, "b": "x"})
        self.assertEqual(expand_grid({}), [{}])
        self.assertEqual(len(expand_grid(DEFAULT_GRID)), 18)


class ObjectiveTests(unittest.TestCase):
    def test_no_trades_scores_zero(self):
        self.assertEqual(objective(report(trades=0)), 0.0)

    def test_drawdown_is_penalised(self):
        calm = objective(report(max_drawdown=0.05))
        rough = objective(report(max_drawdown=0.40))
        self.assertGreater(calm, rough)

    def test_thin_samples_are_discounted(self):
        many = objective(report(trades=40))
        few = objective(report(trades=3))
        self.assertGreater(many, few)

    def test_infinite_sortino_is_clamped(self):
        self.assertTrue(math.isfinite(objective(report(sortino=float("inf")))))


class SliceTests(unittest.TestCase):
    def test_slice_keeps_series_aligned(self):
        history = {"A": make_bars("A", 300), "B": make_bars("B", 300, seed=1.4)}
        cut = slice_history(history, 50, 150)
        self.assertEqual(len(cut["A"]), 100)
        self.assertEqual(len(cut["B"]), 100)
        self.assertEqual(cut["A"].closes[0], history["A"].closes[50])


class WalkForwardTests(unittest.TestCase):
    def setUp(self):
        self.history = {
            "AAA": make_bars("AAA", 420),
            "BBB": make_bars("BBB", 420, seed=1.6),
        }
        self.settings = Settings(starting_cash=100_000.0)
        self.opt = Optimizer(self.settings)
        self.grid = {"scan.min_entry_score": (60.0, 70.0)}

    def test_grid_search_ranks_best_first(self):
        trials = self.opt.grid_search(slice_history(self.history, 0, 260), self.grid)
        self.assertEqual(len(trials), 2)
        self.assertGreaterEqual(trials[0].score, trials[1].score)
        self.assertIn("min_entry_score", trials[0].label())

    def test_walk_forward_produces_folds_and_a_verdict(self):
        result = self.opt.walk_forward(self.history, self.grid, folds=2,
                                       train_bars=200, test_bars=60)
        self.assertGreaterEqual(len(result.folds), 1)
        self.assertEqual(result.trials_per_fold, 2)
        for fold in result.folds:
            self.assertLessEqual(fold.train[1], fold.test[0])
        self.assertIn(":", result.verdict())
        self.assertIn("Walk-forward", result.summary())

    def test_test_window_never_overlaps_training(self):
        result = self.opt.walk_forward(self.history, self.grid, folds=2,
                                       train_bars=200, test_bars=60)
        for fold in result.folds:
            self.assertEqual(fold.test[0], fold.train[1])

    def test_insufficient_history_is_refused(self):
        short = slice_history(self.history, 0, 100)
        with self.assertRaises(ValueError):
            Optimizer(self.settings).walk_forward(short, self.grid,
                                                  train_bars=200, test_bars=60)

    def test_results_are_deterministic(self):
        a = self.opt.walk_forward(self.history, self.grid, folds=2, train_bars=200, test_bars=60)
        b = self.opt.walk_forward(self.history, self.grid, folds=2, train_bars=200, test_bars=60)
        self.assertEqual([f.out_of_sample for f in a.folds], [f.out_of_sample for f in b.folds])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = LiveGuard(limits=LiveLimits(dry_run=False))

    def order(self, shares=100.0, ticker="AAPL", side=Side.BUY):
        return Order(ticker, side, shares, reason="test")

    def test_unarmed_system_refuses_everything(self):
        self.assertFalse(self.guard.check(self.order(), 100.0).allowed)

    def test_arming_requires_the_exact_phrase(self):
        self.assertFalse(self.guard.arm("trade"))
        self.assertFalse(self.guard.armed)
        self.assertTrue(self.guard.arm(" trade live "))
        self.assertTrue(self.guard.armed)

    def test_order_notional_cap(self):
        self.guard.arm("TRADE LIVE")
        self.guard.start_cycle()
        self.assertTrue(self.guard.check(self.order(100), 100.0).allowed)
        self.assertFalse(self.guard.check(self.order(1000), 100.0).allowed)

    def test_dust_orders_are_refused(self):
        self.guard.arm("TRADE LIVE")
        self.guard.start_cycle()
        self.assertFalse(self.guard.check(self.order(1), 10.0).allowed)

    def test_per_cycle_runaway_protection(self):
        self.guard.arm("TRADE LIVE")
        self.guard.start_cycle()
        for _ in range(self.guard.limits.max_orders_per_cycle):
            o = self.order(10)
            self.assertTrue(self.guard.check(o, 100.0).allowed)
            self.guard.record(o, 100.0)
        self.assertFalse(self.guard.check(self.order(10), 100.0).allowed)

    def test_daily_notional_cap(self):
        guard = LiveGuard(limits=LiveLimits(dry_run=False, max_daily_notional=5_000.0,
                                            max_orders_per_cycle=99))
        guard.arm("TRADE LIVE")
        guard.start_cycle()
        o = self.order(40)
        self.assertTrue(guard.check(o, 100.0).allowed)
        guard.record(o, 100.0)
        self.assertFalse(guard.check(self.order(40), 100.0).allowed)

    def test_whitelist_blocks_unknown_symbols(self):
        guard = LiveGuard(limits=LiveLimits(dry_run=False, allowed_tickers=["MSFT"]))
        guard.arm("TRADE LIVE")
        guard.start_cycle()
        self.assertFalse(guard.check(self.order(ticker="AAPL"), 100.0).allowed)
        self.assertTrue(guard.check(self.order(ticker="MSFT"), 100.0).allowed)

    def test_kill_switch_overrides_arming(self):
        self.guard.arm("TRADE LIVE")
        self.guard.halt("data feed stale")
        self.assertFalse(self.guard.armed)
        decision = self.guard.check(self.order(), 100.0)
        self.assertFalse(decision.allowed)
        self.assertIn("halted", decision.reason)

    def test_new_day_resets_counters(self):
        self.guard.arm("TRADE LIVE")
        day1 = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
        self.guard.start_cycle(day1)
        o = self.order(10)
        self.guard.record(o, 100.0)
        self.assertEqual(self.guard.orders_today, 1)
        self.guard.start_cycle(day1 + timedelta(days=1))
        self.assertEqual(self.guard.orders_today, 0)
        self.assertEqual(self.guard.notional_today, 0.0)


class GuardedBrokerTests(unittest.TestCase):
    def setUp(self):
        self.inner = PaperBroker(100_000.0)

    def test_dry_run_never_transmits(self):
        guard = LiveGuard(limits=LiveLimits(dry_run=True))
        guard.arm("TRADE LIVE")
        guard.start_cycle()
        broker = GuardedBroker(self.inner, guard)
        fill = broker.submit(Order("AAPL", Side.BUY, 100, reason="x"), 100.0)
        self.assertIsNone(fill)
        self.assertEqual(len(broker.simulated), 1)
        self.assertEqual(self.inner.cash, 100_000.0)

    def test_armed_live_order_reaches_the_venue(self):
        guard = LiveGuard(limits=LiveLimits(dry_run=False))
        guard.arm("TRADE LIVE")
        guard.start_cycle()
        broker = GuardedBroker(self.inner, guard)
        fill = broker.submit(Order("AAPL", Side.BUY, 100, reason="x"), 100.0)
        self.assertIsNotNone(fill)
        self.assertLess(broker.cash, 100_000.0)
        self.assertEqual(guard.orders_today, 1)

    def test_blocked_order_is_marked_rejected(self):
        broker = GuardedBroker(self.inner, LiveGuard())
        order = Order("AAPL", Side.BUY, 100, reason="x")
        self.assertIsNone(broker.submit(order, 100.0))
        self.assertEqual(order.status.value, "rejected")
        self.assertIn("not armed", order.reject_reason)


if __name__ == "__main__":
    unittest.main()
