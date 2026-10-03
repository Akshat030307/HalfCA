"use client";

import { Check, X } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";

import { Donut } from "@/components/charts/donut";
import { HBars } from "@/components/charts/hbars";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { CountUp } from "@/components/ui/count-up";
import { KpiTile } from "@/components/ui/kpi";
import { ErrorState, LoadingBlocks, Skeleton } from "@/components/ui/states";
import type { InvoiceDetail, Summary } from "@/lib/api";
import { date, duration, inr, lakh, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cssVar } from "@/lib/tokens";

const DONUT_COLOR: Record<string, string> = {
  matched: cssVar.ok,
  discrepant: cssVar.warn,
  duplicate: cssVar.dup,
  unmatched: cssVar.idle,
};

type Thread = { label: string; ok: boolean; detail: string; road?: boolean };

function threadsOf(d: InvoiceDetail): Thread[] {
  const inv = d.invoice as { invoice_date: string; total: number };
  const pay = d.payments[0] as { mode?: string; txn_date?: string; amount?: number } | undefined;
  const v = d.voucher as { voucher_no?: string; voucher_date?: string } | null;
  const p = d.physical as {
    verdict?: string;
    tolls_crossed?: number;
    plazas_expected?: number;
    window_hours?: number;
    distance_km?: number;
    trip_minutes?: number;
    recycled_with?: string;
  } | null;
  let road = "Not an inter-state consignment";
  let roadOk = true;
  if (p?.verdict === "verified") road = `${p.tolls_crossed}/${p.plazas_expected} tolls crossed`;
  else if (p?.verdict === "paper_only") {
    road = `0 toll crossings in ${Math.round(p.window_hours ?? 0)} h`;
    roadOk = false;
  } else if (p?.verdict === "impossible_journey") {
    road = `${p.distance_km} km in ${duration(p.trip_minutes ?? 0)}`;
    roadOk = false;
  } else if (p?.verdict === "recycled_ewb") {
    road = "One trip claimed by several invoices";
    roadOk = false;
  } else if (p?.verdict === "missing_ewb") {
    road = "No e-way bill";
    roadOk = false;
  }
  return [
    { label: "Invoice", ok: true, detail: `${date(inv.invoice_date, false)} · ${inr(inv.total)}` },
    {
      label: "Payment",
      ok: Boolean(pay),
      detail: pay
        ? `${pay.mode} · ${date(pay.txn_date ?? "", false)} · ${inr(pay.amount ?? 0)}`
        : "Not paid yet",
    },
    {
      label: "Ledger",
      ok: Boolean(v),
      detail: v ? `${v.voucher_no} · ${date(v.voucher_date ?? "", false)}` : "Not in the books",
    },
    { label: "Road", ok: roadOk, detail: road, road: true },
  ];
}

function ThreadCard({ id, index }: { id: string; index: number }) {
  const { data } = useApi<InvoiceDetail>(`/invoices/${id}`);
  if (!data) return <Skeleton className="h-44" />;
  const inv = data.invoice as {
    invoice_no: string;
    supplier_name: string;
    buyer_name: string;
    direction: string;
  };
  const threads = threadsOf(data);
  const passed = threads.filter((t) => t.ok).length;
  const party = inv.direction === "inward" ? inv.supplier_name : inv.buyer_name;
  return (
    <div className="rounded-2xl border-[1.5px] border-line bg-panel p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="truncate text-[13.5px] font-semibold text-ink">
          <span className="font-mono">{inv.invoice_no}</span> · {party}
        </div>
        <Chip tone={passed === threads.length ? "ok" : "bad"}>
          {passed}/{threads.length}
        </Chip>
      </div>
      <ul className="space-y-1.5">
        {threads.map((t, i) => (
          <motion.li
            key={t.label}
            initial={{ opacity: 0.25 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 + index * 1.2 + i * 0.3, duration: 0.3 }}
            className="flex items-center gap-2.5 text-[13px]"
          >
            <span
              className={`grid h-5 w-5 shrink-0 place-items-center rounded-full ${t.ok ? "bg-ok" : "bg-bad"}`}
            >
              {t.ok ? (
                <Check size={12} strokeWidth={3} className="text-white" />
              ) : (
                <X size={12} strokeWidth={3} className="text-white" />
              )}
            </span>
            <span className={`w-16 font-semibold ${t.road ? "text-orange" : "text-ink"}`}>
              {t.label}
            </span>
            <span
              className={`ml-auto truncate text-right ${t.ok ? "text-muted" : "font-semibold text-bad"}`}
            >
              {t.detail}
            </span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

export function OverviewScreen() {
  const { data, error } = useApi<Summary>("/summary");
  const router = useRouter();
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingBlocks />;
  const k = data.kpis;
  const types = data.discrepancy_types;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 min-[1400px]:grid-cols-6">
        <KpiTile index={0} label="Reconciled" value={k.reconciled} caption="invoices this month" />
        <KpiTile index={1} label="Matched" value={k.matched} tone="ok" caption="clean on paper" />
        <KpiTile
          index={2}
          label="Discrepancies"
          value={k.discrepancies}
          tone="warn"
          caption="need a fix"
        />
        <KpiTile
          index={3}
          label="Duplicates"
          value={k.duplicates}
          tone="dup"
          caption="keyed twice"
        />
        <KpiTile index={4} label="Unmatched" value={k.unmatched} tone="idle" caption="no partner" />
        <KpiTile
          index={5}
          label="Exposure caught"
          value={k.exposure}
          format={(n) => lakh(n)}
          tone="highlight"
          caption="before filing"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_1fr_1.15fr]">
        <Card title="Where the month landed" subtitle="Every invoice, by outcome">
          <div className="flex flex-col items-center gap-5">
            <Donut
              slices={data.donut.map((d) => ({ ...d, color: DONUT_COLOR[d.key] ?? cssVar.idle }))}
              center={
                <div>
                  <div className="font-display text-[34px] leading-none text-ink">
                    <CountUp
                      value={k.clean_match_pct * 100}
                      format={(n) => `${n.toFixed(1)}%`}
                      delay={0.4}
                    />
                  </div>
                  <div className="mt-1 text-[12px] text-muted">clean match</div>
                </div>
              }
            />
            <ul className="grid w-full grid-cols-2 gap-x-4 gap-y-1.5 text-[13px]">
              {data.donut.map((d) => (
                <li key={d.key} className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: DONUT_COLOR[d.key] }}
                  />
                  <span className="text-muted">{d.label}</span>
                  <span className="ml-auto font-mono font-semibold text-ink">{d.value}</span>
                </li>
              ))}
            </ul>
            <div className="text-[12px] text-muted">
              {pct(k.matched / Math.max(k.reconciled, 1))} of invoices need nothing from you.
            </div>
          </div>
        </Card>

        <Card title="Discrepancies by type" subtitle="Click a bar to see those flags">
          <HBars
            bars={types.map((t) => ({
              key: t.kind,
              label: t.label,
              value: t.count,
              color: t.kind === "duplicate" ? cssVar.dup : cssVar.warn,
              onClick: () => router.push(`/discrepancies/?type=${t.kind}`),
            }))}
          />
          <p className="mt-5 text-[12.5px] text-muted">
            {data.tax_errors.inward ?? 0} tax errors on purchases become IMS rejections;{" "}
            {data.tax_errors.outward ?? 0} on sales change what you owe.
          </p>
        </Card>

        <Card
          title="Four threads · two invoices"
          subtitle="Paper agrees in both. Only one truck moved."
        >
          <div className="space-y-3">
            {data.examples.all_clear && <ThreadCard id={data.examples.all_clear} index={0} />}
            {data.examples.road_fail && <ThreadCard id={data.examples.road_fail} index={1} />}
          </div>
        </Card>
      </div>
    </div>
  );
}
