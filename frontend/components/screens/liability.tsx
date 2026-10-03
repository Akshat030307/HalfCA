"use client";

import { FileDown, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { BenfordChart } from "@/components/charts/benford";
import { Waterfall } from "@/components/charts/waterfall";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CountUp } from "@/components/ui/count-up";
import { ErrorState, LoadingBlocks } from "@/components/ui/states";
import { api, type Benford, type Liability } from "@/lib/api";
import { inr, lakh, lakhNumber } from "@/lib/format";
import { useApi } from "@/lib/hooks";

function NetBar({
  label,
  value,
  max,
  color,
  delay,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
  delay: number;
}) {
  return (
    <div className="grid grid-cols-[90px_1fr_64px] items-center gap-3">
      <span className="text-[13px] font-semibold text-ink">{label}</span>
      <span className="h-8 overflow-hidden rounded-xl bg-peach">
        <motion.span
          className="block h-full rounded-xl border-[1.5px] border-ink"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(4, (value / max) * 100)}%` }}
          transition={{ delay, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
      </span>
      <span className="text-right font-display text-[22px] leading-none text-ink">
        {lakhNumber(value).toFixed(1)}
      </span>
    </div>
  );
}

/** Fetches the audit PDF (the first render takes a few seconds) and saves it. */
function ReportButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(api.reportUrl);
      if (!res.ok) throw new Error(res.statusText || `HTTP ${res.status}`);
      const blob = await res.blob();
      const name =
        /filename="?([^";]+)"?/.exec(res.headers.get("content-disposition") ?? "")?.[1] ??
        "Half-CA-audit-report.pdf";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Button onClick={() => void download()} disabled={busy}>
        {busy ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />}
        {busy ? "Preparing the report…" : "Download audit report (PDF)"}
      </Button>
      <span className="text-[12px] text-muted">
        {error ? (
          <span className="text-bad">Could not build the report: {error}</span>
        ) : (
          "Every finding with its evidence, ready to hand to your CA."
        )}
      </span>
    </div>
  );
}

export function LiabilityScreen() {
  const { data, error } = useApi<Liability>("/liability");
  const { data: bf } = useApi<Benford>(
    data?.benford_focus ? `/benford/${data.benford_focus}` : null,
  );
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingBlocks rows={1} />;
  const s = data.summary;
  const netMax = Math.max(s.net_payable_filed, s.net_payable_reconciled, 1);
  const total = data.heads.reduce(
    (t, h) => ({
      out: t.out + h.output_reconciled,
      itc: t.itc + h.itc_eligible,
      net: t.net + h.net_reconciled,
    }),
    { out: 0, itc: 0, net: 0 },
  );

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card
        title="Input tax credit · ₹ lakh"
        subtitle="What you'd claim as filed, and what survives the checks"
      >
        <Waterfall steps={data.waterfall} />
        <div className="mt-6 border-t-[1.5px] border-line pt-4">
          {bf ? (
            <>
              <div className="font-heading text-[14px] font-bold text-ink">
                Benford screen · {bf.name} · {bf.n} invoices
              </div>
              <BenfordChart observed={bf.observed} expected={bf.expected} />
              <p className="mt-1 text-[13px] text-muted">
                First-digit MAD <b className="font-mono text-bad">{bf.mad.toFixed(3)}</b> ·{" "}
                {bf.nonconforming ? "nonconforming" : "conforming"} (threshold {bf.threshold})
              </p>
            </>
          ) : (
            <p className="text-[13px] text-muted">
              No supplier has enough invoices to screen with Benford&apos;s law.
            </p>
          )}
        </div>
      </Card>

      <div className="flex flex-col gap-5">
        <Card
          title="Net payable · ₹ lakh"
          subtitle="Output tax minus the credit you can actually take"
        >
          <div className="space-y-3">
            <NetBar
              label="As filed"
              value={s.net_payable_filed}
              max={netMax}
              color="var(--idle)"
              delay={0.3}
            />
            <NetBar
              label="Reconciled"
              value={s.net_payable_reconciled}
              max={netMax}
              color="var(--orange)"
              delay={0.6}
            />
          </div>
          <p className="mt-4 rounded-xl bg-peach/70 px-3 py-2 font-mono text-[13px] text-ink">
            Output tax {lakh(s.output_tax_reconciled)} − eligible ITC {lakh(s.itc_eligible)} ={" "}
            <b>{lakh(s.net_payable_reconciled)}</b>
          </p>
          <motion.div
            initial={{ opacity: 0, scale: 0.96, rotate: -1 }}
            animate={{ opacity: 1, scale: 1, rotate: -1 }}
            transition={{ delay: 0.9 }}
            className="relative mt-5 overflow-hidden rounded-2xl border-2 border-ink bg-gradient-to-br from-orange to-[#ffb347] px-5 py-4 shadow-[4px_4px_0_var(--ink)] dark:border-orange"
          >
            <div className="halftone absolute inset-0 opacity-60" />
            <div className="relative">
              <div className="text-[11.5px] font-bold uppercase tracking-[0.16em] text-on-orange/80">
                Exposure caught before filing
              </div>
              <div className="font-display text-[44px] leading-none text-on-orange">
                <CountUp
                  value={s.exposure}
                  format={(n) => lakh(n).replace(" L", " lakh")}
                  delay={1}
                />
              </div>
              <div className="mt-1 text-[12.5px] text-on-orange/80">
                {lakh(s.itc_rejected)} rejected + {lakh(s.itc_at_risk)} held
                {s.under_reported_output > 0 &&
                  ` + ${lakh(s.under_reported_output)} under-reported`}
              </div>
            </div>
          </motion.div>
        </Card>

        <Card title="By tax head" subtitle="Reconciled figures">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                <th className="pb-2 font-bold">Head</th>
                <th className="pb-2 text-right font-bold">Output</th>
                <th className="pb-2 text-right font-bold">ITC</th>
                <th className="pb-2 text-right font-bold">Net</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {data.heads.map((h) => (
                <tr key={h.head} className="border-t border-line">
                  <td className="py-2 font-sans font-semibold text-ink">{h.head}</td>
                  <td className="py-2 text-right text-ink">{inr(h.output_reconciled)}</td>
                  <td className="py-2 text-right text-ink">{inr(h.itc_eligible)}</td>
                  <td className="py-2 text-right text-ink">{inr(h.net_reconciled)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-ink font-bold">
                <td className="py-2 font-sans text-ink">Total</td>
                <td className="py-2 text-right text-ink">{inr(total.out)}</td>
                <td className="py-2 text-right text-ink">{inr(total.itc)}</td>
                <td className="py-2 text-right text-ink">{inr(total.net)}</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-2 text-[12px] text-muted">
            IGST credit left over after IGST is set off against CGST and SGST, so a negative head is
            normal; the total is what you pay.
          </p>
          <ReportButton />
        </Card>
      </div>
    </div>
  );
}
