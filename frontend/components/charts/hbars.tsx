"use client";

import { motion } from "motion/react";

export type HBar = {
  key: string;
  label: string;
  value: number;
  color: string;
  onClick?: () => void;
};

/** Horizontal bars that grow in sequence; widths are relative to the largest value. */
export function HBars({
  bars,
  valueFormat = String,
}: {
  bars: HBar[];
  valueFormat?: (n: number) => string;
}) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <ul className="space-y-3">
      {bars.map((b, i) => (
        <li key={b.key}>
          <button
            type="button"
            onClick={b.onClick}
            disabled={!b.onClick}
            className="group grid w-full grid-cols-[96px_1fr_40px] items-center gap-3 text-left"
          >
            <span className="truncate text-[13px] font-medium text-ink group-enabled:group-hover:underline">
              {b.label}
            </span>
            <span className="h-[18px] overflow-hidden rounded-full bg-peach">
              <motion.span
                className="block h-full rounded-full"
                style={{ background: b.color }}
                initial={{ width: 0 }}
                animate={{ width: `${(b.value / max) * 100}%` }}
                transition={{ duration: 0.6, delay: 0.25 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
              />
            </span>
            <span className="text-right font-mono text-[13px] font-semibold text-ink tabular">
              {valueFormat(b.value)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
