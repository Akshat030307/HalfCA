// Mirror of the CSS variables in app/globals.css, for SVG/chart code that needs raw values.
// Components should prefer the Tailwind classes (bg-panel, text-ok, …), which follow the theme.

export const light = {
  bg: "#FFF0E1",
  panel: "#FFF8F0",
  peach: "#FFDCC2",
  line: "#EBCFB8",
  ink: "#1C130C",
  muted: "#7B6352",
  orange: "#F26B1D",
  orangePale: "#FFC59A",
  ok: "#16A34A",
  warn: "#C98A00",
  dup: "#7C3AED",
  idle: "#64748B",
  bad: "#DC2626",
  trace: "#0284C7",
} as const;

export const dark = {
  bg: "#000000",
  panel: "#0D0D0D",
  peach: "#1A1411",
  line: "#2A2420",
  ink: "#FFF4EA",
  muted: "#A8978A",
  orange: "#FF8A3D",
  orangePale: "#3A2212",
  ok: "#22C55E",
  warn: "#FBBF24",
  dup: "#A78BFA",
  idle: "#94A3B8",
  bad: "#F87171",
  trace: "#7DD3FC",
} as const;

export type Palette = { [K in keyof typeof light]: string };

/** CSS-variable references, for inline SVG fills that should follow the theme. */
export const cssVar = {
  bg: "var(--bg)",
  panel: "var(--panel)",
  peach: "var(--peach)",
  line: "var(--line)",
  ink: "var(--ink)",
  muted: "var(--muted)",
  orange: "var(--orange)",
  orangePale: "var(--orange-pale)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  dup: "var(--dup)",
  idle: "var(--idle)",
  bad: "var(--bad)",
  trace: "var(--trace)",
} as const;
