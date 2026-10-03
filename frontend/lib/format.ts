// The only place money, dates and durations get formatted. Never hand-format in components.

const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const numFmt = new Intl.NumberFormat("en-IN");

const MINUS = "−";

/** ₹2,12,400 (Indian grouping, whole rupees). */
export function inr(value: number): string {
  const sign = value < 0 ? MINUS : "";
  return `${sign}₹${inrFmt.format(Math.abs(Math.round(value)))}`;
}

/** 4.2 (lakh, one decimal) for chart axes and labels. */
export function lakhNumber(value: number, digits = 1): number {
  return Number((value / 1e5).toFixed(digits));
}

/** ₹4.2 L */
export function lakh(value: number, digits = 1): string {
  const sign = value < 0 ? MINUS : "";
  return `${sign}₹${Math.abs(value / 1e5).toFixed(digits)} L`;
}

/** 1,104 */
export function count(value: number): string {
  return numFmt.format(value);
}

/** 88.6% */
export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** 3h 02m */
export function duration(minutes: number): string {
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 12 Sep 2026 (accepts YYYY-MM-DD or a full ISO timestamp). */
export function date(iso: string, withYear = true): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const base = `${String(d).padStart(2, "0")} ${MONTHS[m - 1]}`;
  return withYear ? `${base} ${y}` : base;
}

/** Sep 2026 from a period string like 2026-09. */
export function period(p: string): string {
  const [y, m] = p.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

/** 3d 04h (countdown chip). */
export function countdown(ms: number): string {
  if (ms <= 0) return "0d 00h";
  const hours = Math.floor(ms / 3_600_000);
  const d = Math.floor(hours / 24);
  const h = hours % 24;
  return `${d}d ${String(h).padStart(2, "0")}h`;
}

/** 3812 4471 0093 (e-way bill numbers read in groups of four). */
export function ewb(no: string): string {
  return no.replace(/(\d{4})(?=\d)/g, "$1 ");
}
