"use client";

import { Check, Clock } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { useEvidence } from "@/components/evidence/evidence-drawer";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { KpiTile } from "@/components/ui/kpi";
import { ErrorState, LoadingBlocks } from "@/components/ui/states";
import { Toast } from "@/components/ui/toast";
import { api, type Ims, type ImsRecord } from "@/lib/api";
import { useNow } from "@/lib/clock";
import { cn } from "@/lib/cn";
import { count, date, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";

const PILL: Record<string, string> = {
  Accept: "border-ok/40 bg-ok/10 text-ok",
  Reject: "border-bad/40 bg-bad/10 text-bad",
  Pending: "border-warn/40 bg-warn/10 text-warn",
};
const PAGE = 40;

function Pill({ r, approvedIndex }: { r: ImsRecord; approvedIndex: number | null }) {
  if (r.approved && r.decision === "Accept") {
    return (
      <motion.span
        initial={approvedIndex !== null ? { scale: 0.7, opacity: 0.4 } : false}
        animate={{ scale: 1, opacity: 1 }}
        transition={{
          delay: (approvedIndex ?? 0) * 0.025,
          type: "spring",
          stiffness: 400,
          damping: 14,
        }}
        className="inline-flex items-center gap-1 rounded-full border-[1.5px] border-ok bg-ok px-2.5 py-0.5 text-[12px] font-bold text-white"
      >
        <Check size={12} strokeWidth={3} /> Approved
      </motion.span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex rounded-full border-[1.5px] px-2.5 py-0.5 text-[12px] font-bold",
        PILL[r.decision],
      )}
    >
      {r.decision}
    </span>
  );
}

export function ImsHeaderRight() {
  const { data, mutate } = useApi<Ims>("/ims");
  const now = useNow();
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!data) return null;
  const due = new Date(`${data.gstr2b_date}T00:00:00+05:30`);
  const days = now === null ? null : Math.max(0, Math.ceil((due.getTime() - now) / 86_400_000));
  const left = data.counts.accept - data.counts.approved;

  async function approve() {
    setBusy(true);
    try {
      const res = await api.approveIms();
      setToast(res.message);
      await mutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Chip tone="warn">
        <Clock size={13} />
        GSTR-2B generates {days === null ? "soon" : days === 0 ? "today" : `in ${days} days`} ·{" "}
        {date(data.gstr2b_date, false)}
      </Chip>
      <Button onClick={() => void approve()} disabled={busy || left === 0}>
        {left === 0
          ? `✓ ${count(data.counts.approved)} approved`
          : `Approve ${count(left)} accepts`}
      </Button>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

export function ImsScreen() {
  const { data, error } = useApi<Ims>("/ims");
  const show = useEvidence();
  const [limit, setLimit] = useState(PAGE);
  const [filter, setFilter] = useState<string | null>(null);

  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingBlocks rows={1} />;
  const c = data.counts;
  const rows = data.records.filter((r) => !filter || r.decision === filter);
  const acceptOrder = new Map(
    data.records.filter((r) => r.decision === "Accept").map((r, i) => [r.ims_id, i]),
  );

  async function evidence(r: ImsRecord) {
    if (!r.invoice_id) return;
    const d = await api.invoice(r.invoice_id);
    const f = d.flags.find((x) =>
      [
        "tax_rate",
        "tax_head",
        "tax_arith",
        "paper_only",
        "impossible_journey",
        "recycled_ewb",
        "missing_ewb",
      ].includes(x.kind),
    );
    if (f) show(f);
    else if (r.rule === "supplier_taint") {
      const s = await api.supplier(r.supplier_gstin);
      if (s.flag) show(s.flag);
    }
  }

  const tiles: {
    label: string;
    value: number;
    tone: "neutral" | "ok" | "bad" | "warn";
    key: string | null;
  }[] = [
    { label: "Supplier records", value: c.records, tone: "neutral", key: null },
    { label: "Accept", value: c.accept, tone: "ok", key: "Accept" },
    { label: "Reject", value: c.reject, tone: "bad", key: "Reject" },
    { label: "Pending", value: c.pending, tone: "warn", key: "Pending" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {tiles.map((t, i) => (
          <button
            key={t.label}
            type="button"
            onClick={() => setFilter(t.key)}
            className="text-left"
          >
            <KpiTile
              index={i}
              label={t.label}
              value={t.value}
              tone={t.tone}
              caption={
                filter === t.key ? "showing these" : t.key ? "click to filter" : "click to show all"
              }
            />
          </button>
        ))}
      </div>

      <Card
        title="Autopilot's call on every supplier invoice"
        subtitle="Decided by rules on the evidence; nothing reaches the GST portal from this demo"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                <th className="pb-2 font-bold">Supplier</th>
                <th className="pb-2 font-bold">Invoice</th>
                <th className="pb-2 font-bold">Date</th>
                <th className="pb-2 text-right font-bold">Taxable</th>
                <th className="pb-2 text-right font-bold">ITC</th>
                <th className="pb-2 pl-4 font-bold">Autopilot</th>
                <th className="pb-2 font-bold">Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, limit).map((r, i) => (
                <motion.tr
                  key={r.ims_id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 + Math.min(i, 25) * 0.025 }}
                  onClick={() => void evidence(r)}
                  className={cn(
                    "border-t border-line",
                    r.decision !== "Accept" && "cursor-pointer hover:bg-peach/50",
                  )}
                >
                  <td className="max-w-[200px] truncate py-2 pr-3 text-ink">{r.supplier_name}</td>
                  <td className="py-2 pr-3 font-mono font-semibold text-ink">{r.invoice_no}</td>
                  <td className="py-2 pr-3 text-muted">{date(r.invoice_date, false)}</td>
                  <td className="py-2 pr-3 text-right font-mono text-ink">
                    {inr(r.taxable_value)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono font-semibold text-ink">
                    {inr(r.itc)}
                  </td>
                  <td className="py-2 pl-4 pr-3">
                    <Pill
                      r={r}
                      approvedIndex={r.approved ? (acceptOrder.get(r.ims_id) ?? 0) : null}
                    />
                  </td>
                  <td className="max-w-[340px] truncate py-2 text-muted" title={r.reason}>
                    {r.reason}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > limit && (
          <div className="mt-4 text-center">
            <Button variant="secondary" onClick={() => setLimit((l) => l + 80)}>
              Show more ({rows.length - limit} left)
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
