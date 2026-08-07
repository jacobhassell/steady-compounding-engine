import { useState } from "react";
import {
  CANDIDATES,
  COMPONENT_LABELS,
  SCORE_WEIGHTS,
  type Candidate,
  type ComponentKey,
} from "@/lib/scanner-data";

const KEYS = Object.keys(SCORE_WEIGHTS) as ComponentKey[];

const statusStyles: Record<Candidate["status"], string> = {
  ready: "border-profit/40 bg-profit/10 text-profit",
  watch: "border-caution/40 bg-caution/10 text-caution",
  blocked: "border-loss/40 bg-loss/10 text-loss",
};

function ScoreBar({ score }: { score: number }) {
  const tone = score >= 70 ? "bg-profit" : score >= 55 ? "bg-caution" : "bg-muted-foreground/60";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${score}%` }} />
      </div>
      <span className="num w-10 text-right text-sm font-semibold">{score.toFixed(1)}</span>
    </div>
  );
}

function Breakdown({ candidate }: { candidate: Candidate }) {
  return (
    <div className="grid gap-2 border-t border-border bg-surface-raised/60 px-4 py-4 sm:grid-cols-2 lg:grid-cols-4">
      {KEYS.map((key) => {
        const earned = candidate.raw[key] * SCORE_WEIGHTS[key];
        return (
          <div key={key}>
            <div className="flex items-baseline justify-between">
              <span className="label-xs">{COMPONENT_LABELS[key]}</span>
              <span className="num text-[11px] text-muted-foreground">
                {earned.toFixed(1)} / {SCORE_WEIGHTS[key]}
              </span>
            </div>
            <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-info"
                style={{ width: `${candidate.raw[key] * 100}%` }}
              />
            </div>
          </div>
        );
      })}
      <p className="num text-[11px] text-muted-foreground sm:col-span-2 lg:col-span-4">
        ATR {candidate.atr.toFixed(2)} · RVOL {candidate.rvol.toFixed(2)}x · RSI {candidate.rsi} ·{" "}
        {candidate.note}
      </p>
    </div>
  );
}

export function CandidateTable() {
  const [expanded, setExpanded] = useState<string | null>(CANDIDATES[0]?.ticker ?? null);

  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Ranked Opportunities</h2>
          <p className="num text-[11px] text-muted-foreground">
            weighted 0–100 score · entry threshold 70 · sorted by conviction
          </p>
        </div>
        <span className="label-xs">{CANDIDATES.length} ranked</span>
      </header>

      <div className="grid grid-cols-[1fr_auto] gap-2 border-b border-border px-4 py-2 sm:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))_auto]">
        <span className="label-xs">Symbol</span>
        <span className="label-xs hidden sm:block">Venue</span>
        <span className="label-xs hidden text-right sm:block">Last</span>
        <span className="label-xs hidden text-right sm:block">RVOL</span>
        <span className="label-xs hidden sm:block">Gate</span>
        <span className="label-xs text-right">Score</span>
      </div>

      <ul>
        {CANDIDATES.map((c) => {
          const open = expanded === c.ticker;
          return (
            <li key={c.ticker} className="border-b border-border/70 last:border-b-0">
              <button
                type="button"
                onClick={() => setExpanded(open ? null : c.ticker)}
                aria-expanded={open}
                className="grid w-full grid-cols-[1fr_auto] items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-surface-raised sm:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))_auto]"
              >
                <span className="min-w-0">
                  <span className="num block text-sm font-semibold">{c.ticker}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">
                    {c.name} · {c.sector}
                  </span>
                </span>
                <span className="num hidden text-xs text-muted-foreground sm:block">{c.exchange}</span>
                <span className="num hidden text-right text-xs sm:block">
                  {c.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </span>
                <span className="num hidden text-right text-xs sm:block">{c.rvol.toFixed(2)}x</span>
                <span className="hidden sm:block">
                  <span
                    className={`num rounded-sm border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${statusStyles[c.status]}`}
                  >
                    {c.status}
                  </span>
                </span>
                <span className="justify-self-end">
                  <ScoreBar score={c.score} />
                </span>
              </button>
              {open ? <Breakdown candidate={c} /> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
