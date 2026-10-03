"use client";

import { Clock, FlaskConical } from "lucide-react";

import { Chip } from "@/components/ui/chip";
import { gstr2bDate, useNow } from "@/lib/clock";
import { COMPANY } from "@/lib/company";
import { countdown, period } from "@/lib/format";

export function Topbar() {
  const now = useNow();
  const due = gstr2bDate(COMPANY.period).getTime();
  const left = now === null ? null : due - now;

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-4 border-b-2 border-ink/10 bg-bg/90 px-8 backdrop-blur dark:border-line">
      <div className="grid h-10 w-10 place-items-center rounded-xl border-2 border-ink bg-peach font-heading text-sm font-bold text-ink dark:border-line">
        {COMPANY.initials}
      </div>
      <div className="leading-tight">
        <div className="font-heading text-[15px] font-bold text-ink">{COMPANY.name}</div>
        <div className="text-[12px] text-muted">
          <span className="font-mono">{COMPANY.gstin}</span> · {COMPANY.city}
        </div>
      </div>
      <Chip className="ml-2">Period · {period(COMPANY.period)}</Chip>

      <div className="ml-auto flex items-center gap-2">
        <Chip tone="warn">
          <Clock size={13} />
          {left === null
            ? "GSTR-2B countdown"
            : left > 0
              ? `GSTR-2B in ${countdown(left)}`
              : "GSTR-2B generated"}
        </Chip>
        <Chip>
          <FlaskConical size={13} />
          Synthetic data
        </Chip>
      </div>
    </header>
  );
}
