import {
  Color,
  DataTexture,
  LinearFilter,
  LinearMipmapLinearFilter,
  Material,
  RGBAFormat,
  RepeatWrapping,
  ShaderChunk,
  UnsignedByteType,
  Vector3,
  Vector4,
  type Texture,
  type WebGLProgramParametersWithUniforms,
} from 'three';

export type Shader = WebGLProgramParametersWithUniforms;

/** Uniforms shared by every material that sways, glows or sits under a cloud. */
export const shared = {
  uTime: { value: 0 },
  /** xy = wind direction on the XZ plane, z = strength. */
  uWind: { value: new Vector4(0.82, 0.57, 1, 0) },
  uNoise: { value: null as Texture | null },
  /** xy = scroll offset, z = shadow strength, w = world scale. */
  uCloud: { value: new Vector4(0, 0, 0, 1 / 55) },
  uSunDir: { value: new Vector3(0, 1, 0) },
  uSunColor: { value: new Color(1, 1, 1) },
};

/** Periodic value-noise fbm, tileable, three decorrelated channels + a finer one in alpha. */
export function makeNoiseTexture(size = 256): DataTexture {
  const data = new Uint8Array(size * size * 4);
  const hash = (x: number, y: number, s: number): number => {
    let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(s, 1442695041);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  };
  const vnoise = (x: number, y: number, period: number, seed: number): number => {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const fx = x - ix;
    const fy = y - iy;
    const ux = fx * fx * (3 - 2 * fx);
    const uy = fy * fy * (3 - 2 * fy);
    const w = (v: number): number => ((v % period) + period) % period;
    const a = hash(w(ix), w(iy), seed);
    const b = hash(w(ix + 1), w(iy), seed);
    const c = hash(w(ix), w(iy + 1), seed);
    const d = hash(w(ix + 1), w(iy + 1), seed);
    return a + (b - a) * ux + (c - a + (a - b - c + d) * ux) * uy;
  };
  const fbm = (u: number, v: number, base: number, oct: number, seed: number): number => {
    let amp = 0.5;
    let sum = 0;
    let norm = 0;
    let f = base;
    for (let o = 0; o < oct; o++) {
      sum += amp * vnoise(u * f, v * f, f, seed + o * 17);
      norm += amp;
      amp *= 0.5;
      f *= 2;
    }
    return sum / norm;
  };
  const chans: Float32Array[] = [];
  const cfg: [number, number][] = [
    [4, 4],
    [8, 4],
    [16, 3],
    [32, 2],
  ];
  for (let c = 0; c < 4; c++) {
    const arr = new Float32Array(size * size);
    let lo = Infinity;
    let hi = -Infinity;
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const v = fbm(x / size, y / size, cfg[c]![0], cfg[c]![1], 31 + c * 101);
        arr[y * size + x] = v;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    for (let i = 0; i < arr.length; i++) arr[i] = (arr[i]! - lo) / (hi - lo);
    chans.push(arr);
  }
  for (let i = 0; i < size * size; i++) {
    data[i * 4] = Math.round(chans[0]![i]! * 255);
    data[i * 4 + 1] = Math.round(chans[1]![i]! * 255);
    data[i * 4 + 2] = Math.round(chans[2]![i]! * 255);
    data[i * 4 + 3] = Math.round(chans[3]![i]! * 255);
  }
  const tex = new DataTexture(data, size, size, RGBAFormat, UnsignedByteType);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  tex.magFilter = LinearFilter;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.needsUpdate = true;
  return tex;
}

/** Wind field shared by grass, crops, leaves and their shadow passes. */
export const WIND_GLSL = /* glsl */ `
uniform float uTime;
uniform vec4 uWind;
uniform sampler2D uNoise;
// xz = horizontal push (world units at weight 1), y = gust amount 0..1
vec3 windAt( vec3 wp ) {
  vec2 dir = uWind.xy;
  float gust = textureLod( uNoise, wp.xz * 0.0105 - dir * uTime * 0.045, 0.0 ).r;
  vec2 fl = textureLod( uNoise, wp.xz * 0.11 - dir * uTime * 0.30, 0.0 ).gb - 0.5;
  float g = smoothstep( 0.28, 0.82, gust );
  vec2 d = dir * ( 0.16 + g ) + fl * ( 0.30 + g * 0.55 );
  return vec3( d.x, g, d.y ) * uWind.z;
}
`;

const CLOUD_GLSL = /* glsl */ `
uniform vec4 uCloud;
float cloudHash( vec2 p ) {
  p = fract( p * vec2( 0.1031, 0.1030 ) );
  p += dot( p, p.yx + 33.33 );
  return fract( ( p.x + p.y ) * p.x );
}
float cloudNoise( vec2 p ) {
  vec2 i = floor( p );
  vec2 f = fract( p );
  vec2 u = f * f * f * ( f * ( f * 6.0 - 15.0 ) + 10.0 );
  return mix( mix( cloudHash( i ), cloudHash( i + vec2( 1.0, 0.0 ) ), u.x ),
              mix( cloudHash( i + vec2( 0.0, 1.0 ) ), cloudHash( i + vec2( 1.0, 1.0 ) ), u.x ), u.y );
}
// soft drifting cloud shadows, applied to direct sunlight only
float cloudShadow( vec3 wp ) {
  vec2 p = wp.xz * uCloud.w + uCloud.xy;
  float n = cloudNoise( p ) * 0.62 + cloudNoise( p * 2.13 + 7.3 ) * 0.28 + cloudNoise( p * 4.7 + 1.9 ) * 0.10;
  return 1.0 - uCloud.z * smoothstep( 0.50, 0.70, n );
}
`;

let installed = false;

/** Patch three's shared shader chunks once, before any material compiles. */
export function installGlobalShaderPatches(): void {
  if (installed) return;
  installed = true;
  ShaderChunk.lights_pars_begin = ShaderChunk.lights_pars_begin + CLOUD_GLSL;
  const needle = 'getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) : 1.0;';
  if (!ShaderChunk.lights_fragment_begin.includes(needle)) {
    console.warn('[shaders] sun shadow hook not found; cloud shadows disabled');
  }
  ShaderChunk.lights_fragment_begin = ShaderChunk.lights_fragment_begin.replace(
    needle,
    'getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) * cloudShadow( vSunShadowWorldPosition.xyz ) : 1.0;',
  );
  // every material, including ones we never touch, gets the cloud uniform
  Material.prototype.onBeforeCompile = function (shader: Shader): void {
    shader.uniforms.uCloud = shared.uCloud;
  };
}

/** Attach a shader patch with an explicit cache key (closures share source text). */
export function patch(mat: Material, key: string, fn: (s: Shader) => void): void {
  mat.onBeforeCompile = (s: Shader): void => {
    s.uniforms.uCloud = shared.uCloud;
    fn(s);
  };
  mat.customProgramCacheKey = (): string => key;
}

export interface WindOpts {
  /** Horizontal travel in metres at full weight. */
  amp: number;
  /** Height above the object's origin (metres) at which the weight reaches 1. */
  height: number;
  /** Height below which nothing moves. */
  base?: number;
  /** 0 = whole object moves in phase, 1 = every vertex samples the field itself (leaf flutter). */
  spread?: number;
  /** Small fast per-vertex shimmer in metres (tree leaves). */
  flutter?: number;
}

export function windKey(o: WindOpts | null): string {
  return o ? `w${o.amp}_${o.height}_${o.base ?? 0}_${o.spread ?? 0.25}_${o.flutter ?? 0}` : 'w0';
}

/** Vertex patch: sway in world space after instancing. Works for depth materials too. */
export function applyWindVertex(s: Shader, o: WindOpts): void {
  s.uniforms.uTime = shared.uTime;
  s.uniforms.uWind = shared.uWind;
  s.uniforms.uNoise = shared.uNoise;
  const f = (n: number): string => n.toFixed(4);
  s.vertexShader = s.vertexShader
    .replace('#include <common>', `#include <common>\n${WIND_GLSL}`)
    .replace(
      '#include <project_vertex>',
      /* glsl */ `
vec4 wPos = vec4( transformed, 1.0 );
#ifdef USE_INSTANCING
  wPos = instanceMatrix * wPos;
#endif
wPos = modelMatrix * wPos;
{
  #ifdef USE_INSTANCING
    vec3 rootW = ( modelMatrix * instanceMatrix * vec4( 0.0, 0.0, 0.0, 1.0 ) ).xyz;
  #else
    vec3 rootW = ( modelMatrix * vec4( 0.0, 0.0, 0.0, 1.0 ) ).xyz;
  #endif
  float hgt = max( wPos.y - rootW.y - ${f(o.base ?? 0)}, 0.0 );
  float wgt = pow( min( hgt / ${f(o.height)}, 1.6 ), 1.5 );
  vec3 wf = windAt( mix( rootW, wPos.xyz, ${f(o.spread ?? 0.25)} ) );
  wPos.xz += wf.xz * wgt * ${f(o.amp)};
  wPos.y -= dot( wf.xz, wf.xz ) * wgt * ${f(o.amp * 0.3)};
  wPos.xyz += sin( uTime * vec3( 5.3, 4.1, 6.7 ) + wPos.zxy * vec3( 2.9, 3.7, 3.1 ) ) * ${f(o.flutter ?? 0)} * min( wgt, 1.0 ) * ( 0.35 + wf.y );
}
vec4 mvPosition = viewMatrix * wPos;
gl_Position = projectionMatrix * mvPosition;
`,
    );
}

/** Fragment patch: light bleeding through thin foliage (back-lit glow toward the sun). */
export function applyTranslucency(s: Shader, strength: number): void {
  s.fragmentShader = s.fragmentShader.replace(
    '#include <lights_physical_pars_fragment>',
    /* glsl */ `#include <lights_physical_pars_fragment>
void RE_Direct_Foliage( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
  RE_Direct_Physical( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
  float back = saturate( dot( - geometryNormal, directLight.direction ) * 0.6 + 0.4 );
  float toSun = pow( saturate( dot( geometryViewDir, - directLight.direction ) ), 3.0 );
  vec3 tint = material.diffuseColor * vec3( 1.10, 1.22, 0.50 );
  reflectedLight.directDiffuse += directLight.color * tint * ( back * 0.20 + toSun * 0.55 ) * ${strength.toFixed(3)};
}
#undef RE_Direct
#define RE_Direct RE_Direct_Foliage
`,
  );
}

/** Fragment patch: keep authored normals on both faces (fluffy foliage cards, grass). */
export function applyNoFaceFlip(s: Shader): void {
  s.fragmentShader = s.fragmentShader.replace(
    '#include <normal_fragment_begin>',
    ShaderChunk.normal_fragment_begin.replace('gl_FrontFacing ? 1.0 : - 1.0', '1.0'),
  );
}

/** World-space varyings for shaders that texture by world position. */
export const WORLD_VARYINGS_VERT = /* glsl */ `
varying vec3 vWPos;
varying vec3 vWNormal;
`;
export const WORLD_VARYINGS_ASSIGN = /* glsl */ `
vWPos = ( modelMatrix * vec4( transformed, 1.0 ) ).xyz;
vWNormal = normalize( mat3( modelMatrix ) * objectNormal );
`;
/** Tangent-space normal (already scaled) on world-projected UVs -> view-space `normal`. */
export const WORLD_NORMAL_APPLY = /* glsl */ `
{
  vec3 wn = normalize( vWNormal );
  vec3 wT = normalize( vec3( 1.0, 0.0, 0.0 ) - wn * wn.x );
  vec3 wB = cross( wn, wT );
  vec3 nW = normalize( wT * gNormalTS.x + wB * gNormalTS.y + wn * gNormalTS.z );
  normal = normalize( mat3( viewMatrix ) * nW );
}
`;
