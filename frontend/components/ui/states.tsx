import { AlertTriangle, Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-peach/80", className)} />;
}

/** Placeholder blocks shaped like the screen while data loads. */
export function LoadingBlocks({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-3 gap-4 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-48" />
      ))}
    </div>
  );
}

export function ErrorState({ error, children }: { error: unknown; children?: ReactNode }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="card halftone flex flex-col items-start gap-3 p-8">
      <div className="flex items-center gap-2 font-heading text-lg font-bold text-bad">
        <AlertTriangle size={20} /> That didn&apos;t load.
      </div>
      <p className="text-[14px] text-muted">{message}</p>
      {children}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <Inbox className="text-muted" size={28} />
      <div className="font-heading text-[15px] font-bold text-ink">{title}</div>
      {children && <div className="max-w-sm text-[13px] text-muted">{children}</div>}
    </div>
  );
}
