import { PORTFOLIO, POSITIONS } from "@/lib/scanner-data";

const money = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "profit" | "loss" | "caution";
}) {
  const toneClass =
    tone === "profit"
      ? "text-profit"
      : tone === "loss"
        ? "text-loss"
        : tone === "caution"
          ? "text-caution"
          : "text-foreground";
  return (
    <div className="panel px-4 py-3.5">
      <div className="label-xs">{label}</div>
      <div className={`num mt-1.5 text-xl font-semibold ${toneClass}`}>{value}</div>
      {sub ? <div className="num mt-0.5 text-[11px] text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

export function PortfolioStats() {
  const heat = PORTFOLIO.openRisk / PORTFOLIO.equity;
  const heatPct = (heat / PORTFOLIO.heatLimit) * 100;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Stat label="Portfolio Value" value={money(PORTFOLIO.equity)} sub={`CAGR ${PORTFOLIO.cagr}% · Sharpe ${PORTFOLIO.sharpe}`} />
      <Stat label="Cash" value={money(PORTFOLIO.cash)} sub={`Buying power ${money(PORTFOLIO.buyingPower)}`} />
      <Stat
        label="Today's P/L"
        value={`${PORTFOLIO.dayPnl >= 0 ? "+" : ""}${money(PORTFOLIO.dayPnl)}`}
        sub={`${PORTFOLIO.dayPnlPct >= 0 ? "+" : ""}${PORTFOLIO.dayPnlPct.toFixed(2)}% on the day`}
        tone={PORTFOLIO.dayPnl >= 0 ? "profit" : "loss"}
      />
      <Stat
        label="Open Positions"
        value={`${POSITIONS.length} / ${PORTFOLIO.maxPositions}`}
        sub={`Max drawdown ${PORTFOLIO.maxDrawdown}%`}
      />
      <div className="panel px-4 py-3.5">
        <div className="label-xs">Portfolio Heat</div>
        <div className="num mt-1.5 text-xl font-semibold text-caution">{(heat * 100).toFixed(2)}%</div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-caution"
            style={{ width: `${Math.min(100, heatPct)}%` }}
          />
        </div>
        <div className="num mt-1 text-[11px] text-muted-foreground">
          ceiling {(PORTFOLIO.heatLimit * 100).toFixed(0)}% · risk-first
        </div>
      </div>
    </div>
  );
}
