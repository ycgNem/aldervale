import {
  BufferAttribute,
  Color,
  DoubleSide,
  Group,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  MeshStandardMaterial,
  Sphere,
  Vector3,
  type DataTexture,
} from 'three';
import { WIND_GLSL, applyNoFaceFlip, applyTranslucency, patch, shared } from '../core/shared';
import { mulberry32, smoothstep } from '../util/math';
import { MASK, WELL, cottageSdf, terrainHeight } from './layout';

/** Nearest-texel read of the splat mask: [dirt, path, shore, meadow] in 0..1. */
export function makeMaskSampler(mask: DataTexture): (x: number, z: number, out: Float32Array) => void {
  const data = mask.image.data as Uint8Array;
  const n = MASK.res;
  return (x, z, out) => {
    const u = Math.floor(((x - MASK.min) / MASK.size) * n);
    const v = Math.floor(((z - MASK.min) / MASK.size) * n);
    if (u < 0 || v < 0 || u >= n || v >= n) {
      out[0] = out[1] = out[2] = 0;
      out[3] = 1;
      return;
    }
    const k = (v * n + u) * 4;
    out[0] = data[k]! / 255;
    out[1] = data[k + 1]! / 255;
    out[2] = data[k + 2]! / 255;
    out[3] = data[k + 3]! / 255;
  };
}

const GRASS_VERT_PARS = /* glsl */ `
${WIND_GLSL}
attribute vec3 aRoot;
attribute vec4 aData;
uniform vec3 uGrassRoot;
uniform vec3 uGrassTip;
varying float vT;
varying vec3 vGrassCol;
vec3 gPos;
`;

const GRASS_BEGIN_NORMAL = /* glsl */ `
float gt = position.y;
float gYaw = aData.x;
float gH = aData.y;
float gW = aData.z;
float gR = aData.w;
vec2 gFace = vec2( cos( gYaw ), sin( gYaw ) );
vec2 gLean = vec2( - gFace.y, gFace.x );
vec3 gWind = windAt( aRoot );
vec2 gBend = gLean * ( 0.22 + gR * 0.30 ) * gH + gWind.xz * ( 0.50 + gR * 0.45 ) * gH;
float gt2 = gt * gt;
gPos = aRoot;
gPos.xz += gFace * position.x * gW + gBend * gt2;
float gB = min( dot( gBend, gBend ) / ( gH * gH ), 0.9 );
gPos.y += gH * gt * ( 1.0 - 0.42 * gB * gt );
vec3 gAlong = normalize( vec3( gBend.x * 2.0 * gt, gH, gBend.y * 2.0 * gt ) );
vec3 gSide = vec3( gFace.x, 0.0, gFace.y );
vec3 gN = normalize( cross( gSide, gAlong ) );
if ( gN.y < 0.0 ) gN = - gN;
// lean the shading normal toward "up" so the lawn lights as one soft surface, round it across the blade
vec3 objectNormal = normalize( mix( gN, vec3( 0.0, 1.0, 0.0 ), 0.60 ) + gSide * position.x * 0.9 );
vT = gt;
{
  vec2 uvw = vec2( aRoot.x, - aRoot.z );
  vec4 nzBig = textureLod( uNoise, uvw * 0.0047 + 0.31, 0.0 );
  vec3 patchTint = mix( vec3( 0.80, 0.90, 0.72 ), vec3( 1.20, 1.10, 0.86 ), nzBig.r );
  patchTint = mix( patchTint, patchTint * vec3( 1.22, 1.10, 0.60 ), smoothstep( 0.62, 0.9, nzBig.g ) * 0.45 );
  vec3 c = mix( uGrassRoot, uGrassTip, pow( gt, 1.35 ) ) * patchTint * ( 0.86 + gR * 0.28 );
  // gusts lay the blades over and flash their lighter sides
  c *= 1.0 + gWind.y * 0.22 * gt;
  vGrassCol = c;
}
`;

function bladeGeometry(lod: boolean): { positions: Float32Array; index: Uint16Array } {
  const rows: [number, number][] = lod
    ? [
        [0.0, 1.0],
        [0.55, 0.78],
      ]
    : [
        [0.0, 1.0],
        [0.3, 0.92],
        [0.58, 0.74],
        [0.82, 0.44],
      ];
  const pos: number[] = [];
  for (const [y, w] of rows) {
    pos.push(-0.5 * w, y, 0, 0.5 * w, y, 0);
  }
  pos.push(0, 1, 0);
  const idx: number[] = [];
  for (let r = 0; r < rows.length - 1; r++) {
    const a = r * 2;
    idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  const last = (rows.length - 1) * 2;
  idx.push(last, last + 1, last + 2);
  return { positions: new Float32Array(pos), index: new Uint16Array(idx) };
}

export interface GrassOptions {
  /** Blades per square metre close to home. */
  density: number;
  half: number;
  chunk: number;
}

export interface Grass {
  group: Group;
  material: MeshStandardMaterial;
  count: number;
}

export function createGrass(mask: DataTexture, groundColor: Color, opts: GrassOptions): Grass {
  const sample = makeMaskSampler(mask);
  const m = new Float32Array(4);
  const bladeHi = bladeGeometry(false);
  const bladeLo = bladeGeometry(true);
  const hiPos = new BufferAttribute(bladeHi.positions, 3);
  const hiIdx = new BufferAttribute(bladeHi.index, 1);
  const loPos = new BufferAttribute(bladeLo.positions, 3);
  const loIdx = new BufferAttribute(bladeLo.index, 1);

  const mat = new MeshStandardMaterial({ color: 0xffffff, roughness: 0.62, metalness: 0, side: DoubleSide });
  mat.envMapIntensity = 0.85;
  const root = groundColor.clone().multiplyScalar(0.72);
  const tip = new Color(0.33, 0.50, 0.105);
  patch(mat, 'grass', (s) => {
    s.uniforms.uTime = shared.uTime;
    s.uniforms.uWind = shared.uWind;
    s.uniforms.uNoise = shared.uNoise;
    s.uniforms.uGrassRoot = { value: root };
    s.uniforms.uGrassTip = { value: tip };
    s.vertexShader = s.vertexShader
      .replace('#include <common>', `#include <common>\n${GRASS_VERT_PARS}`)
      .replace('#include <beginnormal_vertex>', GRASS_BEGIN_NORMAL)
      .replace('#include <begin_vertex>', 'vec3 transformed = gPos;');
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vT;\nvarying vec3 vGrassCol;')
      .replace('#include <color_fragment>', 'diffuseColor.rgb *= vGrassCol * mix( 0.50, 1.0, smoothstep( 0.0, 0.55, vT ) );');
    applyNoFaceFlip(s);
    applyTranslucency(s, 1.15);
  });

  const group = new Group();
  group.name = 'grass';
  let total = 0;
  const { half, chunk } = opts;
  const cells = Math.ceil((half * 2) / chunk);
  for (let cj = 0; cj < cells; cj++) {
    for (let ci = 0; ci < cells; ci++) {
      const x0 = -half + ci * chunk;
      const z0 = -half + cj * chunk;
      const rng = mulberry32(1000 + cj * 131 + ci * 17);
      const nearChunk = Math.hypot(x0 + chunk / 2 - 2, z0 + chunk / 2 - 1) < 40;
      // blades grow in tufts of a few, which reads far richer than an even scatter
      const tufts = Math.floor((chunk * chunk * opts.density) / 4.5);
      const roots: number[] = [];
      const data: number[] = [];
      let minY = Infinity;
      let maxY = -Infinity;
      for (let i = 0; i < tufts; i++) {
        const x = x0 + rng() * chunk;
        const z = z0 + rng() * chunk;
        const r = Math.hypot(x - 2, z - 1);
        // thin out with distance; the ground texture carries the far field
        const keep = 1 - smoothstep(17, half * 0.92, r) * 0.87;
        if (rng() > keep) continue;
        sample(x, z, m);
        const block = Math.max(smoothstep(0.12, 0.5, m[0]!), smoothstep(0.08, 0.42, m[1]!), smoothstep(0.2, 0.6, m[2]!));
        if (rng() < block) continue;
        if (cottageSdf(x, z) < 0.2) continue;
        if (Math.hypot(x - WELL.x, z - WELL.z) < WELL.r + 0.2) continue;
        const meadow = m[3]!;
        const far = smoothstep(16, half, r);
        const y = terrainHeight(x, z);
        // short and tidy near home, taller in the meadow; shorter again beside paths and soil
        let th = 0.17 + rng() * 0.13 + meadow * (0.14 + rng() * 0.22);
        th *= 1 - 0.45 * Math.min(Math.max(m[0]!, m[1]!) * 2, 1);
        const tint = rng();
        const nb = 3 + Math.floor(rng() * 4);
        const spread = 0.05 + rng() * 0.07 + far * 0.1;
        for (let b = 0; b < nb; b++) {
          const a = rng() * Math.PI * 2;
          const d = Math.sqrt(rng()) * spread;
          const h = th * (0.6 + rng() * 0.7) * (1 + far * 0.4);
          const w = (0.02 + rng() * 0.018) * (1 + far * 2.6);
          roots.push(x + Math.cos(a) * d, y - 0.01, z + Math.sin(a) * d);
          data.push(rng() * Math.PI * 2, h, w, tint * 0.7 + rng() * 0.3);
        }
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
      const count = roots.length / 3;
      if (count === 0) continue;
      const geo = new InstancedBufferGeometry();
      geo.setAttribute('position', nearChunk ? hiPos : loPos);
      geo.setIndex(nearChunk ? hiIdx : loIdx);
      geo.setAttribute('aRoot', new InstancedBufferAttribute(new Float32Array(roots), 3));
      geo.setAttribute('aData', new InstancedBufferAttribute(new Float32Array(data), 4));
      geo.instanceCount = count;
      const cy = (minY + maxY) / 2;
      geo.boundingSphere = new Sphere(new Vector3(x0 + chunk / 2, cy, z0 + chunk / 2), Math.hypot(chunk / 2, chunk / 2, (maxY - minY) / 2 + 0.8));
      const mesh = new Mesh(geo, mat);
      mesh.receiveShadow = true;
      mesh.castShadow = false;
      mesh.matrixAutoUpdate = false;
      group.add(mesh);
      total += count;
    }
  }
  return { group, material: mat, count: total };
}
