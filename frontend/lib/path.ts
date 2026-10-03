// Arc-length sampling of the simple SVG paths in routes.json (M, C and S commands only),
// so the map can place toll pins and move the truck by fraction of the route.

type Pt = [number, number];

export type SampledPath = { pts: Pt[]; lens: number[]; total: number };

function cubic(a: Pt, b: Pt, c: Pt, d: Pt, t: number): Pt {
  const u = 1 - t;
  return [
    u * u * u * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t * t * t * d[0],
    u * u * u * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t * t * t * d[1],
  ];
}

export function samplePath(d: string, perSegment = 80): SampledPath {
  const tokens = d.match(/[MCS]|-?\d*\.?\d+/g) ?? [];
  const pts: Pt[] = [];
  let cur: Pt = [0, 0];
  let lastCtrl: Pt | null = null;
  let cmd = "M";
  let i = 0;
  const num = () => Number(tokens[i++]);
  while (i < tokens.length) {
    if (/[MCS]/.test(tokens[i])) cmd = tokens[i++];
    if (cmd === "M") {
      cur = [num(), num()];
      pts.push(cur);
      lastCtrl = null;
    } else {
      const c1: Pt =
        cmd === "C"
          ? [num(), num()]
          : lastCtrl
            ? [2 * cur[0] - lastCtrl[0], 2 * cur[1] - lastCtrl[1]]
            : cur;
      const c2: Pt = [num(), num()];
      const end: Pt = [num(), num()];
      for (let s = 1; s <= perSegment; s++) pts.push(cubic(cur, c1, c2, end, s / perSegment));
      lastCtrl = c2;
      cur = end;
    }
  }
  const lens = [0];
  for (let k = 1; k < pts.length; k++) {
    lens.push(lens[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
  }
  return { pts, lens, total: lens[lens.length - 1] };
}

/** Point and heading (degrees) at a fraction of the path's length. */
export function pointAt(p: SampledPath, frac: number): { x: number; y: number; angle: number } {
  const target = Math.min(Math.max(frac, 0), 1) * p.total;
  let lo = 0;
  let hi = p.lens.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (p.lens[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  const k = Math.max(1, lo);
  const [x0, y0] = p.pts[k - 1];
  const [x1, y1] = p.pts[k];
  const seg = p.lens[k] - p.lens[k - 1] || 1;
  const t = (target - p.lens[k - 1]) / seg;
  return {
    x: x0 + (x1 - x0) * t,
    y: y0 + (y1 - y0) * t,
    angle: (Math.atan2(y1 - y0, x1 - x0) * 180) / Math.PI,
  };
}
