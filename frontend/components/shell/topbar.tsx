"use client";

import { Clock, FlaskConical } from "lucide-react";

import { Chip } from "@/components/ui/chip";
import { gstr2bDate, useNow } from "@/lib/clock";
import { COMPANY } from "@/lib/company";
import { countdown, period } from "@/lib/format";

import { MobileNav } from "./sidebar";

export function Topbar() {
  const now = useNow();
  const due = gstr2bDate(COMPANY.period).getTime();
  const left = now === null ? null : due - now;

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b-2 border-ink/10 bg-bg/90 px-4 backdrop-blur sm:px-6 lg:gap-4 lg:px-8 dark:border-line">
      <MobileNav />
      <div className="hidden min-w-0 items-center gap-3 md:flex lg:gap-4">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border-2 border-ink bg-peach font-heading text-sm font-bold text-ink dark:border-line">
          {COMPANY.initials}
        </div>
        <div className="min-w-0 leading-tight">
          <div className="truncate font-heading text-[15px] font-bold text-ink">{COMPANY.name}</div>
          <div className="truncate text-[12px] text-muted">
            <span className="font-mono">{COMPANY.gstin}</span> · {COMPANY.city}
          </div>
        </div>
        <span className="ml-2 hidden xl:block">
          <Chip>Period · {period(COMPANY.period)}</Chip>
        </span>
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <Chip tone="warn">
          <Clock size={13} />
          {left === null ? (
            "GSTR-2B"
          ) : left > 0 ? (
            <>
              <span className="hidden sm:inline">GSTR-2B in</span>
              <span className="sm:hidden">2B in</span> {countdown(left)}
            </>
          ) : (
            "GSTR-2B generated"
          )}
        </Chip>
        <Chip>
          <FlaskConical size={13} />
          Synthetic<span className="hidden sm:inline"> data</span>
        </Chip>
      </div>
    </header>
  );
}
