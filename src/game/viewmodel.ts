import { Group, Matrix4, Mesh, Quaternion, Vector3, type Object3D, type PerspectiveCamera } from 'three';
import { findByPrefix, type Assets } from '../core/assets';
import type { MaterialLib } from '../core/materials';
import { clamp, damp, easeInOut } from '../util/math';

export type ToolId = 'hoe' | 'seeds' | 'water' | 'harvest';
export const TOOL_IDS: ToolId[] = ['hoe', 'seeds', 'water', 'harvest'];
const TOOL_ASSET: Record<ToolId, string> = { hoe: 'tool_hoe', seeds: 'tool_seed_bag', water: 'tool_watering_can', harvest: 'tool_basket' };

/** Duration of each tool's use animation and the moment (0..1) it takes effect. */
export const ACTION: Record<ToolId, { time: number; hit: number }> = {
  hoe: { time: 0.62, hit: 0.5 },
  seeds: { time: 0.5, hit: 0.48 },
  water: { time: 0.95, hit: 0.3 },
  harvest: { time: 0.48, hit: 0.5 },
};

/**
 * A pose of the held tool in camera space. `up` is where the tool's local +Y points
 * (the shaft / handle-up axis), `fwd` where its local +Z points (hoe blade, can spout).
 */
interface Pose {
  p: [number, number, number];
  up: [number, number, number];
  fwd: [number, number, number];
}
interface Key extends Pose {
  t: number;
}

interface ToolRig {
  rest: Pose;
  keys: Key[];
  /** Axis of the handle in tool space that the right hand closes around. */
  gripAxis: Vector3;
  /** Grip point in tool space. */
  gripAt: Vector3;
  /** Roll of the hand about the handle (radians). */
  roll: number;
  /** Direction the forearm runs from the wrist, in camera space. */
  fore: [number, number, number];
  /** Left hand pose in camera space while this tool is held (null = off screen). */
  left: Pose | null;
  leftKeys: Key[] | null;
}

const RIGS: Record<ToolId, ToolRig> = {
  hoe: {
    rest: { p: [0.3, -0.38, -0.48], up: [-0.16, 0.8, -0.56], fwd: [0.02, -0.55, -0.83] },
    keys: [
      { t: 0.0, p: [0.3, -0.38, -0.48], up: [-0.16, 0.8, -0.56], fwd: [0.02, -0.55, -0.83] },
      { t: 0.36, p: [0.22, -0.16, -0.34], up: [-0.2, 0.98, 0.1], fwd: [0.0, 0.15, -1.0] },
      { t: 0.5, p: [0.18, -0.42, -0.72], up: [-0.15, 0.25, -0.96], fwd: [0.03, -0.97, -0.25] },
      { t: 0.62, p: [0.18, -0.44, -0.7], up: [-0.17, 0.28, -0.94], fwd: [0.03, -0.96, -0.28] },
      { t: 1.0, p: [0.3, -0.38, -0.48], up: [-0.16, 0.8, -0.56], fwd: [0.02, -0.55, -0.83] },
    ],
    gripAxis: new Vector3(0, 1, 0),
    gripAt: new Vector3(0, 0, 0),
    roll: 0,
    fore: [0.25, -0.9, 0.4],
    left: null,
    leftKeys: null,
  },
  seeds: {
    rest: { p: [0.25, -0.24, -0.46], up: [0.05, 1, 0.15], fwd: [-0.35, 0, -1] },
    keys: [
      { t: 0.0, p: [0.25, -0.24, -0.46], up: [0.05, 1, 0.15], fwd: [-0.35, 0, -1] },
      { t: 0.3, p: [0.24, -0.22, -0.44], up: [0.15, 1, 0.25], fwd: [-0.45, 0, -1] },
      { t: 1.0, p: [0.25, -0.24, -0.46], up: [0.05, 1, 0.15], fwd: [-0.35, 0, -1] },
    ],
    gripAxis: new Vector3(1, 0, 0),
    gripAt: new Vector3(0, 0.01, 0),
    roll: 0,
    fore: [0.4, -0.75, 0.5],
    left: { p: [-0.21, -0.3, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
    leftKeys: [
      { t: 0.0, p: [-0.21, -0.3, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
      { t: 0.28, p: [-0.16, -0.33, -0.42], up: [0.3, 1, 0.3], fwd: [0.4, 0, -1] },
      { t: 0.5, p: [-0.08, -0.2, -0.74], up: [0.1, 0.55, 0.85], fwd: [0.15, 0.5, -1] },
      { t: 1.0, p: [-0.21, -0.3, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
    ],
  },
  water: {
    rest: { p: [0.29, -0.16, -0.56], up: [0, 1, 0.05], fwd: [-1, 0, -0.35] },
    keys: [
      { t: 0.0, p: [0.29, -0.16, -0.56], up: [0, 1, 0.05], fwd: [-1, 0, -0.35] },
      { t: 0.22, p: [0.2, -0.17, -0.6], up: [-0.65, 0.72, -0.15], fwd: [-0.72, -0.66, -0.2] },
      { t: 0.75, p: [0.2, -0.18, -0.61], up: [-0.7, 0.68, -0.15], fwd: [-0.68, -0.72, -0.2] },
      { t: 1.0, p: [0.29, -0.16, -0.56], up: [0, 1, 0.05], fwd: [-1, 0, -0.35] },
    ],
    gripAxis: new Vector3(0, 0, 1),
    gripAt: new Vector3(0, 0, 0),
    roll: 0,
    fore: [0.35, -0.45, 0.8],
    left: null,
    leftKeys: null,
  },
  harvest: {
    rest: { p: [0.27, -0.2, -0.5], up: [0, 1, 0.05], fwd: [-0.2, 0, -1] },
    keys: [
      { t: 0.0, p: [0.27, -0.2, -0.5], up: [0, 1, 0.05], fwd: [-0.2, 0, -1] },
      { t: 0.5, p: [0.25, -0.23, -0.52], up: [0.05, 1, 0.0], fwd: [-0.2, 0, -1] },
      { t: 1.0, p: [0.27, -0.2, -0.5], up: [0, 1, 0.05], fwd: [-0.2, 0, -1] },
    ],
    gripAxis: new Vector3(1, 0, 0),
    gripAt: new Vector3(0, 0, 0),
    roll: 0,
    fore: [0.35, -0.5, 0.8],
    left: { p: [-0.23, -0.34, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
    leftKeys: [
      { t: 0.0, p: [-0.23, -0.34, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
      { t: 0.42, p: [-0.06, -0.44, -0.8], up: [0.1, -0.8, -0.3], fwd: [0.15, -0.5, -1] },
      { t: 0.62, p: [-0.08, -0.36, -0.72], up: [0.1, -0.7, -0.3], fwd: [0.15, -0.3, -1] },
      { t: 1.0, p: [-0.23, -0.34, -0.48], up: [0.25, 1, 0.15], fwd: [0.35, 0.05, -1] },
    ],
  },
};

const _m = new Matrix4();
const _x = new Vector3();
const _y = new Vector3();
const _z = new Vector3();
const _qa = new Quaternion();
const _qb = new Quaternion();
const _pa = new Vector3();
const _pb = new Vector3();

function poseQuat(p: Pose, out: Quaternion): Quaternion {
  _y.set(p.up[0], p.up[1], p.up[2]).normalize();
  _z.set(p.fwd[0], p.fwd[1], p.fwd[2]);
  _z.addScaledVector(_y, -_z.dot(_y)).normalize();
  _x.crossVectors(_y, _z);
  _m.makeBasis(_x, _y, _z);
  return out.setFromRotationMatrix(_m);
}

function samplePose(keys: Key[], t: number, outP: Vector3, outQ: Quaternion): void {
  let i = 0;
  while (i < keys.length - 2 && t > keys[i + 1]!.t) i++;
  const a = keys[i]!;
  const b = keys[i + 1]!;
  const u = easeInOut(clamp((t - a.t) / Math.max(b.t - a.t, 1e-4), 0, 1));
  _pa.set(...a.p);
  _pb.set(...b.p);
  outP.lerpVectors(_pa, _pb, u);
  poseQuat(a, _qa);
  poseQuat(b, _qb);
  outQ.slerpQuaternions(_qa, _qb, u);
}

/** Arms and held tool, drawn in camera space. */
export class ViewModel {
  readonly root = new Group();
  private readonly sway = new Group();
  private readonly toolPivot = new Group();
  private readonly leftPivot = new Group();
  private readonly tools = new Map<ToolId, Object3D>();
  private readonly hands = new Map<ToolId, Object3D>();
  private leftArm: Object3D | null = null;
  private spout: Object3D | null = null;
  tool: ToolId = 'hoe';
  private shown: ToolId = 'hoe';
  private action: { tool: ToolId; t: number; fired: boolean; onHit: () => void } | null = null;
  /** 0 = held up, 1 = lowered out of view (tool switching, menus). */
  private lower = 1;
  private lowerTarget = 0;
  private swayX = 0;
  private swayY = 0;
  private time = 0;
  readonly hasArms: boolean;

  constructor(camera: PerspectiveCamera, assets: Assets, lib: MaterialLib) {
    this.root.name = 'viewmodel';
    camera.add(this.root);
    this.root.add(this.sway);
    this.sway.add(this.toolPivot, this.leftPivot);

    const prep = (o: Object3D): void => {
      lib.apply(o, 'none', { cast: false, receive: true });
      o.traverse((c) => {
        const m = c as Mesh;
        if (m.isMesh) m.frustumCulled = false;
      });
    };

    const armR = assets.clone('fp_arm_r');
    const armL = assets.clone('fp_arm_l');
    this.hasArms = !!armR;
    for (const id of Object.keys(TOOL_ASSET) as ToolId[]) {
      const holder = new Group();
      holder.visible = false;
      const t = assets.clone(TOOL_ASSET[id]);
      if (t) {
        prep(t);
        holder.add(t);
        if (id === 'water') this.spout = findByPrefix(t, 'spout_tip');
      }
      if (armR) {
        const hand = armR.clone(true);
        prep(hand);
        this.alignHand(hand, RIGS[id], 'fp_grip_r');
        holder.add(hand);
        this.hands.set(id, hand);
      }
      this.toolPivot.add(holder);
      this.tools.set(id, holder);
    }
    if (armL) {
      prep(armL);
      // the left arm is authored hand-forward along Blender -Y (three +Z); its palm faces the pose's fwd
      const g = new Group();
      g.add(armL);
      const grip = findByPrefix(armL, 'fp_grip_l');
      if (grip) armL.position.copy(grip.position).negate();
      this.leftPivot.add(g);
      this.leftArm = g;
    }
    this.leftPivot.visible = false;
    this.show('hoe');
  }

  /**
   * Place the right arm so its grip marker sits on the tool's grip, the fingers close around the
   * handle axis, and the forearm runs back toward the bottom-right of the screen.
   * Arm space (three.js): the gripped handle runs along +X, the forearm along -Z.
   */
  private alignHand(hand: Object3D, rig: ToolRig, marker: string): void {
    const g = findByPrefix(hand, marker);
    const gp = g ? g.position.clone() : new Vector3();
    const a = rig.gripAxis.clone().normalize();
    // desired forearm direction, camera space -> tool space at the rest pose
    const qr = poseQuat(rig.rest, new Quaternion()).invert();
    const f = new Vector3(...rig.fore).normalize().applyQuaternion(qr);
    f.addScaledVector(a, -f.dot(a)).normalize();
    if (rig.roll) f.applyAxisAngle(a, rig.roll);
    const side = new Vector3().crossVectors(a, f);
    const m = new Matrix4().makeBasis(a, side, f.clone().negate());
    const q = new Quaternion().setFromRotationMatrix(m);
    hand.quaternion.copy(q);
    hand.position.copy(gp.applyQuaternion(q).negate()).add(rig.gripAt);
  }

  /** Live tuning hook (console / tests): adjust a rig and re-seat the hand. */
  tune(id: ToolId, p: { rest?: Pose; fore?: [number, number, number]; roll?: number; gripAxis?: [number, number, number]; left?: Pose }): string {
    const rig = RIGS[id];
    if (p.rest) {
      rig.rest = p.rest;
      const k0 = rig.keys[0]!;
      const kn = rig.keys[rig.keys.length - 1]!;
      for (const k of [k0, kn]) {
        k.p = p.rest.p;
        k.up = p.rest.up;
        k.fwd = p.rest.fwd;
      }
    }
    if (p.fore) rig.fore = p.fore;
    if (p.roll !== undefined) rig.roll = p.roll;
    if (p.gripAxis) rig.gripAxis.set(...p.gripAxis);
    if (p.left) rig.left = p.left;
    const h = this.hands.get(id);
    if (h) this.alignHand(h, rig, 'fp_grip_r');
    return JSON.stringify({ rest: rig.rest, fore: rig.fore, roll: rig.roll, grip: rig.gripAxis.toArray(), left: rig.left });
  }

  private show(id: ToolId): void {
    this.shown = id;
    for (const [k, t] of this.tools) t.visible = k === id;
    const rig = RIGS[id];
    this.leftPivot.visible = !!(rig.left && this.leftArm);
  }

  setTool(id: ToolId): void {
    if (id === this.tool) return;
    this.tool = id;
    if (!this.action) this.lowerTarget = 1;
  }

  setLowered(v: boolean): void {
    this.lowerTarget = v ? 1 : 0;
  }

  get busy(): boolean {
    return this.action !== null;
  }

  /** Play the use animation; `onHit` fires at the impact frame. */
  use(tool: ToolId, onHit: () => void): boolean {
    if (this.action || this.lower > 0.3) return false;
    if (tool !== this.shown) {
      this.tool = tool;
      this.show(tool);
    }
    this.action = { tool, t: 0, fired: false, onHit };
    return true;
  }

  spoutPosition(out: Vector3): Vector3 | null {
    if (!this.spout || this.shown !== 'water') return null;
    return this.spout.getWorldPosition(out);
  }
  handPosition(out: Vector3): Vector3 {
    return (this.leftPivot.visible ? this.leftPivot : this.toolPivot).getWorldPosition(out);
  }

  update(dt: number, speed: number, phase: number, lookX: number, lookY: number, running: boolean): void {
    this.time += dt;
    // switching: lower the old tool, swap at the bottom, raise the new one
    if (!this.action) {
      if (this.shown !== this.tool && this.lower > 0.97) this.show(this.tool);
      if (this.shown !== this.tool) this.lowerTarget = 1;
      else if (this.lowerTarget === 1 && this.lower > 0.97 && !this.forcedLow) this.lowerTarget = 0;
    }
    this.lower = damp(this.lower, this.lowerTarget, this.lowerTarget > this.lower ? 16 : 9, dt);

    const rig = RIGS[this.shown];
    const p = this.toolPivot.position;
    const q = this.toolPivot.quaternion;
    let lt = -1;
    if (this.action) {
      const a = this.action;
      const spec = ACTION[a.tool];
      a.t += dt / spec.time;
      if (!a.fired && a.t >= spec.hit) {
        a.fired = true;
        a.onHit();
      }
      lt = Math.min(a.t, 1);
      samplePose(rig.keys, lt, p, q);
      if (a.t >= 1) this.action = null;
    } else {
      p.set(...rig.rest.p);
      poseQuat(rig.rest, q);
    }
    if (rig.left && this.leftArm) {
      if (lt >= 0 && rig.leftKeys) samplePose(rig.leftKeys, lt, this.leftPivot.position, this.leftPivot.quaternion);
      else {
        this.leftPivot.position.set(...rig.left.p);
        poseQuat(rig.left, this.leftPivot.quaternion);
      }
    }

    // sway lags behind the mouse, bob follows the stride, a slow breath when idle
    this.swayX = damp(this.swayX, clamp(-lookX * 0.0009, -0.05, 0.05), 7, dt);
    this.swayY = damp(this.swayY, clamp(lookY * 0.0009, -0.05, 0.05), 7, dt);
    const k = clamp(speed / 3.3, 0, 1.4);
    const bob = running ? 1.35 : 1;
    const bx = Math.cos(phase) * 0.012 * k * bob;
    const by = -Math.abs(Math.sin(phase)) * 0.016 * k * bob;
    const breath = Math.sin(this.time * 1.6) * 0.004 * (1 - Math.min(k, 1));
    const low = easeInOut(this.lower);
    this.sway.position.set(this.swayX + bx, this.swayY + by + breath - low * 0.42, low * 0.1 + (running ? 0.03 : 0));
    this.sway.rotation.set(this.swayY * 2.2 - low * 0.5 + (running ? -0.08 : 0), this.swayX * 2.5, -this.swayX * 1.6 + bx * 1.5);
  }

  /** Keep the tools down while a menu is open. */
  forcedLow = false;
  setForcedLow(v: boolean): void {
    this.forcedLow = v;
    this.lowerTarget = v ? 1 : 0;
  }
}
