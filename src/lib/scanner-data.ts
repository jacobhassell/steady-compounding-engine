/**
 * Dashboard view model. Mirrors the Python engine's output shapes
 * (project/scanner/engine.py ScanResult + project/risk/manager.py PortfolioState)
 * so wiring the live feed later is a data-source swap, not a rewrite.
 */

export const SCORE_WEIGHTS = {
  squeeze_fired: 35,
  lower_bollinger: 20,
  rsi_oversold: 10,
  macd_bullish_cross: 10,
  volume_confirmation: 10,
  trend_alignment: 5,
  volatility_quality: 5,
  support_proximity: 5,
} as const;

export type ComponentKey = keyof typeof SCORE_WEIGHTS;

export const COMPONENT_LABELS: Record<ComponentKey, string> = {
  squeeze_fired: "TTM Squeeze",
  lower_bollinger: "Lower BB",
  rsi_oversold: "RSI",
  macd_bullish_cross: "MACD",
  volume_confirmation: "Volume",
  trend_alignment: "Trend",
  volatility_quality: "Volatility",
  support_proximity: "Support",
};

export type Candidate = {
  ticker: string;
  name: string;
  exchange: string;
  country: string;
  sector: string;
  price: number;
  atr: number;
  rvol: number;
  rsi: number;
  score: number;
  raw: Record<ComponentKey, number>;
  status: "ready" | "watch" | "blocked";
  note: string;
};

const mk = (
  ticker: string,
  name: string,
  exchange: string,
  country: string,
  sector: string,
  price: number,
  atr: number,
  rvol: number,
  rsi: number,
  raw: Record<ComponentKey, number>,
  status: Candidate["status"],
  note: string,
): Candidate => ({
  ticker,
  name,
  exchange,
  country,
  sector,
  price,
  atr,
  rvol,
  rsi,
  raw,
  status,
  note,
  score:
    Math.round(
      (Object.keys(SCORE_WEIGHTS) as ComponentKey[]).reduce(
        (sum, key) => sum + raw[key] * SCORE_WEIGHTS[key],
        0,
      ) * 10,
    ) / 10,
});

export const CANDIDATES: Candidate[] = [
  mk("NVDA", "NVIDIA", "NASDAQ", "US", "Technology", 178.42, 6.12, 2.31, 41,
    { squeeze_fired: 0.98, lower_bollinger: 0.72, rsi_oversold: 0.86, macd_bullish_cross: 1, volume_confirmation: 1, trend_alignment: 1, volatility_quality: 0.94, support_proximity: 0.81 },
    "ready", "squeeze released after 14 bars of compression"),
  mk("SHOP", "Shopify", "TSX", "CA", "Technology", 96.18, 3.44, 1.86, 38,
    { squeeze_fired: 0.91, lower_bollinger: 0.88, rsi_oversold: 0.95, macd_bullish_cross: 1, volume_confirmation: 0.84, trend_alignment: 0.6, volatility_quality: 1, support_proximity: 0.9 },
    "ready", "reclaim of 60-day support on rising volume"),
  mk("BTC-USD", "Bitcoin", "CRYPTO", "GLOBAL", "Crypto", 91_204.0, 2_840.0, 1.42, 44,
    { squeeze_fired: 0.86, lower_bollinger: 0.61, rsi_oversold: 0.72, macd_bullish_cross: 0.6, volume_confirmation: 0.79, trend_alignment: 1, volatility_quality: 0.82, support_proximity: 0.66 },
    "ready", "24/7 session — trend intact above EMA200"),
  mk("CSL", "CSL Limited", "ASX", "AU", "Healthcare", 241.9, 5.02, 1.28, 36,
    { squeeze_fired: 0.74, lower_bollinger: 0.93, rsi_oversold: 1, macd_bullish_cross: 0.6, volume_confirmation: 0.66, trend_alignment: 0.6, volatility_quality: 0.88, support_proximity: 0.95 },
    "watch", "score below entry threshold — monitoring for squeeze fire"),
  mk("AMD", "AMD", "NASDAQ", "US", "Technology", 164.05, 5.88, 1.74, 47,
    { squeeze_fired: 0.7, lower_bollinger: 0.44, rsi_oversold: 0.53, macd_bullish_cross: 1, volume_confirmation: 0.91, trend_alignment: 1, volatility_quality: 0.9, support_proximity: 0.48 },
    "blocked", "sector exposure limit reached for Technology"),
  mk("ENB", "Enbridge", "TSX", "CA", "Energy", 44.77, 0.71, 1.11, 42,
    { squeeze_fired: 0.62, lower_bollinger: 0.68, rsi_oversold: 0.8, macd_bullish_cross: 0.6, volume_confirmation: 0.55, trend_alignment: 0.6, volatility_quality: 0.6, support_proximity: 0.72 },
    "watch", "volatility quality thin — ATR 1.6% of price"),
  mk("FPH", "Fisher & Paykel", "NZX", "NZ", "Healthcare", 33.4, 0.82, 1.35, 39,
    { squeeze_fired: 0.58, lower_bollinger: 0.77, rsi_oversold: 0.88, macd_bullish_cross: 0.2, volume_confirmation: 0.62, trend_alignment: 0.35, volatility_quality: 0.85, support_proximity: 0.6 },
    "watch", "no MACD confirmation yet"),
  mk("SOL-USD", "Solana", "CRYPTO", "GLOBAL", "Crypto", 214.6, 12.9, 2.05, 33,
    { squeeze_fired: 0.55, lower_bollinger: 0.96, rsi_oversold: 1, macd_bullish_cross: 0.2, volume_confirmation: 1, trend_alignment: 0.35, volatility_quality: 0.42, support_proximity: 0.55 },
    "blocked", "volatility above tradeable band — 7.4% ATR"),
];

export type Position = {
  ticker: string;
  exchange: string;
  shares: number;
  entry: number;
  last: number;
  stop: number;
  initialStop: number;
  rMultiple: number;
  score: number;
  stage: "initial" | "breakeven" | "runner";
  openRisk: number;
};

export const POSITIONS: Position[] = [
  { ticker: "MSFT", exchange: "NASDAQ", shares: 84, entry: 402.1, last: 431.55, stop: 418.4, initialStop: 386.2, rMultiple: 1.85, score: 78, stage: "breakeven", openRisk: 0 },
  { ticker: "CAT", exchange: "NYSE", shares: 46, entry: 344.2, last: 388.9, stop: 366.1, initialStop: 328.0, rMultiple: 2.76, score: 81, stage: "runner", openRisk: 0 },
  { ticker: "BHP", exchange: "ASX", shares: 610, entry: 41.9, last: 43.22, stop: 39.6, initialStop: 39.6, rMultiple: 0.57, score: 69, stage: "initial", openRisk: 2208 },
  { ticker: "ETH-USD", exchange: "CRYPTO", shares: 5.4, entry: 3_120.0, last: 3_004.5, stop: 2_902.0, initialStop: 2_902.0, rMultiple: -0.53, score: 52, stage: "initial", openRisk: 553 },
  { ticker: "RY", exchange: "TSX", shares: 118, entry: 148.3, last: 152.05, stop: 144.9, initialStop: 144.9, rMultiple: 1.1, score: 74, stage: "initial", openRisk: 844 },
];

export const PORTFOLIO = {
  equity: 128_412.66,
  cash: 41_905.12,
  buyingPower: 83_810.24,
  dayPnl: 1_284.4,
  dayPnlPct: 1.01,
  openRisk: POSITIONS.reduce((s, p) => s + p.openRisk, 0),
  heatLimit: 0.06,
  maxPositions: 10,
  cagr: 21.4,
  sharpe: 1.84,
  sortino: 2.41,
  calmar: 1.92,
  maxDrawdown: -11.2,
  profitFactor: 2.16,
  winRate: 48.3,
  expectancy: 0.34,
  avgHoldDays: 19,
  totalTrades: 412,
};

export type ExchangeStatus = {
  code: string;
  label: string;
  state: "open" | "soon" | "closed";
  detail: string;
};

export const EXCHANGES: ExchangeStatus[] = [
  { code: "NYSE", label: "New York", state: "open", detail: "closes 16:00 ET" },
  { code: "NASDAQ", label: "Nasdaq", state: "open", detail: "closes 16:00 ET" },
  { code: "AMEX", label: "NYSE American", state: "open", detail: "closes 16:00 ET" },
  { code: "TSX", label: "Toronto", state: "open", detail: "closes 16:00 ET" },
  { code: "STO", label: "Stockholm", state: "closed", detail: "opens in 14h 18m" },
  { code: "OSL", label: "Oslo", state: "closed", detail: "opens in 14h 18m" },
  { code: "CPH", label: "Copenhagen", state: "closed", detail: "opens in 14h 18m" },
  { code: "HEL", label: "Helsinki", state: "closed", detail: "opens in 14h 18m" },
  { code: "FRA", label: "Frankfurt", state: "closed", detail: "opens in 14h 18m" },
  { code: "LSE", label: "London", state: "closed", detail: "opens in 13h 42m" },
  { code: "TSE", label: "Tokyo", state: "soon", detail: "opens in 26m" },
  { code: "HKEX", label: "Hong Kong", state: "closed", detail: "opens in 1h 56m" },
  { code: "ASX", label: "Sydney", state: "soon", detail: "opens in 24m" },
  { code: "NZX", label: "New Zealand", state: "soon", detail: "opens in 26m" },
  { code: "FOREX", label: "FX 24/5", state: "open", detail: "continuous" },
  { code: "GLOBEX", label: "Futures", state: "open", detail: "23/5 session" },
  { code: "CRYPTO", label: "Crypto", state: "closed", detail: "suppressed — 466 active" },
];


export type JournalEntry = { time: string; level: "info" | "trade" | "risk" | "warn"; message: string };

export const JOURNAL: JournalEntry[] = [
  { time: "15:42:07", level: "info", message: "NYSE, NASDAQ, AMEX, TSX and CRYPTO open. ASX/NZX open in ~25m." },
  { time: "15:42:09", level: "info", message: "Scanning SP500, NASDAQ100, TSX60, CRYPTO — 517 symbols queued." },
  { time: "15:42:41", level: "warn", message: "ZZZQ.TO failed 3 retries (provider timeout). Blacklisted, scan continues." },
  { time: "15:43:02", level: "info", message: "Downloaded 514 symbols, skipped 3. Indicators refreshed." },
  { time: "15:43:03", level: "info", message: "Top candidates: NVDA 94.1, SHOP 90.6, BTC-USD 84.2." },
  { time: "15:43:04", level: "risk", message: "AMD 82.7 blocked — sector exposure limit reached for Technology." },
  { time: "15:43:05", level: "trade", message: "ENTRY NVDA — 71 shares @ 178.42, stop 166.18 (2.0x ATR), risking $869 (0.68% of equity)." },
  { time: "15:43:06", level: "trade", message: "MSFT reached +1R — sold 25%, stop moved to breakeven 418.40. Downside eliminated." },
  { time: "15:43:07", level: "trade", message: "CAT trailing stop raised to 366.10 (3.0x ATR). Trend and volume still healthy — letting it run." },
  { time: "15:43:08", level: "risk", message: "ETH-USD score decayed 71 → 52. Tightening stop, preparing exit." },
  { time: "15:43:09", level: "info", message: "Portfolio heat 2.8% of 6.0% ceiling. 5 of 10 positions open. Next scan in 5m." },
];
