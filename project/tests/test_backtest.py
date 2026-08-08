"""Tests for performance analytics and the event-driven backtester. Deterministic, offline."""

from __future__ import annotations

import math
import random
import unittest

from project.backtests.engine import BacktestConfig, Backtester
from project.config.settings import Settings
from project.data.provider import Bars
from project.reports.performance import (
    TradeRecord, build_report, cagr, format_report, max_drawdown, profit_factor,
    sharpe_ratio, sortino_ratio, verdict,
)


def trade(pnl: float, r: float, reason: str = "stop hit at 10.00", ticker: str = "T") -> TradeRecord:
    return TradeRecord(ticker, 0, 5, 100.0, 100.0 + pnl, 1, pnl, r, reason)


class MetricTests(unittest.TestCase):
    def test_max_drawdown(self):
        dd, length = max_drawdown([100, 120, 90, 130])
        self.assertAlmostEqual(dd, 0.25)
        self.assertEqual(length, 1)

    def test_no_drawdown_on_monotonic_curve(self):
        dd, length = max_drawdown([100, 101, 102])
        self.assertEqual(dd, 0.0)
        self.assertEqual(length, 0)

    def test_sharpe_zero_for_flat_curve(self):
        self.assertEqual(sharpe_ratio([0.0, 0.0, 0.0]), 0.0)

    def test_sortino_ignores_upside_volatility(self):
        upside_only = [0.01, 0.02, 0.03, 0.01]
        self.assertGreater(sortino_ratio(upside_only), sharpe_ratio(upside_only))

    def test_cagr_doubling_in_one_year(self):
        curve = [100.0] + [100.0 * (2 ** (i / 252)) for i in range(1, 253)]
        self.assertAlmostEqual(cagr(curve), 1.0, places=2)

    def test_profit_factor(self):
        self.assertAlmostEqual(profit_factor([trade(200, 2), trade(-100, -1)]), 2.0)
        self.assertEqual(profit_factor([]), 0.0)
        self.assertTrue(math.isinf(profit_factor([trade(50, 1)])))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.trades = [trade(300, 3), trade(-100, -1), trade(-100, -1), trade(200, 2)]
        self.report = build_report([100_000, 100_300, 100_200, 100_100, 100_300], self.trades)

    def test_core_aggregates(self):
        r = self.report
        self.assertEqual(r.trades, 4)
        self.assertEqual(r.wins, 2)
        self.assertAlmostEqual(r.win_rate, 0.5)
        self.assertAlmostEqual(r.expectancy_r, 0.75)
        self.assertAlmostEqual(r.profit_factor, 2.5)
        self.assertEqual(r.largest_loss, -100)

    def test_exit_reasons_are_grouped(self):
        self.assertEqual(self.report.exit_reasons, {"stop hit": 4})

    def test_format_and_verdict(self):
        text = format_report(self.report)
        self.assertIn("BACKTEST", format_report(self.report, "Backtest"))
        self.assertIn("Sharpe", text)
        self.assertIn("INCONCLUSIVE", verdict(self.report))

    def test_verdict_rejects_deep_drawdown(self):
        deep = build_report([100.0, 60.0, 80.0], [trade(1, 0.1) for _ in range(30)])
        self.assertIn("REJECT", verdict(deep))

    def test_verdict_rejects_negative_expectancy(self):
        losing = build_report([100.0, 99.0, 98.0], [trade(-1, -0.5) for _ in range(30)])
        self.assertIn("REJECT", verdict(losing))


def synthetic_bars(ticker: str, n: int = 220, seed: int = 7, drift: float = 0.0006) -> Bars:
    """Trending series with pullbacks — enough structure to trigger real signals."""
    rng = random.Random(seed)
    price = 50.0
    b = Bars(ticker=ticker)
    for i in range(n):
        shock = rng.gauss(drift, 0.018) + (0.03 * math.sin(i / 9))
        price = max(2.0, price * (1 + shock))
        high = price * (1 + abs(rng.gauss(0, 0.008)))
        low = price * (1 - abs(rng.gauss(0, 0.008)))
        b.dates.append(f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}")
        b.opens.append(round(price * (1 + rng.gauss(0, 0.002)), 4))
        b.highs.append(round(max(high, price), 4))
        b.lows.append(round(min(low, price), 4))
        b.closes.append(round(price, 4))
        b.volumes.append(1_500_000 + rng.random() * 800_000)
    return b


class BacktesterTests(unittest.TestCase):
    def setUp(self):
        self.history = {
            "AAA": synthetic_bars("AAA", seed=1),
            "BBB": synthetic_bars("BBB", seed=2, drift=-0.0004),
            "CCC": synthetic_bars("CCC", seed=3),
        }
        self.bt = Backtester(Settings(), BacktestConfig(warmup_bars=80, max_new_positions_per_bar=2))

    def test_run_produces_a_complete_result(self):
        res = self.bt.run(self.history, sectors={"AAA": "Tech", "BBB": "Energy", "CCC": "Tech"})
        self.assertEqual(res.symbols_tested, 3)
        self.assertGreater(len(res.equity_curve), 100)
        self.assertEqual(res.report.trades, len(res.trades))
        self.assertIsInstance(res.summary(), str)

    def test_equity_never_goes_negative(self):
        res = self.bt.run(self.history)
        self.assertTrue(all(e > 0 for e in res.equity_curve))

    def test_deterministic_across_runs(self):
        a = self.bt.run(self.history)
        b = Backtester(Settings(), BacktestConfig(warmup_bars=80, max_new_positions_per_bar=2)).run(self.history)
        self.assertEqual(a.equity_curve, b.equity_curve)
        self.assertEqual(len(a.trades), len(b.trades))

    def test_every_trade_records_a_reason(self):
        res = self.bt.run(self.history)
        for t in res.trades:
            self.assertTrue(t.reason)
            self.assertGreaterEqual(t.exit_day, t.entry_day)

    def test_losses_are_bounded_by_risk_config(self):
        """Only an overnight gap may take a trade beyond its planned 1R of risk."""
        res = self.bt.run(self.history)
        for t in res.trades:
            if "gapped" in t.reason:
                continue
            self.assertGreater(t.r_multiple, -1.2, f"{t.ticker} lost {t.r_multiple:.2f}R")

    def test_rejects_history_that_is_too_short(self):
        with self.assertRaises(ValueError):
            self.bt.run({"XXX": synthetic_bars("XXX", n=20)})


if __name__ == "__main__":
    unittest.main()
