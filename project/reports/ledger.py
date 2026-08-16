"""Trade ledger — durable, auditable history of every order, fill and closed trade.

Three artifacts, all append-only so nothing is ever rewritten or lost:

  reports/fills.csv    one row per fill (entry, partial, exit) with costs
  reports/trades.csv   one row per closed round trip with R-multiple and reason
  reports/events.jsonl one JSON line per closed position with its full event trail

CSV so you can open it in Excel or pandas; JSONL so the per-bar decision trail
(stop moves, score decay, partials) survives for forensic review.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

FILL_FIELDS = [
    "at", "cycle", "order_id", "ticker", "side", "shares", "price",
    "notional", "commission", "slippage", "cash_after", "reason",
]

TRADE_FIELDS = [
    "opened_at", "closed_at", "cycle_opened", "cycle_closed", "ticker", "sector", "country",
    "shares", "entry", "initial_stop", "final_stop", "risk_at_open",
    "realized_pnl", "r_multiple", "stage", "exit_reason", "events",
]


@dataclass
class TradeLedger:
    directory: str = "reports"
    fills_name: str = "fills.csv"
    trades_name: str = "trades.csv"
    events_name: str = "events.jsonl"

    @property
    def fills_path(self) -> str:
        return os.path.join(self.directory, self.fills_name)

    @property
    def trades_path(self) -> str:
        return os.path.join(self.directory, self.trades_name)

    @property
    def events_path(self) -> str:
        return os.path.join(self.directory, self.events_name)

    # -- writing ------------------------------------------------------------------
    def _append(self, path: str, fields: List[str], row: Dict[str, Any]) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
            new = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, "a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                if new:
                    writer.writeheader()
                writer.writerow({k: row.get(k, "") for k in fields})
        except OSError as exc:  # bookkeeping must never kill the trading loop
            log.warning("Could not append to %s: %s", path, exc)

    def record_fill(self, fill, cash_after: float, cycle: int = 0) -> None:
        self._append(self.fills_path, FILL_FIELDS, {
            "at": fill.at.isoformat(),
            "cycle": cycle,
            "order_id": fill.order_id,
            "ticker": fill.ticker,
            "side": fill.side.value,
            "shares": round(fill.shares, 6),
            "price": round(fill.price, 4),
            "notional": round(fill.notional, 2),
            "commission": round(fill.commission, 4),
            "slippage": round(fill.slippage, 4),
            "cash_after": round(cash_after, 2),
            "reason": fill.reason,
        })

    def record_trade(self, position, cycle_closed: int = 0,
                     closed_at: Optional[datetime] = None) -> None:
        when = closed_at or datetime.now(timezone.utc)
        risk = position.risk_at_open
        events = [
            {"day": e.day, "kind": e.kind, "detail": e.detail,
             "price": e.price, "shares": e.shares}
            for e in position.events
        ]
        self._append(self.trades_path, TRADE_FIELDS, {
            "opened_at": "",
            "closed_at": when.isoformat(),
            "cycle_opened": position.opened_day,
            "cycle_closed": cycle_closed,
            "ticker": position.ticker,
            "sector": position.sector,
            "country": position.country,
            "shares": round(position.shares, 6),
            "entry": round(position.entry, 4),
            "initial_stop": round(position.initial_stop, 4),
            "final_stop": round(position.stop, 4),
            "risk_at_open": round(risk, 2),
            "realized_pnl": round(position.realized_pnl, 2),
            "r_multiple": round(position.realized_pnl / risk, 3) if risk else 0.0,
            "stage": position.stage.value,
            "exit_reason": position.exit_reason or "",
            "events": "; ".join(f"d{e['day']} {e['kind']}: {e['detail']}" for e in events),
        })
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self.events_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "closed_at": when.isoformat(),
                    "ticker": position.ticker,
                    "entry": position.entry,
                    "initial_stop": position.initial_stop,
                    "shares": position.shares,
                    "realized_pnl": round(position.realized_pnl, 2),
                    "r_multiple": round(position.realized_pnl / risk, 3) if risk else 0.0,
                    "exit_reason": position.exit_reason or "",
                    "events": events,
                }) + "\n")
        except OSError as exc:
            log.warning("Could not append to %s: %s", self.events_path, exc)

    # -- reading ------------------------------------------------------------------
    def _read(self, path: str) -> List[Dict[str, str]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                return list(csv.DictReader(fh))
        except OSError as exc:
            log.warning("Could not read %s: %s", path, exc)
            return []

    def fills(self) -> List[Dict[str, str]]:
        return self._read(self.fills_path)

    def trades(self) -> List[Dict[str, str]]:
        return self._read(self.trades_path)

    def events(self) -> List[dict]:
        if not os.path.exists(self.events_path):
            return []
        rows: List[dict] = []
        try:
            with open(self.events_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read %s: %s", self.events_path, exc)
        return rows

    # -- presentation --------------------------------------------------------------
    def report(self, limit: int = 50, ticker: Optional[str] = None,
               verbose: bool = False) -> str:
        trades = self.trades()
        fills = self.fills()
        if ticker:
            up = ticker.upper()
            trades = [t for t in trades if t["ticker"].upper() == up]
            fills = [f for f in fills if f["ticker"].upper() == up]
        if not trades and not fills:
            return ("No trade history yet. The ledger fills up as the paper/live loop "
                    f"runs — look for {self.trades_path} once the first trade closes.")

        lines: List[str] = []
        lines.append(f"FILLS ({len(fills)} total, showing last {min(limit, len(fills))})")
        lines.append(f"  {'time':<20}{'ticker':<12}{'side':<6}{'shares':>10}{'price':>10}"
                     f"{'comm':>8}  reason")
        for f in fills[-limit:]:
            lines.append(
                f"  {f['at'][:19]:<20}{f['ticker']:<12}{f['side'].upper():<6}"
                f"{float(f['shares']):>10.4g}{float(f['price']):>10.2f}"
                f"{float(f['commission']):>8.2f}  {f['reason']}"
            )

        wins = [t for t in trades if float(t["realized_pnl"]) > 0]
        total = sum(float(t["realized_pnl"]) for t in trades)
        r_total = sum(float(t["r_multiple"]) for t in trades)
        lines.append("")
        lines.append(f"CLOSED TRADES ({len(trades)} total, showing last {min(limit, len(trades))})")
        lines.append(f"  {'closed':<20}{'ticker':<12}{'entry':>9}{'shares':>9}"
                     f"{'pnl':>11}{'R':>7}  exit reason")
        for t in trades[-limit:]:
            lines.append(
                f"  {t['closed_at'][:19]:<20}{t['ticker']:<12}{float(t['entry']):>9.2f}"
                f"{float(t['shares']):>9.4g}{float(t['realized_pnl']):>11,.2f}"
                f"{float(t['r_multiple']):>7.2f}  {t['exit_reason']}"
            )
            if verbose and t.get("events"):
                for step in t["events"].split("; "):
                    lines.append(f"      · {step}")
        if trades:
            lines.append("")
            lines.append(
                f"  net P&L ${total:,.2f} | total {r_total:+.2f}R | "
                f"win rate {len(wins) / len(trades):.0%} ({len(wins)}/{len(trades)})"
            )
        lines.append("")
        lines.append(f"  fills: {self.fills_path} | trades: {self.trades_path} | "
                     f"per-bar trail: {self.events_path}")
        return "\n".join(lines)


__all__ = ["TradeLedger", "FILL_FIELDS", "TRADE_FIELDS"]
