"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";

import { CountUp } from "@/components/ui/count-up";
import type { CreditGraph, GraphEdge, GraphNode, SupplierRisk } from "@/lib/api";
import { lakh } from "@/lib/format";

type P = { x: number; y: number };

const YOU: P = { x: 720, y: 300 };
const AT_RISK: P[] = [
  { x: 520, y: 220 },
  { x: 470, y: 330 },
];
// Clean suppliers, busiest (most upstream sellers shown) first, each with seats for its sellers.
const SUPPLIER_SLOTS: { at: P; feeders: P[] }[] = [
  {
    at: { x: 540, y: 390 },
    feeders: [
      { x: 390, y: 470 },
      { x: 430, y: 555 },
    ],
  },
  {
    at: { x: 590, y: 110 },
    feeders: [
      { x: 440, y: 60 },
      { x: 470, y: 150 },
    ],
  },
  {
    at: { x: 620, y: 480 },
    feeders: [
      { x: 520, y: 560 },
      { x: 700, y: 560 },
    ],
  },
];
const RING_C: P = { x: 240, y: 200 };
const RING_R = 110;

// Stages of the on-enter sequence.
const STAGE_MS = [0, 1300, 2300, 2900, 3700, 4500, 5300, 6100];

function ringPos(i: number, n: number): P {
  const a = ((-90 + (i * 360) / n) * Math.PI) / 180;
  return { x: RING_C.x + RING_R * Math.cos(a), y: RING_C.y + RING_R * Math.sin(a) };
}

function scatter(i: number): P {
  const seeds = [
    [-150, -70],
    [120, -110],
    [150, 90],
    [-60, 150],
    [-170, 60],
    [60, 40],
  ];
  const [dx, dy] = seeds[i % seeds.length];
  return { x: RING_C.x + dx, y: RING_C.y + dy };
}

function radius(n: GraphNode): number {
  if (n.slot === "you") return 38;
  if (n.slot === "at_risk") return 26;
  if (n.slot === "ring") return 17;
  return n.slot === "supplier" ? 18 : 14;
}

function shortSignal(text: string): string | null {
  if (text.startsWith("Registered")) return text;
  if (text.startsWith("Zero e-way")) return "Zero e-way bills";
  if (text.startsWith("Turnover")) return text;
  return null;
}

/** A gentle curve from a to b, trimmed so it starts and ends at the node rims. */
function curve(a: P, ra: number, b: P, rb: number, bend: number, away?: P): string {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  let nx = -(b.y - a.y);
  let ny = b.x - a.x;
  const len = Math.hypot(nx, ny) || 1;
  nx /= len;
  ny /= len;
  if (away) {
    // bend outwards, away from a centre (ring edges hug the circle)
    const ox = mx - away.x;
    const oy = my - away.y;
    if (ox * nx + oy * ny < 0) {
      nx = -nx;
      ny = -ny;
    }
  }
  const dist = Math.hypot(b.x - a.x, b.y - a.y);
  const cx = mx + nx * bend * dist;
  const cy = my + ny * bend * dist;
  const trim = (from: P, r: number) => {
    const dx = cx - from.x;
    const dy = cy - from.y;
    const d = Math.hypot(dx, dy) || 1;
    return { x: from.x + (dx / d) * r, y: from.y + (dy / d) * r };
  };
  const s = trim(a, ra + 2);
  const e = trim(b, rb + 7);
  return `M${s.x.toFixed(1)} ${s.y.toFixed(1)} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${e.x.toFixed(1)} ${e.y.toFixed(1)}`;
}

function layout(graph: CreditGraph): Map<string, P> {
  const pos = new Map<string, P>();
  const nodes = graph.nodes;
  for (const n of nodes) if (n.slot === "you") pos.set(n.gstin, YOU);
  nodes
    .filter((n) => n.slot === "at_risk")
    .forEach((n, i) => pos.set(n.gstin, AT_RISK[i % AT_RISK.length]));

  const feedersOf = (g: string) => nodes.filter((n) => n.slot === "upstream" && n.feeds === g);
  const suppliers = nodes
    .filter((n) => n.slot === "supplier")
    .sort(
      (a, b) =>
        feedersOf(b.gstin).length - feedersOf(a.gstin).length || a.name.localeCompare(b.name),
    );
  suppliers.slice(0, SUPPLIER_SLOTS.length).forEach((s, i) => {
    const slot = SUPPLIER_SLOTS[i];
    pos.set(s.gstin, slot.at);
    feedersOf(s.gstin).forEach((f, j) => pos.set(f.gstin, slot.feeders[j % slot.feeders.length]));
  });

  // Rings: the member that feeds the at-risk supplier sits lower right, nearest to it.
  const focus = graph.focus;
  graph.cycles.slice(0, 1).forEach((cycle) => {
    const feeder = cycle.findIndex((g) =>
      graph.edges.some((e) => e.seller === g && e.buyer === focus),
    );
    const shift = feeder >= 0 ? (feeder - 2 + cycle.length) % cycle.length : 0;
    const ordered = [...cycle.slice(shift), ...cycle.slice(0, shift)];
    ordered.forEach((g, i) => pos.set(g, ringPos(i, ordered.length)));
  });
  // Anything else on the ring → supplier chain sits between the two.
  nodes
    .filter((n) => !pos.has(n.gstin))
    .forEach((n, i) => pos.set(n.gstin, { x: 400 + i * 30, y: 230 + i * 40 }));
  return pos;
}

export function RingGraph({
  graph,
  supplier,
  runKey,
  onFocusClick,
}: {
  graph: CreditGraph;
  supplier: SupplierRisk | null;
  runKey: number;
  onFocusClick: () => void;
}) {
  const [stage, setStage] = useState<{ run: number; n: number }>({ run: -1, n: 0 });
  const s = stage.run === runKey ? stage.n : 0;

  useEffect(() => {
    const timers = STAGE_MS.map((ms, i) =>
      window.setTimeout(() => setStage({ run: runKey, n: i + 1 }), ms),
    );
    const click = window.setTimeout(onFocusClick, STAGE_MS[1] + 500);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      window.clearTimeout(click);
    };
    // onFocusClick is a parent callback; one sequence per run key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  const pos = useMemo(() => layout(graph), [graph]);
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.gstin, n])), [graph.nodes]);
  const ringSet = useMemo(() => new Set(graph.cycles.flat()), [graph.cycles]);
  const you = graph.nodes.find((n) => n.slot === "you");
  const focus = graph.focus ? byId.get(graph.focus) : undefined;
  const feeder = graph.edges.find((e) => e.buyer === graph.focus && ringSet.has(e.seller));

  const visible = (n: GraphNode) => {
    if (n.slot === "you" || n.slot === "supplier" || n.slot === "at_risk") return s >= 1;
    if (n.slot === "upstream") return s >= 3;
    return s >= 4; // ring
  };
  const edgeKind = (e: GraphEdge): "ring" | "feeder" | "risk" | "plain" => {
    if (ringSet.has(e.seller) && ringSet.has(e.buyer)) return "ring";
    if (feeder && e.seller === feeder.seller && e.buyer === feeder.buyer) return "feeder";
    if (e.seller === graph.focus && you && e.buyer === you.gstin) return "risk";
    return "plain";
  };

  const badges = useMemo(() => {
    const out: { gstin: string; text: string }[] = [];
    for (const g of graph.cycles[0] ?? []) {
      const n = byId.get(g);
      const text = n?.signals.map(shortSignal).find(Boolean);
      if (text && out.length < 3) out.push({ gstin: g, text });
    }
    return out;
  }, [graph.cycles, byId]);

  const pendingCount = supplier?.invoices.filter((i) => i.ims_decision === "Pending").length ?? 0;

  return (
    <div className="relative">
      <svg
        viewBox="0 0 860 600"
        className="block h-auto w-full"
        role="img"
        aria-label="Supplier graph"
      >
        <defs>
          <pattern id="cgrid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0H0V20" fill="none" stroke="var(--line)" strokeWidth="0.6" />
          </pattern>
          <marker
            id="arrow-red"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10 z" fill="var(--bad)" />
          </marker>
          <marker
            id="arrow-grey"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10 z" fill="var(--muted)" />
          </marker>
        </defs>
        <rect width="860" height="600" fill="url(#cgrid)" opacity="0.7" />

        {/* ring outline */}
        {s >= 5 && (
          <motion.circle
            cx={RING_C.x}
            cy={RING_C.y}
            r={RING_R + 34}
            fill="var(--bad)"
            fillOpacity="0.06"
            stroke="var(--bad)"
            strokeOpacity="0.25"
            strokeDasharray="3 6"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            style={{ transformOrigin: `${RING_C.x}px ${RING_C.y}px` }}
          />
        )}

        {/* edges */}
        {graph.edges.map((e) => {
          const a = pos.get(e.seller);
          const b = pos.get(e.buyer);
          const na = byId.get(e.seller);
          const nb = byId.get(e.buyer);
          if (!a || !b || !na || !nb) return null;
          const kind = edgeKind(e);
          const shown =
            kind === "ring" ? s >= 5 : kind === "feeder" ? s >= 5 : visible(na) && visible(nb);
          if (!shown) return null;
          const d = curve(
            a,
            radius(na),
            b,
            radius(nb),
            kind === "ring" ? 0.12 : 0.1,
            kind === "ring" ? RING_C : undefined,
          );
          const red = kind === "ring" || kind === "feeder" || (kind === "risk" && s >= 7);
          return (
            <g key={`${e.seller}-${e.buyer}`}>
              <motion.path
                d={d}
                fill="none"
                stroke={red ? "var(--bad)" : "var(--muted)"}
                strokeOpacity={red ? 0.9 : 0.45}
                strokeWidth={red ? 2.4 : 1.6}
                strokeDasharray={kind === "ring" || kind === "feeder" ? "8 4" : undefined}
                className={kind === "ring" || kind === "feeder" ? "marching" : undefined}
                markerEnd={red ? "url(#arrow-red)" : "url(#arrow-grey)"}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 0.6 }}
              />
              {(kind === "feeder" || kind === "risk") &&
                s >= 7 &&
                [0, 0.55, 1.1].map((delay) => (
                  <circle key={delay} r="4" fill="var(--bad)">
                    <animateMotion
                      dur="1.6s"
                      repeatCount="indefinite"
                      begin={`${delay}s`}
                      path={d}
                    />
                  </circle>
                ))}
            </g>
          );
        })}

        {/* nodes */}
        {graph.nodes.map((n, i) => {
          const p = pos.get(n.gstin);
          if (!p || !visible(n)) return null;
          const r = radius(n);
          const isRing = n.slot === "ring";
          const start = isRing && s < 5 ? scatter(i) : p;
          const fill =
            n.slot === "you"
              ? "#1C130C"
              : n.slot === "at_risk"
                ? "var(--warn)"
                : isRing
                  ? "var(--bad)"
                  : n.slot === "upstream"
                    ? "color-mix(in oklab, var(--ok) 55%, var(--panel))"
                    : "var(--ok)";
          const ringOut = isRing ? Math.atan2(p.y - RING_C.y, p.x - RING_C.x) : 0;
          const lx = isRing ? Math.cos(ringOut) * (r + 14) : 0;
          const ly = isRing ? Math.sin(ringOut) * (r + 14) + 4 : r + 16;
          return (
            <motion.g
              key={n.gstin}
              initial={{ opacity: 0, x: start.x, y: start.y, scale: 0.6 }}
              animate={{
                opacity: 1,
                x: isRing && s < 5 ? start.x : p.x,
                y: isRing && s < 5 ? start.y : p.y,
                scale: 1,
              }}
              transition={{ type: "spring", stiffness: 140, damping: 16 }}
              style={{ cursor: n.slot === "at_risk" ? "pointer" : "default" }}
              onClick={n.slot === "at_risk" ? onFocusClick : undefined}
            >
              {n.slot === "you" && (
                <circle
                  r={r}
                  fill="none"
                  stroke="var(--orange)"
                  strokeWidth="3"
                  className="pulse-ring"
                />
              )}
              <circle
                r={r}
                fill={fill}
                stroke={n.slot === "you" ? "var(--orange)" : "var(--ink)"}
                strokeWidth={n.slot === "you" ? 4 : 2}
              />
              {n.slot === "you" && (
                <text
                  y="8"
                  textAnchor="middle"
                  fontSize="22"
                  fill="#FF8A3D"
                  fontFamily="var(--font-anton)"
                >
                  YOU
                </text>
              )}
              {n.slot === "at_risk" && s >= 6 && (
                <text
                  y="5"
                  textAnchor="middle"
                  fontSize="13"
                  fontWeight="800"
                  fill="#1C130C"
                  fontFamily="var(--font-jetbrains-mono)"
                >
                  {n.risk.toFixed(2)}
                </text>
              )}
              <text
                x={lx}
                y={n.slot === "you" ? r + 18 : ly}
                textAnchor={
                  isRing
                    ? Math.cos(ringOut) > 0.3
                      ? "start"
                      : Math.cos(ringOut) < -0.3
                        ? "end"
                        : "middle"
                    : "middle"
                }
                fontSize={n.slot === "you" ? 12 : 12.5}
                fontWeight="700"
                fill="var(--ink)"
                paintOrder="stroke"
                stroke="var(--panel)"
                strokeWidth="4"
                fontFamily="var(--font-space-grotesk)"
              >
                {n.slot === "you" ? n.name : n.name}
              </text>
            </motion.g>
          );
        })}

        {/* the animated click on the at-risk supplier */}
        {focus && s >= 2 && s < 4 && pos.get(focus.gstin) && (
          <motion.g
            initial={{ x: 790, y: 560, opacity: 0 }}
            animate={{ x: pos.get(focus.gstin)!.x + 6, y: pos.get(focus.gstin)!.y + 8, opacity: 1 }}
            transition={{ duration: 0.8, ease: "easeInOut" }}
          >
            <path
              d="M0 0 L0 22 L6 16 L10 26 L14 24 L10 14 L18 14 Z"
              fill="#fff"
              stroke="#1C130C"
              strokeWidth="1.6"
            />
            <motion.circle
              r="10"
              fill="none"
              stroke="var(--orange)"
              strokeWidth="3"
              initial={{ scale: 0.2, opacity: 0 }}
              animate={{ scale: [0.2, 2.4], opacity: [0, 1, 0] }}
              transition={{ delay: 0.8, duration: 0.6 }}
            />
          </motion.g>
        )}

        {/* signal badges */}
        <AnimatePresence>
          {s >= 6 &&
            badges.map((b, i) => {
              const p = pos.get(b.gstin);
              if (!p) return null;
              const w = b.text.length * 6.6 + 18;
              // Inside the ring, toward its centre: the outside is busy with labels.
              const ang = Math.atan2(p.y - RING_C.y, p.x - RING_C.x);
              const bx = p.x - Math.cos(ang) * 46;
              const by = p.y - Math.sin(ang) * 46;
              return (
                <motion.g
                  key={b.gstin}
                  initial={{ opacity: 0, scale: 0.4 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.25, type: "spring", stiffness: 300, damping: 15 }}
                  style={{ transformOrigin: `${p.x}px ${p.y}px` }}
                >
                  <g transform={`translate(${bx - w / 2} ${by - 11}) rotate(${i % 2 ? 2 : -2})`}>
                    <rect
                      width={w}
                      height="22"
                      rx="11"
                      fill="var(--bad)"
                      stroke="#1C130C"
                      strokeWidth="1.5"
                    />
                    <text
                      x={w / 2}
                      y="15"
                      textAnchor="middle"
                      fontSize="11"
                      fontWeight="700"
                      fill="#fff"
                      fontFamily="var(--font-space-grotesk)"
                    >
                      {b.text}
                    </text>
                  </g>
                </motion.g>
              );
            })}
        </AnimatePresence>
      </svg>

      {/* bottom-left callout */}
      <AnimatePresence>
        {s >= 8 && supplier && supplier.itc_at_risk > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute bottom-4 left-4 w-[260px] rotate-[-1deg] rounded-2xl border-2 border-ink bg-panel px-4 py-3 shadow-[4px_4px_0_var(--ink)] dark:border-bad"
          >
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-bad">
              Your ITC at risk
            </div>
            <div className="font-display text-[34px] leading-none text-bad">
              <CountUp
                value={supplier.itc_at_risk}
                format={(n) => lakh(n).replace(" L", " lakh")}
              />
            </div>
            <div className="mt-1 text-[12.5px] text-ink">
              {supplier.invoices.length} invoices from {supplier.name} · kept{" "}
              <b className="text-warn">Pending</b>
              {pendingCount !== supplier.invoices.length && ` (${pendingCount})`}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
