import {
  ACESFilmicToneMapping,
  AmbientLight,
  Box3,
  Color,
  DirectionalLight,
  PMREMGenerator,
  PerspectiveCamera,
  Scene,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import type { Assets } from '../core/assets';
import type { MaterialLib } from '../core/materials';

/**
 * Renders the 3D goods/tools once into little transparent PNGs, so every icon in the UI is the
 * real model with the real materials.
 */
export function renderIcons(assets: Assets, lib: MaterialLib, models: Record<string, string>, size = 192): Record<string, string> {
  const out: Record<string, string> = {};
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  let r: WebGLRenderer;
  try {
    r = new WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: true });
  } catch {
    return out;
  }
  r.setPixelRatio(1);
  r.setSize(size, size, false);
  r.outputColorSpace = SRGBColorSpace;
  r.toneMapping = ACESFilmicToneMapping;
  r.toneMappingExposure = 1.05;
  r.setClearColor(0x000000, 0);
  const scene = new Scene();
  const pm = new PMREMGenerator(r);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const key = new DirectionalLight(new Color(1.0, 0.92, 0.8), 2.6);
  key.position.set(2, 3.2, 2.6);
  const rim = new DirectionalLight(new Color(0.75, 0.85, 1.0), 1.6);
  rim.position.set(-2.5, 1.5, -2.5);
  scene.add(key, rim, new AmbientLight(0xffffff, 0.15));
  const cam = new PerspectiveCamera(26, 1, 0.01, 50);
  const box = new Box3();
  const c = new Vector3();
  const s = new Vector3();

  for (const [id, model] of Object.entries(models)) {
    const obj = assets.clone(model);
    if (!obj) continue;
    lib.apply(obj, 'none', { cast: false, receive: false });
    scene.add(obj);
    obj.updateMatrixWorld(true);
    box.setFromObject(obj);
    box.getCenter(c);
    box.getSize(s);
    const rad = Math.max(s.x, s.y, s.z) * 0.62 + 1e-3;
    const dist = rad / Math.tan((cam.fov * Math.PI) / 360);
    const dir = new Vector3(0.62, 0.52, 0.86).normalize();
    cam.position.copy(c).addScaledVector(dir, dist);
    cam.near = dist * 0.1;
    cam.far = dist * 4;
    cam.updateProjectionMatrix();
    cam.lookAt(c);
    r.render(scene, cam);
    out[id] = canvas.toDataURL('image/png');
    scene.remove(obj);
  }
  pm.dispose();
  r.dispose();
  r.forceContextLoss();
  return out;
}
