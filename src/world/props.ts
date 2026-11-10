import {
  Color,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  PointLight,
  Quaternion,
  Vector3,
  type Material,
  type Object3D,
  type Scene,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { findAllByPrefix, findByPrefix, type Assets } from '../core/assets';
import type { MaterialLib, WindProfile } from '../core/materials';
import { damp, mulberry32, smoothstep } from '../util/math';
import {
  CASTLE,
  COTTAGE,
  DOCK,
  FENCE,
  GATE,
  POND,
  WELL,
  cottageSdf,
  fieldSdf,
  pondSdf,
  terrainHeight,
  type Colliders,
} from './layout';
import { LAYER_REFLECT, LAYER_REFRACT } from './water';

export interface World {
  colliders: Colliders;
  smoke: Vector3;
  update(dt: number, px: number, pz: number, glow: number): void;
  /** Flower clump positions, for butterflies. */
  flowers: Vector3[];
  /** Height of walkable decks at a point, or null. */
  deckAt(x: number, z: number): number | null;
}

const _q = new Quaternion();
const _s = new Vector3();
const _p = new Vector3();
const _y = new Vector3(0, 1, 0);

function setLayers(o: Object3D, reflect: boolean, refract: boolean): void {
  o.traverse((c) => {
    if (reflect) c.layers.enable(LAYER_REFLECT);
    if (refract) c.layers.enable(LAYER_REFRACT);
  });
}

/**
 * Merge every static, non-instanced mesh under `root` into one mesh per material
 * (and per layer / shadow setting), baking world transforms. Cuts hundreds of draw calls.
 */
function batchStatic(root: Group, keep: Object3D | null): void {
  root.updateMatrixWorld(true);
  const groups = new Map<string, Mesh[]>();
  root.traverse((o) => {
    const m = o as Mesh;
    if (!m.isMesh || (m as unknown as InstancedMesh).isInstancedMesh || m.customDepthMaterial) return;
    for (let p: Object3D | null = m; p; p = p.parent) if (p === keep) return;
    const g = m.geometry;
    const sig = Object.keys(g.attributes)
      .sort()
      .map((k) => `${k}${g.attributes[k]!.itemSize}${g.attributes[k]!.array.constructor.name}${g.attributes[k]!.normalized ? 'n' : ''}`)
      .join(',');
    const key = `${(m.material as Material).uuid}|${m.layers.mask}|${m.castShadow ? 1 : 0}${m.receiveShadow ? 1 : 0}|${g.index ? 'i' : 'n'}|${sig}`;
    let list = groups.get(key);
    if (!list) groups.set(key, (list = []));
    list.push(m);
  });
  for (const list of groups.values()) {
    if (list.length < 2) continue;
    const merged = mergeGeometries(
      list.map((m) => m.geometry.clone().applyMatrix4(m.matrixWorld)),
      false,
    );
    if (!merged) continue;
    const first = list[0]!;
    const mesh = new Mesh(merged, first.material);
    mesh.name = `batch_${(first.material as Material).name}`;
    mesh.castShadow = first.castShadow;
    mesh.receiveShadow = first.receiveShadow;
    mesh.layers.mask = first.layers.mask;
    for (const m of list) m.removeFromParent();
    root.add(mesh);
  }
}

/** Keep a clear sightline from the farm road up to the castle. */
function inCastleView(x: number, z: number): boolean {
  const ox = -14;
  const oz = 9;
  const dx = CASTLE.x - ox;
  const dz = CASTLE.z - oz;
  const l = Math.hypot(dx, dz);
  const along = ((x - ox) * dx + (z - oz) * dz) / l;
  const perp = Math.abs((x - ox) * dz - (z - oz) * dx) / l;
  return along > 4 && along < l - 30 && perp < 6 + along * 0.11;
}

export function buildWorld(scene: Scene, assets: Assets, lib: MaterialLib, maskAt: (x: number, z: number, out: Float32Array) => void): World {
  const root = new Group();
  root.name = 'props';
  scene.add(root);
  const colliders: Colliders = { circles: [], segments: [] };
  const rng = mulberry32(4242);
  const mk = new Float32Array(4);

  const place = (
    name: string,
    x: number,
    z: number,
    rot = 0,
    scale = 1,
    o: { wind?: WindProfile; reflect?: boolean; refract?: boolean; y?: number; collide?: number } = {},
  ): Object3D | null => {
    const obj = assets.clone(name);
    if (!obj) return null;
    lib.apply(obj, o.wind ?? 'none');
    obj.position.set(x, o.y ?? terrainHeight(x, z), z);
    obj.rotation.y = rot;
    obj.scale.setScalar(scale);
    root.add(obj);
    obj.updateMatrixWorld(true);
    if (o.reflect || o.refract) setLayers(obj, !!o.reflect, !!o.refract);
    if (o.collide) colliders.circles.push({ x, z, r: o.collide });
    return obj;
  };

  /** One InstancedMesh per primitive of `name`, placed with the given matrices. */
  const scatter = (name: string, mats: Matrix4[], wind: WindProfile = 'none', o: { cast?: boolean; reflect?: boolean; refract?: boolean } = {}): void => {
    const src = assets.node(name);
    if (!src || mats.length === 0) return;
    src.traverse((c) => {
      const m = c as Mesh;
      if (!m.isMesh) return;
      const matName = (m.material as Material).name.replace(/\.\d+$/, '');
      const im = new InstancedMesh(m.geometry, lib.get(matName, wind), mats.length);
      for (let i = 0; i < mats.length; i++) im.setMatrixAt(i, mats[i]!);
      im.instanceMatrix.needsUpdate = true;
      im.castShadow = o.cast ?? true;
      im.receiveShadow = true;
      const depth = lib.depthFor(matName, wind);
      if (depth) im.customDepthMaterial = depth;
      im.computeBoundingSphere();
      im.name = name;
      if (o.reflect) im.layers.enable(LAYER_REFLECT);
      if (o.refract) im.layers.enable(LAYER_REFRACT);
      root.add(im);
    });
  };
  const mat4 = (x: number, y: number, z: number, rot: number, sx: number, sy = sx, sz = sx): Matrix4 => {
    _q.setFromAxisAngle(_y, rot);
    return new Matrix4().compose(_p.set(x, y, z), _q, _s.set(sx, sy, sz));
  };

  // ------------------------------------------------------------------ cottage
  const lights: PointLight[] = [];
  let smoke = new Vector3(COTTAGE.x + 2, 6.5, COTTAGE.z);
  const cottage = place('cottage', COTTAGE.x, COTTAGE.z, COTTAGE.rot, 1, { reflect: true, y: 0 });
  if (cottage) {
    const sm = findByPrefix(cottage, 'smoke_emitter');
    if (sm) smoke = sm.getWorldPosition(new Vector3());
    const addLight = (o: Object3D | null, intensity: number, dist: number, lift = 0): void => {
      if (!o) return;
      const l = new PointLight(new Color(1.0, 0.62, 0.3), 0, dist, 1.8);
      o.getWorldPosition(l.position);
      l.position.y += lift;
      l.userData.base = intensity;
      scene.add(l);
      lights.push(l);
    };
    addLight(findByPrefix(cottage, 'lantern_light'), 9, 9);
    // one soft pool of window light in front of the house instead of a light per pane
    const wins = findAllByPrefix(cottage, 'window_light');
    if (wins.length >= 2) {
      const a = wins[0]!.getWorldPosition(new Vector3());
      const b = wins[1]!.getWorldPosition(new Vector3());
      const l = new PointLight(new Color(1.0, 0.66, 0.34), 0, 10, 1.8);
      l.position.copy(a).add(b).multiplyScalar(0.5);
      const c = Math.cos(COTTAGE.rot);
      const s = Math.sin(COTTAGE.rot);
      l.position.x += s * 1.3;
      l.position.z += c * 1.3;
      l.userData.base = 10;
      scene.add(l);
      lights.push(l);
    }
  }
  // footprint collider (body only, not the roof overhang)
  {
    const hw = 3.35;
    const hd = 2.7;
    const c = Math.cos(COTTAGE.rot);
    const s = Math.sin(COTTAGE.rot);
    const corner = (lx: number, lz: number): [number, number] => [COTTAGE.x + lx * c + lz * s, COTTAGE.z - lx * s + lz * c];
    const cs = [corner(-hw, -hd), corner(hw, -hd), corner(hw, hd), corner(-hw, hd)];
    for (let i = 0; i < 4; i++) {
      const a = cs[i]!;
      const b = cs[(i + 1) % 4]!;
      colliders.segments.push({ ax: a[0], az: a[1], bx: b[0], bz: b[1], r: 0.35 });
    }
    const ch = corner(3.7, -0.9);
    colliders.circles.push({ x: ch[0], z: ch[1], r: 0.75 });
  }

  // ------------------------------------------------------------------ yard
  place('well', WELL.x, WELL.z, -0.5, 1, { collide: 1.05, reflect: true });
  place('trough', -6.7, -4.4, 1.25, 1, { collide: 0.75 });
  const cl = (lx: number, lz: number): [number, number] => {
    const c = Math.cos(COTTAGE.rot);
    const s = Math.sin(COTTAGE.rot);
    return [COTTAGE.x + lx * c + lz * s, COTTAGE.z - lx * s + lz * c];
  };
  let q = cl(3.0, 3.6);
  place('barrel', q[0], q[1], 0.4, 1, { collide: 0.45 });
  q = cl(3.75, 3.35);
  place('barrel', q[0], q[1], 2.1, 0.92, { collide: 0.42 });
  q = cl(2.1, 3.75);
  place('crate', q[0], q[1], 0.2, 1, { collide: 0.45 });
  q = cl(2.2, 3.8);
  place('crate', q[0], q[1], 0.9, 0.8, { y: 0.61 });
  q = cl(1.35, 3.6);
  place('sack', q[0], q[1], 1.4, 1, { collide: 0.3 });
  q = cl(-4.3, 0.6);
  place('woodpile', q[0], q[1], COTTAGE.rot + Math.PI / 2, 1, { collide: 0.7 });
  q = cl(-4.25, -1.2);
  place('bucket', q[0], q[1], 0.7, 1);
  place('bucket', WELL.x + 1.25, WELL.z + 0.85, 2.0, 1);
  place('lantern_post', GATE.x - 0.75, GATE.z - 2.0, Math.PI * 0.5, 1, { collide: 0.2 });
  place('signpost', -9.0, 1.6, -0.9, 1, { collide: 0.18 });
  place('bench', -15.6, 4.3, 1.9, 1, { collide: 0.6 });
  place('hay_bale', FENCE.x1 + 1.5, 6.4, 0.3, 1, { collide: 0.6 });
  place('hay_bale', FENCE.x1 + 2.3, 5.2, 1.2, 1, { collide: 0.6 });
  place('hay_bale', FENCE.x1 + 1.75, 5.85, 0.75, 0.95, { y: 0.6 });
  place('sack', FENCE.x1 + 1.0, 4.4, 0.4, 1);
  place('scarecrow', FENCE.x1 + 0.9, FENCE.z0 - 0.9, -2.2, 1, { collide: 0.25 });
  place('crate', FENCE.x0 - 0.9, 4.2, 0.5, 1, { collide: 0.45 });
  place('bucket', FENCE.x0 - 0.7, 3.3, 1.1, 1);

  // lantern post light
  {
    const l = new PointLight(new Color(1.0, 0.62, 0.3), 0, 8, 1.8);
    l.position.set(GATE.x - 0.75, 1.65, GATE.z - 1.5);
    l.userData.base = 7;
    scene.add(l);
    lights.push(l);
  }

  // ------------------------------------------------------------------ fence + gate
  {
    const posts: Matrix4[] = [];
    const rails: Matrix4[] = [];
    const seen = new Set<string>();
    const post = (x: number, z: number): void => {
      const k = `${x.toFixed(2)},${z.toFixed(2)}`;
      if (seen.has(k)) return;
      seen.add(k);
      posts.push(mat4(x, terrainHeight(x, z) - 0.02, z, rng() * 0.5, 1, 0.92 + rng() * 0.14, 1));
    };
    const line = (ax: number, az: number, bx: number, bz: number): void => {
      const len = Math.hypot(bx - ax, bz - az);
      const n = Math.max(1, Math.round(len / 2.35));
      const rot = Math.atan2(-(bz - az), bx - ax);
      for (let i = 0; i <= n; i++) post(ax + ((bx - ax) * i) / n, az + ((bz - az) * i) / n);
      for (let i = 0; i < n; i++) {
        const mx = ax + ((bx - ax) * (i + 0.5)) / n;
        const mz = az + ((bz - az) * (i + 0.5)) / n;
        const flip = rng() < 0.5 ? Math.PI : 0;
        rails.push(mat4(mx, terrainHeight(mx, mz) + (rng() - 0.5) * 0.03, mz, rot + flip, len / n / 2.4, 1, 1));
      }
      colliders.segments.push({ ax, az, bx, bz, r: 0.16 });
    };
    const g0 = GATE.z - GATE.width / 2;
    const g1 = GATE.z + GATE.width / 2;
    line(FENCE.x0, FENCE.z0, FENCE.x1, FENCE.z0);
    line(FENCE.x1, FENCE.z0, FENCE.x1, FENCE.z1);
    line(FENCE.x1, FENCE.z1, FENCE.x0, FENCE.z1);
    line(FENCE.x0, FENCE.z1, FENCE.x0, g1);
    line(FENCE.x0, g0, FENCE.x0, FENCE.z0);
    scatter('fence_post', posts);
    scatter('fence_rails', rails);
  }
  const gate = place('gate_leaf', GATE.x, GATE.z - GATE.width / 2 + 0.08, -Math.PI / 2, 0.97, { y: 0.02 });
  let gateOpen = 0;

  // ------------------------------------------------------------------ pond dressing
  const dock = place('dock', DOCK.x, DOCK.z, DOCK.rot, 1, { y: 0, reflect: true, refract: true });
  const dockDir = new Vector3(0, 0, 1).applyAxisAngle(_y, DOCK.rot);
  void dock;
  {
    const rocks: [string, number, number, number, number][] = [
      ['rock_c', POND.x + 5.9, POND.z + 2.6, 0.4, 1.0],
      ['rock_b', POND.x + 5.0, POND.z + 4.0, 1.9, 1.0],
      ['rock_a', POND.x + 4.2, POND.z + 4.9, 0.3, 1.3],
      ['rock_b', POND.x - 4.6, POND.z - 4.4, 2.6, 1.15],
      ['rock_a', POND.x - 3.5, POND.z - 5.3, 1.0, 1.5],
      ['rock_c', POND.x + 1.0, POND.z - 6.6, 2.2, 0.85],
      ['rock_a', POND.x - 1.0, POND.z + 5.6, 0.7, 1.2],
      ['rock_b', -17.5, 6.0, 0.2, 0.9],
      ['rock_a', -16.6, 6.7, 1.2, 1.2],
      ['rock_b', 8.6, 17.2, 2.0, 0.8],
      ['rock_a', -2.4, -5.0, 0.4, 1.0],
      ['rock_c', 23, 6, 1.1, 1.2],
      ['rock_b', -25.8, -4.6, 2.3, 1.3],
    ];
    for (const [n, x, z, r, s] of rocks) {
      place(n, x, z, r, s, { reflect: true, refract: true, y: terrainHeight(x, z) - 0.05, collide: n === 'rock_a' ? 0 : 0.45 * s });
    }
    // stepping stones from the path to the dock
    const stones: Matrix4[] = [];
    for (let i = 0; i < 5; i++) {
      const x = DOCK.x - 0.5 - i * 0.72 - dockDir.x * 0.2;
      const z = DOCK.z + 0.5 + i * 0.26 + (i % 2) * 0.12;
      stones.push(mat4(x, terrainHeight(x, z) + 0.005, z, rng() * 6, 0.85 + rng() * 0.3));
    }
    scatter('stepping_stone', stones);

    const reeds: Matrix4[] = [];
    const pads: Matrix4[] = [];
    for (let i = 0; i < 400 && reeds.length < 30; i++) {
      const a = rng() * Math.PI * 2;
      const d = POND.r * (0.75 + rng() * 0.45);
      const x = POND.x + Math.cos(a) * d;
      const z = POND.z + Math.sin(a) * d;
      const sd = pondSdf(x, z);
      if (sd > 0.25 || sd < -0.75) continue;
      // keep the dock approach clear
      if (Math.hypot(x - DOCK.x, z - DOCK.z) < 2.3) continue;
      if (rng() < 0.45) continue;
      reeds.push(mat4(x, Math.max(terrainHeight(x, z), POND.level - 0.25), z, rng() * 6, 0.8 + rng() * 0.5));
    }
    for (let i = 0; i < 200 && pads.length < 8; i++) {
      const a = rng() * Math.PI * 2;
      const d = POND.r * rng() * 0.8;
      const x = POND.x + Math.cos(a) * d;
      const z = POND.z + Math.sin(a) * d;
      if (pondSdf(x, z) > -1.3) continue;
      if (Math.hypot(x - (DOCK.x + dockDir.x * 2.2), z - (DOCK.z + dockDir.z * 2.2)) < 1.6) continue;
      pads.push(mat4(x, POND.level + 0.012, z, rng() * 6, 0.8 + rng() * 0.5));
    }
    scatter('reed_clump', reeds, 'crop', { reflect: true, refract: true });
    scatter('lily_pad', pads, 'none', { cast: false, reflect: true });
  }

  // ------------------------------------------------------------------ trees
  const treeSpots: [string, number, number, number, number][] = [
    ['tree_apple_a', -15.2, 2.6, 0.3, 1.0],
    ['tree_apple_b', -11.6, 9.4, 2.0, 1.05],
    ['tree_apple_a', 14.6, 11.8, 4.0, 0.95],
    ['tree_apple_b', 27.0, 7.0, 1.0, 1.1],
    ['tree_apple_a', -3.4, 14.6, 5.2, 1.05],
    ['tree_apple_b', 5.6, -6.6, 3.3, 0.9],
    ['tree_oak', -22.5, -10.5, 0.6, 1.0],
    ['tree_oak', 24.5, -19.5, 2.2, 1.1],
    ['tree_oak', 22.0, 15.5, 4.1, 0.95],
    ['tree_oak', -22.0, 25.5, 1.4, 1.05],
    ['tree_oak', -8.0, -22.0, 3.0, 1.1],
    ['tree_oak', 6.0, 26.0, 5.0, 1.0],
  ];
  {
    const byKind = new Map<string, Matrix4[]>();
    for (const [n, x, z, r, s] of treeSpots) {
      let list = byKind.get(n);
      if (!list) byKind.set(n, (list = []));
      list.push(mat4(x, terrainHeight(x, z), z, r, s));
      colliders.circles.push({ x, z, r: n === 'tree_oak' ? 0.55 : 0.34 });
    }
    for (const [n, list] of byKind) scatter(n, list, 'tree', { reflect: true });
  }
  // far treeline, clustered into copses along the hills
  {
    const far: Matrix4[] = [];
    const clusters: [number, number][] = [];
    for (let i = 0; i < 64; i++) {
      const a = rng() * Math.PI * 2;
      const d = 58 + rng() * 190;
      clusters.push([Math.cos(a) * d, Math.sin(a) * d]);
    }
    for (const [cx, cz] of clusters) {
      const n = 4 + Math.floor(rng() * 9);
      for (let i = 0; i < n; i++) {
        const a = rng() * Math.PI * 2;
        const d = Math.sqrt(rng()) * (6 + rng() * 12);
        const x = cx + Math.cos(a) * d;
        const z = cz + Math.sin(a) * d;
        if (Math.hypot(x, z) < 46 || Math.hypot(x - CASTLE.x, z - CASTLE.z) < 70) continue;
        if (inCastleView(x, z)) continue;
        const s = 1.0 + rng() * 0.9;
        far.push(mat4(x, terrainHeight(x, z) - 0.15, z, rng() * 6, s, s * (0.9 + rng() * 0.35), s));
      }
    }
    // hedgerows: loose lines of trees that follow the land and give the hills some structure
    for (let i = 0; i < 16; i++) {
      const a = rng() * Math.PI * 2;
      const d = 70 + rng() * 150;
      const dir = a + Math.PI / 2 + (rng() - 0.5) * 1.2;
      const len = 40 + rng() * 70;
      const n = Math.floor(len / 7);
      for (let k = 0; k < n; k++) {
        const t = (k / n - 0.5) * len;
        const x = Math.cos(a) * d + Math.cos(dir) * t + (rng() - 0.5) * 5;
        const z = Math.sin(a) * d + Math.sin(dir) * t + (rng() - 0.5) * 5;
        if (Math.hypot(x, z) < 52 || Math.hypot(x - CASTLE.x, z - CASTLE.z) < 70) continue;
        if (inCastleView(x, z)) continue;
        const s = 0.8 + rng() * 0.7;
        far.push(mat4(x, terrainHeight(x, z) - 0.15, z, rng() * 6, s * (0.9 + rng() * 0.5), s * (0.8 + rng() * 0.5), s * (0.9 + rng() * 0.5)));
      }
    }
    // beyond the shadow range, so they never need to be drawn into the shadow maps
    scatter('tree_far', far, 'tree', { reflect: true, cast: false });
  }

  // ------------------------------------------------------------------ bushes + flowers
  const flowers: Vector3[] = [];
  {
    const bushSpots: [string, number, number, number][] = [
      ['bush_a', FENCE.x1 + 1.3, FENCE.z0 + 1.6, 1.0],
      ['bush_b', FENCE.x1 + 1.5, FENCE.z1 - 0.6, 1.1],
      ['bush_a', FENCE.x0 - 1.3, FENCE.z1 + 0.4, 0.9],
      ['bush_b', FENCE.x0 + 3.5, FENCE.z1 + 1.5, 1.0],
      ['bush_a', -17.2, -6.2, 1.2],
      ['bush_b', -9.3, -14.2, 1.1],
      ['bush_a', -1.2, -12.4, 1.0],
      ['bush_b', 8.2, -16.0, 1.2],
      ['bush_a', 20.4, -6.4, 1.1],
      ['bush_b', 10.0, 15.6, 1.0],
      ['bush_a', -19.0, 9.0, 1.15],
      ['bush_b', 1.0, 17.0, 0.95],
    ];
    const bushes = new Map<string, Matrix4[]>();
    for (const [n, x, z, s] of bushSpots) {
      let list = bushes.get(n);
      if (!list) bushes.set(n, (list = []));
      list.push(mat4(x, terrainHeight(x, z), z, rng() * 6, s));
      colliders.circles.push({ x, z, r: 0.45 * s });
    }
    for (const [n, list] of bushes) scatter(n, list, 'bush');

    const kinds = ['flower_daisy', 'flower_poppy', 'flower_lavender'];
    const lists: Matrix4[][] = [[], [], []];
    for (let i = 0; i < 9000; i++) {
      const x = (rng() - 0.5) * 104;
      const z = (rng() - 0.5) * 104;
      const r = Math.hypot(x, z);
      if (r < 5 || r > 52) continue;
      maskAt(x, z, mk);
      if (mk[0]! > 0.08 || mk[1]! > 0.08 || mk[2]! > 0.1) continue;
      if (cottageSdf(x, z) < 0.6 || fieldSdf(x, z) < 1.4) continue;
      // patches: each kind follows its own low-frequency field
      const k = Math.floor(rng() * 3);
      const fx = x * 0.07 + k * 13.1;
      const fz = z * 0.07 - k * 7.7;
      const field = Math.sin(fx) * Math.cos(fz * 1.3) + Math.sin(fx * 2.3 + fz) * 0.5;
      const want = smoothstep(0.35, 1.1, field) * (0.25 + mk[3]! * 0.75);
      if (rng() > want) continue;
      const s = 0.8 + rng() * 0.6;
      lists[k]!.push(mat4(x, terrainHeight(x, z), z, rng() * 6, s));
      if (flowers.length < 60 && r < 30 && rng() < 0.15) flowers.push(new Vector3(x, terrainHeight(x, z) + 0.35, z));
    }
    for (let k = 0; k < 3; k++) scatter(kinds[k]!, lists[k]!, 'flower', { cast: false });
  }

  // pond: keep the walker out of deep water except along the dock
  const dockLen = 2.6;
  const deckAt = (x: number, z: number): number | null => {
    const dx = x - DOCK.x;
    const dz = z - DOCK.z;
    const along = dx * dockDir.x + dz * dockDir.z;
    const side = dx * dockDir.z - dz * dockDir.x;
    if (along > -0.2 && along < dockLen && Math.abs(side) < 0.6) return 0.35;
    return null;
  };

  batchStatic(root, gate);

  return {
    colliders,
    smoke,
    flowers,
    deckAt,
    update(dt, px, pz, glow) {
      if (gate) {
        const near = Math.hypot(px - GATE.x, pz - GATE.z) < 3.4 ? 1 : 0;
        gateOpen = damp(gateOpen, near, 4.5, dt);
        gate.rotation.y = -Math.PI / 2 - gateOpen * 1.75;
      }
      for (const l of lights) l.intensity = (l.userData.base as number) * glow;
    },
  };
}
