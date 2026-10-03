"use client";

import { useSyncExternalStore } from "react";

// A minute-resolution clock shared by every countdown. null during SSR/static render.
function subscribe(onTick: () => void): () => void {
  const id = window.setInterval(onTick, 15_000);
  return () => window.clearInterval(id);
}

const minuteNow = () => Math.floor(Date.now() / 60_000) * 60_000;

export function useNow(): number | null {
  return useSyncExternalStore(subscribe, minuteNow, () => null);
}

/** GSTR-2B for a period (YYYY-MM) generates on the 14th of the next month, 00:00 IST. */
export function gstr2bDate(period: string): Date {
  const [y, m] = period.split("-").map(Number);
  const nextY = m === 12 ? y + 1 : y;
  const nextM = m === 12 ? 1 : m + 1;
  return new Date(`${nextY}-${String(nextM).padStart(2, "0")}-14T00:00:00+05:30`);
}
