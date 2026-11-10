import {
  Color,
  DoubleSide,
  FrontSide,
  Mesh,
  MeshDepthMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Vector2,
  type ColorRepresentation,
  type Material,
  type Object3D,
  type Texture,
} from 'three';
import type { Assets, TexName, TexSet } from './assets';
import { applyNoFaceFlip, applyTranslucency, applyWindVertex, patch, windKey, type WindOpts } from './shared';

export type WindProfile = 'none' | 'crop' | 'tree' | 'bush' | 'flower';

const WIND: Record<WindProfile, WindOpts | null> = {
  none: null,
  crop: { amp: 0.11, height: 0.9, spread: 0.3 },
  tree: { amp: 0.15, height: 3.4, base: 0.9, spread: 1.0, flutter: 0.018 },
  bush: { amp: 0.05, height: 1.0, base: 0.1, spread: 1.0, flutter: 0.01 },
  flower: { amp: 0.1, height: 0.42, spread: 0.3 },
};

interface StdOpts {
  set?: TexName;
  /** Metres covered by one texture tile (model UVs are in metres). */
  tile?: number;
  color?: ColorRepresentation;
  rough?: number;
  metal?: number;
  normalScale?: number;
  useAlbedo?: boolean;
  useRough?: boolean;
  envIntensity?: number;
}

function retile(tex: Texture, tile: number): Texture {
  const t = tex.clone();
  t.repeat.set(1 / tile, 1 / tile);
  t.needsUpdate = true;
  return t;
}

export class MaterialLib {
  private readonly cache = new Map<string, Material>();
  private readonly depthCache = new Map<string, MeshDepthMaterial>();
  /** Materials that light up at dusk (window panes, lanterns). */
  readonly glass: MeshStandardMaterial[] = [];

  constructor(private readonly assets: Assets) {}

  private std(o: StdOpts): MeshStandardMaterial {
    const m = new MeshStandardMaterial({
      color: o.color ?? 0xffffff,
      roughness: o.rough ?? 1,
      metalness: o.metal ?? 0,
      vertexColors: true,
    });
    if (o.set) {
      const s: TexSet = this.assets.set(o.set);
      const tile = o.tile ?? 1;
      if (o.useAlbedo !== false) m.map = retile(s.albedo, tile);
      m.normalMap = retile(s.normal, tile);
      m.normalScale = new Vector2(o.normalScale ?? 1, o.normalScale ?? 1);
      if (s.rough && o.useRough !== false) {
        m.roughnessMap = retile(s.rough, tile);
        m.roughness = o.rough ?? 1;
      } else if (o.rough === undefined) {
        m.roughness = 0.8;
      }
    }
    if (o.envIntensity !== undefined) m.envMapIntensity = o.envIntensity;
    return m;
  }

  private create(name: string, wind: WindProfile): Material {
    const w = WIND[wind];
    switch (name) {
      case 'wood_plank':
        return this.std({ set: 'wood', color: new Color(1.0, 0.9, 0.78) });
      case 'wood_dark':
        return this.std({ set: 'wood', color: new Color(0.42, 0.33, 0.27), normalScale: 1.2 });
      case 'wood_light':
        return this.std({ set: 'wood', color: new Color(1.3, 1.16, 0.95), tile: 0.8 });
      case 'bark':
        return this.std({ set: 'bark', normalScale: 1.4 });
      case 'stone':
        return this.std({ set: 'stone', tile: 0.9, color: new Color(1.0, 0.97, 0.93) });
      case 'roof':
        return this.std({ set: 'roof', color: new Color(0.86, 0.36, 0.26), normalScale: 1.2 });
      case 'plaster':
        return this.std({ set: 'plaster', tile: 2, color: new Color(1.0, 0.97, 0.9) });
      case 'paint': {
        const m = this.std({ set: 'wood', useAlbedo: false, useRough: false, rough: 0.55, normalScale: 0.45 });
        return m;
      }
      case 'glass': {
        const m = new MeshStandardMaterial({
          color: 0x263842,
          roughness: 0.08,
          metalness: 0,
          emissive: new Color(1.0, 0.62, 0.26),
          emissiveIntensity: 0,
          envMapIntensity: 1.4,
        });
        this.glass.push(m);
        return m;
      }
      case 'metal':
        return this.std({ set: 'metal', tile: 0.22, metal: 0.92, rough: 1, normalScale: 0.45, envIntensity: 1.1 });
      case 'metal_dark':
        return this.std({ set: 'metal', tile: 0.18, useAlbedo: false, useRough: false, color: 0x5a554f, metal: 0.35, rough: 0.5, normalScale: 0.5, envIntensity: 0.55 });
      case 'rope':
        return this.std({ set: 'straw', tile: 0.12, color: new Color(0.85, 0.74, 0.6) });
      case 'straw':
        return this.std({ set: 'straw', tile: 0.25 });
      case 'cloth':
        return this.std({ set: 'fabric', tile: 0.22, normalScale: 0.9 });
      case 'skin':
        return new MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.58, vertexColors: true, sheen: 0.35, sheenRoughness: 0.6, sheenColor: new Color(1.0, 0.55, 0.4) });
      case 'hair':
        return this.std({ set: 'plant', tile: 0.18, useAlbedo: false, useRough: false, rough: 0.5, normalScale: 0.9 });
      case 'eye':
        return new MeshStandardMaterial({ color: 0x0b0b0e, roughness: 0.06, envMapIntensity: 1.5 });
      case 'leather':
        return this.std({ set: 'fabric', tile: 0.3, useAlbedo: false, useRough: false, color: 0x7a4a2c, rough: 0.52, normalScale: 0.35 });
      case 'water_still':
        return new MeshStandardMaterial({ color: 0x1b3a42, roughness: 0.05, metalness: 0, envMapIntensity: 1.7 });
      case 'soil':
        return this.std({ set: 'soil', tile: 1.2 });
      case 'leaf': {
        const m = new MeshStandardMaterial({
          // the card texture is already green; lift it so the vertex colour sets the hue
          color: this.assets.leafAlbedo ? new Color(3.6, 2.5, 5.2) : new Color(1, 1, 1),
          roughness: 0.86,
          envMapIntensity: 0.55,
          vertexColors: true,
          side: DoubleSide,
          map: this.assets.leafAlbedo,
          normalMap: this.assets.leafNormal,
          normalScale: new Vector2(0.6, 0.6),
          alphaTest: this.assets.leafAlbedo ? 0.42 : 0,
          alphaToCoverage: !!this.assets.leafAlbedo,
        });
        patch(m, `leaf_${windKey(w)}`, (s) => {
          if (w) applyWindVertex(s, w);
          applyNoFaceFlip(s);
          applyTranslucency(s, 1.0);
        });
        return m;
      }
      case 'plant': {
        const m = this.std({ set: 'plant', tile: 0.5, rough: 0.95, normalScale: 0.7 });
        m.side = DoubleSide;
        patch(m, `plant_${windKey(w)}`, (s) => {
          if (w) applyWindVertex(s, w);
          applyTranslucency(s, 0.75);
        });
        return m;
      }
      case 'plant_glossy': {
        const m = new MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.34, vertexColors: true, side: FrontSide, clearcoat: 0.25, clearcoatRoughness: 0.3 });
        if (w) patch(m, `plantg_${windKey(w)}`, (s) => applyWindVertex(s, w));
        return m;
      }
      case 'brick':
        return this.std({ set: 'roof', tile: 0.4, color: new Color(1.0, 0.56, 0.42), normalScale: 1.2 });
      case 'clay':
        return this.std({ set: 'plaster', tile: 1.2, color: new Color(0.95, 0.66, 0.5), normalScale: 1.3 });
      case 'slate':
        return this.std({ set: 'roof', color: new Color(0.42, 0.5, 0.62), normalScale: 1.2 });
      case 'gold':
        return this.std({ set: 'metal', useAlbedo: false, useRough: false, color: new Color(1.0, 0.72, 0.3), metal: 1, rough: 0.32, normalScale: 0.3, envIntensity: 1.3 });
      case 'parchment':
        return this.std({ set: 'fabric', tile: 0.4, useAlbedo: false, useRough: false, color: new Color(0.98, 0.93, 0.8), rough: 0.88, normalScale: 0.25 });
      case 'bread':
        return this.std({ set: 'plaster', tile: 0.25, useAlbedo: false, useRough: false, rough: 0.62, normalScale: 0.9 });
      case 'egg':
        return new MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.45, vertexColors: true, sheen: 0.2, sheenColor: new Color(1, 0.95, 0.85) });
      case 'glass_jar':
        return new MeshPhysicalMaterial({ color: 0xe8f2ee, roughness: 0.06, metalness: 0, transparent: true, opacity: 0.38, envMapIntensity: 1.6, vertexColors: true, depthWrite: false });
      case 'ember': {
        const m = new MeshStandardMaterial({ color: 0x1a0904, roughness: 0.9, emissive: new Color(1.0, 0.42, 0.12), emissiveIntensity: 0.3, vertexColors: true });
        // the vertex colour carries the glow gradient (bright at the bottom of the oven)
        patch(m, 'ember', (s) => {
          s.fragmentShader = s.fragmentShader.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\n  totalEmissiveRadiance *= vColor.rgb;');
        });
        return m;
      }
      default:
        console.warn(`[materials] unknown material "${name}"`);
        return new MeshStandardMaterial({ color: 0xff00ff, roughness: 0.8, vertexColors: true });
    }
  }

  get(name: string, wind: WindProfile = 'none'): Material {
    const windy = name === 'leaf' || name === 'plant' || name === 'plant_glossy';
    const key = `${name}|${windy ? wind : 'none'}`;
    let m = this.cache.get(key);
    if (!m) {
      m = this.create(name, windy ? wind : 'none');
      m.name = name;
      this.cache.set(key, m);
    }
    return m;
  }

  /** Shadow-pass material that sways and cuts out exactly like the visible one. */
  depthFor(name: string, wind: WindProfile): MeshDepthMaterial | null {
    const w = WIND[wind];
    const windy = name === 'leaf' || name === 'plant' || name === 'plant_glossy';
    if (!w || !windy) return null;
    const key = `${name}|${wind}`;
    let d = this.depthCache.get(key);
    if (!d) {
      d = new MeshDepthMaterial();
      if (name === 'leaf' && this.assets.leafAlbedo) {
        d.map = this.assets.leafAlbedo;
        d.alphaTest = 0.42;
      }
      patch(d, `depth_${name}_${windKey(w)}`, (s) => applyWindVertex(s, w));
      this.depthCache.set(key, d);
    }
    return d;
  }

  /** Swap every mesh's glTF placeholder for the real PBR material of the same name. */
  apply(root: Object3D, wind: WindProfile = 'none', opts: { cast?: boolean; receive?: boolean } = {}): void {
    root.traverse((o) => {
      const mesh = o as Mesh;
      if (!mesh.isMesh) return;
      const src = mesh.material as Material;
      const name = src.name.replace(/\.\d+$/, '');
      mesh.material = this.get(name, wind);
      mesh.castShadow = opts.cast ?? true;
      mesh.receiveShadow = opts.receive ?? true;
      const depth = this.depthFor(name, wind);
      if (depth) mesh.customDepthMaterial = depth;
      if (name === 'glass' || name === 'water_still') mesh.castShadow = false;
    });
  }

  setWindowGlow(v: number): void {
    for (const g of this.glass) g.emissiveIntensity = v;
  }
}
