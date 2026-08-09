import { createFileRoute } from "@tanstack/react-router";
import { BacktestPanel } from "@/components/dashboard/BacktestPanel";
import { CandidateTable } from "@/components/dashboard/CandidateTable";
import { ExchangeStrip } from "@/components/dashboard/ExchangeStrip";
import { JournalFeed } from "@/components/dashboard/JournalFeed";
import { MetricsPanel } from "@/components/dashboard/MetricsPanel";
import { PortfolioStats } from "@/components/dashboard/PortfolioStats";
import { PositionsPanel } from "@/components/dashboard/PositionsPanel";

const TITLE = "Mastermind — Global Algorithmic Trading Terminal";
const DESCRIPTION =
  "Session-aware multi-market scanner, weighted 0-100 opportunity scoring, ATR risk sizing and Mastermind position management on a Backtrader engine.";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  return (
    <main className="mx-auto min-h-screen w-full max-w-[1600px] px-4 py-6 lg:px-8">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-xs">Mastermind Trading Platform</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Global Scanner Terminal</h1>
          <p className="num mt-1 text-[11px] text-muted-foreground">
            Backtrader engine · paper mode · capital preservation first
          </p>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="label-xs">Last Scan</div>
            <div className="num text-sm">15:43:09 UTC</div>
          </div>
          <div className="text-right">
            <div className="label-xs">Next Scan</div>
            <div className="num text-sm text-caution">04:51</div>
          </div>
          <div className="min-w-40">
            <div className="flex items-center justify-between">
              <span className="label-xs">Scan Progress</span>
              <span className="num text-[11px] text-muted-foreground">514 / 517</span>
            </div>
            <div className="scanline mt-1.5 h-1.5 w-full rounded-full bg-muted">
              <div className="h-full w-[99%] rounded-full bg-primary" />
            </div>
          </div>
        </div>
      </header>

      <div className="space-y-3">
        <ExchangeStrip />
        <PortfolioStats />

        <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-3">
            <CandidateTable />
            <BacktestPanel />
            <JournalFeed />

          </div>
          <div className="space-y-3">
            <PositionsPanel />
            <MetricsPanel />
          </div>
        </div>
      </div>

      <footer className="num mt-6 border-t border-border pt-4 text-[11px] text-muted-foreground">
        Decision hierarchy: protect capital → control risk → pursue profit → maximize returns.
        Engine source lives in <span className="text-foreground">project/</span> (Python + Backtrader).
      </footer>
    </main>
  );
}
