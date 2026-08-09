"""Entry point. Paper trading first; live is a configuration change, not a rewrite."""

from __future__ import annotations

import argparse
import logging
import time

from project.config.settings import DEFAULT_SETTINGS, Settings
from project.data.provider import ResilientProvider, build_provider
from project.risk.manager import PortfolioState, RiskManager
from project.scanner.engine import ScannerEngine
from project.utils.logging_setup import configure_logging

log = logging.getLogger("mastermind")


def build_engine(settings: Settings) -> ScannerEngine:
    provider = ResilientProvider(
        build_provider(settings.data.provider, settings.data.request_timeout_seconds),
        max_retries=settings.data.max_retries,
        backoff_seconds=settings.data.retry_backoff_seconds,
        blacklist_threshold=settings.data.blacklist_failure_threshold,
        aliases=settings.data.aliases,
    )
    return ScannerEngine(settings, provider)


def run_once(settings: Settings) -> None:
    engine = build_engine(settings)
    risk = RiskManager(settings.risk)
    state = PortfolioState(equity=settings.starting_cash, cash=settings.starting_cash)

    result = engine.scan()
    log.info(
        "Scan complete in %.1fs — %s scanned, %s skipped, %s ranked.",
        result.duration_seconds, result.scanned, result.skipped, len(result.candidates),
    )

    for candidate in result.candidates[:10]:
        ready, why = engine.entry_ready(candidate)
        if not ready:
            log.info("%s scored %.0f — skipped: %s", candidate.ticker, candidate.total, why)
            continue
        allowed, risk_why = risk.can_open(
            state, candidate.symbol.sector, candidate.symbol.country, candidate.ticker
        )
        if not allowed:
            log.info("%s scored %.0f — blocked by risk: %s", candidate.ticker, candidate.total, risk_why)
            continue
        sizing = risk.size(state, candidate.snapshot.price, candidate.snapshot.atr or 0.0)
        if not sizing.allowed:
            log.info("%s scored %.0f — no size: %s", candidate.ticker, candidate.total, sizing.reason)
            continue
        log.info(
            "ENTRY %s | score %.0f | %s shares @ %.2f | stop %.2f | %s | %s",
            candidate.ticker, candidate.total, sizing.shares, candidate.snapshot.price,
            sizing.stop, sizing.reason, ", ".join(candidate.score.top_reasons()),
        )


def run_forever(settings: Settings) -> None:
    engine = build_engine(settings)
    while True:
        try:
            run_once(settings)
        except KeyboardInterrupt:
            log.info("Shutdown requested. Exiting cleanly.")
            return
        except Exception as exc:  # noqa: BLE001 — the bot must never die on a transient fault
            log.exception("Scan cycle failed, continuing after backoff: %s", exc)
        sleep_for = engine.sleep_seconds()
        log.info("Sleeping %.0fs until the next scan window.", sleep_for)
        time.sleep(max(5.0, sleep_for))


def run_backtest(settings: Settings, tickers: list[str], bars: int) -> None:
    """Historical validation using the same scoring, risk and position code as live."""
    from project.backtests.engine import BacktestConfig, Backtester

    provider = build_engine(settings).provider
    history = {}
    for ticker in tickers:
        data = provider.fetch(ticker, bars)
        if data is not None and len(data) > 120:
            history[ticker] = data
        else:
            log.warning("Skipping %s — not enough history to test honestly.", ticker)
    if not history:
        log.error("No usable history. Nothing to backtest.")
        return

    result = Backtester(settings, BacktestConfig()).run(history)
    log.info("Backtested %d symbols over %d bars.", result.symbols_tested, result.bars_tested)
    print(result.summary())


def run_paper(settings: Settings, cycles: int) -> None:
    """Paper trade with the production scanner, risk stack and Mastermind ladder."""
    from project.paper.trader import PaperTrader

    trader = PaperTrader(build_engine(settings), settings)
    completed = 0
    while cycles <= 0 or completed < cycles:
        try:
            report = trader.run_cycle()
            print(report.summary())
        except KeyboardInterrupt:
            log.info("Shutdown requested. Paper state saved.")
            trader.save()
            return
        except Exception as exc:  # noqa: BLE001 — the loop must survive transient faults
            log.exception("Paper cycle failed, continuing after backoff: %s", exc)
        completed += 1
        if cycles <= 0 or completed < cycles:
            sleep_for = trader.engine.sleep_seconds()
            log.info("Sleeping %.0fs until the next paper cycle.", sleep_for)
            time.sleep(max(5.0, sleep_for))


def main() -> None:
    parser = argparse.ArgumentParser(description="Mastermind algorithmic trading platform")
    parser.add_argument("command", choices=["scan", "run", "backtest", "paper"],
                        help="scan = single cycle, run = continuous, "
                             "backtest = historical validation, paper = simulated trading")
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,JPM,XOM,VOLV-B.ST",
                        help="comma-separated symbols for backtest")
    parser.add_argument("--cycles", type=int, default=1,
                        help="paper trading cycles to run; 0 = forever")
    parser.add_argument("--bars", type=int, default=500, help="history length for backtest")
    parser.add_argument("--mode", default="paper", choices=["paper", "live", "backtest"])
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    configure_logging(args.log_level, logfile="reports/journal.log")
    settings = Settings(mode=args.mode) if args.mode != DEFAULT_SETTINGS.mode else DEFAULT_SETTINGS
    settings.validate()

    log.info("Mastermind starting in %s mode. Capital preservation first.", settings.mode)
    if args.command == "scan":
        run_once(settings)
    elif args.command == "paper":
        run_paper(settings, args.cycles)
    elif args.command == "backtest":
        run_backtest(settings, [t.strip() for t in args.tickers.split(",") if t.strip()], args.bars)
    else:
        run_forever(settings)


if __name__ == "__main__":
    main()
