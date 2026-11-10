import { Vector3, type PerspectiveCamera } from 'three';
import { clamp, damp } from '../util/math';
import { COLS, FIELD, PLOT, ROWS, pondSdf, terrainHeight, type Colliders } from '../world/layout';

export const EYE = 1.62;
const RADIUS = 0.32;
const WALK = 3.3;
const RUN = 5.6;

export interface FpInput {
  fwd: number;
  side: number;
  run: boolean;
}

/** First-person walker: mouse look, eased movement, head bob, collisions. */
export class FirstPerson {
  readonly pos = new Vector3();
  readonly vel = new Vector3();
  yaw = 0;
  pitch = -0.12;
  /** Horizontal speed (m/s), for the view model. */
  speed = 0;
  /** Walk cycle phase (radians). */
  phase = 0;
  /** Accumulated mouse motion this frame, for view-model sway. */
  readonly look = { x: 0, y: 0 };
  sensitivity = 0.0022;
  onStep: ((x: number, y: number, z: number) => void) | null = null;
  private stepAcc = 0;
  private groundY = 0;
  private bobY = 0;
  private bobX = 0;
  private roll = 0;

  constructor(private readonly camera: PerspectiveCamera) {
    camera.rotation.order = 'YXZ';
  }

  /** Feed raw mouse deltas (pointer lock). */
  mouse(dx: number, dy: number): void {
    this.yaw -= dx * this.sensitivity;
    this.pitch = clamp(this.pitch - dy * this.sensitivity, -1.45, 1.35);
    this.look.x += dx;
    this.look.y += dy;
  }

  forward(out: Vector3): Vector3 {
    const cp = Math.cos(this.pitch);
    return out.set(-Math.sin(this.yaw) * cp, Math.sin(this.pitch), -Math.cos(this.yaw) * cp);
  }

  private collide(c: Colliders, deckAt: (x: number, z: number) => number | null): void {
    const p = this.pos;
    for (let iter = 0; iter < 2; iter++) {
      for (const k of c.circles) {
        const dx = p.x - k.x;
        const dz = p.z - k.z;
        const d = Math.hypot(dx, dz);
        const min = k.r + RADIUS;
        if (d < min && d > 1e-5) {
          p.x = k.x + (dx / d) * min;
          p.z = k.z + (dz / d) * min;
        }
      }
      for (const s of c.segments) {
        const ex = s.bx - s.ax;
        const ez = s.bz - s.az;
        const l2 = ex * ex + ez * ez;
        const t = l2 > 0 ? clamp(((p.x - s.ax) * ex + (p.z - s.az) * ez) / l2, 0, 1) : 0;
        const cx = s.ax + ex * t;
        const cz = s.az + ez * t;
        const dx = p.x - cx;
        const dz = p.z - cz;
        const d = Math.hypot(dx, dz);
        const min = s.r + RADIUS;
        if (d < min && d > 1e-5) {
          p.x = cx + (dx / d) * min;
          p.z = cz + (dz / d) * min;
        }
      }
    }
    if (deckAt(p.x, p.z) === null) {
      const sd = pondSdf(p.x, p.z);
      const limit = -0.3;
      if (sd < limit) {
        const e = 0.2;
        const gx = pondSdf(p.x + e, p.z) - pondSdf(p.x - e, p.z);
        const gz = pondSdf(p.x, p.z + e) - pondSdf(p.x, p.z - e);
        const gl = Math.hypot(gx, gz) || 1;
        p.x += (gx / gl) * (limit - sd);
        p.z += (gz / gl) * (limit - sd);
      }
    }
    const lim = 60;
    p.x = clamp(p.x, -lim, lim);
    p.z = clamp(p.z, -lim, lim);
  }

  teleport(x: number, z: number, yaw: number, pitch = this.pitch): void {
    this.pos.set(x, terrainHeight(x, z), z);
    this.groundY = this.pos.y;
    this.vel.set(0, 0, 0);
    this.yaw = yaw;
    this.pitch = pitch;
  }

  update(dt: number, input: FpInput, colliders: Colliders, deckAt: (x: number, z: number) => number | null, soilAt: (x: number, z: number) => number): void {
    const len = Math.hypot(input.fwd, input.side);
    const ix = len > 0 ? input.side / len : 0;
    const iz = len > 0 ? input.fwd / len : 0;
    const max = input.run ? RUN : WALK;
    const s = Math.sin(this.yaw);
    const c = Math.cos(this.yaw);
    // forward is -Z rotated by yaw
    const tvx = (-s * iz + c * ix) * max;
    const tvz = (-c * iz - s * ix) * max;
    const moving = len > 0;
    this.vel.x = damp(this.vel.x, tvx, moving ? 9 : 12, dt);
    this.vel.z = damp(this.vel.z, tvz, moving ? 9 : 12, dt);
    const bx = this.pos.x;
    const bz = this.pos.z;
    this.pos.x += this.vel.x * dt;
    this.pos.z += this.vel.z * dt;
    this.collide(colliders, deckAt);
    const moved = Math.hypot(this.pos.x - bx, this.pos.z - bz);
    this.speed = dt > 0 ? damp(this.speed, moved / dt, 12, dt) : 0;

    let gy = terrainHeight(this.pos.x, this.pos.z);
    if (this.pos.x > FIELD.x0 && this.pos.x < FIELD.x0 + COLS * PLOT && this.pos.z > FIELD.z0 && this.pos.z < FIELD.z0 + ROWS * PLOT) {
      gy = Math.max(gy, soilAt(this.pos.x, this.pos.z) - 0.02);
    }
    const deck = deckAt(this.pos.x, this.pos.z);
    if (deck !== null) gy = Math.max(gy, deck);
    this.groundY = damp(this.groundY, gy, 14, dt);
    this.pos.y = this.groundY;

    // head bob: a soft figure-eight that fades in with speed
    const k = clamp(this.speed / WALK, 0, 1.6);
    this.phase += dt * (5.2 + this.speed * 1.15) * (k > 0.05 ? 1 : 0);
    const amp = Math.min(k, 1.25);
    this.bobY = damp(this.bobY, Math.abs(Math.sin(this.phase)) * 0.045 * amp - 0.02 * amp, 18, dt);
    this.bobX = damp(this.bobX, Math.cos(this.phase) * 0.022 * amp, 18, dt);
    const strafe = (-s * this.vel.z + c * this.vel.x) / RUN; // signed sideways speed
    this.roll = damp(this.roll, -strafe * 0.028 + Math.cos(this.phase) * 0.004 * amp, 8, dt);

    this.stepAcc += moved;
    const stride = input.run ? 1.15 : 0.85;
    if (this.stepAcc > stride) {
      this.stepAcc = 0;
      this.onStep?.(this.pos.x, this.pos.y, this.pos.z);
    }

    const cam = this.camera;
    cam.position.set(this.pos.x + c * this.bobX, this.pos.y + EYE + this.bobY, this.pos.z - s * this.bobX);
    cam.rotation.set(this.pitch, this.yaw, this.roll);
    cam.updateMatrixWorld();
  }

  /** Clear per-frame mouse motion (after the view model has read it). */
  endFrame(): void {
    this.look.x = 0;
    this.look.y = 0;
  }
}
