"use client";

import useSWR from "swr";

import { Chip } from "@/components/ui/chip";

type Health = { ok: boolean; version: string; data_ready: boolean; llm: string | null };

const fetcher = async (url: string): Promise<Health> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status}`);
  return (await res.json()) as Health;
};

/** Small live check that the static site can reach the API (proves the deploy wiring). */
export function ApiStatus() {
  const { data, error, isLoading } = useSWR("/api/health", fetcher, { refreshInterval: 30_000 });

  if (isLoading) return <Chip tone="idle">Checking the backend…</Chip>;
  if (error || !data) return <Chip tone="bad">Backend unreachable</Chip>;
  return (
    <div className="flex flex-wrap gap-2">
      <Chip tone="ok">Backend up · v{data.version}</Chip>
      <Chip tone={data.data_ready ? "ok" : "warn"}>
        {data.data_ready ? "Demo data loaded" : "Demo data not generated yet"}
      </Chip>
      <Chip tone={data.llm ? "ok" : "idle"}>
        {data.llm ? `LLM: ${data.llm}` : "LLM off · templates"}
      </Chip>
    </div>
  );
}
