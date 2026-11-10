import {
  BackSide,
  Color,
  Mesh,
  PMREMGenerator,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  Vector2,
  Vector3,
  type PerspectiveCamera,
  type WebGLRenderTarget,
  type WebGLRenderer,
} from 'three';
import { SunLight } from 'three/addons/lights/SunLight.js';
import { shared } from '../core/shared';
import { clamp, lerp, smoothstep } from '../util/math';

interface Key {
  h: number;
  sun: [number, number, number];
  sunI: number;
  zen: [number, number, number];
  hor: [number, number, number];
  fog: [number, number, number];
  fogD: number;
  env: number;
  exposure: number;
  stars: number;
  glow: number;
  cloud: number;
}

// Keyframes over a 24h day. Colours are linear.
const KEYS: Key[] = [
  { h: 0, sun: [0.5, 0.64, 1.0], sunI: 0.42, zen: [0.010, 0.018, 0.050], hor: [0.030, 0.050, 0.105], fog: [0.028, 0.045, 0.090], fogD: 0.010, env: 1.5, exposure: 1.5, stars: 1, glow: 1, cloud: 0.0 },
  { h: 4.8, sun: [0.5, 0.64, 1.0], sunI: 0.4, zen: [0.012, 0.022, 0.060], hor: [0.050, 0.065, 0.130], fog: [0.040, 0.055, 0.105], fogD: 0.012, env: 1.5, exposure: 1.5, stars: 1, glow: 1, cloud: 0.0 },
  { h: 6.3, sun: [1.0, 0.52, 0.28], sunI: 1.3, zen: [0.10, 0.18, 0.40], hor: [0.95, 0.50, 0.30], fog: [0.80, 0.52, 0.40], fogD: 0.014, env: 1.1, exposure: 1.02, stars: 0, glow: 0.5, cloud: 0.5 },
  { h: 8.0, sun: [1.0, 0.86, 0.70], sunI: 3.2, zen: [0.14, 0.32, 0.72], hor: [0.60, 0.74, 0.92], fog: [0.62, 0.73, 0.88], fogD: 0.0064, env: 1.3, exposure: 0.95, stars: 0, glow: 0, cloud: 1 },
  { h: 12.5, sun: [1.0, 0.96, 0.90], sunI: 3.9, zen: [0.09, 0.27, 0.76], hor: [0.50, 0.70, 0.95], fog: [0.54, 0.69, 0.92], fogD: 0.0055, env: 1.0, exposure: 0.86, stars: 0, glow: 0, cloud: 1 },
  { h: 16.0, sun: [1.0, 0.86, 0.66], sunI: 3.9, zen: [0.10, 0.26, 0.70], hor: [0.66, 0.76, 0.90], fog: [0.62, 0.72, 0.88], fogD: 0.0060, env: 1.0, exposure: 0.9, stars: 0, glow: 0, cloud: 1 },
  { h: 17.8, sun: [1.0, 0.70, 0.42], sunI: 4.0, zen: [0.10, 0.22, 0.60], hor: [0.98, 0.70, 0.44], fog: [0.74, 0.70, 0.74], fogD: 0.0068, env: 1.05, exposure: 0.94, stars: 0, glow: 0.05, cloud: 1 },
  { h: 19.3, sun: [1.0, 0.44, 0.20], sunI: 2.2, zen: [0.09, 0.13, 0.35], hor: [0.98, 0.46, 0.24], fog: [0.56, 0.36, 0.33], fogD: 0.010, env: 1.1, exposure: 1.02, stars: 0.05, glow: 0.85, cloud: 0.8 },
  { h: 20.3, sun: [0.7, 0.5, 0.6], sunI: 0.05, zen: [0.028, 0.045, 0.130], hor: [0.26, 0.17, 0.24], fog: [0.14, 0.11, 0.18], fogD: 0.011, env: 1.3, exposure: 1.3, stars: 0.55, glow: 1, cloud: 0.25 },
  { h: 21.6, sun: [0.5, 0.64, 1.0], sunI: 0.42, zen: [0.010, 0.018, 0.050], hor: [0.030, 0.050, 0.105], fog: [0.028, 0.045, 0.090], fogD: 0.010, env: 1.5, exposure: 1.5, stars: 1, glow: 1, cloud: 0.0 },
  { h: 24, sun: [0.5, 0.64, 1.0], sunI: 0.42, zen: [0.010, 0.018, 0.050], hor: [0.030, 0.050, 0.105], fog: [0.028, 0.045, 0.090], fogD: 0.010, env: 1.5, exposure: 1.5, stars: 1, glow: 1, cloud: 0.0 },
];

export interface DayParams {
  sun: Color;
  sunI: number;
  zen: Color;
  hor: Color;
  fog: Color;
  fogD: number;
  env: number;
  exposure: number;
  stars: number;
  glow: number;
  cloud: number;
}

const SUNRISE = 5.9;
const SUNSET = 20.0;

const SKY_VERT = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize( position );
  vec4 p = modelViewMatrix * vec4( position, 1.0 );
  gl_Position = projectionMatrix * p;
  gl_Position.z = gl_Position.w; // pin to the far plane
}
`;

const SKY_FRAG = /* glsl */ `
precision highp float;
varying vec3 vDir;
uniform vec3 uZenith;
uniform vec3 uHorizon;
uniform vec3 uGround;
uniform vec3 uSunDir;
uniform vec3 uMoonDir;
uniform vec3 uSunCol;
uniform float uSunDisc;
uniform float uStars;
uniform float uCloudAmt;
uniform vec2 uCloudOff;
uniform float uNight;

float h21( vec2 p ) {
  p = fract( p * vec2( 0.1031, 0.1030 ) );
  p += dot( p, p.yx + 33.33 );
  return fract( ( p.x + p.y ) * p.x );
}
float vn( vec2 p ) {
  vec2 i = floor( p );
  vec2 f = fract( p );
  vec2 u = f * f * ( 3.0 - 2.0 * f );
  return mix( mix( h21( i ), h21( i + vec2( 1.0, 0.0 ) ), u.x ), mix( h21( i + vec2( 0.0, 1.0 ) ), h21( i + vec2( 1.0, 1.0 ) ), u.x ), u.y );
}
float fbm( vec2 p ) {
  float a = 0.5;
  float s = 0.0;
  for ( int i = 0; i < 5; i ++ ) {
    s += a * vn( p );
    p = mat2( 1.6, 1.2, -1.2, 1.6 ) * p + 3.7;
    a *= 0.5;
  }
  return s;
}

void main() {
  vec3 dir = normalize( vDir );
  float h = dir.y;
  float sd = max( dot( dir, uSunDir ), 0.0 );
  // the horizon only carries its full warmth on the sun's side of the sky
  float up = 1.0 - exp( - max( h, 0.0 ) * 4.2 );
  vec3 horiz = mix( mix( uHorizon, uZenith, 0.42 ), uHorizon, 0.30 + 0.70 * sd * sd );
  vec3 col = mix( horiz, uZenith, up );

  float band = exp( - max( h, 0.0 ) * 5.0 );
  // warm scattering toward the sun, strongest along the horizon
  col += uSunCol * ( pow( sd, 5.0 ) * 0.30 * band + pow( sd, 24.0 ) * 0.30 + pow( sd, 180.0 ) * 0.9 + pow( sd, 1400.0 ) * 3.0 );
  // sun disc (hidden while the environment map is captured)
  col += uSunCol * 24.0 * smoothstep( 0.99915, 0.99985, dot( dir, uSunDir ) ) * uSunDisc;

  // moon
  float md = dot( dir, uMoonDir );
  col += vec3( 0.75, 0.82, 1.0 ) * ( smoothstep( 0.9994, 0.9997, md ) * 2.2 + pow( max( md, 0.0 ), 200.0 ) * 0.12 ) * uNight * uSunDisc;

  // stars
  if ( uStars > 0.01 && h > 0.0 ) {
    vec2 sp = dir.xz / ( h + 0.35 ) * 90.0;
    vec2 cell = floor( sp );
    float r = h21( cell );
    vec2 o = vec2( h21( cell + 3.1 ), h21( cell + 7.7 ) ) - 0.5;
    float d = length( fract( sp ) - 0.5 - o * 0.6 );
    float star = smoothstep( 0.09, 0.0, d ) * step( 0.93, r ) * ( 0.4 + 0.6 * h21( cell + 1.3 ) );
    col += vec3( 0.85, 0.9, 1.0 ) * star * uStars * smoothstep( 0.0, 0.25, h ) * 1.4;
  }

  // soft cumulus layer
  if ( h > - 0.01 ) {
    vec2 uv = dir.xz / ( h + 0.24 ) * 0.62 + uCloudOff;
    float d1 = fbm( uv );
    float d2 = fbm( uv * 2.7 + 11.0 );
    float dens = d1 * 0.78 + d2 * 0.22;
    float c = smoothstep( 0.52, 0.72, dens );
    // light from the sun side: compare against density a step toward the sun
    float toward = fbm( uv + normalize( uSunDir.xz + 1e-4 ) * 0.22 );
    float lit = clamp( 0.60 + ( dens - toward ) * 3.4, 0.0, 1.0 );
    vec3 lightCol = mix( uHorizon * 0.75 + uSunCol * 0.75, vec3( 1.0 ), 0.25 ) * ( 0.95 + 0.6 * sd );
    vec3 darkCol = mix( uZenith, uHorizon, 0.38 ) * 1.05 + vec3( 0.02, 0.02, 0.05 );
    vec3 cc = mix( darkCol, lightCol, lit );
    c *= smoothstep( 0.0, 0.14, h ) * uCloudAmt;
    col = mix( col, cc, c * 0.9 );
  }

  // below the horizon: bounce colour for the environment map
  col = mix( col, uGround, smoothstep( 0.0, - 0.06, h ) );
  gl_FragColor = vec4( col, 1.0 );
}
`;

export class Environment {
  readonly sun = new SunLight(0xffffff, 3);
  readonly dome: Mesh;
  private readonly mat: ShaderMaterial;
  private readonly pmrem: PMREMGenerator;
  private readonly envScene = new Scene();
  private envRT: WebGLRenderTarget | null = null;
  private envTimer = 0;

  hour = 17.0;
  day = 1;
  /** Game hours per real second while running. */
  speed = 24 / 600;
  paused = false;

  readonly sunDir = new Vector3(0, 1, 0);
  readonly moonDir = new Vector3(0, 1, 0);
  /** Direction the active key light comes from. */
  readonly lightDir = new Vector3(0, 1, 0);
  readonly p: DayParams = {
    sun: new Color(),
    sunI: 1,
    zen: new Color(),
    hor: new Color(),
    fog: new Color(),
    fogD: 0.008,
    env: 1,
    exposure: 1,
    stars: 0,
    glow: 0,
    cloud: 1,
  };
  /** 0 by day, 1 at night. */
  night = 0;
  /** Scales cloud shadow strength (0 at night). */
  daylight = 1;
  private readonly cloudOff = new Vector2(0, 0);

  constructor(
    renderer: WebGLRenderer,
    private readonly scene: Scene,
  ) {
    this.pmrem = new PMREMGenerator(renderer);
    this.mat = new ShaderMaterial({
      vertexShader: SKY_VERT,
      fragmentShader: SKY_FRAG,
      side: BackSide,
      depthWrite: false,
      depthTest: true,
      fog: false,
      uniforms: {
        uZenith: { value: this.p.zen },
        uHorizon: { value: this.p.hor },
        uGround: { value: new Color(0.1, 0.12, 0.06) },
        uSunDir: { value: this.sunDir },
        uMoonDir: { value: this.moonDir },
        uSunCol: { value: new Color(1, 1, 1) },
        uSunDisc: { value: 1 },
        uStars: { value: 0 },
        uCloudAmt: { value: 1 },
        uCloudOff: { value: this.cloudOff },
        uNight: { value: 0 },
      },
    });
    const geo = new SphereGeometry(1, 48, 24);
    this.dome = new Mesh(geo, this.mat);
    this.dome.scale.setScalar(1800);
    this.dome.frustumCulled = false;
    this.dome.renderOrder = -100;
    this.dome.name = 'sky';
    scene.add(this.dome);

    const envDome = new Mesh(geo, this.mat);
    envDome.scale.setScalar(50);
    this.envScene.add(envDome);

    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 78;
    this.sun.shadow.bias = -0.00035;
    this.sun.shadow.normalBias = 0.035;
    this.sun.shadow.radius = 2.2;
    this.sun.layers.enableAll();
    scene.add(this.sun);

    this.sample();
    this.refreshEnv();
  }

  private sample(): void {
    const h = ((this.hour % 24) + 24) % 24;
    let i = 0;
    while (i < KEYS.length - 2 && KEYS[i + 1]!.h <= h) i++;
    const a = KEYS[i]!;
    const b = KEYS[i + 1]!;
    const t = smoothstep(0, 1, clamp((h - a.h) / (b.h - a.h), 0, 1));
    const p = this.p;
    p.sun.setRGB(lerp(a.sun[0], b.sun[0], t), lerp(a.sun[1], b.sun[1], t), lerp(a.sun[2], b.sun[2], t));
    p.zen.setRGB(lerp(a.zen[0], b.zen[0], t), lerp(a.zen[1], b.zen[1], t), lerp(a.zen[2], b.zen[2], t));
    p.hor.setRGB(lerp(a.hor[0], b.hor[0], t), lerp(a.hor[1], b.hor[1], t), lerp(a.hor[2], b.hor[2], t));
    p.fog.setRGB(lerp(a.fog[0], b.fog[0], t), lerp(a.fog[1], b.fog[1], t), lerp(a.fog[2], b.fog[2], t));
    p.sunI = lerp(a.sunI, b.sunI, t);
    p.fogD = lerp(a.fogD, b.fogD, t);
    p.env = lerp(a.env, b.env, t);
    p.exposure = lerp(a.exposure, b.exposure, t);
    p.stars = lerp(a.stars, b.stars, t);
    p.glow = lerp(a.glow, b.glow, t);
    p.cloud = lerp(a.cloud, b.cloud, t);

    // sun arc: rises in the east (+X), swings through the north (-Z), sets in the west (-X)
    const th = ((h - SUNRISE) / (SUNSET - SUNRISE)) * Math.PI;
    this.sunDir.set(Math.cos(th), Math.sin(th) * 0.86, -Math.sin(th) * 0.52 - 0.16).normalize();
    // moon: opposite side of the sky, on its own gentle arc
    const nightLen = 24 - (SUNSET - SUNRISE);
    const hn = h >= SUNSET ? h - SUNSET : h + 24 - SUNSET;
    const tm = (hn / nightLen) * Math.PI;
    this.moonDir.set(Math.cos(tm) * 0.8, Math.sin(tm) * 0.75 + 0.12, Math.sin(tm) * 0.35 + 0.25).normalize();

    const sunUp = smoothstep(-0.03, 0.09, this.sunDir.y);
    this.night = 1 - smoothstep(-0.12, 0.05, this.sunDir.y);
    this.daylight = sunUp;
    const useSun = this.sunDir.y > -0.02;
    this.lightDir.copy(useSun ? this.sunDir : this.moonDir);
    const fade = useSun ? sunUp : smoothstep(0.02, 0.2, this.moonDir.y) * this.night;
    this.sun.color.copy(p.sun);
    this.sun.intensity = p.sunI * fade;
    this.sun.position.copy(this.lightDir);

    const u = this.mat.uniforms;
    (u.uSunCol!.value as Color).copy(p.sun).multiplyScalar(sunUp);
    u.uStars!.value = p.stars;
    u.uCloudAmt!.value = 0.35 + 0.65 * p.cloud;
    u.uNight!.value = this.night;
    const g = u.uGround!.value as Color;
    const bounce = Math.max(this.sunDir.y, 0) * p.sunI * 0.085 * sunUp;
    g.setRGB((p.hor.r * 0.3 + p.sun.r * bounce) * 0.5, (p.hor.g * 0.3 + p.sun.g * bounce) * 0.62, (p.hor.b * 0.3 + p.sun.b * bounce) * 0.3);

    shared.uSunDir.value.copy(this.lightDir);
    shared.uSunColor.value.copy(p.sun).multiplyScalar(this.sun.intensity);
    this.scene.environmentIntensity = p.env;
  }

  private refreshEnv(): void {
    const u = this.mat.uniforms;
    u.uSunDisc!.value = 0;
    const rt = this.pmrem.fromScene(this.envScene, 0, 0.1, 200);
    u.uSunDisc!.value = 1;
    this.scene.environment = rt.texture;
    if (this.envRT) this.envRT.dispose();
    this.envRT = rt;
  }

  /** Jump to a time (hours, 0-24) and rebuild lighting immediately. */
  setHour(h: number): void {
    this.hour = ((h % 24) + 24) % 24;
    this.sample();
    this.refreshEnv();
  }

  update(dt: number, camera: PerspectiveCamera): void {
    if (!this.paused) {
      // nights pass quicker than days
      const nightBoost = 1 + this.night * 2.2;
      this.hour += dt * this.speed * nightBoost;
      if (this.hour >= 24) {
        this.hour -= 24;
        this.day++;
      }
    }
    this.cloudOff.x += dt * 0.006 * shared.uWind.value.x;
    this.cloudOff.y += dt * 0.006 * shared.uWind.value.y;
    this.sample();
    this.dome.position.copy(camera.position);
    this.envTimer += dt;
    if (this.envTimer > 0.6) {
      this.envTimer = 0;
      this.refreshEnv();
    }
  }
}
