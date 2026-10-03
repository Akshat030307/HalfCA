"use client";

import { animate } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Goods, Route, Trip, Verdict } from "@/lib/api";
import { cn } from "@/lib/cn";
import { duration } from "@/lib/format";
import { pointAt, samplePath, type SampledPath } from "@/lib/path";

export type BeatPlay = { kind: Verdict; trips: Trip[] };

const LAND =
  "M58 46 C200 8 430 18 610 58 C770 94 846 220 834 362 C822 502 704 584 522 578 C360 572 196 562 108 470 C28 388 18 166 58 46 Z";
const STATE_LINES = [
  "M86 176 C160 154 232 132 272 100 S334 58 352 26",
  "M352 26 C368 120 380 220 394 300 S410 420 424 560",
  "M52 306 C150 316 252 334 332 362 S384 382 396 384",
];
const STATE_LABELS: [string, number, number][] = [
  ["PUNJAB", 92, 74],
  ["HARYANA", 236, 262],
  ["RAJASTHAN", 118, 540],
  ["UTTAR PRADESH", 560, 330],
];
const LABEL_LEFT = new Set(["Lucknow", "Kanpur"]);

function routeFrac(route: Route, city: string | null): number {
  if (!city || route.stops[city] === undefined) return 0;
  return route.stops[city] / route.distance_km;
}

/** A small truck facing right, centred on the origin. Fixed colours so it reads in both themes. */
function TruckShape({ color = "#FF7A1A", ghost = false }: { color?: string; ghost?: boolean }) {
  const ink = ghost ? "#94A3B8" : "#1C130C";
  return (
    <g transform="translate(-17,-10)">
      <rect
        x="0"
        y="2"
        width="21"
        height="13"
        rx="2.5"
        fill={ghost ? "#CBD5E1" : color}
        stroke={ink}
        strokeWidth="1.6"
      />
      <path d="M21 6 h6.5 l4.5 4.5 v4.5 h-11 z" fill={ink} />
      <circle cx="6" cy="16.5" r="2.7" fill={ink} />
      <circle cx="25" cy="16.5" r="2.7" fill={ink} />
    </g>
  );
}

export function RouteMap({
  goods,
  beat,
  runKey,
  onEnd,
  className,
}: {
  goods: Goods;
  beat: BeatPlay | null;
  runKey: number;
  onEnd: () => void;
  className?: string;
}) {
  const sampled = useMemo(() => {
    const out: Record<string, SampledPath> = {};
    for (const r of goods.routes) out[r.id] = samplePath(r.svg_path);
    return out;
  }, [goods.routes]);

  // One pin per plaza, positioned on the first route that lists it.
  const pins = useMemo(() => {
    const seen = new Map<
      string,
      { id: string; name: string; x: number; y: number; route: string }
    >();
    for (const r of goods.routes) {
      for (const p of r.plazas) {
        if (seen.has(p.id)) continue;
        const pt = pointAt(sampled[r.id], p.frac);
        seen.set(p.id, { id: p.id, name: p.name, x: pt.x, y: pt.y, route: r.id });
      }
    }
    return [...seen.values()];
  }, [goods.routes, sampled]);

  const trip = beat?.trips[0] ?? null;
  const route = goods.routes.find((r) => r.id === trip?.route_id) ?? null;
  const failure = beat && beat.kind !== "verified";

  const truckRef = useRef<SVGGElement>(null);
  const tagsRef = useRef<SVGGElement>(null);
  const trailRef = useRef<SVGPathElement>(null);
  const onEndRef = useRef(onEnd);
  useEffect(() => {
    onEndRef.current = onEnd;
  });

  // Per-run overlay state; anything stamped with an older run is ignored.
  const [lit, setLit] = useState<{ run: number; ids: Record<string, "ok" | "bad"> }>({
    run: -1,
    ids: {},
  });
  const [badge, setBadge] = useState<{ run: number; text: string; bad: boolean } | null>(null);
  const [clock, setClock] = useState<{ run: number; minutes: number } | null>(null);
  const [tags, setTags] = useState<{ run: number; n: number }>({ run: -1, n: 0 });

  useEffect(() => {
    if (!beat || !trip || !route) return;
    const path = sampled[route.id];
    const truck = truckRef.current;
    const trail = trailRef.current;
    if (!truck || !trail) return;
    let cancelled = false;
    const stops: (() => void)[] = [];
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const t = window.setTimeout(resolve, ms);
        stops.push(() => window.clearTimeout(t));
      });

    const start = routeFrac(route, trip.from_city);
    const crossed = new Set(trip.crossings.map((c) => c.plaza_id));
    const color =
      beat.kind === "verified" || beat.kind === "recycled_ewb" ? "var(--orange)" : "var(--bad)";
    truck.style.opacity = "0";
    trail.setAttribute("stroke", color);
    trail.setAttribute("stroke-dasharray", "0 1");
    trail.setAttribute("stroke-dashoffset", String(-start));
    trail.style.opacity = "1";

    const place = (f: number) => {
      const p = pointAt(path, f);
      const flip = Math.abs(p.angle) > 90 ? " scale(1,-1)" : "";
      truck.setAttribute("transform", `translate(${p.x} ${p.y}) rotate(${p.angle})${flip}`);
      tagsRef.current?.setAttribute("transform", `translate(${p.x} ${p.y})`);
      trail.setAttribute("stroke-dasharray", `${Math.max(0, f - start)} 2`);
    };

    async function drive(seconds: number, onProgress?: (f: number) => void) {
      truck!.style.opacity = "1";
      const lighting = new Set<string>();
      const controls = animate(start, 1, {
        duration: seconds,
        ease: beat!.kind === "impossible_journey" ? "linear" : [0.45, 0, 0.25, 1],
        onUpdate: (f) => {
          place(f);
          onProgress?.(f);
          for (const plaza of route!.plazas) {
            if (f >= plaza.frac && crossed.has(plaza.id) && !lighting.has(plaza.id)) {
              lighting.add(plaza.id);
              const state = beat!.kind === "impossible_journey" ? "bad" : "ok";
              setLit((prev) => ({
                run: runKey,
                ids: { ...(prev.run === runKey ? prev.ids : {}), [plaza.id]: state },
              }));
            }
          }
        },
      });
      stops.push(() => controls.stop());
      await controls;
    }

    async function play() {
      await wait(350);
      if (beat!.kind === "paper_only") {
        trail!.setAttribute("stroke-dasharray", "0.03 0.02");
        trail!.style.opacity = "0.9";
        await wait(2600);
      } else if (beat!.kind === "impossible_journey") {
        const total = trip!.trip_minutes ?? 0;
        await drive(1.5, (f) =>
          setClock({ run: runKey, minutes: Math.round(total * ((f - start) / (1 - start || 1))) }),
        );
      } else if (beat!.kind === "recycled_ewb") {
        const n = beat!.trips.length;
        await drive(3.6, (f) => {
          const shown = Math.min(n, 1 + Math.floor(((f - start) / (1 - start || 1)) * n * 1.15));
          setTags((prev) =>
            prev.run === runKey && prev.n === shown ? prev : { run: runKey, n: shown },
          );
        });
      } else {
        await drive(3.6);
      }
      if (cancelled) return;
      const t = trip!;
      const text =
        beat!.kind === "verified"
          ? `✓ Goods verified · ${t.tolls_crossed}/${t.plazas_expected} tolls`
          : beat!.kind === "paper_only"
            ? `✕ Paper-only supply · 0 tolls`
            : beat!.kind === "impossible_journey"
              ? "✕ Impossible journey"
              : beat!.kind === "recycled_ewb"
                ? `✕ Recycled e-way bill · 1 trip, ${beat!.trips.length} invoices`
                : "✕ No e-way bill";
      setBadge({ run: runKey, text, bad: beat!.kind !== "verified" });
      await wait(1600);
      if (!cancelled) onEndRef.current();
    }
    void play();
    return () => {
      cancelled = true;
      stops.forEach((s) => s());
    };
    // Each run is one playback; the beat data is fixed for a given run key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  const litNow = lit.run === runKey ? lit.ids : {};
  const showBadge = badge?.run === runKey ? badge : null;
  const showClock = clock?.run === runKey && beat?.kind === "impossible_journey" ? clock : null;
  const tagCount = tags.run === runKey && beat?.kind === "recycled_ewb" ? tags.n : 0;
  const ghost = beat?.kind === "paper_only" && route ? sampled[route.id] : null;
  const activePlazas = new Set(route?.plazas.map((p) => p.id) ?? []);
  const [vw, vh] = goods.view_box;

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox={`0 0 ${vw} ${vh}`}
        className="block h-auto w-full"
        role="img"
        aria-label="Route map"
      >
        <defs>
          <pattern id="dotgrid" width="16" height="16" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1.1" fill="var(--dots)" />
          </pattern>
          <radialGradient id="landglow" cx="45%" cy="45%" r="60%">
            <stop offset="0%" stopColor="var(--land)" stopOpacity="1" />
            <stop offset="100%" stopColor="var(--land)" stopOpacity="0.35" />
          </radialGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={vw} height={vh} fill="url(#dotgrid)" />
        <path d={LAND} fill="url(#landglow)" />
        {STATE_LINES.map((d) => (
          <path
            key={d}
            d={d}
            fill="none"
            stroke="var(--muted)"
            strokeOpacity="0.35"
            strokeWidth="1.2"
            strokeDasharray="5 6"
          />
        ))}
        {STATE_LABELS.map(([t, x, y]) => (
          <text
            key={t}
            x={x}
            y={y}
            fill="var(--muted)"
            fillOpacity="0.55"
            fontSize="13"
            fontWeight="700"
            letterSpacing="7"
            fontFamily="var(--font-space-grotesk)"
          >
            {t}
          </text>
        ))}

        {goods.routes.map((r) => (
          <g key={r.id} opacity={route && route.id !== r.id ? 0.55 : 1}>
            <path
              d={r.svg_path}
              fill="none"
              stroke="var(--road)"
              strokeWidth="10"
              strokeLinecap="round"
            />
            <path
              d={r.svg_path}
              fill="none"
              stroke="var(--road-dash)"
              strokeWidth="1.4"
              strokeDasharray="6 7"
            />
          </g>
        ))}

        {/* The active trip's trail */}
        <path
          key={`trail-${runKey}`}
          ref={trailRef}
          d={route?.svg_path ?? "M0 0"}
          pathLength={1}
          fill="none"
          stroke="var(--orange)"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray="0 1"
          filter={failure ? undefined : "url(#glow)"}
          style={{ opacity: 0 }}
        />

        {pins.map((p) => {
          const state = litNow[p.id];
          const fill =
            state === "ok" ? "var(--ok)" : state === "bad" ? "var(--bad)" : "var(--panel)";
          return (
            <g key={p.id} transform={`translate(${p.x} ${p.y})`}>
              {state && <circle r="13" fill={fill} opacity="0.25" filter="url(#glow)" />}
              <circle r="7" fill={fill} stroke="var(--ink)" strokeWidth="2" />
              {activePlazas.has(p.id) && (
                <text
                  x="11"
                  y="-9"
                  fontSize="10.5"
                  fontWeight="600"
                  fill="var(--ink)"
                  paintOrder="stroke"
                  stroke="var(--bg)"
                  strokeWidth="3"
                >
                  {p.name}
                </text>
              )}
            </g>
          );
        })}

        {goods.cities
          .filter((c) => !c.minor)
          .map((c) => {
            const left = LABEL_LEFT.has(c.name);
            return (
              <g key={c.name} transform={`translate(${c.x} ${c.y})`}>
                <circle
                  r={c.hub ? 6.5 : 4.5}
                  fill={c.hub ? "var(--orange)" : "var(--panel)"}
                  stroke="var(--ink)"
                  strokeWidth="2"
                />
                <text
                  x={left ? -11 : 11}
                  y={left ? -9 : 4}
                  textAnchor={left ? "end" : "start"}
                  fontSize="13"
                  fontWeight="700"
                  fill="var(--ink)"
                  paintOrder="stroke"
                  stroke="var(--bg)"
                  strokeWidth="4"
                  fontFamily="var(--font-space-grotesk)"
                >
                  {c.name}
                </text>
              </g>
            );
          })}

        {ghost && (
          <>
            {[0.03, 0.97].map((f) => {
              const p = pointAt(ghost, f);
              return (
                <g key={f} className="ghost-truck" transform={`translate(${p.x} ${p.y - 16})`}>
                  <TruckShape ghost />
                </g>
              );
            })}
          </>
        )}

        <g ref={truckRef} style={{ opacity: 0 }}>
          <TruckShape />
        </g>
        <g ref={tagsRef}>
          {Array.from({ length: tagCount }, (_, i) => (
            <g key={i} transform={`translate(-26 ${-26 - i * 17})`}>
              <rect
                width="52"
                height="14"
                rx="4"
                fill="var(--panel)"
                stroke="var(--bad)"
                strokeWidth="1.5"
              />
              <text
                x="26"
                y="10.5"
                textAnchor="middle"
                fontSize="9"
                fontWeight="700"
                fill="var(--bad)"
                fontFamily="var(--font-jetbrains-mono)"
              >
                {beat?.trips[i]?.invoice_no}
              </text>
            </g>
          ))}
        </g>
      </svg>

      {/* Fixed overlays */}
      {showBadge && (
        <div
          className={cn(
            "absolute left-4 top-4 rounded-full border-2 px-4 py-1.5 font-heading text-[14px] font-bold shadow-[3px_3px_0_var(--ink)]",
            showBadge.bad ? "border-ink bg-bad text-white" : "border-ink bg-ok text-white",
          )}
        >
          {showBadge.text}
        </div>
      )}
      {showClock && trip && (
        <div className="absolute right-4 top-4 rounded-2xl border-2 border-ink bg-panel px-4 py-2.5 text-right shadow-[3px_3px_0_var(--ink)] dark:border-bad">
          <div className="font-display text-[30px] leading-none text-bad">
            {duration(showClock.minutes)}
          </div>
          <div className="mt-1 font-mono text-[12px] text-ink">
            {trip.distance_km} km · {Math.round(trip.speed_kmh ?? 0)} km/h{" "}
            <span className="text-muted">(limit 80)</span>
          </div>
        </div>
      )}
      <div className="absolute bottom-3 left-4 flex items-center gap-4 rounded-full bg-panel/85 px-3 py-1.5 text-[11.5px] text-muted backdrop-blur">
        <span className="flex items-center gap-1.5">
          <span className="h-1 w-5 rounded-full bg-orange" /> truck trail
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-ink bg-ok" /> toll crossed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-ink bg-panel" /> no crossing
        </span>
      </div>
    </div>
  );
}
