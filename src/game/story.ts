/**
 * The story of Brookhollow Farm: chapters, their objectives, the letters that carry the plot,
 * the story commissions and the standing orders that keep the wagon busy afterwards.
 */
import { mulberry32 } from '../util/math';
import { ITEMS, since, type Commission, type GameState, type ItemId, type Line } from './state';

export type MarkerId =
  | 'pip'
  | 'crate'
  | 'wren'
  | 'field'
  | 'well'
  | 'block1'
  | 'log'
  | 'windmill'
  | 'hopper'
  | 'henhouse'
  | 'henrun'
  | 'bakehouse'
  | 'oven'
  | 'bed'
  | 'board';

export interface Objective {
  id: string;
  text: string;
  /** 'tally' counts an event since the chapter began; 'have' checks the satchel; 'flag' is a yes/no. */
  kind: 'tally' | 'have' | 'flag';
  key: string;
  target: number;
  marker?: MarkerId;
  /** Shown under the objective while it is the current one. */
  hint?: string;
}

export interface Chapter {
  n: number;
  title: string;
  /** Letter that opens the chapter. */
  letter: string;
  objectives: Objective[];
  /** Story commissions that arrive with the chapter. */
  commissions: (s: GameState, avail: (c: ItemId) => boolean) => Commission[];
}

export interface Letter {
  title: string;
  from: string;
  body: string[];
  sign: string;
}

export const LETTERS: Record<string, Letter> = {
  intro: {
    title: 'A Deed for Brookhollow',
    from: 'Aldervale Castle',
    body: [
      'To the new keeper of Brookhollow Farm,',
      'By leave of the Crown the old homestead below the castle is yours. It has lain wild since Old Tom laid down his hoe: thistles in the furrows, the mill plot staked but never built, the hens long gone.',
      'The castle larders are bare after a hard winter. Grow what you can, fill our commissions, and by harvest-tide we may yet hold a feast worthy of the name.',
      'Pip, our courier, waits with the wagon by the road. He will show you the way of things.',
    ],
    sign: 'Lady Ashby, Chatelaine of Aldervale',
  },
  ch2: {
    title: 'Old Tom’s Tools',
    from: 'Pip, by way of the wagon',
    body: [
      'Steward! The kitchens were overjoyed — first fresh wheat since autumn.',
      'I found these in the castle storehouse: Old Tom’s axe and pick, still sharp. The east furrows were his best soil before the thistles and stones took them. Clear them and you’ll have room to grow.',
      'And a friend of mine, Wren, has pitched her cart at the crossroads. She sells seeds from all over the valley and buys whatever you can spare.',
    ],
    sign: 'Pip',
  },
  ch3: {
    title: 'Flour for the Bakers',
    from: 'The Castle Bakehouse',
    body: [
      'Good steward, we have wheat at last, but no mill to grind it. The old miller’s plot east of your field is still staked out.',
      'Gather timber from the fallen trees and stone from the fields, and raise a windmill. Pour your wheat into its hopper and send us flour — we will pay handsomely.',
    ],
    sign: 'Bartholomew, Master Baker',
  },
  ch4: {
    title: 'Hens and Hearth',
    from: 'The East Tower',
    body: [
      'Dear Steward, I am told you are the one to ask. My birthday falls at harvest-tide and I should dearly love a proper pumpkin pie, the kind my nurse used to bake.',
      'You will need eggs, of course, and an oven. There is room on your farm for a hen house and a bakehouse — I have asked Lady Ashby to see you are paid for your trouble.',
    ],
    sign: 'Elowen, Princess of Aldervale',
  },
  ch5: {
    title: 'The Harvest Feast',
    from: 'King Corwin of Aldervale',
    body: [
      'Steward of Brookhollow,',
      'Word of your farm has reached the throne room. This year Aldervale will hold its Harvest Feast again, the first since my father’s day, and I would have it supplied from your fields.',
      'Three crates, if you please: one for the bread table, one for the sweet table, and one for the cellar. Send them up the hill with Pip and come and watch the sky above the castle that night.',
    ],
    sign: 'Corwin, by the grace of the valley, King',
  },
  end: {
    title: 'A Feast to Remember',
    from: 'King Corwin of Aldervale',
    body: [
      'They are still talking about the bread, the pies, the cider. My daughter has declared your pumpkin pie the finest in seven kingdoms.',
      'By my hand and seal, you are named Royal Steward of Aldervale. Brookhollow is yours for as long as you wish to keep it, and the castle will always have work for your fields.',
    ],
    sign: 'Corwin, King',
  },
};

const C = (s: GameState, id: string, from: string, title: string, note: string, lines: Line[], coins: number): Commission => ({ id, from, title, note, lines, coins, story: true, packed: !!s.flags[`packed:${id}`] });

export const CHAPTERS: Chapter[] = [
  {
    n: 1,
    title: 'The Steward Arrives',
    letter: 'intro',
    objectives: [
      { id: 'pip', text: 'Meet Pip by the royal wagon', kind: 'flag', key: 'talk_pip', target: 1, marker: 'pip' },
      { id: 'harvest', text: 'Harvest ripe crops', kind: 'tally', key: 'harvest', target: 3, marker: 'field', hint: 'Basket (4) or press E on a ripe plot' },
      { id: 'till', text: 'Till fresh soil', kind: 'tally', key: 'till', target: 3, marker: 'field', hint: 'Hoe (1) on bare earth' },
      { id: 'plant', text: 'Plant seeds', kind: 'tally', key: 'plant', target: 3, marker: 'field', hint: 'Seed bag (2), Q switches seed' },
      { id: 'water', text: 'Water the seedlings', kind: 'tally', key: 'water', target: 3, marker: 'field', hint: 'Can (3) — refill it at the well' },
      { id: 'c1', text: 'Pack the Royal Kitchens’ crate', kind: 'flag', key: 'packed:c1', target: 1, marker: 'crate', hint: 'Bring 6 wheat to the crate behind the wagon' },
      { id: 'send1', text: 'Send Pip up the hill', kind: 'flag', key: 'sent:c1', target: 1, marker: 'pip' },
    ],
    commissions: (s) => [C(s, 'c1', 'The Royal Kitchens', 'Bread wheat', 'The first fresh wheat since autumn, if you please.', [{ item: 'wheat', qty: 6 }], 20)],
  },
  {
    n: 2,
    title: 'Room to Grow',
    letter: 'ch2',
    objectives: [
      { id: 'block1', text: 'Clear the East Furrows', kind: 'flag', key: 'block1', target: 1, marker: 'block1', hint: 'Hoe pulls weeds, the pick (6) breaks stones' },
      { id: 'wood', text: 'Chop firewood from fallen trees', kind: 'tally', key: 'wood', target: 6, marker: 'log', hint: 'Axe (5) on logs, stumps and branches' },
      { id: 'buy', text: 'Buy seeds at Wren’s stall', kind: 'tally', key: 'buy', target: 1, marker: 'wren' },
      { id: 'c2', text: 'Pack Head Cook Marigold’s crate', kind: 'flag', key: 'packed:c2', target: 1, marker: 'crate' },
      { id: 'send2', text: 'Send Pip up the hill', kind: 'flag', key: 'sent:c2', target: 1, marker: 'pip' },
    ],
    commissions: (s, avail) => [
      C(s, 'c2', 'Head Cook Marigold', 'Stew for the garrison', 'The guards have eaten turnip soup for a month. Spare them.', avail('carrot') ? [{ item: 'tomato', qty: 6 }, { item: 'carrot', qty: 4 }] : [{ item: 'tomato', qty: 6 }, { item: 'wheat', qty: 6 }], 55),
    ],
  },
  {
    n: 3,
    title: 'The Mill on the Rise',
    letter: 'ch3',
    objectives: [
      { id: 'mats', text: 'Gather 12 wood and 6 stone', kind: 'flag', key: 'mats3', target: 1, marker: 'log', hint: 'Fallen logs and field stones' },
      { id: 'build', text: 'Raise the windmill', kind: 'flag', key: 'built:windmill', target: 1, marker: 'windmill', hint: 'E at the staked plot east of the field' },
      { id: 'grind', text: 'Grind sacks of flour', kind: 'tally', key: 'grind', target: 3, marker: 'hopper', hint: '3 wheat into the hopper makes a sack' },
      { id: 'c3', text: 'Pack the Master Baker’s crate', kind: 'flag', key: 'packed:c3', target: 1, marker: 'crate' },
      { id: 'send3', text: 'Send Pip up the hill', kind: 'flag', key: 'sent:c3', target: 1, marker: 'pip' },
    ],
    commissions: (s) => [C(s, 'c3', 'Bartholomew, Master Baker', 'Flour at last', 'Four sacks and the castle eats bread again.', [{ item: 'flour', qty: 4 }, { item: 'wheat', qty: 4 }], 95)],
  },
  {
    n: 4,
    title: 'Hens and Hearth',
    letter: 'ch4',
    objectives: [
      { id: 'hen', text: 'Build the hen house', kind: 'flag', key: 'built:henhouse', target: 1, marker: 'henhouse' },
      { id: 'eggs', text: 'Collect eggs', kind: 'tally', key: 'eggs', target: 2, marker: 'henrun', hint: 'Scatter wheat in the run, then check the nest' },
      { id: 'bake', text: 'Build the bakehouse', kind: 'flag', key: 'built:bakehouse', target: 1, marker: 'bakehouse' },
      { id: 'bread', text: 'Bake loaves of bread', kind: 'tally', key: 'bake:bread', target: 2, marker: 'oven' },
      { id: 'c4', text: 'Pack Princess Elowen’s crate', kind: 'flag', key: 'packed:c4', target: 1, marker: 'crate' },
      { id: 'send4', text: 'Send Pip up the hill', kind: 'flag', key: 'sent:c4', target: 1, marker: 'pip' },
    ],
    commissions: (s) => [C(s, 'c4', 'Princess Elowen', 'A birthday pie', 'Pumpkin, golden, and still warm if you can manage it.', [{ item: 'pie', qty: 1 }, { item: 'bread', qty: 2 }], 140)],
  },
  {
    n: 5,
    title: 'The Harvest Feast',
    letter: 'ch5',
    objectives: [
      { id: 'f1', text: 'Pack the Bread Table crate', kind: 'flag', key: 'packed:f1', target: 1, marker: 'crate' },
      { id: 'f2', text: 'Pack the Sweet Table crate', kind: 'flag', key: 'packed:f2', target: 1, marker: 'crate' },
      { id: 'f3', text: 'Pack the Cellar crate', kind: 'flag', key: 'packed:f3', target: 1, marker: 'crate' },
      { id: 'send5', text: 'Send the feast up the hill', kind: 'flag', key: 'sent:f', target: 1, marker: 'pip' },
    ],
    commissions: (s, avail) => [
      C(s, 'f1', 'King Corwin', 'The Bread Table', 'Loaves for every bench in the great hall.', avail('cabbage') ? [{ item: 'bread', qty: 3 }, { item: 'cabbage', qty: 3 }] : [{ item: 'bread', qty: 3 }, { item: 'carrot', qty: 6 }], 160),
      C(s, 'f2', 'King Corwin', 'The Sweet Table', 'For the princess, and for the King, who has a sweet tooth.', [{ item: 'pie', qty: 2 }, { item: 'tart', qty: 2 }], 220),
      C(s, 'f3', 'King Corwin', 'The Cellar', 'Something to raise a cup with.', [{ item: 'chutney', qty: 2 }, { item: 'cider', qty: 2 }], 180),
    ],
  },
];

export function chapterOf(n: number): Chapter | null {
  return CHAPTERS[n - 1] ?? null;
}

/** Progress of an objective (0..target). */
export function objectiveValue(s: GameState, o: Objective): number {
  switch (o.kind) {
    case 'tally':
      return Math.min(o.target, since(s, o.key));
    case 'have':
      return Math.min(o.target, s.inv[o.key as ItemId] ?? 0);
    case 'flag':
      return s.flags[o.key] ? 1 : 0;
  }
}
export function objectiveDone(s: GameState, o: Objective): boolean {
  return objectiveValue(s, o) >= o.target;
}

// ------------------------------------------------------------------ standing orders
const PATRONS = ['The Royal Kitchens', 'Captain of the Guard', 'The Stable Hands', 'Lady Ashby', 'The Castle Laundry', 'Brother Anselm', 'The Gatehouse', 'Cook’s apprentice'];
const NOTES = ['Whatever you can spare.', 'For the evening table.', 'The usual, if it’s no trouble.', 'They go fast up here.', 'Paid on packing, as ever.'];

/** A modest order for things the player can already make. */
export function standingOrder(s: GameState, avail: (c: ItemId) => boolean): Commission {
  const rnd = mulberry32(s.seed++ * 7919);
  const pool: ItemId[] = ['wheat', 'tomato'];
  if (s.chapter >= 2) pool.push('apple');
  if (avail('carrot') && s.chapter >= 2) pool.push('carrot');
  if (s.chapter >= 2) pool.push('pumpkin');
  if (avail('cabbage') && s.chapter >= 3) pool.push('cabbage');
  if (s.buildings.windmill.built) pool.push('flour', 'flour');
  if (s.buildings.henhouse.built) pool.push('eggs');
  if (s.buildings.bakehouse.built) pool.push('bread', 'chutney', 'pie');
  if (s.buildings.bakehouse.built && s.chapter >= 5) pool.push('tart', 'cider');
  const n = 1 + (rnd() < 0.45 && s.chapter >= 2 ? 1 : 0);
  const lines: Line[] = [];
  for (let i = 0; i < n; i++) {
    const item = pool[Math.floor(Math.pow(rnd(), 0.7) * pool.length)]!;
    if (lines.some((l) => l.item === item)) continue;
    const v = ITEMS[item].sell;
    const qty = Math.max(1, Math.round((v <= 4 ? 4 + rnd() * 5 : v <= 12 ? 2 + rnd() * 3 : 1 + rnd() * 1.6) * (1 + (s.chapter - 1) * 0.15)));
    lines.push({ item, qty });
  }
  let value = 0;
  for (const l of lines) value += ITEMS[l.item].sell * l.qty;
  const coins = Math.round(value * 1.45 + 4);
  return {
    id: `o${s.nextId++}`,
    from: PATRONS[Math.floor(rnd() * PATRONS.length)]!,
    title: 'Standing order',
    note: NOTES[Math.floor(rnd() * NOTES.length)]!,
    lines,
    coins,
    story: false,
    packed: false,
  };
}
