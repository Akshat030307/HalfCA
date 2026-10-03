"use client";

import { motion } from "motion/react";

import type { WaterfallStep } from "@/lib/api";
import { lakhNumber } from "@/lib/format";
import { cssVar } from "@/lib/tokens";

const COLORS = [cssVar.idle, cssVar.bad, cssVar.warn, cssVar.ok];

/** Claimed → −rejected → −at risk → eligible, in ₹ lakh. Deltas float. */
export function Waterfall({ steps }: { steps: WaterfallStep[] }) {
  const W = 520;
  const H = 250;
  const top = 34;
  const base = H - 30;
  const max = Math.max(...steps.map((s) => Math.abs(s.value)), 1);
  const y = (v: number) => base - (v / max) * (base - top);
  const bw = 78;
  const gap = (W - steps.length * bw) / (steps.length + 1);

  const bars: { s: WaterfallStep; i: number; x: number; y1: number; y2: number; joinAt: number }[] =
    [];
  let level = 0;
  for (const [i, s] of steps.entries()) {
    const from = s.kind === "total" ? 0 : level;
    const to = s.kind === "total" ? s.value : level + s.value;
    level = to;
    bars.push({
      s,
      i,
      x: gap + i * (bw + gap),
      y1: y(Math.max(from, to)),
      y2: y(Math.min(from, to)),
      joinAt: y(to),
    });
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="ITC waterfall"
    >
      <line x1="0" x2={W} y1={base} y2={base} stroke="var(--line)" strokeWidth="1.5" />
      {bars.map(({ s, i, x, y1, y2, joinAt }) => (
        <g key={s.step}>
          {i < bars.length - 1 && (
            <motion.line
              x1={x + bw}
              x2={x + bw + gap}
              y1={joinAt}
              y2={joinAt}
              stroke="var(--muted)"
              strokeDasharray="3 3"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.7 }}
              transition={{ delay: 0.6 + i * 0.45 }}
            />
          )}
          <motion.rect
            x={x}
            width={bw}
            rx="8"
            fill={COLORS[i % COLORS.length]}
            stroke="var(--ink)"
            strokeWidth="1.5"
            initial={{ y: y2, height: 0 }}
            animate={{ y: y1, height: Math.max(2, y2 - y1) }}
            transition={{ delay: 0.3 + i * 0.45, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          />
          <motion.text
            x={x + bw / 2}
            y={y1 - 9}
            textAnchor="middle"
            fontSize="17"
            fill="var(--ink)"
            fontFamily="var(--font-anton)"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.75 + i * 0.45 }}
          >
            {s.value < 0 ? "−" : ""}
            {Math.abs(lakhNumber(s.value)).toFixed(1)}
          </motion.text>
          <text
            x={x + bw / 2}
            y={base + 20}
            textAnchor="middle"
            fontSize="12.5"
            fontWeight="600"
            fill="var(--muted)"
          >
            {s.step}
          </text>
        </g>
      ))}
    </svg>
  );
}
