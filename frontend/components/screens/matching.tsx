"use client";

import { motion } from "motion/react";

import { useEvidence } from "@/components/evidence/evidence-drawer";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import type { DiscrepancyList, Funnel } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count, date, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export function MatchingScreen() {
  const { data, error } = useApi<Funnel>("/funnel");
  const { data: flags } = useApi<DiscrepancyList>("/discrepancies?type=unmatched");
  const showEvidence = useEvidence();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Skeleton className="h-[520px]" />;

  const first = data.stages[0]?.records_in || 1;
  const last = data.stages[data.stages.length - 1];
  const byInvoice = new Map((flags?.items ?? []).map((f) => [f.invoice_id, f]));

  return (
    <div className="space-y-6">
      <Card
        title="Four stages, cheapest first"
        subtitle="Each stage only sees what the one before it could not pair."
        right={
          data.llm.model ? (
            <Chip tone="orange">✦ Stage 4 · {data.llm.model}</Chip>
          ) : (
            <Chip tone="idle">Stage 4 off · no LLM</Chip>
          )
        }
      >
        <ol className="space-y-4">
          {data.stages.map((st, i) => {
            const ai = st.stage === 4;
            return (
              <li key={st.stage} className="grid grid-cols-[230px_1fr_190px] items-center gap-5">
                <div>
                  <div className="font-heading text-[15px] font-bold text-ink">
                    <span className="mr-2 font-mono text-[12px] text-muted">{st.stage}</span>
                    {st.label}
                  </div>
                  <div className="text-[12.5px] text-muted">{st.method}</div>
                </div>
                <div className="h-11 rounded-2xl bg-peach/70 p-1">
                  <motion.div
                    className={cn(
                      "relative flex h-full items-center overflow-hidden rounded-xl px-3 font-mono text-[13px] font-bold",
                      ai
                        ? "bg-gradient-to-r from-[#8a6100] to-[#c99a1a] text-white"
                        : "bg-orange text-on-orange",
                      st.skipped && "bg-idle/40 text-ink",
                    )}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.max(ai ? 17 : 13, (st.records_in / first) * 100)}%` }}
                    transition={{ duration: 0.7, delay: 0.2 + i * 0.35, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <span className="whitespace-nowrap">{count(st.records_in)} in</span>
                    {ai && !st.skipped && (
                      <motion.span
                        className="absolute right-2 text-[16px]"
                        animate={{ opacity: [0.3, 1, 0.3], scale: [0.85, 1.15, 0.85] }}
                        transition={{ repeat: Infinity, duration: 1.6 }}
                      >
                        ✦
                      </motion.span>
                    )}
                  </motion.div>
                </div>
                <div className="text-right text-[14px] text-muted">
                  {st.skipped ? (
                    <span>skipped · {st.left} left</span>
                  ) : (
                    <>
                      <b className="font-display text-[22px] font-normal text-ink">
                        {count(st.paired)}
                      </b>{" "}
                      paired · {count(st.left)} left
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      <Card
        title={
          <span>
            Unmatched queue{" "}
            <span className="font-display text-[22px] font-normal text-idle">
              {last?.left ?? 0}
            </span>
          </span>
        }
        subtitle="Records with no partner in the books, sorted by ₹ impact"
      >
        {data.unmatched.length === 0 ? (
          <EmptyState title="Everything found a partner.">Nothing left in the queue.</EmptyState>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                <th className="pb-2 font-bold">Invoice</th>
                <th className="pb-2 font-bold">Date</th>
                <th className="pb-2 font-bold">Counterparty</th>
                <th className="pb-2 font-bold">Type</th>
                <th className="pb-2 font-bold">Money</th>
                <th className="pb-2 text-right font-bold">₹ impact</th>
              </tr>
            </thead>
            <tbody>
              {data.unmatched.map((u, i) => {
                const flag = byInvoice.get(u.invoice_id);
                return (
                  <motion.tr
                    key={u.invoice_id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 + Math.min(i, 20) * 0.03 }}
                    onClick={() => flag && showEvidence(flag)}
                    className="cursor-pointer border-t border-line hover:bg-peach/50"
                  >
                    <td className="py-2 font-mono font-semibold text-ink">{u.invoice_no}</td>
                    <td className="py-2 text-muted">{date(u.invoice_date, false)}</td>
                    <td className="py-2 text-ink">{u.counterparty}</td>
                    <td className="py-2">
                      <Chip tone="neutral">{u.direction === "inward" ? "Purchase" : "Sale"}</Chip>
                    </td>
                    <td className="py-2 text-muted">
                      {u.paid ? "Paid, never booked" : "No payment"}
                    </td>
                    <td className="py-2 text-right font-mono font-semibold text-ink">
                      {inr(u.total)}
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
