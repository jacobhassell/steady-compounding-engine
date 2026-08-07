"""Weighted 0-100 scoring engine.

Each component is an independent, testable callable returning a 0..1 quality fraction.
The weighted sum is the symbol score. Weights are configuration, never code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from project.config.settings import IndicatorConfig, ScoreWeights
from project.data.provider import Bars
from project.indicators import technical as ta


@dataclass
class IndicatorSnapshot:
    """Everything the scoring components and position manager need, computed once."""

    ticker: str
    price: float
    atr: Optional[float]
    rsi: Optional[float]
    macd: Optional[ta.MacdReading]
    bollinger: Optional[ta.BollingerReading]
    squeeze: Optional[ta.SqueezeReading]
    ema_fast: Optional[float]
    ema_slow: Optional[float]
    rel_volume: Optional[float]
    momentum: Optional[float]
    volatility: Optional[float]
    support: Optional[float]
    resistance: Optional[float]
    avg_dollar_volume: float

    @property
    def atr_pct(self) -> Optional[float]:
        if self.atr is None or not self.price:
            return None
        return self.atr / self.price * 100.0


def build_snapshot(bars: Bars, cfg: IndicatorConfig) -> IndicatorSnapshot:
    c, h, l, v = bars.closes, bars.highs, bars.lows, bars.volumes
    price = bars.last_price
    lookback = min(len(v), cfg.rel_volume_lookback) or 1
    adv = sum(cl * vol for cl, vol in zip(c[-lookback:], v[-lookback:])) / lookback if lookback else 0.0
    return IndicatorSnapshot(
        ticker=bars.ticker,
        price=price,
        atr=ta.atr(h, l, c, cfg.atr_period),
        rsi=ta.rsi(c, cfg.rsi_period),
        macd=ta.macd(c, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal),
        bollinger=ta.bollinger(c, cfg.bb_period, cfg.bb_stddev),
        squeeze=ta.ttm_squeeze(h, l, c, cfg.keltner_period, cfg.bb_stddev, cfg.keltner_atr_mult),
        ema_fast=ta.ema(c, cfg.ema_fast),
        ema_slow=ta.ema(c, cfg.ema_slow),
        rel_volume=ta.relative_volume(v, cfg.rel_volume_lookback),
        momentum=ta.momentum(c, cfg.momentum_period),
        volatility=ta.annualized_volatility(c, cfg.bb_period),
        support=ta.nearest_support(l, price, cfg.support_lookback),
        resistance=ta.nearest_resistance(h, price, cfg.support_lookback),
        avg_dollar_volume=adv,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# --- Scoring components: snapshot + config -> 0..1 ---------------------------------

def score_squeeze_fired(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    sq = s.squeeze
    if sq is None or not sq.bullish:
        return 0.0
    if sq.fired:
        # A longer compression before the release is a higher-quality setup.
        return _clamp(0.7 + 0.3 * min(sq.bars_in_squeeze, 20) / 20.0)
    if sq.in_squeeze:
        return _clamp(0.25 + 0.25 * min(sq.bars_in_squeeze, 20) / 20.0)
    return 0.0


def score_lower_bollinger(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.bollinger is None:
        return 0.0
    pct_b = s.bollinger.percent_b
    if pct_b <= 0.0:
        return 0.8            # below the band: stretched, but knife-catch risk
    if pct_b >= 0.5:
        return 0.0
    return _clamp(1.0 - pct_b / 0.5)


def score_rsi_oversold(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.rsi is None:
        return 0.0
    if s.rsi >= cfg.rsi_overbought:
        return 0.0
    if s.rsi <= 20:
        return 0.85           # deeply oversold can mean broken, not cheap
    if s.rsi <= cfg.rsi_oversold:
        return 1.0 - (s.rsi - 20) / max(cfg.rsi_oversold - 20, 1e-9) * 0.15
    return _clamp((cfg.rsi_overbought - s.rsi) / (cfg.rsi_overbought - cfg.rsi_oversold) * 0.4)


def score_macd_cross(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.macd is None:
        return 0.0
    if s.macd.bullish_cross:
        return 1.0
    if s.macd.histogram > 0 and s.macd.macd > s.macd.signal:
        return 0.6
    if s.macd.bearish_cross:
        return 0.0
    return 0.2 if s.macd.histogram > 0 else 0.0


def score_volume(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.rel_volume is None:
        return 0.0
    if s.rel_volume >= 2.0:
        return 1.0
    if s.rel_volume <= 0.7:
        return 0.0
    return _clamp((s.rel_volume - 0.7) / 1.3)


def score_trend_alignment(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.ema_fast is None or s.ema_slow is None:
        return 0.0
    if s.price > s.ema_fast > s.ema_slow:
        return 1.0
    if s.price > s.ema_slow:
        return 0.6
    if s.ema_fast > s.ema_slow:
        return 0.35
    return 0.0


def score_volatility_quality(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    """Tradeable volatility: enough range to pay for risk, not so much it is unstable."""
    atr_pct = s.atr_pct
    if atr_pct is None:
        return 0.0
    if 1.5 <= atr_pct <= 4.0:
        return 1.0
    if atr_pct < 1.5:
        return _clamp(atr_pct / 1.5 * 0.7)
    if atr_pct <= 8.0:
        return _clamp(1.0 - (atr_pct - 4.0) / 4.0)
    return 0.0


def score_support_proximity(s: IndicatorSnapshot, cfg: IndicatorConfig) -> float:
    if s.support is None or not s.price or s.atr is None or s.atr <= 0:
        return 0.0
    distance_in_atr = (s.price - s.support) / s.atr
    if distance_in_atr < 0:
        return 0.0            # already broken support
    return _clamp(1.0 - distance_in_atr / 3.0)


ScoreComponent = Callable[[IndicatorSnapshot, IndicatorConfig], float]

COMPONENTS: Dict[str, ScoreComponent] = {
    "squeeze_fired": score_squeeze_fired,
    "lower_bollinger": score_lower_bollinger,
    "rsi_oversold": score_rsi_oversold,
    "macd_bullish_cross": score_macd_cross,
    "volume_confirmation": score_volume,
    "trend_alignment": score_trend_alignment,
    "volatility_quality": score_volatility_quality,
    "support_proximity": score_support_proximity,
}


@dataclass
class ScoreBreakdown:
    ticker: str
    total: float
    components: Dict[str, float] = field(default_factory=dict)   # weighted points earned
    raw: Dict[str, float] = field(default_factory=dict)          # 0..1 quality fractions
    reasons: List[str] = field(default_factory=list)

    def top_reasons(self, n: int = 3) -> List[str]:
        return self.reasons[:n]


class ScoringEngine:
    """Composable scorer. Add a component + weight; nothing else changes."""

    def __init__(
        self,
        weights: ScoreWeights,
        indicators: IndicatorConfig,
        components: Optional[Dict[str, ScoreComponent]] = None,
    ) -> None:
        weights.validate()
        self.weights = weights.as_dict()
        self.indicators = indicators
        self.components = components or dict(COMPONENTS)

    def score(self, snapshot: IndicatorSnapshot) -> ScoreBreakdown:
        weighted: Dict[str, float] = {}
        raw: Dict[str, float] = {}
        for key, weight in self.weights.items():
            component = self.components.get(key)
            if component is None:
                continue
            quality = _clamp(component(snapshot, self.indicators))
            raw[key] = quality
            weighted[key] = quality * weight

        total = round(sum(weighted.values()), 2)
        ordered = sorted(weighted.items(), key=lambda kv: kv[1], reverse=True)
        reasons = [
            f"{key.replace('_', ' ')} +{points:.1f}" for key, points in ordered if points >= 1.0
        ]
        return ScoreBreakdown(snapshot.ticker, total, weighted, raw, reasons)
