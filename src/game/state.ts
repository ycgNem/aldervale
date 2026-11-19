/**
 * Aldervale's rules and data: goods, seeds, materials, buildings, stations, upgrades and the
 * persistent game state. Pure data + small helpers; no rendering.
 */
import type { CropType } from '../world/field';

export type GoodId = 'flour' | 'eggs' | 'bread' | 'pie' | 'chutney' | 'tart' | 'cider' | 'apple';
export type MaterialId = 'wood' | 'stone' | 'weeds' | 'compost';
export type SeedId = `seed_${CropType}`;
export type ItemId = CropType | GoodId | MaterialId | SeedId;

export const CROPS: CropType[] = ['wheat', 'tomato', 'carrot', 'pumpkin', 'cabbage'];

export interface ItemDef {
  name: string;
  plural: string;
  /** Model rendered for the icon (with fallbacks). */
  model: string;
  fallback?: string;
  /** What Wren pays for one. 0 = she won't buy it. */
  sell: number;
  kind: 'crop' | 'good' | 'material' | 'seed';
}

const seed = (c: string, name: string): ItemDef => ({ name: `${name} seeds`, plural: `${name} seeds`, model: `seed_${c}`, fallback: `${c}_0`, sell: 0, kind: 'seed' });

export const ITEMS: Record<ItemId, ItemDef> = {
  wheat: { name: 'Wheat', plural: 'Wheat', model: 'item_wheat', fallback: 'wheat_3', sell: 2, kind: 'crop' },
  tomato: { name: 'Tomato', plural: 'Tomatoes', model: 'item_tomato', fallback: 'tomato_3', sell: 4, kind: 'crop' },
  carrot: { name: 'Carrot', plural: 'Carrots', model: 'item_carrot', fallback: 'carrot_3', sell: 3, kind: 'crop' },
  pumpkin: { name: 'Pumpkin', plural: 'Pumpkins', model: 'item_pumpkin', fallback: 'pumpkin_3', sell: 10, kind: 'crop' },
  cabbage: { name: 'Cabbage', plural: 'Cabbages', model: 'item_cabbage', fallback: 'cabbage_3', sell: 9, kind: 'crop' },
  flour: { name: 'Flour', plural: 'Sacks of flour', model: 'item_flour', sell: 9, kind: 'good' },
  eggs: { name: 'Eggs', plural: 'Eggs', model: 'item_eggs', sell: 7, kind: 'good' },
  bread: { name: 'Bread', plural: 'Loaves', model: 'item_bread', sell: 24, kind: 'good' },
  pie: { name: 'Pumpkin Pie', plural: 'Pumpkin pies', model: 'item_pie', sell: 38, kind: 'good' },
  chutney: { name: 'Tomato Chutney', plural: 'Jars of chutney', model: 'item_chutney', sell: 18, kind: 'good' },
  tart: { name: 'Apple Tart', plural: 'Apple tarts', model: 'item_tart', fallback: 'item_pie', sell: 34, kind: 'good' },
  cider: { name: 'Spiced Cider', plural: 'Jugs of cider', model: 'item_cider', fallback: 'item_chutney', sell: 22, kind: 'good' },
  apple: { name: 'Apple', plural: 'Apples', model: 'item_apple', fallback: 'item_tomato', sell: 2, kind: 'good' },
  wood: { name: 'Wood', plural: 'Wood', model: 'item_wood', fallback: 'woodpile', sell: 2, kind: 'material' },
  stone: { name: 'Stone', plural: 'Stone', model: 'item_stone', fallback: 'rock_c', sell: 2, kind: 'material' },
  weeds: { name: 'Weeds', plural: 'Weeds', model: 'item_weeds', fallback: 'reed_clump', sell: 0, kind: 'material' },
  compost: { name: 'Compost', plural: 'Compost', model: 'item_compost', fallback: 'bucket', sell: 4, kind: 'material' },
  seed_wheat: seed('wheat', 'Wheat'),
  seed_tomato: seed('tomato', 'Tomato'),
  seed_carrot: seed('carrot', 'Carrot'),
  seed_pumpkin: seed('pumpkin', 'Pumpkin'),
  seed_cabbage: seed('cabbage', 'Cabbage'),
};
export const ITEM_IDS = Object.keys(ITEMS) as ItemId[];

export function seedOf(c: CropType): SeedId {
  return `seed_${c}` as SeedId;
}

/** Crops harvested per plot. */
export const YIELD: Record<CropType, number> = { wheat: 2, tomato: 3, carrot: 2, pumpkin: 1, cabbage: 1 };
/** Seed price per seed at Wren's stall. */
export const SEED_PRICE: Record<CropType, number> = { wheat: 1, tomato: 2, carrot: 2, pumpkin: 5, cabbage: 4 };
/** Chapter from which Wren stocks the seed. */
export const SEED_CHAPTER: Record<CropType, number> = { wheat: 1, tomato: 1, carrot: 2, pumpkin: 2, cabbage: 3 };

// ------------------------------------------------------------------ tools + upgrades
export type ToolId = 'hoe' | 'seeds' | 'water' | 'harvest' | 'axe' | 'pick';
export const TOOL_ORDER: ToolId[] = ['hoe', 'seeds', 'water', 'harvest', 'axe', 'pick'];
export const TOOL_NAMES: Record<ToolId, string> = { hoe: 'Hoe', seeds: 'Seed bag', water: 'Watering can', harvest: 'Basket', axe: 'Axe', pick: 'Pick' };

export type UpgradeId = 'can' | 'hoe' | 'basket' | 'edge';
export interface UpgradeDef {
  id: UpgradeId;
  name: string;
  blurb: string;
  cost: number;
  chapter: number;
}
export const UPGRADES: UpgradeDef[] = [
  { id: 'can', name: 'Copper Watering Can', blurb: 'Holds 30 waterings and soaks three plots in a row.', cost: 120, chapter: 3 },
  { id: 'hoe', name: 'Broad Hoe', blurb: 'Tills three plots in a row with every stroke.', cost: 90, chapter: 3 },
  { id: 'basket', name: 'Wide Basket', blurb: 'Gathers the ripe crops of three plots at once.', cost: 80, chapter: 3 },
  { id: 'edge', name: 'Whetstone', blurb: 'Keener axe and pick: one swing fewer on every log and stone.', cost: 60, chapter: 2 },
];
export function canCapacity(s: GameState): number {
  return s.upgrades.can ? 30 : 12;
}

// ------------------------------------------------------------------ buildings + stations
export type BuildingId = 'windmill' | 'henhouse' | 'bakehouse';
export const BUILDING_IDS: BuildingId[] = ['windmill', 'henhouse', 'bakehouse'];
export interface BuildingDef {
  id: BuildingId;
  name: string;
  blurb: string;
  coins: number;
  wood: number;
  stone: number;
  chapter: number;
}
export const BUILDINGS: Record<BuildingId, BuildingDef> = {
  windmill: { id: 'windmill', name: 'Windmill', blurb: 'Pour wheat into its hopper and the sails grind it into flour.', coins: 80, wood: 12, stone: 6, chapter: 3 },
  henhouse: { id: 'henhouse', name: 'Hen House', blurb: 'Four hens who lay when you scatter them a little grain.', coins: 120, wood: 10, stone: 6, chapter: 4 },
  bakehouse: { id: 'bakehouse', name: 'Bakehouse', blurb: 'A wood-fired oven for bread, pies, tarts, chutney and cider.', coins: 160, wood: 8, stone: 12, chapter: 4 },
};
export const CONSTRUCT_TIME = 8;

export interface Recipe {
  out: GoodId;
  needs: Partial<Record<ItemId, number>>;
  time: number;
  chapter: number;
}
export const OVEN_RECIPES: Recipe[] = [
  { out: 'chutney', needs: { tomato: 3, apple: 1 }, time: 30, chapter: 4 },
  { out: 'bread', needs: { flour: 2, eggs: 1 }, time: 40, chapter: 4 },
  { out: 'pie', needs: { pumpkin: 1, flour: 1, eggs: 1 }, time: 50, chapter: 4 },
  { out: 'tart', needs: { apple: 3, flour: 1 }, time: 45, chapter: 5 },
  { out: 'cider', needs: { apple: 4 }, time: 35, chapter: 5 },
];
export const MILL_BATCH = 3; // wheat per sack
export const MILL_TIME = 18;
export const MILL_CAP = 4;
export const HEN_FEED = 2; // wheat per feeding
export const HEN_TIME = 30;
export const HEN_CAP = 3;
export const COMPOST_BATCH = 4; // weeds per compost
export const COMPOST_TIME = 35;
export const COMPOST_CAP = 4;

export interface Timed {
  /** Batches still being worked, oldest first; each value is seconds of work done. */
  work: number[];
  /** Finished outputs waiting to be taken. */
  ready: number;
}
export interface OvenState {
  recipe: number | null;
  t: number;
  ready: GoodId | null;
}
export interface BuildingState {
  built: boolean;
  progress: number;
}

// ------------------------------------------------------------------ commissions
export interface Line {
  item: ItemId;
  qty: number;
}
export interface Commission {
  id: string;
  from: string;
  title: string;
  note: string;
  lines: Line[];
  coins: number;
  story: boolean;
  packed: boolean;
}

export type WagonPhase = 'home' | 'leaving' | 'away' | 'returning';
export interface WagonState {
  phase: WagonPhase;
  t: number;
  /** Letters (ids) Pip brings back. */
  mail: string[];
}

// ------------------------------------------------------------------ state
export interface GameState {
  v: 2;
  coins: number;
  inv: Record<ItemId, number>;
  tools: ToolId[];
  upgrades: Partial<Record<UpgradeId, boolean>>;
  water: number;
  chapter: number;
  /** Objective progress counters for the current chapter (by objective id). */
  progress: Record<string, number>;
  /** Event tallies over the whole game (for objectives that count since chapter start we snapshot). */
  tally: Record<string, number>;
  /** Tally snapshot taken when the chapter began. */
  base: Record<string, number>;
  flags: Record<string, boolean>;
  commissions: Commission[];
  nextId: number;
  wagon: WagonState;
  buildings: Record<BuildingId, BuildingState>;
  mill: Timed;
  hens: Timed;
  compost: Timed;
  oven: OvenState;
  /** Cleared field obstacles, by key. */
  cleared: Record<string, boolean>;
  /** Hits taken by obstacles in progress. */
  hits: Record<string, number>;
  /** Meadow obstacles respawn: key -> day it was cleared. */
  clearedDay: Record<string, number>;
  blocks: boolean[];
  /** Day each apple tree was last shaken. */
  shaken: Record<string, number>;
  /** Plots that have had compost spread (by index). */
  fertile: Record<string, boolean>;
  rain: boolean;
  rainUntil: number;
  letters: string[];
  stats: { harvested: number; delivered: number; earned: number; days: number };
  seed: number;
  ended: boolean;
}

function emptyInv(): Record<ItemId, number> {
  const inv = {} as Record<ItemId, number>;
  for (const id of ITEM_IDS) inv[id] = 0;
  return inv;
}

export function newState(): GameState {
  const s: GameState = {
    v: 2,
    coins: 25,
    inv: emptyInv(),
    tools: ['hoe', 'seeds', 'water', 'harvest'],
    upgrades: {},
    water: 12,
    chapter: 1,
    progress: {},
    tally: {},
    base: {},
    flags: {},
    commissions: [],
    nextId: 1,
    wagon: { phase: 'home', t: 0, mail: [] },
    buildings: {
      windmill: { built: false, progress: 0 },
      henhouse: { built: false, progress: 0 },
      bakehouse: { built: false, progress: 0 },
    },
    mill: { work: [], ready: 0 },
    hens: { work: [], ready: 0 },
    compost: { work: [], ready: 0 },
    oven: { recipe: null, t: 0, ready: null },
    cleared: {},
    hits: {},
    clearedDay: {},
    blocks: [true, false, false, false],
    shaken: {},
    fertile: {},
    rain: false,
    rainUntil: 0,
    letters: [],
    stats: { harvested: 0, delivered: 0, earned: 0, days: 1 },
    seed: 7,
    ended: false,
  };
  s.inv.seed_wheat = 6;
  s.inv.seed_tomato = 3;
  return s;
}

// ------------------------------------------------------------------ helpers
export function has(s: GameState, needs: Partial<Record<ItemId, number>>): boolean {
  for (const k of Object.keys(needs) as ItemId[]) if (s.inv[k] < (needs[k] ?? 0)) return false;
  return true;
}
export function take(s: GameState, needs: Partial<Record<ItemId, number>>): boolean {
  if (!has(s, needs)) return false;
  for (const k of Object.keys(needs) as ItemId[]) s.inv[k] -= needs[k] ?? 0;
  return true;
}
export function give(s: GameState, id: ItemId, n = 1): void {
  s.inv[id] = (s.inv[id] ?? 0) + n;
}
export function count(s: GameState, id: ItemId): number {
  return s.inv[id] ?? 0;
}
export function tally(s: GameState, key: string, n = 1): void {
  s.tally[key] = (s.tally[key] ?? 0) + n;
}
/** Tally since the current chapter began. */
export function since(s: GameState, key: string): number {
  return (s.tally[key] ?? 0) - (s.base[key] ?? 0);
}

export function canBuild(s: GameState, b: BuildingId): { ok: boolean; why: string } {
  const d = BUILDINGS[b];
  if (s.chapter < d.chapter) return { ok: false, why: `Opens in chapter ${d.chapter}` };
  if (s.coins < d.coins) return { ok: false, why: `${d.coins - s.coins} more coins needed` };
  if (s.inv.wood < d.wood) return { ok: false, why: `${d.wood - s.inv.wood} more wood needed` };
  if (s.inv.stone < d.stone) return { ok: false, why: `${d.stone - s.inv.stone} more stone needed` };
  return { ok: true, why: '' };
}

export function build(s: GameState, b: BuildingId): boolean {
  const d = BUILDINGS[b];
  const st = s.buildings[b];
  if (st.built || !canBuild(s, b).ok) return false;
  s.coins -= d.coins;
  s.inv.wood -= d.wood;
  s.inv.stone -= d.stone;
  st.built = true;
  st.progress = 0;
  return true;
}

/** Advance a timed station. Returns how many outputs finished. */
export function tickTimed(t: Timed, dt: number, time: number): number {
  let done = 0;
  const first = t.work[0];
  if (first !== undefined) {
    t.work[0] = first + dt;
    if (t.work[0]! >= time) {
      t.work.shift();
      t.ready++;
      done++;
    }
  }
  return done;
}

export const STEWARD_RANKS = ['Tenant', 'Smallholder', 'Yeoman', 'Steward', 'Royal Steward'];
