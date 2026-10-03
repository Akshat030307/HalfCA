"use client";

import { motion } from "motion/react";

/** The "half" badge: a circle split across the middle, with "CA" inverted in each half. */
export function LogoBadge({ size = 44 }: { size?: number }) {
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Half CA"
      whileHover={{ rotate: [0, -14, 10, -4, 0] }}
      transition={{ duration: 0.6 }}
    >
      <defs>
        <clipPath id="halfca-top">
          <rect x="0" y="0" width="64" height="32" />
        </clipPath>
        <clipPath id="halfca-bottom">
          <rect x="0" y="32" width="64" height="32" />
        </clipPath>
      </defs>
      {/* Fixed colours so the badge reads the same in both themes. */}
      <circle cx="32" cy="32" r="29" fill="#FF7A1A" clipPath="url(#halfca-top)" />
      <circle cx="32" cy="32" r="29" fill="#1C130C" clipPath="url(#halfca-bottom)" />
      <g
        fontFamily="var(--font-anton), Impact, sans-serif"
        fontSize="30"
        textAnchor="middle"
        letterSpacing="1"
      >
        <text x="32" y="43" fill="#1C130C" clipPath="url(#halfca-top)">
          CA
        </text>
        <text x="32" y="43" fill="#FF8A3D" clipPath="url(#halfca-bottom)">
          CA
        </text>
      </g>
      <circle cx="32" cy="32" r="29" fill="none" stroke="var(--ink)" strokeWidth="2.5" />
    </motion.svg>
  );
}

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <LogoBadge />
      <div className="leading-none">
        <div className="font-display text-[28px] tracking-wide text-ink">HALF CA</div>
        <div className="mt-1 text-[11px] font-medium text-muted">follows the goods</div>
      </div>
    </div>
  );
}
