import { clamp, fbm2, noise2, smoothstep } from '../util/math';

/** World is Y-up, metres. +X east, +Z south (toward the default camera). */
export const PLOT = 1.2;
export const COLS = 10;
export const ROWS = 8;
export const FIELD = {
  x0: -3,
  z0: -1.8,
  w: COLS * PLOT,
  d: ROWS * PLOT,
};
export const FIELD_CX = FIELD.x0 + FIELD.w / 2;
export const FIELD_CZ = FIELD.z0 + FIELD.d / 2;

const FENCE_PAD = 1.05;
export const FENCE = {
  x0: FIELD.x0 - FENCE_PAD,
  x1: FIELD.x0 + FIELD.w + FENCE_PAD,
  z0: FIELD.z0 - FENCE_PAD,
  z1: FIELD.z0 + FIELD.d + FENCE_PAD,
};
/** Gate sits in the west fence line. */
export const GATE = { x: FENCE.x0, z: 1.35, width: 2.4 };

export const COTTAGE = { x: -13.2, z: -9.6, rot: 0.5, halfW: 3.6, halfD: 3.0 };
export const WELL = { x: -5.6, z: -10.4, r: 0.95 };
export const POND = { x: 14.2, z: -11.2, r: 5.4, level: -0.3, depth: 1.35 };
export const DOCK = { x: 9.35, z: -8.6, rot: -1.05 };

export const SPAWN = { x: -8.6, z: 6.6, yaw: -0.35 };

/** Building plots (centre, facing angle about +Y where the model's front +Z points, half size). */
export const SITES = {
  windmill: { x: 22.5, z: -0.5, rot: -Math.PI / 2, half: 3.0 },
  henhouse: { x: 3.6, z: 13.4, rot: Math.PI, half: 3.4 },
  bakehouse: { x: -19.6, z: -2.4, rot: 1.28, half: 3.1 },
} as const;

/** The royal requisition corner by the road. */
export const ROYAL = {
  board: { x: -11.9, z: 4.5, rot: 0.69 },
  banner: { x: -10.6, z: 3.3 },
  courier: { x: -13.3, z: 7.1, rot: 0.55 },
  wagon: { x: -18.6, z: 13.6, rot: -1.08 },
  milestone: { x: -25.2, z: 16.9, rot: -2.64 },
};

/** The castle on the far hill, at the end of the road. */
export const CASTLE = { x: -236, z: 132, rot: 0.95, hillR: 70, top: 44, scale: 1.4 };

/** Region covered by the splat mask texture. */
export const MASK = { min: -64, size: 128, res: 512 };

// ---------------------------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------------------------
type P2 = [number, number];

function catmull(points: P2[], perSeg = 10): P2[] {
  const out: P2[] = [];
  const n = points.length;
  for (let i = 0; i < n - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)]!;
    const p1 = points[i]!;
    const p2 = points[i + 1]!;
    const p3 = points[Math.min(i + 2, n - 1)]!;
    for (let s = 0; s < perSeg; s++) {
      const t = s / perSeg;
      const t2 = t * t;
      const t3 = t2 * t;
      out.push([
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
      ]);
    }
  }
  out.push(points[n - 1]!);
  return out;
}

/** Door position in world space (cottage front is local +Z, door left of centre). */
export const DOOR: P2 = (() => {
  const lx = -1.7;
  const lz = 4.2;
  const c = Math.cos(COTTAGE.rot);
  const s = Math.sin(COTTAGE.rot);
  return [COTTAGE.x + lx * c + lz * s, COTTAGE.z - lx * s + lz * c] as P2;
})();

interface PathDef {
  pts: P2[];
  width: number;
}
const PATHS: PathDef[] = [
  // door -> gate
  { pts: catmull([DOOR, [-10.2, -3.6], [-8.2, -0.2], [-6.4, 1.3], [GATE.x - 0.2, GATE.z]]), width: 0.85 },
  // junction -> off to the south-west
  { pts: catmull([[-7.6, 0.6], [-9.6, 4.6], [-14.5, 9.5], [-22, 13.5], [-32, 15.5], [-46, 21], [-60, 30]]), width: 1.15 },
  // door -> well
  { pts: catmull([[-10.4, -4.4], [-8.6, -7.4], [WELL.x - 1.3, WELL.z + 0.6]]), width: 0.6 },
  // well -> dock
  { pts: catmull([[WELL.x + 1.2, WELL.z + 0.5], [-0.5, -8.6], [4.5, -7.2], [DOCK.x - 0.4, DOCK.z + 0.25]]), width: 0.55 },
];

function distToPolyline(x: number, z: number, pts: P2[]): number {
  let best = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i]!;
    const b = pts[i + 1]!;
    const dx = b[0] - a[0];
    const dz = b[1] - a[1];
    const l2 = dx * dx + dz * dz;
    const t = l2 > 0 ? clamp(((x - a[0]) * dx + (z - a[1]) * dz) / l2, 0, 1) : 0;
    const px = a[0] + dx * t - x;
    const pz = a[1] + dz * t - z;
    const d = px * px + pz * pz;
    if (d < best) best = d;
  }
  return Math.sqrt(best);
}

/** 0..1 path coverage (soft edge, noisy outline). */
export function pathMask(x: number, z: number): number {
  let m = 0;
  const wob = (fbm2(x * 0.9, z * 0.9, 2) - 0.5) * 0.5;
  for (const p of PATHS) {
    const d = distToPolyline(x, z, p.pts) + wob;
    m = Math.max(m, 1 - smoothstep(p.width - 0.3, p.width + 0.45, d));
  }
  // fade the long path out toward the mask border
  const edge = Math.max(Math.abs(x), Math.abs(z));
  return m * (1 - smoothstep(48, 60, edge));
}

// ---------------------------------------------------------------------------------------------
// Pond
// ---------------------------------------------------------------------------------------------
/** Signed distance to the pond shoreline (negative inside the water). */
export function pondSdf(x: number, z: number): number {
  const dx = x - POND.x;
  const dz = z - POND.z;
  const a = Math.atan2(dz, dx);
  const r = POND.r * (1 + 0.13 * Math.sin(a * 2 + 0.7) + 0.08 * Math.sin(a * 3 + 2.1) + 0.04 * Math.sin(a * 5 + 4.0));
  return Math.hypot(dx, dz) - r;
}

// ---------------------------------------------------------------------------------------------
// Footprints
// ---------------------------------------------------------------------------------------------
function rectSdf(x: number, z: number, cx: number, cz: number, hw: number, hd: number, rot = 0): number {
  const c = Math.cos(rot);
  const s = Math.sin(rot);
  const dx = x - cx;
  const dz = z - cz;
  const lx = Math.abs(dx * c - dz * s) - hw;
  const lz = Math.abs(dx * s + dz * c) - hd;
  return Math.hypot(Math.max(lx, 0), Math.max(lz, 0)) + Math.min(Math.max(lx, lz), 0);
}
export function cottageSdf(x: number, z: number): number {
  return rectSdf(x, z, COTTAGE.x, COTTAGE.z, COTTAGE.halfW, COTTAGE.halfD, COTTAGE.rot);
}
export function fieldSdf(x: number, z: number): number {
  return rectSdf(x, z, FIELD_CX, FIELD_CZ, FIELD.w / 2, FIELD.d / 2);
}

// ---------------------------------------------------------------------------------------------
// Height
// ---------------------------------------------------------------------------------------------
function terrainHeight0(x: number, z: number): number {
  const r = Math.hypot(x, z);
  const roll = smoothstep(22, 62, r);
  return (fbm2(x * 0.021 + 3.1, z * 0.021 - 1.7, 4) - 0.5) * 7.5 * roll;
}

export function terrainHeight(x: number, z: number): number {
  const r = Math.hypot(x, z);
  const roll = smoothstep(22, 62, r);
  let h = (fbm2(x * 0.021 + 3.1, z * 0.021 - 1.7, 4) - 0.5) * 7.5 * roll;
  // distant ring of hills
  const far = smoothstep(75, 190, r);
  // a broad valley opens along the road so the castle stands clear on the skyline
  const cl = Math.hypot(CASTLE.x, CASTLE.z);
  const along = (x * CASTLE.x + z * CASTLE.z) / cl;
  const perp = Math.abs(x * CASTLE.z - z * CASTLE.x) / cl;
  const valley = (1 - smoothstep(22, 75, perp)) * smoothstep(40, 90, along) * (1 - smoothstep(cl - 70, cl - 30, along));
  h += far * (7 + 26 * fbm2(x * 0.0058 + 11.0, z * 0.0058 + 4.0, 4)) * (1 - 0.72 * valley);
  h += far * far * 10 * (1 - 0.6 * valley);
  // tiny undulation near home, kept away from the flat working areas
  const flat = smoothstep(0.5, 4.0, Math.min(fieldSdf(x, z), cottageSdf(x, z)));
  h += (noise2(x * 0.16 + 40, z * 0.16) - 0.5) * 0.22 * flat * (1 - roll);
  // the castle hill: a broad mound with a flat crown
  {
    const d = Math.hypot(x - CASTLE.x, z - CASTLE.z);
    const mound = 1 - smoothstep(CASTLE.hillR * 0.35, CASTLE.hillR * 2.4, d);
    const crown = 1 - smoothstep(CASTLE.hillR * 0.42, CASTLE.hillR * 0.62, d);
    const base = h;
    h = base + mound * mound * (CASTLE.top - base * 0.6);
    h = h + (CASTLE.top + 0.5 - h) * crown;
  }
  // level pads under the building plots
  for (const k in SITES) {
    const s = SITES[k as keyof typeof SITES];
    const sd = rectSdf(x, z, s.x, s.z, s.half, s.half, s.rot);
    const w = 1 - smoothstep(0.0, 3.5, sd);
    h = h + (terrainHeight0(s.x, s.z) - h) * w;
  }
  // pond basin
  const sd = pondSdf(x, z);
  const basin = smoothstep(1.4, -2.6, sd);
  h -= basin * basin * (POND.depth + 0.25) + smoothstep(2.8, 0.2, sd) * 0.06;
  return h;
}

export function terrainNormal(x: number, z: number, out: [number, number, number]): void {
  const e = 0.35;
  const hx = terrainHeight(x + e, z) - terrainHeight(x - e, z);
  const hz = terrainHeight(x, z + e) - terrainHeight(x, z - e);
  const nx = -hx;
  const ny = 2 * e;
  const nz = -hz;
  const l = Math.hypot(nx, ny, nz);
  out[0] = nx / l;
  out[1] = ny / l;
  out[2] = nz / l;
}

// ---------------------------------------------------------------------------------------------
// Ground cover masks
// ---------------------------------------------------------------------------------------------
export interface GroundMask {
  dirt: number;
  path: number;
  shore: number;
}

const WORN: [number, number, number][] = [
  [DOOR[0], DOOR[1], 2.0],
  [WELL.x, WELL.z, 2.1],
  [GATE.x - 0.4, GATE.z, 1.9],
  [-9.3, -5.2, 1.5],
];

export function groundMask(x: number, z: number, out: GroundMask): GroundMask {
  const n = fbm2(x * 0.55 + 7, z * 0.55 - 3, 3) - 0.5;
  // field bed: bare earth a little beyond the plots
  let dirt = 1 - smoothstep(0.25, 0.95, fieldSdf(x, z) + n * 0.5);
  for (const w of WORN) {
    const d = Math.hypot(x - w[0], z - w[1]);
    dirt = Math.max(dirt, (1 - smoothstep(w[2] * 0.35, w[2], d + n * 0.9)) * 0.9);
  }
  // cleared earth on the building plots
  for (const k in SITES) {
    const s = SITES[k as keyof typeof SITES];
    dirt = Math.max(dirt, (1 - smoothstep(-0.6, 0.4, rectSdf(x, z, s.x, s.z, s.half - 0.4, s.half - 0.4, s.rot) + n * 0.8)) * 0.9);
  }
  // trodden ground by the requisition board
  dirt = Math.max(dirt, (1 - smoothstep(0.6, 2.2, Math.hypot(x - ROYAL.board.x - 0.9, z - ROYAL.board.z - 1.1) + n * 0.9)) * 0.85);
  // around the cottage walls
  dirt = Math.max(dirt, (1 - smoothstep(0.1, 0.9, cottageSdf(x, z) + n * 0.5)) * 0.85);
  out.dirt = dirt;
  out.path = pathMask(x, z);
  const sd = pondSdf(x, z);
  out.shore = 1 - smoothstep(-0.1, 1.15, sd + n * 0.7);
  return out;
}

const _gm: GroundMask = { dirt: 0, path: 0, shore: 0 };

/** 0..1 how much grass may grow here (0 on paths, soil, water, under buildings). */
export function grassDensity(x: number, z: number): number {
  groundMask(x, z, _gm);
  let g = 1 - Math.max(smoothstep(0.15, 0.55, _gm.dirt), smoothstep(0.1, 0.5, _gm.path), smoothstep(0.25, 0.7, _gm.shore));
  if (cottageSdf(x, z) < 0.25) g = 0;
  if (Math.hypot(x - WELL.x, z - WELL.z) < WELL.r + 0.25) g = 0;
  return g;
}

/** 0 = short tidy grass near home, 1 = tall meadow. */
export function meadowness(x: number, z: number): number {
  const r = Math.hypot(x - 2, z - 0);
  const wild = fbm2(x * 0.045 + 30, z * 0.045 + 12, 3);
  return clamp(smoothstep(14, 34, r) * 0.75 + (wild - 0.42) * 1.3, 0, 1);
}

// ---------------------------------------------------------------------------------------------
// Colliders
// ---------------------------------------------------------------------------------------------
export interface Circle {
  x: number;
  z: number;
  r: number;
}
export interface Segment {
  ax: number;
  az: number;
  bx: number;
  bz: number;
  r: number;
}
export interface Colliders {
  circles: Circle[];
  segments: Segment[];
}

export function plotCenter(col: number, row: number): [number, number] {
  return [FIELD.x0 + (col + 0.5) * PLOT, FIELD.z0 + (row + 0.5) * PLOT];
}
export function plotAt(x: number, z: number): [number, number] | null {
  const c = Math.floor((x - FIELD.x0) / PLOT);
  const r = Math.floor((z - FIELD.z0) / PLOT);
  if (c < 0 || r < 0 || c >= COLS || r >= ROWS) return null;
  return [c, r];
}
