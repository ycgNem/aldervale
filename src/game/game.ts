import { Vector3, type PerspectiveCamera } from 'three';
import type { Particles } from '../fx/particles';
import type { Environment } from '../render/sky';
import type { UI, PromptInfo } from '../ui/ui';
import type { Estate } from '../world/estate';
import { CROP_TYPES, type CropType, type Field, type Plot } from '../world/field';
import { FIELD, PLOT, POND, WELL, plotAt, pondSdf, terrainHeight } from '../world/layout';
import {
  BUILDINGS,
  BUILDING_IDS,
  CROP_LEVEL,
  CROP_YIELD,
  EXPANSIONS,
  ITEMS,
  WATER_MAX,
  build,
  buyExpansion,
  collect,
  deliver,
  discard,
  enqueue,
  expansionOf,
  levelFor,
  newEconomy,
  tick,
  unlocksAt,
  type BuildingId,
  type EconomyState,
  type Order,
} from './economy';
import type { FirstPerson } from './fp';
import { TOOL_IDS, type ToolId, type ViewModel } from './viewmodel';

const SAVE_KEY = 'aldervale.save.v1';
const REACH = 4.3;

interface Target {
  kind: 'plot' | 'board' | 'courier' | 'site' | 'sign' | 'well' | 'pond';
  dist: number;
  plot?: Plot;
  building?: BuildingId;
  expansion?: number;
  point: Vector3;
}

interface Verdict {
  ok: boolean;
  verb: string;
  label?: string;
  detail?: string;
}

interface SaveData {
  v: 1;
  econ: EconomyState;
  plots: { t: boolean; w: number; c: CropType | null; s: number; g: number }[];
  hour: number;
  day: number;
  pos: [number, number, number];
}

const GREETINGS = [
  'Good day, steward! The castle’s requests are pinned to the board.',
  'Fine weather for it. The kitchens are counting on you!',
  'Her Highness asked after your tomatoes again.',
  'Mind the road — the wagon’s heavy on the way up the hill.',
];
const THANKS = ['Splendid! The kitchens will be delighted.', 'That’ll keep the cooks singing. Here’s your pay.', 'Right on time. The castle thanks you, steward.', 'Lovely produce. I’ll have it up the hill by supper.'];

const _v = new Vector3();
const _d = new Vector3();
const _o = new Vector3();

export class Game {
  econ: EconomyState;
  tool: ToolId = 'hoe';
  seed: CropType = 'wheat';
  private target: Target | null = null;
  private holding = false;
  private holdCool = 0;
  private lastActed: Plot | null = null;
  private saveT = 0;
  private pouring = 0;
  private pourTarget = new Vector3();
  private greeted = false;
  private time = 0;
  /** True while gameplay input is live (pointer locked or forced by tests). */
  active = false;

  constructor(
    private readonly field: Field,
    private readonly fp: FirstPerson,
    private readonly vm: ViewModel,
    private readonly estate: Estate,
    private readonly particles: Particles,
    private readonly ui: UI,
    private readonly camera: PerspectiveCamera,
    private readonly env: Environment,
    fresh: boolean,
  ) {
    const saved = fresh ? null : Game.readSave();
    if (saved) {
      this.econ = saved.econ;
      saved.plots.forEach((q, i) => {
        const p = field.plots[i];
        if (!p) return;
        p.tilled = q.t;
        p.till = q.t ? 1 : 0;
        p.wet = q.w;
        p.crop = q.c;
        p.stage = q.s;
        p.growth = q.g;
        p.pop = 9;
      });
      env.setHour(saved.hour);
      env.day = saved.day;
      fp.teleport(saved.pos[0], saved.pos[2], saved.pos[1]);
    } else {
      this.econ = newEconomy();
      this.starterField();
    }
    estate.sync(this.econ);
    ui.setTool(this.tool);
    ui.setSeed(this.seed, this.unlockedCrops());
    ui.setEconomy(this.econ);
    ui.setWater(this.econ.water, WATER_MAX);
    ui.onTool = (t) => this.selectTool(t);
    ui.onSeed = (c) => this.selectSeed(c);
  }

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
      return d.v === 1 ? d : null;
    } catch {
      return null;
    }
  }
  save(): void {
    const d: SaveData = {
      v: 1,
      econ: this.econ,
      plots: this.field.plots.map((p) => ({ t: p.tilled, w: +p.wet.toFixed(3), c: p.crop, s: p.stage, g: +p.growth.toFixed(3) })),
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

  /** A few beds already on the go so the first requests can be filled quickly. */
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
      [3, 1, 'tomato', 0, true],
      [4, 1, 'wheat', 0, false],
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
    for (let c = 0; c < 4; c++) {
      const p = this.field.plot(c, 2);
      this.field.till(p);
      p.till = 1;
    }
  }

  unlockedCrops(): CropType[] {
    const l = levelFor(this.econ.xp);
    return CROP_TYPES.filter((c) => CROP_LEVEL[c] <= l);
  }

  selectTool(t: ToolId): void {
    this.tool = t;
    this.vm.setTool(t);
    this.ui.setTool(t);
    if (t === 'seeds') this.ui.setSeed(this.seed, this.unlockedCrops());
  }
  selectSeed(c: CropType): void {
    if (!this.unlockedCrops().includes(c)) {
      this.ui.toast(`${ITEMS[c].name} seeds unlock at Royal Favour level ${CROP_LEVEL[c]}`, c);
      return;
    }
    this.seed = c;
    if (this.tool !== 'seeds') this.selectTool('seeds');
    this.ui.setSeed(c, this.unlockedCrops());
  }
  cycleSeed(): void {
    const list = this.unlockedCrops();
    const i = list.indexOf(this.seed);
    this.selectSeed(list[(i + 1) % list.length]!);
  }
  cycleTool(dir: number): void {
    const i = TOOL_IDS.indexOf(this.tool);
    this.selectTool(TOOL_IDS[(i + dir + TOOL_IDS.length) % TOOL_IDS.length]!);
  }

  private locked(p: Plot): boolean {
    return !this.econ.expansions[expansionOf(p.col, p.row)];
  }

  // ------------------------------------------------------------------ targeting
  private findTarget(): Target | null {
    const o = this.camera.getWorldPosition(_o);
    const d = this.camera.getWorldDirection(_d);
    let best: Target | null = null;
    const consider = (t: Target): void => {
      if (!best || t.dist < best.dist) best = t;
    };
    const cyl = (cx: number, cz: number, base: number, r: number, hgt: number, max: number): number | null => {
      // ray vs vertical cylinder
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
      if (y < base - 0.2 || y > base + hgt) {
        // maybe enters through the cap: accept if the ray is inside at the cap level
        return null;
      }
      return t <= max ? t : null;
    };

    // the board and the courier
    const bp = this.estate.boardPos;
    let t = cyl(bp.x, bp.z, bp.y, 1.15, 2.8, REACH + 0.6);
    if (t !== null) consider({ kind: 'board', dist: t, point: bp });
    const cp = this.estate.courierPos;
    t = cyl(cp.x, cp.z, cp.y, 0.45, 1.95, REACH + 0.6);
    if (t !== null) consider({ kind: 'courier', dist: t, point: cp });
    // buildings / plots for buildings
    for (const id of BUILDING_IDS) {
      const c = this.estate.siteCentre(id, new Vector3());
      const r = id === 'windmill' ? 2.6 : id === 'bakehouse' ? 2.7 : 2.9;
      t = cyl(c.x, c.z, c.y, r, id === 'windmill' ? 9 : 4.5, REACH + 3.2);
      if (t !== null) consider({ kind: 'site', building: id, dist: t, point: c });
    }
    // the well
    t = cyl(WELL.x, WELL.z, terrainHeight(WELL.x, WELL.z), WELL.r, 2.4, REACH);
    if (t !== null) consider({ kind: 'well', dist: t, point: new Vector3(WELL.x, 0, WELL.z) });
    // expansion signs
    for (const e of EXPANSIONS) {
      if (e.cost === 0 || this.econ.expansions[e.id]) continue;
      const sp = this.estate.signPos[e.id];
      if (!sp) continue;
      t = cyl(sp.x, sp.z, sp.y, 0.45, 1.4, REACH);
      if (t !== null) consider({ kind: 'sign', expansion: e.id, dist: t, point: sp });
    }
    // the ground: field plots, pond water
    if (d.y < -0.05) {
      const tf = (0.12 - o.y) / d.y;
      if (tf > 0 && tf <= REACH) {
        const x = o.x + d.x * tf;
        const z = o.z + d.z * tf;
        const cr = plotAt(x, z);
        if (cr) {
          const p = this.field.plot(cr[0], cr[1]);
          consider({ kind: 'plot', plot: p, dist: tf, point: new Vector3(FIELD.x0 + (p.col + 0.5) * PLOT, 0.1, FIELD.z0 + (p.row + 0.5) * PLOT) });
        }
      }
      const tw = (POND.level - o.y) / d.y;
      if (tw > 0 && tw <= REACH + 0.5) {
        const x = o.x + d.x * tw;
        const z = o.z + d.z * tw;
        if (pondSdf(x, z) < -0.2) consider({ kind: 'pond', dist: tw, point: new Vector3(x, POND.level, z) });
      }
    }
    return best;
  }

  // ------------------------------------------------------------------ verdicts
  private plotVerdict(p: Plot, tool: ToolId): Verdict {
    if (this.locked(p)) {
      const e = EXPANSIONS[expansionOf(p.col, p.row)]!;
      return { ok: false, verb: 'Overgrown', detail: `Clear “${e.name}” at its sign` };
    }
    const crop = p.crop;
    switch (tool) {
      case 'hoe':
        if (crop) return { ok: false, verb: `${ITEMS[crop].name} growing here` };
        if (p.tilled) return { ok: false, verb: 'Already tilled', detail: 'Plant seeds here (2)' };
        return { ok: true, verb: 'Till soil' };
      case 'seeds':
        if (!p.tilled) return { ok: false, verb: 'Till the soil first', detail: 'Hoe (1)' };
        if (crop) return { ok: false, verb: 'Already planted' };
        return { ok: true, verb: 'Plant', label: `${ITEMS[this.seed].name}` };
      case 'water':
        if (!p.tilled) return { ok: false, verb: 'Nothing to water' };
        if (this.econ.water <= 0) return { ok: false, verb: 'The can is empty', detail: 'Fill it at the well or the pond' };
        if (p.wet > 0.55) return { ok: false, verb: 'Still damp' };
        return { ok: true, verb: 'Water', detail: crop ? 'Crops only grow while the soil is wet' : undefined };
      case 'harvest':
        if (!crop) return { ok: false, verb: 'Nothing to harvest' };
        if (!this.field.isRipe(p)) {
          const left = Math.ceil(this.field.timeToRipe(p));
          return { ok: false, verb: `${ITEMS[crop].name} not ripe yet`, detail: p.wet > 0.04 ? `About ${left}s more` : 'Dry soil — water it to grow' };
        }
        return { ok: true, verb: 'Harvest', label: ITEMS[crop].name, detail: `+${CROP_YIELD[crop]} ${ITEMS[crop].plural}` };
    }
  }

  /** The tool that makes sense for this plot right now. */
  private smartTool(p: Plot): ToolId | null {
    if (this.locked(p)) return null;
    if (!p.tilled) return 'hoe';
    if (!p.crop) return 'seeds';
    if (this.field.isRipe(p)) return 'harvest';
    if (p.wet < 0.3 && this.econ.water > 0) return 'water';
    return null;
  }

  private targetPrompt(t: Target): PromptInfo | null {
    const e = this.econ;
    switch (t.kind) {
      case 'plot': {
        const p = t.plot!;
        const v = this.plotVerdict(p, this.tool);
        if (v.ok) return { key: 'LMB', ...v };
        const smart = this.smartTool(p);
        if (smart && smart !== this.tool) {
          const sv = this.plotVerdict(p, smart);
          if (sv.ok) return { key: 'E', ...sv, detail: sv.detail ?? `switches to the ${smart === 'seeds' ? 'seed bag' : smart === 'water' ? 'watering can' : smart === 'harvest' ? 'basket' : 'hoe'}` };
        }
        if (this.locked(p)) return { key: 'E', ok: true, verb: 'Clear this land', detail: v.detail };
        return { key: 'LMB', ...v };
      }
      case 'board': {
        const ready = e.orders.filter((o) => o.wait <= 0 && o.lines.every((l) => e.inv[l.item] >= l.qty)).length;
        return { key: 'E', ok: true, verb: 'Read', label: 'the Royal Requisitions', detail: ready ? `${ready} ready to deliver` : undefined };
      }
      case 'courier':
        return { key: 'E', ok: true, verb: 'Talk to', label: 'Pip the Courier' };
      case 'well':
      case 'pond':
        if (e.water >= WATER_MAX) return { key: 'E', ok: false, verb: 'Watering can is full' };
        return { key: 'E', ok: true, verb: 'Fill', label: 'the watering can', detail: `${e.water}/${WATER_MAX}` };
      case 'sign': {
        const ex = EXPANSIONS[t.expansion!]!;
        return { key: 'E', ok: true, verb: 'Clear', label: ex.name, detail: `${ex.cost} coins · level ${ex.level}` };
      }
      case 'site': {
        const id = t.building!;
        const st = e.buildings[id];
        const def = BUILDINGS[id];
        if (!st.built) return { key: 'E', ok: true, verb: 'Build a', label: def.name, detail: `${def.cost} coins · level ${def.level}` };
        if (st.progress < 1) return { key: 'E', ok: false, verb: `Building the ${def.name}…`, detail: `${Math.round(st.progress * 100)}%` };
        if (st.ready.length) return { key: 'E', ok: true, verb: 'Collect', label: `${st.ready.length} ${st.ready.length > 1 ? ITEMS[st.ready[0]!].plural : ITEMS[st.ready[0]!].name}` };
        const job = st.queue[0];
        if (job) {
          const r = def.recipes[job.recipe]!;
          return { key: 'E', ok: true, verb: 'Open', label: def.name, detail: `Making ${ITEMS[r.out].name} · ${Math.ceil(r.time - job.t)}s` };
        }
        return { key: 'E', ok: true, verb: 'Open', label: def.name, detail: 'Idle' };
      }
    }
  }

  // ------------------------------------------------------------------ actions
  /** Left click: use the held tool on the plot ahead. */
  useTool(): void {
    const t = this.target;
    if (!t || t.kind !== 'plot') {
      if (t && (t.kind === 'well' || t.kind === 'pond') && this.tool === 'water') this.interact();
      return;
    }
    this.actOnPlot(t.plot!, this.tool);
  }

  private actOnPlot(p: Plot, tool: ToolId): boolean {
    const v = this.plotVerdict(p, tool);
    if (!v.ok) return false;
    if (tool !== this.tool) this.selectTool(tool);
    const x = FIELD.x0 + (p.col + 0.5) * PLOT;
    const z = FIELD.z0 + (p.row + 0.5) * PLOT;
    const started = this.vm.use(tool, () => {
      // re-check at the moment of impact: things may have changed
      if (!this.plotVerdict(p, tool).ok) return;
      const y = this.field.surfaceAt(x, z);
      switch (tool) {
        case 'hoe':
          this.field.till(p);
          this.particles.dust(x, y, z, 1);
          break;
        case 'seeds': {
          const from = this.vm.handPosition(_v);
          this.particles.seeds(from.x, from.y, from.z, x, y + 0.02, z);
          this.field.plant(p, this.seed);
          break;
        }
        case 'water':
          this.field.water(p);
          this.econ.water = Math.max(0, this.econ.water - 1);
          this.ui.setWater(this.econ.water, WATER_MAX);
          this.pouring = 0.55;
          this.pourTarget.set(x, y, z);
          break;
        case 'harvest': {
          const crop = this.field.harvest(p);
          if (!crop) return;
          const col = crop === 'wheat' ? [0.95, 0.78, 0.35] : crop === 'tomato' ? [0.9, 0.18, 0.1] : [1.0, 0.5, 0.1];
          this.particles.harvest(x, y, z, col[0]!, col[1]!, col[2]!);
          const n = CROP_YIELD[crop];
          this.econ.inv[crop] += n;
          const sp = this.project(_v.set(x, y + 0.5, z));
          if (sp) this.ui.float(`+${n}`, sp[0], sp[1], crop);
          this.ui.setEconomy(this.econ);
          break;
        }
      }
      this.lastActed = p;
    });
    return started;
  }

  /** E: talk, open, build, fill, or do the sensible thing to a plot. */
  interact(): void {
    const t = this.target;
    if (!t) return;
    const e = this.econ;
    switch (t.kind) {
      case 'plot': {
        const p = t.plot!;
        if (this.locked(p)) {
          this.openExpansion(expansionOf(p.col, p.row));
          return;
        }
        const smart = this.plotVerdict(p, this.tool).ok ? this.tool : this.smartTool(p);
        if (smart) this.actOnPlot(p, smart);
        return;
      }
      case 'board':
        this.openBoard();
        return;
      case 'courier': {
        const ready = e.orders.some((o) => o.wait <= 0 && o.lines.every((l) => e.inv[l.item] >= l.qty));
        this.ui.speech('Pip the Courier', ready ? 'I see you’ve got something for the castle! Pin it on the board and I’ll carry it up.' : GREETINGS[Math.floor(Math.random() * GREETINGS.length)]!);
        this.estate.wave();
        return;
      }
      case 'well':
      case 'pond':
        if (e.water >= WATER_MAX) return;
        if (this.tool !== 'water') this.selectTool('water');
        e.water = WATER_MAX;
        this.ui.setWater(e.water, WATER_MAX);
        this.particles.splash(t.point.x, t.kind === 'pond' ? POND.level : terrainHeight(WELL.x, WELL.z) + 0.9, t.point.z);
        this.ui.toast('Watering can filled', undefined);
        return;
      case 'sign':
        this.openExpansion(t.expansion!);
        return;
      case 'site': {
        const id = t.building!;
        const st = e.buildings[id];
        if (!st.built) this.openBuild(id);
        else if (st.progress < 1) return;
        else if (st.ready.length) {
          const got = collect(e, id);
          const sp = this.project(_v.copy(t.point).setY(t.point.y + 2));
          if (sp && got[0]) this.ui.float(`+${got.length}`, sp[0], sp[1], got[0]);
          this.ui.setEconomy(e);
        } else this.openBuilding(id);
        return;
      }
    }
  }

  private openBoard(): void {
    this.ui.openBoard(
      this.econ,
      (o: Order) => {
        const r = deliver(this.econ, o);
        if (!r) return;
        this.ui.toast(`Delivered! +${r.coins} coins, +${r.xp} favour`);
        this.ui.setEconomy(this.econ);
        this.estate.wave();
        this.ui.speech('Pip the Courier', THANKS[this.econ.delivered % THANKS.length]!);
        if (r.levelUp) this.levelUp(r.levelUp);
        this.save();
      },
      (o: Order) => {
        discard(o);
        this.ui.setEconomy(this.econ);
      },
    );
  }
  private openBuilding(id: BuildingId): void {
    this.ui.openBuilding(
      id,
      this.econ,
      (i) => {
        if (enqueue(this.econ, id, i)) this.ui.setEconomy(this.econ);
      },
      () => {
        collect(this.econ, id);
        this.ui.setEconomy(this.econ);
      },
    );
  }
  private openBuild(id: BuildingId): void {
    this.ui.openBuild(id, this.econ, () => {
      if (!build(this.econ, id)) return;
      this.ui.closePanel();
      this.ui.toast(`The carpenters are raising your ${BUILDINGS[id].name}!`);
      this.ui.setEconomy(this.econ);
      this.save();
    });
  }
  private openExpansion(id: number): void {
    const ex = EXPANSIONS[id];
    if (!ex) return;
    this.ui.openExpansion(ex, this.econ, () => {
      if (!buyExpansion(this.econ, id)) return;
      this.ui.closePanel();
      this.estate.clearBlock(id, true);
      this.ui.toast(`${ex.name} cleared — more room to grow!`);
      this.ui.setEconomy(this.econ);
      this.save();
    });
  }

  private levelUp(level: number): void {
    this.ui.levelUp(level, unlocksAt(level));
    this.ui.setSeed(this.seed, this.unlockedCrops());
  }

  /** World point -> CSS pixels, or null if behind the camera. */
  project(p: Vector3): [number, number] | null {
    const v = _v.copy(p).project(this.camera);
    if (v.z > 1) return null;
    return [((v.x + 1) / 2) * window.innerWidth, ((1 - v.y) / 2) * window.innerHeight];
  }

  setHolding(v: boolean): void {
    this.holding = v;
    if (!v) this.lastActed = null;
  }

  update(dt: number): void {
    this.time += dt;
    const ev = tick(this.econ, dt);
    for (const id of ev.finished) {
      const c = this.estate.siteCentre(id, new Vector3());
      if (c.distanceTo(this.fp.pos) < 30) this.ui.toast(`${BUILDINGS[id].name}: ${ITEMS[this.econ.buildings[id].ready.at(-1)!].name} ready`, this.econ.buildings[id].ready.at(-1));
    }
    for (const id of ev.built) {
      this.ui.toast(`Your ${BUILDINGS[id].name} is finished!`);
      this.save();
    }
    if (ev.newOrders) this.ui.toast(ev.newOrders > 1 ? 'New requests from the castle' : 'A new request from the castle');

    // targeting + prompt
    this.target = this.active && !this.ui.panelOpen ? this.findTarget() : null;
    const t = this.target;
    const prompt = t ? this.targetPrompt(t) : null;
    this.ui.setPrompt(prompt);
    if (t?.kind === 'plot') {
      const ok = this.plotVerdict(t.plot!, this.tool).ok || !!this.smartTool(t.plot!);
      this.field.setHighlight(t.plot!, ok);
    } else this.field.setHighlight(null, false);

    // hold the button to work along a row
    this.holdCool -= dt;
    if (this.holding && this.active && !this.vm.busy && this.holdCool <= 0 && t?.kind === 'plot' && t.plot !== this.lastActed) {
      if (this.actOnPlot(t.plot!, this.tool)) this.holdCool = 0.05;
    }

    // water stream while the can is tipped
    if (this.pouring > 0) {
      this.pouring -= dt;
      const sp = this.vm.spoutPosition(_v);
      if (sp) this.particles.droplets(sp.x, sp.y, sp.z, this.pourTarget.x, this.pourTarget.y, this.pourTarget.z, 2);
      if (Math.random() < 0.5) this.particles.splash(this.pourTarget.x, this.pourTarget.y, this.pourTarget.z);
    }

    // courier says hello when you walk up
    const cd = this.fp.pos.distanceTo(this.estate.courierPos);
    if (cd < 5.5 && !this.greeted) {
      this.greeted = true;
      this.ui.speech('Pip the Courier', GREETINGS[this.econ.delivered % GREETINGS.length]!);
    } else if (cd > 12) this.greeted = false;
    const head = this.project(_v.copy(this.estate.courierPos).setY(this.estate.courierPos.y + 2.15));
    this.ui.placeSpeech(head ? head[0] : -999, head ? head[1] : -999, !!head && cd < 16);

    this.ui.setEconomy(this.econ);
    this.ui.setClock(this.env.hour, this.env.day);
    this.ui.update(dt);

    this.saveT += dt;
    if (this.saveT > 6) {
      this.saveT = 0;
      this.save();
    }
  }
}
