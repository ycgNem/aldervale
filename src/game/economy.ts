/**
 * The castle economy: goods, recipes, buildings, Royal Favour levels and requisition orders.
 * Pure data + rules, no rendering.
 */
import type { CropType } from '../world/field';
import { mulberry32 } from '../util/math';

export type ItemId = CropType | 'flour' | 'eggs' | 'bread' | 'pie' | 'chutney';
export const ITEM_IDS: ItemId[] = ['wheat', 'tomato', 'pumpkin', 'flour', 'eggs', 'bread', 'pie', 'chutney'];

export interface ItemDef {
  id: ItemId;
  name: string;
  plural: string;
  /** Model in items.glb used for the 3D icon. */
  model: string;
  /** Base coin value per unit in an order. */
  value: number;
  /** Favour per unit delivered. */
  xp: number;
  /** Level at which the castle starts asking for it. */
  level: number;
}

export const ITEMS: Record<ItemId, ItemDef> = {
  wheat: { id: 'wheat', name: 'Wheat', plural: 'Wheat', model: 'item_wheat', value: 3, xp: 1, level: 1 },
  tomato: { id: 'tomato', name: 'Tomato', plural: 'Tomatoes', model: 'item_tomato', value: 5, xp: 1, level: 1 },
  pumpkin: { id: 'pumpkin', name: 'Pumpkin', plural: 'Pumpkins', model: 'item_pumpkin', value: 9, xp: 2, level: 2 },
  flour: { id: 'flour', name: 'Flour', plural: 'Flour', model: 'item_flour', value: 14, xp: 3, level: 2 },
  eggs: { id: 'eggs', name: 'Eggs', plural: 'Eggs', model: 'item_eggs', value: 12, xp: 3, level: 3 },
  chutney: { id: 'chutney', name: 'Tomato Chutney', plural: 'Tomato Chutney', model: 'item_chutney', value: 24, xp: 5, level: 4 },
  bread: { id: 'bread', name: 'Bread', plural: 'Loaves', model: 'item_bread', value: 36, xp: 7, level: 4 },
  pie: { id: 'pie', name: 'Pumpkin Pie', plural: 'Pumpkin Pies', model: 'item_pie', value: 44, xp: 8, level: 5 },
};

export const CROP_YIELD: Record<CropType, number> = { wheat: 2, tomato: 2, pumpkin: 1 };
export const CROP_LEVEL: Record<CropType, number> = { wheat: 1, tomato: 1, pumpkin: 2 };

export type BuildingId = 'windmill' | 'henhouse' | 'bakehouse';
export const BUILDING_IDS: BuildingId[] = ['windmill', 'henhouse', 'bakehouse'];

export interface Recipe {
  out: ItemId;
  qty: number;
  needs: Partial<Record<ItemId, number>>;
  /** Seconds. */
  time: number;
  level: number;
}

export interface BuildingDef {
  id: BuildingId;
  name: string;
  blurb: string;
  cost: number;
  level: number;
  slots: number;
  recipes: Recipe[];
}

export const BUILDINGS: Record<BuildingId, BuildingDef> = {
  windmill: {
    id: 'windmill',
    name: 'Windmill',
    blurb: 'Grinds wheat into flour for the royal bakers.',
    cost: 150,
    level: 2,
    slots: 3,
    recipes: [{ out: 'flour', qty: 1, needs: { wheat: 3 }, time: 30, level: 2 }],
  },
  henhouse: {
    id: 'henhouse',
    name: 'Hen House',
    blurb: 'Feed the hens a little wheat and they lay fresh eggs.',
    cost: 240,
    level: 3,
    slots: 3,
    recipes: [{ out: 'eggs', qty: 1, needs: { wheat: 2 }, time: 35, level: 3 }],
  },
  bakehouse: {
    id: 'bakehouse',
    name: 'Bakehouse',
    blurb: 'A wood-fired oven for bread, pies and preserves.',
    cost: 420,
    level: 4,
    slots: 3,
    recipes: [
      { out: 'chutney', qty: 1, needs: { tomato: 3 }, time: 35, level: 4 },
      { out: 'bread', qty: 1, needs: { flour: 2, eggs: 1 }, time: 45, level: 4 },
      { out: 'pie', qty: 1, needs: { pumpkin: 1, flour: 1, eggs: 1 }, time: 55, level: 5 },
    ],
  },
};

/** Field expansions: column/row blocks of the 10x8 field. */
export interface ExpansionDef {
  id: number;
  name: string;
  cols: [number, number];
  rows: [number, number];
  cost: number;
  level: number;
}
export const EXPANSIONS: ExpansionDef[] = [
  { id: 0, name: 'Home plot', cols: [0, 4], rows: [0, 3], cost: 0, level: 1 },
  { id: 1, name: 'East furrows', cols: [5, 9], rows: [0, 3], cost: 90, level: 2 },
  { id: 2, name: 'South-west beds', cols: [0, 4], rows: [4, 7], cost: 260, level: 3 },
  { id: 3, name: 'South-east beds', cols: [5, 9], rows: [4, 7], cost: 520, level: 5 },
];

/** Total favour needed to reach each level (index = level - 1). */
export const LEVEL_XP = [0, 24, 70, 150, 270, 440, 680, 1000, 1400, 1900, 2500];
export function levelFor(xp: number): number {
  let l = 1;
  while (l < LEVEL_XP.length && xp >= LEVEL_XP[l]!) l++;
  return l;
}
export function levelProgress(xp: number): number {
  const l = levelFor(xp);
  if (l >= LEVEL_XP.length) return 1;
  const a = LEVEL_XP[l - 1]!;
  const b = LEVEL_XP[l]!;
  return (xp - a) / (b - a);
}

export interface OrderLine {
  item: ItemId;
  qty: number;
}
export interface Order {
  id: number;
  /** Who at the castle wants it (flavour). */
  from: string;
  lines: OrderLine[];
  coins: number;
  xp: number;
  /** >0 while the slot is waiting for a new order (seconds left). */
  wait: number;
}

const PATRONS = [
  'The Royal Kitchens',
  'Head Cook Marigold',
  'The Steward of Aldervale',
  'Princess Elowen',
  'Captain of the Guard',
  'The Castle Bakers',
  'Lady Ashby of the West Tower',
  'The Harvest Feast Committee',
  'Old King Corwin',
  'The Stable Hands',
];

export interface Job {
  recipe: number;
  /** Seconds of work done. */
  t: number;
}
export interface BuildingState {
  built: boolean;
  /** 0..1 while under construction, 1 when done. */
  progress: number;
  queue: Job[];
  /** Finished goods waiting to be collected. */
  ready: ItemId[];
}

export interface EconomyState {
  coins: number;
  xp: number;
  inv: Record<ItemId, number>;
  orders: Order[];
  nextOrderId: number;
  buildings: Record<BuildingId, BuildingState>;
  expansions: boolean[];
  water: number;
  delivered: number;
  seed: number;
}

export const WATER_MAX = 12;
export const ORDER_SLOTS = 3;
export const CONSTRUCT_TIME = 6;

function emptyInv(): Record<ItemId, number> {
  return { wheat: 0, tomato: 0, pumpkin: 0, flour: 0, eggs: 0, bread: 0, pie: 0, chutney: 0 };
}

export function newEconomy(): EconomyState {
  const s: EconomyState = {
    coins: 40,
    xp: 0,
    inv: emptyInv(),
    orders: [],
    nextOrderId: 1,
    buildings: {
      windmill: { built: false, progress: 0, queue: [], ready: [] },
      henhouse: { built: false, progress: 0, queue: [], ready: [] },
      bakehouse: { built: false, progress: 0, queue: [], ready: [] },
    },
    expansions: [true, false, false, false],
    water: WATER_MAX,
    delivered: 0,
    seed: 1234,
  };
  s.inv.wheat = 2;
  // the first requisitions are gentle and only want what the starter field grows
  s.orders.push(makeOrder(s, [{ item: 'wheat', qty: 4 }], 'The Royal Kitchens'));
  s.orders.push(makeOrder(s, [{ item: 'tomato', qty: 3 }], 'Head Cook Marigold'));
  s.orders.push(makeOrder(s, [{ item: 'wheat', qty: 2 }, { item: 'tomato', qty: 2 }], 'The Steward of Aldervale'));
  return s;
}

function priceOf(lines: OrderLine[]): { coins: number; xp: number } {
  let coins = 0;
  let xp = 0;
  for (const l of lines) {
    coins += ITEMS[l.item].value * l.qty;
    xp += ITEMS[l.item].xp * l.qty;
  }
  return { coins: Math.round(coins * 1.35 + 4), xp: Math.max(2, Math.round(xp * 1.5)) };
}

function makeOrder(s: EconomyState, lines: OrderLine[], from: string): Order {
  const p = priceOf(lines);
  return { id: s.nextOrderId++, from, lines, coins: p.coins, xp: p.xp, wait: 0 };
}

/** Items the castle may ask for at this level: only things the player can actually make. */
export function wantedItems(s: EconomyState): ItemId[] {
  const lvl = levelFor(s.xp);
  const out: ItemId[] = [];
  for (const id of ITEM_IDS) {
    const d = ITEMS[id];
    if (d.level > lvl) continue;
    if (id === 'flour' && !s.buildings.windmill.built) continue;
    if (id === 'eggs' && !s.buildings.henhouse.built) continue;
    if ((id === 'bread' || id === 'pie' || id === 'chutney') && !s.buildings.bakehouse.built) continue;
    out.push(id);
  }
  return out;
}

export function generateOrder(s: EconomyState): Order {
  const rnd = mulberry32(s.seed++);
  const lvl = levelFor(s.xp);
  const pool = wantedItems(s);
  const nLines = Math.min(pool.length, 1 + Math.floor(rnd() * Math.min(3, 1 + lvl / 2)));
  const lines: OrderLine[] = [];
  const used = new Set<ItemId>();
  // lean toward the newest goods so new buildings get used
  for (let i = 0; i < nLines; i++) {
    let pick: ItemId = pool[Math.floor(Math.pow(rnd(), 0.6) * pool.length)]!;
    for (let k = 0; k < 6 && used.has(pick); k++) pick = pool[Math.floor(rnd() * pool.length)]!;
    if (used.has(pick)) continue;
    used.add(pick);
    const v = ITEMS[pick].value;
    const base = v <= 5 ? 3 + lvl * 0.8 : v <= 14 ? 1 + lvl * 0.35 : 1 + lvl * 0.15;
    const qty = Math.max(1, Math.round(base * (0.6 + rnd() * 0.7)));
    lines.push({ item: pick, qty });
  }
  return makeOrder(s, lines, PATRONS[Math.floor(rnd() * PATRONS.length)]!);
}

export function canFill(s: EconomyState, o: Order): boolean {
  if (o.wait > 0) return false;
  return o.lines.every((l) => s.inv[l.item] >= l.qty);
}

export interface Reward {
  coins: number;
  xp: number;
  levelUp: number | null;
}

export function deliver(s: EconomyState, o: Order): Reward | null {
  if (!canFill(s, o)) return null;
  const before = levelFor(s.xp);
  for (const l of o.lines) s.inv[l.item] -= l.qty;
  s.coins += o.coins;
  s.xp += o.xp;
  s.delivered++;
  const after = levelFor(s.xp);
  const r: Reward = { coins: o.coins, xp: o.xp, levelUp: after > before ? after : null };
  o.wait = 14;
  o.lines = [];
  return r;
}

/** Throw an order away; a new one arrives after a longer wait. */
export function discard(o: Order): void {
  o.wait = 25;
  o.lines = [];
}

export function canAfford(s: EconomyState, needs: Partial<Record<ItemId, number>>): boolean {
  for (const k of Object.keys(needs) as ItemId[]) if (s.inv[k] < (needs[k] ?? 0)) return false;
  return true;
}

export function enqueue(s: EconomyState, b: BuildingId, recipe: number): boolean {
  const st = s.buildings[b];
  const def = BUILDINGS[b];
  const r = def.recipes[recipe];
  if (!r || !st.built || st.progress < 1) return false;
  if (st.queue.length + st.ready.length >= def.slots) return false;
  if (levelFor(s.xp) < r.level) return false;
  if (!canAfford(s, r.needs)) return false;
  for (const k of Object.keys(r.needs) as ItemId[]) s.inv[k] -= r.needs[k] ?? 0;
  st.queue.push({ recipe, t: 0 });
  return true;
}

export function collect(s: EconomyState, b: BuildingId): ItemId[] {
  const st = s.buildings[b];
  const got = st.ready.splice(0);
  for (const id of got) s.inv[id] += 1;
  return got;
}

/** Advance timers. Returns events worth showing. */
export function tick(s: EconomyState, dt: number): { finished: BuildingId[]; built: BuildingId[]; newOrders: number } {
  const out = { finished: [] as BuildingId[], built: [] as BuildingId[], newOrders: 0 };
  for (const id of BUILDING_IDS) {
    const st = s.buildings[id];
    if (st.built && st.progress < 1) {
      st.progress = Math.min(1, st.progress + dt / CONSTRUCT_TIME);
      if (st.progress >= 1) out.built.push(id);
    }
    const job = st.queue[0];
    if (job && st.progress >= 1) {
      const r = BUILDINGS[id].recipes[job.recipe]!;
      job.t += dt;
      if (job.t >= r.time) {
        st.queue.shift();
        for (let i = 0; i < r.qty; i++) st.ready.push(r.out);
        out.finished.push(id);
      }
    }
  }
  for (const o of s.orders) {
    if (o.wait > 0) {
      o.wait -= dt;
      if (o.wait <= 0) {
        const n = generateOrder(s);
        o.id = n.id;
        o.from = n.from;
        o.lines = n.lines;
        o.coins = n.coins;
        o.xp = n.xp;
        o.wait = 0;
        out.newOrders++;
      }
    }
  }
  return out;
}

export function build(s: EconomyState, b: BuildingId): boolean {
  const def = BUILDINGS[b];
  const st = s.buildings[b];
  if (st.built || s.coins < def.cost || levelFor(s.xp) < def.level) return false;
  s.coins -= def.cost;
  st.built = true;
  st.progress = 0;
  return true;
}

export function buyExpansion(s: EconomyState, id: number): boolean {
  const e = EXPANSIONS[id];
  if (!e || s.expansions[id] || s.coins < e.cost || levelFor(s.xp) < e.level) return false;
  s.coins -= e.cost;
  s.expansions[id] = true;
  return true;
}

export function expansionOf(col: number, row: number): number {
  for (const e of EXPANSIONS) {
    if (col >= e.cols[0] && col <= e.cols[1] && row >= e.rows[0] && row <= e.rows[1]) return e.id;
  }
  return 0;
}

/** What a new level unlocks, for the level-up banner. */
export function unlocksAt(level: number): string[] {
  const out: string[] = [];
  for (const c of Object.keys(CROP_LEVEL) as CropType[]) if (CROP_LEVEL[c] === level) out.push(`${ITEMS[c].name} seeds`);
  for (const b of BUILDING_IDS) if (BUILDINGS[b].level === level) out.push(BUILDINGS[b].name);
  for (const b of BUILDING_IDS) for (const r of BUILDINGS[b].recipes) if (r.level === level && BUILDINGS[b].level !== level) out.push(`${ITEMS[r.out].name} recipe`);
  for (const e of EXPANSIONS) if (e.level === level && e.cost > 0) out.push(`Field: ${e.name}`);
  return out;
}
