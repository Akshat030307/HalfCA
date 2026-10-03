"use client";

import { motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { useEvidence } from "@/components/evidence/evidence-drawer";
import { LogoBadge } from "@/components/shell/logo";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import type { DiscrepancyList, Flag } from "@/lib/api";
import { cn } from "@/lib/cn";
import { date, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { KIND_TONE } from "@/lib/labels";

const rate = (text: string | null) =>
  parseFloat(
    (text ?? "")
      .replace(/[^\d.]/g, " ")
      .trim()
      .split(" ")[0],
  );

/** The three story cards, picked by rule from the flags. */
function pickHeroes(items: Flag[]): { label: string; flag: Flag }[] {
  const byImpact = [...items].sort((a, b) => b.impact - a.impact);
  const rateFlags = byImpact.filter((f) => f.kind === "tax_rate");
  // An abolished slab still charged *below* the right rate tells the GST 2.0 story best.
  const taxRate =
    rateFlags.find((f) => f.title.startsWith("Abolished") && rate(f.recorded) < rate(f.expected)) ??
    rateFlags[0];
  const heads = byImpact.filter((f) => f.kind === "tax_head");
  const taxHead = heads.find((f) => f.title.startsWith("IGST on an intra")) ?? heads[0];
  const dup =
    byImpact.find((f) => f.kind === "near_duplicate") ??
    byImpact.find((f) => f.kind === "duplicate");
  return [
    taxRate && { label: "Tax rate", flag: taxRate },
    taxHead && { label: "Tax head", flag: taxHead },
    dup && { label: "Duplicate", flag: dup },
  ].filter((x): x is { label: string; flag: Flag } => Boolean(x));
}

function field(f: Flag, key: string): string | null {
  // The flagged record's own link first (a duplicate's chain starts with the original).
  const links = [...f.evidence.chain].sort(
    (a, b) => Number(b.id === f.invoice_id) - Number(a.id === f.invoice_id),
  );
  for (const link of links) {
    const v = link.fields[key];
    if (v !== undefined && v !== null && v !== "") return String(v);
  }
  return null;
}

function FlipCard({ label, flag, index }: { label: string; flag: Flag; index: number }) {
  const show = useEvidence();
  const hsn = field(flag, "hsn");
  const when = field(flag, "date")?.slice(0, 10);
  const note =
    flag.kind === "duplicate" || flag.kind === "near_duplicate"
      ? flag.evidence.summary
      : flag.kind === "tax_rate"
        ? flag.evidence.notes.join(" ")
        : (flag.evidence.notes[0] ?? flag.evidence.summary);
  return (
    <div className="[perspective:1400px]">
      <motion.div
        className="relative h-full min-h-[300px] [transform-style:preserve-3d]"
        initial={{ rotateY: 180 }}
        animate={{ rotateY: 0 }}
        transition={{ delay: 0.5 + index * 0.6, duration: 0.8, ease: [0.3, 1.2, 0.4, 1] }}
      >
        {/* back */}
        <div className="card absolute inset-0 grid place-items-center overflow-hidden [backface-visibility:hidden] [transform:rotateY(180deg)]">
          <div className="absolute inset-0 bg-[repeating-linear-gradient(45deg,var(--orange)_0_14px,var(--orange-pale)_14px_28px)] opacity-80" />
          <div className="relative rounded-full bg-panel p-3 shadow-[3px_3px_0_var(--ink)]">
            <LogoBadge size={64} />
          </div>
        </div>
        {/* front */}
        <button
          type="button"
          onClick={() => show(flag)}
          className="card flex h-full w-full flex-col p-5 text-left [backface-visibility:hidden]"
        >
          <div className="flex items-center justify-between gap-2">
            <Chip tone={KIND_TONE[flag.kind] ?? "warn"}>{label}</Chip>
            <span className="font-mono text-[12px] text-muted">{inr(flag.impact)} at stake</span>
          </div>
          <h3 className="mt-3 font-heading text-[18px] font-bold leading-tight text-ink">
            {flag.title}
          </h3>
          <div className="mt-1 text-[13px] text-muted">
            <span className="font-mono font-semibold text-ink">{flag.ref}</span> ·{" "}
            {flag.counterparty}
            {when && ` · ${date(when)}`}
            {hsn && ` · HSN ${hsn}`}
          </div>
          <div className="mt-4 overflow-hidden rounded-xl border-[1.5px] border-line font-mono text-[13.5px]">
            <div className="flex items-center justify-between gap-3 bg-bad/10 px-3 py-2 text-bad">
              <span className="font-sans text-[11px] font-bold uppercase tracking-wider">
                Recorded
              </span>
              <span>{flag.recorded}</span>
            </div>
            <div className="flex items-center justify-between gap-3 bg-ok/10 px-3 py-2 text-ok">
              <span className="font-sans text-[11px] font-bold uppercase tracking-wider">
                Expected
              </span>
              <span>{flag.expected}</span>
            </div>
          </div>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted">{note}</p>
          <span className="mt-auto pt-3 text-[12.5px] font-semibold text-orange">
            See the evidence →
          </span>
        </button>
      </motion.div>
    </div>
  );
}

export function DiscrepanciesScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const type = params.get("type");
  const { data: all, error } = useApi<DiscrepancyList>("/discrepancies");
  const show = useEvidence();
  const heroes = useMemo(() => pickHeroes(all?.items ?? []), [all]);

  if (error) return <ErrorState error={error} />;
  if (!all) return <Skeleton className="h-[640px]" />;

  const kinds = all.counts;
  const wanted = type === "duplicate" ? ["duplicate", "near_duplicate"] : type ? [type] : null;
  const rows = wanted ? all.items.filter((f) => wanted.includes(f.kind)) : all.items;
  const setType = (k: string | null) =>
    router.replace(k ? `/discrepancies/?type=${k}` : "/discrepancies/", { scroll: false });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => setType(null)}>
          <Chip tone={!type ? "orange" : "neutral"}>All · {all.items.length}</Chip>
        </button>
        {kinds.map((k) => (
          <button key={k.kind} type="button" onClick={() => setType(k.kind)}>
            <Chip tone={type === k.kind ? "orange" : (KIND_TONE[k.kind] ?? "neutral")}>
              {k.label} · {k.count}
            </Chip>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {heroes.map((h, i) => (
          <FlipCard key={h.flag.flag_id} label={h.label} flag={h.flag} index={i} />
        ))}
      </div>

      <Card title="All flags" subtitle="Click a row to see the records behind it">
        {rows.length === 0 ? (
          <EmptyState title="Nothing of this kind.">Try another filter.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-[13px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                  <th className="pb-2 font-bold">Record</th>
                  <th className="pb-2 font-bold">Counterparty</th>
                  <th className="pb-2 font-bold">Type</th>
                  <th className="pb-2 font-bold">Recorded</th>
                  <th className="pb-2 font-bold">Expected</th>
                  <th className="pb-2 text-right font-bold">₹ impact</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((f, i) => (
                  <motion.tr
                    key={f.flag_id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 + Math.min(i, 25) * 0.025 }}
                    onClick={() => show(f)}
                    className="cursor-pointer border-t border-line align-top hover:bg-peach/50"
                  >
                    <td className="py-2 pr-3 font-mono font-semibold text-ink">{f.ref}</td>
                    <td className="max-w-[220px] truncate py-2 pr-3 text-ink">{f.counterparty}</td>
                    <td className="py-2 pr-3">
                      <Chip tone={KIND_TONE[f.kind] ?? "neutral"}>{f.label}</Chip>
                    </td>
                    <td className={cn("py-2 pr-3 font-mono text-bad")}>{f.recorded}</td>
                    <td className="py-2 pr-3 font-mono text-ok">{f.expected}</td>
                    <td className="py-2 text-right font-mono font-semibold text-ink">
                      {f.impact > 0 ? inr(f.impact) : "—"}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
