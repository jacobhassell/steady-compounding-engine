import { PORTFOLIO } from "@/lib/scanner-data";

const METRICS: { label: string; value: string }[] = [
  { label: "CAGR", value: `${PORTFOLIO.cagr}%` },
  { label: "Sharpe", value: PORTFOLIO.sharpe.toFixed(2) },
  { label: "Sortino", value: PORTFOLIO.sortino.toFixed(2) },
  { label: "Calmar", value: PORTFOLIO.calmar.toFixed(2) },
  { label: "Max DD", value: `${PORTFOLIO.maxDrawdown}%` },
  { label: "Profit Factor", value: PORTFOLIO.profitFactor.toFixed(2) },
  { label: "Win Rate", value: `${PORTFOLIO.winRate}%` },
  { label: "Expectancy", value: `${PORTFOLIO.expectancy.toFixed(2)}R` },
  { label: "Avg Hold", value: `${PORTFOLIO.avgHoldDays}d` },
  { label: "Trades", value: `${PORTFOLIO.totalTrades}` },
];

export function MetricsPanel() {
  return (
    <section className="panel px-4 py-4">
      <h2 className="text-sm font-semibold">Performance</h2>
      <p className="num text-[11px] text-muted-foreground">risk-adjusted, since inception</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-5 lg:grid-cols-2">
        {METRICS.map((m) => (
          <div key={m.label} className="flex items-baseline justify-between border-b border-border/50 pb-1">
            <dt className="label-xs">{m.label}</dt>
            <dd className="num text-sm font-medium">{m.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
