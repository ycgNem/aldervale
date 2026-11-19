import { Vector3, type PerspectiveCamera } from 'three';
import type { AudioEngine, Sfx } from '../audio/audio';
import type { Particles } from '../fx/particles';
import type { Environment } from '../render/sky';
import type { MarkerView, PromptInfo, QuestView, TagView, UI } from '../ui/ui';
import { AWAY_TIME, BLOCK_NAMES, BLOCK_PLOTS, LEAVE_TIME, blockOf, type Estate, type Obstacle } from '../world/estate';
import { CROP_TYPES, type CropType, type Field, type Plot } from '../world/field';
import { FIELD, PLOT, POND, WELL, groundMask, plotAt, pondSdf, terrainHeight, type GroundMask } from '../world/layout';
import type { AppleTree } from '../world/props';
import { clamp, smoothstep } from '../util/math';
import {
  BUILDINGS,
  BUILDING_IDS,
  COMPOST_BATCH,
  COMPOST_CAP,
  COMPOST_TIME,
  CONSTRUCT_TIME,
  HEN_CAP,
  HEN_FEED,
  HEN_TIME,
  ITEMS,
  MILL_BATCH,
  MILL_CAP,
  MILL_TIME,
  OVEN_RECIPES,
  SEED_CHAPTER,
  SEED_PRICE,
  TOOL_NAMES,
  TOOL_ORDER,
  UPGRADES,
  YIELD,
  build,
  canBuild,
  canCapacity,
  give,
  has,
  newState,
  seedOf,
  take,
  tally,
  tickTimed,
  type BuildingId,
  type Commission,
  type GameState,
  type ItemId,
  type ToolId,
  type UpgradeId,
} from './state';
import { CHAPTERS, LETTERS, chapterOf, objectiveDone, objectiveValue, standingOrder, type MarkerId, type Objective } from './story';
import type { FirstPerson } from './fp';
import type { ViewModel } from './viewmodel';

const SAVE_KEY = 'aldervale.save.v2';
const REACH = 4.3;

type TargetKind = 'plot' | 'obstacle' | 'tree' | 'board' | 'pip' | 'crate' | 'wren' | 'site' | 'hopper' | 'henrun' | 'oven' | 'compost' | 'bed' | 'well' | 'pond' | 'sign';
interface Target {
  kind: TargetKind;
  dist: number;
  point: Vector3;
  plot?: Plot;
  obstacle?: Obstacle;
  tree?: AppleTree;
  building?: BuildingId;
  block?: number;
}

interface Verdict {
  ok: boolean;
  verb: string;
  label?: string;
  detail?: string;
}

interface SaveData {
  v: 2;
  s: GameState;
  plots: { t: boolean; w: number; c: CropType | null; s: number; g: number; f: boolean }[];
  hour: number;
  day: number;
  pos: [number, number, number];
}

const PIP_LINES: Record<number, string[]> = {
  1: ['Welcome to Brookhollow, steward! The crate behind the wagon is for the castle — fill it and I’ll ride it up.', 'The ripe wheat by the gate wants harvesting. Basket’s on your belt.'],
  2: ['Old Tom’s axe and pick, as promised. Mind your fingers.', 'Wren’s set up at the crossroads — tell her Pip sent you.'],
  3: ['The bakers are pacing the kitchens. Flour, steward, flour!', 'A windmill on that rise would turn all day in this wind.'],
  4: ['Her Highness has asked about the pie three times today.', 'Hens are good company. Better than the pony, some days.'],
  5: ['The whole castle is buzzing about the feast.', 'Three crates, steward. I’ve oiled the wheels.'],
  6: ['The castle sends its thanks — and its appetite.', 'Another fine day for it, Royal Steward.'],
};
const WREN_LINES = ['Seeds from every corner of the valley, love. Have a look.', 'Fair prices, fair weather. Mostly.', 'I’ll take any surplus off your hands — the castle isn’t the only hungry place.'];

const _v = new Vector3();
const _d = new Vector3();
const _o = new Vector3();
const _w = new Vector3();

export interface Settings {
  master: number;
  music: number;
  sfx: number;
  sensitivity: number;
  invertY: boolean;
  fov: number;
  markers: boolean;
}

export class Game {
  s: GameState;
  tool: ToolId = 'hoe';
  seed: CropType = 'wheat';
  /** True while gameplay input is live (pointer locked or forced by tests). */
  active = false;
  settings: Settings = { master: 0.8, music: 0.5, sfx: 0.9, sensitivity: 1, invertY: false, fov: 72, markers: true };
  onEnding: (() => void) | null = null;
  private target: Target | null = null;
  private holding = false;
  private holdCool = 0;
  private lastActed: unknown = null;
  private saveT = 0;
  private pouring = 0;
  private readonly pourTarget = new Vector3();
  private greeted = false;
  private greetedWren = false;
  private time = 0;
  private doneObjectives = new Set<string>();
  private lastDay = 1;
  private readonly gm: GroundMask = { dirt: 0, path: 0, shore: 0 };
  private sleeping = false;
  private endingT = -1;

  constructor(
    private readonly field: Field,
    private readonly fp: FirstPerson,
    private readonly vm: ViewModel,
    private readonly estate: Estate,
    private readonly particles: Particles,
    private readonly ui: UI,
    private readonly camera: PerspectiveCamera,
    private readonly env: Environment,
    private readonly audio: AudioEngine,
    private readonly avail: (c: CropType) => boolean,
    fresh: boolean,
  ) {
    const saved = fresh ? null : Game.readSave();
    if (saved) {
      this.s = saved.s;
      saved.plots.forEach((q, i) => {
        const p = field.plots[i];
        if (!p) return;
        p.tilled = q.t;
        p.till = q.t ? 1 : 0;
        p.wet = q.w;
        p.crop = q.c;
        p.stage = q.s;
        p.growth = q.g;
        p.fert = !!q.f;
        p.pop = 9;
      });
      env.setHour(saved.hour);
      env.day = saved.day;
      fp.teleport(saved.pos[0], saved.pos[2], saved.pos[1]);
    } else {
      this.s = newState();
      this.starterField();
      for (const c of CHAPTERS[0]!.commissions(this.s, (i) => this.availItem(i))) this.s.commissions.push(c);
    }
    this.lastDay = env.day;
    this.s.stats.days = env.day;
    // objectives already complete when loading shouldn't fire banners again
    const ch = chapterOf(this.s.chapter);
    if (ch) for (const o of ch.objectives) if (objectiveDone(this.s, o) || this.special(o)) this.doneObjectives.add(o.id);
    estate.sync(this.s);
    this.vm.setCopperCan(!!this.s.upgrades.can);
    ui.setTool(this.tool);
    ui.setSeed(this.seed, this.unlockedCrops());
    ui.onTool = (t) => this.selectTool(t);
    ui.onSeed = (c) => this.selectSeed(c);
    estate.onBurst = () => {
      // the boom arrives a moment after the flash
      setTimeout(() => this.audio.play('boom', undefined, 0.8), 750);
    };
    this.loadSettings();
  }

  // ------------------------------------------------------------------ persistence
  static hasSave(): boolean {
    try {
      return !!localStorage.getItem(SAVE_KEY);
    } catch {
      return false;
    }
  }
  private static readSave(): SaveData | null {
    try {
      const raw = localStorage.getItem(SAVE_KEY);
      if (!raw) return null;
      const d = JSON.parse(raw) as SaveData;
      if (d.v !== 2 || !d.s || d.s.v !== 2) return null;
      // forward-compatible: fill anything a newer version added
      const fresh = newState();
      for (const k of Object.keys(fresh.inv) as ItemId[]) if (d.s.inv[k] === undefined) d.s.inv[k] = 0;
      return d;
    } catch {
      return null;
    }
  }
  save(): void {
    if (this.sleeping) return;
    const d: SaveData = {
      v: 2,
      s: this.s,
      plots: this.field.plots.map((p) => ({ t: p.tilled, w: +p.wet.toFixed(3), c: p.crop, s: p.stage, g: +p.growth.toFixed(3), f: p.fert })),
      hour: this.env.hour,
      day: this.env.day,
      pos: [this.fp.pos.x, this.fp.yaw, this.fp.pos.z],
    };
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify(d));
    } catch {
      /* private mode: progress just isn't kept */
    }
  }
  static clearSave(): void {
    try {
      localStorage.removeItem(SAVE_KEY);
    } catch {
      /* ignore */
    }
  }
  private loadSettings(): void {
    try {
      const raw = localStorage.getItem('aldervale.settings');
      if (raw) Object.assign(this.settings, JSON.parse(raw) as Partial<Settings>);
    } catch {
      /* defaults */
    }
  }
  saveSettings(): void {
    try {
      localStorage.setItem('aldervale.settings', JSON.stringify(this.settings));
    } catch {
      /* ignore */
    }
  }

  /** A few beds already on the go so the first steps are quick. */
  private starterField(): void {
    const plan: [number, number, CropType, number, boolean][] = [
      [0, 0, 'wheat', 3, true],
      [1, 0, 'wheat', 3, true],
      [2, 0, 'wheat', 2, true],
      [3, 0, 'tomato', 3, true],
      [4, 0, 'tomato', 2, true],
      [0, 1, 'wheat', 1, true],
      [1, 1, 'wheat', 1, false],
      [2, 1, 'tomato', 1, false],
    ];
    for (const [c, r, crop, stage, wet] of plan) {
      const p = this.field.plot(c, r);
      this.field.till(p);
      p.till = 1;
      this.field.plant(p, crop);
      p.stage = stage;
      p.pop = 9;
      if (wet) p.wet = 0.8;
    }
    for (let c = 0; c < 3; c++) {
      const p = this.field.plot(c, 2);
      this.field.till(p);
      p.till = 1;
    }
    this.s.inv.wheat = 2;
  }

  private availItem(i: ItemId): boolean {
    return (CROP_TYPES as string[]).includes(i) ? this.avail(i as CropType) : true;
  }

  unlockedCrops(): CropType[] {
    return CROP_TYPES.filter((c) => this.avail(c) && (SEED_CHAPTER[c] <= this.s.chapter || this.s.inv[seedOf(c)] > 0));
  }

  private sfx(name: Sfx, at?: Vector3, vol = 1): void {
    this.audio.play(name, at, vol);
  }

  // ------------------------------------------------------------------ tools
  selectTool(t: ToolId): void {
    if (!this.s.tools.includes(t)) return;
    if (t !== this.tool) this.sfx('click', undefined, 0.5);
    this.tool = t;
    this.vm.setTool(t);
    this.ui.setTool(t);
    if (t === 'seeds') this.ui.setSeed(this.seed, this.unlockedCrops());
  }
  selectSeed(c: CropType): void {
    if (!this.unlockedCrops().includes(c)) return;
    this.seed = c;
    if (this.tool !== 'seeds') this.selectTool('seeds');
    this.ui.setSeed(c, this.unlockedCrops());
  }
  cycleSeed(): void {
    const list = this.unlockedCrops();
    if (!list.length) return;
    const i = list.indexOf(this.seed);
    this.selectSeed(list[(i + 1) % list.length]!);
  }
  cycleTool(dir: number): void {
    const owned = TOOL_ORDER.filter((t) => this.s.tools.includes(t));
    const i = owned.indexOf(this.tool);
    this.selectTool(owned[(i + dir + owned.length) % owned.length]!);
  }

  // ------------------------------------------------------------------ targeting
  private obstaclesOn(c: number, r: number): Obstacle[] {
    return this.estate.obstacles.filter((o) => o.alive && o.plot && o.plot[0] === c && o.plot[1] === r);
  }

  private findTarget(): Target | null {
    const o = this.camera.getWorldPosition(_o);
    const d = this.camera.getWorldDirection(_d);
    let best: Target | null = null;
    const consider = (t: Target): void => {
      if (!best || t.dist < best.dist) best = t;
    };
    const cyl = (cx: number, cz: number, base: number, r: number, hgt: number, max: number): number | null => {
      const ox = o.x - cx;
      const oz = o.z - cz;
      const a = d.x * d.x + d.z * d.z;
      const b = 2 * (ox * d.x + oz * d.z);
      const c = ox * ox + oz * oz - r * r;
      let t: number;
      if (c <= 0) t = 0;
      else {
        if (a < 1e-6) return null;
        const disc = b * b - 4 * a * c;
        if (disc < 0) return null;
        t = (-b - Math.sqrt(disc)) / (2 * a);
        if (t < 0) return null;
      }
      const y = o.y + d.y * t;
      if (y < base - 0.25 || y > base + hgt) {
        // the ray may still drop onto the top of a low object
        if (d.y < 0) {
          const tt = (base + hgt - o.y) / d.y;
          if (tt > 0 && tt <= max) {
            const x = o.x + d.x * tt - cx;
            const z = o.z + d.z * tt - cz;
            if (x * x + z * z <= r * r) return tt;
          }
        }
        return null;
      }
      return t <= max ? t : null;
    };
    const E = this.estate;
    const add = (kind: TargetKind, p: Vector3, r: number, h: number, extra: Partial<Target> = {}, reach = REACH): void => {
      const t = cyl(p.x, p.z, p.y, r, h, reach);
      if (t !== null) consider({ kind, dist: t, point: p, ...extra });
    };
    add('board', E.boardPos, 1.15, 2.8, {}, REACH + 0.6);
    if (!E.wagonAway) {
      add('pip', E.courierPos, 0.45, 1.95, {}, REACH + 0.6);
      add('crate', E.cratePos, 0.6, 0.9);
    }
    if (E.stallVisible) {
      add('wren', E.wrenPos, 0.5, 1.9, {}, REACH + 1.2);
      add('wren', E.stallPos, 0.9, 2.0, {}, REACH);
    }
    for (const id of BUILDING_IDS) {
      const c = E.siteCentre(id, new Vector3());
      const r = id === 'windmill' ? 2.6 : id === 'bakehouse' ? 2.7 : 2.9;
      add('site', c, r, id === 'windmill' ? 9 : 4.5, { building: id }, REACH + 3.2);
    }
    if (this.s.buildings.windmill.built && this.s.buildings.windmill.progress >= 1) add('hopper', E.hopperPos, 0.75, 1.6, {}, REACH);
    if (this.s.buildings.henhouse.built && this.s.buildings.henhouse.progress >= 1) add('henrun', E.runCentre, 1.9, 1.4, {}, REACH + 0.8);
    if (this.s.buildings.bakehouse.built && this.s.buildings.bakehouse.progress >= 1) {
      const op = _w.copy(E.ovenPos);
      add('oven', new Vector3(op.x, op.y - 0.8, op.z), 0.9, 1.8, {}, REACH);
    }
    add('compost', E.compostPos, 0.95, 1.1);
    add('bed', E.bedPos, 1.0, 0.9);
    add('well', new Vector3(WELL.x, terrainHeight(WELL.x, WELL.z), WELL.z), WELL.r, 2.4);
    for (const t of E.appleTrees) add('tree', new Vector3(t.x, terrainHeight(t.x, t.z), t.z), 0.75, 3.2, { tree: t }, REACH);
    for (const ob of E.obstacles) {
      if (!ob.alive || ob.block >= 0) continue;
      add('obstacle', new Vector3(ob.x, ob.y, ob.z), Math.max(ob.r, 0.5), Math.max(ob.h, 0.5), { obstacle: ob }, REACH);
    }
    // the ground: field plots (or what's growing wild on them), pond water
    if (d.y < -0.05) {
      const tf = (0.12 - o.y) / d.y;
      if (tf > 0 && tf <= REACH) {
        const x = o.x + d.x * tf;
        const z = o.z + d.z * tf;
        const cr = plotAt(x, z);
        if (cr) {
          const p = this.field.plot(cr[0], cr[1]);
          const centre = new Vector3(FIELD.x0 + (p.col + 0.5) * PLOT, 0.1, FIELD.z0 + (p.row + 0.5) * PLOT);
          const obs = this.obstaclesOn(p.col, p.row);
          if (obs.length) {
            // pull weeds before breaking the stone underneath
            const ob = obs.find((q) => q.kind === 'weed') ?? obs[0]!;
            consider({ kind: 'obstacle', obstacle: ob, plot: p, dist: tf, point: new Vector3(ob.x, ob.y, ob.z) });
          } else consider({ kind: 'plot', plot: p, dist: tf, point: centre });
        }
      }
      const tw = (POND.level - o.y) / d.y;
      if (tw > 0 && tw <= REACH + 0.5) {
        const x = o.x + d.x * tw;
        const z = o.z + d.z * tw;
        if (pondSdf(x, z) < -0.2) consider({ kind: 'pond', dist: tw, point: new Vector3(x, POND.level, z) });
      }
    }
    // block signs only win when nothing on the ground is in the way
    for (let bi = 1; bi < 4; bi++) {
      if (this.s.blocks[bi]) continue;
      const sp = E.signPosition(bi, new Vector3());
      sp.x += 0.3;
      sp.z -= 0.4;
      const t = cyl(sp.x, sp.z, sp.y, 0.3, 1.4, REACH);
      const cur = best as Target | null;
      if (t !== null && (!cur || t < cur.dist - 0.8)) best = { kind: 'sign', dist: t, point: sp, block: bi };
    }
    return best;
  }

  // ------------------------------------------------------------------ verdicts
  private plotVerdict(p: Plot, tool: ToolId): Verdict {
    const crop = p.crop;
    switch (tool) {
      case 'hoe':
        if (crop) return { ok: false, verb: `${ITEMS[crop].name} growing here` };
        if (p.tilled) return { ok: false, verb: 'Already tilled', detail: 'Plant seeds here (2)' };
        return { ok: true, verb: 'Till soil' };
      case 'seeds': {
        if (!p.tilled) return { ok: false, verb: 'Till the soil first', detail: 'Hoe (1)' };
        if (crop) return { ok: false, verb: 'Already planted' };
        if (this.s.inv[seedOf(this.seed)] <= 0) {
          const other = this.unlockedCrops().find((c) => this.s.inv[seedOf(c)] > 0);
          return { ok: false, verb: `No ${ITEMS[this.seed].name.toLowerCase()} seeds left`, detail: other ? 'Q switches seed' : this.s.chapter >= 2 ? 'Buy more at Wren’s stall' : 'Pip may know where to get more' };
        }
        return { ok: true, verb: 'Plant', label: ITEMS[this.seed].name, detail: `${this.s.inv[seedOf(this.seed)]} seeds` };
      }
      case 'water':
        if (!p.tilled) return { ok: false, verb: 'Nothing to water' };
        if (this.s.water <= 0) return { ok: false, verb: 'The can is empty', detail: 'Fill it at the well or the pond' };
        if (p.wet > 0.55) return { ok: false, verb: 'Still damp' };
        return { ok: true, verb: 'Water', detail: crop ? 'Crops only grow while the soil is wet' : undefined };
      case 'harvest':
        if (!crop) return { ok: false, verb: 'Nothing to harvest' };
        if (!this.field.isRipe(p)) {
          const left = Math.ceil(this.field.timeToRipe(p));
          return { ok: false, verb: `${ITEMS[crop].name} not ripe yet`, detail: p.wet > 0.04 ? `About ${left}s more` : 'Dry soil — water it to grow' };
        }
        return { ok: true, verb: 'Harvest', label: ITEMS[crop].name, detail: `+${YIELD[crop] + (p.fert ? 1 : 0)} ${ITEMS[crop].plural}` };
      default:
        return { ok: false, verb: `The ${TOOL_NAMES[tool].toLowerCase()} won’t help here` };
    }
  }

  private smartTool(p: Plot): ToolId | null {
    if (!p.tilled) return 'hoe';
    if (!p.crop) return this.s.inv[seedOf(this.seed)] > 0 || this.unlockedCrops().some((c) => this.s.inv[seedOf(c)] > 0) ? 'seeds' : null;
    if (this.field.isRipe(p)) return 'harvest';
    if (p.wet < 0.3 && this.s.water > 0) return 'water';
    return null;
  }

  private obstacleVerdict(ob: Obstacle, tool: ToolId): Verdict {
    const left = Math.max(1, this.hitsNeeded(ob) - (this.s.hits[ob.key] ?? 0));
    const what = ob.kind === 'weed' ? 'weeds' : ob.kind === 'stone' ? 'field stone' : ob.kind === 'boulder' ? 'boulder' : ob.kind === 'log' ? 'fallen log' : ob.kind === 'stump' ? 'old stump' : 'dead branches';
    if (tool !== ob.tool) {
      const need = TOOL_NAMES[ob.tool];
      return { ok: false, verb: `Overgrown: ${what}`, detail: this.s.tools.includes(ob.tool) ? `Use the ${need.toLowerCase()} (${TOOL_ORDER.indexOf(ob.tool) + 1})` : `You’ll need a ${need.toLowerCase()}` };
    }
    const verb = ob.tool === 'hoe' ? 'Pull' : ob.tool === 'pick' ? 'Break' : 'Chop';
    const drop = ob.drops[0]!;
    return { ok: true, verb, label: `the ${what}`, detail: left > 1 ? `${left} more swings · +${drop[1]} ${ITEMS[drop[0]].name.toLowerCase()}` : `+${drop[1]} ${ITEMS[drop[0]].name.toLowerCase()}` };
  }

  private hitsNeeded(ob: Obstacle): number {
    return Math.max(1, ob.hits - (this.s.upgrades.edge && ob.tool !== 'hoe' ? 1 : 0));
  }

  private targetPrompt(t: Target): PromptInfo | null {
    const s = this.s;
    switch (t.kind) {
      case 'plot': {
        const p = t.plot!;
        const v = this.plotVerdict(p, this.tool);
        if (v.ok) return { key: 'LMB', ...v };
        const smart = this.smartTool(p);
        if (smart && smart !== this.tool && s.tools.includes(smart)) {
          const sv = this.plotVerdict(p, smart);
          if (sv.ok) return { key: 'E', ...sv, detail: sv.detail ?? `switches to the ${TOOL_NAMES[smart].toLowerCase()}` };
        }
        if (p.crop && !p.fert && s.inv.compost > 0 && !this.field.isRipe(p)) return { key: 'E', ok: true, verb: 'Spread compost', detail: 'Grows faster, one extra crop' };
        return { key: 'LMB', ...v };
      }
      case 'obstacle': {
        const ob = t.obstacle!;
        const v = this.obstacleVerdict(ob, this.tool);
        if (v.ok) return { key: 'LMB', ...v };
        if (s.tools.includes(ob.tool)) return { key: 'E', ...this.obstacleVerdict(ob, ob.tool), detail: `switches to the ${TOOL_NAMES[ob.tool].toLowerCase()}` };
        return { key: 'LMB', ...v };
      }
      case 'tree': {
        const shaken = s.shaken[t.tree!.key] === this.env.day;
        return shaken ? { key: 'E', ok: false, verb: 'Picked clean', detail: 'More apples tomorrow' } : { key: 'E', ok: true, verb: 'Shake the apple tree' };
      }
      case 'board':
        return { key: 'E', ok: true, verb: 'Open', label: 'the Steward’s Journal', detail: 'Objectives, ledger and letters (J)' };
      case 'pip':
        return { key: 'E', ok: true, verb: 'Talk to', label: 'Pip', detail: s.commissions.some((c) => !c.packed && c.lines.every((l) => s.inv[l.item] >= l.qty)) ? 'You can fill a commission!' : undefined };
      case 'crate': {
        const packed = s.commissions.filter((c) => c.packed).length;
        return { key: 'E', ok: true, verb: 'Open', label: 'the royal crate', detail: packed ? `${packed} packed, ready to send` : `${s.commissions.length} commission${s.commissions.length === 1 ? '' : 's'}` };
      }
      case 'wren':
        return { key: 'E', ok: true, verb: 'Trade with', label: 'Wren', detail: 'Seeds, tools, and she buys surplus' };
      case 'well':
      case 'pond':
        if (s.water >= canCapacity(s)) return { key: 'E', ok: false, verb: 'Watering can is full' };
        return { key: 'E', ok: true, verb: 'Fill', label: 'the watering can', detail: `${s.water}/${canCapacity(s)}` };
      case 'sign': {
        const bi = t.block!;
        const left = this.estate.obstacles.filter((o) => o.alive && o.block === bi).length;
        return { key: 'E', ok: s.chapter >= 2, verb: BLOCK_NAMES[bi]!, detail: `${left} weeds and stones to clear` };
      }
      case 'site': {
        const id = t.building!;
        const st = s.buildings[id];
        const def = BUILDINGS[id];
        if (!st.built) return { key: 'E', ok: s.chapter >= def.chapter, verb: `Raise the ${def.name}`, detail: s.chapter >= def.chapter ? `${def.coins} coins · ${def.wood} wood · ${def.stone} stone` : `The plot is staked for chapter ${def.chapter}` };
        if (st.progress < 1) return { key: 'E', ok: false, verb: `Raising the ${def.name}…`, detail: `${Math.round(st.progress * 100)}%` };
        return null;
      }
      case 'hopper': {
        const m = s.mill;
        if (m.ready) return { key: 'E', ok: true, verb: 'Take', label: `${m.ready} sack${m.ready > 1 ? 's' : ''} of flour` };
        if (m.work.length >= MILL_CAP) return { key: 'E', ok: false, verb: 'The hopper is full', detail: 'Grinding…' };
        if (s.inv.wheat < MILL_BATCH) return { key: 'E', ok: false, verb: 'The hopper is waiting', detail: `Needs ${MILL_BATCH} wheat per sack` };
        return { key: 'E', ok: true, verb: 'Pour in wheat', detail: `${MILL_BATCH} wheat makes a sack · ${m.work.length}/${MILL_CAP} grinding` };
      }
      case 'henrun': {
        const hn = s.hens;
        if (hn.ready) return { key: 'E', ok: true, verb: 'Collect', label: `${hn.ready} basket${hn.ready > 1 ? 's' : ''} of eggs` };
        if (hn.work.length >= HEN_CAP) return { key: 'E', ok: false, verb: 'The hens are well fed', detail: 'Eggs soon' };
        if (s.inv.wheat < HEN_FEED) return { key: 'E', ok: false, verb: 'The hens are hungry', detail: `Scatter ${HEN_FEED} wheat` };
        return { key: 'E', ok: true, verb: 'Scatter grain', detail: `${HEN_FEED} wheat · eggs in ${HEN_TIME}s` };
      }
      case 'oven': {
        const ov = s.oven;
        if (ov.ready) return { key: 'E', ok: true, verb: 'Take the', label: ITEMS[ov.ready].name };
        if (ov.recipe !== null) {
          const r = OVEN_RECIPES[ov.recipe]!;
          return { key: 'E', ok: true, verb: `Baking ${ITEMS[r.out].name}`, detail: `${Math.ceil(r.time - ov.t)}s` };
        }
        return { key: 'E', ok: true, verb: 'Bake at', label: 'the oven' };
      }
      case 'compost': {
        const c = s.compost;
        if (c.ready) return { key: 'E', ok: true, verb: 'Take', label: `${c.ready} compost` };
        if (s.inv.weeds >= COMPOST_BATCH && c.work.length < COMPOST_CAP) return { key: 'E', ok: true, verb: 'Fork in weeds', detail: `${COMPOST_BATCH} weeds make compost` };
        return { key: 'E', ok: false, verb: 'Compost bay', detail: c.work.length ? 'Rotting down nicely…' : `Bring ${COMPOST_BATCH} weeds` };
      }
      case 'bed': {
        const h = this.env.hour;
        const late = h >= 18 || h < 5;
        return { key: 'E', ok: late, verb: late ? 'Sleep until morning' : 'A rest spot for the night', detail: late ? 'Saves the day' : 'Come back after six in the evening' };
      }
    }
  }

  // ------------------------------------------------------------------ actions
  /** Left click: use the held tool on what's ahead (or interact with people and stations). */
  useTool(): void {
    const t = this.target;
    if (!t) return;
    if (t.kind === 'plot') this.actOnPlot(t.plot!, this.tool, false);
    else if (t.kind === 'obstacle') this.actOnObstacle(t.obstacle!, this.tool);
    else if ((t.kind === 'well' || t.kind === 'pond') && this.tool === 'water') this.interact();
    else if (t.kind !== 'tree' && t.kind !== 'site') this.interact();
  }

  private neighbours(p: Plot, wide: boolean): Plot[] {
    if (!wide) return [p];
    const out = [p];
    for (const dc of [-1, 1]) {
      const c = p.col + dc;
      if (c < 0 || c > 9) continue;
      const q = this.field.plot(c, p.row);
      if (!this.obstaclesOn(q.col, q.row).length) out.push(q);
    }
    return out;
  }

  private actOnPlot(p: Plot, tool: ToolId, smart: boolean): boolean {
    const v = this.plotVerdict(p, tool);
    if (!v.ok) {
      if (!smart) this.sfx('error', undefined, 0.4);
      return false;
    }
    if (tool !== this.tool) this.selectTool(tool);
    const x = FIELD.x0 + (p.col + 0.5) * PLOT;
    const z = FIELD.z0 + (p.row + 0.5) * PLOT;
    return this.vm.use(tool, () => {
      const at = new Vector3(x, 0.2, z);
      switch (tool) {
        case 'hoe': {
          for (const q of this.neighbours(p, !!this.s.upgrades.hoe)) {
            if (!this.plotVerdict(q, 'hoe').ok) continue;
            this.field.till(q);
            const qx = FIELD.x0 + (q.col + 0.5) * PLOT;
            const qz = FIELD.z0 + (q.row + 0.5) * PLOT;
            this.particles.dust(qx, this.field.surfaceAt(qx, qz), qz, 1);
            tally(this.s, 'till');
          }
          this.sfx('hoe', at);
          break;
        }
        case 'seeds': {
          if (!this.plotVerdict(p, 'seeds').ok) return;
          const from = this.vm.handPosition(_v);
          this.particles.seeds(from.x, from.y, from.z, x, this.field.surfaceAt(x, z) + 0.02, z);
          this.field.plant(p, this.seed);
          this.s.inv[seedOf(this.seed)]--;
          tally(this.s, 'plant');
          this.sfx('seeds', at);
          if (this.s.inv[seedOf(this.seed)] <= 0) {
            const next = this.unlockedCrops().find((c) => this.s.inv[seedOf(c)] > 0);
            if (next) this.selectSeed(next);
          }
          break;
        }
        case 'water': {
          let used = 0;
          for (const q of this.neighbours(p, !!this.s.upgrades.can)) {
            if (this.s.water <= 0 || !this.plotVerdict(q, 'water').ok) continue;
            this.field.water(q);
            this.s.water--;
            used++;
            tally(this.s, 'water');
          }
          if (!used) return;
          this.pouring = 0.55;
          this.pourTarget.set(x, this.field.surfaceAt(x, z), z);
          this.sfx('pour', at);
          break;
        }
        case 'harvest': {
          for (const q of this.neighbours(p, !!this.s.upgrades.basket)) {
            if (!this.field.isRipe(q)) continue;
            const fert = q.fert;
            const crop = this.field.harvest(q);
            if (!crop) continue;
            const qx = FIELD.x0 + (q.col + 0.5) * PLOT;
            const qz = FIELD.z0 + (q.row + 0.5) * PLOT;
            const col = crop === 'wheat' ? [0.95, 0.78, 0.35] : crop === 'tomato' ? [0.9, 0.18, 0.1] : crop === 'carrot' ? [1.0, 0.5, 0.12] : crop === 'cabbage' ? [0.5, 0.75, 0.4] : [1.0, 0.5, 0.1];
            const y = this.field.surfaceAt(qx, qz);
            this.particles.harvest(qx, y, qz, col[0]!, col[1]!, col[2]!);
            const n = YIELD[crop] + (fert ? 1 : 0);
            give(this.s, crop, n);
            this.s.stats.harvested += n;
            tally(this.s, 'harvest');
            const sp = this.project(_v.set(qx, y + 0.5, qz));
            if (sp && !sp.edge) this.ui.float(`+${n}`, sp.x, sp.y, crop);
          }
          this.sfx('harvest', at);
          break;
        }
        default:
          return;
      }
      this.lastActed = p;
    });
  }

  private actOnObstacle(ob: Obstacle, tool: ToolId): boolean {
    if (tool !== ob.tool) {
      this.sfx('error', undefined, 0.4);
      return false;
    }
    if (!this.s.tools.includes(tool)) return false;
    if (tool !== this.tool) this.selectTool(tool);
    return this.vm.use(tool, () => {
      if (!ob.alive) return;
      const at = new Vector3(ob.x, ob.y + 0.3, ob.z);
      const hits = (this.s.hits[ob.key] ?? 0) + 1;
      if (hits < this.hitsNeeded(ob)) {
        this.s.hits[ob.key] = hits;
        this.estate.hitObstacle(ob);
        this.sfx(ob.tool === 'axe' ? 'chop' : ob.tool === 'pick' ? 'stone' : 'weed', at);
        this.lastActed = ob;
        return;
      }
      delete this.s.hits[ob.key];
      this.estate.hitObstacle(ob);
      this.estate.clearObstacle(ob, true);
      if (ob.respawn) this.s.clearedDay[ob.key] = this.env.day;
      else this.s.cleared[ob.key] = true;
      this.sfx(ob.tool === 'axe' ? 'timber' : ob.tool === 'pick' ? 'stone_break' : 'weed', at);
      for (const [item, n] of ob.drops) {
        give(this.s, item, n);
        tally(this.s, item, n);
        const sp = this.project(_v.set(ob.x, ob.y + 0.6, ob.z));
        if (sp && !sp.edge) this.ui.float(`+${n}`, sp.x, sp.y, item);
      }
      // a whole block cleared?
      if (ob.block > 0 && !this.s.blocks[ob.block] && !this.estate.obstacles.some((q) => q.alive && q.block === ob.block)) {
        this.s.blocks[ob.block] = true;
        this.s.flags[`block${ob.block}`] = true;
        this.estate.clearBlock(ob.block, true);
        this.ui.toast(`${BLOCK_NAMES[ob.block]} cleared — good soil, ready to till!`);
        this.sfx('objective');
      }
      this.lastActed = ob;
    });
  }

  /** E: talk, open, fill, build, or do the sensible thing. */
  interact(): void {
    const t = this.target;
    if (!t) return;
    const s = this.s;
    switch (t.kind) {
      case 'plot': {
        const p = t.plot!;
        const smart = this.plotVerdict(p, this.tool).ok ? this.tool : this.smartTool(p);
        if (smart && s.tools.includes(smart) && this.actOnPlot(p, smart, true)) return;
        if (p.crop && !p.fert && s.inv.compost > 0 && !this.field.isRipe(p)) {
          p.fert = true;
          s.inv.compost--;
          const x = FIELD.x0 + (p.col + 0.5) * PLOT;
          const z = FIELD.z0 + (p.row + 0.5) * PLOT;
          for (let i = 0; i < 18; i++) this.particles.emit({ x: x + (Math.random() - 0.5) * 0.9, y: 0.6, z: z + (Math.random() - 0.5) * 0.9, vy: -0.5, life: 0.8, size: 0.05, r: 0.18, g: 0.12, b: 0.07, alpha: 1, sprite: 0, gravity: 6, floor: 0.12 });
          this.sfx('seeds', new Vector3(x, 0.2, z));
          tally(s, 'compost_spread');
        }
        return;
      }
      case 'obstacle':
        this.actOnObstacle(t.obstacle!, t.obstacle!.tool);
        return;
      case 'tree': {
        const tr = t.tree!;
        if (s.shaken[tr.key] === this.env.day) {
          this.ui.toast('Nothing left on this one until tomorrow');
          return;
        }
        s.shaken[tr.key] = this.env.day;
        this.estate.shakeTree(tr, 3);
        this.sfx('shake', new Vector3(tr.x, 2, tr.z));
        tally(s, 'shake');
        return;
      }
      case 'board':
        this.openJournal();
        return;
      case 'pip':
      case 'crate':
        if (t.kind === 'pip' && !s.flags.talk_pip) {
          s.flags.talk_pip = true;
          this.estate.wave();
          this.ui.speech('Pip', 'Steward! Welcome to Brookhollow. Fill the castle’s commissions into that crate and I’ll ride them up the hill. The ripe wheat by the gate is a fine start.', 7);
          this.sfx('paper', undefined, 0.6);
          return;
        }
        this.openWagon();
        return;
      case 'wren':
        this.estate.waveWren();
        this.openShop();
        return;
      case 'well':
      case 'pond': {
        const cap = canCapacity(s);
        if (s.water >= cap) return;
        if (this.tool !== 'water') this.selectTool('water');
        s.water = cap;
        this.particles.splash(t.point.x, t.kind === 'pond' ? POND.level : terrainHeight(WELL.x, WELL.z) + 0.9, t.point.z);
        this.sfx('splash', t.point);
        this.ui.toast('Watering can filled', 'tool_water');
        return;
      }
      case 'sign':
        this.ui.toast(s.chapter >= 2 ? `${BLOCK_NAMES[t.block!]}: pull weeds with the hoe, break stones with the pick` : 'Overgrown. Old Tom’s tools would make short work of it…');
        return;
      case 'site': {
        const id = t.building!;
        const st = s.buildings[id];
        if (st.built) return;
        this.openBuild(id);
        return;
      }
      case 'hopper': {
        const m = s.mill;
        if (m.ready) {
          const n = m.ready;
          give(s, 'flour', n);
          tally(s, 'grind', n);
          m.ready = 0;
          this.floatAt(this.estate.sackPos, `+${n}`, 'flour');
          this.sfx('pack', this.estate.sackPos);
          return;
        }
        if (m.work.length < MILL_CAP && take(s, { wheat: MILL_BATCH })) {
          m.work.push(0);
          this.sfx('pour', this.estate.hopperPos, 0.7);
          for (let i = 0; i < 12; i++) this.particles.emit({ x: this.estate.hopperPos.x + (Math.random() - 0.5) * 0.2, y: this.estate.hopperPos.y + 1.4, z: this.estate.hopperPos.z + (Math.random() - 0.5) * 0.2, vy: -0.6, life: 0.6, size: 0.03, r: 0.9, g: 0.75, b: 0.4, alpha: 1, sprite: 0, gravity: 6, floor: this.estate.hopperPos.y + 0.9 });
        } else this.sfx('error', undefined, 0.4);
        return;
      }
      case 'henrun': {
        const hn = s.hens;
        if (hn.ready) {
          const n = hn.ready;
          give(s, 'eggs', n);
          tally(s, 'eggs', n);
          hn.ready = 0;
          this.floatAt(this.estate.nestPos, `+${n}`, 'eggs');
          this.sfx('pop', this.estate.nestPos);
          return;
        }
        if (hn.work.length < HEN_CAP && take(s, { wheat: HEN_FEED })) {
          hn.work.push(0);
          this.estate.scatterGrain();
          this.sfx('seeds', this.estate.runCentre);
          setTimeout(() => this.sfx('cluck', this.estate.runCentre), 350);
        } else this.sfx('error', undefined, 0.4);
        return;
      }
      case 'oven': {
        if (s.oven.ready) {
          this.takeDish();
          return;
        }
        this.openOven();
        return;
      }
      case 'compost': {
        const c = s.compost;
        if (c.ready) {
          const n = c.ready;
          give(s, 'compost', n);
          c.ready = 0;
          this.floatAt(this.estate.compostPos, `+${n}`, 'compost');
          this.sfx('pack', this.estate.compostPos);
          this.ui.toast('Compost: press E on a growing crop to spread it', 'compost');
          return;
        }
        if (c.work.length < COMPOST_CAP && take(s, { weeds: COMPOST_BATCH })) {
          c.work.push(0);
          this.sfx('weed', this.estate.compostPos);
        } else this.sfx('error', undefined, 0.4);
        return;
      }
      case 'bed':
        this.sleep();
        return;
    }
  }

  private floatAt(p: Vector3, text: string, icon: string): void {
    const sp = this.project(_v.copy(p).setY(p.y + 0.8));
    if (sp && !sp.edge) this.ui.float(text, sp.x, sp.y, icon);
  }

  private takeDish(): void {
    const d = this.s.oven.ready;
    if (!d) return;
    give(this.s, d, 1);
    tally(this.s, `bake:${d}`);
    this.s.oven.ready = null;
    this.s.oven.recipe = null;
    this.s.oven.t = 0;
    this.floatAt(this.estate.ovenPos, '+1', d);
    this.sfx('pop', this.estate.ovenPos);
  }

  // ------------------------------------------------------------------ panels
  /** Called by main after opening a panel, so it can release the mouse. */
  onPanel: (() => void) | null = null;

  openJournal(): void {
    this.ui.openJournal(this.s, this.questView(), (id) => this.ui.openLetter(id, () => this.openJournal()));
    this.sfx('paper');
    this.onPanel?.();
  }

  private pipLine(): string {
    const s = this.s;
    if (s.commissions.some((c) => c.packed)) return 'All packed? Say the word and I’ll have the pony moving.';
    const ready = s.commissions.find((c) => !c.packed && c.lines.every((l) => s.inv[l.item] >= l.qty));
    if (ready) return `You’ve got everything for ${ready.from}! Pack it in.`;
    const lines = PIP_LINES[s.ended ? 6 : s.chapter] ?? PIP_LINES[1]!;
    return lines[Math.floor(this.time / 9) % lines.length]!;
  }

  openWagon(): void {
    this.ui.openWagon(this.s, {
      pack: (c) => this.pack(c),
      send: () => this.sendWagon(),
      line: this.pipLine(),
      away: this.s.wagon.phase !== 'home',
      eta: 0,
    });
    this.sfx('paper');
    this.onPanel?.();
  }

  private pack(c: Commission): void {
    const s = this.s;
    if (c.packed || s.wagon.phase !== 'home') return;
    const needs: Partial<Record<ItemId, number>> = {};
    for (const l of c.lines) needs[l.item] = (needs[l.item] ?? 0) + l.qty;
    if (!take(s, needs)) {
      this.sfx('error');
      return;
    }
    c.packed = true;
    s.flags[`packed:${c.id}`] = true;
    s.coins += c.coins;
    s.stats.earned += c.coins;
    tally(s, 'pack');
    this.sfx('pack');
    setTimeout(() => this.sfx('coin'), 180);
    this.ui.toast(`Packed for ${c.from}: +${c.coins} coins`);
    this.estate.wave();
    this.updateCrateGoods();
    this.save();
  }

  private updateCrateGoods(): void {
    const items: ItemId[] = [];
    for (const c of this.s.commissions) if (c.packed) for (const l of c.lines) items.push(l.item);
    this.estate.setCrateGoods(items);
  }

  sendWagon(): void {
    const s = this.s;
    if (s.wagon.phase !== 'home') return;
    const packed = s.commissions.filter((c) => c.packed);
    if (!packed.length) return;
    for (const c of packed) {
      s.flags[`sent:${c.id}`] = true;
      s.stats.delivered++;
    }
    if (s.chapter === 5 && ['f1', 'f2', 'f3'].every((id) => s.flags[`sent:${id}`])) s.flags['sent:f'] = true;
    s.commissions = s.commissions.filter((c) => !c.packed);
    // the chapter is done once its last objective (sending) is ticked
    const ch = chapterOf(s.chapter);
    if (ch && !s.ended && ch.objectives.every((o) => objectiveDone(s, o) || this.special(o))) {
      s.wagon.mail.push(s.chapter >= CHAPTERS.length ? 'end' : `chapter:${s.chapter + 1}`);
    }
    s.wagon.phase = 'leaving';
    s.wagon.t = 0;
    this.estate.wave();
    this.ui.speech('Pip', 'Up the hill we go! Back before you know it.', 3.5);
    this.sfx('thunk', this.estate.cratePos);
    this.estate.setCrateGoods([]);
    this.save();
  }

  openShop(): void {
    if (!this.estate.stallVisible) return;
    this.ui.openShop(this.s, {
      avail: (c) => this.avail(c),
      buySeed: (c, n) => {
        const cost = SEED_PRICE[c] * n;
        if (this.s.coins < cost || this.s.chapter < SEED_CHAPTER[c]) return this.sfx('error');
        this.s.coins -= cost;
        give(this.s, seedOf(c), n);
        tally(this.s, 'buy');
        this.sfx('coin', undefined, 0.6);
        this.ui.setSeed(this.seed, this.unlockedCrops());
      },
      buyUpgrade: (u: UpgradeId) => {
        const def = UPGRADES.find((x) => x.id === u)!;
        if (this.s.upgrades[u] || this.s.coins < def.cost || this.s.chapter < def.chapter) return this.sfx('error');
        this.s.coins -= def.cost;
        this.s.upgrades[u] = true;
        tally(this.s, 'buy');
        if (u === 'can') {
          this.s.water = canCapacity(this.s);
          this.vm.setCopperCan(true);
        }
        this.sfx('chapter', undefined, 0.6);
        this.ui.toast(`${def.name} — ${def.blurb}`);
      },
      sell: (id, n) => {
        n = Math.min(n, this.s.inv[id]);
        if (n <= 0) return;
        this.s.inv[id] -= n;
        const coins = ITEMS[id].sell * n;
        this.s.coins += coins;
        this.s.stats.earned += coins;
        tally(this.s, 'sell', n);
        this.sfx('coin', undefined, 0.6);
      },
    });
    this.ui.speech('Wren', WREN_LINES[Math.floor(this.time / 7) % WREN_LINES.length]!, 4);
    this.sfx('paper');
    this.onPanel?.();
  }

  private openOven(): void {
    this.ui.openOven(
      this.s,
      (i) => {
        const r = OVEN_RECIPES[i]!;
        const ov = this.s.oven;
        if (ov.recipe !== null || ov.ready || this.s.chapter < r.chapter || !take(this.s, r.needs)) return this.sfx('error');
        ov.recipe = i;
        ov.t = 0;
        this.sfx('thunk', this.estate.ovenPos);
      },
      () => this.takeDish(),
    );
    this.sfx('paper');
    this.onPanel?.();
  }

  private openBuild(id: BuildingId): void {
    this.ui.openBuild(id, this.s, () => {
      if (!build(this.s, id)) return this.sfx('error');
      this.ui.closePanel();
      this.ui.toast(`The carpenters are raising your ${BUILDINGS[id].name}!`);
      this.sfx('build', this.estate.siteCentre(id, new Vector3()));
      this.save();
    });
    this.sfx('paper');
    this.onPanel?.();
  }

  // ------------------------------------------------------------------ chapters
  /** Objectives whose state isn't a plain tally or flag. */
  private special(o: Objective): boolean {
    if (o.key === 'mats3') return (this.s.inv.wood >= 12 && this.s.inv.stone >= 6) || this.s.buildings.windmill.built;
    return false;
  }

  questView(): QuestView {
    const s = this.s;
    const ch = chapterOf(s.chapter);
    if (!ch || s.ended) {
      return { chapter: s.chapter, title: s.ended ? 'Brookhollow, ever after' : '', objectives: [{ text: 'Fill the castle’s standing orders', value: 0, target: 1, done: false, current: true, hint: 'Commissions arrive with every wagon trip' }], foot: s.ended ? 'Royal Steward of Aldervale' : undefined };
    }
    let current = false;
    const objectives = ch.objectives.map((o) => {
      const done = objectiveDone(s, o) || this.special(o);
      const cur = !done && !current;
      if (cur) current = true;
      return { text: o.text, value: o.kind === 'flag' ? (done ? 1 : 0) : objectiveValue(s, o), target: o.target, done, current: cur, hint: o.hint };
    });
    let foot: string | undefined;
    if (s.wagon.phase !== 'home') foot = `Pip is on the road · back in ${Math.ceil(this.wagonEta())}s`;
    return { chapter: ch.n, title: ch.title, objectives, foot };
  }

  private wagonEta(): number {
    const w = this.s.wagon;
    if (w.phase === 'leaving') return LEAVE_TIME - w.t + AWAY_TIME + LEAVE_TIME;
    if (w.phase === 'away') return AWAY_TIME - w.t + LEAVE_TIME;
    if (w.phase === 'returning') return LEAVE_TIME - w.t;
    return 0;
  }

  private currentObjective(): Objective | null {
    const ch = chapterOf(this.s.chapter);
    if (!ch || this.s.ended) return null;
    return ch.objectives.find((o) => !(objectiveDone(this.s, o) || this.special(o))) ?? null;
  }

  private checkObjectives(): void {
    const ch = chapterOf(this.s.chapter);
    if (!ch || this.s.ended) return;
    for (const o of ch.objectives) {
      if (this.doneObjectives.has(o.id)) continue;
      if (objectiveDone(this.s, o) || this.special(o)) {
        this.doneObjectives.add(o.id);
        this.ui.objective(o.text);
        this.sfx('objective');
      }
    }
  }

  /** Begin chapter n: letter, banner, commissions, gifts. */
  startChapter(n: number): void {
    const s = this.s;
    const ch = chapterOf(n);
    if (!ch) return;
    s.chapter = n;
    s.base = { ...s.tally };
    this.doneObjectives = new Set();
    for (const c of ch.commissions(s, (i) => this.availItem(i))) if (!s.commissions.some((x) => x.id === c.id)) s.commissions.push(c);
    if (n >= 2) {
      for (const t of ['axe', 'pick'] as ToolId[]) if (!s.tools.includes(t)) s.tools.push(t);
      this.estate.setStallVisible(true);
      if (!s.commissions.some((c) => !c.story)) s.commissions.push(standingOrder(s, (i) => this.availItem(i)));
    }
    if (!s.letters.includes(ch.letter)) s.letters.push(ch.letter);
    this.ui.setSeed(this.seed, this.unlockedCrops());
    this.ui.openLetter(ch.letter, () => {
      this.ui.chapterBanner(n, ch.title);
      this.sfx('chapter');
    });
    this.onPanel?.();
    this.sfx('paper');
    this.save();
  }

  /** Show the opening letter on a brand-new farm. */
  intro(): void {
    if (this.s.letters.includes('intro')) return;
    this.s.letters.push('intro');
    this.ui.openLetter('intro', () => {
      this.ui.chapterBanner(1, CHAPTERS[0]!.title);
      this.sfx('chapter');
    });
    this.onPanel?.();
    this.sfx('paper');
  }

  private wagonArrived(): void {
    const s = this.s;
    const mail = s.wagon.mail.splice(0);
    // standing orders refresh with every trip once the stall is open
    if (s.chapter >= 2 || s.ended) {
      const standing = s.commissions.filter((c) => !c.story);
      if (standing.length < 2) s.commissions.push(standingOrder(s, (i) => this.availItem(i)));
    }
    this.ui.toast('Pip is back from the castle');
    this.sfx('thunk', this.estate.cratePos);
    for (const m of mail) {
      if (m === 'end') this.beginEnding();
      else if (m.startsWith('chapter:')) this.startChapter(Number(m.split(':')[1]));
    }
    this.save();
  }

  private beginEnding(): void {
    // fade to the night of the feast, then fireworks over the castle
    this.endingT = 0;
    this.ui.fade(true, 'That night, at Aldervale…');
    this.sfx('chapter');
  }

  private updateEnding(dt: number): void {
    if (this.endingT < 0) return;
    const before = this.endingT;
    this.endingT += dt;
    if (before < 2.2 && this.endingT >= 2.2) {
      this.env.setHour(21.2);
      this.fp.teleport(-29.5, 16.2, Math.atan2(-(-236 - -29.5), -(132 - 16.2)), 0.16);
      this.estate.startFireworks(32);
      this.ui.fade(false);
    }
    if (before < 30 && this.endingT >= 30) {
      if (!this.s.letters.includes('end')) this.s.letters.push('end');
      this.s.ended = true;
      this.onPanel?.();
      this.ui.openLetter('end', () => {
        this.onPanel?.();
        this.ui.openEnding(this.s, () => this.onEnding?.());
      });
      this.endingT = -1;
      this.save();
    }
  }

  // ------------------------------------------------------------------ day + night
  sleep(): void {
    const h = this.env.hour;
    if (!(h >= 18 || h < 5)) {
      this.ui.toast('Too early to turn in — come back after six');
      return;
    }
    if (this.sleeping) return;
    this.sleeping = true;
    this.ui.fade(true, 'You sleep soundly…');
    setTimeout(() => {
      // skip to morning: the farm keeps working while you sleep
      const toMorning = (h >= 18 ? 24 - h : 0) + 6.5 - (h < 5 ? h : 0);
      const sim = Math.round(toMorning * 20);
      for (let i = 0; i < sim; i++) {
        this.field.update(1);
        this.tickStations(1);
      }
      if (h >= 18) this.env.day++;
      this.env.setHour(6.5);
      this.sleeping = false;
      this.newDayCheck();
      this.save();
      this.ui.fade(false);
      this.ui.toast(`Day ${this.env.day} — good morning, steward`);
    }, 1300);
  }

  private newDayCheck(): void {
    if (this.env.day === this.lastDay) return;
    this.lastDay = this.env.day;
    const s = this.s;
    s.stats.days = this.env.day;
    // fallen branches gather again, apple trees fill, weather turns
    for (const ob of this.estate.obstacles) if (ob.respawn && !ob.alive && (s.clearedDay[ob.key] ?? -1) < this.env.day) this.estate.restoreObstacle(ob);
    const roll = Math.abs(Math.sin(this.env.day * 12.9898 + s.seed * 0.137) * 43758.5453) % 1;
    s.rain = s.chapter >= 2 && roll < 0.28;
    s.rainUntil = 7 + Math.floor((roll * 97) % 9);
    if (s.rain) this.ui.toast('Rain today — the fields will water themselves');
  }

  private tickStations(dt: number): void {
    const s = this.s;
    for (const id of BUILDING_IDS) {
      const st = s.buildings[id];
      if (st.built && st.progress < 1) {
        st.progress = Math.min(1, st.progress + dt / CONSTRUCT_TIME);
        if (st.progress >= 1) {
          this.ui.toast(`Your ${BUILDINGS[id].name} is finished!`);
          this.sfx('chapter', undefined, 0.7);
          s.flags[`built:${id}`] = true;
        }
      }
    }
    if (s.buildings.windmill.progress >= 1 && tickTimed(s.mill, dt, MILL_TIME)) this.near(this.estate.sackPos) && this.ui.toast('A sack of flour is ready at the mill', 'flour');
    if (s.buildings.henhouse.progress >= 1 && tickTimed(s.hens, dt, HEN_TIME)) this.near(this.estate.nestPos) && this.ui.toast('The hens have laid', 'eggs');
    tickTimed(s.compost, dt, COMPOST_TIME);
    const ov = s.oven;
    if (ov.recipe !== null && !ov.ready) {
      ov.t += dt;
      const r = OVEN_RECIPES[ov.recipe]!;
      if (ov.t >= r.time) {
        ov.ready = r.out;
        if (this.near(this.estate.ovenPos)) this.ui.toast(`${ITEMS[r.out].name} is ready`, r.out);
      }
    }
  }

  private near(p: Vector3): boolean {
    return this.fp.pos.distanceTo(p) < 40;
  }

  private tickWagon(dt: number): void {
    const w = this.s.wagon;
    if (w.phase === 'home') return;
    w.t += dt;
    if (w.phase === 'leaving' && w.t >= LEAVE_TIME) {
      w.phase = 'away';
      w.t = 0;
    } else if (w.phase === 'away' && w.t >= AWAY_TIME) {
      w.phase = 'returning';
      w.t = 0;
    } else if (w.phase === 'returning' && w.t >= LEAVE_TIME) {
      w.phase = 'home';
      w.t = 0;
      this.wagonArrived();
    }
  }

  // ------------------------------------------------------------------ helpers
  /** World point -> CSS pixels, clamped to the screen edge when off-screen. */
  project(p: Vector3): { x: number; y: number; edge: boolean } | null {
    const v = _w.copy(p).project(this.camera);
    const W = window.innerWidth;
    const H = window.innerHeight;
    let x = ((v.x + 1) / 2) * W;
    let y = ((1 - v.y) / 2) * H;
    let edge = false;
    if (v.z > 1) {
      // behind: mirror to the opposite edge
      x = W - x;
      y = H - 40;
      edge = true;
    }
    const m = 30;
    if (x < 0 || x > W || y < 0 || y > H) edge = true;
    x = clamp(x, m, W - m);
    y = clamp(y, m + 40, H - m);
    return { x, y, edge };
  }

  /** Like project(), but anything off-screen or behind is pinned to the screen edge on its side. */
  private edgeProject(p: Vector3): { x: number; y: number; edge: boolean } {
    const W = window.innerWidth;
    const H = window.innerHeight;
    const v = _w.copy(p).applyMatrix4(this.camera.matrixWorldInverse);
    const ndc = _v.copy(p).project(this.camera);
    const inFront = v.z < 0;
    if (inFront && Math.abs(ndc.x) <= 0.92 && ndc.y <= 0.85 && ndc.y >= -0.8) {
      return { x: ((ndc.x + 1) / 2) * W, y: ((1 - ndc.y) / 2) * H, edge: false };
    }
    // direction on screen from the centre (camera space x right, y up)
    let dx = v.x;
    let dy = inFront ? v.y : Math.min(v.y, 0) * 0.3;
    if (!inFront && Math.abs(dx) < 1e-3) dx = 1e-3;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const hw = W / 2 - 40;
    const hh = H / 2 - 90;
    const k = Math.min(hw / Math.max(Math.abs(dx), 1e-4), hh / Math.max(Math.abs(dy), 1e-4));
    return { x: W / 2 + dx * k, y: H / 2 - dy * k, edge: true };
  }

  private markerPos(id: MarkerId, out: Vector3): Vector3 | null {
    const E = this.estate;
    switch (id) {
      case 'pip':
        return E.wagonAway ? null : out.copy(E.courierPos).setY(E.courierPos.y + 2.25);
      case 'crate':
        return E.wagonAway ? null : out.copy(E.cratePos).setY(E.cratePos.y + 1.1);
      case 'wren':
        return E.stallVisible ? out.copy(E.wrenPos).setY(E.wrenPos.y + 2.3) : null;
      case 'field':
        return out.set(FIELD.x0 + 3.0, 1.0, FIELD.z0 + 2.4);
      case 'well':
        return out.set(WELL.x, terrainHeight(WELL.x, WELL.z) + 2.4, WELL.z);
      case 'block1':
        return E.signPosition(1, out).setY(1.8);
      case 'log': {
        const needStone = this.s.chapter === 3 && this.s.inv.stone < 6 && this.s.inv.wood >= 12;
        let best: Obstacle | null = null;
        let bd = Infinity;
        for (const ob of E.obstacles) {
          if (!ob.alive) continue;
          if (needStone ? ob.tool !== 'pick' : ob.tool !== 'axe') continue;
          const d = Math.hypot(ob.x - this.fp.pos.x, ob.z - this.fp.pos.z);
          if (d < bd) {
            bd = d;
            best = ob;
          }
        }
        return best ? out.set(best.x, best.y + best.h + 0.9, best.z) : null;
      }
      case 'windmill':
      case 'henhouse':
      case 'bakehouse':
        return E.siteCentre(id, out).setY(out.y + (this.s.buildings[id].built ? 6 : 2.6));
      case 'hopper':
        return out.copy(E.hopperPos).setY(E.hopperPos.y + 2.0);
      case 'henrun':
        return out.copy(E.runCentre).setY(E.runCentre.y + 1.8);
      case 'oven':
        return out.copy(E.ovenPos).setY(E.ovenPos.y + 1.2);
      case 'bed':
        return out.copy(E.bedPos).setY(E.bedPos.y + 1.4);
      case 'board':
        return out.copy(E.boardPos).setY(E.boardPos.y + 3.0);
    }
  }

  private markers(): MarkerView[] {
    if (!this.settings.markers || this.ui.panelOpen) return [];
    const o = this.currentObjective();
    if (!o?.marker) return [];
    // with the pick needed, guide to the nearest stone in the east furrows instead of the sign
    let id: MarkerId = o.marker;
    if (id === 'pip' && this.s.wagon.phase !== 'home') return [];
    if (id === 'crate' && this.s.commissions.some((c) => c.packed) && !this.s.flags[`sent:${this.s.chapter}`]) id = 'pip';
    const p = this.markerPos(id, new Vector3());
    if (!p) return [];
    const dist = Math.hypot(p.x - this.fp.pos.x, p.z - this.fp.pos.z);
    if (dist < 3.2) return [];
    const sp = this.edgeProject(p);
    return [{ x: sp.x, y: sp.y, label: `${o.text} · ${Math.round(dist)} m`, edge: sp.edge }];
  }

  private tags(): TagView[] {
    if (this.ui.panelOpen) return [];
    const s = this.s;
    const E = this.estate;
    const out: TagView[] = [];
    const add = (p: Vector3, lift: number, text: string, icon: string | undefined, ready: boolean): void => {
      const d = this.fp.pos.distanceTo(p);
      if (d > 14 || d < 1.2) return;
      const sp = this.project(_v.copy(p).setY(p.y + lift));
      if (!sp || sp.edge) return;
      out.push({ x: sp.x, y: sp.y, text, icon, ready });
    };
    if (s.buildings.windmill.progress >= 1) {
      const m = s.mill;
      const text = m.ready ? `${m.ready} sack${m.ready > 1 ? 's' : ''} ready` : m.work.length ? `Grinding · ${Math.ceil(MILL_TIME - (m.work[0] ?? 0))}s${m.work.length > 1 ? ` (+${m.work.length - 1})` : ''}` : 'Hopper · 3 wheat a sack';
      add(E.hopperPos, 1.9, text, 'flour', m.ready > 0);
    }
    if (s.buildings.henhouse.progress >= 1) {
      const hn = s.hens;
      const text = hn.ready ? `${hn.ready} egg basket${hn.ready > 1 ? 's' : ''}` : hn.work.length ? `Laying · ${Math.ceil(HEN_TIME - (hn.work[0] ?? 0))}s` : 'Hungry hens';
      add(E.runCentre, 1.6, text, 'eggs', hn.ready > 0);
    }
    if (s.buildings.bakehouse.progress >= 1) {
      const ov = s.oven;
      const text = ov.ready ? `${ITEMS[ov.ready].name} ready` : ov.recipe !== null ? `${ITEMS[OVEN_RECIPES[ov.recipe]!.out].name} · ${Math.ceil(OVEN_RECIPES[ov.recipe]!.time - ov.t)}s` : 'Oven';
      add(E.ovenPos, 0.9, text, ov.ready ?? (ov.recipe !== null ? OVEN_RECIPES[ov.recipe]!.out : 'bread'), !!ov.ready);
    }
    {
      const c = s.compost;
      if (c.ready || c.work.length) add(E.compostPos, 1.3, c.ready ? `${c.ready} compost ready` : `Rotting · ${Math.ceil(COMPOST_TIME - (c.work[0] ?? 0))}s`, 'compost', c.ready > 0);
    }
    if (!E.wagonAway && s.commissions.some((c) => c.packed)) add(E.cratePos, 1.0, `${s.commissions.filter((c) => c.packed).length} packed · tell Pip`, undefined, true);
    return out;
  }

  setHolding(v: boolean): void {
    this.holding = v;
    if (!v) this.lastActed = null;
  }

  // ------------------------------------------------------------------ per frame
  update(dt: number): void {
    this.time += dt;
    const s = this.s;
    this.tickStations(dt);
    this.tickWagon(dt);
    this.updateEnding(dt);
    if (!this.sleeping) this.newDayCheck();

    // weather
    if (s.rain && this.env.hour >= s.rainUntil && this.env.hour < 20) s.rain = false;
    this.env.rainTarget = s.rain ? 1 : 0;
    if (this.env.rain > 0.35) for (const p of this.field.plots) if (p.tilled && p.wet < 0.9) p.wet = 0.9;

    // apples on the ground are picked up as you walk over them
    const got = this.estate.collectApples(this.fp.pos, 1.15);
    if (got) {
      give(s, 'apple', got);
      tally(s, 'apple', got);
      this.sfx('pop');
      this.ui.toast(`+${got} apple${got > 1 ? 's' : ''}`, 'apple');
    }

    // targeting + prompt
    this.target = this.active && !this.ui.panelOpen && this.endingT < 0 ? this.findTarget() : null;
    const t = this.target;
    this.ui.setPrompt(t ? this.targetPrompt(t) : null);
    if (t?.kind === 'plot') {
      const ok = this.plotVerdict(t.plot!, this.tool).ok || !!this.smartTool(t.plot!);
      this.field.setHighlight(t.plot!, ok);
    } else if (t?.kind === 'obstacle' && t.plot) this.field.setHighlight(t.plot, t.obstacle!.tool === this.tool);
    else this.field.setHighlight(null, false);

    // hold the button to work along a row
    this.holdCool -= dt;
    if (this.holding && this.active && !this.vm.busy && this.holdCool <= 0 && t) {
      const key = t.kind === 'plot' ? t.plot : t.kind === 'obstacle' ? t.obstacle : null;
      if (key && (key !== this.lastActed || t.kind === 'obstacle')) {
        const ok = t.kind === 'plot' ? this.actOnPlot(t.plot!, this.tool, true) : this.actOnObstacle(t.obstacle!, this.tool);
        if (ok) this.holdCool = 0.05;
      }
    }

    // water stream while the can is tipped
    if (this.pouring > 0) {
      this.pouring -= dt;
      const sp = this.vm.spoutPosition(_v);
      if (sp) this.particles.droplets(sp.x, sp.y, sp.z, this.pourTarget.x, this.pourTarget.y, this.pourTarget.z, 2);
      if (Math.random() < 0.5) this.particles.splash(this.pourTarget.x, this.pourTarget.y, this.pourTarget.z);
    }

    // Pip and Wren say hello when you walk up
    const cd = this.estate.wagonAway ? 99 : this.fp.pos.distanceTo(this.estate.courierPos);
    if (cd < 5.5 && !this.greeted) {
      this.greeted = true;
      this.ui.speech('Pip', s.flags.talk_pip ? this.pipLine() : 'Steward! Over here, by the wagon!');
    } else if (cd > 12) this.greeted = false;
    const wd = this.estate.stallVisible ? this.fp.pos.distanceTo(this.estate.wrenPos) : 99;
    if (wd < 5 && !this.greetedWren) {
      this.greetedWren = true;
      this.estate.waveWren();
      this.ui.speech('Wren', WREN_LINES[Math.floor(this.time) % WREN_LINES.length]!);
    } else if (wd > 11) this.greetedWren = false;
    const who = wd < cd ? this.estate.wrenPos : this.estate.courierPos;
    const head = this.project(_v.copy(who).setY(who.y + 2.15));
    this.ui.placeSpeech(head ? head.x : -999, head ? head.y : -999, !!head && !head.edge && Math.min(cd, wd) < 16);

    this.checkObjectives();
    const ch = chapterOf(s.chapter);
    this.ui.setState(s, ch?.title ?? '');
    this.ui.setQuest(this.questView());
    this.ui.setMarkers(this.markers());
    this.ui.setTags(this.tags());
    this.ui.setClock(this.env.hour, this.env.day, s.rain);
    this.ui.update(dt);
    if (this.s.water > canCapacity(s)) this.s.water = canCapacity(s);

    this.saveT += dt;
    if (this.saveT > 8) {
      this.saveT = 0;
      this.save();
    }
  }

  /** Footstep surface under the player. */
  surface(x: number, z: number): 'grass' | 'dirt' | 'wood' {
    groundMask(x, z, this.gm);
    if (Math.max(this.gm.dirt, this.gm.path) > 0.35 || plotAt(x, z)) return 'dirt';
    return 'grass';
  }

  /** Ambience levels for the audio engine. */
  ambience(): { water: number; mill: number; fire: number; hens: number } {
    const p = this.fp.pos;
    const s = this.s;
    const water = 1 - smoothstep(1, 14, pondSdf(p.x, p.z));
    const mill = s.buildings.windmill.progress >= 1 && s.mill.work.length ? 1 - smoothstep(4, 24, p.distanceTo(this.estate.hopperPos)) : 0;
    const fire = s.buildings.bakehouse.progress >= 1 && s.oven.recipe !== null && !s.oven.ready ? 1 - smoothstep(2, 14, p.distanceTo(this.estate.ovenPos)) : 0;
    const hens = s.buildings.henhouse.progress >= 1 ? 1 - smoothstep(3, 18, p.distanceTo(this.estate.runCentre)) : 0;
    return { water, mill, fire, hens };
  }

  /** Debug: jump straight to a chapter with what it needs (for tests). */
  debugChapter(n: number): void {
    const s = this.s;
    s.coins += 400;
    s.inv.wood += 30;
    s.inv.stone += 30;
    s.commissions = s.commissions.filter((c) => !c.story);
    this.startChapter(n);
    this.ui.closePanel();
  }

  get targetKind(): string | null {
    return this.target?.kind ?? null;
  }
  get blockPlots(): typeof BLOCK_PLOTS {
    return BLOCK_PLOTS;
  }
  blockOfPlot(c: number, r: number): number {
    return blockOf(c, r);
  }
  hasItems(n: Partial<Record<ItemId, number>>): boolean {
    return has(this.s, n);
  }
  canRaise(b: BuildingId): boolean {
    return canBuild(this.s, b).ok;
  }
  get letters(): typeof LETTERS {
    return LETTERS;
  }
}
