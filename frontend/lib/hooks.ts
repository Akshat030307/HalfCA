"use client";

import useSWR, { useSWRConfig } from "swr";

import { fetcher } from "./api";

/** GET /api{path} with SWR. Pass null to skip. */
export function useApi<T>(path: string | null) {
  return useSWR<T>(path, fetcher, { revalidateOnFocus: false, keepPreviousData: true });
}

/** Refetch everything (after an upload, reset or approval changes the dataset). */
export function useRefreshAll() {
  const { mutate } = useSWRConfig();
  return () => mutate(() => true);
}
