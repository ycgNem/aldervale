import { Color, HalfFloatType, Matrix4, NoToneMapping, SRGBColorSpace, Uniform, Vector3, WebGLRenderer, type PerspectiveCamera, type Scene } from 'three';
import {
  BlendFunction,
  BloomEffect,
  Effect,
  EffectAttribute,
  EffectComposer,
  EffectPass,
  KernelSize,
  RenderPass,
  SMAAEffect,
  SMAAPreset,
  TiltShiftEffect,
  ToneMappingEffect,
  ToneMappingMode,
  VignetteEffect,
} from 'postprocessing';
import { N8AOPostPass } from 'n8ao';
import type { Environment } from './sky';

const ATMOS_FRAG = /* glsl */ `
uniform mat4 uProjInv;
uniform mat4 uCamWorld;
uniform vec3 uCamPos;
uniform vec3 uFogColor;
uniform vec3 uSunGlow;
uniform vec3 uSunDir;
uniform float uDensity;
uniform float uFalloff;
uniform float uStart;

void mainImage( const in vec4 inputColor, const in vec2 uv, const in float depth, out vec4 outputColor ) {
  if ( depth >= 0.999999 ) { outputColor = inputColor; return; }
  vec4 ndc = vec4( uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0 );
  vec4 view = uProjInv * ndc;
  view /= view.w;
  vec3 wp = ( uCamWorld * view ).xyz;
  vec3 rd = wp - uCamPos;
  float dist = length( rd );
  rd /= max( dist, 1e-4 );
  // keep the foreground crisp: haze only builds beyond the yard
  float fd = max( dist - uStart, 0.0 );
  // analytic exponential height fog: dense in the hollows, thin on the hilltops
  float a = uDensity * exp( - uCamPos.y * uFalloff );
  float dy = rd.y * uFalloff;
  float od = abs( dy ) > 1e-5 ? a * ( 1.0 - exp( - fd * dy ) ) / dy : a * fd;
  float fog = 1.0 - exp( - max( od, 0.0 ) );
  // in-scattering warms toward the sun
  float sd = max( dot( rd, uSunDir ), 0.0 );
  vec3 fc = uFogColor + uSunGlow * ( pow( sd, 3.0 ) * 0.42 + pow( sd, 30.0 ) * 0.30 );
  outputColor = vec4( mix( inputColor.rgb, fc, fog ), inputColor.a );
}
`;

class AtmosphereEffect extends Effect {
  constructor() {
    super('AtmosphereEffect', ATMOS_FRAG, {
      blendFunction: BlendFunction.SET,
      attributes: EffectAttribute.DEPTH,
      uniforms: new Map<string, Uniform>([
        ['uProjInv', new Uniform(new Matrix4())],
        ['uCamWorld', new Uniform(new Matrix4())],
        ['uCamPos', new Uniform(new Vector3())],
        ['uFogColor', new Uniform(new Color())],
        ['uSunGlow', new Uniform(new Color())],
        ['uSunDir', new Uniform(new Vector3(0, 1, 0))],
        ['uDensity', new Uniform(0.008)],
        ['uFalloff', new Uniform(0.05)],
        ['uStart', new Uniform(15)],
      ]),
    });
  }
}

const GRADE_FRAG = /* glsl */ `
uniform float uSaturation;
uniform float uContrast;
uniform vec3 uShadowTint;
uniform vec3 uHighTint;
void mainImage( const in vec4 inputColor, const in vec2 uv, out vec4 outputColor ) {
  vec3 c = max( inputColor.rgb, 0.0 );
  float l = dot( c, vec3( 0.2126, 0.7152, 0.0722 ) );
  c = mix( vec3( l ), c, uSaturation );
  // work in a display-like curve so contrast pivots on mid grey
  c = pow( max( c, 0.0 ), vec3( 1.0 / 2.2 ) );
  c = ( c - 0.5 ) * uContrast + 0.5;
  float lum = dot( c, vec3( 0.299, 0.587, 0.114 ) );
  c += ( 1.0 - smoothstep( 0.0, 0.45, lum ) ) * uShadowTint + smoothstep( 0.55, 1.0, lum ) * uHighTint;
  c = pow( clamp( c, 0.0, 1.0 ), vec3( 2.2 ) );
  outputColor = vec4( c, inputColor.a );
}
`;

class GradeEffect extends Effect {
  constructor() {
    super('GradeEffect', GRADE_FRAG, {
      blendFunction: BlendFunction.SET,
      uniforms: new Map<string, Uniform>([
        ['uSaturation', new Uniform(1.2)],
        ['uContrast', new Uniform(1.13)],
        ['uShadowTint', new Uniform(new Vector3(-0.012, 0.0, 0.026))],
        ['uHighTint', new Uniform(new Vector3(0.026, 0.01, -0.018))],
      ]),
    });
  }
}

export interface PipelineOptions {
  tone: 'agx' | 'aces';
  msaa: number;
  ao: boolean;
  tilt: boolean;
}

export class Pipeline {
  readonly renderer: WebGLRenderer;
  readonly composer: EffectComposer;
  readonly atmosphere = new AtmosphereEffect();
  readonly grade = new GradeEffect();
  readonly bloom: BloomEffect;
  readonly tilt: TiltShiftEffect;
  readonly ao: N8AOPostPass;
  /** Callbacks that render auxiliary targets (water) before the main pass. */
  readonly prePasses: (() => void)[] = [];
  pixelRatio = 1;

  constructor(
    canvas: HTMLCanvasElement,
    scene: Scene,
    private readonly camera: PerspectiveCamera,
    opts: PipelineOptions,
  ) {
    const renderer = new WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', stencil: false, depth: false, alpha: false });
    this.renderer = renderer;
    this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(this.pixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = NoToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.autoUpdate = false;
    renderer.info.autoReset = false;

    const samples = Math.min(opts.msaa, renderer.capabilities.maxSamples);
    this.composer = new EffectComposer(renderer, { frameBufferType: HalfFloatType, multisampling: samples });
    this.composer.addPass(new RenderPass(scene, camera));

    this.ao = new N8AOPostPass(scene, camera, window.innerWidth, window.innerHeight);
    // n8ao's two-attachment target overrides `texture` to return the array, which three r187's
    // setupRenderTarget reads as a single texture. Point it back at the first attachment.
    const aoInternals = this.ao as unknown as { configureHalfResTargets: () => void; depthDownsampleTarget: { textures: unknown[] } | null };
    const fixTarget = (): void => {
      const t = aoInternals.depthDownsampleTarget;
      if (t) Object.defineProperty(t, 'texture', { configurable: true, get: () => t.textures[0] });
    };
    const configure = aoInternals.configureHalfResTargets.bind(this.ao);
    aoInternals.configureHalfResTargets = () => {
      configure();
      fixTarget();
    };
    fixTarget();
    const c = this.ao.configuration;
    c.aoRadius = 1.1;
    c.distanceFalloff = 1.0;
    c.intensity = 2.4;
    c.aoSamples = 12;
    c.denoiseSamples = 6;
    c.denoiseRadius = 10;
    c.halfRes = true;
    c.depthAwareUpsampling = true;
    c.color = new Color(0.03, 0.035, 0.07);
    this.ao.enabled = opts.ao;
    this.composer.addPass(this.ao);

    this.bloom = new BloomEffect({ mipmapBlur: true, luminanceThreshold: 1.05, luminanceSmoothing: 0.35, intensity: 0.42, radius: 0.72, levels: 7 });
    this.composer.addPass(new EffectPass(camera, this.atmosphere, this.bloom));

    this.tilt = new TiltShiftEffect({ offset: 0.05, rotation: 0, focusArea: 0.78, feather: 0.55, kernelSize: KernelSize.VERY_SMALL, resolutionScale: 1 });
    const tiltPass = new EffectPass(camera, this.tilt);
    tiltPass.enabled = opts.tilt;
    this.composer.addPass(tiltPass);

    const tone = new ToneMappingEffect({ mode: opts.tone === 'aces' ? ToneMappingMode.ACES_FILMIC : ToneMappingMode.AGX });
    const vignette = new VignetteEffect({ offset: 0.32, darkness: 0.42 });
    const effects: Effect[] = [tone, this.grade, vignette];
    if (samples === 0) effects.push(new SMAAEffect({ preset: SMAAPreset.HIGH }));
    this.composer.addPass(new EffectPass(camera, ...effects));

    if (opts.tone === 'aces') {
      this.grade.uniforms.get('uSaturation')!.value = 1.0;
      this.grade.uniforms.get('uContrast')!.value = 1.0;
    }
  }

  resize(w: number, h: number): void {
    this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(this.pixelRatio);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  render(dt: number, env: Environment): void {
    const u = this.atmosphere.uniforms;
    (u.get('uProjInv')!.value as Matrix4).copy(this.camera.projectionMatrixInverse);
    (u.get('uCamWorld')!.value as Matrix4).copy(this.camera.matrixWorld);
    (u.get('uCamPos')!.value as Vector3).copy(this.camera.position);
    (u.get('uFogColor')!.value as Color).copy(env.p.fog);
    (u.get('uSunGlow')!.value as Color).copy(env.p.sun).multiplyScalar(env.daylight * 0.9);
    (u.get('uSunDir')!.value as Vector3).copy(env.sunDir);
    u.get('uDensity')!.value = env.p.fogD * 0.4;
    this.renderer.toneMappingExposure = env.p.exposure;

    this.renderer.info.reset();
    for (const p of this.prePasses) p();
    this.renderer.shadowMap.needsUpdate = true;
    this.composer.render(dt);
  }
}
