import { EXCHANGES, type ExchangeStatus } from "@/lib/scanner-data";

const dotClass: Record<ExchangeStatus["state"], string> = {
  open: "bg-profit live-dot",
  soon: "bg-caution",
  closed: "bg-muted-foreground/50",
};

const textClass: Record<ExchangeStatus["state"], string> = {
  open: "text-foreground",
  soon: "text-caution",
  closed: "text-muted-foreground",
};

export function ExchangeStrip() {
  return (
    <div className="panel flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
      <span className="label-xs">Sessions</span>
      {EXCHANGES.map((ex) => (
        <div key={ex.code} className="flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${dotClass[ex.state]}`} aria-hidden />
          <span className={`num text-xs font-medium ${textClass[ex.state]}`}>{ex.code}</span>
          <span className="num text-[10px] text-muted-foreground">{ex.detail}</span>
        </div>
      ))}
    </div>
  );
}
