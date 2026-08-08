"""Deterministic tests for Mastermind position management. No network, no framework."""

from __future__ import annotations

import unittest

from project.config.settings import RiskConfig, ScanConfig
from project.portfolio.position import ManagedPosition, MastermindPositionManager, Stage


def bar(mgr, pos, day, high, low, close, atr=None, score=None, open_=None):
    return mgr.on_bar(pos, day=day, high=high, low=low, close=close, open_=open_, atr=atr, score=score)


class PositionGeometryTests(unittest.TestCase):
    def test_r_value_and_risk(self):
        p = ManagedPosition("AAPL", entry=100.0, initial_stop=90.0, shares=50)
        self.assertEqual(p.r_value, 10.0)
        self.assertEqual(p.risk_at_open, 500.0)
        self.assertEqual(p.remaining, 50)
        self.assertIs(p.stage, Stage.INITIAL)

    def test_invalid_stop_rejected(self):
        with self.assertRaises(ValueError):
            ManagedPosition("X", entry=10.0, initial_stop=12.0, shares=10)

    def test_stops_never_move_down(self):
        p = ManagedPosition("X", entry=100.0, initial_stop=90.0, shares=10)
        self.assertTrue(p.raise_stop(95.0, 1, "up"))
        self.assertFalse(p.raise_stop(92.0, 2, "down"))
        self.assertEqual(p.stop, 95.0)


class LadderTests(unittest.TestCase):
    def setUp(self):
        self.mgr = MastermindPositionManager(RiskConfig(), ScanConfig())
        self.pos = self.mgr.open_position("TEST", entry=100.0, stop=90.0, shares=100, day=0)

    def test_one_r_partial_and_breakeven(self):
        a = bar(self.mgr, self.pos, 1, high=110.5, low=99.0, close=110.0, atr=5.0)
        self.assertEqual(a.sold_shares, 25.0)
        self.assertIs(self.pos.stage, Stage.BREAKEVEN)
        self.assertEqual(self.pos.stop, 100.0)
        self.assertEqual(self.pos.remaining, 75.0)

    def test_two_r_partial_switches_to_trailing(self):
        bar(self.mgr, self.pos, 1, 110.5, 99.0, 110.0, atr=5.0)
        a = bar(self.mgr, self.pos, 2, 121.0, 109.0, 120.0, atr=2.0)
        self.assertEqual(a.sold_shares, 25.0)
        self.assertIs(self.pos.stage, Stage.TRAILING)
        self.assertEqual(self.pos.remaining, 50.0)
        # stop = max(+1R=110, trail=120-3*2=114)
        self.assertEqual(self.pos.stop, 114.0)

    def test_trailing_stop_ratchets_with_price(self):
        bar(self.mgr, self.pos, 1, 110.5, 99.0, 110.0, atr=5.0)
        bar(self.mgr, self.pos, 2, 121.0, 109.0, 120.0, atr=2.0)
        bar(self.mgr, self.pos, 3, 131.0, 119.0, 130.0, atr=2.0)
        self.assertEqual(self.pos.stop, 124.0)
        bar(self.mgr, self.pos, 4, 130.0, 125.0, 126.0, atr=2.0)
        self.assertEqual(self.pos.stop, 124.0)  # never retreats

    def test_full_winning_cycle_is_profitable(self):
        bar(self.mgr, self.pos, 1, 110.5, 99.0, 110.0, atr=5.0)
        bar(self.mgr, self.pos, 2, 121.0, 109.0, 120.0, atr=2.0)
        bar(self.mgr, self.pos, 3, 131.0, 119.0, 130.0, atr=2.0)
        bar(self.mgr, self.pos, 4, 130.0, 120.0, 121.0, atr=2.0)  # trips 124 stop
        self.assertFalse(self.pos.is_open)
        # 25@110 + 25@120 + 50@124 vs entry 100
        self.assertAlmostEqual(self.pos.realized_pnl, 250 + 500 + 1200, places=2)


class LossAndExitTests(unittest.TestCase):
    def setUp(self):
        self.mgr = MastermindPositionManager(RiskConfig(), ScanConfig())

    def test_initial_stop_caps_loss_at_one_r(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        a = bar(self.mgr, pos, 1, high=101.0, low=89.0, close=91.0, atr=4.0)
        self.assertTrue(a.closed)
        self.assertAlmostEqual(pos.realized_pnl, -1000.0)
        self.assertEqual(pos.exit_reason, "stop hit at 90.00")

    def test_breakeven_stop_makes_trade_free(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        bar(self.mgr, pos, 1, 110.5, 99.0, 110.0, atr=5.0)
        bar(self.mgr, pos, 2, 108.0, 95.0, 96.0, atr=5.0)  # back through breakeven
        self.assertFalse(pos.is_open)
        self.assertAlmostEqual(pos.realized_pnl, 250.0)  # +1R partial kept, runner flat

    def test_score_collapse_forces_exit(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        a = bar(self.mgr, pos, 1, 102.0, 99.0, 101.0, atr=3.0, score=20.0)
        self.assertTrue(a.closed)
        self.assertIn("below exit threshold", pos.exit_reason or "")

    def test_score_decay_tightens_stop(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        a = bar(self.mgr, pos, 1, 106.0, 99.0, 105.0, atr=3.0, score=50.0)
        self.assertTrue(a.stop_moved)
        self.assertEqual(pos.stop, 102.0)
        self.assertTrue(pos.is_open)

    def test_time_stop_recycles_capital(self):
        cfg = RiskConfig(max_holding_days=5)
        mgr = MastermindPositionManager(cfg, ScanConfig())
        pos = mgr.open_position("TEST", 100.0, 90.0, 100, day=0)
        bar(mgr, pos, 5, 101.0, 99.0, 100.5, atr=2.0)
        self.assertFalse(pos.is_open)
        self.assertIn("max holding period", pos.exit_reason or "")

    def test_gap_through_stop_fills_at_the_open(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        a = bar(self.mgr, pos, 1, high=86.0, low=84.0, close=85.0, open_=85.5, atr=3.0)
        self.assertTrue(a.closed)
        self.assertAlmostEqual(pos.realized_pnl, -1450.0)
        self.assertIn("gapped through", pos.exit_reason or "")

    def test_closed_position_ignores_further_bars(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        bar(self.mgr, pos, 1, 101.0, 85.0, 86.0, atr=3.0)
        pnl = pos.realized_pnl
        a = bar(self.mgr, pos, 2, 120.0, 110.0, 119.0, atr=3.0)
        self.assertFalse(a.acted)
        self.assertEqual(pos.realized_pnl, pnl)

    def test_events_form_an_audit_trail(self):
        pos = self.mgr.open_position("TEST", 100.0, 90.0, 100)
        bar(self.mgr, pos, 1, 110.5, 99.0, 110.0, atr=5.0)
        kinds = [e.kind for e in pos.events]
        self.assertIn("partial", kinds)
        self.assertIn("stop_move", kinds)


class StrategyAdapterTests(unittest.TestCase):
    def test_module_imports_without_backtrader(self):
        from project.strategy import mastermind

        self.assertIsInstance(mastermind.BACKTRADER_AVAILABLE, bool)
        if not mastermind.BACKTRADER_AVAILABLE:
            with self.assertRaises(ImportError):
                mastermind.build_cerebro()


if __name__ == "__main__":
    unittest.main()
