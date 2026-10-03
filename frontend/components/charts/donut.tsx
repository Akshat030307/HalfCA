"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

export type DonutSlice = { key: string; label: string; value: number; color: string };

/** Animated ring chart; segments draw in one after another. */
export function Donut({
  slices,
  size = 200,
  thickness = 26,
  center,
}: {
  slices: DonutSlice[];
  size?: number;
  thickness?: number;
  center?: ReactNode;
}) {
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const gap = slices.filter((s) => s.value > 0).length > 1 ? 4 : 0;
  // Where each segment starts along the circumference.
  const starts = slices.map((_, i) =>
    slices.slice(0, i).reduce((sum, x) => sum + (x.value / total) * c, 0),
  );
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--peach)"
          strokeWidth={thickness}
        />
        {slices.map((s, i) => {
          const len = Math.max(0, (s.value / total) * c - gap);
          return (
            <motion.circle
              key={s.key}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeLinecap="butt"
              strokeDashoffset={-starts[i]}
              initial={{ strokeDasharray: `0 ${c}` }}
              animate={{ strokeDasharray: `${len} ${c}` }}
              transition={{ duration: 0.7, delay: 0.2 + i * 0.25, ease: [0.16, 1, 0.3, 1] }}
            />
          );
        })}
      </svg>
      {center && (
        <div className="absolute inset-0 grid place-items-center text-center">{center}</div>
      )}
    </div>
  );
}
