"use client";

import { motion } from "motion/react";

/** Observed first-digit shares (bars) against Benford's expected curve (dashed line). */
export function BenfordChart({ observed, expected }: { observed: number[]; expected: number[] }) {
  const W = 520;
  const H = 190;
  const top = 14;
  const base = H - 26;
  const max = Math.max(...observed, ...expected, 0.01);
  const y = (v: number) => base - (v / max) * (base - top);
  const step = W / 9;
  const bw = step * 0.56;
  const cx = (i: number) => step * i + step / 2;
  const line = expected
    .map((e, i) => `${i ? "L" : "M"}${cx(i).toFixed(1)} ${y(e).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="Benford chart"
    >
      <line x1="0" x2={W} y1={base} y2={base} stroke="var(--line)" strokeWidth="1.5" />
      {observed.map((o, i) => (
        <g key={i}>
          <motion.rect
            x={cx(i) - bw / 2}
            width={bw}
            rx="4"
            fill="var(--warn)"
            initial={{ y: base, height: 0 }}
            animate={{ y: y(o), height: base - y(o) }}
            transition={{ delay: 0.2 + i * 0.07, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          />
          <text
            x={cx(i)}
            y={base + 17}
            textAnchor="middle"
            fontSize="12"
            fontWeight="700"
            fill="var(--muted)"
            fontFamily="var(--font-jetbrains-mono)"
          >
            {i + 1}
          </text>
        </g>
      ))}
      <motion.path
        d={line}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="2"
        strokeDasharray="5 5"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ delay: 0.9, duration: 0.9 }}
      />
      {expected.map((e, i) => (
        <motion.circle
          key={i}
          cx={cx(i)}
          cy={y(e)}
          r="3.6"
          fill="var(--ink)"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1 + i * 0.08 }}
        />
      ))}
    </svg>
  );
}
