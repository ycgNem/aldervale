import {
  BufferAttribute,
  BufferGeometry,
  Color,
  DataTexture,
  LinearFilter,
  Mesh,
  MeshStandardMaterial,
  RGBAFormat,
  UnsignedByteType,
  Vector2,
  type Texture,
} from 'three';
import type { Assets } from '../core/assets';
import { WORLD_NORMAL_APPLY, WORLD_VARYINGS_ASSIGN, WORLD_VARYINGS_VERT, patch, shared } from '../core/shared';
import { MASK, groundMask, meadowness, terrainHeight, terrainNormal, type GroundMask } from './layout';

export const TERRAIN_HALF = 330;

/** R = bare dirt, G = path, B = shore / pond bed, A = meadow height. */
export function buildMaskTexture(): DataTexture {
  const n = MASK.res;
  const data = new Uint8Array(n * n * 4);
  const gm: GroundMask = { dirt: 0, path: 0, shore: 0 };
  const step = MASK.size / n;
  for (let j = 0; j < n; j++) {
    const z = MASK.min + (j + 0.5) * step;
    for (let i = 0; i < n; i++) {
      const x = MASK.min + (i + 0.5) * step;
      const k = (j * n + i) * 4;
      const border = i < 2 || j < 2 || i > n - 3 || j > n - 3;
      if (border) {
        data[k] = data[k + 1] = data[k + 2] = 0;
        data[k + 3] = 255;
        continue;
      }
      groundMask(x, z, gm);
      data[k] = Math.round(gm.dirt * 255);
      data[k + 1] = Math.round(gm.path * 255);
      data[k + 2] = Math.round(gm.shore * 255);
      data[k + 3] = Math.round(meadowness(x, z) * 255);
    }
  }
  const tex = new DataTexture(data, n, n, RGBAFormat, UnsignedByteType);
  tex.magFilter = LinearFilter;
  tex.minFilter = LinearFilter;
  tex.needsUpdate = true;
  return tex;
}

const TERRAIN_PARS = /* glsl */ `
varying vec3 vWPos;
varying vec3 vWNormal;
uniform sampler2D tGrassA;
uniform sampler2D tGrassN;
uniform sampler2D tDirtA;
uniform sampler2D tDirtN;
uniform sampler2D tPathA;
uniform sampler2D tPathN;
uniform sampler2D tMask;
uniform sampler2D uNoise;
uniform vec2 uMaskMin;
uniform float uMaskSize;
uniform vec3 uGrassTint;
vec3 gNormalTS;
float gRough;
float edgeBlend( float m, float n ) {
  return smoothstep( 0.0, 1.0, clamp( m * 1.7 - 0.35 + ( n - 0.5 ) * 3.2 * m * ( 1.0 - m ), 0.0, 1.0 ) );
}
`;

const TERRAIN_MAP = /* glsl */ `
{
  vec2 uvw = vec2( vWPos.x, - vWPos.z );
  vec2 muv = ( vWPos.xz - uMaskMin ) / uMaskSize;
  vec4 mask = texture2D( tMask, muv );
  vec4 nz = texture2D( uNoise, uvw * 0.043 );
  vec4 nzBig = texture2D( uNoise, uvw * 0.0047 + 0.31 );
  float camDist = length( cameraPosition - vWPos );
  float farMix = smoothstep( 16.0, 70.0, camDist );

  // grass: two scales hide tiling, large soft patches vary the hue
  vec3 gA = texture2D( tGrassA, uvw / 2.0 ).rgb;
  vec3 gAf = texture2D( tGrassA, uvw / 13.7 ).rgb;
  vec3 gN = texture2D( tGrassN, uvw / 2.0 ).xyz * 2.0 - 1.0;
  gA = mix( gA, gAf, farMix * 0.75 ) * uGrassTint;
  float patchN = nzBig.r;
  gA *= mix( vec3( 0.80, 0.90, 0.72 ), vec3( 1.20, 1.10, 0.86 ), patchN );
  gA = mix( gA, gA * vec3( 1.22, 1.10, 0.60 ), smoothstep( 0.62, 0.9, nzBig.g ) * 0.45 );
  gN.xy *= 1.0 - farMix * 0.7;
  // the far hills: broad meadows of drier and lusher grass so they never read as one flat colour
  float hill = smoothstep( 48.0, 150.0, length( vWPos.xz ) );
  vec4 nzHuge = texture2D( uNoise, uvw * 0.0019 + 0.71 );
  vec4 nzMid = texture2D( uNoise, uvw * 0.011 + 0.13 );
  float meadowN = nzHuge.b * 0.7 + nzMid.r * 0.3;
  gA *= mix( vec3( 1.0 ), mix( vec3( 0.66, 0.84, 0.62 ), vec3( 1.22, 1.16, 0.80 ), smoothstep( 0.25, 0.75, meadowN ) ), hill * 0.85 );
  gA = mix( gA, gA * vec3( 1.42, 1.22, 0.58 ), smoothstep( 0.52, 0.70, nzHuge.r * 0.75 + nzMid.g * 0.25 ) * hill * 0.6 );

  vec3 dA = texture2D( tDirtA, uvw / 2.0 ).rgb;
  vec3 dN = texture2D( tDirtN, uvw / 2.0 ).xyz * 2.0 - 1.0;
  vec3 pA = texture2D( tPathA, uvw / 2.0 ).rgb;
  vec3 pN = texture2D( tPathN, uvw / 2.0 ).xyz * 2.0 - 1.0;

  float wDirt = edgeBlend( mask.r, nz.g );
  float wPath = edgeBlend( mask.g, nz.b );
  float wShore = edgeBlend( mask.b, nz.g );

  vec3 col = gA;
  vec3 nrm = gN;
  float rgh = 0.93;
  col = mix( col, dA, wDirt );
  nrm = mix( nrm, dN, wDirt );
  col = mix( col, pA, wPath );
  nrm = mix( nrm, pN, wPath );
  rgh = mix( rgh, 0.88, wPath );
  // shore: damp sand, darker and glossier toward (and under) the waterline
  float wet = smoothstep( 0.25, - 0.45, vWPos.y );
  vec3 sA = pA * mix( vec3( 0.86, 0.80, 0.70 ), vec3( 0.42, 0.40, 0.34 ), wet );
  col = mix( col, sA, wShore );
  nrm = mix( nrm, pN, wShore );
  rgh = mix( rgh, mix( 0.8, 0.35, wet ), wShore );

  diffuseColor.rgb *= col;
  gNormalTS = normalize( vec3( nrm.xy * 1.15, nrm.z ) );
  gRough = rgh;
}
`;

export interface Terrain {
  mesh: Mesh;
  mask: DataTexture;
  material: MeshStandardMaterial;
  /** Average colour of the grass ground layer (linear), for matching blades. */
  grassGround: Color;
}

export function createTerrain(assets: Assets): Terrain {
  const seg = 400;
  const n = seg + 1;
  const pos = new Float32Array(n * n * 3);
  const nor = new Float32Array(n * n * 3);
  const tmp: [number, number, number] = [0, 1, 0];
  // warped grid: dense around the homestead, coarse out on the hills
  const warp = (u: number): number => Math.sign(u) * Math.pow(Math.abs(u), 2.1) * TERRAIN_HALF;
  for (let j = 0; j < n; j++) {
    const z = warp((j / seg) * 2 - 1);
    for (let i = 0; i < n; i++) {
      const x = warp((i / seg) * 2 - 1);
      const k = (j * n + i) * 3;
      pos[k] = x;
      pos[k + 1] = terrainHeight(x, z);
      pos[k + 2] = z;
      terrainNormal(x, z, tmp);
      nor[k] = tmp[0];
      nor[k + 1] = tmp[1];
      nor[k + 2] = tmp[2];
    }
  }
  const idx = new Uint32Array(seg * seg * 6);
  let q = 0;
  for (let j = 0; j < seg; j++) {
    for (let i = 0; i < seg; i++) {
      const a = j * n + i;
      const b = a + 1;
      const c = a + n;
      const d = c + 1;
      idx[q++] = a;
      idx[q++] = c;
      idx[q++] = b;
      idx[q++] = b;
      idx[q++] = c;
      idx[q++] = d;
    }
  }
  const geo = new BufferGeometry();
  geo.setAttribute('position', new BufferAttribute(pos, 3));
  geo.setAttribute('normal', new BufferAttribute(nor, 3));
  geo.setIndex(new BufferAttribute(idx, 1));
  geo.computeBoundingSphere();

  const mask = buildMaskTexture();
  const grass = assets.set('grass');
  const dirt = assets.set('dirt');
  const path = assets.set('path');
  const mat = new MeshStandardMaterial({ color: 0xffffff, roughness: 1, metalness: 0 });
  mat.envMapIntensity = 0.9;
  const grassTint = new Color(1.42, 1.32, 1.2);
  const uniforms: Record<string, { value: Texture | Vector2 | number | Color | null }> = {
    tGrassA: { value: grass.albedo },
    tGrassN: { value: grass.normal },
    tDirtA: { value: dirt.albedo },
    tDirtN: { value: dirt.normal },
    tPathA: { value: path.albedo },
    tPathN: { value: path.normal },
    tMask: { value: mask },
    uMaskMin: { value: new Vector2(MASK.min, MASK.min) },
    uMaskSize: { value: MASK.size },
    uGrassTint: { value: grassTint },
  };
  patch(mat, 'terrain', (s) => {
    Object.assign(s.uniforms, uniforms);
    s.uniforms.uNoise = shared.uNoise;
    s.vertexShader = s.vertexShader
      .replace('#include <common>', `#include <common>\n${WORLD_VARYINGS_VERT}`)
      .replace('#include <project_vertex>', `#include <project_vertex>\n${WORLD_VARYINGS_ASSIGN}`);
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', `#include <common>\n${TERRAIN_PARS}`)
      .replace('#include <map_fragment>', TERRAIN_MAP)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = gRough;')
      .replace('#include <normal_fragment_maps>', WORLD_NORMAL_APPLY);
  });

  const mesh = new Mesh(geo, mat);
  mesh.receiveShadow = true;
  mesh.castShadow = false;
  mesh.name = 'terrain';
  mesh.matrixAutoUpdate = false;
  return { mesh, mask, material: mat, grassGround: grass.avg.clone().multiply(grassTint) };
}
