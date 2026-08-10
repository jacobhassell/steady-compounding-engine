"""Parameter search and walk-forward validation.

A backtest that is optimised and reported on the same data is a marketing document,
not evidence. Everything here exists to separate the two:

    * `grid_search`  — brute-force a parameter grid on one slice of history.
    * `walk_forward` — repeatedly optimise on a training window and *only* score the
      untouched window that follows it, then compare in-sample to out-of-sample.

The objective deliberately favours survivability: risk-adjusted return, penalised for
drawdown and for sample sizes too small to mean anything.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from project.backtests.engine import BacktestConfig, Backtester
from project.config.settings import DEFAULT_SETTINGS, Settings
from project.data.provider import Bars
from project.reports.performance import PerformanceReport

log = logging.getLogger(__name__)

MIN_TRADES_FOR_CONFIDENCE = 12


# --- settings plumbing --------------------------------------------------------------

def apply_overrides(settings: Settings, overrides: Dict[str, object]) -> Settings:
    """Return a copy of `settings` with dotted-path values replaced.

    Keys look like "scan.min_entry_score" or "risk.atr_trail_multiple". Every config
    object is frozen, so this rebuilds the tree instead of mutating it.
    """
    grouped: Dict[str, Dict[str, object]] = {}
    top: Dict[str, object] = {}
    for path, value in overrides.items():
        if "." in path:
            section, name = path.split(".", 1)
            grouped.setdefault(section, {})[name] = value
        else:
            top[path] = value

    for section, values in grouped.items():
        if not hasattr(settings, section):
            raise KeyError(f"Unknown settings section: {section}")
        current = getattr(settings, section)
        for name in values:
            if not hasattr(current, name):
                raise KeyError(f"Unknown setting: {section}.{name}")
        top[section] = replace(current, **values)

    out = replace(settings, **top)
    out.validate()
    return out


def expand_grid(grid: Dict[str, Sequence[object]]) -> List[Dict[str, object]]:
    """Cartesian product of the grid, in a stable order."""
    if not grid:
        return [{}]
    keys = list(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


# --- objective ----------------------------------------------------------------------

def objective(report: PerformanceReport) -> float:
    """Single number to rank parameter sets by. Higher is better, 0 means unusable.

    Sortino is the base (downside risk is the only risk that matters), scaled down by
    drawdown and by how thin the trade sample is. A strategy that made money in three
    trades has proven nothing and is scored accordingly.
    """
    if report.trades == 0 or report.ending_equity <= 0:
        return 0.0
    base = report.sortino if report.sortino not in (float("inf"), float("-inf")) else 5.0
    base = max(-5.0, min(5.0, base))
    dd_penalty = 1.0 / (1.0 + 4.0 * max(0.0, report.max_drawdown))
    confidence = min(1.0, report.trades / MIN_TRADES_FOR_CONFIDENCE)
    expectancy = max(-1.0, min(2.0, report.expectancy_r))
    return round((base + expectancy) * dd_penalty * confidence, 4)


# --- history slicing -----------------------------------------------------------------

def slice_history(history: Dict[str, Bars], start: int, end: int) -> Dict[str, Bars]:
    """Bars[start:end] for every symbol, preserving alignment across the book."""
    out: Dict[str, Bars] = {}
    for ticker, bars in history.items():
        out[ticker] = Bars(
            ticker=bars.ticker,
            dates=bars.dates[start:end],
            opens=bars.opens[start:end],
            highs=bars.highs[start:end],
            lows=bars.lows[start:end],
            closes=bars.closes[start:end],
            volumes=bars.volumes[start:end],
        )
    return out


# --- results --------------------------------------------------------------------------

@dataclass
class Trial:
    overrides: Dict[str, object]
    score: float
    report: PerformanceReport

    def label(self) -> str:
        if not self.overrides:
            return "baseline"
        return ", ".join(f"{k}={v}" for k, v in self.overrides.items())


@dataclass
class Fold:
    index: int
    train: Tuple[int, int]
    test: Tuple[int, int]
    chosen: Dict[str, object]
    in_sample: float
    out_of_sample: float
    test_report: PerformanceReport

    @property
    def degradation(self) -> float:
        """How much of the in-sample edge survived contact with unseen data."""
        if self.in_sample <= 0:
            return 0.0
        return round(1.0 - (self.out_of_sample / self.in_sample), 3)


@dataclass
class WalkForwardResult:
    folds: List[Fold] = field(default_factory=list)
    trials_per_fold: int = 0

    @property
    def avg_in_sample(self) -> float:
        return sum(f.in_sample for f in self.folds) / len(self.folds) if self.folds else 0.0

    @property
    def avg_out_of_sample(self) -> float:
        return sum(f.out_of_sample for f in self.folds) / len(self.folds) if self.folds else 0.0

    @property
    def efficiency(self) -> float:
        """Out-of-sample / in-sample. Above ~0.5 is respectable; near 0 is curve fitting."""
        if self.avg_in_sample <= 0:
            return 0.0
        return round(self.avg_out_of_sample / self.avg_in_sample, 3)

    @property
    def consistency(self) -> float:
        """Share of folds that stayed profitable out of sample."""
        if not self.folds:
            return 0.0
        good = sum(1 for f in self.folds if f.out_of_sample > 0)
        return round(good / len(self.folds), 3)

    def most_common_choice(self) -> Dict[str, object]:
        """The parameter set the optimiser picked most often across folds."""
        counts: Dict[str, int] = {}
        by_key: Dict[str, Dict[str, object]] = {}
        for fold in self.folds:
            key = repr(sorted(fold.chosen.items()))
            counts[key] = counts.get(key, 0) + 1
            by_key[key] = fold.chosen
        if not counts:
            return {}
        best = max(counts, key=lambda k: counts[k])
        return by_key[best]

    def verdict(self) -> str:
        if not self.folds:
            return "No folds ran — not enough history to validate anything."
        if self.avg_out_of_sample <= 0:
            return "REJECT: the edge does not survive out of sample. Do not trade this."
        if self.efficiency < 0.35 or self.consistency < 0.5:
            return "FRAGILE: results look curve-fitted. Widen the grid or simplify the rules."
        if self.efficiency >= 0.7 and self.consistency >= 0.75:
            return "ROBUST: out-of-sample performance tracks in-sample. Promote to paper."
        return "ACCEPTABLE: real but modest edge. Paper trade before risking capital."

    def summary(self) -> str:
        lines = [
            "Walk-forward validation",
            f"  folds {len(self.folds)} | {self.trials_per_fold} parameter sets per fold",
            f"  avg in-sample {self.avg_in_sample:.3f} | out-of-sample {self.avg_out_of_sample:.3f}",
            f"  efficiency {self.efficiency:.2f} | consistency {self.consistency:.0%}",
        ]
        for fold in self.folds:
            chosen = ", ".join(f"{k}={v}" for k, v in fold.chosen.items()) or "baseline"
            lines.append(
                f"  fold {fold.index}: train {fold.train[0]}-{fold.train[1]} "
                f"test {fold.test[0]}-{fold.test[1]} | IS {fold.in_sample:.2f} "
                f"OOS {fold.out_of_sample:.2f} | {chosen}"
            )
        lines.append(f"  {self.verdict()}")
        return "\n".join(lines)


# --- the optimiser ----------------------------------------------------------------------

class Optimizer:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        config: Optional[BacktestConfig] = None,
        sectors: Optional[Dict[str, str]] = None,
    ) -> None:
        self.settings = settings or DEFAULT_SETTINGS
        self.settings.validate()
        self.config = config or BacktestConfig()
        self.sectors = sectors or {}

    def _evaluate(self, history: Dict[str, Bars], overrides: Dict[str, object]) -> Optional[Trial]:
        try:
            tuned = apply_overrides(self.settings, overrides)
            result = Backtester(tuned, self.config).run(history, self.sectors)
        except Exception as exc:  # noqa: BLE001 — one bad combination never kills the sweep
            log.warning("Parameter set %s failed: %s", overrides, exc)
            return None
        return Trial(overrides=overrides, score=objective(result.report), report=result.report)

    def grid_search(self, history: Dict[str, Bars], grid: Dict[str, Sequence[object]]) -> List[Trial]:
        """Every combination, ranked best first. Ties break toward the earlier (simpler) set."""
        trials: List[Trial] = []
        for overrides in expand_grid(grid):
            trial = self._evaluate(history, overrides)
            if trial is not None:
                trials.append(trial)
        trials.sort(key=lambda t: t.score, reverse=True)
        return trials

    def walk_forward(
        self,
        history: Dict[str, Bars],
        grid: Dict[str, Sequence[object]],
        folds: int = 4,
        train_bars: int = 260,
        test_bars: int = 65,
    ) -> WalkForwardResult:
        """Anchored-step walk forward: optimise on `train_bars`, score the next `test_bars`."""
        length = min(len(b) for b in history.values()) if history else 0
        needed = train_bars + test_bars
        if length < needed:
            raise ValueError(
                f"Need at least {needed} bars for one fold, got {length}. "
                "Shorten the windows or fetch more history."
            )

        step = test_bars
        max_folds = 1 + (length - needed) // step
        folds = max(1, min(folds, max_folds))
        combos = expand_grid(grid)
        out = WalkForwardResult(trials_per_fold=len(combos))

        for i in range(folds):
            start = i * step
            train_end = start + train_bars
            test_end = train_end + test_bars
            train = slice_history(history, start, train_end)
            # The test window keeps the tail of training so indicators are warm.
            warm = max(0, train_end - self.config.warmup_bars)
            test = slice_history(history, warm, test_end)

            ranked = self.grid_search(train, grid)
            if not ranked:
                log.warning("Fold %d produced no usable trials — skipping.", i + 1)
                continue
            best = ranked[0]
            scored = self._evaluate(test, best.overrides)
            if scored is None:
                continue
            out.folds.append(Fold(
                index=i + 1,
                train=(start, train_end),
                test=(train_end, test_end),
                chosen=best.overrides,
                in_sample=best.score,
                out_of_sample=scored.score,
                test_report=scored.report,
            ))
        return out


DEFAULT_GRID: Dict[str, Sequence[object]] = {
    "scan.min_entry_score": (65.0, 70.0, 75.0),
    "risk.atr_stop_multiple": (1.5, 2.0, 2.5),
    "risk.atr_trail_multiple": (2.5, 3.0),
}


__all__ = [
    "DEFAULT_GRID", "Fold", "Optimizer", "Trial", "WalkForwardResult",
    "apply_overrides", "expand_grid", "objective", "slice_history",
]
