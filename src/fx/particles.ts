import {
  AdditiveBlending,
  BufferAttribute,
  CanvasTexture,
  Color,
  DynamicDrawUsage,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  LinearFilter,
  Mesh,
  NormalBlending,
  ShaderMaterial,
  type Scene,
} from 'three';
import { shared } from '../core/shared';

export const enum Sprite {
  Puff = 0,
  Drop = 1,
  Leaf = 2,
  Spark = 3,
}

export interface EmitOptions {
  x: number;
  y: number;
  z: number;
  vx?: number;
  vy?: number;
  vz?: number;
  life: number;
  size: number;
  sizeEnd?: number;
  r: number;
  g: number;
  b: number;
  alpha?: number;
  sprite: Sprite;
  gravity?: number;
  drag?: number;
  rot?: number;
  spin?: number;
  /** Wind influence (m/s^2 per unit wind). */
  wind?: number;
  /** Sideways wobble speed for floating motes. */
  wobble?: number;
  additive?: boolean;
  /** Fraction of life spent fading in. */
  fadeIn?: number;
  /** Bounce off the ground at this height. */
  floor?: number;
}

interface P {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  age: number;
  life: number;
  size: number;
  sizeEnd: number;
  r: number;
  g: number;
  b: number;
  alpha: number;
  sprite: number;
  gravity: number;
  drag: number;
  rot: number;
  spin: number;
  wind: number;
  wobble: number;
  phase: number;
  fadeIn: number;
  floor: number;
}

function makeAtlas(): CanvasTexture {
  const s = 128;
  const cv = document.createElement('canvas');
  cv.width = cv.height = s * 2;
  const g = cv.getContext('2d')!;
  // 0: soft puff
  let grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.35, 'rgba(255,255,255,0.62)');
  grd.addColorStop(0.7, 'rgba(255,255,255,0.18)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, s, s);
  // 1: droplet (teardrop with a soft highlight)
  g.save();
  g.translate(s + s / 2, s / 2);
  grd = g.createRadialGradient(0, 6, 2, 0, 6, 34);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.75, 'rgba(255,255,255,0.9)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.beginPath();
  g.moveTo(0, -44);
  g.bezierCurveTo(26, -6, 32, 14, 0, 40);
  g.bezierCurveTo(-32, 14, -26, -6, 0, -44);
  g.fill();
  g.restore();
  // 2: leaf
  g.save();
  g.translate(s / 2, s + s / 2);
  g.rotate(-0.6);
  g.fillStyle = 'rgba(255,255,255,1)';
  g.shadowColor = 'rgba(255,255,255,0.6)';
  g.shadowBlur = 4;
  g.beginPath();
  g.moveTo(-46, 0);
  g.bezierCurveTo(-18, -34, 26, -30, 48, 0);
  g.bezierCurveTo(26, 30, -18, 34, -46, 0);
  g.fill();
  g.shadowBlur = 0;
  g.strokeStyle = 'rgba(190,190,190,1)';
  g.lineWidth = 3;
  g.beginPath();
  g.moveTo(-40, 0);
  g.lineTo(42, 0);
  g.stroke();
  g.restore();
  // 3: four-point sparkle
  g.save();
  g.translate(s + s / 2, s + s / 2);
  grd = g.createRadialGradient(0, 0, 0, 0, 0, 30);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(-32, -32, 64, 64);
  g.fillStyle = 'rgba(255,255,255,1)';
  g.shadowColor = 'rgba(255,255,255,0.9)';
  g.shadowBlur = 8;
  for (let i = 0; i < 2; i++) {
    g.rotate(Math.PI / 2);
    g.beginPath();
    g.moveTo(-54, 0);
    g.quadraticCurveTo(0, -7, 54, 0);
    g.quadraticCurveTo(0, 7, -54, 0);
    g.fill();
  }
  g.restore();
  const tex = new CanvasTexture(cv);
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = false;
  return tex;
}

const VERT = /* glsl */ `
attribute vec3 iPos;
attribute vec4 iParams; // size, rotation, alpha, sprite
attribute vec3 iColor;
varying vec2 vUv;
varying float vAlpha;
varying vec3 vColor;
void main() {
  vec3 right = vec3( viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0] );
  vec3 up = vec3( viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1] );
  float c = cos( iParams.y );
  float s = sin( iParams.y );
  vec2 q = vec2( position.x * c - position.y * s, position.x * s + position.y * c ) * iParams.x;
  vec3 wp = iPos + right * q.x + up * q.y;
  float cell = iParams.w;
  vec2 cellOff = vec2( mod( cell, 2.0 ), 1.0 - floor( cell / 2.0 ) ) * 0.5;
  vUv = cellOff + ( position.xy + 0.5 ) * 0.5;
  vAlpha = iParams.z;
  vColor = iColor;
  gl_Position = projectionMatrix * viewMatrix * vec4( wp, 1.0 );
}
`;
const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D tAtlas;
uniform vec3 uLight;
varying vec2 vUv;
varying float vAlpha;
varying vec3 vColor;
void main() {
  vec4 t = texture2D( tAtlas, vUv );
  float a = t.a * vAlpha;
  if ( a < 0.003 ) discard;
  gl_FragColor = vec4( t.rgb * vColor * uLight * a, a );
}
`;

class Layer {
  readonly mesh: Mesh;
  readonly list: P[] = [];
  private readonly pos: Float32Array;
  private readonly par: Float32Array;
  private readonly col: Float32Array;
  private readonly geo: InstancedBufferGeometry;

  constructor(
    readonly cap: number,
    atlas: CanvasTexture,
    additive: boolean,
    light: Color,
  ) {
    this.pos = new Float32Array(cap * 3);
    this.par = new Float32Array(cap * 4);
    this.col = new Float32Array(cap * 3);
    const geo = new InstancedBufferGeometry();
    geo.setAttribute('position', new BufferAttribute(new Float32Array([-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0]), 3));
    geo.setIndex([0, 1, 2, 0, 2, 3]);
    geo.setAttribute('iPos', new InstancedBufferAttribute(this.pos, 3).setUsage(DynamicDrawUsage));
    geo.setAttribute('iParams', new InstancedBufferAttribute(this.par, 4).setUsage(DynamicDrawUsage));
    geo.setAttribute('iColor', new InstancedBufferAttribute(this.col, 3).setUsage(DynamicDrawUsage));
    geo.instanceCount = 0;
    this.geo = geo;
    const mat = new ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: { tAtlas: { value: atlas }, uLight: { value: additive ? new Color(1, 1, 1) : light } },
      transparent: true,
      depthWrite: false,
      premultipliedAlpha: true,
      blending: additive ? AdditiveBlending : NormalBlending,
    });
    this.mesh = new Mesh(geo, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = additive ? 21 : 20;
  }

  update(dt: number, time: number): void {
    const wx = shared.uWind.value.x * shared.uWind.value.z;
    const wz = shared.uWind.value.y * shared.uWind.value.z;
    let n = 0;
    const list = this.list;
    for (let i = 0; i < list.length; i++) {
      const p = list[i]!;
      p.age += dt;
      if (p.age >= p.life) continue;
      const k = Math.exp(-p.drag * dt);
      p.vx = p.vx * k + wx * p.wind * dt;
      p.vz = p.vz * k + wz * p.wind * dt;
      p.vy = p.vy * k - p.gravity * dt;
      let ox = 0;
      let oy = 0;
      if (p.wobble) {
        ox = Math.sin(time * 1.3 + p.phase) * p.wobble;
        oy = Math.cos(time * 0.9 + p.phase * 1.7) * p.wobble * 0.6;
      }
      p.x += (p.vx + ox) * dt;
      p.y += (p.vy + oy) * dt;
      p.z += (p.vz + ox * 0.7) * dt;
      if (p.floor > -1e5 && p.y < p.floor) {
        p.y = p.floor;
        p.vy = -p.vy * 0.25;
        p.vx *= 0.5;
        p.vz *= 0.5;
        p.spin *= 0.4;
      }
      p.rot += p.spin * dt;
      list[n] = p;
      const t = p.age / p.life;
      const fade = Math.min(1, t / Math.max(p.fadeIn, 1e-4)) * Math.pow(1 - t, 1.4);
      this.pos[n * 3] = p.x;
      this.pos[n * 3 + 1] = p.y;
      this.pos[n * 3 + 2] = p.z;
      this.par[n * 4] = p.size + (p.sizeEnd - p.size) * (1 - (1 - t) * (1 - t));
      this.par[n * 4 + 1] = p.rot;
      this.par[n * 4 + 2] = p.alpha * fade;
      this.par[n * 4 + 3] = p.sprite;
      this.col[n * 3] = p.r;
      this.col[n * 3 + 1] = p.g;
      this.col[n * 3 + 2] = p.b;
      n++;
    }
    list.length = n;
    this.geo.instanceCount = n;
    (this.geo.getAttribute('iPos') as InstancedBufferAttribute).needsUpdate = true;
    (this.geo.getAttribute('iParams') as InstancedBufferAttribute).needsUpdate = true;
    (this.geo.getAttribute('iColor') as InstancedBufferAttribute).needsUpdate = true;
  }
}

export class Particles {
  private readonly normal: Layer;
  private readonly add: Layer;
  /** Scene light tint for non-emissive particles; set every frame. */
  readonly light = new Color(1, 1, 1);

  constructor(scene: Scene) {
    const atlas = makeAtlas();
    this.normal = new Layer(2600, atlas, false, this.light);
    this.add = new Layer(900, atlas, true, this.light);
    scene.add(this.normal.mesh, this.add.mesh);
  }

  emit(o: EmitOptions): void {
    const layer = o.additive ? this.add : this.normal;
    if (layer.list.length >= layer.cap) return;
    layer.list.push({
      x: o.x,
      y: o.y,
      z: o.z,
      vx: o.vx ?? 0,
      vy: o.vy ?? 0,
      vz: o.vz ?? 0,
      age: 0,
      life: o.life,
      size: o.size,
      sizeEnd: o.sizeEnd ?? o.size,
      r: o.r,
      g: o.g,
      b: o.b,
      alpha: o.alpha ?? 1,
      sprite: o.sprite,
      gravity: o.gravity ?? 0,
      drag: o.drag ?? 0,
      rot: o.rot ?? 0,
      spin: o.spin ?? 0,
      wind: o.wind ?? 0,
      wobble: o.wobble ?? 0,
      phase: Math.random() * 6.283,
      fadeIn: o.fadeIn ?? 0.08,
      floor: o.floor ?? -1e9,
    });
  }

  update(dt: number): void {
    this.normal.update(dt, shared.uTime.value);
    this.add.update(dt, shared.uTime.value);
  }

  // ---- canned effects -------------------------------------------------------
  dust(x: number, y: number, z: number, strength = 1): void {
    for (let i = 0; i < 14 * strength; i++) {
      const a = Math.random() * 6.283;
      const sp = 0.4 + Math.random() * 1.1;
      this.emit({ x: x + Math.cos(a) * 0.15, y: y + 0.05, z: z + Math.sin(a) * 0.15, vx: Math.cos(a) * sp, vy: 0.5 + Math.random() * 0.9, vz: Math.sin(a) * sp, life: 0.9 + Math.random() * 0.7, size: 0.16, sizeEnd: 0.6 + Math.random() * 0.4, r: 0.62, g: 0.46, b: 0.32, alpha: 0.42, sprite: Sprite.Puff, drag: 2.2, gravity: -0.15, wind: 0.5, rot: Math.random() * 6 });
    }
    // flung clods
    for (let i = 0; i < 7 * strength; i++) {
      const a = Math.random() * 6.283;
      const sp = 0.8 + Math.random() * 1.4;
      this.emit({ x, y: y + 0.08, z, vx: Math.cos(a) * sp, vy: 1.8 + Math.random() * 1.6, vz: Math.sin(a) * sp, life: 0.8, size: 0.05 + Math.random() * 0.05, r: 0.2, g: 0.13, b: 0.08, alpha: 1, sprite: Sprite.Puff, gravity: 9, floor: y, fadeIn: 0.01 });
    }
  }

  droplets(x: number, y: number, z: number, tx: number, ty: number, tz: number, n = 5): void {
    for (let i = 0; i < n; i++) {
      const t = 0.42 + Math.random() * 0.12;
      const jx = (Math.random() - 0.5) * 0.5;
      const jz = (Math.random() - 0.5) * 0.5;
      const vx = (tx + jx - x) / t;
      const vz = (tz + jz - z) / t;
      const vy = (ty - y) / t + 0.5 * 9 * t;
      this.emit({ x, y, z, vx, vy, vz, life: t + 0.25, size: 0.045 + Math.random() * 0.03, r: 0.72, g: 0.88, b: 1.0, alpha: 0.85, sprite: Sprite.Drop, gravity: 9, floor: ty, fadeIn: 0.02 });
    }
  }

  splash(x: number, y: number, z: number): void {
    for (let i = 0; i < 3; i++) {
      const a = Math.random() * 6.283;
      this.emit({ x: x + (Math.random() - 0.5) * 0.6, y: y + 0.02, z: z + (Math.random() - 0.5) * 0.6, vx: Math.cos(a) * 0.5, vy: 0.9 + Math.random() * 0.6, vz: Math.sin(a) * 0.5, life: 0.4, size: 0.03, r: 0.75, g: 0.9, b: 1, alpha: 0.8, sprite: Sprite.Drop, gravity: 7, fadeIn: 0.02 });
    }
  }

  seeds(x: number, y: number, z: number, tx: number, ty: number, tz: number): void {
    for (let i = 0; i < 10; i++) {
      const t = 0.38 + Math.random() * 0.14;
      const jx = (Math.random() - 0.5) * 0.7;
      const jz = (Math.random() - 0.5) * 0.7;
      this.emit({ x, y, z, vx: (tx + jx - x) / t, vy: (ty - y) / t + 0.5 * 9 * t, vz: (tz + jz - z) / t, life: t + 0.5, size: 0.04, r: 0.85, g: 0.72, b: 0.42, alpha: 1, sprite: Sprite.Puff, gravity: 9, floor: ty + 0.01, fadeIn: 0.01 });
    }
  }

  harvest(x: number, y: number, z: number, cr: number, cg: number, cb: number): void {
    for (let i = 0; i < 16; i++) {
      const a = Math.random() * 6.283;
      const sp = 1.0 + Math.random() * 1.8;
      const green = Math.random() < 0.6;
      this.emit({ x, y: y + 0.3, z, vx: Math.cos(a) * sp, vy: 2.2 + Math.random() * 2.2, vz: Math.sin(a) * sp, life: 1.1 + Math.random() * 0.6, size: 0.13 + Math.random() * 0.09, r: green ? 0.2 : cr, g: green ? 0.45 : cg, b: green ? 0.1 : cb, alpha: 1, sprite: Sprite.Leaf, gravity: 5.5, drag: 1.4, rot: Math.random() * 6, spin: (Math.random() - 0.5) * 12, wind: 1.0, floor: y, fadeIn: 0.02 });
    }
    for (let i = 0; i < 12; i++) {
      const a = Math.random() * 6.283;
      const sp = 0.6 + Math.random() * 1.6;
      this.emit({ x: x + Math.cos(a) * 0.2, y: y + 0.35 + Math.random() * 0.4, z: z + Math.sin(a) * 0.2, vx: Math.cos(a) * sp, vy: 1.2 + Math.random() * 1.8, vz: Math.sin(a) * sp, life: 0.6 + Math.random() * 0.5, size: 0.1, sizeEnd: 0.26, r: 2.4, g: 1.9, b: 0.9, alpha: 1, sprite: Sprite.Spark, drag: 2.5, additive: true, rot: Math.random() * 3, spin: (Math.random() - 0.5) * 3, fadeIn: 0.05 });
    }
    this.emit({ x, y: y + 0.4, z, life: 0.35, size: 0.3, sizeEnd: 1.5, r: 1.6, g: 1.3, b: 0.7, alpha: 0.5, sprite: Sprite.Puff, additive: true, fadeIn: 0.05 });
  }
}
