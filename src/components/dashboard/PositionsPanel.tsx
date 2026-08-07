import { POSITIONS, type Position } from "@/lib/scanner-data";

const stageLabel: Record<Position["stage"], string> = {
  initial: "Initial stop",
  breakeven: "Breakeven · 25% out",
  runner: "Runner · 50% out",
};

const stageTone: Record<Position["stage"], string> = {
  initial: "text-muted-foreground",
  breakeven: "text-info",
  runner: "text-profit",
};

export function PositionsPanel() {
  return (
    <section className="panel overflow-hidden">
      <header className="border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Open Positions</h2>
        <p className="num text-[11px] text-muted-foreground">
          Mastermind management · ATR stops · 1R/2R partials · score decay
        </p>
      </header>
      <ul>
        {POSITIONS.map((p) => {
          const pnlPct = (p.last / p.entry - 1) * 100;
          return (
            <li key={p.ticker} className="border-b border-border/70 px-4 py-3 last:border-b-0">
              <div className="flex items-baseline justify-between gap-3">
                <div>
                  <span className="num text-sm font-semibold">{p.ticker}</span>
                  <span className="num ml-2 text-[11px] text-muted-foreground">{p.exchange}</span>
                </div>
                <span className={`num text-sm font-semibold ${pnlPct >= 0 ? "text-profit" : "text-loss"}`}>
                  {pnlPct >= 0 ? "+" : ""}
                  {pnlPct.toFixed(2)}%
                </span>
              </div>
              <div className="num mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
                <span>{p.shares} @ {p.entry.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
                <span>stop {p.stop.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
                <span className={p.rMultiple >= 0 ? "text-profit" : "text-loss"}>
                  {p.rMultiple >= 0 ? "+" : ""}
                  {p.rMultiple.toFixed(2)}R
                </span>
                <span>score {p.score}</span>
                <span className={stageTone[p.stage]}>{stageLabel[p.stage]}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
