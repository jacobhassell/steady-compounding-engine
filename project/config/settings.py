"""Central configuration. Nothing in strategy code should hardcode a value that lives here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ScoreWeights:
    """Weighted scoring engine. Must sum to 100."""

    squeeze_fired: float = 35.0
    lower_bollinger: float = 20.0
    rsi_oversold: float = 10.0
    macd_bullish_cross: float = 10.0
    volume_confirmation: float = 10.0
    trend_alignment: float = 5.0
    volatility_quality: float = 5.0
    support_proximity: float = 5.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "squeeze_fired": self.squeeze_fired,
            "lower_bollinger": self.lower_bollinger,
            "rsi_oversold": self.rsi_oversold,
            "macd_bullish_cross": self.macd_bullish_cross,
            "volume_confirmation": self.volume_confirmation,
            "trend_alignment": self.trend_alignment,
            "volatility_quality": self.volatility_quality,
            "support_proximity": self.support_proximity,
        }

    def validate(self) -> None:
        total = sum(self.as_dict().values())
        if abs(total - 100.0) > 1e-6:
            raise ValueError(f"Score weights must sum to 100, got {total}")


@dataclass(frozen=True)
class IndicatorConfig:
    bb_period: int = 20
    bb_stddev: float = 2.0
    keltner_period: int = 20
    keltner_atr_mult: float = 1.5
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    ema_fast: int = 50
    ema_slow: int = 200
    rel_volume_lookback: int = 20
    momentum_period: int = 10
    support_lookback: int = 60


@dataclass(frozen=True)
class RiskConfig:
    """Risk always wins over profit. These are hard ceilings, not suggestions."""

    max_risk_per_trade: float = 0.01           # 1% of equity
    max_portfolio_heat: float = 0.06           # 6% aggregate open risk
    max_concurrent_positions: int = 10
    max_sector_exposure: float = 0.30
    max_country_exposure: float = 0.60
    max_daily_loss: float = 0.03
    max_weekly_loss: float = 0.06
    consecutive_loss_circuit_breaker: int = 5
    atr_stop_multiple: float = 2.0
    atr_trail_multiple: float = 3.0
    partial_one_r: float = 0.25                # sell 25% at +1R, stop -> breakeven
    partial_two_r: float = 0.25                # sell 25% at +2R
    max_holding_days: int = 90


@dataclass(frozen=True)
class ScanConfig:
    min_entry_score: float = 70.0
    exit_score_threshold: float = 40.0
    score_decay_tighten: float = 55.0
    max_candidates_reported: int = 25
    scan_interval_seconds: int = 300
    idle_sleep_seconds: int = 900
    min_price: float = 2.0
    min_avg_dollar_volume: float = 1_000_000.0
    history_bars: int = 260
    # Crypto is only permitted in genuinely thin hours. If more than this many
    # non-crypto securities are tradeable right now, crypto is excluded from the scan.
    crypto_max_active_securities: int = 25



@dataclass(frozen=True)
class DataConfig:
    provider: str = "yahoo"
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    request_timeout_seconds: float = 20.0
    blacklist_failure_threshold: int = 3
    cache_dir: str = ".cache/marketdata"
    aliases: Dict[str, str] = field(default_factory=lambda: {"FB": "META", "TWTR": "X"})


@dataclass(frozen=True)
class Settings:
    starting_cash: float = 100_000.0
    base_currency: str = "USD"
    mode: str = "paper"                        # paper | live | backtest
    universes: List[str] = field(default_factory=lambda: ["SP500", "NASDAQ100", "TSX60", "ASX200", "NZX50", "CRYPTO"])
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    data: DataConfig = field(default_factory=DataConfig)
    log_level: str = "INFO"

    def validate(self) -> None:
        self.weights.validate()
        if self.mode not in {"paper", "live", "backtest"}:
            raise ValueError(f"Unknown mode: {self.mode}")


DEFAULT_SETTINGS = Settings()
