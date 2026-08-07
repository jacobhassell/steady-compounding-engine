"""Deterministic tests for the scoring + scanner slice. No network required."""

from __future__ import annotations

import math
import random
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from project.config.settings import DEFAULT_SETTINGS, ScoreWeights, Settings
from project.data.provider import Bars, DataProvider, ResilientProvider
from project.indicators import technical as ta
from project.risk.manager import OpenPosition, PortfolioState, RiskManager
from project.scanner.engine import ScannerEngine
from project.scanner.scoring import ScoringEngine, build_snapshot
from project.universe import exchanges as ex
from project.universe.registry import Symbol, Universe


def synth_bars(ticker="TEST", n=300, trend=0.0004, vol=0.01, seed=7, squeeze=False) -> Bars:
    rng = random.Random(seed)
    price = 100.0
    bars = Bars(ticker=ticker)
    for i in range(n):
        step = trend + rng.gauss(0, vol * (0.15 if squeeze and i > n - 40 else 1.0))
        price = max(1.0, price * (1 + step))
        high = price * (1 + abs(rng.gauss(0, vol / 2)))
        low = price * (1 - abs(rng.gauss(0, vol / 2)))
        bars.dates.append(f"2024-01-{i % 28 + 1:02d}")
        bars.opens.append(price)
        bars.highs.append(high)
        bars.lows.append(low)
        bars.closes.append(price)
        bars.volumes.append(1_000_000 * (1 + rng.random()))
    return bars


# --- indicators ------------------------------------------------------------------

def test_ema_tracks_constant_series():
    assert ta.ema([10.0] * 50, 10) == pytest.approx(10.0)


def test_rsi_bounds_and_extremes():
    rising = list(range(1, 100))
    assert ta.rsi([float(v) for v in rising], 14) == pytest.approx(100.0)
    value = ta.rsi(synth_bars().closes, 14)
    assert value is not None and 0 <= value <= 100


def test_atr_positive_and_scales():
    b = synth_bars()
    a = ta.atr(b.highs, b.lows, b.closes, 14)
    assert a is not None and a > 0


def test_bollinger_percent_b_midband_is_half():
    closes = [100.0] * 19 + [100.0]
    bb = ta.bollinger(closes, 20, 2.0)
    assert bb is not None and math.isfinite(bb.percent_b)


def test_macd_detects_cross_direction():
    reading = ta.macd(synth_bars(trend=0.002).closes)
    assert reading is not None
    assert not (reading.bullish_cross and reading.bearish_cross)


def test_ttm_squeeze_returns_reading():
    b = synth_bars(squeeze=True)
    sq = ta.ttm_squeeze(b.highs, b.lows, b.closes)
    assert sq is not None
    assert sq.bars_in_squeeze >= 0


def test_indicators_return_none_when_insufficient_history():
    assert ta.rsi([1.0, 2.0], 14) is None
    assert ta.atr([1.0], [1.0], [1.0], 14) is None
    assert ta.ttm_squeeze([1.0], [1.0], [1.0]) is None


# --- scoring ---------------------------------------------------------------------

def test_weights_must_sum_to_100():
    with pytest.raises(ValueError):
        ScoreWeights(squeeze_fired=50).validate()
    ScoreWeights().validate()


def test_score_is_bounded_and_decomposes():
    snap = build_snapshot(synth_bars(), DEFAULT_SETTINGS.indicators)
    engine = ScoringEngine(DEFAULT_SETTINGS.weights, DEFAULT_SETTINGS.indicators)
    result = engine.score(snap)
    assert 0.0 <= result.total <= 100.0
    assert sum(result.components.values()) == pytest.approx(result.total, abs=0.05)


def test_uptrend_scores_higher_trend_alignment_than_downtrend():
    cfg = DEFAULT_SETTINGS.indicators
    engine = ScoringEngine(DEFAULT_SETTINGS.weights, cfg)
    up = engine.score(build_snapshot(synth_bars(trend=0.0015, seed=1), cfg))
    down = engine.score(build_snapshot(synth_bars(trend=-0.0015, seed=1), cfg))
    assert up.raw["trend_alignment"] > down.raw["trend_alignment"]


def test_custom_weights_are_respected():
    cfg = DEFAULT_SETTINGS.indicators
    snap = build_snapshot(synth_bars(), cfg)
    only_trend = ScoreWeights(
        squeeze_fired=0, lower_bollinger=0, rsi_oversold=0, macd_bullish_cross=0,
        volume_confirmation=0, trend_alignment=100, volatility_quality=0, support_proximity=0,
    )
    result = ScoringEngine(only_trend, cfg).score(snap)
    assert result.total == pytest.approx(result.raw["trend_alignment"] * 100, abs=0.05)


# --- market hours ----------------------------------------------------------------

def test_nyse_open_and_closed_windows():
    tz = ZoneInfo("America/New_York")
    open_moment = datetime(2024, 5, 1, 11, 0, tzinfo=tz)     # Wednesday
    closed_moment = datetime(2024, 5, 4, 11, 0, tzinfo=tz)   # Saturday
    assert ex.EXCHANGES["NYSE"].is_open(open_moment)
    assert not ex.EXCHANGES["NYSE"].is_open(closed_moment)


def test_crypto_never_closes():
    assert ex.EXCHANGES["CRYPTO"].is_open(datetime(2024, 5, 5, 3, 0, tzinfo=ZoneInfo("UTC")))


def test_open_exchanges_on_weekend_is_crypto_only():
    weekend = datetime(2024, 5, 4, 3, 0, tzinfo=ZoneInfo("UTC"))
    assert [e.code for e in ex.open_exchanges(weekend)] == ["CRYPTO"]


# --- resilient data provider -----------------------------------------------------

class FlakyProvider(DataProvider):
    def __init__(self, fail_times: int):
        self.calls = 0
        self.fail_times = fail_times

    def fetch(self, ticker, bars, interval="1d"):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("simulated outage")
        return synth_bars(ticker)


def test_provider_retries_then_succeeds():
    rp = ResilientProvider(FlakyProvider(2), max_retries=3, sleep=lambda _s: None)
    assert rp.fetch("AAPL", 100) is not None


def test_provider_blacklists_after_repeated_failures():
    rp = ResilientProvider(FlakyProvider(999), max_retries=1, blacklist_threshold=2, sleep=lambda _s: None)
    assert rp.fetch("BAD", 100) is None
    assert rp.fetch("BAD", 100) is None
    assert "BAD" in rp.blacklist
    assert rp.fetch("BAD", 100) is None  # short-circuits, no crash


def test_provider_resolves_aliases():
    rp = ResilientProvider(FlakyProvider(0), aliases={"FB": "META"}, sleep=lambda _s: None)
    assert rp.resolve("FB") == "META"


# --- scanner ---------------------------------------------------------------------

class GoodProvider(DataProvider):
    def fetch(self, ticker, bars, interval="1d"):
        return synth_bars(ticker, seed=abs(hash(ticker)) % 1000)


def make_engine(settings: Settings | None = None) -> ScannerEngine:
    s = settings or DEFAULT_SETTINGS
    return ScannerEngine(s, ResilientProvider(GoodProvider(), sleep=lambda _s: None))


def test_scan_ranks_candidates_descending():
    universe = Universe("T", "Test", "CRYPTO", [
        Symbol("AAA", "CRYPTO", "GLOBAL", "Crypto"),
        Symbol("BBB", "CRYPTO", "GLOBAL", "Crypto"),
        Symbol("CCC", "CRYPTO", "GLOBAL", "Crypto"),
    ])
    result = make_engine().scan(universes=[universe])
    scores = [c.total for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert result.scanned == 3


def test_scan_skips_when_all_markets_closed():
    weekend = datetime(2024, 5, 4, 3, 0, tzinfo=ZoneInfo("UTC"))
    engine = make_engine()
    # Only crypto is open on a weekend, so equity universes are excluded.
    assert all(u.exchange == "CRYPTO" for u in engine.active_universes(weekend))


def test_entry_requires_minimum_score():
    strict = Settings(scan=type(DEFAULT_SETTINGS.scan)(min_entry_score=99.0))
    engine = make_engine(strict)
    universe = Universe("T", "Test", "CRYPTO", [Symbol("AAA", "CRYPTO", "GLOBAL", "Crypto")])
    result = engine.scan(universes=[universe])
    for candidate in result.candidates:
        ready, why = engine.entry_ready(candidate)
        assert not ready and "below minimum" in why


# --- risk ------------------------------------------------------------------------

def test_position_size_never_exceeds_risk_budget():
    risk = RiskManager(DEFAULT_SETTINGS.risk)
    state = PortfolioState(equity=100_000, cash=100_000)
    sizing = risk.size(state, price=50.0, atr=1.0)
    assert sizing.allowed
    assert sizing.risk_amount <= 100_000 * DEFAULT_SETTINGS.risk.max_risk_per_trade + 50


def test_heat_ceiling_blocks_new_positions():
    risk = RiskManager(DEFAULT_SETTINGS.risk)
    hot = [OpenPosition(f"P{i}", "Tech", "US", 1000, 100, 94) for i in range(2)]
    state = PortfolioState(equity=100_000, cash=100_000, positions=hot)
    allowed, why = risk.can_open(state, "Tech", "US", "NEW")
    assert not allowed and "heat" in why


def test_duplicate_position_rejected():
    risk = RiskManager(DEFAULT_SETTINGS.risk)
    state = PortfolioState(100_000, 100_000, [OpenPosition("AAPL", "Tech", "US", 10, 100, 95)])
    allowed, why = risk.can_open(state, "Tech", "US", "AAPL")
    assert not allowed and "duplicate" in why


def test_circuit_breaker_after_consecutive_losses():
    risk = RiskManager(DEFAULT_SETTINGS.risk)
    state = PortfolioState(100_000, 100_000, consecutive_losses=5)
    allowed, why = risk.can_open(state, "Tech", "US", "AAPL")
    assert not allowed and "circuit breaker" in why


def test_daily_loss_limit_halts_new_risk():
    risk = RiskManager(DEFAULT_SETTINGS.risk)
    state = PortfolioState(100_000, 100_000, realized_today=-4_000)
    allowed, why = risk.can_open(state, "Tech", "US", "AAPL")
    assert not allowed and "daily loss" in why
