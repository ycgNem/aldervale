import { BufferAttribute, Color, InstancedBufferAttribute, InstancedBufferGeometry, Mesh, NormalBlending, ShaderMaterial, Vector3, type Camera, type Scene } from 'three';

const COUNT = 3200;
const BOX = 26;
const HEIGHT = 15;

const VERT = /* glsl */ `
attribute vec3 aOff;
uniform float uTime;
uniform vec3 uCam;
uniform vec3 uWind;
varying float vFade;
varying float vV;
void main() {
  // drops are anchored to the world grid so they don't swim when you turn
  vec2 cell = (aOff.xz * ${BOX.toFixed(1)}) - uCam.xz;
  vec2 xz = uCam.xz + (fract(cell / ${BOX.toFixed(1)}) - 0.5) * ${BOX.toFixed(1)};
  float fall = mod(aOff.y * ${HEIGHT.toFixed(1)} - uTime * (10.5 + aOff.x * 3.0), ${HEIGHT.toFixed(1)});
  vec3 base = vec3(xz.x, uCam.y - 5.0 + fall, xz.y);
  base.xz += uWind.xz * (fall - ${HEIGHT.toFixed(1)}) * 0.12;
  // a thin vertical streak facing the camera
  vec3 toCam = normalize(vec3(uCam.x - base.x, 0.0, uCam.z - base.z));
  vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), toCam));
  vec3 p = base + right * position.x * 0.012 + vec3(uWind.x * 0.05, 1.0, uWind.z * 0.05) * position.y * 0.5;
  float d = length(base.xz - uCam.xz);
  vFade = (1.0 - smoothstep(${(BOX * 0.32).toFixed(1)}, ${(BOX * 0.5).toFixed(1)}, d)) * smoothstep(0.4, 1.6, d);
  vV = position.y;
  gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
}
`;

const FRAG = /* glsl */ `
uniform float uAlpha;
uniform vec3 uColor;
varying float vFade;
varying float vV;
void main() {
  float a = uAlpha * vFade * smoothstep(0.0, 0.3, vV) * (1.0 - smoothstep(0.7, 1.0, vV));
  if (a < 0.003) discard;
  gl_FragColor = vec4(uColor, a);
}
`;

/** Rain streaks that follow the camera. */
export class Rain {
  readonly mesh: Mesh;
  private readonly mat: ShaderMaterial;
  private time = 0;

  constructor(scene: Scene) {
    const geo = new InstancedBufferGeometry();
    // a quad: x in -0.5..0.5, y in 0..1
    const pos = new Float32Array([-0.5, 0, 0, 0.5, 0, 0, 0.5, 1, 0, -0.5, 1, 0]);
    geo.setAttribute('position', new BufferAttribute(pos, 3));
    geo.setIndex([0, 1, 2, 0, 2, 3]);
    const off = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT * 3; i++) off[i] = Math.random();
    geo.setAttribute('aOff', new InstancedBufferAttribute(off, 3));
    geo.instanceCount = COUNT;
    this.mat = new ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: {
        uTime: { value: 0 },
        uCam: { value: new Vector3() },
        uWind: { value: new Vector3(0.6, 0, 0.3) },
        uAlpha: { value: 0 },
        uColor: { value: new Color(0.78, 0.82, 0.88) },
      },
      transparent: true,
      depthWrite: false,
      blending: NormalBlending,
    });
    this.mesh = new Mesh(geo, this.mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 5;
    this.mesh.visible = false;
    scene.add(this.mesh);
  }

  update(dt: number, camera: Camera, intensity: number, light: number, wind: { x: number; y: number }): void {
    this.time += dt;
    const u = this.mat.uniforms;
    u.uTime!.value = this.time;
    (u.uCam!.value as Vector3).copy(camera.position);
    (u.uWind!.value as Vector3).set(wind.x, 0, wind.y);
    u.uAlpha!.value = 0.22 * intensity;
    (u.uColor!.value as Color).setRGB(0.55 + 0.35 * light, 0.6 + 0.35 * light, 0.68 + 0.32 * light);
    this.mesh.visible = intensity > 0.02;
  }
}
