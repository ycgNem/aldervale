import {
  Color,
  DepthTexture,
  Frustum,
  HalfFloatType,
  LinearFilter,
  Matrix4,
  Mesh,
  PerspectiveCamera,
  Plane,
  PlaneGeometry,
  ShaderMaterial,
  Sphere,
  UnsignedIntType,
  Vector2,
  Vector3,
  Vector4,
  WebGLRenderTarget,
  type Scene,
  type Texture,
  type WebGLRenderer,
} from 'three';
import { shared } from '../core/shared';
import type { Environment } from '../render/sky';
import { POND } from './layout';

export const LAYER_REFLECT = 1;
export const LAYER_REFRACT = 2;

const VERT = /* glsl */ `
varying vec3 vWorld;
varying float vViewZ;
void main() {
  vec4 wp = modelMatrix * vec4( position, 1.0 );
  vWorld = wp.xyz;
  vec4 mv = viewMatrix * wp;
  vViewZ = - mv.z;
  gl_Position = projectionMatrix * mv;
}
`;

const FRAG = /* glsl */ `
precision highp float;
#include <packing>
varying vec3 vWorld;
varying float vViewZ;
uniform sampler2D tRefl;
uniform sampler2D tRefr;
uniform sampler2D tDepth;
uniform sampler2D tNormal;
uniform mat4 uTexMat;
uniform vec2 uRes;
uniform float uNear;
uniform float uFar;
uniform float uTime;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uLight;
uniform vec3 uDeep;

float sceneDepth( vec2 uv ) {
  return - perspectiveDepthToViewZ( texture2D( tDepth, uv ).x, uNear, uFar );
}

void main() {
  vec2 suv = gl_FragCoord.xy / uRes;
  vec3 V = normalize( cameraPosition - vWorld );

  // two ripple layers drifting across each other
  vec2 uv1 = vWorld.xz * 0.21 + uTime * vec2( 0.013, 0.008 );
  vec2 uv2 = vWorld.xz * 0.34 - uTime * vec2( 0.009, 0.015 );
  vec3 n1 = texture2D( tNormal, uv1 ).xyz * 2.0 - 1.0;
  vec3 n2 = texture2D( tNormal, uv2 ).xyz * 2.0 - 1.0;
  vec2 rip = ( n1.xy + n2.xy ) * 0.5;
  vec3 N = normalize( vec3( rip.x * 0.55, 1.0, rip.y * 0.55 ) );

  float thick0 = max( sceneDepth( suv ) - vViewZ, 0.0 );
  // refraction: bend the view through the surface, more where the water is deeper
  vec2 off = rip * 0.045 * smoothstep( 0.0, 0.6, thick0 );
  float zOff = sceneDepth( suv + off );
  if ( zOff < vViewZ ) off = vec2( 0.0 );
  float thick = max( sceneDepth( suv + off ) - vViewZ, 0.0 );
  float depth = thick * clamp( V.y, 0.25, 1.0 );
  vec3 bed = texture2D( tRefr, suv + off ).rgb;

  // depth-based colour: red goes first, then green; deep water scatters teal
  vec3 absorb = exp( - depth * vec3( 2.3, 0.85, 0.70 ) );
  vec3 body = bed * absorb + uDeep * uLight * ( 1.0 - absorb.g );

  // planar reflection, wobbled by the ripples
  vec4 rc = uTexMat * vec4( vWorld, 1.0 );
  vec2 ruv = rc.xy / rc.w + rip * 0.035;
  vec3 refl = texture2D( tRefl, ruv ).rgb;
  float ndv = max( dot( N, V ), 0.0 );
  float fres = mix( 0.06, 1.0, pow( 1.0 - ndv, 3.6 ) );
  vec3 col = mix( body, refl, fres );

  // sun glitter
  vec3 H = normalize( uSunDir + V );
  float spec = pow( max( dot( N, H ), 0.0 ), 300.0 );
  col += uSunColor * spec * 2.0;

  // soft shoreline foam: a bright rim plus slow lapping rings
  float fn = texture2D( tNormal, vWorld.xz * 0.55 + uTime * vec2( 0.02, -0.014 ) ).x;
  float rim = smoothstep( 0.13, 0.0, depth + ( fn - 0.5 ) * 0.12 );
  float ring = smoothstep( 0.085, 0.0, abs( fract( depth * 1.9 - uTime * 0.16 + fn * 0.35 ) - 0.5 ) - 0.38 ) * smoothstep( 0.75, 0.12, depth );
  float foam = clamp( rim * 0.85 + ring * 0.24 * fn * 2.0, 0.0, 1.0 );
  col = mix( col, uLight * 0.82, foam * 0.68 );

  // melt into the bank at the waterline
  col = mix( texture2D( tRefr, suv ).rgb, col, smoothstep( 0.0, 0.05, thick0 ) );
  gl_FragColor = vec4( col, 1.0 );
}
`;

export class Pond {
  readonly mesh: Mesh;
  private readonly mat: ShaderMaterial;
  private readonly reflRT: WebGLRenderTarget;
  private readonly refrRT: WebGLRenderTarget;
  private readonly virtualCam = new PerspectiveCamera();
  private readonly texMat = new Matrix4();
  private readonly bounds = new Sphere(new Vector3(POND.x, POND.level, POND.z), POND.r * 1.35);
  private readonly frustum = new Frustum();
  private readonly pv = new Matrix4();
  private readonly light = new Color();

  constructor(
    private readonly renderer: WebGLRenderer,
    private readonly scene: Scene,
    private readonly camera: PerspectiveCamera,
    normalMap: Texture | null,
  ) {
    const size = renderer.getDrawingBufferSize(new Vector2());
    const w = Math.max(2, Math.floor(size.x / 2));
    const h = Math.max(2, Math.floor(size.y / 2));
    this.reflRT = new WebGLRenderTarget(w, h, { type: HalfFloatType, minFilter: LinearFilter, magFilter: LinearFilter, samples: 2 });
    this.refrRT = new WebGLRenderTarget(w, h, { type: HalfFloatType, minFilter: LinearFilter, magFilter: LinearFilter });
    this.refrRT.depthTexture = new DepthTexture(w, h, UnsignedIntType);

    this.mat = new ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: {
        tRefl: { value: this.reflRT.texture },
        tRefr: { value: this.refrRT.texture },
        tDepth: { value: this.refrRT.depthTexture },
        tNormal: { value: normalMap ?? shared.uNoise.value },
        uTexMat: { value: this.texMat },
        uRes: { value: new Vector2(size.x, size.y) },
        uNear: { value: camera.near },
        uFar: { value: camera.far },
        uTime: shared.uTime,
        uSunDir: shared.uSunDir,
        uSunColor: shared.uSunColor,
        uLight: { value: this.light },
        uDeep: { value: new Color(0.035, 0.16, 0.15) },
      },
    });
    const s = POND.r * 2.9;
    const geo = new PlaneGeometry(s, s, 1, 1);
    geo.rotateX(-Math.PI / 2);
    this.mesh = new Mesh(geo, this.mat);
    this.mesh.position.set(POND.x, POND.level, POND.z);
    this.mesh.name = 'pond';
    this.mesh.renderOrder = 5;
    scene.add(this.mesh);
  }

  resize(): void {
    const size = this.renderer.getDrawingBufferSize(new Vector2());
    const w = Math.max(2, Math.floor(size.x / 2));
    const h = Math.max(2, Math.floor(size.y / 2));
    this.reflRT.setSize(w, h);
    this.refrRT.setSize(w, h);
    (this.mat.uniforms.uRes!.value as Vector2).set(size.x, size.y);
  }

  /** Renders the reflection and refraction targets. Call before the main pass. */
  prePass(env: Environment): void {
    const cam = this.camera;
    this.pv.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    this.frustum.setFromProjectionMatrix(this.pv);
    this.mesh.visible = true;
    if (!this.frustum.intersectsSphere(this.bounds)) return;
    if (cam.position.y <= POND.level + 0.05) return;

    // ambient + sun light arriving at the surface, for foam and scattering
    const up = Math.max(env.lightDir.y, 0);
    this.light.copy(env.p.hor).multiplyScalar(0.55).add(_c.copy(env.p.sun).multiplyScalar(env.sun.intensity * up * 0.32));
    this.mat.uniforms.uNear!.value = cam.near;
    this.mat.uniforms.uFar!.value = cam.far;

    const r = this.renderer;
    const prevTarget = r.getRenderTarget();
    this.mesh.visible = false;

    // --- refraction: what lies under the surface, with depth
    cam.layers.set(LAYER_REFRACT);
    r.setRenderTarget(this.refrRT);
    r.setClearColor(0x000000, 1);
    r.clear();
    r.render(this.scene, cam);
    cam.layers.set(0);

    // --- reflection: mirror the camera through the water plane
    const vc = this.virtualCam;
    const planeY = POND.level;
    _camPos.setFromMatrixPosition(cam.matrixWorld);
    _rot.extractRotation(cam.matrixWorld);
    _look.set(0, 0, -1).applyMatrix4(_rot).add(_camPos);
    vc.position.set(_camPos.x, 2 * planeY - _camPos.y, _camPos.z);
    _target.set(_look.x, 2 * planeY - _look.y, _look.z);
    vc.up.set(0, 1, 0).applyMatrix4(_rot);
    vc.up.y *= -1;
    vc.lookAt(_target);
    vc.near = cam.near;
    vc.far = cam.far;
    vc.updateMatrixWorld();
    vc.projectionMatrix.copy(cam.projectionMatrix);
    vc.projectionMatrixInverse.copy(cam.projectionMatrixInverse);

    this.texMat.set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1);
    this.texMat.multiply(vc.projectionMatrix);
    this.texMat.multiply(vc.matrixWorldInverse);

    // oblique near plane so nothing below the surface leaks into the mirror image
    _plane.setFromNormalAndCoplanarPoint(_up, _p.set(0, planeY + 0.02, 0));
    _plane.applyMatrix4(vc.matrixWorldInverse);
    _clip.set(_plane.normal.x, _plane.normal.y, _plane.normal.z, _plane.constant);
    const pe = vc.projectionMatrix.elements;
    _q.x = (Math.sign(_clip.x) + pe[8]!) / pe[0]!;
    _q.y = (Math.sign(_clip.y) + pe[9]!) / pe[5]!;
    _q.z = -1;
    _q.w = (1 + pe[10]!) / pe[14]!;
    _clip.multiplyScalar(2 / _clip.dot(_q));
    pe[2] = _clip.x;
    pe[6] = _clip.y;
    pe[10] = _clip.z + 1;
    pe[14] = _clip.w;

    vc.layers.set(LAYER_REFLECT);
    r.setRenderTarget(this.reflRT);
    r.clear();
    r.render(this.scene, vc);

    r.setRenderTarget(prevTarget);
    this.mesh.visible = true;
  }
}

const _c = new Color();
const _camPos = new Vector3();
const _rot = new Matrix4();
const _look = new Vector3();
const _target = new Vector3();
const _up = new Vector3(0, 1, 0);
const _p = new Vector3();
const _plane = new Plane();
const _clip = new Vector4();
const _q = new Vector4();
