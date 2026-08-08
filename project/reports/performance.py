"""Portfolio performance analytics.

Pure functions over an equity curve and a list of closed trades. No plotting, no I/O —
the same numbers feed the CLI report, the backtest summary and the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Dict, List, Optional, Sequence

TRADING_DAYS = 252


@dataclass(frozen=True)
class TradeRecord:
    """A completed round trip, priced in money and in R."""

    ticker: str
    entry_day: int
    exit_day: int
    entry: float
    exit: float
    shares: float
    pnl: float
    r_multiple: float
    reason: str

    @property
    def held_days(self) -> int:
        return max(0, self.exit_day - self.entry_day)

    @property
    def is_win(self) -> bool:
        return self.pnl > 0


@dataclass
class PerformanceReport:
    starting_equity: float
    ending_equity: float
    total_return: float
    cagr: float
    max_drawdown: float
    max_drawdown_days: int
    sharpe: float
    sortino: float
    volatility: float
    trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    avg_win_r: float
    avg_loss_r: float
    largest_loss: float
    avg_hold_days: float
    exit_reasons: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, float | int | Dict[str, int]]:
        return dict(self.__dict__)

    def summary_lines(self) -> List[str]:
        return [
            f"Equity      {self.starting_equity:,.0f} -> {self.ending_equity:,.0f} ({self.total_return:+.2%})",
            f"CAGR        {self.cagr:+.2%}   Volatility {self.volatility:.2%}",
            f"Sharpe      {self.sharpe:.2f}   Sortino {self.sortino:.2f}",
            f"Max DD      {self.max_drawdown:.2%} over {self.max_drawdown_days} bars",
            f"Trades      {self.trades} ({self.wins}W / {self.losses}L, {self.win_rate:.1%} win rate)",
            f"Profit fac. {self.profit_factor:.2f}   Expectancy {self.expectancy_r:+.2f}R",
            f"Avg win     {self.avg_win_r:+.2f}R   Avg loss {self.avg_loss_r:+.2f}R",
            f"Avg hold    {self.avg_hold_days:.1f} bars   Worst trade {self.largest_loss:,.0f}",
        ]


# --- primitives --------------------------------------------------------------------

def daily_returns(equity_curve: Sequence[float]) -> List[float]:
    out: List[float] = []
    for prev, curr in zip(equity_curve, equity_curve[1:]):
        out.append((curr - prev) / prev if prev else 0.0)
    return out


def max_drawdown(equity_curve: Sequence[float]) -> tuple[float, int]:
    """Worst peak-to-trough decline and how many bars it lasted."""
    peak = float("-inf")
    peak_index = 0
    worst = 0.0
    worst_len = 0
    for i, value in enumerate(equity_curve):
        if value > peak:
            peak, peak_index = value, i
        elif peak > 0:
            dd = (peak - value) / peak
            if dd > worst:
                worst, worst_len = dd, i - peak_index
    return worst, worst_len


def sharpe_ratio(returns: Sequence[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free / TRADING_DAYS for r in returns]
    mean = sum(excess) / len(excess)
    var = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    sd = sqrt(var)
    return (mean / sd) * sqrt(TRADING_DAYS) if sd else 0.0


def sortino_ratio(returns: Sequence[float], risk_free: float = 0.0) -> float:
    """Upside volatility is not risk; only downside deviation is penalised."""
    if len(returns) < 2:
        return 0.0
    target = risk_free / TRADING_DAYS
    mean = sum(returns) / len(returns) - target
    downside = [min(0.0, r - target) ** 2 for r in returns]
    dd = sqrt(sum(downside) / len(returns))
    if dd == 0.0:
        # No losing bar in the sample: undefined downside risk, not zero performance.
        return float("inf") if mean > 0 else 0.0
    return (mean / dd) * sqrt(TRADING_DAYS)


def annualized_volatility(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return sqrt(var) * sqrt(TRADING_DAYS)


def cagr(equity_curve: Sequence[float], bars_per_year: int = TRADING_DAYS) -> float:
    if len(equity_curve) < 2 or equity_curve[0] <= 0:
        return 0.0
    years = (len(equity_curve) - 1) / bars_per_year
    if years <= 0:
        return 0.0
    growth = equity_curve[-1] / equity_curve[0]
    if growth <= 0:
        return -1.0
    return growth ** (1 / years) - 1


def profit_factor(trades: Sequence[TradeRecord]) -> float:
    gains = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def build_report(
    equity_curve: Sequence[float],
    trades: Sequence[TradeRecord],
    bars_per_year: int = TRADING_DAYS,
    risk_free: float = 0.0,
) -> PerformanceReport:
    curve = list(equity_curve) or [0.0]
    rets = daily_returns(curve)
    dd, dd_len = max_drawdown(curve)
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    reasons: Dict[str, int] = {}
    for t in trades:
        key = t.reason.split(" at ")[0].split(" of ")[0]
        reasons[key] = reasons.get(key, 0) + 1

    start, end = curve[0], curve[-1]
    return PerformanceReport(
        starting_equity=round(start, 2),
        ending_equity=round(end, 2),
        total_return=(end - start) / start if start else 0.0,
        cagr=cagr(curve, bars_per_year),
        max_drawdown=dd,
        max_drawdown_days=dd_len,
        sharpe=sharpe_ratio(rets, risk_free),
        sortino=sortino_ratio(rets, risk_free),
        volatility=annualized_volatility(rets),
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        profit_factor=profit_factor(trades),
        expectancy_r=sum(t.r_multiple for t in trades) / len(trades) if trades else 0.0,
        avg_win_r=sum(t.r_multiple for t in wins) / len(wins) if wins else 0.0,
        avg_loss_r=sum(t.r_multiple for t in losses) / len(losses) if losses else 0.0,
        largest_loss=min((t.pnl for t in trades), default=0.0),
        avg_hold_days=sum(t.held_days for t in trades) / len(trades) if trades else 0.0,
        exit_reasons=reasons,
    )


def format_report(report: PerformanceReport, title: str = "Performance") -> str:
    width = 64
    lines = [title.upper().center(width, "="), *report.summary_lines()]
    if report.exit_reasons:
        lines.append("-" * width)
        lines.append("Exits: " + ", ".join(f"{k} x{v}" for k, v in sorted(
            report.exit_reasons.items(), key=lambda kv: -kv[1])))
    lines.append("=" * width)
    return "\n".join(lines)


def verdict(report: PerformanceReport, min_trades: int = 20) -> str:
    """Blunt, capital-preservation-first read on whether a config deserves real money."""
    if report.trades < min_trades:
        return f"INCONCLUSIVE — only {report.trades} trades, not a statistically usable sample."
    if report.max_drawdown > 0.25:
        return f"REJECT — {report.max_drawdown:.1%} drawdown breaches survivable limits."
    if report.expectancy_r <= 0:
        return f"REJECT — negative expectancy ({report.expectancy_r:+.2f}R per trade)."
    if report.profit_factor < 1.3 or report.sharpe < 0.5:
        return "MARGINAL — positive but thin edge; do not scale size."
    return "ACCEPTABLE — edge is positive with survivable drawdown; forward-test on paper next."


__all__ = [
    "TradeRecord", "PerformanceReport", "build_report", "format_report", "verdict",
    "max_drawdown", "sharpe_ratio", "sortino_ratio", "cagr", "profit_factor",
    "daily_returns", "annualized_volatility",
]
