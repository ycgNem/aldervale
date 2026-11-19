/**
 * Everything on Brookhollow Farm beyond the original yard: the far castle, the royal wagon and its
 * pony on the road up the hill, Pip and Wren, the building plots and their construction, the
 * work stations (mill hopper, nest box, oven, compost bay), the land you clear by hand (weeds,
 * field stones, fallen logs, stumps, branches), apple trees you can shake, and the feast fireworks.
 */
import {
  Box3,
  Color,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  PointLight,
  Quaternion,
  SphereGeometry,
  Vector3,
  type Material,
  type Object3D,
  type Scene,
} from 'three';
import { findByPrefix, type Assets } from '../core/assets';
import type { MaterialLib, WindProfile } from '../core/materials';
import { Sprite, type Particles } from '../fx/particles';
import { BUILDING_IDS, type BuildingId, type GameState, type ItemId } from '../game/state';
import { clamp, damp, easeOutBack, mulberry32 } from '../util/math';
import {
  CASTLE,
  COMPOST,
  COTTAGE,
  FIELD,
  PLOT,
  ROYAL,
  SITES,
  STALL,
  WAGON_ROUTE,
  groundMask,
  pondSdf,
  terrainHeight,
  type Circle,
  type Colliders,
  type GroundMask,
  type Segment,
} from './layout';
import type { AppleTree } from './props';
import { LAYER_REFLECT } from './water';

const _q = new Quaternion();
const _q2 = new Quaternion();
const _p = new Vector3();
const _s = new Vector3();
const _m = new Matrix4();
const _y = new Vector3(0, 1, 0);
const _x = new Vector3(1, 0, 0);
const _z = new Vector3(0, 0, 1);
const ZERO = new Matrix4().makeScale(0, 0, 0);

function mat4(x: number, y: number, z: number, rot: number, s: number): Matrix4 {
  _q.setFromAxisAngle(_y, rot);
  return new Matrix4().compose(_p.set(x, y, z), _q, _s.set(s, s, s));
}

// ------------------------------------------------------------------ obstacles
export type ObstacleKind = 'weed' | 'stone' | 'boulder' | 'log' | 'stump' | 'branch';
export type ObstacleTool = 'hoe' | 'pick' | 'axe';

interface Piece {
  model: string;
  meshes: InstancedMesh[];
  index: number;
  base: Matrix4;
}

export interface Obstacle {
  key: string;
  kind: ObstacleKind;
  x: number;
  z: number;
  y: number;
  /** Targeting cylinder. */
  r: number;
  h: number;
  tool: ObstacleTool;
  hits: number;
  drops: [ItemId, number][];
  /** Field block it belongs to (-1 = meadow). */
  block: number;
  plot: [number, number] | null;
  respawn: boolean;
  collider: Circle | null;
  colliderR: number;
  pieces: Piece[];
  alive: boolean;
  shake: number;
}

const OB_SPEC: Record<ObstacleKind, { tool: ObstacleTool; hits: number; drops: [ItemId, number][]; r: number; h: number; collide: number }> = {
  weed: { tool: 'hoe', hits: 1, drops: [['weeds', 1]], r: 0.45, h: 0.7, collide: 0 },
  stone: { tool: 'pick', hits: 2, drops: [['stone', 2]], r: 0.45, h: 0.5, collide: 0 },
  boulder: { tool: 'pick', hits: 4, drops: [['stone', 4]], r: 0.75, h: 0.8, collide: 0.6 },
  log: { tool: 'axe', hits: 3, drops: [['wood', 3]], r: 0.9, h: 0.7, collide: 0.55 },
  stump: { tool: 'axe', hits: 3, drops: [['wood', 2]], r: 0.5, h: 0.7, collide: 0.4 },
  branch: { tool: 'axe', hits: 1, drops: [['wood', 1]], r: 0.55, h: 0.45, collide: 0 },
};

export const BLOCK_PLOTS: { cols: [number, number]; rows: [number, number] }[] = [
  { cols: [0, 4], rows: [0, 3] },
  { cols: [5, 9], rows: [0, 3] },
  { cols: [0, 4], rows: [4, 7] },
  { cols: [5, 9], rows: [4, 7] },
];
export const BLOCK_NAMES = ['Home plot', 'East Furrows', 'South-west Beds', 'South-east Beds'];
export function blockOf(col: number, row: number): number {
  for (let i = 0; i < BLOCK_PLOTS.length; i++) {
    const b = BLOCK_PLOTS[i]!;
    if (col >= b.cols[0] && col <= b.cols[1] && row >= b.rows[0] && row <= b.rows[1]) return i;
  }
  return 0;
}

// ------------------------------------------------------------------ helpers
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
  pop: number;
  shownBuilt: boolean;
  door: Vector3;
  lamps: PointLight[];
}

interface Apple {
  obj: Object3D;
  p: Vector3;
  v: Vector3;
  rest: boolean;
  age: number;
}

interface Rocket {
  t: number;
  fuse: number;
  from: Vector3;
  to: Vector3;
  hue: number;
}

/** Catmull-Rom path with arc-length lookup. */
class Route {
  readonly pts: Vector3[] = [];
  readonly len: number[] = [];
  constructor(ctrl: [number, number][], perSeg = 16) {
    const P = ctrl.map(([x, z]) => new Vector3(x, 0, z));
    const n = P.length;
    for (let i = 0; i < n - 1; i++) {
      const p0 = P[Math.max(i - 1, 0)]!;
      const p1 = P[i]!;
      const p2 = P[i + 1]!;
      const p3 = P[Math.min(i + 2, n - 1)]!;
      for (let s = 0; s < perSeg; s++) {
        const t = s / perSeg;
        const t2 = t * t;
        const t3 = t2 * t;
        const f = (a: number, b: number, c: number, d: number): number => 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
        this.pts.push(new Vector3(f(p0.x, p1.x, p2.x, p3.x), 0, f(p0.z, p1.z, p2.z, p3.z)));
      }
    }
    this.pts.push(P[n - 1]!.clone());
    this.len.push(0);
    for (let i = 1; i < this.pts.length; i++) this.len.push(this.len[i - 1]! + this.pts[i]!.distanceTo(this.pts[i - 1]!));
  }
  get total(): number {
    return this.len[this.len.length - 1]!;
  }
  /** Position and tangent at distance d. */
  at(d: number, pos: Vector3, tan: Vector3): void {
    d = clamp(d, 0, this.total);
    let i = 1;
    while (i < this.len.length - 1 && this.len[i]! < d) i++;
    const a = this.pts[i - 1]!;
    const b = this.pts[i]!;
    const t = (d - this.len[i - 1]!) / Math.max(this.len[i]! - this.len[i - 1]!, 1e-6);
    pos.lerpVectors(a, b, t);
    tan.subVectors(b, a).normalize();
  }
}

export const LEAVE_TIME = 34;
export const AWAY_TIME = 40;

function easeInOutSoft(t: number): number {
  t = clamp(t, 0, 1);
  return t * t * (3 - 2 * t);
}

/** Item -> model, for goods shown in the world. */
export const MODEL_OF: Partial<Record<ItemId, string>> = {
  wheat: 'item_wheat',
  tomato: 'item_tomato',
  pumpkin: 'item_pumpkin',
  carrot: 'item_carrot',
  cabbage: 'item_cabbage',
  flour: 'item_flour',
  eggs: 'item_eggs',
  bread: 'item_bread',
  pie: 'item_pie',
  chutney: 'item_chutney',
  tart: 'item_tart',
  cider: 'item_cider',
  apple: 'item_apple',
};

export class Estate {
  readonly group = new Group();
  readonly boardPos: Vector3;
  /** Where Pip stands when the wagon is home. */
  readonly courierPos = new Vector3();
  readonly cratePos = new Vector3();
  readonly stallPos = new Vector3();
  readonly wrenPos = new Vector3();
  readonly hopperPos = new Vector3();
  readonly sackPos = new Vector3();
  readonly nestPos = new Vector3();
  readonly ovenPos = new Vector3();
  readonly compostPos = new Vector3();
  readonly bedPos = new Vector3();
  readonly runCentre = new Vector3();
  readonly obstacles: Obstacle[] = [];
  readonly apples: Apple[] = [];
  readonly appleTrees: AppleTree[];
  /** True while the wagon is away (Pip and the crate are gone). */
  wagonAway = false;

  private readonly plots = new Map<BuildingId, Plot3D>();
  private sails: Object3D | null = null;
  private sailSpeed = 0.25;
  private readonly bakeSmoke = new Vector3();
  private smokeT = 0;
  private readonly hens: Hen[] = [];
  private grainT = 0;
  private readonly blockDecor: InstancedMesh[][] = [[], [], [], []];
  private readonly signs: (Object3D | null)[] = [null, null, null, null];
  private bannerCloth: Object3D | null = null;
  private courier: Object3D | null = null;
  private courierHead: Object3D | null = null;
  private courierArmR: Object3D | null = null;
  private courierArmL: Object3D | null = null;
  private courierWave = 0;
  private wren: Object3D | null = null;
  private wrenHead: Object3D | null = null;
  private wrenArmR: Object3D | null = null;
  private wrenWave = 0;
  private stall: Object3D | null = null;
  private readonly lights: PointLight[] = [];
  private stallLamp: PointLight | null = null;
  private time = 0;
  private readonly runHalf = { x: 1.6, z: 1.1 };
  private readonly ovenGlow: Material[] = [];
  private ovenFound = false;

  // wagon
  private readonly route = new Route(WAGON_ROUTE);
  private wagon: Object3D | null = null;
  private readonly wheels: { o: Object3D; r: number }[] = [];
  private pony: Object3D | null = null;
  private readonly ponyLegs: { o: Object3D; phase: number; rest: Quaternion }[] = [];
  private ponyHead: Object3D | null = null;
  private ponyTail: Object3D | null = null;
  private wagonDist = 0;
  private ponyPhase = 0;
  private readonly wagonBackLocal = new Vector3(0, 0, -2.35);
  private readonly ponyAhead = 3.9;
  private wagonCollider: Segment | null = null;
  private crate: Object3D | null = null;
  private readonly crateGoods: Object3D[] = [];
  private crateGoodsKey = '';

  // stations
  private hopper: Object3D | null = null;
  private readonly sacks: Object3D[] = [];
  private nest: Object3D | null = null;
  private readonly eggs: Object3D[] = [];
  private dish: Object3D | null = null;
  private dishKey = '';
  private heap: Object3D | null = null;

  // apples + fireworks
  private readonly appleShake = new Map<string, number>();
  private appleSrc: Object3D | null = null;
  private readonly rockets: Rocket[] = [];
  private fireworksLeft = 0;
  private fireT = 0;
  /** Called when a rocket bursts (for the boom). */
  onBurst: ((at: Vector3) => void) | null = null;

  constructor(
    scene: Scene,
    private readonly assets: Assets,
    private readonly lib: MaterialLib,
    private readonly particles: Particles,
    private readonly colliders: Colliders,
    appleTrees: AppleTree[],
  ) {
    this.group.name = 'estate';
    scene.add(this.group);
    this.appleTrees = appleTrees;

    // ---------------------------------------------------------------- castle
    const castle = this.place('castle', CASTLE.x, CASTLE.z, CASTLE.rot, CASTLE.scale, { cast: false, y: terrainHeight(CASTLE.x, CASTLE.z) - 0.4 });
    if (castle) castle.traverse((o) => o.layers.enable(LAYER_REFLECT));

    // ---------------------------------------------------------------- the board (now the steward's journal)
    const b = ROYAL.board;
    this.boardPos = new Vector3(b.x, terrainHeight(b.x, b.z), b.z);
    const board = this.place('notice_board', b.x, b.z, b.rot, 1);
    if (board) this.addSegment(b.x, b.z, b.rot, 1.05, 0.18);
    const ban = this.place('banner_pole', ROYAL.banner.x, ROYAL.banner.z, 0.3, 1);
    if (ban) {
      this.colliders.circles.push({ x: ROYAL.banner.x, z: ROYAL.banner.z, r: 0.15 });
      this.bannerCloth = findByPrefix(ban, 'banner_cloth');
    }
    this.place('milestone', ROYAL.milestone.x, ROYAL.milestone.z, ROYAL.milestone.rot, 1, { collide: 0.35 });
    this.lantern(scene, board, 'board_lantern_light', 5, 7);

    // ---------------------------------------------------------------- the royal wagon, its pony, Pip and the crate
    const w = ROYAL.wagon;
    this.wagon = this.place('wagon', w.x, w.z, w.rot, 1);
    if (this.wagon) {
      for (const n of ['wagon_wheel_fl', 'wagon_wheel_fr', 'wagon_wheel_bl', 'wagon_wheel_br']) {
        const o = findByPrefix(this.wagon, n);
        if (o) this.wheels.push({ o, r: n.includes('_f') ? 0.46 : 0.58 });
      }
      const back = findByPrefix(this.wagon, 'wagon_back');
      if (back) this.wagonBackLocal.copy(back.position);
      const seg: Segment = { ax: 0, az: 0, bx: 0, bz: 0, r: 0.85 };
      this.colliders.segments.push(seg);
      this.wagonCollider = seg;
      this.lantern(scene, this.wagon, 'wagon_lantern_light', 3.5, 6);
    }
    this.pony = this.place('pony', w.x, w.z, w.rot, 1);
    if (this.pony) {
      const legs: [string, number][] = [
        ['pony_leg_fl', 0],
        ['pony_leg_br', 0],
        ['pony_leg_fr', Math.PI],
        ['pony_leg_bl', Math.PI],
      ];
      for (const [n, ph] of legs) {
        const o = findByPrefix(this.pony, n);
        if (o) this.ponyLegs.push({ o, phase: ph, rest: o.quaternion.clone() });
      }
      this.ponyHead = findByPrefix(this.pony, 'pony_head');
      this.ponyTail = findByPrefix(this.pony, 'pony_tail');
      for (const o of [this.ponyHead, this.ponyTail]) if (o) o.userData.rest = o.quaternion.clone();
      this.colliders.circles.push({ x: w.x + Math.sin(w.rot) * this.ponyAhead, z: w.z + Math.cos(w.rot) * this.ponyAhead, r: 0.6 });
    }
    this.poseWagon(0, 0);
    // the crate sits on the ground behind the tailgate, Pip beside it
    {
      const fx = Math.sin(w.rot);
      const fz = Math.cos(w.rot);
      const back = Math.abs(this.wagonBackLocal.z);
      this.cratePos.set(w.x - fx * (back + 0.25), 0, w.z - fz * (back + 0.25));
      this.cratePos.y = terrainHeight(this.cratePos.x, this.cratePos.z);
      this.crate = this.place('delivery_crate', this.cratePos.x, this.cratePos.z, w.rot + Math.PI, 1, { collide: 0.5 }) ?? this.place('crate', this.cratePos.x, this.cratePos.z, w.rot, 0.9, { collide: 0.5 });
      const rx = Math.cos(w.rot);
      const rz = -Math.sin(w.rot);
      this.courierPos.set(this.cratePos.x + rx * 1.35 - fx * 0.3, 0, this.cratePos.z + rz * 1.35 - fz * 0.3);
      this.courierPos.y = terrainHeight(this.courierPos.x, this.courierPos.z);
    }
    this.courier = this.place('courier', this.courierPos.x, this.courierPos.z, Math.atan2(-8 - this.courierPos.x, 4 - this.courierPos.z), 1);
    if (this.courier) {
      this.courierHead = findByPrefix(this.courier, 'courier_head');
      this.courierArmR = findByPrefix(this.courier, 'courier_arm_r');
      this.courierArmL = findByPrefix(this.courier, 'courier_arm_l');
      for (const o of [this.courierHead, this.courierArmR, this.courierArmL]) if (o) o.userData.rest = o.quaternion.clone();
    }
    this.colliders.circles.push({ x: this.courierPos.x, z: this.courierPos.z, r: 0.35 });

    // ---------------------------------------------------------------- Wren's stall
    {
      const st = this.place('peddler_stall', STALL.x, STALL.z, STALL.rot, 1);
      this.stall = st;
      const fx = Math.sin(STALL.rot);
      const fz = Math.cos(STALL.rot);
      const keeper = st ? findByPrefix(st, 'stall_keeper') : null;
      const front = st ? findByPrefix(st, 'stall_front') : null;
      if (keeper) keeper.getWorldPosition(this.wrenPos);
      else this.wrenPos.set(STALL.x - fx * 0.4, 0, STALL.z - fz * 0.4);
      if (front) front.getWorldPosition(this.stallPos);
      else this.stallPos.set(STALL.x + fx * 1.6, 0, STALL.z + fz * 1.6);
      this.wrenPos.y = terrainHeight(this.wrenPos.x, this.wrenPos.z);
      this.stallPos.y = terrainHeight(this.stallPos.x, this.stallPos.z);
      if (st) this.addSegment(STALL.x, STALL.z, STALL.rot, 1.5, 0.75);
      const lampM = st ? findByPrefix(st, 'stall_lantern_light') : null;
      if (lampM) {
        const l = new PointLight(new Color(1.0, 0.64, 0.32), 0, 7, 1.8);
        lampM.getWorldPosition(l.position);
        l.userData.base = 4;
        scene.add(l);
        this.stallLamp = l;
      }
      this.wren = this.place('peddler', this.wrenPos.x, this.wrenPos.z, STALL.rot, 1);
      if (this.wren) {
        this.wrenHead = findByPrefix(this.wren, 'peddler_head');
        this.wrenArmR = findByPrefix(this.wren, 'peddler_arm_r');
        for (const o of [this.wrenHead, this.wrenArmR]) if (o) o.userData.rest = o.quaternion.clone();
      }
      this.setStallVisible(false);
    }

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
        // the oven mouth: centre of the glowing ember mesh
        const box = new Box3();
        building.updateMatrixWorld(true);
        building.traverse((o) => {
          const m = o as Mesh;
          if (!m.isMesh || (m.material as Material).name !== 'ember') return;
          this.ovenGlow.push(m.material as Material);
          m.geometry.computeBoundingBox();
          box.union(m.geometry.boundingBox!.clone().applyMatrix4(m.matrixWorld));
        });
        if (!box.isEmpty()) {
          box.getCenter(this.ovenPos);
          this.ovenFound = true;
        } else this.ovenPos.set(s.x, terrainHeight(s.x, s.z) + 0.9, s.z);
      }
      if (id === 'henhouse') {
        const run = building ? findByPrefix(building, 'henhouse_run') : null;
        if (run) run.getWorldPosition(this.runCentre);
        else this.runCentre.set(s.x, terrainHeight(s.x, s.z), s.z - 1.5);
      }
      if (id === 'windmill') {
        // the hopper stands to one side of the mill door
        const fx = Math.sin(s.rot);
        const fz = Math.cos(s.rot);
        const rx = Math.cos(s.rot);
        const rz = -Math.sin(s.rot);
        this.hopperPos.set(door.x + rx * 1.8 + fx * 0.2, 0, door.z + rz * 1.8 + fz * 0.2);
        this.hopperPos.y = terrainHeight(this.hopperPos.x, this.hopperPos.z);
      }
    }
    // stations: hidden until their building stands
    {
      const s = SITES.windmill;
      this.hopper = this.place('mill_hopper', this.hopperPos.x, this.hopperPos.z, s.rot, 1) ?? this.place('trough', this.hopperPos.x, this.hopperPos.z, s.rot, 0.8);
      const out = this.hopper ? findByPrefix(this.hopper, 'hopper_out') : null;
      if (out) out.getWorldPosition(this.sackPos);
      else this.sackPos.set(this.hopperPos.x + Math.sin(s.rot) * 0.9, this.hopperPos.y, this.hopperPos.z + Math.cos(s.rot) * 0.9);
      this.sackPos.y = terrainHeight(this.sackPos.x, this.sackPos.z);
      if (this.hopper) this.hopper.visible = false;
      for (let i = 0; i < 6; i++) {
        const sk = this.assets.clone('item_flour') ?? this.assets.clone('sack');
        if (!sk) break;
        this.lib.apply(sk);
        const a = i * 1.9;
        sk.position.set(this.sackPos.x + Math.cos(a) * (i ? 0.3 : 0), this.sackPos.y, this.sackPos.z + Math.sin(a) * (i ? 0.3 : 0));
        sk.rotation.y = a * 1.7;
        sk.scale.setScalar(1.2);
        sk.visible = false;
        this.group.add(sk);
        this.sacks.push(sk);
      }
    }
    {
      const s = SITES.henhouse;
      const nx = this.runCentre.x - Math.cos(s.rot) * 1.45;
      const nz = this.runCentre.z + Math.sin(s.rot) * 1.45;
      this.nest = this.place('nest_box', nx, nz, s.rot + Math.PI / 2, 1) ?? this.place('crate', nx, nz, s.rot, 0.5);
      const ne = this.nest ? findByPrefix(this.nest, 'nest_eggs') : null;
      if (ne) ne.getWorldPosition(this.nestPos);
      else this.nestPos.set(nx, terrainHeight(nx, nz) + 0.3, nz);
      if (this.nest) this.nest.visible = false;
      for (let i = 0; i < 3; i++) {
        const e = this.assets.clone('item_eggs');
        if (!e) break;
        this.lib.apply(e);
        e.position.set(this.nestPos.x + (i - 1) * 0.12, this.nestPos.y + i * 0.015, this.nestPos.z + (i % 2) * 0.06);
        e.scale.setScalar(0.8);
        e.visible = false;
        this.group.add(e);
        this.eggs.push(e);
      }
    }
    {
      this.compostPos.set(COMPOST.x, terrainHeight(COMPOST.x, COMPOST.z), COMPOST.z);
      const bay = this.place('compost_bay', COMPOST.x, COMPOST.z, COMPOST.rot, 1, { collide: 0.7 }) ?? this.place('hay_bale', COMPOST.x, COMPOST.z, COMPOST.rot, 1, { collide: 0.6 });
      this.heap = bay ? findByPrefix(bay, 'compost_heap') : null;
      if (this.heap) this.heap.userData.rest = this.heap.scale.clone();
      const front = bay ? findByPrefix(bay, 'compost_front') : null;
      if (front) front.getWorldPosition(this.compostPos);
    }
    {
      // a rest spot on the cottage porch, left of the door
      const c = Math.cos(COTTAGE.rot);
      const s = Math.sin(COTTAGE.rot);
      const lx = -3.55;
      const lz = 4.0;
      this.bedPos.set(COTTAGE.x + lx * c + lz * s, 0, COTTAGE.z - lx * s + lz * c);
      this.bedPos.y = terrainHeight(this.bedPos.x, this.bedPos.z);
      if (!this.place('hay_bed', this.bedPos.x, this.bedPos.z, COTTAGE.rot, 1, { collide: 0.55 })) this.place('bench', this.bedPos.x, this.bedPos.z, COTTAGE.rot, 1, { collide: 0.5 });
    }

    // ---------------------------------------------------------------- land to clear
    this.buildObstacles();
    this.appleSrc = this.assets.node('item_apple');
  }

  // ------------------------------------------------------------------ placement helpers
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

  private instanced(name: string, mats: Matrix4[], wind: WindProfile): InstancedMesh[] {
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

  private addSegment(x: number, z: number, rot: number, half: number, r: number): Segment {
    const dx = Math.cos(rot) * half;
    const dz = -Math.sin(rot) * half;
    const seg = { ax: x - dx, az: z - dz, bx: x + dx, bz: z + dz, r };
    this.colliders.segments.push(seg);
    return seg;
  }

  private lantern(scene: Scene, o: Object3D | null, marker: string, base: number, dist: number): void {
    const m = o ? findByPrefix(o, marker) : null;
    if (!m) return;
    const l = new PointLight(new Color(1.0, 0.64, 0.32), 0, dist, 1.8);
    m.getWorldPosition(l.position);
    l.userData.base = base;
    l.userData.wagon = o === this.wagon;
    scene.add(l);
    this.lights.push(l);
  }

  // ------------------------------------------------------------------ obstacles
  private buildObstacles(): void {
    const rng = mulberry32(2024);
    type Want = { kind: ObstacleKind; x: number; z: number; rot: number; scale: number; block: number; plot: [number, number] | null; respawn: boolean };
    const wants: Want[] = [];
    // field blocks 1-3: every plot is overgrown, some carry a buried stone
    for (let bi = 1; bi < BLOCK_PLOTS.length; bi++) {
      const b = BLOCK_PLOTS[bi]!;
      for (let col = b.cols[0]; col <= b.cols[1]; col++) {
        for (let row = b.rows[0]; row <= b.rows[1]; row++) {
          const x = FIELD.x0 + (col + 0.5) * PLOT;
          const z = FIELD.z0 + (row + 0.5) * PLOT;
          const stone = rng() < 0.3;
          const weed = !stone || rng() < 0.35;
          if (weed) wants.push({ kind: 'weed', x: x + (rng() - 0.5) * 0.35, z: z + (rng() - 0.5) * 0.35, rot: rng() * 6.28, scale: 0.85 + rng() * 0.3, block: bi, plot: [col, row], respawn: false });
          if (stone) wants.push({ kind: 'stone', x: x + (rng() - 0.5) * 0.3, z: z + (rng() - 0.5) * 0.3, rot: rng() * 6.28, scale: 0.85 + rng() * 0.3, block: bi, plot: [col, row], respawn: false });
        }
      }
    }
    // the meadow: fallen timber and a few big stones
    const meadow: [ObstacleKind, number, number, boolean][] = [
      ['log', -24.5, 6.5, false],
      ['log', -18.5, 21.5, false],
      ['log', 12.5, 19.8, false],
      ['log', 19.5, 23.0, false],
      ['log', 31.5, -4.5, false],
      ['log', 28.5, -14.5, false],
      ['log', -28.0, -15.5, false],
      ['log', -3.5, -16.5, false],
      ['stump', -27.0, 11.0, false],
      ['stump', 16.5, -21.0, false],
      ['stump', -14.5, -17.5, false],
      ['stump', 9.5, 22.0, false],
      ['stump', 33.5, 10.5, false],
      ['boulder', -27.5, -6.0, false],
      ['boulder', 20.5, 18.5, false],
      ['boulder', -10.5, 21.5, false],
      ['branch', -20.5, 9.0, true],
      ['branch', 6.5, -13.8, true],
      ['branch', -9.5, 17.5, true],
      ['branch', 25.5, 5.0, true],
      ['branch', -30.5, 2.0, true],
      ['branch', 0.5, 20.8, true],
      ['branch', -16.5, -14.0, true],
      ['branch', 18.0, -7.5, true],
    ];
    const gm: GroundMask = { dirt: 0, path: 0, shore: 0 };
    for (const [kind, x0, z0, respawn] of meadow) {
      let x = x0;
      let z = z0;
      // nudge off paths, water and anything solid
      for (let k = 0; k < 12; k++) {
        groundMask(x, z, gm);
        const blocked = gm.path > 0.1 || gm.dirt > 0.3 || pondSdf(x, z) < 1.5 || this.colliders.circles.some((c) => c.r > 0 && Math.hypot(c.x - x, c.z - z) < c.r + 1.4);
        if (!blocked) break;
        const a = rng() * 6.28;
        x += Math.cos(a) * 1.5;
        z += Math.sin(a) * 1.5;
      }
      wants.push({ kind, x, z, rot: rng() * 6.28, scale: kind === 'boulder' ? 1.7 : 0.9 + rng() * 0.25, block: -1, plot: null, respawn });
    }

    const MODEL: Record<ObstacleKind, [string, string]> = {
      weed: ['weed_clump', 'reed_clump'],
      stone: ['field_stone', 'rock_c'],
      boulder: ['field_stone', 'rock_b'],
      log: ['fallen_log', 'woodpile'],
      stump: ['tree_stump', 'rock_a'],
      branch: ['branch_pile', 'woodpile'],
    };
    const FALLBACK_SCALE: Record<ObstacleKind, number> = { weed: 0.42, stone: 0.42, boulder: 0.6, log: 0.7, stump: 0.6, branch: 0.45 };
    // group by model so each kind is a handful of instanced meshes
    const byModel = new Map<string, { mats: Matrix4[]; obs: Obstacle[]; wind: WindProfile }>();
    let n = 0;
    for (const wnt of wants) {
      const [primary, fb] = MODEL[wnt.kind];
      const model = this.assets.has(primary) ? primary : fb;
      const spec = OB_SPEC[wnt.kind];
      const fs = model === fb ? FALLBACK_SCALE[wnt.kind] : 1;
      const y = wnt.block >= 0 ? 0.1 : terrainHeight(wnt.x, wnt.z) - (wnt.kind === 'stone' || wnt.kind === 'boulder' ? 0.06 : 0.0);
      const base = mat4(wnt.x, y, wnt.z, wnt.rot, wnt.scale * fs);
      const ob: Obstacle = {
        key: `${wnt.kind}${n++}`,
        kind: wnt.kind,
        x: wnt.x,
        z: wnt.z,
        y,
        r: spec.r * wnt.scale,
        h: spec.h * wnt.scale,
        tool: spec.tool,
        hits: spec.hits,
        drops: spec.drops,
        block: wnt.block,
        plot: wnt.plot,
        respawn: wnt.respawn,
        collider: null,
        colliderR: spec.collide * wnt.scale,
        pieces: [],
        alive: true,
        shake: 0,
      };
      if (ob.colliderR > 0) {
        ob.collider = { x: wnt.x, z: wnt.z, r: ob.colliderR };
        this.colliders.circles.push(ob.collider);
      }
      let g = byModel.get(model);
      if (!g) byModel.set(model, (g = { mats: [], obs: [], wind: wnt.kind === 'weed' ? 'crop' : 'none' }));
      ob.pieces.push({ model, meshes: [], index: g.mats.length, base });
      g.mats.push(base);
      g.obs.push(ob);
      this.obstacles.push(ob);
    }
    for (const [model, g] of byModel) {
      const meshes = this.instanced(model, g.mats, g.wind);
      for (const ob of g.obs) for (const p of ob.pieces) if (p.model === model) p.meshes = meshes;
    }

    // daisies and scrub in the overgrown blocks, purely for looks
    for (let bi = 1; bi < BLOCK_PLOTS.length; bi++) {
      const b = BLOCK_PLOTS[bi]!;
      const daisies: Matrix4[] = [];
      const scrub: Matrix4[] = [];
      for (let col = b.cols[0]; col <= b.cols[1]; col++) {
        for (let row = b.rows[0]; row <= b.rows[1]; row++) {
          const x = FIELD.x0 + (col + 0.5) * PLOT;
          const z = FIELD.z0 + (row + 0.5) * PLOT;
          if (rng() < 0.55) daisies.push(mat4(x + (rng() - 0.5) * PLOT * 0.8, 0.1, z + (rng() - 0.5) * PLOT * 0.8, rng() * 6, 0.9 + rng() * 0.4));
          if (rng() < 0.3) scrub.push(mat4(x + (rng() - 0.5) * PLOT * 0.7, 0.06, z + (rng() - 0.5) * PLOT * 0.7, rng() * 6, 0.22 + rng() * 0.1));
        }
      }
      this.blockDecor[bi]!.push(...this.instanced('flower_daisy', daisies, 'flower'), ...this.instanced('bush_a', scrub, 'bush'));
      const cx = FIELD.x0 + ((b.cols[0] + b.cols[1] + 1) / 2) * PLOT;
      const cz = FIELD.z0 + ((b.rows[0] + b.rows[1] + 1) / 2) * PLOT;
      this.signs[bi] = this.place('expand_sign', cx + 0.3, cz - 0.4, 0.15, 1, { y: 0.1 });
    }
  }

  private setPiece(ob: Obstacle, m: Matrix4): void {
    for (const p of ob.pieces) {
      for (const im of p.meshes) {
        im.setMatrixAt(p.index, m);
        im.instanceMatrix.needsUpdate = true;
      }
    }
  }

  /** A swing landed on an obstacle. */
  hitObstacle(ob: Obstacle): void {
    ob.shake = 0.35;
    const y = ob.y + ob.h * 0.5;
    if (ob.tool === 'axe') {
      for (let i = 0; i < 9; i++) {
        const a = Math.random() * 6.28;
        this.particles.emit({ x: ob.x, y, z: ob.z, vx: Math.cos(a) * 1.6, vy: 1.6 + Math.random() * 1.5, vz: Math.sin(a) * 1.6, life: 0.9, size: 0.05 + Math.random() * 0.04, r: 0.85, g: 0.66, b: 0.42, alpha: 1, sprite: Sprite.Leaf, gravity: 8, floor: ob.y, rot: Math.random() * 6, spin: (Math.random() - 0.5) * 14, fadeIn: 0.01 });
      }
    } else if (ob.tool === 'pick') {
      for (let i = 0; i < 10; i++) {
        const a = Math.random() * 6.28;
        this.particles.emit({ x: ob.x, y, z: ob.z, vx: Math.cos(a) * 1.8, vy: 1.4 + Math.random() * 1.6, vz: Math.sin(a) * 1.8, life: 0.8, size: 0.04 + Math.random() * 0.04, r: 0.55, g: 0.54, b: 0.52, alpha: 1, sprite: Sprite.Puff, gravity: 9, floor: ob.y, fadeIn: 0.01 });
      }
      for (let i = 0; i < 5; i++) this.particles.emit({ x: ob.x, y, z: ob.z, vx: (Math.random() - 0.5) * 3, vy: 1 + Math.random() * 2, vz: (Math.random() - 0.5) * 3, life: 0.25, size: 0.05, sizeEnd: 0.01, r: 2.4, g: 1.9, b: 1.2, alpha: 1, sprite: Sprite.Spark, additive: true, fadeIn: 0.01 });
      this.particles.dust(ob.x, ob.y, ob.z, 0.35);
    } else {
      this.particles.dust(ob.x, ob.y, ob.z, 0.6);
    }
  }

  /** The obstacle is gone: hide it, free its collider. */
  clearObstacle(ob: Obstacle, fx: boolean): void {
    ob.alive = false;
    ob.shake = 0;
    this.setPiece(ob, ZERO);
    if (ob.collider) ob.collider.r = 0;
    if (!fx) return;
    this.particles.dust(ob.x, ob.y, ob.z, ob.kind === 'log' || ob.kind === 'boulder' ? 1.4 : 0.8);
    if (ob.kind === 'weed') {
      for (let i = 0; i < 8; i++) this.particles.emit({ x: ob.x, y: ob.y + 0.3, z: ob.z, vx: (Math.random() - 0.5) * 1.6, vy: 1.2 + Math.random() * 1.2, vz: (Math.random() - 0.5) * 1.6, life: 1.0, size: 0.12, sizeEnd: 0.05, r: 0.35, g: 0.55, b: 0.2, alpha: 1, sprite: Sprite.Leaf, gravity: 4, drag: 1.2, wind: 0.8, rot: Math.random() * 6, spin: (Math.random() - 0.5) * 10, floor: ob.y });
    }
  }

  restoreObstacle(ob: Obstacle): void {
    ob.alive = true;
    this.setPiece(ob, ob.pieces[0]!.base);
    if (ob.collider) ob.collider.r = ob.colliderR;
  }

  /** Remove the block's decorations and sign once it is fully cleared. */
  clearBlock(bi: number, fx: boolean): void {
    for (const m of this.blockDecor[bi] ?? []) m.visible = false;
    const sg = this.signs[bi];
    if (sg) sg.visible = false;
    if (!fx) return;
    const b = BLOCK_PLOTS[bi]!;
    for (let col = b.cols[0]; col <= b.cols[1]; col += 2) {
      for (let row = b.rows[0]; row <= b.rows[1]; row += 2) this.particles.dust(FIELD.x0 + (col + 1) * PLOT, 0.15, FIELD.z0 + (row + 1) * PLOT, 0.8);
    }
  }

  signPosition(bi: number, out: Vector3): Vector3 {
    const b = BLOCK_PLOTS[bi]!;
    return out.set(FIELD.x0 + ((b.cols[0] + b.cols[1] + 1) / 2) * PLOT, 0.1, FIELD.z0 + ((b.rows[0] + b.rows[1] + 1) / 2) * PLOT);
  }

  // ------------------------------------------------------------------ apples
  shakeTree(t: AppleTree, n: number): void {
    this.appleShake.set(t.key, 1.1);
    for (let i = 0; i < n; i++) {
      const obj = this.appleSrc ? this.appleSrc.clone(true) : new Mesh(new SphereGeometry(0.045, 14, 10), new MeshStandardMaterial({ color: 0xb8322a, roughness: 0.4 }));
      if (this.appleSrc) this.lib.apply(obj);
      obj.scale.setScalar(1.15);
      const a = Math.random() * 6.28;
      const r = 0.6 + Math.random() * 1.3;
      const p = new Vector3(t.x + Math.cos(a) * r, terrainHeight(t.x, t.z) + 2.4 + Math.random() * 1.2, t.z + Math.sin(a) * r);
      obj.position.copy(p);
      this.group.add(obj);
      this.apples.push({ obj, p, v: new Vector3((Math.random() - 0.5) * 0.6, 0, (Math.random() - 0.5) * 0.6), rest: false, age: -i * 0.18 - Math.random() * 0.2 });
    }
    // a little shower of leaves
    for (let i = 0; i < 14; i++) {
      const a = Math.random() * 6.28;
      const r = Math.random() * 1.8;
      this.particles.emit({ x: t.x + Math.cos(a) * r, y: terrainHeight(t.x, t.z) + 2.6 + Math.random() * 1.4, z: t.z + Math.sin(a) * r, vx: 0, vy: -0.4, vz: 0, life: 2.4, size: 0.1, r: 0.32, g: 0.55, b: 0.2, alpha: 1, sprite: Sprite.Leaf, gravity: 1.2, drag: 1.5, wind: 1.2, rot: Math.random() * 6, spin: (Math.random() - 0.5) * 6, floor: terrainHeight(t.x, t.z) });
    }
  }

  /** Apples within reach of `pos` are picked up. Returns how many. */
  collectApples(pos: Vector3, reach: number): number {
    let got = 0;
    for (let i = this.apples.length - 1; i >= 0; i--) {
      const a = this.apples[i]!;
      if (a.age < 0.5) continue;
      if (Math.hypot(a.p.x - pos.x, a.p.z - pos.z) > reach) continue;
      a.obj.removeFromParent();
      this.apples.splice(i, 1);
      got++;
    }
    return got;
  }

  // ------------------------------------------------------------------ hens
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

  /** Grain scattered in the run: hens come running. */
  scatterGrain(): void {
    this.grainT = 6;
    for (let i = 0; i < 24; i++) {
      const a = Math.random() * 6.28;
      const r = Math.random() * 0.9;
      this.particles.emit({ x: this.runCentre.x + Math.cos(a) * r * 0.3, y: this.runCentre.y + 1.0, z: this.runCentre.z + Math.sin(a) * r * 0.3, vx: Math.cos(a) * r * 1.6, vy: 0.6, vz: Math.sin(a) * r * 1.6, life: 1.6, size: 0.035, r: 0.86, g: 0.72, b: 0.4, alpha: 1, sprite: Sprite.Puff, gravity: 7, floor: this.runCentre.y + 0.01, fadeIn: 0.01 });
    }
    for (const h of this.hens) {
      const a = Math.random() * 6.28;
      h.tx = this.runCentre.x + Math.cos(a) * 0.45;
      h.tz = this.runCentre.z + Math.sin(a) * 0.45;
      h.wait = 0.2;
    }
  }

  // ------------------------------------------------------------------ people
  wave(): void {
    this.courierWave = 1.6;
  }
  waveWren(): void {
    this.wrenWave = 1.6;
  }
  setStallVisible(v: boolean): void {
    if (this.stall) this.stall.visible = v;
    if (this.wren) this.wren.visible = v;
  }
  get stallVisible(): boolean {
    return this.stall ? this.stall.visible : this.wren ? this.wren.visible : false;
  }

  // ------------------------------------------------------------------ wagon
  /** Place wagon + pony at distance d along the route; `moved` spins the wheels. */
  private poseWagon(d: number, moved: number): void {
    const pos = new Vector3();
    const tan = new Vector3();
    this.route.at(d, pos, tan);
    const home = d < 0.01;
    const rot = home ? ROYAL.wagon.rot : Math.atan2(tan.x, tan.z);
    if (home) pos.set(ROYAL.wagon.x, 0, ROYAL.wagon.z);
    if (this.wagon) {
      this.wagon.position.set(pos.x, terrainHeight(pos.x, pos.z), pos.z);
      this.wagon.rotation.y = rot;
      for (const w of this.wheels) w.o.rotateX(moved / w.r);
    }
    if (this.pony) {
      const pp = new Vector3();
      const pt = new Vector3();
      if (home) {
        pp.set(pos.x + Math.sin(rot) * this.ponyAhead, 0, pos.z + Math.cos(rot) * this.ponyAhead);
        pt.set(Math.sin(rot), 0, Math.cos(rot));
      } else {
        const pd = d + this.ponyAhead;
        if (pd <= this.route.total) this.route.at(pd, pp, pt);
        else {
          this.route.at(this.route.total, pp, pt);
          pp.addScaledVector(pt, pd - this.route.total);
        }
      }
      this.pony.position.set(pp.x, terrainHeight(pp.x, pp.z), pp.z);
      this.pony.rotation.y = Math.atan2(pt.x, pt.z);
    }
    if (this.wagonCollider) {
      const fx = Math.sin(rot);
      const fz = Math.cos(rot);
      const away = d > 0.5;
      this.wagonCollider.ax = pos.x - fx * 1.3;
      this.wagonCollider.az = pos.z - fz * 1.3;
      this.wagonCollider.bx = pos.x + fx * 1.1;
      this.wagonCollider.bz = pos.z + fz * 1.1;
      this.wagonCollider.r = away && d > 20 ? 0 : 0.85;
    }
  }

  /** Where the wagon is now (for markers). */
  wagonPosition(out: Vector3): Vector3 {
    return out.copy(this.wagon ? this.wagon.position : this.cratePos);
  }

  private updateWagon(s: GameState): void {
    const W = s.wagon;
    const total = this.route.total;
    let k = 0;
    let visible = true;
    if (W.phase === 'leaving') k = easeInOutSoft(W.t / LEAVE_TIME);
    else if (W.phase === 'away') {
      k = 1;
      visible = false;
    } else if (W.phase === 'returning') k = 1 - easeInOutSoft(W.t / LEAVE_TIME);
    const d = k * total;
    const moved = d - this.wagonDist;
    this.wagonDist = d;
    this.poseWagon(d, moved);
    const far = d > total - 8;
    if (this.wagon) this.wagon.visible = visible && !far;
    if (this.pony) this.pony.visible = visible && !far;
    this.wagonAway = W.phase !== 'home';
    if (this.courier) this.courier.visible = !this.wagonAway;
    if (this.crate) this.crate.visible = !this.wagonAway;
    for (const g of this.crateGoods) g.visible = !this.wagonAway;

    // pony gait
    const walking = Math.abs(moved) > 0.0005;
    this.ponyPhase += Math.abs(moved) * 2.4;
    for (const L of this.ponyLegs) {
      const a = walking ? Math.sin(this.ponyPhase + L.phase) * 0.42 : 0;
      _q.setFromAxisAngle(_x, a);
      L.o.quaternion.copy(L.rest).multiply(_q);
    }
    if (this.ponyHead) {
      const rest = this.ponyHead.userData.rest as Quaternion;
      const graze = Math.max(0, Math.sin(this.time * 0.21)) > 0.85 ? 0.35 : 0;
      const nod = walking ? Math.sin(this.ponyPhase * 2) * 0.05 : Math.sin(this.time * 0.7) * 0.04 + graze;
      _q.setFromAxisAngle(_x, nod);
      this.ponyHead.quaternion.copy(rest).multiply(_q);
    }
    if (this.ponyTail) {
      const rest = this.ponyTail.userData.rest as Quaternion;
      _q.setFromAxisAngle(_y, Math.sin(this.time * 1.9) * 0.25 + Math.sin(this.time * 4.1) * 0.08);
      this.ponyTail.quaternion.copy(rest).multiply(_q);
    }
  }

  /** Goods visibly packed in the crate (up to six). */
  setCrateGoods(items: ItemId[]): void {
    const key = items.join(',');
    if (key === this.crateGoodsKey) return;
    this.crateGoodsKey = key;
    for (const g of this.crateGoods) g.removeFromParent();
    this.crateGoods.length = 0;
    if (!this.crate) return;
    const inside = findByPrefix(this.crate, 'crate_inside');
    const base = inside ? inside.getWorldPosition(new Vector3()) : this.cratePos.clone().setY(this.cratePos.y + 0.45);
    items.slice(0, 6).forEach((id, i) => {
      const src = this.assets.clone(MODEL_OF[id] ?? `item_${id}`) ?? this.assets.clone('item_wheat');
      if (!src) return;
      this.lib.apply(src, 'none', { cast: true });
      const a = (i / 6) * Math.PI * 2;
      src.position.set(base.x + Math.cos(a) * 0.2 * (i > 0 ? 1 : 0), base.y, base.z + Math.sin(a) * 0.16 * (i > 0 ? 1 : 0));
      src.rotation.y = a * 2.3;
      src.scale.setScalar(0.9);
      src.visible = !this.wagonAway;
      this.group.add(src);
      this.crateGoods.push(src);
    });
  }

  // ------------------------------------------------------------------ fireworks
  startFireworks(seconds: number): void {
    this.fireworksLeft = seconds;
    this.fireT = 0;
  }
  get fireworksActive(): boolean {
    return this.fireworksLeft > 0 || this.rockets.length > 0;
  }

  private updateFireworks(dt: number): void {
    const cx = CASTLE.x;
    const cz = CASTLE.z;
    const cy = terrainHeight(cx, cz);
    if (this.fireworksLeft > 0) {
      this.fireworksLeft -= dt;
      this.fireT -= dt;
      if (this.fireT <= 0) {
        this.fireT = 0.35 + Math.random() * 0.7;
        const from = new Vector3(cx + (Math.random() - 0.5) * 40, cy + 40, cz + (Math.random() - 0.5) * 40);
        const to = new Vector3(from.x + (Math.random() - 0.5) * 50, cy + 100 + Math.random() * 60, from.z + (Math.random() - 0.5) * 50);
        this.rockets.push({ t: 0, fuse: 1.3 + Math.random() * 0.5, from, to, hue: Math.random() });
      }
    }
    for (let i = this.rockets.length - 1; i >= 0; i--) {
      const r = this.rockets[i]!;
      r.t += dt;
      const k = Math.min(r.t / r.fuse, 1);
      const e = 1 - (1 - k) * (1 - k);
      _p.lerpVectors(r.from, r.to, e);
      this.particles.emit({ x: _p.x, y: _p.y, z: _p.z, life: 0.6, size: 3.6, sizeEnd: 0.6, r: 2.6, g: 1.9, b: 1.1, alpha: 0.9, sprite: Sprite.Spark, additive: true, fadeIn: 0.02 });
      if (k >= 1) {
        this.rockets.splice(i, 1);
        const col = new Color().setHSL(r.hue, 0.85, 0.62);
        for (let j = 0; j < 90; j++) {
          const u = Math.random() * 2 - 1;
          const th = Math.random() * 6.283;
          const sr = Math.sqrt(1 - u * u);
          const sp = 26 + Math.random() * 9;
          const white = Math.random() < 0.25;
          this.particles.emit({ x: r.to.x, y: r.to.y, z: r.to.z, vx: sr * Math.cos(th) * sp, vy: u * sp, vz: sr * Math.sin(th) * sp, life: 2.2 + Math.random() * 1.0, size: 5.5, sizeEnd: 1.2, r: white ? 2.8 : col.r * 3, g: white ? 2.4 : col.g * 3, b: white ? 1.6 : col.b * 3, alpha: 1, sprite: Sprite.Spark, additive: true, gravity: 5, drag: 1.2, fadeIn: 0.01 });
        }
        this.particles.emit({ x: r.to.x, y: r.to.y, z: r.to.z, life: 0.6, size: 30, sizeEnd: 70, r: col.r * 2, g: col.g * 2, b: col.b * 2, alpha: 0.5, sprite: Sprite.Puff, additive: true, fadeIn: 0.02 });
        this.onBurst?.(r.to.clone());
      }
    }
  }

  // ------------------------------------------------------------------ buildings
  doorOf(id: BuildingId): Vector3 {
    return this.plots.get(id)!.door;
  }
  siteCentre(id: BuildingId, out: Vector3): Vector3 {
    const s = SITES[id];
    return out.set(s.x, terrainHeight(s.x, s.z), s.z);
  }

  private addFootprint(id: BuildingId): void {
    const p = this.plots.get(id);
    if (!p?.building) return;
    const s = SITES[id];
    p.building.updateMatrixWorld(true);
    const box = new Box3();
    const inv = new Matrix4().copy(p.building.matrixWorld).invert();
    p.building.traverse((o) => {
      const m = o as Mesh;
      if (!m.isMesh) return;
      for (let a: Object3D | null = o; a; a = a.parent) if (a.name.startsWith('windmill_sails')) return;
      m.geometry.computeBoundingBox();
      box.union(m.geometry.boundingBox!.clone().applyMatrix4(_m.copy(inv).multiply(m.matrixWorld)));
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

  private finish(id: BuildingId, fx: boolean): void {
    const p = this.plots.get(id)!;
    p.shownBuilt = true;
    if (p.site) p.site.visible = false;
    if (p.scaffold) p.scaffold.visible = false;
    if (p.building) p.building.visible = true;
    p.pop = fx ? 0 : 99;
    this.addFootprint(id);
    if (id === 'henhouse') {
      this.spawnHens();
      if (this.nest) this.nest.visible = true;
    }
    if (id === 'windmill' && this.hopper) this.hopper.visible = true;
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

  /** Apply saved state instantly. */
  sync(s: GameState): void {
    for (const id of BUILDING_IDS) {
      const st = s.buildings[id];
      const p = this.plots.get(id)!;
      if (st.built && st.progress >= 1 && !p.shownBuilt) this.finish(id, false);
    }
    for (const ob of this.obstacles) {
      const gone = ob.respawn ? (s.clearedDay[ob.key] ?? -1) >= s.stats.days : !!s.cleared[ob.key];
      if (gone && ob.alive) this.clearObstacle(ob, false);
      else if (!gone && !ob.alive) this.restoreObstacle(ob);
    }
    for (let bi = 1; bi < 4; bi++) if (s.blocks[bi]) this.clearBlock(bi, false);
    this.setStallVisible(s.chapter >= 2);
    this.wagonDist = -1;
  }

  // ------------------------------------------------------------------ per frame
  update(dt: number, s: GameState, eye: Vector3, glow: number): void {
    this.time += dt;
    for (const l of this.lights) l.intensity = (l.userData.base as number) * glow * (l.userData.wagon && this.wagonAway ? 0 : 1);
    if (this.stallLamp) this.stallLamp.intensity = this.stallVisible ? 4 * glow : 0;
    for (const p of this.plots.values()) for (const l of p.lamps) l.intensity = p.shownBuilt ? (l.userData.base as number) * glow : 0;

    // construction
    for (const id of BUILDING_IDS) {
      const st = s.buildings[id];
      const p = this.plots.get(id)!;
      if (st.built && st.progress < 1) {
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
      const busy = s.mill.work.length > 0;
      this.sailSpeed = damp(this.sailSpeed, busy ? 1.6 : 0.28, 0.8, dt);
      this.sails.rotateZ(this.sailSpeed * dt);
    }
    // flour sacks waiting by the hopper, eggs in the nest, the compost heap
    this.sacks.forEach((sk, i) => (sk.visible = s.buildings.windmill.built && i < s.mill.ready));
    this.eggs.forEach((e, i) => (e.visible = s.buildings.henhouse.built && i < s.hens.ready));
    if (this.heap) {
      const rest = this.heap.userData.rest as Vector3;
      const fill = clamp((s.compost.work.length + s.compost.ready) / 4, 0.12, 1);
      const cur = this.heap.scale.y / Math.max(rest.y, 1e-4);
      this.heap.scale.set(rest.x, rest.y * damp(cur, fill, 3, dt), rest.z);
    }

    // bakehouse: smoke + oven glow while baking, the finished dish on the oven's lip
    const baking = s.buildings.bakehouse.built && s.oven.recipe !== null && !s.oven.ready;
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
    const dk = s.oven.ready ?? '';
    if (dk !== this.dishKey) {
      this.dishKey = dk;
      this.dish?.removeFromParent();
      this.dish = null;
      if (s.oven.ready) {
        const d = this.assets.clone(MODEL_OF[s.oven.ready] ?? `item_${s.oven.ready}`);
        if (d) {
          this.lib.apply(d);
          const s2 = SITES.bakehouse;
          const fx = Math.sin(s2.rot);
          const fz = Math.cos(s2.rot);
          d.position.set(this.ovenPos.x + fx * 0.45, this.ovenFound ? this.ovenPos.y - 0.18 : this.ovenPos.y, this.ovenPos.z + fz * 0.45);
          d.scale.setScalar(1.2);
          this.group.add(d);
          this.dish = d;
        }
      }
    }

    // hens wander inside their run, crowd round scattered grain, and peck
    if (this.grainT > 0) this.grainT -= dt;
    for (const h of this.hens) {
      h.wait -= dt;
      const dx = h.tx - h.x;
      const dz = h.tz - h.z;
      const d = Math.hypot(dx, dz);
      if (d > 0.05) {
        const sp = Math.min(this.grainT > 0 ? 1.1 : 0.55, d * 2);
        h.x += (dx / d) * sp * dt;
        h.z += (dz / d) * sp * dt;
        let da = Math.atan2(dx, dz) - h.yaw;
        while (da > Math.PI) da -= Math.PI * 2;
        while (da < -Math.PI) da += Math.PI * 2;
        h.yaw += da * Math.min(1, dt * 8);
      } else if (h.wait <= 0) {
        if (this.grainT > 0 || Math.random() < 0.55) h.peck = 0.6;
        else {
          h.tx = this.runCentre.x + (Math.random() - 0.5) * this.runHalf.x * 1.6;
          h.tz = this.runCentre.z + (Math.random() - 0.5) * this.runHalf.z * 1.6;
        }
        h.wait = this.grainT > 0 ? 0.3 + Math.random() * 0.5 : 0.8 + Math.random() * 2.2;
      }
      h.peck = Math.max(0, h.peck - dt);
      const hop = d > 0.05 ? Math.abs(Math.sin(this.time * 14 + h.x)) * 0.025 : 0;
      h.obj.position.set(h.x, terrainHeight(h.x, h.z) + hop, h.z);
      h.obj.rotation.y = h.yaw;
      if (h.head) {
        const rest = h.head.userData.rest as Quaternion;
        const pk = h.peck > 0 ? Math.sin((h.peck / 0.6) * Math.PI * 3) * 0.5 + 0.4 : Math.sin(this.time * 2 + h.z) * 0.08;
        _q.setFromAxisAngle(_x, pk);
        h.head.quaternion.copy(rest).multiply(_q);
      }
    }

    // obstacles shiver after a hit
    for (const ob of this.obstacles) {
      if (ob.shake <= 0 || !ob.alive) continue;
      ob.shake = Math.max(0, ob.shake - dt);
      const k = ob.shake / 0.35;
      const base = ob.pieces[0]!.base;
      if (ob.shake <= 0) {
        this.setPiece(ob, base);
        continue;
      }
      _q.setFromAxisAngle(_z, Math.sin(this.time * 60) * 0.06 * k);
      _q2.setFromAxisAngle(_x, Math.cos(this.time * 47) * 0.05 * k);
      _q.multiply(_q2);
      const pos = new Vector3().setFromMatrixPosition(base);
      const m = base.clone().setPosition(0, 0, 0).premultiply(_m.makeRotationFromQuaternion(_q)).setPosition(pos);
      this.setPiece(ob, m);
    }

    // apple trees sway when shaken; apples fall, bounce and settle
    for (const t of this.appleTrees) {
      const k = this.appleShake.get(t.key) ?? 0;
      if (k <= 0) continue;
      const nk = Math.max(0, k - dt);
      this.appleShake.set(t.key, nk);
      _q.setFromAxisAngle(_z, Math.sin(this.time * 22) * 0.045 * (nk / 1.1));
      const pos = new Vector3().setFromMatrixPosition(t.base);
      const m = nk > 0 ? t.base.clone().setPosition(0, 0, 0).premultiply(_m.makeRotationFromQuaternion(_q)).setPosition(pos) : t.base;
      for (const im of t.meshes) {
        im.setMatrixAt(t.index, m);
        im.instanceMatrix.needsUpdate = true;
      }
    }
    for (const a of this.apples) {
      a.age += dt;
      if (a.age < 0 || a.rest) continue;
      a.v.y -= 9.8 * dt;
      a.p.addScaledVector(a.v, dt);
      const gy = terrainHeight(a.p.x, a.p.z) + 0.035;
      if (a.p.y < gy) {
        a.p.y = gy;
        if (Math.abs(a.v.y) < 0.6) {
          a.v.set(0, 0, 0);
          a.rest = true;
        } else {
          a.v.y = -a.v.y * 0.35;
          a.v.x *= 0.6;
          a.v.z *= 0.6;
        }
      }
      a.obj.position.copy(a.p);
      a.obj.rotation.x += dt * 4;
    }

    // the wagon on the road, the sky over the castle
    this.updateWagon(s);
    this.updateFireworks(dt);

    // banner sways
    if (this.bannerCloth) {
      this.bannerCloth.rotation.z = Math.sin(this.time * 1.3) * 0.06 + Math.sin(this.time * 3.1) * 0.025;
      this.bannerCloth.rotation.x = Math.sin(this.time * 0.9 + 1) * 0.05;
    }

    // Pip and Wren: breathe, follow you with their eyes, wave
    this.animatePerson(this.courier, this.courierHead, this.courierArmR, this.courierArmL, eye, this.courierWave, 1.7, dt);
    this.courierWave = Math.max(0, this.courierWave - dt);
    if (this.stallVisible) this.animatePerson(this.wren, this.wrenHead, this.wrenArmR, null, eye, this.wrenWave, 1.5, dt);
    this.wrenWave = Math.max(0, this.wrenWave - dt);
  }

  private animatePerson(body: Object3D | null, head: Object3D | null, armR: Object3D | null, armL: Object3D | null, eye: Vector3, wave: number, rate: number, dt: number): void {
    if (!body || !body.visible) return;
    const dx = eye.x - body.position.x;
    const dz = eye.z - body.position.z;
    const near = Math.hypot(dx, dz) < 9;
    body.scale.y = 1 + Math.sin(this.time * rate) * 0.006;
    if (head) {
      const rest = head.userData.rest as Quaternion;
      let yaw = 0;
      if (near) {
        yaw = Math.atan2(dx, dz) - body.rotation.y;
        while (yaw > Math.PI) yaw -= Math.PI * 2;
        while (yaw < -Math.PI) yaw += Math.PI * 2;
        yaw = clamp(yaw, -1.0, 1.0);
      } else yaw = Math.sin(this.time * 0.3) * 0.35;
      const cur = (head.userData.yaw as number | undefined) ?? 0;
      const ny = damp(cur, yaw, 4, dt);
      head.userData.yaw = ny;
      _q.setFromAxisAngle(_y, ny);
      head.quaternion.copy(rest).premultiply(_q);
    }
    if (armR) {
      const rest = armR.userData.rest as Quaternion;
      const w = wave > 0 ? Math.min(1, wave * 3, (1.6 - wave) * 4) : 0;
      _q.setFromAxisAngle(_z, -(w * 2.5 + Math.sin(this.time * 9) * 0.3 * w));
      _q2.setFromAxisAngle(_x, Math.sin(this.time * rate) * 0.03);
      armR.quaternion.copy(rest).multiply(_q).multiply(_q2);
    }
    if (armL) {
      const rest = armL.userData.rest as Quaternion;
      _q.setFromAxisAngle(_x, Math.sin(this.time * rate + 0.5) * 0.03);
      armL.quaternion.copy(rest).multiply(_q);
    }
  }
}
