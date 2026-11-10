import { Group, Vector3, type Object3D, type Scene } from 'three';
import { findByPrefix, type Assets } from '../core/assets';
import type { MaterialLib } from '../core/materials';
import { shared } from '../core/shared';
import { Sprite, type Particles } from '../fx/particles';
import { mulberry32 } from '../util/math';
import { POND, terrainHeight } from './layout';
import type { World } from './props';

interface Butterfly {
  root: Object3D;
  wl: Object3D | null;
  wr: Object3D | null;
  home: Vector3;
  target: Vector3;
  pos: Vector3;
  vel: Vector3;
  phase: number;
  rest: number;
  yaw: number;
}

interface Bird {
  root: Object3D;
  wl: Object3D | null;
  wr: Object3D | null;
  cx: number;
  cz: number;
  r: number;
  h: number;
  a: number;
  speed: number;
  phase: number;
}

/** Ambient life: chimney smoke, drifting pollen, butterflies, birds, fireflies after dark. */
export class Life {
  private readonly group = new Group();
  private readonly butterflies: Butterfly[] = [];
  private readonly birds: Bird[] = [];
  private smokeT = 0;
  private pollenT = 0;
  private flyT = 0;
  private readonly rng = mulberry32(977);

  constructor(
    scene: Scene,
    assets: Assets,
    lib: MaterialLib,
    private readonly world: World,
    private readonly particles: Particles,
  ) {
    this.group.name = 'life';
    scene.add(this.group);
    const rng = this.rng;

    const spots = world.flowers.length ? world.flowers : [new Vector3(-4, 0, 6)];
    const nb = Math.min(7, Math.max(4, spots.length));
    for (let i = 0; i < nb; i++) {
      const root = assets.clone('butterfly');
      if (!root) break;
      lib.apply(root, 'none', { cast: false, receive: false });
      const home = spots[Math.floor(rng() * spots.length)]!.clone();
      const pos = home.clone();
      pos.y = terrainHeight(pos.x, pos.z) + 0.6 + rng() * 0.5;
      root.scale.setScalar(1.7);
      this.group.add(root);
      this.butterflies.push({
        root,
        wl: findByPrefix(root, 'butterfly_wing_l'),
        wr: findByPrefix(root, 'butterfly_wing_r'),
        home,
        target: pos.clone(),
        pos,
        vel: new Vector3(),
        phase: rng() * 10,
        rest: 0,
        yaw: rng() * 6,
      });
    }

    for (let i = 0; i < 5; i++) {
      const root = assets.clone('bird');
      if (!root) break;
      lib.apply(root, 'none', { cast: false, receive: false });
      root.scale.setScalar(2.3);
      this.group.add(root);
      const flock = i < 3;
      this.birds.push({
        root,
        wl: findByPrefix(root, 'bird_wing_l'),
        wr: findByPrefix(root, 'bird_wing_r'),
        cx: flock ? 6 : -22 + rng() * 10,
        cz: flock ? -34 : 12 + rng() * 10,
        r: flock ? 30 + i * 2.6 : 20 + rng() * 9,
        h: flock ? 17 + i * 1.1 : 12 + rng() * 5,
        a: flock ? 1.2 + i * 0.11 : rng() * 6.28,
        speed: flock ? 0.2 : -0.17 - rng() * 0.05,
        phase: rng() * 6,
      });
    }
  }

  update(dt: number, focus: Vector3, daylight: number, night: number): void {
    const p = this.particles;
    const t = shared.uTime.value;
    const rng = this.rng;

    // --- chimney smoke: slow warm-grey puffs leaning with the wind
    this.smokeT -= dt;
    if (this.smokeT <= 0) {
      this.smokeT = 0.085;
      const s = this.world.smoke;
      const g = 0.62 + rng() * 0.2;
      p.emit({
        x: s.x + (rng() - 0.5) * 0.14,
        y: s.y + 0.05,
        z: s.z + (rng() - 0.5) * 0.14,
        vx: (rng() - 0.5) * 0.12,
        vy: 0.85 + rng() * 0.3,
        vz: (rng() - 0.5) * 0.12,
        life: 5.5 + rng() * 2.5,
        size: 0.28,
        sizeEnd: 1.9 + rng() * 0.9,
        r: g * 0.86,
        g: g * 0.93,
        b: g * 1.06,
        alpha: 0.2,
        sprite: Sprite.Puff,
        drag: 0.25,
        gravity: -0.05,
        wind: 0.42,
        rot: rng() * 6,
        spin: (rng() - 0.5) * 0.5,
        fadeIn: 0.12,
      });
    }

    // --- pollen and dust motes catching the light around the player
    this.pollenT -= dt;
    if (this.pollenT <= 0 && daylight > 0.05) {
      this.pollenT = 0.05;
      const a = rng() * 6.283;
      const d = 2 + rng() * 15;
      const x = focus.x + Math.cos(a) * d;
      const z = focus.z + Math.sin(a) * d;
      const y = terrainHeight(x, z) + 0.3 + rng() * 2.8;
      const k = daylight;
      p.emit({
        x,
        y,
        z,
        vx: (rng() - 0.5) * 0.1,
        vy: 0.02 + rng() * 0.08,
        vz: (rng() - 0.5) * 0.1,
        life: 6 + rng() * 5,
        size: 0.028 + rng() * 0.03,
        r: 1.5 * k,
        g: 1.25 * k,
        b: 0.72 * k,
        alpha: 0.7,
        sprite: Sprite.Spark,
        additive: true,
        wind: 0.22,
        wobble: 0.6 + rng() * 0.8,
        drag: 0.6,
        fadeIn: 0.25,
      });
    }

    // --- fireflies near the pond and meadow after dark
    this.flyT -= dt;
    if (this.flyT <= 0 && night > 0.35) {
      this.flyT = 0.07;
      const nearPond = rng() < 0.5;
      const a = rng() * 6.283;
      const d = nearPond ? POND.r * (0.8 + rng() * 0.9) : 3 + rng() * 14;
      const x = (nearPond ? POND.x : focus.x) + Math.cos(a) * d;
      const z = (nearPond ? POND.z : focus.z) + Math.sin(a) * d;
      const y = Math.max(terrainHeight(x, z), POND.level) + 0.35 + rng() * 1.4;
      p.emit({
        x,
        y,
        z,
        vx: (rng() - 0.5) * 0.3,
        vy: (rng() - 0.3) * 0.12,
        vz: (rng() - 0.5) * 0.3,
        life: 3.5 + rng() * 3,
        size: 0.07 + rng() * 0.04,
        r: 2.6 * night,
        g: 3.0 * night,
        b: 0.8 * night,
        alpha: 1,
        sprite: Sprite.Spark,
        additive: true,
        wobble: 1.2 + rng(),
        drag: 0.8,
        fadeIn: 0.3,
      });
    }

    // --- butterflies: flit between flowers, settle, flit again
    const active = daylight > 0.2;
    for (const b of this.butterflies) {
      b.root.visible = active;
      if (!active) continue;
      b.phase += dt * (b.rest > 0 ? 5 : 26);
      if (b.rest > 0) {
        b.rest -= dt;
        b.vel.multiplyScalar(Math.exp(-6 * dt));
      } else {
        _d.copy(b.target).sub(b.pos);
        const dist = _d.length();
        if (dist < 0.25) {
          if (rng() < 0.45) b.rest = 1.2 + rng() * 2.5;
          const f = this.world.flowers.length && rng() < 0.75 ? this.world.flowers[Math.floor(rng() * this.world.flowers.length)]! : b.home;
          const far = f.distanceTo(b.home) > 14 ? b.home : f;
          b.target.set(far.x + (rng() - 0.5) * 2.4, 0, far.z + (rng() - 0.5) * 2.4);
          b.target.y = terrainHeight(b.target.x, b.target.z) + 0.35 + rng() * 0.9;
        } else {
          _d.multiplyScalar(1 / dist);
          // erratic flutter around the straight line
          _d.x += Math.sin(t * 3.1 + b.phase * 0.13) * 0.7;
          _d.z += Math.cos(t * 2.7 + b.phase * 0.11) * 0.7;
          _d.y += Math.sin(b.phase * 0.5) * 0.9;
          b.vel.x += (_d.x * 1.5 - b.vel.x) * Math.min(1, dt * 3);
          b.vel.y += (_d.y * 0.8 - b.vel.y) * Math.min(1, dt * 5);
          b.vel.z += (_d.z * 1.5 - b.vel.z) * Math.min(1, dt * 3);
        }
      }
      b.pos.addScaledVector(b.vel, dt);
      const floor = terrainHeight(b.pos.x, b.pos.z) + 0.22;
      if (b.pos.y < floor) b.pos.y = floor;
      b.root.position.copy(b.pos);
      if (b.vel.x * b.vel.x + b.vel.z * b.vel.z > 0.01) {
        const want = Math.atan2(b.vel.x, b.vel.z);
        let dy = want - b.yaw;
        dy = Math.atan2(Math.sin(dy), Math.cos(dy));
        b.yaw += dy * Math.min(1, dt * 6);
      }
      b.root.rotation.set(-0.25, b.yaw, 0);
      const flap = b.rest > 0 ? 0.9 + Math.sin(b.phase) * 0.25 : Math.sin(b.phase) * 1.05 + 0.25;
      if (b.wl) b.wl.rotation.z = flap;
      if (b.wr) b.wr.rotation.z = -flap;
    }

    // --- birds wheeling over the far fields
    for (const b of this.birds) {
      b.root.visible = daylight > 0.12;
      if (!b.root.visible) continue;
      b.a += b.speed * dt * (18 / b.r);
      b.phase += dt * 7.5;
      const x = b.cx + Math.cos(b.a) * b.r;
      const z = b.cz + Math.sin(b.a) * b.r;
      const glide = Math.sin(t * 0.31 + b.cx) > 0.55;
      b.root.position.set(x, b.h + Math.sin(b.a * 3 + b.cx) * 1.3, z);
      const dir = b.speed > 0 ? 1 : -1;
      // tangent heading, banking into the turn
      b.root.rotation.set(0, -b.a + (dir > 0 ? Math.PI : 0), 0);
      b.root.rotateZ(-dir * 0.32);
      const flap = glide ? 0.12 + Math.sin(b.phase * 0.2) * 0.05 : Math.sin(b.phase) * 0.62;
      if (b.wl) b.wl.rotation.z = flap;
      if (b.wr) b.wr.rotation.z = -flap;
    }
  }
}

const _d = new Vector3();
