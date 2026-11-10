import '@fontsource-variable/fraunces';
import '@fontsource-variable/nunito';
import './ui.css';
import type { CropType } from '../world/field';
import {
  BUILDINGS,
  ITEMS,
  ITEM_IDS,
  LEVEL_XP,
  canFill,
  levelFor,
  levelProgress,
  type BuildingId,
  type EconomyState,
  type ExpansionDef,
  type ItemId,
  type Order,
} from '../game/economy';
import type { ToolId } from '../game/viewmodel';

type Attrs = Record<string, string>;
function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', attrs: Attrs = {}, ...kids: (Node | string | null)[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k in attrs) e.setAttribute(k, attrs[k]!);
  for (const c of kids) if (c !== null) e.append(c);
  return e;
}

const CREST_SVG = `<svg viewBox="0 0 50 56"><defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3f5fb0"/><stop offset=".6" stop-color="#2b4486"/><stop offset="1" stop-color="#1c2d5e"/></linearGradient><linearGradient id="cgd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d27a"/><stop offset="1" stop-color="#b8862b"/></linearGradient></defs><path d="M25 2 L46 8 V27 C46 41 36 50 25 54 C14 50 4 41 4 27 V8 Z" fill="url(#cgd)"/><path d="M25 6 L42.5 11 V27 C42.5 39 34 47 25 50.5 C16 47 7.5 39 7.5 27 V11 Z" fill="url(#cg)"/><path d="M14 13 l3 4 3-5 2.5 5 2.5-5 2.5 5 2.5-5 3 5 3-4 -1.5 7 h-19 z" fill="#f6d27a" opacity=".22"/></svg>`;
const COIN_SVG = `<svg class="coin-ico" viewBox="0 0 20 20"><defs><radialGradient id="cn" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#fff1b8"/><stop offset=".5" stop-color="#f2c14e"/><stop offset="1" stop-color="#b07a1c"/></radialGradient></defs><circle cx="10" cy="10" r="9" fill="url(#cn)" stroke="#8a5d12" stroke-width="1"/><circle cx="10" cy="10" r="6" fill="none" stroke="#a87418" stroke-width="1" opacity=".7"/><path d="M7 7.5l1.5 2 1.5-2.5 1.5 2.5 1.5-2-0.8 4.5h-4.4z" fill="#a87418" opacity=".8"/></svg>`;
const FAV_SVG = `<svg viewBox="0 0 50 56"><path d="M25 2 L46 8 V27 C46 41 36 50 25 54 C14 50 4 41 4 27 V8 Z" fill="#2b4486"/><path d="M25 8 L41 12.5 V27 C41 37 33 45 25 48.5 C17 45 9 37 9 27 V12.5 Z" fill="#d8a63f"/></svg>`;
const MOUSE_SVG = `<svg viewBox="0 0 13 17"><rect x=".75" y=".75" width="11.5" height="15.5" rx="5.75" fill="none" stroke="#2f2519" stroke-width="1.5"/><path d="M1.5 6.5 H6.5 V1.2 A5.4 5.4 0 0 0 1.5 6.5Z" fill="#2f2519"/></svg>`;

const TOOL_NAMES: Record<ToolId, string> = { hoe: 'Hoe', seeds: 'Seeds', water: 'Watering Can', harvest: 'Basket' };
const TOOL_ORDER: ToolId[] = ['hoe', 'seeds', 'water', 'harvest'];

export interface PromptInfo {
  key: 'E' | 'LMB';
  verb: string;
  label?: string;
  detail?: string;
  ok: boolean;
}

/** Changes whenever anything a panel shows changes (cheap enough to run every frame). */
function econSig(s: EconomyState): string {
  let k = `${s.coins}|${s.xp}|`;
  for (const id of ITEM_IDS) k += `${s.inv[id]},`;
  for (const o of s.orders) k += `|${o.id}:${Math.ceil(o.wait)}`;
  for (const b of Object.keys(s.buildings) as BuildingId[]) {
    const st = s.buildings[b];
    k += `|${b}${st.built ? 1 : 0}${st.ready.length}:${st.queue.map((j) => `${j.recipe}.${Math.floor(j.t)}`).join('.')}`;
  }
  return k;
}

function fmtTime(s: number): string {
  s = Math.max(0, Math.ceil(s));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

export class UI {
  readonly root: HTMLElement;
  icons: Record<string, string> = {};
  onTool: ((t: ToolId) => void) | null = null;
  onSeed: ((c: CropType) => void) | null = null;
  /** Called when a modal closes (the game re-locks the pointer). */
  onClose: (() => void) | null = null;

  private readonly crest: HTMLElement;
  private readonly crestNum: HTMLElement;
  private readonly favBar: HTMLElement;
  private readonly favLabel: HTMLElement;
  private readonly coinEl: HTMLElement;
  private readonly coinWrap: HTMLElement;
  private readonly wheel: HTMLElement;
  private readonly timeEl: HTMLElement;
  private readonly dayEl: HTMLElement;
  private readonly reticle: HTMLElement;
  private readonly prompt: HTMLElement;
  private readonly promptMain: HTMLElement;
  private readonly promptDetail: HTMLElement;
  private readonly slots = new Map<ToolId, HTMLElement>();
  private readonly seedBadge: HTMLImageElement;
  private readonly waterGauge: HTMLElement;
  private readonly seedPick: HTMLElement;
  private readonly seedBtns = new Map<CropType, HTMLButtonElement>();
  private readonly satchel: HTMLElement;
  private readonly satchelGrid: HTMLElement;
  private readonly ordersEl: HTMLElement;
  private readonly toasts: HTMLElement;
  private readonly levelEl: HTMLElement;
  private readonly speechEl: HTMLElement;
  private readonly veil: HTMLElement;
  private readonly panel: HTMLElement;
  private readonly titleEl: HTMLElement;
  private readonly loadingEl: HTMLElement;
  private readonly loadBar: HTMLElement;
  private readonly statsEl: HTMLElement;
  private lastCoins = -1;
  private lastLevel = -1;
  private lastInv: Partial<Record<ItemId, number>> = {};
  private seedTimer = 0;
  private panelKind: string | null = null;
  private panelRefresh: (() => void) | null = null;
  private speechTimer = 0;
  private levelTimer = 0;
  private hudHidden = false;

  constructor(parent: HTMLElement) {
    this.root = h('div', 'ui');
    parent.append(this.root);

    // favour + coins
    this.crest = h('div', 'crest');
    this.crest.innerHTML = CREST_SVG;
    this.crestNum = h('b', '', {}, '1');
    this.crest.append(this.crestNum);
    this.favLabel = h('small', '', {}, '');
    this.favBar = h('i');
    this.coinEl = h('span', '', {}, '0');
    this.coinWrap = h('div', 'coins');
    this.coinWrap.innerHTML = COIN_SVG;
    this.coinWrap.append(this.coinEl);
    this.root.append(
      h('div', 'favour paper hud-el fade-in-menu', {}, this.crest, h('div', 'favour-text', {}, h('div', 'favour-title', {}, 'Royal Favour', this.favLabel), h('div', 'bar', {}, this.favBar), this.coinWrap)),
    );

    // clock
    this.wheel = h('div', 'wheel', {}, h('i', 'sun'), h('i', 'moon'));
    this.timeEl = h('b', '', {}, '17:00');
    this.dayEl = h('span', '', {}, 'Day 1');
    this.root.append(h('div', 'clock paper hud-el fade-in-menu', {}, h('div', 'dial', {}, this.wheel), h('div', 'clock-text', {}, this.timeEl, this.dayEl)));

    // orders tracker
    this.ordersEl = h('div', 'orders paper hud-el fade-in-menu');
    this.root.append(this.ordersEl);

    // reticle + prompt
    this.reticle = h('div', 'reticle hud-el fade-in-menu');
    this.promptMain = h('div', 'prompt-main');
    this.promptDetail = h('div', 'prompt-detail');
    this.prompt = h('div', 'prompt hud-el fade-in-menu', {}, this.promptMain, this.promptDetail);
    this.root.append(this.reticle, this.prompt);

    // tool belt
    const belt = h('div', 'belt hud-el fade-in-menu');
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
    for (const c of ['wheat', 'tomato', 'pumpkin'] as CropType[]) {
      const b = h('button', '', {}, h('img', '', { alt: '' }), ITEMS[c].name);
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
    this.satchel = h('div', 'satchel paper hud-el fade-in-menu', {}, h('h4', '', {}, 'Satchel'), this.satchelGrid);
    this.root.append(this.satchel);

    // toasts, level banner, speech
    this.toasts = h('div', 'toasts');
    this.levelEl = h('div', 'levelup');
    this.speechEl = h('div', 'speech paper hud-el fade-in-menu');
    this.root.append(this.toasts, this.levelEl, this.speechEl);

    // modal
    this.veil = h('div', 'veil');
    this.panel = h('div', 'panel paper');
    this.veil.addEventListener('mousedown', () => this.closePanel());
    this.root.append(this.veil, this.panel);

    // title
    this.titleEl = h('div', 'title');
    this.root.append(this.titleEl);

    this.statsEl = h('div', 'stats');
    this.statsEl.style.display = 'none';
    this.root.append(this.statsEl);

    // loading
    this.loadBar = h('i');
    this.loadingEl = h('div', 'loading', {}, h('div', 'loading-inner', {}, h('h1', '', {}, 'Aldervale'), h('div', 'bar', {}, this.loadBar), h('div', 'loading-sub', {}, 'Saddling the courier…')));
    this.root.append(this.loadingEl);
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

  setIcons(icons: Record<string, string>): void {
    this.icons = icons;
    for (const [t, s] of this.slots) {
      const im = s.querySelector('img');
      if (im) im.src = this.icon(`tool_${t}`);
    }
    for (const [c, b] of this.seedBtns) b.querySelector('img')!.src = this.icon(c);
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

  // ------------------------------------------------------------------ hud
  setEconomy(s: EconomyState): void {
    const lvl = levelFor(s.xp);
    if (lvl !== this.lastLevel) {
      if (this.lastLevel > 0) {
        this.crest.classList.remove('bump');
        void this.crest.offsetWidth;
        this.crest.classList.add('bump');
      }
      this.lastLevel = lvl;
      this.crestNum.textContent = String(lvl);
    }
    const next = LEVEL_XP[lvl];
    this.favLabel.textContent = next !== undefined ? `${s.xp} / ${next}` : `${s.xp}`;
    this.favBar.style.width = `${Math.round(levelProgress(s.xp) * 100)}%`;
    if (s.coins !== this.lastCoins) {
      if (this.lastCoins >= 0 && s.coins > this.lastCoins) {
        this.coinWrap.classList.remove('bump');
        void this.coinWrap.offsetWidth;
        this.coinWrap.classList.add('bump');
      }
      this.lastCoins = s.coins;
      this.coinEl.textContent = s.coins.toLocaleString();
    }
    this.renderSatchel(s);
    this.renderTracker(s);
    if (this.panelRefresh) {
      const sig = econSig(s);
      if (sig !== this.panelSig) {
        this.panelSig = sig;
        this.panelRefresh();
      }
    }
  }
  private panelSig = '';

  private renderSatchel(s: EconomyState): void {
    const have = ITEM_IDS.filter((id) => s.inv[id] > 0);
    const key = have.map((id) => `${id}:${s.inv[id]}`).join(',');
    if (this.satchelGrid.dataset.key === key) return;
    this.satchelGrid.dataset.key = key;
    this.satchelGrid.replaceChildren();
    if (!have.length) {
      this.satchelGrid.style.display = 'block';
      this.satchelGrid.append(h('div', 'empty', {}, 'Empty. Harvest crops to fill it.'));
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

  private renderTracker(s: EconomyState): void {
    const parts: string[] = [];
    for (const o of s.orders) parts.push(o.wait > 0 ? `w${Math.ceil(o.wait / 5)}` : `${o.id}:${o.lines.map((l) => `${l.item}${Math.min(s.inv[l.item], l.qty)}`).join(',')}`);
    const key = parts.join('|');
    if (this.ordersEl.dataset.key === key) return;
    this.ordersEl.dataset.key = key;
    const ready = s.orders.filter((o) => canFill(s, o)).length;
    this.ordersEl.replaceChildren(h('h4', '', {}, 'Requisitions', h('small', '', {}, ready ? `${ready} ready` : 'at the board')));
    for (const o of s.orders) {
      if (o.wait > 0) {
        this.ordersEl.append(h('div', 'track waiting', {}, 'A new request is on its way…'));
        continue;
      }
      const lines = h('div', 'track-lines');
      for (const l of o.lines) {
        const n = s.inv[l.item];
        lines.append(h('span', `tl ${n >= l.qty ? 'done' : ''}`, {}, this.img(l.item), `${Math.min(n, l.qty)}/${l.qty}`));
      }
      this.ordersEl.append(h('div', 'track', {}, h('div', 'track-from', {}, o.from, canFill(s, o) ? h('i', '', {}, '✓ ready') : null), lines));
    }
  }

  setClock(hour: number, day: number): void {
    const hh = Math.floor(hour);
    const mm = Math.floor((hour - hh) * 60 / 10) * 10;
    this.timeEl.textContent = `${hh}:${String(mm).padStart(2, '0')}`;
    this.dayEl.textContent = `Day ${day}`;
    this.wheel.style.transform = `rotate(${((hour - 12) / 24) * 360}deg)`;
  }

  private curTool: ToolId = "hoe";
  setTool(t: ToolId): void {
    this.curTool = t;
    for (const [k, s] of this.slots) s.classList.toggle('active', k === t);
    if (t === 'seeds') {
      this.seedPick.classList.add('on');
      this.seedTimer = 2.4;
    } else this.seedPick.classList.remove('on');
  }
  setSeed(c: CropType, unlocked: CropType[]): void {
    this.seedBadge.src = this.icon(c);
    for (const [k, b] of this.seedBtns) {
      b.classList.toggle('on', k === c);
      b.classList.toggle("locked", !unlocked.includes(k));
    }
    if (this.curTool !== "seeds") return;
    this.seedPick.classList.add("on");
    this.seedTimer = 2.4;
  }
  setWater(v: number, max: number): void {
    this.waterGauge.style.width = `${Math.round((v / max) * 100)}%`;
  }

  setPrompt(p: PromptInfo | null): void {
    this.reticle.classList.toggle('on', !!p);
    this.reticle.classList.toggle('bad', !!p && !p.ok);
    if (!p) {
      this.prompt.classList.remove('on');
      return;
    }
    const sig = `${p.key}|${p.verb}|${p.label ?? ''}|${p.detail ?? ''}|${p.ok}`;
    if (this.prompt.dataset.sig !== sig) {
      this.prompt.dataset.sig = sig;
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

  toast(text: string, icon?: string): void {
    const t = h('div', 'toast paper', {}, icon ? this.img(icon) : null, text);
    this.toasts.append(t);
    while (this.toasts.children.length > 3) this.toasts.firstElementChild?.remove();
    setTimeout(() => t.classList.add('out'), 2600);
    setTimeout(() => t.remove(), 3200);
  }

  /** A little "+2 wheat" that drifts up from the screen position. */
  float(text: string, x: number, y: number, icon?: string): void {
    const f = h('div', 'float', {}, icon ? this.img(icon) : null, text);
    f.style.left = `${x}px`;
    f.style.top = `${y}px`;
    this.root.append(f);
    setTimeout(() => f.remove(), 1400);
  }

  levelUp(level: number, unlocks: string[]): void {
    this.levelEl.replaceChildren(h('div', 'ribbon', {}, h('small', '', {}, 'Royal Favour'), `Level ${level}`));
    if (unlocks.length) this.levelEl.append(h('div', '', {}, h('div', 'unlocks paper', {}, ...unlocks.map((u) => h('span', '', {}, u)))));
    this.levelEl.classList.add('on');
    this.levelTimer = 4.2;
  }

  speech(name: string, text: string, secs = 4): void {
    this.speechEl.replaceChildren(h('b', '', {}, name), text);
    this.speechEl.classList.add('on');
    this.speechTimer = secs;
  }
  placeSpeech(x: number, y: number, visible: boolean): void {
    this.speechEl.style.left = `${x}px`;
    this.speechEl.style.top = `${y}px`;
    if (!visible) this.speechEl.style.opacity = '0';
    else this.speechEl.style.opacity = '';
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
    if (this.levelTimer > 0) {
      this.levelTimer -= dt;
      if (this.levelTimer <= 0) this.levelEl.classList.remove('on');
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
      this.panel.replaceChildren(...build());
    };
    this.panelSig = '';
    render();
    this.panelRefresh = refresh ? render : null;
    this.veil.classList.add('on');
    this.panel.classList.add('on');
    this.root.classList.add('in-menu');
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

  private coinRow(n: number): HTMLElement {
    const s = h('span');
    s.innerHTML = COIN_SVG;
    s.append(String(n));
    return s;
  }
  private favRow(n: number): HTMLElement {
    const s = h('span', 'fav');
    s.innerHTML = FAV_SVG;
    s.append(`+${n}`);
    return s;
  }

  openBoard(s: EconomyState, onDeliver: (o: Order) => void, onDiscard: (o: Order) => void): void {
    const stamped = new Set<number>();
    const tilts = ['-1.2deg', '0.8deg', '-0.5deg'];
    this.openPanel('board', false, () => {
      const notes = h('div', 'notes');
      s.orders.forEach((o, i) => {
        if (o.wait > 0 && !stamped.has(i)) {
          notes.append(h('div', 'note waiting', { style: `--tilt:${tilts[i]}` }, 'The courier rides to the castle for the next request…', h('div', 'eta', {}, `back in ${fmtTime(o.wait)}`)));
          return;
        }
        if (stamped.has(i)) {
          notes.append(h('div', 'note waiting stamped', { style: `--tilt:${tilts[i]}` }, ''));
          return;
        }
        const lines = h('div', 'lines');
        for (const l of o.lines) {
          const n = s.inv[l.item];
          lines.append(h('div', 'line', {}, this.img(l.item), `${l.qty} × ${l.qty > 1 ? ITEMS[l.item].plural : ITEMS[l.item].name}`, h('span', `have ${n >= l.qty ? 'ok' : ''}`, {}, `${Math.min(n, l.qty)}/${l.qty}`)));
        }
        const ok = canFill(s, o);
        const btn = h('button', 'btn royal', ok ? {} : { disabled: '' }, 'Deliver');
        btn.addEventListener('click', () => {
          if (!canFill(s, o)) return;
          stamped.add(i);
          onDeliver(o);
          setTimeout(() => {
            stamped.delete(i);
            this.panelRefresh?.();
          }, 1100);
        });
        const dis = h('button', 'link', {}, 'Decline');
        dis.addEventListener('click', () => onDiscard(o));
        notes.append(
          h('div', 'note', { style: `--tilt:${tilts[i]}` }, h('div', 'from', {}, o.from), h('div', 'ask', {}, 'humbly requests:'), lines, h('div', 'reward', {}, this.coinRow(o.coins), this.favRow(o.xp)), h('div', 'note-actions', {}, dis, btn)),
        );
      });
      return [this.head('Royal Requisitions', 'Fill the castle’s requests for coin and Royal Favour. The courier carries them up the hill.'), notes];
    });
  }

  openBuilding(id: BuildingId, s: EconomyState, onMake: (recipe: number) => void, onCollect: () => void): void {
    const def = BUILDINGS[id];
    this.openPanel(`building:${id}`, false, () => {
      const st = s.buildings[id];
      const lvl = levelFor(s.xp);
      const queue = h('div', 'queue');
      for (let i = 0; i < def.slots; i++) {
        const ready = st.ready[i - 0];
        if (i < st.ready.length && ready) {
          queue.append(h('div', 'qslot ready', {}, this.img(ready)));
          continue;
        }
        const j = i - st.ready.length;
        const job = st.queue[j];
        if (job) {
          const r = def.recipes[job.recipe]!;
          const slot = h('div', 'qslot', {}, this.img(r.out));
          if (j === 0) {
            const f = Math.min(1, job.t / r.time);
            const ring = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            ring.setAttribute('viewBox', '0 0 40 40');
            ring.setAttribute('class', 'ring');
            ring.innerHTML = `<circle cx="20" cy="20" r="18" fill="none" stroke="rgba(160,130,80,.25)" stroke-width="2.5"/><circle cx="20" cy="20" r="18" fill="none" stroke="#d8a63f" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="${(113 * f).toFixed(1)} 113"/>`;
            slot.append(ring, h('span', 't', {}, fmtTime(r.time - job.t)));
          } else slot.append(h('span', 't', {}, 'queued'));
          queue.append(slot);
        } else queue.append(h('div', 'qslot empty'));
      }
      if (st.ready.length) {
        const c = h('button', 'btn gold collect', {}, `Collect ${st.ready.length}`);
        c.addEventListener('click', () => onCollect());
        queue.append(c);
      }
      const recipes = h('div', 'recipes');
      def.recipes.forEach((r, i) => {
        const locked = lvl < r.level;
        const needs = h('div', 'needs');
        let can = !locked && st.queue.length + st.ready.length < def.slots;
        for (const k of Object.keys(r.needs) as ItemId[]) {
          const want = r.needs[k] ?? 0;
          const ok = s.inv[k] >= want;
          if (!ok) can = false;
          needs.append(h('span', ok ? 'ok' : '', {}, this.img(k), `${s.inv[k]}/${want}`));
        }
        const btn = h('button', 'btn', can ? {} : { disabled: '' }, locked ? `Level ${r.level}` : 'Make');
        btn.addEventListener('click', () => onMake(i));
        recipes.append(h('div', `recipe ${locked ? 'locked' : ''}`, {}, this.img(r.out), h('div', '', {}, h('div', 'rname', {}, ITEMS[r.out].name), needs), h('span', 'rtime', {}, fmtTime(r.time)), btn));
      });
      return [this.head(def.name, def.blurb), queue, recipes];
    });
  }

  openBuild(id: BuildingId, s: EconomyState, onBuild: () => void): void {
    const def = BUILDINGS[id];
    this.openPanel(`build:${id}`, true, () => {
      const lvl = levelFor(s.xp);
      const lvlOk = lvl >= def.level;
      const cashOk = s.coins >= def.cost;
      const makes = h('div', 'makes', {}, 'Makes', ...def.recipes.map((r) => this.img(r.out)));
      const price = h('div', 'price');
      price.innerHTML = COIN_SVG;
      price.append(String(def.cost));
      const btn = h('button', 'btn gold', lvlOk && cashOk ? {} : { disabled: '' }, 'Build it');
      btn.addEventListener('click', () => onBuild());
      return [
        this.head(`Build a ${def.name}`, 'A cleared plot, staked and ready for the carpenters.', false),
        h('div', 'buildcard', {}, this.img(`bld_${id}`), h('div', 'facts', {}, def.blurb, makes, price, h('div', `req ${lvlOk ? 'ok' : ''}`, {}, lvlOk ? `Royal Favour level ${def.level} ✓` : `Needs Royal Favour level ${def.level}`), cashOk || !lvlOk ? null : h('div', 'req', {}, `${def.cost - s.coins} more coins needed`))),
        h('div', 'panel-foot', {}, btn),
      ];
    });
  }

  openExpansion(e: ExpansionDef, s: EconomyState, onBuy: () => void): void {
    this.openPanel(`expand:${e.id}`, true, () => {
      const lvlOk = levelFor(s.xp) >= e.level;
      const cashOk = s.coins >= e.cost;
      const price = h('div', 'price');
      price.innerHTML = COIN_SVG;
      price.append(String(e.cost));
      const btn = h('button', 'btn gold', lvlOk && cashOk ? {} : { disabled: '' }, 'Clear the land');
      btn.addEventListener('click', () => onBuy());
      const plots = (e.cols[1] - e.cols[0] + 1) * (e.rows[1] - e.rows[0] + 1);
      return [
        this.head(e.name, `${plots} more plots of good soil, once the weeds and stones are cleared.`, false),
        h('div', 'buildcard', {}, h('div', 'facts', {}, price, h('div', `req ${lvlOk ? 'ok' : ''}`, {}, lvlOk ? `Royal Favour level ${e.level} ✓` : `Needs Royal Favour level ${e.level}`), cashOk || !lvlOk ? null : h('div', 'req', {}, `${e.cost - s.coins} more coins needed`))),
        h('div', 'panel-foot', {}, btn),
      ];
    });
  }

  // ------------------------------------------------------------------ title / pause
  showTitle(mode: 'new' | 'continue' | 'pause', onStart: () => void, onReset: (() => void) | null): void {
    const begin = h('button', 'btn gold', {}, mode === 'pause' ? 'Resume' : mode === 'continue' ? 'Continue' : 'Begin');
    begin.addEventListener('click', () => onStart());
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
        h('div', 'title-kicker', {}, mode === 'pause' ? 'Paused' : 'A steward’s homestead'),
        h('h1', '', {}, 'Aldervale', h('em', '', {}, 'Farm for the Castle')),
        h('p', '', {}, 'High on the western hill stands Aldervale Castle, and its kitchens are always hungry. Grow the crops, mill the flour, bake the bread — fill the royal requisitions to earn coin and favour, and turn this little plot into the finest farm in the valley.'),
        h('div', 'row', {}, begin, reset),
        h('div', 'controls', {}, k('W', 'A', 'S', 'D'), 'Walk  ·  Shift to run', k('1', '2', '3', '4'), 'Hoe, seeds, watering can, basket  ·  Q switches seed', k('Click'), 'Use the tool on the plot you look at', k('E'), 'Talk, open, build  ·  on a plot: does the right thing', k('Esc'), 'Pause'),
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
  get hudVisible(): boolean {
    return !this.hudHidden;
  }
}
