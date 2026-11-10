import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  DynamicDrawUsage,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  Quaternion,
  ShaderMaterial,
  Vector3,
  type Material,
} from 'three';
import type { Assets } from '../core/assets';
import type { MaterialLib } from '../core/materials';
import { WORLD_NORMAL_APPLY, WORLD_VARYINGS_ASSIGN, WORLD_VARYINGS_VERT, patch, shared } from '../core/shared';
import { clamp, damp, easeOutElastic, mulberry32, noise2, smoothstep } from '../util/math';
import { COLS, FIELD, PLOT, ROWS } from './layout';

export type CropType = 'wheat' | 'tomato' | 'pumpkin';
export const CROP_TYPES: CropType[] = ['wheat', 'tomato', 'pumpkin'];
export const CROP_LABEL: Record<CropType, string> = { wheat: 'Wheat', tomato: 'Tomato', pumpkin: 'Pumpkin' };
/** Seconds of watered time per growth stage. */
export const STAGE_TIME: Record<CropType, number> = { wheat: 12, tomato: 17, pumpkin: 24 };
export const DRY_TIME = 80;
export const STAGES = 4;

export interface Plot {
  col: number;
  row: number;
  tilled: boolean;
  till: number;
  wet: number;
  crop: CropType | null;
  stage: number;
  growth: number;
  /** Seconds since the last stage change (drives the pop). */
  pop: number;
  yaw: number;
  /** >0 while a harvested crop is flying off. */
  leaving: number;
  leavingCrop: CropType | null;
}

const MARGIN = 0.2;
const RES = 0.1;
const FIELD_Y = 0.014;

const SOIL_PARS = /* glsl */ `
varying vec3 vWPos;
varying vec3 vWNormal;
varying float vTill;
varying float vWet;
uniform sampler2D tDirtA;
uniform sampler2D tDirtN;
uniform sampler2D tSoilA;
uniform sampler2D tSoilN;
uniform sampler2D uNoise;
vec3 gNormalTS;
float gRough;
`;
const SOIL_MAP = /* glsl */ `
{
  vec2 uvw = vec2( vWPos.x, - vWPos.z );
  // fallow ground: two texture scales and soft patches of drier and damper earth hide the tiling
  vec4 nzD = texture2D( uNoise, uvw * 0.052 );
  vec3 dA = mix( texture2D( tDirtA, uvw / 2.0 ).rgb, texture2D( tDirtA, uvw / 5.3 + 0.37 ).rgb, 0.45 );
  dA *= mix( 0.80, 1.12, nzD.r );
  dA = mix( dA, dA * vec3( 1.14, 1.06, 0.88 ), smoothstep( 0.5, 0.8, nzD.g ) * 0.55 );
  vec3 dN = texture2D( tDirtN, uvw / 2.0 ).xyz * 2.0 - 1.0;
  dN.xy *= 0.6;
  vec3 sA = texture2D( tSoilA, uvw / 1.2 ).rgb;
  vec3 sN = texture2D( tSoilN, uvw / 1.2 ).xyz * 2.0 - 1.0;
  float t = smoothstep( 0.05, 0.6, vTill );
  vec3 col = mix( dA, sA * 1.12, t );
  vec3 nrm = mix( dN, vec3( sN.xy * 1.5, sN.z ), t );
  // furrow crests catch a little dry dust, troughs stay dark
  float crest = smoothstep( 0.035, 0.10, vWPos.y );
  col *= mix( 1.0, mix( 0.86, 1.12, crest ), t );
  // watered soil: darker, saturated, glossy; water gathers in the troughs
  float wet = vWet * t;
  col *= mix( vec3( 1.0 ), vec3( 0.46, 0.44, 0.45 ), wet );
  float pool = 1.0 - crest;
  gRough = mix( 0.94, mix( 0.50, 0.26, pool ), wet );
  nrm.xy *= mix( 1.0, mix( 0.7, 0.18, pool ), wet );
  diffuseColor.rgb *= col;
  gNormalTS = normalize( nrm );
}
`;

const HILITE_FRAG = /* glsl */ `
varying vec2 vUv;
uniform vec3 uColor;
uniform float uAlpha;
uniform float uTime;
float rbox( vec2 p, vec2 b, float r ) {
  vec2 q = abs( p ) - b + r;
  return length( max( q, 0.0 ) ) + min( max( q.x, q.y ), 0.0 ) - r;
}
void main() {
  vec2 p = vUv * 2.0 - 1.0;
  float d = rbox( p, vec2( 0.86 ), 0.22 );
  float line = smoothstep( 0.075, 0.0, abs( d ) );
  float fill = smoothstep( 0.02, -0.3, d ) * 0.10;
  float pulse = 0.82 + 0.18 * sin( uTime * 4.0 );
  float a = ( line * 0.85 * pulse + fill ) * uAlpha;
  gl_FragColor = vec4( uColor * a, a );
}
`;

interface CropVisual {
  meshes: InstancedMesh[];
}

export class Field {
  readonly group = new Group();
  readonly plots: Plot[] = [];
  private readonly geo: BufferGeometry;
  private readonly nx: number;
  private readonly nz: number;
  private readonly aTill: Float32Array;
  private readonly aWet: Float32Array;
  private dirty = true;
  private readonly visuals = new Map<string, CropVisual>();
  private readonly hilite: Mesh;
  private readonly hiliteMat: ShaderMaterial;
  private hiliteTarget = 0;

  constructor(assets: Assets, lib: MaterialLib) {
    this.group.name = 'field';
    const rng = mulberry32(77);
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        this.plots.push({ col: c, row: r, tilled: false, till: 0, wet: 0, crop: null, stage: 0, growth: 0, pop: 9, yaw: Math.floor(rng() * 4) * (Math.PI / 2) + (rng() - 0.5) * 0.3, leaving: 0, leavingCrop: null });
      }
    }

    // --- soil mesh
    const w = FIELD.w + MARGIN * 2;
    const d = FIELD.d + MARGIN * 2;
    this.nx = Math.round(w / RES) + 1;
    this.nz = Math.round(d / RES) + 1;
    const count = this.nx * this.nz;
    const pos = new Float32Array(count * 3);
    const nor = new Float32Array(count * 3);
    this.aTill = new Float32Array(count);
    this.aWet = new Float32Array(count);
    for (let j = 0; j < this.nz; j++) {
      for (let i = 0; i < this.nx; i++) {
        const k = (j * this.nx + i) * 3;
        pos[k] = FIELD.x0 - MARGIN + (i / (this.nx - 1)) * w;
        pos[k + 1] = FIELD_Y;
        pos[k + 2] = FIELD.z0 - MARGIN + (j / (this.nz - 1)) * d;
        nor[k + 1] = 1;
      }
    }
    const idx = new Uint32Array((this.nx - 1) * (this.nz - 1) * 6);
    let q = 0;
    for (let j = 0; j < this.nz - 1; j++) {
      for (let i = 0; i < this.nx - 1; i++) {
        const a = j * this.nx + i;
        const b = a + 1;
        const c = a + this.nx;
        const e = c + 1;
        idx[q++] = a;
        idx[q++] = c;
        idx[q++] = b;
        idx[q++] = b;
        idx[q++] = c;
        idx[q++] = e;
      }
    }
    this.geo = new BufferGeometry();
    const pa = new BufferAttribute(pos, 3);
    pa.setUsage(DynamicDrawUsage);
    const na = new BufferAttribute(nor, 3);
    na.setUsage(DynamicDrawUsage);
    this.geo.setAttribute('position', pa);
    this.geo.setAttribute('normal', na);
    this.geo.setAttribute('aTill', new BufferAttribute(this.aTill, 1).setUsage(DynamicDrawUsage));
    this.geo.setAttribute('aWet', new BufferAttribute(this.aWet, 1).setUsage(DynamicDrawUsage));
    this.geo.setIndex(new BufferAttribute(idx, 1));
    this.geo.computeBoundingSphere();

    const dirt = assets.set('dirt');
    const soil = assets.set('soil');
    const mat = new MeshStandardMaterial({ color: 0xffffff, roughness: 1 });
    mat.envMapIntensity = 1.0;
    patch(mat, 'fieldsoil', (s) => {
      s.uniforms.tDirtA = { value: dirt.albedo };
      s.uniforms.tDirtN = { value: dirt.normal };
      s.uniforms.tSoilA = { value: soil.albedo };
      s.uniforms.tSoilN = { value: soil.normal };
      s.uniforms.uNoise = shared.uNoise;
      s.vertexShader = s.vertexShader
        .replace('#include <common>', `#include <common>\n${WORLD_VARYINGS_VERT}\nattribute float aTill;\nattribute float aWet;\nvarying float vTill;\nvarying float vWet;`)
        .replace('#include <project_vertex>', `#include <project_vertex>\n${WORLD_VARYINGS_ASSIGN}\nvTill = aTill;\nvWet = aWet;`);
      s.fragmentShader = s.fragmentShader
        .replace('#include <common>', `#include <common>\n${SOIL_PARS}`)
        .replace('#include <map_fragment>', SOIL_MAP)
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = gRough;')
        .replace('#include <normal_fragment_maps>', WORLD_NORMAL_APPLY);
    });
    const soilMesh = new Mesh(this.geo, mat);
    soilMesh.receiveShadow = true;
    soilMesh.castShadow = false;
    soilMesh.name = 'soil';
    this.group.add(soilMesh);

    // --- crops
    for (const type of CROP_TYPES) {
      for (let s = 0; s < STAGES; s++) {
        const name = `${type}_${s}`;
        const src = assets.node(name);
        if (!src) continue;
        const meshes: InstancedMesh[] = [];
        src.traverse((o) => {
          const m = o as Mesh;
          if (!m.isMesh) return;
          const matName = (m.material as Material).name.replace(/\.\d+$/, '');
          const im = new InstancedMesh(m.geometry, lib.get(matName, 'crop'), COLS * ROWS);
          im.instanceMatrix.setUsage(DynamicDrawUsage);
          im.castShadow = true;
          im.receiveShadow = true;
          im.frustumCulled = false;
          const depth = lib.depthFor(matName, 'crop');
          if (depth) im.customDepthMaterial = depth;
          for (let i = 0; i < COLS * ROWS; i++) im.setMatrixAt(i, ZERO);
          im.instanceMatrix.needsUpdate = true;
          im.name = name;
          meshes.push(im);
          this.group.add(im);
        });
        this.visuals.set(name, { meshes });
      }
    }

    // --- hover highlight
    this.hiliteMat = new ShaderMaterial({
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 ); }',
      fragmentShader: HILITE_FRAG,
      uniforms: { uColor: { value: new Color(1.0, 0.95, 0.75) }, uAlpha: { value: 0 }, uTime: shared.uTime },
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      premultipliedAlpha: true,
    });
    const hg = new PlaneGeometry(PLOT, PLOT);
    hg.rotateX(-Math.PI / 2);
    this.hilite = new Mesh(hg, this.hiliteMat);
    this.hilite.renderOrder = 10;
    this.hilite.visible = false;
    this.group.add(this.hilite);
  }

  plot(col: number, row: number): Plot {
    return this.plots[row * COLS + col]!;
  }

  // ---- actions (return true when something changed) ----
  till(p: Plot): boolean {
    if (p.tilled || p.crop) return false;
    p.tilled = true;
    return true;
  }
  plant(p: Plot, type: CropType): boolean {
    if (!p.tilled || p.crop) return false;
    p.crop = type;
    p.stage = 0;
    p.growth = 0;
    p.pop = 0;
    return true;
  }
  water(p: Plot): boolean {
    if (!p.tilled) return false;
    p.wet = 1;
    return true;
  }
  harvest(p: Plot): CropType | null {
    if (!p.crop || p.stage < STAGES - 1) return null;
    const c = p.crop;
    p.leavingCrop = c;
    p.leaving = 0.0001;
    p.crop = null;
    p.stage = 0;
    p.growth = 0;
    return c;
  }
  isRipe(p: Plot): boolean {
    return !!p.crop && p.stage === STAGES - 1;
  }
  /** Watered seconds still needed before the crop is ripe. */
  timeToRipe(p: Plot): number {
    if (!p.crop) return 0;
    return Math.max(0, (STAGES - 1 - p.stage - p.growth) * STAGE_TIME[p.crop]);
  }

  /** Smoothed tilled amount at a world position (soft bed edges, merged neighbours). */
  private tillAt(x: number, z: number): [number, number] {
    const u = (x - FIELD.x0) / PLOT - 0.5;
    const v = (z - FIELD.z0) / PLOT - 0.5;
    const i0 = Math.floor(u);
    const j0 = Math.floor(v);
    const su = smoothstep(0.36, 0.64, u - i0);
    const sv = smoothstep(0.36, 0.64, v - j0);
    let t = 0;
    let wv = 0;
    for (let dj = 0; dj < 2; dj++) {
      for (let di = 0; di < 2; di++) {
        const c = i0 + di;
        const r = j0 + dj;
        if (c < 0 || r < 0 || c >= COLS || r >= ROWS) continue;
        const wgt = (di ? su : 1 - su) * (dj ? sv : 1 - sv);
        const p = this.plots[r * COLS + c]!;
        t += p.till * wgt;
        wv += p.wet * wgt;
      }
    }
    return [t, wv];
  }

  private heightFrom(till: number, x: number, z: number): number {
    if (till <= 0.0005) return FIELD_Y;
    const fz = (z - FIELD.z0) / PLOT;
    const ridge = 0.5 + 0.5 * Math.cos(Math.PI * 2 * 3 * (fz - Math.floor(fz) - 0.5));
    const clod = (noise2(x * 9.0, z * 9.0) - 0.5) * 0.022 + (noise2(x * 3.1 + 5, z * 3.1) - 0.5) * 0.02;
    return FIELD_Y + till * (0.03 + 0.075 * Math.pow(ridge, 0.8) + clod);
  }

  /** Soil surface height (for planting crops and particles). */
  surfaceAt(x: number, z: number): number {
    const [t] = this.tillAt(x, z);
    return this.heightFrom(t, x, z);
  }

  private rebuild(): void {
    const pos = this.geo.getAttribute('position') as BufferAttribute;
    const nor = this.geo.getAttribute('normal') as BufferAttribute;
    const p = pos.array as Float32Array;
    const n = nor.array as Float32Array;
    const nx = this.nx;
    const nz = this.nz;
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        const vi = j * nx + i;
        const k = vi * 3;
        const [t, wv] = this.tillAt(p[k]!, p[k + 2]!);
        this.aTill[vi] = t;
        this.aWet[vi] = wv;
        p[k + 1] = this.heightFrom(t, p[k]!, p[k + 2]!);
      }
    }
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        const k = (j * nx + i) * 3;
        const l = p[(j * nx + Math.max(i - 1, 0)) * 3 + 1]!;
        const r = p[(j * nx + Math.min(i + 1, nx - 1)) * 3 + 1]!;
        const d = p[(Math.max(j - 1, 0) * nx + i) * 3 + 1]!;
        const u = p[(Math.min(j + 1, nz - 1) * nx + i) * 3 + 1]!;
        const ax = l - r;
        const az = d - u;
        const ay = 2 * RES;
        const inv = 1 / Math.hypot(ax, ay, az);
        n[k] = ax * inv;
        n[k + 1] = ay * inv;
        n[k + 2] = az * inv;
      }
    }
    pos.needsUpdate = true;
    nor.needsUpdate = true;
    (this.geo.getAttribute('aTill') as BufferAttribute).needsUpdate = true;
    (this.geo.getAttribute('aWet') as BufferAttribute).needsUpdate = true;
  }

  setHighlight(p: Plot | null, good: boolean): void {
    if (!p) {
      this.hiliteTarget = 0;
      return;
    }
    this.hiliteTarget = 1;
    this.hilite.visible = true;
    const x = FIELD.x0 + (p.col + 0.5) * PLOT;
    const z = FIELD.z0 + (p.row + 0.5) * PLOT;
    this.hilite.position.set(x, 0.15, z);
    (this.hiliteMat.uniforms.uColor!.value as Color).setRGB(good ? 1.0 : 0.75, good ? 0.93 : 0.8, good ? 0.62 : 0.9);
  }

  update(dt: number): void {
    const hu = this.hiliteMat.uniforms.uAlpha!;
    hu.value = damp(hu.value as number, this.hiliteTarget, 14, dt);
    if ((hu.value as number) < 0.01 && this.hiliteTarget === 0) this.hilite.visible = false;

    let cropsDirty = false;
    for (const p of this.plots) {
      const target = p.tilled ? 1 : 0;
      if (Math.abs(p.till - target) > 0.001) {
        p.till = damp(p.till, target, 9, dt);
        if (Math.abs(p.till - target) <= 0.001) p.till = target;
        this.dirty = true;
      }
      if (p.wet > 0) {
        const before = p.wet;
        p.wet = Math.max(0, p.wet - dt / DRY_TIME);
        // only re-upload when the visible value moved a little
        if (Math.floor(before * 60) !== Math.floor(p.wet * 60)) this.dirty = true;
      }
      if (p.crop) {
        p.pop += dt;
        if (p.wet > 0.04 && p.stage < STAGES - 1) {
          p.growth += dt / STAGE_TIME[p.crop];
          if (p.growth >= 1) {
            p.growth = 0;
            p.stage++;
            p.pop = 0;
          }
        }
        cropsDirty = true;
      }
      if (p.leaving > 0) {
        p.leaving += dt;
        if (p.leaving > 0.28) {
          p.leaving = 0;
          p.leavingCrop = null;
        }
        cropsDirty = true;
      }
    }
    if (this.dirty) {
      this.dirty = false;
      this.rebuild();
    }
    if (cropsDirty || this.cropsWereDirty) this.updateCrops();
    this.cropsWereDirty = cropsDirty;
  }
  private cropsWereDirty = true;

  private updateCrops(): void {
    // instances are packed to the front so only living plants are drawn
    for (const v of this.visuals.values()) {
      for (const m of v.meshes) m.count = 0;
    }
    for (let i = 0; i < this.plots.length; i++) {
      const p = this.plots[i]!;
      let type = p.crop;
      let stage = p.stage;
      let s = 1;
      let squash = 0;
      if (p.leaving > 0 && p.leavingCrop) {
        // harvested: quick stretch upward, then gone
        type = p.leavingCrop;
        stage = STAGES - 1;
        const t = clamp(p.leaving / 0.28, 0, 1);
        s = 1 + Math.sin(t * Math.PI) * 0.18 - t * t * 1.0;
        squash = 0.55 * t;
        if (s <= 0.02) continue;
      } else if (type) {
        const t = clamp(p.pop / 0.7, 0, 1);
        const grow = 0.84 + 0.16 * (stage === STAGES - 1 ? 1 : p.growth);
        s = (0.55 + 0.45 * easeOutElastic(t)) * grow;
        squash = Math.sin(t * Math.PI * 3) * (1 - t) * 0.22;
      } else {
        continue;
      }
      const vis = this.visuals.get(`${type}_${stage}`);
      if (!vis) continue;
      const x = FIELD.x0 + (p.col + 0.5) * PLOT;
      const z = FIELD.z0 + (p.row + 0.5) * PLOT;
      _pos.set(x, FIELD_Y + p.till * 0.05, z);
      _quat.setFromAxisAngle(_yAxis, p.yaw);
      _scl.set(s * (1 - squash * 0.5), s * (1 + squash), s * (1 - squash * 0.5));
      _mat.compose(_pos, _quat, _scl);
      for (const m of vis.meshes) m.setMatrixAt(m.count++, _mat);
    }
    for (const v of this.visuals.values()) {
      for (const m of v.meshes) {
        m.visible = m.count > 0;
        m.instanceMatrix.needsUpdate = true;
      }
    }
  }
}

const ZERO = new Matrix4().makeScale(0, 0, 0);
const _pos = new Vector3();
const _quat = new Quaternion();
const _scl = new Vector3();
const _mat = new Matrix4();
const _yAxis = new Vector3(0, 1, 0);
