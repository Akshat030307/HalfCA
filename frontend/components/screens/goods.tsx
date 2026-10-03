"use client";

import { Play } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useMemo, useState } from "react";

import { useEvidence } from "@/components/evidence/evidence-drawer";
import { RouteMap, type BeatPlay } from "@/components/goods/route-map";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { api, type Goods, type Summary, type Trip } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count, ewb, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { VERDICT_TEXT } from "@/lib/labels";

function amountText(trips: Trip[]): string {
  const same = trips.every((t) => t.total === trips[0].total);
  return trips.length > 1 && same ? `${inr(trips[0].total)} ×${trips.length}` : inr(trips[0].total);
}

export function GoodsScreen() {
  const { data, error } = useApi<Goods>("/goods");
  const { data: summary } = useApi<Summary>("/summary");
  const showEvidence = useEvidence();
  const [active, setActive] = useState(0);
  const [runKey, setRunKey] = useState(0);
  const [auto, setAuto] = useState(true);
  const [done, setDone] = useState<Set<number>>(new Set());

  const beats: BeatPlay[] = useMemo(() => {
    if (!data) return [];
    const byId = new Map(data.invoices.map((t) => [t.invoice_id, t]));
    return data.beats.map((b) => ({
      kind: b.kind,
      trips: b.invoice_ids.map((id) => byId.get(id)).filter((t): t is Trip => Boolean(t)),
    }));
  }, [data]);

  const onEnd = useCallback(() => {
    setDone((prev) => new Set(prev).add(active));
    if (auto && active < beats.length - 1) {
      window.setTimeout(() => {
        setActive((a) => a + 1);
        setRunKey((k) => k + 1);
      }, 700);
    }
  }, [active, auto, beats.length]);

  function replay(i: number) {
    setAuto(false);
    setActive(i);
    setRunKey((k) => k + 1);
  }

  async function evidenceFor(trip: Trip) {
    const detail = await api.trip(trip.invoice_id);
    if (detail.flags[0]) showEvidence(detail.flags[0]);
  }

  if (error) return <ErrorState error={error} />;
  if (!data) return <Skeleton className="h-[640px]" />;
  const allDone = beats.length > 0 && done.size >= beats.length;
  const failedOnRoad = summary?.physical.failed_inside_matched ?? 0;

  return (
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[1fr_360px]">
      <Card
        title="Where the goods actually went"
        subtitle={`${count(data.invoices.length)} inter-state consignments of ₹50,000+ checked against FASTag toll crossings`}
        bodyClassName="p-3 pt-2"
      >
        <RouteMap
          goods={data}
          beat={beats[active] ?? null}
          runKey={runKey}
          onEnd={onEnd}
          className="overflow-hidden rounded-2xl"
        />
      </Card>

      <div className="flex flex-col gap-3">
        {beats.map((b, i) => {
          const t = b.trips[0];
          const isActive = i === active;
          const ok = b.kind === "verified";
          return (
            <motion.button
              key={`${b.kind}-${t.invoice_id}`}
              type="button"
              onClick={() => replay(i)}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 + i * 0.1 }}
              className={cn(
                "card group relative px-4 py-3 text-left transition-[outline-color]",
                isActive ? "outline-[3px] outline-offset-2 outline-orange" : "outline-0",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-mono text-[14px] font-bold text-ink">
                    {t.invoice_no}
                    {b.trips.length > 1 && (
                      <span className="text-muted"> +{b.trips.length - 1}</span>
                    )}
                  </div>
                  <div className="truncate text-[13px] text-ink">{t.supplier}</div>
                </div>
                <div className="text-right font-mono text-[13px] font-semibold text-ink">
                  {amountText(b.trips)}
                </div>
              </div>
              <div className="mt-1.5 truncate font-mono text-[11.5px] text-muted">
                EWB {t.ewb_no ? ewb(t.ewb_no) : "—"} · {t.vehicle_no ?? "—"}
              </div>
              <div className="mt-2 flex min-h-[26px] items-center justify-between">
                <AnimatePresence>
                  {done.has(i) ? (
                    <motion.span
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                    >
                      <Chip tone={ok ? "ok" : "bad"}>{VERDICT_TEXT[b.kind]}</Chip>
                    </motion.span>
                  ) : (
                    <span className="text-[12px] text-muted">
                      {isActive ? "On the road…" : "Waiting"}
                    </span>
                  )}
                </AnimatePresence>
                <span className="flex items-center gap-2">
                  {done.has(i) && !ok && (
                    <span
                      role="link"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation();
                        void evidenceFor(t);
                      }}
                      className="text-[12px] font-semibold text-orange hover:underline"
                    >
                      Evidence
                    </span>
                  )}
                  <Play size={14} className="text-muted group-hover:text-orange" />
                </span>
              </div>
            </motion.button>
          );
        })}

        <AnimatePresence>
          {allDone && failedOnRoad > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12, rotate: -1 }}
              animate={{ opacity: 1, y: 0, rotate: -1 }}
              className="rounded-[18px] border-2 border-ink bg-bad p-4 text-white shadow-[4px_4px_0_var(--ink)]"
            >
              <div className="font-display text-[26px] uppercase leading-[1.05]">
                {failedOnRoad} invoices passed every paper check.
              </div>
              <div className="mt-1 font-heading text-[15px] font-bold">They failed the road.</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
