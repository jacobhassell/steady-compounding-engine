import { JOURNAL, type JournalEntry } from "@/lib/scanner-data";

const levelTone: Record<JournalEntry["level"], string> = {
  info: "text-muted-foreground",
  trade: "text-profit",
  risk: "text-caution",
  warn: "text-loss",
};

const levelTag: Record<JournalEntry["level"], string> = {
  info: "SCAN",
  trade: "TRADE",
  risk: "RISK",
  warn: "WARN",
};

export function JournalFeed() {
  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Trading Journal</h2>
          <p className="num text-[11px] text-muted-foreground">every action explains why it happened</p>
        </div>
        <span className="flex items-center gap-1.5">
          <span className="live-dot h-1.5 w-1.5 rounded-full bg-profit" aria-hidden />
          <span className="label-xs">live</span>
        </span>
      </header>
      <ol className="max-h-[22rem] overflow-y-auto">
        {JOURNAL.map((entry, i) => (
          <li key={i} className="flex gap-3 border-b border-border/50 px-4 py-2 last:border-b-0">
            <span className="num shrink-0 text-[11px] text-muted-foreground">{entry.time}</span>
            <span className={`num shrink-0 text-[10px] font-semibold ${levelTone[entry.level]}`}>
              {levelTag[entry.level]}
            </span>
            <span className="num text-[11px] leading-relaxed text-foreground/90">{entry.message}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
