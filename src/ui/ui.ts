import '@fontsource-variable/fraunces';
import '@fontsource-variable/nunito';
import './ui.css';
import type { CropType } from '../world/field';
import {
  BUILDINGS,
  CROPS,
  ITEMS,
  ITEM_IDS,
  OVEN_RECIPES,
  SEED_CHAPTER,
  SEED_PRICE,
  STEWARD_RANKS,
  TOOL_NAMES,
  TOOL_ORDER,
  UPGRADES,
  canBuild,
  canCapacity,
  seedOf,
  type BuildingId,
  type Commission,
  type GameState,
  type ItemId,
  type ToolId,
  type UpgradeId,
} from '../game/state';
import { LETTERS, type Letter } from '../game/story';

type Attrs = Record<string, string>;
function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', attrs: Attrs = {}, ...kids: (Node | string | null | undefined)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k in attrs) e.setAttribute(k, attrs[k]!);
  for (const c of kids) if (c !== null && c !== undefined) e.append(c);
  return e;
}

const CREST_SVG = `<svg viewBox="0 0 50 56"><defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3f5fb0"/><stop offset=".6" stop-color="#2b4486"/><stop offset="1" stop-color="#1c2d5e"/></linearGradient><linearGradient id="cgd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d27a"/><stop offset="1" stop-color="#b8862b"/></linearGradient></defs><path d="M25 2 L46 8 V27 C46 41 36 50 25 54 C14 50 4 41 4 27 V8 Z" fill="url(#cgd)"/><path d="M25 6 L42.5 11 V27 C42.5 39 34 47 25 50.5 C16 47 7.5 39 7.5 27 V11 Z" fill="url(#cg)"/><path d="M14 13 l3 4 3-5 2.5 5 2.5-5 2.5 5 2.5-5 3 5 3-4 -1.5 7 h-19 z" fill="#f6d27a" opacity=".22"/></svg>`;
const COIN_SVG = `<svg class="coin-ico" viewBox="0 0 20 20"><defs><radialGradient id="cn" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#fff1b8"/><stop offset=".5" stop-color="#f2c14e"/><stop offset="1" stop-color="#b07a1c"/></radialGradient></defs><circle cx="10" cy="10" r="9" fill="url(#cn)" stroke="#8a5d12" stroke-width="1"/><circle cx="10" cy="10" r="6" fill="none" stroke="#a87418" stroke-width="1" opacity=".7"/><path d="M7 7.5l1.5 2 1.5-2.5 1.5 2.5 1.5-2-0.8 4.5h-4.4z" fill="#a87418" opacity=".8"/></svg>`;
const MOUSE_SVG = `<svg viewBox="0 0 13 17"><rect x=".75" y=".75" width="11.5" height="15.5" rx="5.75" fill="none" stroke="#2f2519" stroke-width="1.5"/><path d="M1.5 6.5 H6.5 V1.2 A5.4 5.4 0 0 0 1.5 6.5Z" fill="#2f2519"/></svg>`;
const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI'];

export interface PromptInfo {
  key: 'E' | 'LMB';
  verb: string;
  label?: string;
  detail?: string;
  ok: boolean;
}

export interface ObjectiveView {
  text: string;
  value: number;
  target: number;
  done: boolean;
  current: boolean;
  hint?: string;
}

export interface QuestView {
  chapter: number;
  title: string;
  objectives: ObjectiveView[];
  foot?: string;
}

export interface MarkerView {
  x: number;
  y: number;
  label: string;
  edge: boolean;
}
export interface TagView {
  x: number;
  y: number;
  text: string;
  icon?: string;
  ready: boolean;
}

export interface Settings {
  master: number;
  music: number;
  sfx: number;
  sensitivity: number;
  invertY: boolean;
  fov: number;
  markers: boolean;
}

export interface WagonCallbacks {
  pack: (c: Commission) => void;
  send: () => void;
  line: string;
  away: boolean;
  eta: number;
}

export interface ShopCallbacks {
  buySeed: (c: CropType, n: number) => void;
  buyUpgrade: (u: UpgradeId) => void;
  sell: (id: ItemId, n: number) => void;
  avail: (c: CropType) => boolean;
}

function fmtTime(s: number): string {
  s = Math.max(0, Math.ceil(s));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

/** Changes whenever anything a panel shows changes. */
function sig(s: GameState): string {
  let k = `${s.coins}|${s.chapter}|${s.wagon.phase}${Math.ceil(s.wagon.t)}|`;
  for (const id of ITEM_IDS) k += `${s.inv[id]},`;
  for (const c of s.commissions) k += `|${c.id}${c.packed ? 1 : 0}`;
  k += `|${s.oven.recipe}${Math.floor(s.oven.t)}${s.oven.ready}|${JSON.stringify(s.upgrades)}`;
  for (const b of Object.keys(s.buildings) as BuildingId[]) k += `${s.buildings[b].built ? 1 : 0}`;
  return k;
}

export class UI {
  readonly root: HTMLElement;
  icons: Record<string, string> = {};
  onTool: ((t: ToolId) => void) | null = null;
  onSeed: ((c: CropType) => void) | null = null;
  /** Called when a modal closes (the game re-locks the pointer). */
  onClose: (() => void) | null = null;
  /** UI clicks, for sound. */
  onClick: (() => void) | null = null;

  private readonly crest: HTMLElement;
  private readonly crestNum: HTMLElement;
  private readonly chapterTitle: HTMLElement;
  private readonly coinEl: HTMLElement;
  private readonly coinWrap: HTMLElement;
  private readonly matsEl: HTMLElement;
  private readonly wheel: HTMLElement;
  private readonly timeEl: HTMLElement;
  private readonly dayEl: HTMLElement;
  private readonly questEl: HTMLElement;
  private readonly reticle: HTMLElement;
  private readonly prompt: HTMLElement;
  private readonly promptMain: HTMLElement;
  private readonly promptDetail: HTMLElement;
  private readonly slots = new Map<ToolId, HTMLElement>();
  private readonly seedBadge: HTMLImageElement;
  private readonly waterGauge: HTMLElement;
  private readonly seedPick: HTMLElement;
  private readonly seedBtns = new Map<CropType, HTMLButtonElement>();
  private readonly satchelGrid: HTMLElement;
  private readonly toasts: HTMLElement;
  private readonly banner: HTMLElement;
  private readonly objDone: HTMLElement;
  private readonly speechEl: HTMLElement;
  private readonly markersEl: HTMLElement;
  private readonly tagsEl: HTMLElement;
  private readonly veil: HTMLElement;
  private readonly panel: HTMLElement;
  private readonly titleEl: HTMLElement;
  private readonly loadingEl: HTMLElement;
  private readonly loadBar: HTMLElement;
  private readonly statsEl: HTMLElement;
  private readonly fadeEl: HTMLElement;
  private readonly hintEl: HTMLElement;
  private lastCoins = -1;
  private lastChapter = -1;
  private lastInv: Partial<Record<ItemId, number>> = {};
  private seedTimer = 0;
  private panelKind: string | null = null;
  private panelRefresh: (() => void) | null = null;
  private panelSig = '';
  private speechTimer = 0;
  private bannerTimer = 0;
  private objTimer = 0;
  private hudHidden = false;
  private curTool: ToolId = 'hoe';
  private readonly markerPool: HTMLElement[] = [];
  private readonly tagPool: HTMLElement[] = [];

  constructor(parent: HTMLElement) {
    this.root = h('div', 'ui');
    parent.append(this.root);
    this.root.addEventListener('click', (e) => {
      const t = e.target as HTMLElement;
      if (t.closest('button')) this.onClick?.();
    });

    // chapter card + coins (top left)
    this.crest = h('div', 'crest');
    this.crest.innerHTML = CREST_SVG;
    this.crestNum = h('b', '', {}, 'I');
    this.crest.append(this.crestNum);
    this.chapterTitle = h('div', 'chapter-title', {}, '');
    this.coinEl = h('span', '', {}, '0');
    this.coinWrap = h('div', 'coins');
    this.coinWrap.innerHTML = COIN_SVG;
    this.coinWrap.append(this.coinEl);
    this.matsEl = h('div', 'mats');
    const kicker = h('div', 'chapter-kicker', {}, 'Chapter');
    kicker.dataset.role = 'kicker';
    this.root.append(h('div', 'favour paper hud-el fade-in-menu', {}, this.crest, h('div', 'favour-text', {}, kicker, this.chapterTitle, h('div', 'mats', {}, this.coinWrap, this.matsEl))));

    // clock
    this.wheel = h('div', 'wheel', {}, h('i', 'sun'), h('i', 'moon'));
    this.timeEl = h('b', '', {}, '9:30');
    this.dayEl = h('span', '', {}, 'Day 1');
    this.root.append(h('div', 'clock paper hud-el fade-in-menu', {}, h('div', 'dial', {}, this.wheel), h('div', 'clock-text', {}, this.timeEl, this.dayEl)));

    // objectives
    this.questEl = h('div', 'orders quests paper hud-el fade-in-menu');
    this.questEl.style.width = '250px';
    this.root.append(this.questEl);

    // world overlays
    this.markersEl = h('div', 'hud-el fade-in-menu');
    this.tagsEl = h('div', 'hud-el fade-in-menu');
    this.root.append(this.tagsEl, this.markersEl);

    // reticle + prompt
    this.reticle = h('div', 'reticle hud-el fade-in-menu');
    this.promptMain = h('div', 'prompt-main');
    this.promptDetail = h('div', 'prompt-detail');
    this.prompt = h('div', 'prompt hud-el fade-in-menu', {}, this.promptMain, this.promptDetail);
    this.hintEl = h('div', 'lookhint', {}, 'Click to look around');
    this.root.append(this.reticle, this.prompt, this.hintEl);

    // tool belt
    const belt = h('div', 'belt six hud-el fade-in-menu');
    this.seedBadge = h('img', '', { alt: '' });
    this.waterGauge = h('i');
    TOOL_ORDER.forEach((t, i) => {
      const s = h('div', 'slot', { 'data-tool': t }, h('span', 'num', {}, String(i + 1)), h('img', '', { alt: TOOL_NAMES[t] }), h('span', 'name', {}, TOOL_NAMES[t]));
      if (t === 'seeds') s.append(h('div', 'badge', {}, this.seedBadge));
      if (t === 'water') s.append(h('div', 'gauge', {}, this.waterGauge));
      s.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        this.onTool?.(t);
      });
      belt.append(s);
      this.slots.set(t, s);
    });
    this.root.append(belt);
    this.seedPick = h('div', 'seedpick paper hud-el fade-in-menu');
    for (const c of CROPS) {
      const b = h('button', '', {}, h('img', '', { alt: '' }), ITEMS[c].name, h('span', 'cnt', {}, '0'));
      b.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        this.onSeed?.(c);
      });
      this.seedPick.append(b);
      this.seedBtns.set(c, b);
    }
    this.seedPick.append(h('span', 'hint', {}, 'Q to switch'));
    this.root.append(this.seedPick);

    // satchel
    this.satchelGrid = h('div', 'satchel-grid');
    this.root.append(h('div', 'satchel paper hud-el fade-in-menu', {}, h('h4', '', {}, 'Satchel'), this.satchelGrid));

    // toasts, banners, speech
    this.toasts = h('div', 'toasts');
    this.banner = h('div', 'levelup');
    this.objDone = h('div', 'objdone paper');
    this.speechEl = h('div', 'speech paper hud-el fade-in-menu');
    this.root.append(this.toasts, this.banner, this.objDone, this.speechEl);

    // modal
    this.veil = h('div', 'veil');
    this.panel = h('div', 'panel paper');
    this.veil.addEventListener('mousedown', () => this.closePanel());
    this.root.append(this.veil, this.panel);

    // title, fade, stats, loading
    this.titleEl = h('div', 'title');
    this.fadeEl = h('div', 'fade');
    this.statsEl = h('div', 'stats');
    this.statsEl.style.display = 'none';
    this.loadBar = h('i');
    this.loadingEl = h('div', 'loading', {}, h('div', 'loading-inner', {}, h('h1', '', {}, 'Aldervale'), h('div', 'bar', {}, this.loadBar), h('div', 'loading-sub', {}, 'Saddling the pony…')));
    this.root.append(this.titleEl, this.statsEl, this.fadeEl, this.loadingEl);
  }

  // ------------------------------------------------------------------ helpers
  icon(id: string): string {
    return this.icons[id] ?? '';
  }
  private img(id: string, cls = ''): HTMLImageElement {
    const i = h('img', cls, { alt: '' });
    const src = this.icon(id);
    if (src) i.src = src;
    return i;
  }
  private coinSpan(n: number | string): HTMLElement {
    const s = h('span', 'price');
    s.style.fontSize = '15px';
    s.innerHTML = COIN_SVG;
    s.append(String(n));
    return s;
  }

  setIcons(icons: Record<string, string>): void {
    this.icons = icons;
    for (const [t, s] of this.slots) {
      const im = s.querySelector('img');
      if (im) im.src = this.icon(`tool_${t}`);
    }
    for (const [c, b] of this.seedBtns) b.querySelector('img')!.src = this.icon(seedOf(c));
  }

  setLoading(f: number): void {
    this.loadBar.style.width = `${Math.round(f * 100)}%`;
  }
  hideLoading(): void {
    this.loadingEl.classList.add('done');
  }
  showError(msg: string): void {
    const sub = this.loadingEl.querySelector('.loading-sub');
    if (sub) sub.textContent = msg;
  }
  setStats(text: string | null): void {
    this.statsEl.style.display = text ? 'block' : 'none';
    if (text) this.statsEl.textContent = text;
  }
  setHudVisible(v: boolean): void {
    this.hudHidden = !v;
    this.root.classList.toggle('hidden', !v);
  }
  get hudVisible(): boolean {
    return !this.hudHidden;
  }
  setLookHint(v: boolean): void {
    this.hintEl.classList.toggle('on', v);
  }
  fade(on: boolean, text = ''): void {
    this.fadeEl.textContent = text;
    this.fadeEl.classList.toggle('on', on);
  }

  // ------------------------------------------------------------------ hud
  setState(s: GameState, chapterTitle: string): void {
    if (s.chapter !== this.lastChapter) {
      if (this.lastChapter > 0) {
        this.crest.classList.remove('bump');
        void this.crest.offsetWidth;
        this.crest.classList.add('bump');
      }
      this.lastChapter = s.chapter;
      this.crestNum.textContent = s.ended ? '★' : ROMAN[s.chapter] ?? String(s.chapter);
      const k = this.root.querySelector('[data-role="kicker"]');
      if (k) k.textContent = s.ended ? STEWARD_RANKS[4]! : `Chapter ${ROMAN[s.chapter] ?? s.chapter}`;
    }
    this.chapterTitle.textContent = s.ended ? 'Brookhollow Farm' : chapterTitle;
    if (s.coins !== this.lastCoins) {
      if (this.lastCoins >= 0 && s.coins > this.lastCoins) {
        this.coinWrap.classList.remove('bump');
        void this.coinWrap.offsetWidth;
        this.coinWrap.classList.add('bump');
      }
      this.lastCoins = s.coins;
      this.coinEl.textContent = s.coins.toLocaleString();
    }
    const mk = `${s.inv.wood},${s.inv.stone},${s.chapter},${this.icon('wood').length}`;
    if (this.matsEl.dataset.k !== mk) {
      this.matsEl.dataset.k = mk;
      this.matsEl.replaceChildren();
      if (s.inv.wood || s.chapter >= 2) this.matsEl.append(h('span', '', { title: 'Wood' }, this.img('wood'), String(s.inv.wood)));
      if (s.inv.stone || s.chapter >= 2) this.matsEl.append(h('span', '', { title: 'Stone' }, this.img('stone'), String(s.inv.stone)));
    }
    for (const [t, el] of this.slots) el.classList.toggle('locked', !s.tools.includes(t));
    this.waterGauge.style.width = `${Math.round((s.water / canCapacity(s)) * 100)}%`;
    this.renderSatchel(s);
    for (const [c, b] of this.seedBtns) {
      const cnt = b.querySelector('.cnt');
      if (cnt) cnt.textContent = String(s.inv[seedOf(c)]);
    }
    if (this.panelRefresh) {
      const k = sig(s);
      if (k !== this.panelSig) {
        this.panelSig = k;
        this.panelRefresh();
      }
    }
  }

  private renderSatchel(s: GameState): void {
    const have = ITEM_IDS.filter((id) => s.inv[id] > 0 && ITEMS[id].kind !== 'seed' && id !== 'wood' && id !== 'stone');
    const key = have.map((id) => `${id}:${s.inv[id]}`).join(',');
    if (this.satchelGrid.dataset.key === key) return;
    this.satchelGrid.dataset.key = key;
    this.satchelGrid.replaceChildren();
    if (!have.length) {
      this.satchelGrid.style.display = 'block';
      this.satchelGrid.append(h('div', 'empty', {}, 'Empty. Harvest a crop to fill it.'));
    } else {
      this.satchelGrid.style.display = '';
      for (const id of have) {
        const it = h('div', 'item', { title: ITEMS[id].name }, this.img(id), h('b', '', {}, String(s.inv[id])));
        if ((this.lastInv[id] ?? 0) < s.inv[id]) it.classList.add('pop');
        this.satchelGrid.append(it);
      }
    }
    for (const id of ITEM_IDS) this.lastInv[id] = s.inv[id];
  }

  setQuest(q: QuestView): void {
    const key = JSON.stringify(q);
    if (this.questEl.dataset.key === key) return;
    this.questEl.dataset.key = key;
    this.questEl.replaceChildren(h('h4', '', {}, q.title));
    for (const o of q.objectives) {
      const row = h('div', `obj ${o.done ? 'done' : ''} ${o.current ? 'current' : ''}`, {}, h('span', 'tick', {}, o.done ? '✓' : ''), h('span', 'text', {}, o.text), o.target > 1 ? h('span', 'n', {}, `${Math.min(o.value, o.target)}/${o.target}`) : h('span'));
      if (o.current && o.hint) row.append(h('span', 'hint', {}, o.hint));
      this.questEl.append(row);
    }
    if (q.foot) this.questEl.append(h('div', 'quest-foot', {}, q.foot));
  }

  setClock(hour: number, day: number, rain: boolean): void {
    const hh = Math.floor(hour);
    const mm = Math.floor(((hour - hh) * 60) / 10) * 10;
    this.timeEl.textContent = `${hh}:${String(mm).padStart(2, '0')}`;
    this.dayEl.textContent = `Day ${day}${rain ? ' · Rain' : ''}`;
    this.wheel.style.transform = `rotate(${((hour - 12) / 24) * 360}deg)`;
  }

  setTool(t: ToolId): void {
    this.curTool = t;
    for (const [k, s] of this.slots) s.classList.toggle('active', k === t);
    if (t === 'seeds') {
      this.seedPick.classList.add('on');
      this.seedTimer = 2.4;
    } else this.seedPick.classList.remove('on');
  }
  setSeed(c: CropType, unlocked: CropType[]): void {
    this.seedBadge.src = this.icon(seedOf(c));
    for (const [k, b] of this.seedBtns) {
      b.classList.toggle('on', k === c);
      b.classList.toggle('locked', !unlocked.includes(k));
      b.style.display = unlocked.includes(k) ? '' : 'none';
    }
    if (this.curTool !== 'seeds') return;
    this.seedPick.classList.add('on');
    this.seedTimer = 2.4;
  }

  setPrompt(p: PromptInfo | null): void {
    this.reticle.classList.toggle('on', !!p);
    this.reticle.classList.toggle('bad', !!p && !p.ok);
    if (!p) {
      this.prompt.classList.remove('on');
      return;
    }
    const k = `${p.key}|${p.verb}|${p.label ?? ''}|${p.detail ?? ''}|${p.ok}`;
    if (this.prompt.dataset.sig !== k) {
      this.prompt.dataset.sig = k;
      const key = h('span', `key ${p.key === 'LMB' ? 'mouse' : ''}`);
      if (p.key === 'LMB') key.innerHTML = MOUSE_SVG;
      else key.textContent = p.key;
      this.promptMain.replaceChildren(...(p.ok ? [key] : []), `${p.verb}${p.label ? ` ${p.label}` : ''}`);
      this.promptDetail.textContent = p.detail ?? '';
      this.promptDetail.style.display = p.detail ? '' : 'none';
    }
    this.prompt.classList.toggle('bad', !p.ok);
    this.prompt.classList.add('on');
  }

  setMarkers(list: MarkerView[]): void {
    while (this.markerPool.length < list.length) {
      const m = h('div', 'marker', {}, h('div', 'gem'), h('div', 'lbl'));
      this.markersEl.append(m);
      this.markerPool.push(m);
    }
    this.markerPool.forEach((m, i) => {
      const v = list[i];
      if (!v) {
        m.style.display = 'none';
        return;
      }
      m.style.display = '';
      m.style.left = `${v.x}px`;
      m.style.top = `${v.y}px`;
      m.classList.toggle('edge', v.edge);
      const l = m.lastElementChild as HTMLElement;
      if (l.textContent !== v.label) l.textContent = v.label;
    });
  }

  setTags(list: TagView[]): void {
    while (this.tagPool.length < list.length) {
      const t = h('div', 'tag paper', {}, h('img', '', { alt: '' }), h('span'));
      this.tagsEl.append(t);
      this.tagPool.push(t);
    }
    this.tagPool.forEach((t, i) => {
      const v = list[i];
      if (!v) {
        t.style.display = 'none';
        return;
      }
      t.style.display = '';
      t.style.left = `${v.x}px`;
      t.style.top = `${v.y}px`;
      t.classList.toggle('ready', v.ready);
      const im = t.firstElementChild as HTMLImageElement;
      const src = v.icon ? this.icon(v.icon) : '';
      if (im.getAttribute('src') !== src) {
        if (src) im.src = src;
        else im.removeAttribute('src');
      }
      im.style.display = src ? '' : 'none';
      const sp = t.lastElementChild as HTMLElement;
      if (sp.textContent !== v.text) sp.textContent = v.text;
    });
  }

  toast(text: string, icon?: string): void {
    const t = h('div', 'toast paper', {}, icon ? this.img(icon) : null, text);
    this.toasts.append(t);
    while (this.toasts.children.length > 3) this.toasts.firstElementChild?.remove();
    setTimeout(() => t.classList.add('out'), 2600);
    setTimeout(() => t.remove(), 3200);
  }

  float(text: string, x: number, y: number, icon?: string): void {
    const f = h('div', 'float', {}, icon ? this.img(icon) : null, text);
    f.style.left = `${x}px`;
    f.style.top = `${y}px`;
    this.root.append(f);
    setTimeout(() => f.remove(), 1400);
  }

  objective(text: string): void {
    this.objDone.replaceChildren(h('span', 'tick', {}, '✓'), text);
    this.objDone.classList.add('on');
    this.objTimer = 2.6;
  }

  chapterBanner(n: number, title: string): void {
    this.banner.replaceChildren(h('div', 'ribbon', {}, h('small', '', {}, `Chapter ${ROMAN[n] ?? n}`), title));
    this.banner.classList.add('on');
    this.bannerTimer = 4;
  }
  bannerText(kicker: string, title: string, sub?: string[]): void {
    this.banner.replaceChildren(h('div', 'ribbon', {}, h('small', '', {}, kicker), title));
    if (sub?.length) this.banner.append(h('div', '', {}, h('div', 'unlocks paper', {}, ...sub.map((u) => h('span', '', {}, u)))));
    this.banner.classList.add('on');
    this.bannerTimer = 4.2;
  }

  speech(name: string, text: string, secs = 4): void {
    this.speechEl.replaceChildren(h('b', '', {}, name), text);
    this.speechEl.classList.add('on');
    this.speechTimer = secs;
  }
  placeSpeech(x: number, y: number, visible: boolean): void {
    this.speechEl.style.left = `${x}px`;
    this.speechEl.style.top = `${y}px`;
    this.speechEl.style.opacity = visible ? '' : '0';
  }

  update(dt: number): void {
    if (this.seedTimer > 0) {
      this.seedTimer -= dt;
      if (this.seedTimer <= 0) this.seedPick.classList.remove('on');
    }
    if (this.speechTimer > 0) {
      this.speechTimer -= dt;
      if (this.speechTimer <= 0) this.speechEl.classList.remove('on');
    }
    if (this.bannerTimer > 0) {
      this.bannerTimer -= dt;
      if (this.bannerTimer <= 0) this.banner.classList.remove('on');
    }
    if (this.objTimer > 0) {
      this.objTimer -= dt;
      if (this.objTimer <= 0) this.objDone.classList.remove('on');
    }
  }

  // ------------------------------------------------------------------ modal panels
  get panelOpen(): boolean {
    return this.panelKind !== null;
  }
  get panelName(): string | null {
    return this.panelKind;
  }

  private openPanel(kind: string, narrow: boolean, build: () => Node[], refresh = true): void {
    this.panelKind = kind;
    this.panel.classList.toggle('narrow', narrow);
    const render = (): void => {
      const top = this.panel.querySelector('.rows')?.scrollTop ?? 0;
      this.panel.replaceChildren(...build());
      const rows = this.panel.querySelector('.rows');
      if (rows) rows.scrollTop = top;
    };
    this.panelSig = '';
    render();
    this.panelRefresh = refresh ? render : null;
    this.veil.classList.add('on');
    this.panel.classList.add('on');
    this.root.classList.add('in-menu');
  }

  /** Re-render the open panel now (after a click changed something). */
  refreshPanel(): void {
    this.panelSig = '';
    this.panelRefresh?.();
  }

  closePanel(): void {
    if (!this.panelKind) return;
    this.panelKind = null;
    this.panelRefresh = null;
    this.veil.classList.remove('on');
    this.panel.classList.remove('on');
    this.root.classList.remove('in-menu');
    this.onClose?.();
  }

  private head(title: string, sub: string, crest = true): HTMLElement {
    const close = h('button', 'close', { 'aria-label': 'Close' }, '✕');
    close.addEventListener('click', () => this.closePanel());
    const c = crest ? h('div', 'crest') : null;
    if (c) c.innerHTML = CREST_SVG;
    return h('div', 'panel-head', {}, c, h('div', '', {}, h('h2', '', {}, title), h('p', '', {}, sub)), close);
  }

  private needLine(s: GameState, item: ItemId, qty: number): HTMLElement {
    const n = s.inv[item];
    return h('div', 'line', {}, this.img(item), `${qty} × ${qty > 1 ? ITEMS[item].plural : ITEMS[item].name}`, h('span', `have ${n >= qty ? 'ok' : ''}`, {}, `${Math.min(n, qty)}/${qty}`));
  }

  openLetter(id: string, onDone?: () => void): void {
    const L: Letter | undefined = LETTERS[id];
    if (!L) return;
    this.openPanel(
      `letter:${id}`,
      false,
      () => {
        const ok = h('button', 'btn royal', {}, 'Fold the letter');
        ok.addEventListener('click', () => {
          this.closePanel();
          onDone?.();
        });
        return [h('div', 'letter', {}, h('div', 'seal', {}, 'A'), h('h2', '', {}, L.title), h('div', 'from', {}, L.from), ...L.body.map((p) => h('p', '', {}, p)), h('div', 'sign', {}, `— ${L.sign}`), h('div', 'letter-actions', {}, ok))];
      },
      false,
    );
    this.panel.style.width = 'min(640px, calc(100vw - 40px))';
  }

  openWagon(s: GameState, cb: WagonCallbacks): void {
    this.panel.style.width = '';
    this.openPanel('wagon', false, () => {
      const out: Node[] = [this.head('The Royal Wagon', 'Pack commissions into the crate, then send Pip up the hill to the castle.')];
      out.push(h('div', 'pip-line', {}, h('b', '', {}, 'Pip'), cb.line));
      const notes = h('div', 'notes');
      const tilts = ['-1deg', '0.7deg', '-0.4deg', '1deg'];
      s.commissions.forEach((c, i) => {
        const lines = h('div', 'lines');
        for (const l of c.lines) lines.append(this.needLine(s, l.item, l.qty));
        const can = !c.packed && !cb.away && c.lines.every((l) => s.inv[l.item] >= l.qty);
        const btn = h('button', `btn ${c.story ? 'gold' : 'royal'}`, can ? {} : { disabled: '' }, c.packed ? 'Packed ✓' : 'Pack it');
        btn.addEventListener('click', () => {
          cb.pack(c);
          this.refreshPanel();
        });
        notes.append(
          h(
            'div',
            `note ${c.story ? 'story' : ''} ${c.packed ? 'packed' : ''}`,
            { style: `--tilt:${tilts[i % tilts.length]}` },
            h('div', 'from', {}, c.from),
            h('div', 'title', {}, c.title),
            h('div', 'ask', {}, c.note),
            lines,
            h('div', 'reward', {}, this.coinSpan(c.coins), c.story ? h('span', 'fav', {}, 'Story') : null),
            h('div', 'note-actions', {}, h('span'), btn),
          ),
        );
      });
      if (!s.commissions.length) notes.append(h('div', 'note waiting', {}, 'No commissions just now. Pip will bring more from the castle.'));
      out.push(notes);
      const packed = s.commissions.filter((c) => c.packed).length;
      const send = h('button', 'btn gold', packed && !cb.away ? {} : { disabled: '' }, cb.away ? `On the road · back in ${fmtTime(cb.eta)}` : packed ? `Send Pip up the hill (${packed} crate${packed > 1 ? 's' : ''})` : 'Pack a commission first');
      send.addEventListener('click', () => {
        cb.send();
        this.closePanel();
      });
      out.push(h('div', 'wagon-foot', {}, 'Coins are paid as you pack. The wagon brings back new commissions — and letters.', send));
      return out;
    });
  }

  openShop(s: GameState, cb: ShopCallbacks, tab: 'seeds' | 'tools' | 'sell' = 'seeds'): void {
    this.panel.style.width = '';
    let cur = tab;
    this.openPanel('shop', false, () => {
      const tabs = h('div', 'tabs');
      for (const [id, label] of [
        ['seeds', 'Seeds'],
        ['tools', 'Tools & trinkets'],
        ['sell', 'Sell'],
      ] as const) {
        const b = h('button', cur === id ? 'on' : '', {}, label);
        b.addEventListener('click', () => {
          cur = id;
          this.refreshPanel();
        });
        tabs.append(b);
      }
      const coins = h('div', 'shop-coins');
      coins.innerHTML = COIN_SVG;
      coins.append(String(s.coins));
      tabs.append(coins);
      const rows = h('div', 'rows');
      if (cur === 'seeds') {
        for (const c of CROPS) {
          if (!cb.avail(c)) continue;
          const locked = s.chapter < SEED_CHAPTER[c];
          const price = SEED_PRICE[c];
          const btns = h('div', 'btns');
          for (const n of [1, 5, 10]) {
            const b = h('button', 'btn small', !locked && s.coins >= price * n ? {} : { disabled: '' }, `×${n} · ${price * n}`);
            b.addEventListener('click', () => {
              cb.buySeed(c, n);
              this.refreshPanel();
            });
            btns.append(b);
          }
          rows.append(h('div', `row ${locked ? 'locked' : ''}`, {}, this.img(seedOf(c)), h('div', 'grow', {}, h('div', 'rname', {}, `${ITEMS[c].name} seeds`), h('div', 'rsub', {}, locked ? `Wren gets these in chapter ${SEED_CHAPTER[c]}` : `${price} coin${price > 1 ? 's' : ''} each · you have ${s.inv[seedOf(c)]}`)), btns));
        }
      } else if (cur === 'tools') {
        for (const u of UPGRADES) {
          const owned = !!s.upgrades[u.id];
          const locked = s.chapter < u.chapter;
          const btn = owned ? h('span', 'owned', {}, 'Owned ✓') : h('button', 'btn gold small', !locked && s.coins >= u.cost ? {} : { disabled: '' }, locked ? `Chapter ${u.chapter}` : `Buy · ${u.cost}`);
          if (!owned)
            btn.addEventListener('click', () => {
              cb.buyUpgrade(u.id);
              this.refreshPanel();
            });
          rows.append(h('div', `row ${locked ? 'locked' : ''}`, {}, this.img(u.id === 'can' ? 'tool_water' : u.id === 'hoe' ? 'tool_hoe' : u.id === 'basket' ? 'tool_harvest' : 'tool_axe'), h('div', 'grow', {}, h('div', 'rname', {}, u.name), h('div', 'rsub', {}, u.blurb)), btn));
        }
      } else {
        const ids = ITEM_IDS.filter((id) => ITEMS[id].sell > 0 && s.inv[id] > 0);
        if (!ids.length) rows.append(h('div', 'row', {}, h('div', 'grow', {}, h('div', 'rsub', {}, 'Nothing to sell yet. Wren buys crops, goods, timber and stone.'))));
        for (const id of ids) {
          const btns = h('div', 'btns');
          const one = h('button', 'btn small', {}, `Sell 1 · ${ITEMS[id].sell}`);
          one.addEventListener('click', () => {
            cb.sell(id, 1);
            this.refreshPanel();
          });
          const all = h('button', 'btn royal small', {}, `All ${s.inv[id]} · ${ITEMS[id].sell * s.inv[id]}`);
          all.addEventListener('click', () => {
            cb.sell(id, s.inv[id]);
            this.refreshPanel();
          });
          btns.append(one, all);
          rows.append(h('div', 'row', {}, this.img(id), h('div', 'grow', {}, h('div', 'rname', {}, ITEMS[id].name), h('div', 'rsub', {}, `You have ${s.inv[id]}`)), btns));
        }
      }
      return [this.head('Wren’s Wagon Stall', 'Seeds from all over the valley, tools that make light work, and a fair price for your surplus.', false), tabs, rows];
    });
  }

  openOven(s: GameState, onBake: (i: number) => void, onTake: () => void): void {
    this.panel.style.width = '';
    this.openPanel('oven', true, () => {
      const out: Node[] = [this.head('The Bakehouse Oven', 'One dish at a time, the old way. Keep the fire fed.', false)];
      if (s.oven.ready) {
        const take = h('button', 'btn gold', {}, `Take the ${ITEMS[s.oven.ready].name}`);
        take.addEventListener('click', () => {
          onTake();
          this.refreshPanel();
        });
        out.push(h('div', 'row', {}, this.img(s.oven.ready), h('div', 'grow', {}, h('div', 'rname', {}, `${ITEMS[s.oven.ready].name} is ready`)), take));
      } else if (s.oven.recipe !== null) {
        const r = OVEN_RECIPES[s.oven.recipe]!;
        out.push(h('div', 'row', {}, this.img(r.out), h('div', 'grow', {}, h('div', 'rname', {}, `Baking ${ITEMS[r.out].name}`), h('div', 'rsub', {}, `${fmtTime(r.time - s.oven.t)} to go`))));
      }
      const rows = h('div', 'rows');
      OVEN_RECIPES.forEach((r, i) => {
        const locked = s.chapter < r.chapter;
        const needs = h('div', 'needs');
        let can = !locked && s.oven.recipe === null && !s.oven.ready;
        for (const k of Object.keys(r.needs) as ItemId[]) {
          const want = r.needs[k] ?? 0;
          const ok = s.inv[k] >= want;
          if (!ok) can = false;
          needs.append(h('span', ok ? 'ok' : '', {}, this.img(k), `${s.inv[k]}/${want}`));
        }
        const b = h('button', 'btn small', can ? {} : { disabled: '' }, locked ? `Chapter ${r.chapter}` : `Bake · ${fmtTime(r.time)}`);
        b.addEventListener('click', () => {
          onBake(i);
          this.refreshPanel();
        });
        rows.append(h('div', `recipe ${locked ? 'locked' : ''}`, {}, this.img(r.out), h('div', '', {}, h('div', 'rname', {}, ITEMS[r.out].name), needs), h('span', 'rtime'), b));
      });
      out.push(rows);
      return out;
    });
  }

  openBuild(id: BuildingId, s: GameState, onBuild: () => void): void {
    this.panel.style.width = '';
    const def = BUILDINGS[id];
    this.openPanel(`build:${id}`, true, () => {
      const chk = canBuild(s, id);
      const cost = h('div', 'lines');
      cost.append(h('div', 'line', {}, h('span', 'coins', {}, ''), `${def.coins} coins`, h('span', `have ${s.coins >= def.coins ? 'ok' : ''}`, {}, `${Math.min(s.coins, def.coins)}/${def.coins}`)));
      const c0 = cost.lastElementChild!.firstElementChild as HTMLElement;
      c0.innerHTML = COIN_SVG;
      cost.append(this.needLine(s, 'wood', def.wood), this.needLine(s, 'stone', def.stone));
      const btn = h('button', 'btn gold', chk.ok ? {} : { disabled: '' }, 'Raise it');
      btn.addEventListener('click', () => onBuild());
      return [this.head(`Raise the ${def.name}`, def.blurb, false), h('div', 'buildcard', {}, this.img(`bld_${id}`), h('div', 'facts', {}, cost, h('div', `req ${chk.ok ? 'ok' : ''}`, {}, chk.ok ? 'Everything is ready ✓' : chk.why))), h('div', 'panel-foot', {}, btn)];
    });
  }

  openJournal(s: GameState, quest: QuestView, onLetter: (id: string) => void): void {
    this.panel.style.width = '';
    this.openPanel('journal', false, () => {
      const left = h('div', '', {}, h('h3', '', {}, s.ended ? 'The Steward’s Year' : `Chapter ${ROMAN[quest.chapter] ?? quest.chapter} · ${quest.title}`));
      for (const o of quest.objectives) left.append(h('div', `obj ${o.done ? 'done' : ''} ${o.current ? 'current' : ''}`, {}, h('span', 'tick', {}, o.done ? '✓' : ''), h('span', 'text', {}, o.text), o.target > 1 ? h('span', 'n', {}, `${Math.min(o.value, o.target)}/${o.target}`) : h('span')));
      const ledger = h('div', 'ledger', {}, 'Days on the farm', h('b', '', {}, String(s.stats.days)), 'Crops harvested', h('b', '', {}, String(s.stats.harvested)), 'Crates sent to the castle', h('b', '', {}, String(s.stats.delivered)), 'Coins earned', h('b', '', {}, String(s.stats.earned)));
      left.append(ledger);
      const list = h('div', 'letter-list');
      for (const id of [...s.letters].reverse()) {
        const L = LETTERS[id];
        if (!L) continue;
        const b = h('button', '', {}, L.title, h('small', '', {}, L.from));
        b.addEventListener('click', () => onLetter(id));
        list.append(b);
      }
      return [this.head('The Steward’s Journal', 'Your chapter, your ledger, and every letter the castle has sent.'), h('div', 'journal', {}, left, h('div', '', {}, h('h3', '', {}, 'Letters'), list))];
    });
  }

  openSettings(st: Settings, onChange: (s: Settings) => void, onBack?: () => void): void {
    this.panel.style.width = '';
    this.openPanel(
      'settings',
      true,
      () => {
        const grid = h('div', 'settings');
        const slider = (label: string, key: 'master' | 'music' | 'sfx' | 'sensitivity' | 'fov', min: number, max: number, step: number): void => {
          const inp = h('input', '', { type: 'range', min: String(min), max: String(max), step: String(step), value: String(st[key]) });
          inp.addEventListener('input', () => {
            st[key] = Number(inp.value);
            onChange(st);
          });
          grid.append(h('span', '', {}, label), inp);
        };
        const check = (label: string, key: 'invertY' | 'markers'): void => {
          const inp = h('input', '', { type: 'checkbox' });
          inp.checked = st[key];
          inp.addEventListener('change', () => {
            st[key] = inp.checked;
            onChange(st);
          });
          grid.append(h('span', '', {}, label), inp);
        };
        slider('Master volume', 'master', 0, 1, 0.05);
        slider('Music', 'music', 0, 1, 0.05);
        slider('Effects & ambience', 'sfx', 0, 1, 0.05);
        slider('Mouse sensitivity', 'sensitivity', 0.4, 2.5, 0.05);
        slider('Field of view', 'fov', 55, 90, 1);
        check('Invert mouse Y', 'invertY');
        check('Show objective markers', 'markers');
        const done = h('button', 'btn royal', {}, 'Done');
        done.addEventListener('click', () => {
          this.closePanel();
          onBack?.();
        });
        return [this.head('Settings', 'Saved on this computer.', false), grid, h('div', 'panel-foot', {}, done)];
      },
      false,
    );
  }

  openEnding(s: GameState, onContinue: () => void): void {
    this.panel.style.width = 'min(680px, calc(100vw - 40px))';
    this.openPanel(
      'ending',
      false,
      () => {
        const cont = h('button', 'btn gold', {}, 'Keep farming');
        cont.addEventListener('click', () => {
          this.closePanel();
          onContinue();
        });
        return [
          h(
            'div',
            'ending',
            {},
            h('div', 'ribbon', {}, h('small', '', {}, 'The End of the Steward’s Year'), 'Royal Steward of Aldervale'),
            h('p', '', {}, 'The Harvest Feast was the finest the valley had seen in a generation, and every loaf, pie and jug on the King’s tables came from Brookhollow.'),
            h('p', '', {}, `${s.stats.days} days · ${s.stats.harvested} crops harvested · ${s.stats.delivered} crates sent · ${s.stats.earned} coins earned`),
            h('p', '', {}, 'The castle will keep sending commissions, Wren will keep her cart at the crossroads, and Pip will keep the pony fed. The farm is yours.'),
            h('div', 'credits', {}, 'Aldervale · made with Three.js and models built in Blender'),
            h('div', 'panel-foot', {}, cont),
          ),
        ];
      },
      false,
    );
  }

  // ------------------------------------------------------------------ title / pause
  showTitle(mode: 'new' | 'continue' | 'pause', onStart: () => void, onReset: (() => void) | null, onSettings: (() => void) | null): void {
    const begin = h('button', 'btn gold', {}, mode === 'pause' ? 'Resume' : mode === 'continue' ? 'Continue' : 'Begin');
    begin.addEventListener('click', () => onStart());
    const set = onSettings ? h('button', 'btn royal', {}, 'Settings') : null;
    set?.addEventListener('click', () => onSettings?.());
    const reset = onReset ? h('button', 'link', {}, mode === 'pause' ? 'Start over' : 'New farm') : null;
    reset?.addEventListener('click', () => {
      if (reset.dataset.armed) onReset?.();
      else {
        reset.dataset.armed = '1';
        reset.textContent = 'Click again to clear your farm';
      }
    });
    const k = (...keys: string[]): HTMLElement => h('div', 'keys', {}, ...keys.map((x) => h('span', 'key', {}, x)));
    this.titleEl.replaceChildren(
      h(
        'div',
        'title-inner',
        {},
        h('div', 'title-kicker', {}, mode === 'pause' ? 'Paused' : 'A steward’s year'),
        h('h1', '', {}, 'Aldervale', h('em', '', {}, 'Brookhollow Farm')),
        h('p', '', {}, 'The Crown has given you the wild old homestead below Aldervale Castle. Clear the land, raise a mill, keep hens, bake for the castle — and by harvest-tide, supply the first Harvest Feast in a generation.'),
        h('div', 'row', {}, begin, set, reset),
        h('div', 'controls', {}, k('W', 'A', 'S', 'D'), 'Walk · Shift run · Space jump', k('1', '–', '6'), 'Hoe, seeds, can, basket, axe, pick · Q seed', k('Click'), 'Use the tool on what you look at', k('E'), 'Talk, open, pack, do the sensible thing', k('J'), 'Journal · M music · Esc pause'),
      ),
    );
    this.titleEl.classList.add('on');
    this.root.classList.add('in-menu');
  }
  hideTitle(): void {
    this.titleEl.classList.remove('on');
    if (!this.panelKind) this.root.classList.remove('in-menu');
  }
  get titleOpen(): boolean {
    return this.titleEl.classList.contains('on');
  }
}
