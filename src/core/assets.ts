import {
  Color,
  DataTexture,
  LinearFilter,
  LinearMipmapLinearFilter,
  NoColorSpace,
  Object3D,
  RGBAFormat,
  RepeatWrapping,
  SRGBColorSpace,
  TextureLoader,
  UnsignedByteType,
  type Texture,
} from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export interface TexSet {
  albedo: Texture;
  normal: Texture;
  rough: Texture | null;
  /** Average albedo in linear space. */
  avg: Color;
  missing: boolean;
}

const TEX_NAMES = ['grass', 'dirt', 'soil', 'path', 'wood', 'bark', 'stone', 'roof', 'plaster', 'metal', 'fabric', 'straw', 'plant'] as const;
export type TexName = (typeof TEX_NAMES)[number];

/** sRGB fallbacks used while a texture file is absent. */
const FALLBACK: Record<TexName, number> = {
  grass: 0x55803a,
  dirt: 0x866242,
  soil: 0x543a28,
  path: 0xb09268,
  wood: 0x966a42,
  bark: 0x604e3e,
  stone: 0x96928a,
  roof: 0xaaa096,
  plaster: 0xe2d6c0,
  metal: 0xbec0c3,
  fabric: 0xf0f0f0,
  straw: 0xd6b268,
  plant: 0xf0f0f0,
};

function solid(hex: number, srgb: boolean): DataTexture {
  const d = new Uint8Array([(hex >> 16) & 255, (hex >> 8) & 255, hex & 255, 255]);
  const t = new DataTexture(d, 1, 1, RGBAFormat, UnsignedByteType);
  t.colorSpace = srgb ? SRGBColorSpace : NoColorSpace;
  t.wrapS = t.wrapT = RepeatWrapping;
  t.needsUpdate = true;
  return t;
}

function averageColor(tex: Texture): Color {
  const img = tex.image as CanvasImageSource | undefined;
  const out = new Color(0.3, 0.4, 0.2);
  if (!img) return out;
  try {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 8;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    if (!ctx) return out;
    ctx.drawImage(img, 0, 0, 8, 8);
    const px = ctx.getImageData(0, 0, 8, 8).data;
    let r = 0;
    let g = 0;
    let b = 0;
    for (let i = 0; i < px.length; i += 4) {
      r += px[i]!;
      g += px[i + 1]!;
      b += px[i + 2]!;
    }
    const n = px.length / 4;
    out.setRGB(r / n / 255, g / n / 255, b / n / 255, SRGBColorSpace);
  } catch {
    /* keep default */
  }
  return out;
}

export class Assets {
  readonly tex = new Map<string, TexSet>();
  leafAlbedo: Texture | null = null;
  leafNormal: Texture | null = null;
  waterNormal: Texture | null = null;
  /** Every named node from every glb. */
  private readonly nodes = new Map<string, Object3D>();
  readonly missing: string[] = [];
  private readonly loader = new TextureLoader();

  constructor(private readonly maxAniso: number) {}

  private async loadTex(url: string, srgb: boolean, repeat = true): Promise<Texture | null> {
    try {
      const t = await this.loader.loadAsync(url);
      t.colorSpace = srgb ? SRGBColorSpace : NoColorSpace;
      if (repeat) t.wrapS = t.wrapT = RepeatWrapping;
      t.anisotropy = Math.min(8, this.maxAniso);
      t.minFilter = LinearMipmapLinearFilter;
      t.magFilter = LinearFilter;
      return t;
    } catch {
      this.missing.push(url);
      return null;
    }
  }

  private async loadSet(name: TexName): Promise<void> {
    const [a, n, r] = await Promise.all([
      this.loadTex(`textures/${name}_albedo.png`, true),
      this.loadTex(`textures/${name}_normal.png`, false),
      this.loadTex(`textures/${name}_rough.png`, false),
    ]);
    const albedo = a ?? solid(FALLBACK[name], true);
    this.tex.set(name, {
      albedo,
      normal: n ?? solid(0x8080ff, false),
      rough: r,
      avg: a ? averageColor(a) : new Color(FALLBACK[name]),
      missing: !a,
    });
  }

  private async loadGlb(url: string): Promise<void> {
    try {
      const gltf = await new GLTFLoader().loadAsync(url);
      gltf.scene.updateMatrixWorld(true);
      gltf.scene.traverse((o) => {
        if (o.name && !this.nodes.has(o.name)) this.nodes.set(o.name, o);
      });
    } catch (e) {
      this.missing.push(url);
      console.warn(`[assets] ${url} not available`, e);
    }
  }

  async load(onProgress: (done: number, total: number) => void): Promise<void> {
    const jobs: Promise<void>[] = [];
    for (const n of TEX_NAMES) jobs.push(this.loadSet(n));
    jobs.push(
      this.loadTex('textures/leafcard_albedo.png', true, false).then((t) => {
        this.leafAlbedo = t;
      }),
      this.loadTex('textures/leafcard_normal.png', false, false).then((t) => {
        this.leafNormal = t;
      }),
      this.loadTex('textures/water_normal.png', false).then((t) => {
        this.waterNormal = t;
      }),
      this.loadGlb('models/structures.glb'),
      this.loadGlb('models/vegetation.glb'),
      this.loadGlb('models/character.glb'),
      this.loadGlb('models/buildings.glb'),
      this.loadGlb('models/royal.glb'),
      this.loadGlb('models/items.glb'),
      this.loadGlb('models/courier.glb'),
    );
    let done = 0;
    for (const j of jobs) {
      void j.then(() => onProgress(++done, jobs.length));
    }
    await Promise.all(jobs);
  }

  set(name: TexName): TexSet {
    const s = this.tex.get(name);
    if (!s) throw new Error(`texture set ${name} not loaded`);
    return s;
  }

  has(name: string): boolean {
    return this.nodes.has(name);
  }

  /** The original node (do not add to the scene; clone it). */
  node(name: string): Object3D | null {
    return this.nodes.get(name) ?? null;
  }

  /** A detached deep clone of a named asset, reset to the origin. */
  clone(name: string): Object3D | null {
    const src = this.nodes.get(name);
    if (!src) return null;
    const c = src.clone(true);
    c.position.set(0, 0, 0);
    c.rotation.set(0, 0, 0);
    c.scale.set(1, 1, 1);
    return c;
  }
}

/** Find a descendant whose name starts with `prefix` (glTF de-duplicates names with suffixes). */
export function findByPrefix(root: Object3D, prefix: string): Object3D | null {
  let hit: Object3D | null = null;
  root.traverse((o) => {
    if (!hit && o !== root && o.name.startsWith(prefix)) hit = o;
  });
  return hit;
}
export function findAllByPrefix(root: Object3D, prefix: string): Object3D[] {
  const out: Object3D[] = [];
  root.traverse((o) => {
    if (o !== root && o.name.startsWith(prefix)) out.push(o);
  });
  return out;
}
