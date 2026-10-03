"use client";

import { Banknote, BookOpen, FileText, Inbox, Network, Truck, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { Chip } from "@/components/ui/chip";
import type { EvidenceLink, Flag } from "@/lib/api";
import { date, inr } from "@/lib/format";
import { KIND_TONE } from "@/lib/labels";

const SOURCE_ICON: Record<string, typeof FileText> = {
  invoice: FileText,
  ledger: BookOpen,
  bank: Banknote,
  ims: Inbox,
  ewb: Truck,
  toll: Truck,
  graph: Network,
};

const Ctx = createContext<(flag: Flag) => void>(() => {});

/** Open the evidence drawer for any flag: `const show = useEvidence(); show(flag)`. */
export function useEvidence() {
  return useContext(Ctx);
}

function fieldText(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return /amount|total|tax|itc|taxable|paid|value/i.test(key) ? inr(value) : String(value);
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value)) {
    return value.length > 10 ? `${date(value)} ${value.slice(11, 16)}` : date(value);
  }
  if (Array.isArray(value)) return value.join("; ");
  return String(value);
}

function Link({ link }: { link: EvidenceLink }) {
  const Icon = SOURCE_ICON[link.source] ?? FileText;
  const fields = Object.entries(link.fields).filter(([, v]) => v !== null && v !== "");
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border-[1.5px] border-line bg-peach text-ink">
        <Icon size={14} />
      </span>
      <div className="min-w-0">
        <div className="text-[13px] font-semibold text-ink">{link.label}</div>
        <dl className="mt-0.5 grid grid-cols-[auto_1fr] gap-x-3 text-[12px]">
          {fields.slice(0, 6).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replaceAll("_", " ")}</dt>
              <dd className="truncate font-mono text-ink">{fieldText(k, v)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </li>
  );
}

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [flag, setFlag] = useState<Flag | null>(null);
  const close = useCallback(() => setFlag(null), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  return (
    <Ctx.Provider value={setFlag}>
      {children}
      <AnimatePresence>
        {flag && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/30"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={close}
            />
            <motion.aside
              role="dialog"
              aria-label="Evidence"
              className="card fixed inset-y-4 right-4 z-50 flex w-[440px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden"
              initial={{ x: 480 }}
              animate={{ x: 0 }}
              exit={{ x: 480 }}
              transition={{ type: "spring", stiffness: 300, damping: 32 }}
            >
              <header className="flex items-start justify-between gap-3 border-b-[1.5px] border-line p-5">
                <div>
                  <Chip tone={KIND_TONE[flag.kind] ?? "neutral"}>{flag.label}</Chip>
                  <h3 className="mt-2 font-heading text-lg font-bold leading-tight text-ink">
                    {flag.title}
                  </h3>
                  <div className="mt-1 text-[13px] text-muted">
                    <span className="font-mono">{flag.ref}</span> · {flag.counterparty}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={close}
                  className="grid h-8 w-8 place-items-center rounded-full text-muted hover:bg-peach hover:text-ink"
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </header>
              <div className="flex-1 space-y-5 overflow-y-auto p-5">
                {(flag.recorded || flag.expected) && (
                  <div className="overflow-hidden rounded-xl border-[1.5px] border-line font-mono text-[13px]">
                    {flag.recorded && (
                      <div className="flex justify-between gap-3 bg-bad/10 px-3 py-2 text-bad">
                        <span className="font-sans text-[11px] font-bold uppercase tracking-wider">
                          Recorded
                        </span>
                        <span className="text-right">{flag.recorded}</span>
                      </div>
                    )}
                    {flag.expected && (
                      <div className="flex justify-between gap-3 bg-ok/10 px-3 py-2 text-ok">
                        <span className="font-sans text-[11px] font-bold uppercase tracking-wider">
                          Expected
                        </span>
                        <span className="text-right">{flag.expected}</span>
                      </div>
                    )}
                  </div>
                )}
                <p className="text-[14px] leading-relaxed text-ink">{flag.evidence.summary}</p>
                {flag.evidence.notes.length > 0 && (
                  <ul className="space-y-1.5 text-[13px] text-muted">
                    {flag.evidence.notes.map((n) => (
                      <li key={n} className="flex gap-2">
                        <span className="text-orange">●</span>
                        {n}
                      </li>
                    ))}
                  </ul>
                )}
                {flag.evidence.chain.length > 0 && (
                  <div>
                    <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                      The records behind it
                    </div>
                    <ul className="space-y-3">
                      {flag.evidence.chain.map((l, i) => (
                        <Link key={`${l.source}-${l.id}-${i}`} link={l} />
                      ))}
                    </ul>
                  </div>
                )}
                {flag.impact > 0 && (
                  <div className="text-[13px] text-muted">
                    At stake: <span className="font-mono text-ink">{inr(flag.impact)}</span>
                  </div>
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </Ctx.Provider>
  );
}
