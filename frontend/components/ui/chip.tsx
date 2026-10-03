import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type Tone = "neutral" | "orange" | "ok" | "warn" | "dup" | "idle" | "bad";

const TONES: Record<Tone, string> = {
  neutral: "border-line bg-panel text-ink",
  orange: "border-ink bg-orange text-on-orange dark:border-orange",
  ok: "border-ok/40 bg-ok/10 text-ok",
  warn: "border-warn/40 bg-warn/10 text-warn",
  dup: "border-dup/40 bg-dup/10 text-dup",
  idle: "border-idle/40 bg-idle/10 text-idle",
  bad: "border-bad/40 bg-bad/10 text-bad",
};

export function Chip({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border-[1.5px] px-3 py-1 text-[12px] font-semibold",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
