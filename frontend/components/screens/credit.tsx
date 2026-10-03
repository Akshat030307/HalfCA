"use client";

import { RotateCcw } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { RingGraph } from "@/components/credit/ring-graph";
import { useEvidence } from "@/components/evidence/evidence-drawer";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import type { CreditGraph, SupplierRisk } from "@/lib/api";
import { inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { DECISION_TONE } from "@/lib/labels";

function RiskCard({ s, threshold }: { s: SupplierRisk; threshold: number }) {
  const showEvidence = useEvidence();
  const signals = [...s.ring_signals, ...s.signals];
  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", stiffness: 220, damping: 24 }}
      className="card flex flex-col gap-4 p-5"
    >
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-heading text-[20px] font-bold leading-tight text-ink">{s.name}</h2>
          <Chip tone={s.at_risk ? "bad" : "ok"}>{s.at_risk ? "At risk" : "Clear"}</Chip>
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          <span className="font-mono">{s.gstin}</span> · {s.state ?? s.city}
        </div>
      </div>

      <div>
        <div className="flex items-end justify-between">
          <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
            Taint score
          </span>
          <span className="font-display text-[34px] leading-none text-bad">
            {s.risk.toFixed(2)}
          </span>
        </div>
        <div className="relative mt-2 h-3.5 overflow-hidden rounded-full bg-peach">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-warn to-bad"
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(1, s.risk) * 100}%` }}
            transition={{ duration: 1.2, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
          />
          <div
            className="absolute inset-y-0 w-0.5 bg-ink"
            style={{ left: `${threshold * 100}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-muted">
          <span>0</span>
          <span style={{ marginLeft: `${threshold * 100 - 10}%` }}>
            at-risk line {threshold.toFixed(1)}
          </span>
          <span>1</span>
        </div>
        {s.hops_to_you && s.ring_members.length > 0 && (
          <p className="mt-2 text-[13px] font-semibold text-ink">
            {s.hops_to_you} hops downstream of a {s.ring_members.length}-firm ring
          </p>
        )}
      </div>

      {signals.length > 0 && (
        <div>
          <div className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
            Ring signals
          </div>
          <ul className="space-y-1.5">
            {signals.slice(0, 5).map((t) => (
              <li key={t} className="flex gap-2 text-[12.5px] leading-snug text-ink">
                <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-bad text-[10px] font-black text-white">
                  !
                </span>
                {t}
              </li>
            ))}
            {s.benford?.nonconforming && (
              <li className="flex gap-2 text-[12.5px] leading-snug text-ink">
                <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-warn text-[10px] font-black text-white">
                  !
                </span>
                Invoice amounts fail Benford (MAD {s.benford.mad.toFixed(3)} over {s.benford.n})
              </li>
            )}
          </ul>
        </div>
      )}

      <div>
        <div className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
          Your invoices · ITC {inr(s.itc_at_risk)} held
        </div>
        <ul className="divide-y divide-line rounded-xl border-[1.5px] border-line">
          {s.invoices.map((i) => (
            <li key={i.invoice_id} className="flex items-center gap-2 px-3 py-1.5 text-[12.5px]">
              <span className="font-mono text-ink">{i.invoice_no}</span>
              <span className="ml-auto font-mono text-ink">{inr(i.itc)}</span>
              {i.ims_decision && <Chip tone={DECISION_TONE[i.ims_decision]}>{i.ims_decision}</Chip>}
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-2xl border-2 border-ink bg-orange-pale/50 p-3 dark:border-orange">
        <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink">Action</div>
        <p className="mt-1 text-[13px] leading-snug text-ink">{s.action}</p>
        {s.flag && (
          <button
            type="button"
            onClick={() => s.flag && showEvidence(s.flag)}
            className="mt-2 text-[12.5px] font-semibold text-orange hover:underline"
          >
            See the evidence →
          </button>
        )}
      </div>
    </motion.div>
  );
}

export function CreditScreen() {
  const { data: graph, error } = useApi<CreditGraph>("/credit/graph");
  const focus = graph?.focus ?? null;
  const { data: supplier } = useApi<SupplierRisk>(focus ? `/credit/supplier/${focus}` : null);
  const [runKey, setRunKey] = useState(0);
  const [cardFor, setCardFor] = useState(-1);

  if (error) return <ErrorState error={error} />;
  if (!graph) return <Skeleton className="h-[640px]" />;

  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[1fr_340px]">
      <Card
        title="Whose credit is your credit built on?"
        subtitle={
          graph.cycles.length
            ? `Seller → buyer trades upstream of you · ${graph.cycles.length} ring within 3 hops`
            : "Seller → buyer trades upstream of you"
        }
        right={
          <Button variant="ghost" onClick={() => setRunKey((k) => k + 1)}>
            <RotateCcw size={14} /> Replay
          </Button>
        }
        bodyClassName="p-3 pt-2"
      >
        <div className="overflow-hidden rounded-2xl">
          <RingGraph
            graph={graph}
            supplier={supplier ?? null}
            runKey={runKey}
            onFocusClick={() => setCardFor(runKey)}
          />
        </div>
      </Card>

      <AnimatePresence mode="wait">
        {!focus ? (
          <Card key="none" title="No supplier at risk">
            <EmptyState title="Nothing fishy here. Yet.">
              None of your direct suppliers sits within reach of a circular-trading ring.
            </EmptyState>
          </Card>
        ) : supplier && cardFor === runKey ? (
          <RiskCard key={`card-${runKey}`} s={supplier} threshold={graph.threshold} />
        ) : (
          <div
            key="wait"
            className="card halftone grid h-[420px] place-items-center p-6 text-center text-[13px] text-muted"
          >
            Watch the supplier in amber…
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
