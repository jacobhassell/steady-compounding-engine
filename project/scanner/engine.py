"""The scanning engine: which markets are open, what data to pull, what ranks highest.

The scanner never places orders. It produces a ranked, filtered candidate list that the
risk layer and Backtrader strategy consume. Separation keeps both independently testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from project.config.settings import Settings
from project.data.provider import Bars, ResilientProvider
from project.scanner.scoring import IndicatorSnapshot, ScoreBreakdown, ScoringEngine, build_snapshot
from project.universe import exchanges as ex
from project.universe.registry import Symbol, Universe, universes_for_exchanges

log = logging.getLogger(__name__)


@dataclass
class Candidate:
    symbol: Symbol
    snapshot: IndicatorSnapshot
    score: ScoreBreakdown

    @property
    def ticker(self) -> str:
        return self.symbol.ticker

    @property
    def total(self) -> float:
        return self.score.total

    def suggested_stop(self, atr_multiple: float) -> Optional[float]:
        if self.snapshot.atr is None:
            return None
        return round(self.snapshot.price - atr_multiple * self.snapshot.atr, 4)


@dataclass
class ScanResult:
    started_at: datetime
    finished_at: datetime
    open_exchanges: List[str]
    opening_soon: List[str]
    scanned: int
    skipped: int
    candidates: List[Candidate] = field(default_factory=list)
    rejected: Dict[str, str] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def qualified(self) -> List[Candidate]:
        return self.candidates


class ScannerEngine:
    def __init__(self, settings: Settings, provider: ResilientProvider) -> None:
        settings.validate()
        self.settings = settings
        self.provider = provider
        self.scoring = ScoringEngine(settings.weights, settings.indicators)

    # -- market session awareness --------------------------------------------------
    def active_universes(self, at: Optional[datetime] = None) -> List[Universe]:
        open_codes = [e.code for e in ex.open_exchanges(at)]
        if not open_codes:
            return []
        return self._apply_crypto_gate(universes_for_exchanges(open_codes))

    # -- crypto risk gate ----------------------------------------------------------
    def crypto_allowed(self, universes: Sequence[Universe]) -> tuple[bool, int]:
        """Crypto only trades in thin hours.

        Counts securities tradeable right now outside crypto. Above the configured
        ceiling the session is 'busy' — risk budget belongs to regulated venues, so
        crypto is dropped from the scan entirely.
        """
        active = sum(len(u.symbols) for u in universes if u.asset_class != "crypto")
        return active <= self.settings.scan.crypto_max_active_securities, active

    def _apply_crypto_gate(self, universes: List[Universe]) -> List[Universe]:
        allowed, active = self.crypto_allowed(universes)
        if allowed:
            return universes
        dropped = [u for u in universes if u.asset_class == "crypto"]
        if dropped:
            log.info(
                "Crypto suppressed: %d active non-crypto securities exceeds ceiling of %d.",
                active, self.settings.scan.crypto_max_active_securities,
            )
        return [u for u in universes if u.asset_class != "crypto"]


    def sleep_seconds(self, at: Optional[datetime] = None) -> float:
        if ex.open_exchanges(at):
            return float(self.settings.scan.scan_interval_seconds)
        wait = ex.seconds_until_next_open(at)
        return min(wait, float(self.settings.scan.idle_sleep_seconds))

    # -- liquidity / sanity gates --------------------------------------------------
    def _liquidity_reason(self, snap: IndicatorSnapshot) -> Optional[str]:
        cfg = self.settings.scan
        if snap.price < cfg.min_price:
            return f"price {snap.price:.2f} below minimum {cfg.min_price:.2f}"
        if snap.avg_dollar_volume < cfg.min_avg_dollar_volume:
            return f"avg dollar volume {snap.avg_dollar_volume:,.0f} below minimum"
        if snap.atr is None or snap.atr <= 0:
            return "ATR unavailable — cannot size risk"
        return None

    # -- the scan ------------------------------------------------------------------
    def scan(self, at: Optional[datetime] = None, universes: Optional[Sequence[Universe]] = None) -> ScanResult:
        started = datetime.now(timezone.utc)
        open_ex = [e.code for e in ex.open_exchanges(at)]
        soon = [e.code for e in ex.opening_soon(30, at)]
        targets = list(universes) if universes is not None else self.active_universes(at)

        if not targets:
            log.info("All supported exchanges closed. Sleeping instead of burning API requests.")
            return ScanResult(started, datetime.now(timezone.utc), open_ex, soon, 0, 0)

        log.info("Open exchanges: %s | scanning %s", ", ".join(open_ex) or "none",
                 ", ".join(u.label for u in targets))

        candidates: List[Candidate] = []
        rejected: Dict[str, str] = {}
        scanned = skipped = 0

        for universe in targets:
            for symbol in universe.symbols:
                bars = self.provider.fetch(symbol.ticker, self.settings.scan.history_bars)
                if bars is None or not bars.is_usable(self.settings.indicators.ema_slow // 4):
                    skipped += 1
                    rejected[symbol.ticker] = "insufficient or unavailable data"
                    continue

                scanned += 1
                try:
                    snapshot = build_snapshot(bars, self.settings.indicators)
                except Exception as exc:  # noqa: BLE001 — one bad symbol never kills a scan
                    skipped += 1
                    rejected[symbol.ticker] = f"indicator error: {exc}"
                    log.warning("Indicator failure on %s: %s", symbol.ticker, exc)
                    continue

                reason = self._liquidity_reason(snapshot)
                if reason:
                    rejected[symbol.ticker] = reason
                    continue

                breakdown = self.scoring.score(snapshot)
                candidates.append(Candidate(symbol, snapshot, breakdown))

        candidates.sort(key=lambda c: c.total, reverse=True)
        finished = datetime.now(timezone.utc)

        top = candidates[: self.settings.scan.max_candidates_reported]
        if top:
            log.info("Top candidates: %s", ", ".join(f"{c.ticker} {c.total:.0f}" for c in top[:5]))
        else:
            log.info("No candidates passed liquidity gates this scan.")

        return ScanResult(started, finished, open_ex, soon, scanned, skipped, top, rejected)

    def entry_ready(self, candidate: Candidate) -> tuple[bool, str]:
        """Score + setup quality gate. Portfolio/risk gates live in project/risk."""
        cfg = self.settings.scan
        if candidate.total < cfg.min_entry_score:
            return False, f"score {candidate.total:.0f} below minimum {cfg.min_entry_score:.0f}"
        squeeze = candidate.snapshot.squeeze
        if squeeze is None or not squeeze.bullish:
            return False, "squeeze conditions not bullish"
        if candidate.snapshot.macd and candidate.snapshot.macd.bearish_cross:
            return False, "conflicting signal: MACD bearish cross"
        if candidate.suggested_stop(self.settings.risk.atr_stop_multiple) is None:
            return False, "no ATR stop available"
        return True, "all entry requirements satisfied"
