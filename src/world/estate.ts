/**
 * Everything the castle premise adds to the world: the far castle, the requisition corner
 * (board, banner, wagon, courier), the building plots with their construction and the
 * buildings' little animations, the hens, and the weeds on locked field blocks.
 */
import {
  Box3,
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
import { findByPrefix, type Assets } from '../core/assets';
import type { MaterialLib, WindProfile } from '../core/materials';
import { Sprite, type Particles } from '../fx/particles';
import type { BuildingId, EconomyState } from '../game/economy';
import { BUILDING_IDS, EXPANSIONS } from '../game/economy';
import { clamp, damp, easeOutBack, mulberry32 } from '../util/math';
import { CASTLE, FIELD, PLOT, ROYAL, SITES, terrainHeight, type Colliders } from './layout';
import { LAYER_REFLECT } from './water';

const _q = new Quaternion();
const _p = new Vector3();
const _s = new Vector3();
const _y = new Vector3(0, 1, 0);

function mat4(x: number, y: number, z: number, rot: number, s: number): Matrix4 {
  _q.setFromAxisAngle(_y, rot);
  return new Matrix4().compose(_p.set(x, y, z), _q, _s.set(s, s, s));
}

interface Hen {
  obj: Object3D;
  head: Object3D | null;
  x: number;
  z: number;
  yaw: number;
  tx: number;
  tz: number;
  wait: number;
  peck: number;
}

interface Plot3D {
  id: BuildingId;
  site: Object3D | null;
  scaffold: Object3D | null;
  building: Object3D | null;
  /** Seconds since it finished (drives the pop). */
  pop: number;
  shownBuilt: boolean;
  door: Vector3;
  lamps: PointLight[];
}

export class Estate {
  readonly group = new Group();
  readonly courierPos: Vector3;
  readonly boardPos: Vector3;
  private readonly plots = new Map<BuildingId, Plot3D>();
  private sails: Object3D | null = null;
  private sailSpeed = 0.25;
  private bakeSmoke = new Vector3();
  private smokeT = 0;
  private readonly hens: Hen[] = [];
  private readonly weeds: InstancedMesh[][] = [[], [], [], []];
  private readonly signs: (Object3D | null)[] = [null, null, null, null];
  readonly signPos: Vector3[] = [];
  private bannerCloth: Object3D | null = null;
  private courier: Object3D | null = null;
  private courierHead: Object3D | null = null;
  private courierArmR: Object3D | null = null;
  private courierArmL: Object3D | null = null;
  private courierWave = 0;
  private readonly lights: PointLight[] = [];
  private time = 0;
  private readonly runCentre = new Vector3();
  private runHalf = { x: 1.6, z: 1.2 };
  private ovenGlow: Material[] = [];

  constructor(
    scene: Scene,
    private readonly assets: Assets,
    private readonly lib: MaterialLib,
    private readonly particles: Particles,
    private readonly colliders: Colliders,
  ) {
    this.group.name = 'estate';
    scene.add(this.group);

    // ---------------------------------------------------------------- castle
    const castle = this.place('castle', CASTLE.x, CASTLE.z, CASTLE.rot, CASTLE.scale, { cast: false, y: terrainHeight(CASTLE.x, CASTLE.z) - 0.4 });
    if (castle) {
      castle.traverse((o) => o.layers.enable(LAYER_REFLECT));
    }

    // ---------------------------------------------------------------- requisition corner
    const b = ROYAL.board;
    this.boardPos = new Vector3(b.x, terrainHeight(b.x, b.z), b.z);
    const board = this.place('notice_board', b.x, b.z, b.rot, 1);
    if (board) this.addSegment(b.x, b.z, b.rot, 1.05, 0.18);
    const ban = this.place('banner_pole', ROYAL.banner.x, ROYAL.banner.z, 0.3, 1);
    if (ban) {
      this.colliders.circles.push({ x: ROYAL.banner.x, z: ROYAL.banner.z, r: 0.15 });
      this.bannerCloth = findByPrefix(ban, 'banner_cloth');
    }
    const w = ROYAL.wagon;
    const wagon = this.place('wagon', w.x, w.z, w.rot, 1);
    if (wagon) this.addSegment(w.x, w.z, w.rot + Math.PI / 2, 1.9, 0.85);
    this.place('milestone', ROYAL.milestone.x, ROYAL.milestone.z, ROYAL.milestone.rot, 1, { collide: 0.35 });
    const c = ROYAL.courier;
    this.courierPos = new Vector3(c.x, terrainHeight(c.x, c.z), c.z);
    this.courier = this.place('courier', c.x, c.z, c.rot, 1, { collide: 0.35 });
    if (this.courier) {
      this.courierHead = findByPrefix(this.courier, 'courier_head');
      this.courierArmR = findByPrefix(this.courier, 'courier_arm_r');
      this.courierArmL = findByPrefix(this.courier, 'courier_arm_l');
      for (const o of [this.courierHead, this.courierArmR, this.courierArmL]) if (o) o.userData.rest = o.quaternion.clone();
    }
    // the board's and the wagon's lanterns light up in the evening
    const lantern = (o: Object3D | null, marker: string, base: number, dist: number): void => {
      const m = o ? findByPrefix(o, marker) : null;
      if (!m) return;
      const l = new PointLight(new Color(1.0, 0.64, 0.32), 0, dist, 1.8);
      m.getWorldPosition(l.position);
      l.userData.base = base;
      scene.add(l);
      this.lights.push(l);
    };
    lantern(board, 'board_lantern_light', 5, 7);
    lantern(wagon, 'wagon_lantern_light', 3.5, 6);

    // ---------------------------------------------------------------- building plots
    for (const id of BUILDING_IDS) {
      const s = SITES[id];
      const site = this.place('build_site', s.x, s.z, s.rot, 1, { y: terrainHeight(s.x, s.z) });
      const scaffold = this.place('scaffold', s.x, s.z, s.rot, 1, { y: terrainHeight(s.x, s.z) });
      if (scaffold) scaffold.visible = false;
      const building = this.place(id, s.x, s.z, s.rot, 1, { y: terrainHeight(s.x, s.z) - 0.02 });
      if (building) building.visible = false;
      const doorM = building ? findByPrefix(building, `${id}_door`) : null;
      const door = doorM ? doorM.getWorldPosition(new Vector3()) : new Vector3(s.x + Math.sin(s.rot) * (s.half + 0.6), terrainHeight(s.x, s.z), s.z + Math.cos(s.rot) * (s.half + 0.6));
      const lamps: PointLight[] = [];
      const lm = building ? findByPrefix(building, `${id}_lantern_light`) : null;
      if (lm) {
        const l = new PointLight(new Color(1.0, 0.64, 0.32), 0, 7, 1.8);
        lm.getWorldPosition(l.position);
        l.userData.base = 4;
        scene.add(l);
        lamps.push(l);
      }
      this.plots.set(id, { id, site, scaffold, building, pop: 99, shownBuilt: false, door, lamps });
      if (id === 'windmill' && building) this.sails = findByPrefix(building, 'windmill_sails');
      if (id === 'bakehouse' && building) {
        const sm = findByPrefix(building, 'bakehouse_smoke');
        if (sm) sm.getWorldPosition(this.bakeSmoke);
        else this.bakeSmoke.set(s.x, terrainHeight(s.x, s.z) + 5, s.z);
        building.traverse((o) => {
          const m = o as Mesh;
          if (m.isMesh && (m.material as Material).name === 'ember') this.ovenGlow.push(m.material as Material);
        });
      }
      if (id === 'henhouse' && building) {
        const run = findByPrefix(building, 'henhouse_run');
        if (run) run.getWorldPosition(this.runCentre);
        else this.runCentre.set(s.x, terrainHeight(s.x, s.z), s.z - 1.5);
      }
    }

    // ---------------------------------------------------------------- locked field blocks
    const rng = mulberry32(99);
    for (const e of EXPANSIONS) {
      if (e.cost === 0) {
        this.signPos.push(new Vector3());
        continue;
      }
      const reeds: Matrix4[] = [];
      const scrub: Matrix4[] = [];
      const daisies: Matrix4[] = [];
      const stones: Matrix4[] = [];
      for (let col = e.cols[0]; col <= e.cols[1]; col++) {
        for (let row = e.rows[0]; row <= e.rows[1]; row++) {
          const x = FIELD.x0 + (col + 0.5) * PLOT;
          const z = FIELD.z0 + (row + 0.5) * PLOT;
          const n = 1 + Math.floor(rng() * 2);
          for (let i = 0; i < n; i++) {
            const ox = (rng() - 0.5) * PLOT * 0.8;
            const oz = (rng() - 0.5) * PLOT * 0.8;
            if (rng() < 0.4) reeds.push(mat4(x + ox, 0.1, z + oz, rng() * 6, 0.28 + rng() * 0.18));
            else scrub.push(mat4(x + ox, 0.06, z + oz, rng() * 6, 0.24 + rng() * 0.14));
          }
          if (rng() < 0.6) daisies.push(mat4(x + (rng() - 0.5) * PLOT * 0.8, 0.1, z + (rng() - 0.5) * PLOT * 0.8, rng() * 6, 0.9 + rng() * 0.4));
          if (rng() < 0.22) stones.push(mat4(x + (rng() - 0.5) * PLOT * 0.6, 0.06, z + (rng() - 0.5) * PLOT * 0.6, rng() * 6, 0.28 + rng() * 0.18));
        }
      }
      this.weeds[e.id]!.push(...this.scatter('reed_clump', reeds, 'crop'), ...this.scatter('bush_a', scrub, 'bush'), ...this.scatter('flower_daisy', daisies, 'flower'), ...this.scatter('rock_c', stones, 'none'));
      const cx = FIELD.x0 + ((e.cols[0] + e.cols[1] + 1) / 2) * PLOT;
      const cz = FIELD.z0 + ((e.rows[0] + e.rows[1] + 1) / 2) * PLOT;
      this.signs[e.id] = this.place('expand_sign', cx, cz, 0.15, 1, { y: 0.1 });
      this.signPos.push(new Vector3(cx, 0.1, cz));
    }
  }

  private place(name: string, x: number, z: number, rot: number, scale: number, o: { cast?: boolean; y?: number; collide?: number; wind?: WindProfile } = {}): Object3D | null {
    const obj = this.assets.clone(name);
    if (!obj) return null;
    this.lib.apply(obj, o.wind ?? 'none', { cast: o.cast ?? true });
    obj.position.set(x, o.y ?? terrainHeight(x, z), z);
    obj.rotation.y = rot;
    obj.scale.setScalar(scale);
    this.group.add(obj);
    obj.updateMatrixWorld(true);
    if (o.collide) this.colliders.circles.push({ x, z, r: o.collide });
    return obj;
  }

  private scatter(name: string, mats: Matrix4[], wind: WindProfile): InstancedMesh[] {
    const src = this.assets.node(name);
    const out: InstancedMesh[] = [];
    if (!src || mats.length === 0) return out;
    src.traverse((c) => {
      const m = c as Mesh;
      if (!m.isMesh) return;
      const matName = (m.material as Material).name.replace(/\.\d+$/, '');
      const im = new InstancedMesh(m.geometry, this.lib.get(matName, wind), mats.length);
      for (let i = 0; i < mats.length; i++) im.setMatrixAt(i, mats[i]!);
      im.instanceMatrix.needsUpdate = true;
      im.castShadow = true;
      im.receiveShadow = true;
      const depth = this.lib.depthFor(matName, wind);
      if (depth) im.customDepthMaterial = depth;
      im.computeBoundingSphere();
      this.group.add(im);
      out.push(im);
    });
    return out;
  }

  /** A wall-like collider: a segment centred at (x,z) along angle `rot` with half length `half`. */
  private addSegment(x: number, z: number, rot: number, half: number, r: number): void {
    const dx = Math.cos(rot) * half;
    const dz = -Math.sin(rot) * half;
    this.colliders.segments.push({ ax: x - dx, az: z - dz, bx: x + dx, bz: z + dz, r });
  }

  /** Building footprint colliders (added once the building stands). */
  private addFootprint(id: BuildingId): void {
    const p = this.plots.get(id);
    if (!p?.building) return;
    const s = SITES[id];
    p.building.updateMatrixWorld(true);
    const box = new Box3();
    // only the solid core: ignore thin outliers (sails, ramps) by shrinking a little
    p.building.traverse((o) => {
      const m = o as Mesh;
      if (!m.isMesh || o.name.startsWith('windmill_sails')) return;
      for (let a: Object3D | null = o; a; a = a.parent) if (a.name.startsWith('windmill_sails')) return;
      m.geometry.computeBoundingBox();
      const bb = m.geometry.boundingBox!.clone();
      // local box of the root
      bb.applyMatrix4(new Matrix4().copy(p.building!.matrixWorld).invert().multiply(m.matrixWorld));
      box.union(bb);
    });
    if (box.isEmpty()) return;
    const hx = Math.min((box.max.x - box.min.x) / 2, s.half) * 0.86;
    const hz = Math.min((box.max.z - box.min.z) / 2, s.half) * 0.86;
    const cx = (box.max.x + box.min.x) / 2;
    const cz = (box.max.z + box.min.z) / 2;
    const c = Math.cos(s.rot);
    const sn = Math.sin(s.rot);
    const corner = (lx: number, lz: number): [number, number] => [s.x + (cx + lx) * c + (cz + lz) * sn, s.z - (cx + lx) * sn + (cz + lz) * c];
    const cs = [corner(-hx, -hz), corner(hx, -hz), corner(hx, hz), corner(-hx, hz)];
    for (let i = 0; i < 4; i++) {
      const a = cs[i]!;
      const b = cs[(i + 1) % 4]!;
      this.colliders.segments.push({ ax: a[0], az: a[1], bx: b[0], bz: b[1], r: 0.25 });
    }
  }

  doorOf(id: BuildingId): Vector3 {
    return this.plots.get(id)!.door;
  }
  siteCentre(id: BuildingId, out: Vector3): Vector3 {
    const s = SITES[id];
    return out.set(s.x, terrainHeight(s.x, s.z), s.z);
  }

  /** Wave hello (on delivery). */
  wave(): void {
    this.courierWave = 1.6;
  }

  private spawnHens(): void {
    if (this.hens.length) return;
    const rng = mulberry32(5);
    for (let i = 0; i < 4; i++) {
      const obj = this.assets.clone(i % 3 === 2 ? 'chicken_white' : 'chicken') ?? this.assets.clone('chicken');
      if (!obj) return;
      this.lib.apply(obj);
      const x = this.runCentre.x + (rng() - 0.5) * this.runHalf.x * 1.4;
      const z = this.runCentre.z + (rng() - 0.5) * this.runHalf.z * 1.4;
      obj.position.set(x, terrainHeight(x, z), z);
      this.group.add(obj);
      const head = findByPrefix(obj, 'chicken_head') ?? findByPrefix(obj, 'chicken_white_head');
      if (head) head.userData.rest = head.quaternion.clone();
      this.hens.push({ obj, head, x, z, yaw: rng() * 6, tx: x, tz: z, wait: rng() * 2, peck: 0 });
    }
  }

  /** Apply economy state instantly (after loading a save). */
  sync(s: EconomyState): void {
    for (const id of BUILDING_IDS) {
      const st = s.buildings[id];
      const p = this.plots.get(id)!;
      if (st.built && st.progress >= 1 && !p.shownBuilt) this.finish(id, false);
    }
    for (const e of EXPANSIONS) if (s.expansions[e.id]) this.clearBlock(e.id, false);
  }

  private finish(id: BuildingId, fx: boolean): void {
    const p = this.plots.get(id)!;
    p.shownBuilt = true;
    if (p.site) p.site.visible = false;
    if (p.scaffold) p.scaffold.visible = false;
    if (p.building) p.building.visible = true;
    p.pop = fx ? 0 : 99;
    this.addFootprint(id);
    if (id === 'henhouse') this.spawnHens();
    if (fx) {
      const c = this.siteCentre(id, new Vector3());
      for (let i = 0; i < 26; i++) {
        const a = Math.random() * Math.PI * 2;
        const r = 1.5 + Math.random() * 2.5;
        this.particles.emit({ x: c.x + Math.cos(a) * r, y: c.y + 0.2, z: c.z + Math.sin(a) * r, vx: Math.cos(a) * 1.6, vy: 0.4 + Math.random() * 0.8, vz: Math.sin(a) * 1.6, life: 1.2 + Math.random() * 0.8, size: 0.4, sizeEnd: 1.6, r: 0.7, g: 0.6, b: 0.48, alpha: 0.32, sprite: Sprite.Puff, drag: 1.6, wind: 0.4, rot: Math.random() * 6 });
      }
      for (let i = 0; i < 30; i++) {
        this.particles.emit({ x: c.x + (Math.random() - 0.5) * 4, y: c.y + 1 + Math.random() * 5, z: c.z + (Math.random() - 0.5) * 4, vx: 0, vy: 0.5 + Math.random(), vz: 0, life: 1 + Math.random(), size: 0.16, sizeEnd: 0.0, r: 2.4, g: 1.9, b: 0.9, alpha: 1, sprite: Sprite.Spark, drag: 0.5, wind: 0.1, rot: 0, additive: true });
      }
    }
  }

  /** Remove the weeds and sign from a field block. */
  clearBlock(id: number, fx: boolean): void {
    for (const m of this.weeds[id] ?? []) m.visible = false;
    const sg = this.signs[id];
    if (sg) sg.visible = false;
    if (fx) {
      const e = EXPANSIONS[id]!;
      for (let col = e.cols[0]; col <= e.cols[1]; col++) {
        for (let row = e.rows[0]; row <= e.rows[1]; row++) {
          const x = FIELD.x0 + (col + 0.5) * PLOT;
          const z = FIELD.z0 + (row + 0.5) * PLOT;
          this.particles.dust(x, 0.15, z, 1.2);
          this.particles.emit({ x, y: 0.4, z, vx: (Math.random() - 0.5) * 1.2, vy: 1.2 + Math.random(), vz: (Math.random() - 0.5) * 1.2, life: 0.9, size: 0.12, sizeEnd: 0.05, r: 0.45, g: 0.6, b: 0.25, alpha: 0.9, sprite: Sprite.Leaf, drag: 1.2, wind: 0.6, rot: Math.random() * 6 });
        }
      }
    }
  }

  update(dt: number, s: EconomyState, eye: Vector3, glow: number, daylight: number): void {
    this.time += dt;
    for (const l of this.lights) l.intensity = (l.userData.base as number) * glow;
    for (const p of this.plots.values()) for (const l of p.lamps) l.intensity = p.shownBuilt ? (l.userData.base as number) * glow : 0;

    for (const id of BUILDING_IDS) {
      const st = s.buildings[id];
      const p = this.plots.get(id)!;
      if (st.built && st.progress < 1) {
        // under construction: scaffold up, the odd puff of sawdust
        if (p.scaffold) p.scaffold.visible = true;
        if (Math.random() < dt * 6) {
          const c = this.siteCentre(id, _p);
          this.particles.dust(c.x + (Math.random() - 0.5) * 4, c.y + 0.1 + Math.random() * 2.5, c.z + (Math.random() - 0.5) * 4, 0.6);
        }
      }
      if (st.built && st.progress >= 1 && !p.shownBuilt) this.finish(id, true);
      if (p.building && p.pop < 2) {
        p.pop += dt;
        const t = clamp(p.pop / 0.9, 0, 1);
        const sy = 0.6 + 0.4 * easeOutBack(t, 2.2);
        const sxz = 1 + Math.sin(t * Math.PI) * 0.08 * (1 - t);
        p.building.scale.set(sxz, sy, sxz);
      }
    }

    // windmill sails: lazy in the breeze, brisk while grinding
    if (this.sails) {
      const busy = s.buildings.windmill.queue.length > 0;
      this.sailSpeed = damp(this.sailSpeed, busy ? 1.5 : 0.28, 0.8, dt);
      this.sails.rotateZ(this.sailSpeed * dt);
    }

    // bakehouse: smoke + oven glow while baking
    const baking = s.buildings.bakehouse.built && s.buildings.bakehouse.queue.length > 0;
    for (const m of this.ovenGlow) {
      const sm = m as unknown as { emissiveIntensity?: number };
      if (sm.emissiveIntensity !== undefined) sm.emissiveIntensity = damp(sm.emissiveIntensity, baking ? 3.2 + Math.sin(this.time * 7) * 0.5 : 0.3, 3, dt);
    }
    if (s.buildings.bakehouse.built && s.buildings.bakehouse.progress >= 1) {
      this.smokeT += dt * (baking ? 3.2 : 0.7);
      while (this.smokeT > 1) {
        this.smokeT -= 1;
        const sp = this.bakeSmoke;
        this.particles.emit({ x: sp.x + (Math.random() - 0.5) * 0.15, y: sp.y, z: sp.z + (Math.random() - 0.5) * 0.15, vx: (Math.random() - 0.5) * 0.2, vy: 0.6 + Math.random() * 0.3, vz: (Math.random() - 0.5) * 0.2, life: 4 + Math.random() * 2, size: 0.3, sizeEnd: 2.2, r: 0.82, g: 0.84, b: 0.88, alpha: 0.26, sprite: Sprite.Puff, drag: 0.4, wind: 1.1, rot: Math.random() * 6 });
      }
    }

    // hens wander inside their run and peck
    for (const h of this.hens) {
      h.wait -= dt;
      const dx = h.tx - h.x;
      const dz = h.tz - h.z;
      const d = Math.hypot(dx, dz);
      if (d > 0.05) {
        const sp = Math.min(0.55, d * 2);
        h.x += (dx / d) * sp * dt;
        h.z += (dz / d) * sp * dt;
        const want = Math.atan2(dx, dz);
        let da = want - h.yaw;
        while (da > Math.PI) da -= Math.PI * 2;
        while (da < -Math.PI) da += Math.PI * 2;
        h.yaw += da * Math.min(1, dt * 8);
      } else if (h.wait <= 0) {
        if (Math.random() < 0.55) h.peck = 0.6;
        else {
          h.tx = this.runCentre.x + (Math.random() - 0.5) * this.runHalf.x * 1.6;
          h.tz = this.runCentre.z + (Math.random() - 0.5) * this.runHalf.z * 1.6;
        }
        h.wait = 0.8 + Math.random() * 2.2;
      }
      h.peck = Math.max(0, h.peck - dt);
      const hop = d > 0.05 ? Math.abs(Math.sin(this.time * 14 + h.x)) * 0.025 : 0;
      h.obj.position.set(h.x, terrainHeight(h.x, h.z) + hop, h.z);
      h.obj.rotation.y = h.yaw;
      if (h.head) {
        const rest = h.head.userData.rest as Quaternion;
        const pk = h.peck > 0 ? Math.sin((h.peck / 0.6) * Math.PI * 3) * 0.5 + 0.4 : Math.sin(this.time * 2 + h.z) * 0.08;
        _q.setFromAxisAngle(_s.set(1, 0, 0), pk);
        h.head.quaternion.copy(rest).multiply(_q);
      }
    }

    // banner sways
    if (this.bannerCloth) {
      this.bannerCloth.rotation.z = Math.sin(this.time * 1.3) * 0.06 + Math.sin(this.time * 3.1) * 0.025;
      this.bannerCloth.rotation.x = Math.sin(this.time * 0.9 + 1) * 0.05;
    }

    // courier: breathes, follows you with his eyes, waves after a delivery
    if (this.courier) {
      const cp = this.courierPos;
      const dx = eye.x - cp.x;
      const dz = eye.z - cp.z;
      const near = Math.hypot(dx, dz) < 9;
      const body = this.courier;
      body.scale.y = 1 + Math.sin(this.time * 1.7) * 0.006;
      if (this.courierHead) {
        const rest = this.courierHead.userData.rest as Quaternion;
        let yaw = 0;
        if (near) {
          yaw = Math.atan2(dx, dz) - body.rotation.y;
          while (yaw > Math.PI) yaw -= Math.PI * 2;
          while (yaw < -Math.PI) yaw += Math.PI * 2;
          yaw = clamp(yaw, -1.0, 1.0);
        } else yaw = Math.sin(this.time * 0.3) * 0.35;
        const cur = (this.courierHead.userData.yaw as number | undefined) ?? 0;
        const ny = damp(cur, yaw, 4, dt);
        this.courierHead.userData.yaw = ny;
        _q.setFromAxisAngle(_y, ny);
        this.courierHead.quaternion.copy(rest).premultiply(_q);
      }
      this.courierWave = Math.max(0, this.courierWave - dt);
      if (this.courierArmR) {
        const rest = this.courierArmR.userData.rest as Quaternion;
        const w = this.courierWave > 0 ? Math.min(1, this.courierWave * 3, (1.6 - this.courierWave) * 4) : 0;
        _q.setFromAxisAngle(_s.set(0, 0, 1), -(w * 2.5 + Math.sin(this.time * 9) * 0.3 * w));
        const sw = new Quaternion().setFromAxisAngle(_p.set(1, 0, 0), Math.sin(this.time * 1.7) * 0.03);
        this.courierArmR.quaternion.copy(rest).multiply(_q).multiply(sw);
      }
      if (this.courierArmL) {
        const rest = this.courierArmL.userData.rest as Quaternion;
        _q.setFromAxisAngle(_p.set(1, 0, 0), Math.sin(this.time * 1.7 + 0.5) * 0.03);
        this.courierArmL.quaternion.copy(rest).multiply(_q);
      }
    }
    void daylight;
  }
}
