import { BACKTEST, BACKTEST_TRADES } from "@/lib/scanner-data";

function EquityCurve() {
  const pts = BACKTEST.curve;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const w = 100;
  const h = 34;
  const path = pts
    .map((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - ((v - min) / (max - min || 1)) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="h-24 w-full"
      role="img"
      aria-label="Backtest equity curve rising from 100k to 242k"
    >
      <path d={`${path} L${w},${h} L0,${h} Z`} className="fill-primary/10" />
      <path d={path} className="stroke-primary" strokeWidth={0.8} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const STATS: { label: string; value: string; tone?: string }[] = [
  { label: "CAGR", value: `${BACKTEST.cagr}%`, tone: "text-profit" },
  { label: "Sharpe", value: BACKTEST.sharpe.toFixed(2) },
  { label: "Sortino", value: BACKTEST.sortino.toFixed(2) },
  { label: "Max DD", value: `${BACKTEST.maxDrawdown}%`, tone: "text-loss" },
  { label: "DD Days", value: `${BACKTEST.maxDdDays}` },
  { label: "Profit Factor", value: BACKTEST.profitFactor.toFixed(2) },
  { label: "Win Rate", value: `${BACKTEST.winRate}%` },
  { label: "Expectancy", value: `${BACKTEST.expectancy.toFixed(2)}R` },
];

export function BacktestPanel() {
  return (
    <section className="panel overflow-hidden">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Backtest</h2>
          <p className="num text-[11px] text-muted-foreground">{BACKTEST.label}</p>
        </div>
        <div className="flex items-center gap-6 text-right">
          <div>
            <div className="label-xs">Start</div>
            <div className="num text-sm">${(BACKTEST.startEquity / 1000).toFixed(0)}k</div>
          </div>
          <div>
            <div className="label-xs">End</div>
            <div className="num text-sm text-profit">${(BACKTEST.endEquity / 1000).toFixed(0)}k</div>
          </div>
          <div>
            <div className="label-xs">Exposure</div>
            <div className="num text-sm">{BACKTEST.exposurePct}%</div>
          </div>
        </div>
      </header>

      <div className="px-4 pt-3">
        <EquityCurve />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 px-4 py-3 sm:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="flex items-baseline justify-between border-b border-border/50 pb-1">
            <dt className="label-xs">{s.label}</dt>
            <dd className={`num text-sm font-medium ${s.tone ?? ""}`}>{s.value}</dd>
          </div>
        ))}
      </dl>

      <div className="overflow-x-auto border-t border-border">
        <table className="w-full text-left">
          <thead>
            <tr className="label-xs border-b border-border">
              <th className="px-4 py-2 font-medium">Ticker</th>
              <th className="px-2 py-2 text-right font-medium">Entry</th>
              <th className="px-2 py-2 text-right font-medium">Exit</th>
              <th className="px-2 py-2 text-right font-medium">P&amp;L</th>
              <th className="px-2 py-2 text-right font-medium">R</th>
              <th className="px-2 py-2 text-right font-medium">Held</th>
              <th className="px-4 py-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {BACKTEST_TRADES.map((t) => (
              <tr key={t.ticker} className="num border-b border-border/50 text-[11px] last:border-b-0">
                <td className="px-4 py-2 font-medium text-foreground">{t.ticker}</td>
                <td className="px-2 py-2 text-right">{t.entry.toFixed(2)}</td>
                <td className="px-2 py-2 text-right">{t.exit.toFixed(2)}</td>
                <td className={`px-2 py-2 text-right ${t.pnl > 0 ? "text-profit" : t.pnl < 0 ? "text-loss" : "text-muted-foreground"}`}>
                  {t.pnl >= 0 ? "+" : "−"}${Math.abs(t.pnl).toLocaleString()}
                </td>
                <td className={`px-2 py-2 text-right ${t.r > 0 ? "text-profit" : t.r < 0 ? "text-loss" : "text-muted-foreground"}`}>
                  {t.r >= 0 ? "+" : "−"}
                  {Math.abs(t.r).toFixed(2)}R
                </td>
                <td className="px-2 py-2 text-right text-muted-foreground">{t.heldDays}d</td>
                <td className="px-4 py-2 text-muted-foreground">{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="num border-t border-border px-4 py-3 text-[11px] text-muted-foreground">
        Verdict: <span className="text-foreground">{BACKTEST.verdict}</span>
      </p>
    </section>
  );
}
