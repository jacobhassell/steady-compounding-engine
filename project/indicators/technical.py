"""Pure, dependency-light indicator math shared by the scanner and Backtrader strategies.

Backtrader owns execution and accounting; these functions exist so the scanner can
evaluate a symbol without spinning up a Cerebro instance per candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence


def sma(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema_series(values: Sequence[float], period: int) -> List[float]:
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(float(v) * k + out[-1] * (1 - k))
    return out


def ema(values: Sequence[float], period: int) -> Optional[float]:
    series = ema_series(values, period)
    return series[-1] if series else None


def stddev(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 1:
        return None
    window = values[-period:]
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / period
    return var ** 0.5


def true_ranges(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(closes)):
        out.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> Optional[float]:
    tr = true_ranges(highs, lows, closes)
    if len(tr) < period:
        return None
    value = sum(tr[:period]) / period
    for t in tr[period:]:
        value = (value * (period - 1) + t) / period
    return value


def rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass(frozen=True)
class MacdReading:
    macd: float
    signal: float
    histogram: float
    bullish_cross: bool
    bearish_cross: bool


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal_period: int = 9) -> Optional[MacdReading]:
    if len(closes) < slow + signal_period:
        return None
    fast_s, slow_s = ema_series(closes, fast), ema_series(closes, slow)
    line = [f - s for f, s in zip(fast_s, slow_s)]
    sig = ema_series(line, signal_period)
    hist = [m - s for m, s in zip(line, sig)]
    return MacdReading(
        macd=line[-1],
        signal=sig[-1],
        histogram=hist[-1],
        bullish_cross=len(hist) > 1 and hist[-2] <= 0 < hist[-1],
        bearish_cross=len(hist) > 1 and hist[-2] >= 0 > hist[-1],
    )


@dataclass(frozen=True)
class BollingerReading:
    upper: float
    middle: float
    lower: float
    width: float
    percent_b: float


def bollinger(closes: Sequence[float], period: int = 20, num_std: float = 2.0) -> Optional[BollingerReading]:
    mid = sma(closes, period)
    sd = stddev(closes, period)
    if mid is None or sd is None:
        return None
    upper, lower = mid + num_std * sd, mid - num_std * sd
    span = max(upper - lower, 1e-9)
    return BollingerReading(upper, mid, lower, span / mid if mid else 0.0, (closes[-1] - lower) / span)


@dataclass(frozen=True)
class SqueezeReading:
    in_squeeze: bool
    fired: bool           # squeeze released this bar
    bars_in_squeeze: int
    momentum: float
    bullish: bool


def ttm_squeeze(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
    bb_std: float = 2.0,
    kc_mult: float = 1.5,
) -> Optional[SqueezeReading]:
    """TTM Squeeze: Bollinger Bands inside Keltner Channels = compression."""
    if len(closes) < period + 5:
        return None

    def squeezed_at(offset: int) -> Optional[bool]:
        end = len(closes) - offset
        if end < period + 1:
            return None
        c, h, l = closes[:end], highs[:end], lows[:end]
        bb = bollinger(c, period, bb_std)
        mid = ema(c, period)
        a = atr(h, l, c, period)
        if bb is None or mid is None or a is None:
            return None
        return bb.upper < mid + kc_mult * a and bb.lower > mid - kc_mult * a

    now, prev = squeezed_at(0), squeezed_at(1)
    if now is None or prev is None:
        return None

    bars = 0
    for offset in range(1, min(60, len(closes) - period - 1)):
        state = squeezed_at(offset)
        if not state:
            break
        bars += 1

    mid = sma(closes, period) or closes[-1]
    momentum = (closes[-1] - mid) / mid * 100 if mid else 0.0
    return SqueezeReading(
        in_squeeze=now,
        fired=(prev and not now),
        bars_in_squeeze=bars,
        momentum=momentum,
        bullish=momentum > 0,
    )


def relative_volume(volumes: Sequence[float], lookback: int = 20) -> Optional[float]:
    if len(volumes) < lookback + 1:
        return None
    baseline = sum(volumes[-lookback - 1:-1]) / lookback
    return volumes[-1] / baseline if baseline > 0 else None


def momentum(closes: Sequence[float], period: int = 10) -> Optional[float]:
    if len(closes) <= period or closes[-period - 1] == 0:
        return None
    return (closes[-1] / closes[-period - 1] - 1.0) * 100.0


def annualized_volatility(closes: Sequence[float], period: int = 20) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    rets = [(closes[i] / closes[i - 1] - 1.0) for i in range(len(closes) - period, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return (var ** 0.5) * (252 ** 0.5) * 100.0


def nearest_support(lows: Sequence[float], price: float, lookback: int = 60) -> Optional[float]:
    window = lows[-lookback:]
    below = [l for l in window if l <= price]
    return max(below) if below else (min(window) if window else None)


def nearest_resistance(highs: Sequence[float], price: float, lookback: int = 60) -> Optional[float]:
    window = highs[-lookback:]
    above = [h for h in window if h >= price]
    return min(above) if above else (max(window) if window else None)
