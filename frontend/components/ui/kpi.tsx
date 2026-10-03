"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/cn";

import { CountUp } from "./count-up";

type KpiTone = "neutral" | "ok" | "warn" | "dup" | "idle" | "bad" | "highlight";

const NUMBER_TONE: Record<KpiTone, string> = {
  neutral: "text-ink",
  ok: "text-ok",
  warn: "text-warn",
  dup: "text-dup",
  idle: "text-idle",
  bad: "text-bad",
  highlight: "text-on-orange",
};

export function KpiTile({
  label,
  value,
  format,
  tone = "neutral",
  caption,
  index = 0,
}: {
  label: string;
  value: number;
  format?: (n: number) => string;
  tone?: KpiTone;
  caption?: string;
  index?: number;
}) {
  const highlight = tone === "highlight";
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 24, delay: index * 0.08 }}
      className={cn(
        "card relative overflow-hidden px-5 py-4",
        highlight && "border-ink! bg-gradient-to-br from-orange to-[#ffb347] dark:border-orange!",
      )}
    >
      {highlight && <div className="halftone absolute inset-0 opacity-60" />}
      <div className="relative">
        <div
          className={cn(
            "text-[11px] font-bold uppercase tracking-[0.14em]",
            highlight ? "text-on-orange/80" : "text-muted",
          )}
        >
          {label}
        </div>
        <div
          className={cn(
            "mt-1 font-display text-[44px] leading-none tracking-wide tabular",
            NUMBER_TONE[tone],
          )}
        >
          <CountUp value={value} format={format} delay={0.15 + index * 0.08} />
        </div>
        {caption && (
          <div className={cn("mt-1.5 text-[12px]", highlight ? "text-on-orange/80" : "text-muted")}>
            {caption}
          </div>
        )}
      </div>
    </motion.div>
  );
}
