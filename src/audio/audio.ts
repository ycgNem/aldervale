/**
 * All of Aldervale's sound is synthesised with WebAudio: no files to load. Short one-shots for
 * tools and UI, positional by panning + distance, a bed of ambience that follows the time of day
 * and weather, and a quiet generative tune on plucked strings over a soft drone.
 */
import { Vector3 } from 'three';

export type Sfx =
  | 'step_grass'
  | 'step_dirt'
  | 'step_wood'
  | 'hoe'
  | 'seeds'
  | 'pour'
  | 'harvest'
  | 'chop'
  | 'stone'
  | 'stone_break'
  | 'timber'
  | 'weed'
  | 'coin'
  | 'click'
  | 'paper'
  | 'objective'
  | 'chapter'
  | 'splash'
  | 'cluck'
  | 'boom'
  | 'thunk'
  | 'pack'
  | 'creak'
  | 'shake'
  | 'pop'
  | 'error'
  | 'jump'
  | 'land'
  | 'build';

export interface AmbientInput {
  daylight: number;
  night: number;
  rain: number;
  /** 0..1 how close the pond is. */
  water: number;
  /** 0..1 how close a working mill is. */
  mill: number;
  /** 0..1 how close the baking oven is. */
  fire: number;
  /** 0..1 how close the hens are. */
  hens: number;
  muffled: boolean;
}

const D_MAJOR_PENTA = [62, 64, 66, 69, 71, 74, 76, 78, 81, 83];
const CHORDS: number[][] = [
  [50, 57, 62, 66],
  [43, 55, 59, 62],
  [47, 54, 59, 62],
  [45, 52, 57, 61],
];

function mtof(m: number): number {
  return 440 * Math.pow(2, (m - 69) / 12);
}

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private sfx!: GainNode;
  private music!: GainNode;
  private amb!: GainNode;
  private verb!: GainNode;
  private noise!: AudioBuffer;
  private wind: { g: GainNode; f: BiquadFilterNode } | null = null;
  private rain: { g: GainNode; f: BiquadFilterNode } | null = null;
  private water: { g: GainNode } | null = null;
  private crickets: { g: GainNode } | null = null;
  private fire: { g: GainNode } | null = null;
  private drone: { g: GainNode; oscs: OscillatorNode[] } | null = null;
  private readonly listener = new Vector3();
  private readonly right = new Vector3(1, 0, 0);
  private birdT = 2;
  private cluckT = 3;
  private creakT = 2;
  private crackleT = 0.5;
  private musicT = 1;
  private bar = 0;
  private chordIdx = 0;
  private time = 0;
  private lastAmb: AmbientInput | null = null;
  volumes = { master: 0.8, music: 0.5, sfx: 0.9 };
  musicOn = true;

  get started(): boolean {
    return !!this.ctx;
  }

  /** Must be called from a user gesture. */
  start(): void {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') void this.ctx.resume();
      return;
    }
    let ctx: AudioContext;
    try {
      ctx = new AudioContext();
    } catch {
      return;
    }
    this.ctx = ctx;
    this.master = ctx.createGain();
    this.master.connect(ctx.destination);
    // a gentle compressor keeps sudden hits polite
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -16;
    comp.ratio.value = 3;
    comp.connect(this.master);
    this.sfx = ctx.createGain();
    this.music = ctx.createGain();
    this.amb = ctx.createGain();
    this.sfx.connect(comp);
    this.music.connect(comp);
    this.amb.connect(comp);
    // cheap "room": two filtered feedback delays
    this.verb = ctx.createGain();
    this.verb.gain.value = 0.32;
    for (const [t, fb] of [
      [0.23, 0.38],
      [0.37, 0.32],
    ] as const) {
      const d = ctx.createDelay(1);
      d.delayTime.value = t;
      const g = ctx.createGain();
      g.gain.value = fb;
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 2200;
      this.verb.connect(d);
      d.connect(lp);
      lp.connect(g);
      g.connect(d);
      lp.connect(comp);
    }
    // two seconds of white noise to slice everything from
    const len = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    this.applyVolumes();
    this.startBeds();
  }

  applyVolumes(): void {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.master.gain.setTargetAtTime(this.volumes.master, t, 0.05);
    this.sfx.gain.setTargetAtTime(this.volumes.sfx, t, 0.05);
    this.music.gain.setTargetAtTime(this.musicOn ? this.volumes.music * 0.55 : 0, t, 0.3);
    this.amb.gain.setTargetAtTime(this.volumes.sfx * 0.9, t, 0.05);
  }

  suspend(v: boolean): void {
    if (!this.ctx) return;
    if (v) void this.ctx.suspend();
    else void this.ctx.resume();
  }

  setListener(pos: Vector3, forward: Vector3): void {
    this.listener.copy(pos);
    this.right.set(-forward.z, 0, forward.x).normalize();
  }

  // ------------------------------------------------------------------ building blocks
  private noiseSrc(loop = false): AudioBufferSourceNode {
    const ctx = this.ctx!;
    const s = ctx.createBufferSource();
    s.buffer = this.noise;
    s.loop = loop;
    if (!loop) s.loopStart = Math.random() * 1.5;
    return s;
  }

  /** Output node for a one-shot: panned and distance-attenuated if `at` is given. */
  private out(vol: number, at?: Vector3, verb = 0.15): AudioNode {
    const ctx = this.ctx!;
    const g = ctx.createGain();
    let v = vol;
    let pan = 0;
    if (at) {
      const dx = at.x - this.listener.x;
      const dz = at.z - this.listener.z;
      const d = Math.hypot(dx, dz, at.y - this.listener.y);
      v *= 1 / (1 + Math.max(0, d - 1.5) / 6);
      pan = d > 0.3 ? Math.max(-0.9, Math.min(0.9, (dx * this.right.x + dz * this.right.z) / d)) : 0;
    }
    g.gain.value = v;
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    g.connect(p);
    p.connect(this.sfx);
    if (verb > 0) {
      const s = ctx.createGain();
      s.gain.value = verb;
      p.connect(s);
      s.connect(this.verb);
    }
    return g;
  }

  private env(g: GainNode, t: number, a: number, peak: number, dec: number): void {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t + a + dec);
  }

  private burst(dest: AudioNode, t: number, type: BiquadFilterType, freq: number, q: number, peak: number, a: number, dec: number, sweepTo?: number): void {
    const ctx = this.ctx!;
    const s = this.noiseSrc();
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.setValueAtTime(freq, t);
    if (sweepTo) f.frequency.exponentialRampToValueAtTime(sweepTo, t + a + dec);
    f.Q.value = q;
    const g = ctx.createGain();
    this.env(g, t, a, peak, dec);
    s.connect(f);
    f.connect(g);
    g.connect(dest);
    s.start(t, Math.random() * 1.5);
    s.stop(t + a + dec + 0.05);
  }

  private tone(dest: AudioNode, t: number, type: OscillatorType, f0: number, f1: number, peak: number, a: number, dec: number): void {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t + a + dec);
    const g = ctx.createGain();
    this.env(g, t, a, peak, dec);
    o.connect(g);
    g.connect(dest);
    o.start(t);
    o.stop(t + a + dec + 0.05);
  }

  /** Plucked string: a bright triangle with a falling low-pass. */
  private pluck(dest: AudioNode, t: number, midi: number, peak: number, dec = 1.2): void {
    const ctx = this.ctx!;
    const f = mtof(midi);
    const o = ctx.createOscillator();
    o.type = 'triangle';
    o.frequency.value = f;
    const o2 = ctx.createOscillator();
    o2.type = 'sine';
    o2.frequency.value = f * 2.003;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.setValueAtTime(f * 7, t);
    lp.frequency.exponentialRampToValueAtTime(f * 1.3, t + dec);
    const g = ctx.createGain();
    this.env(g, t, 0.004, peak, dec);
    const g2 = ctx.createGain();
    g2.gain.value = 0.25;
    o.connect(lp);
    o2.connect(g2);
    g2.connect(lp);
    lp.connect(g);
    g.connect(dest);
    o.start(t);
    o2.start(t);
    o.stop(t + dec + 0.1);
    o2.stop(t + dec + 0.1);
  }

  // ------------------------------------------------------------------ one-shots
  play(name: Sfx, at?: Vector3, vol = 1): void {
    const ctx = this.ctx;
    if (!ctx || ctx.state !== 'running') return;
    const t = ctx.currentTime + 0.005;
    const r = (a: number, b: number): number => a + Math.random() * (b - a);
    switch (name) {
      case 'step_grass': {
        const o = this.out(0.22 * vol, undefined, 0);
        this.burst(o, t, 'bandpass', r(1800, 2600), 0.8, 0.5, 0.008, 0.09);
        this.burst(o, t + 0.03, 'highpass', 3500, 0.5, 0.18, 0.005, 0.05);
        break;
      }
      case 'step_dirt': {
        const o = this.out(0.3 * vol, undefined, 0);
        this.burst(o, t, 'lowpass', r(700, 1000), 0.7, 0.7, 0.005, 0.09);
        this.tone(o, t, 'sine', 95, 60, 0.25, 0.004, 0.07);
        break;
      }
      case 'step_wood': {
        const o = this.out(0.3 * vol, undefined, 0.1);
        this.burst(o, t, 'bandpass', r(500, 650), 3, 0.8, 0.003, 0.08);
        this.tone(o, t, 'sine', 160, 120, 0.3, 0.003, 0.09);
        break;
      }
      case 'hoe': {
        const o = this.out(0.55 * vol, at);
        this.tone(o, t, 'sine', 90, 45, 0.6, 0.004, 0.18);
        this.burst(o, t, 'lowpass', 1300, 0.7, 0.8, 0.004, 0.28, 400);
        this.burst(o, t + 0.05, 'bandpass', 2800, 1.2, 0.25, 0.01, 0.2);
        break;
      }
      case 'weed': {
        const o = this.out(0.5 * vol, at);
        this.burst(o, t, 'bandpass', 2400, 0.8, 0.6, 0.02, 0.3, 900);
        this.tone(o, t + 0.08, 'sine', 140, 70, 0.25, 0.005, 0.12);
        break;
      }
      case 'seeds': {
        const o = this.out(0.35 * vol, at);
        for (let i = 0; i < 9; i++) this.burst(o, t + 0.12 + i * r(0.015, 0.04), 'bandpass', r(3500, 6500), 4, 0.35, 0.002, 0.025);
        break;
      }
      case 'pour': {
        const o = this.out(0.45 * vol, at);
        const s = this.noiseSrc(true);
        const f = ctx.createBiquadFilter();
        f.type = 'bandpass';
        f.frequency.value = 1500;
        f.Q.value = 1.2;
        const lfo = ctx.createOscillator();
        lfo.frequency.value = 9;
        const lg = ctx.createGain();
        lg.gain.value = 500;
        lfo.connect(lg);
        lg.connect(f.frequency);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.6, t + 0.15);
        g.gain.setValueAtTime(0.6, t + 0.55);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.85);
        s.connect(f);
        f.connect(g);
        g.connect(o);
        s.start(t);
        lfo.start(t);
        s.stop(t + 0.9);
        lfo.stop(t + 0.9);
        break;
      }
      case 'splash': {
        const o = this.out(0.5 * vol, at);
        this.burst(o, t, 'lowpass', 3000, 0.7, 0.7, 0.01, 0.4, 500);
        this.tone(o, t + 0.02, 'sine', 600, 1400, 0.12, 0.005, 0.08);
        break;
      }
      case 'harvest': {
        const o = this.out(0.5 * vol, at);
        this.burst(o, t, 'bandpass', 2000, 0.8, 0.45, 0.01, 0.22, 1200);
        this.pluck(o, t + 0.05, 74 + Math.floor(r(0, 3)) * 2, 0.25, 0.5);
        this.tone(o, t + 0.02, 'sine', 300, 900, 0.18, 0.004, 0.08);
        break;
      }
      case 'pop': {
        const o = this.out(0.4 * vol, at);
        this.tone(o, t, 'sine', 500, 1200, 0.3, 0.003, 0.07);
        break;
      }
      case 'chop': {
        const o = this.out(0.6 * vol, at);
        this.burst(o, t, 'bandpass', r(800, 1000), 3.5, 1.0, 0.002, 0.12);
        this.tone(o, t, 'triangle', 230, 140, 0.45, 0.002, 0.14);
        this.burst(o, t + 0.01, 'highpass', 4000, 0.7, 0.2, 0.002, 0.05);
        break;
      }
      case 'timber': {
        const o = this.out(0.6 * vol, at);
        this.burst(o, t, 'lowpass', 900, 0.8, 0.8, 0.02, 0.6, 200);
        this.tone(o, t, 'sine', 120, 50, 0.5, 0.01, 0.5);
        for (let i = 0; i < 5; i++) this.burst(o, t + 0.1 + i * 0.07, 'bandpass', r(700, 1400), 3, 0.25, 0.002, 0.06);
        break;
      }
      case 'stone': {
        const o = this.out(0.55 * vol, at);
        this.burst(o, t, 'highpass', 1800, 0.8, 0.9, 0.001, 0.07);
        this.tone(o, t, 'sine', r(1700, 2100), r(1500, 1700), 0.22, 0.001, 0.2);
        this.tone(o, t, 'square', 140, 90, 0.12, 0.001, 0.06);
        break;
      }
      case 'stone_break': {
        const o = this.out(0.6 * vol, at);
        this.burst(o, t, 'lowpass', 1600, 0.7, 0.9, 0.003, 0.45, 300);
        for (let i = 0; i < 6; i++) this.burst(o, t + 0.05 + i * r(0.03, 0.07), 'highpass', r(1500, 3000), 1, 0.3, 0.001, 0.05);
        break;
      }
      case 'coin': {
        const o = this.out(0.35 * vol, undefined, 0.3);
        for (let i = 0; i < 2; i++) {
          this.tone(o, t + i * 0.09, 'sine', 1320 * (1 + i * 0.335), 1320 * (1 + i * 0.335), 0.35, 0.002, 0.35);
          this.tone(o, t + i * 0.09, 'sine', 2640 * (1 + i * 0.335), 2640 * (1 + i * 0.335), 0.08, 0.002, 0.2);
        }
        break;
      }
      case 'click': {
        const o = this.out(0.25 * vol, undefined, 0);
        this.tone(o, t, 'sine', 950, 650, 0.3, 0.002, 0.045);
        break;
      }
      case 'error': {
        const o = this.out(0.25 * vol, undefined, 0);
        this.tone(o, t, 'triangle', 220, 180, 0.3, 0.004, 0.12);
        this.tone(o, t + 0.1, 'triangle', 196, 160, 0.3, 0.004, 0.14);
        break;
      }
      case 'paper': {
        const o = this.out(0.3 * vol, undefined, 0.1);
        for (let i = 0; i < 4; i++) this.burst(o, t + i * r(0.03, 0.06), 'bandpass', r(2500, 4500), 1.5, 0.4, 0.004, r(0.05, 0.1));
        break;
      }
      case 'objective': {
        const o = this.out(0.3 * vol, undefined, 0.4);
        [74, 78, 81].forEach((m, i) => this.pluck(o, t + i * 0.09, m, 0.35, 1.0));
        break;
      }
      case 'chapter': {
        const o = this.out(0.35 * vol, undefined, 0.5);
        [62, 66, 69, 74, 78, 81, 86].forEach((m, i) => this.pluck(o, t + i * 0.11, m, 0.3, 1.6));
        this.tone(o, t, 'sine', mtof(50), mtof(50), 0.12, 0.3, 2.0);
        break;
      }
      case 'cluck': {
        const o = this.out(0.3 * vol, at);
        for (let i = 0; i < 2 + Math.floor(Math.random() * 2); i++) {
          const tt = t + i * r(0.09, 0.14);
          const car = ctx.createOscillator();
          car.type = 'sawtooth';
          car.frequency.setValueAtTime(r(500, 650), tt);
          car.frequency.exponentialRampToValueAtTime(r(350, 420), tt + 0.07);
          const bp = ctx.createBiquadFilter();
          bp.type = 'bandpass';
          bp.frequency.value = 1200;
          bp.Q.value = 2;
          const g = ctx.createGain();
          this.env(g, tt, 0.005, 0.5, 0.07);
          car.connect(bp);
          bp.connect(g);
          g.connect(o);
          car.start(tt);
          car.stop(tt + 0.1);
        }
        break;
      }
      case 'boom': {
        const o = this.out(0.5 * vol, undefined, 0.6);
        this.burst(o, t, 'lowpass', 260, 0.7, 1.0, 0.01, 1.6, 60);
        for (let i = 0; i < 14; i++) this.burst(o, t + 0.25 + Math.random() * 1.2, 'highpass', r(2000, 5000), 1, 0.15, 0.001, 0.03);
        break;
      }
      case 'thunk':
      case 'pack': {
        const o = this.out(0.5 * vol, at);
        this.tone(o, t, 'sine', 140, 80, 0.5, 0.003, 0.16);
        this.burst(o, t, 'bandpass', 600, 2, 0.5, 0.002, 0.1);
        if (name === 'pack') this.burst(o, t + 0.05, 'bandpass', 3000, 1, 0.25, 0.01, 0.2);
        break;
      }
      case 'creak': {
        const o = this.out(0.18 * vol, at);
        this.tone(o, t, 'sawtooth', r(110, 140), r(90, 100), 0.18, 0.08, 0.5);
        break;
      }
      case 'shake': {
        const o = this.out(0.5 * vol, at);
        this.burst(o, t, 'bandpass', 1800, 0.6, 0.6, 0.05, 0.9, 900);
        break;
      }
      case 'jump': {
        const o = this.out(0.15 * vol, undefined, 0);
        this.burst(o, t, 'bandpass', 1500, 1, 0.3, 0.005, 0.06);
        break;
      }
      case 'land': {
        const o = this.out(0.35 * vol, undefined, 0);
        this.burst(o, t, 'lowpass', 600, 0.7, 0.8, 0.003, 0.12);
        this.tone(o, t, 'sine', 80, 50, 0.4, 0.003, 0.1);
        break;
      }
      case 'build': {
        const o = this.out(0.45 * vol, at, 0.3);
        for (let i = 0; i < 6; i++) {
          this.tone(o, t + i * 0.16, 'triangle', r(200, 260), 150, 0.3, 0.002, 0.08);
          this.burst(o, t + i * 0.16, 'bandpass', 900, 3, 0.4, 0.002, 0.07);
        }
        [62, 69, 74].forEach((m, i) => this.pluck(o, t + 1.0 + i * 0.1, m, 0.25, 1.2));
        break;
      }
    }
  }

  // ------------------------------------------------------------------ ambience beds
  private loopBed(type: BiquadFilterType, freq: number, q: number): { g: GainNode; f: BiquadFilterNode } {
    const ctx = this.ctx!;
    const s = this.noiseSrc(true);
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = ctx.createGain();
    g.gain.value = 0;
    s.connect(f);
    f.connect(g);
    g.connect(this.amb);
    s.start();
    return { g, f };
  }

  private startBeds(): void {
    const ctx = this.ctx!;
    this.wind = this.loopBed('lowpass', 420, 0.6);
    this.rain = this.loopBed('bandpass', 2600, 0.5);
    this.water = this.loopBed('lowpass', 500, 1.2);
    this.fire = this.loopBed('bandpass', 900, 0.8);
    // crickets: a high tone chopped by a fast pulse
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.value = 4400;
    const am = ctx.createGain();
    am.gain.value = 0;
    const lfo = ctx.createOscillator();
    lfo.type = 'square';
    lfo.frequency.value = 22;
    const lg = ctx.createGain();
    lg.gain.value = 0.5;
    lfo.connect(lg);
    lg.connect(am.gain);
    const g = ctx.createGain();
    g.gain.value = 0;
    o.connect(am);
    am.connect(g);
    g.connect(this.amb);
    o.start();
    lfo.start();
    this.crickets = { g };
    // the music's drone pad
    const dg = ctx.createGain();
    dg.gain.value = 0;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 700;
    dg.connect(lp);
    lp.connect(this.music);
    const oscs: OscillatorNode[] = [];
    for (let i = 0; i < 3; i++) {
      const os = ctx.createOscillator();
      os.type = i === 2 ? 'triangle' : 'sine';
      os.frequency.value = mtof(CHORDS[0]![i]!);
      os.detune.value = (i - 1) * 6;
      os.connect(dg);
      os.start();
      oscs.push(os);
    }
    this.drone = { g: dg, oscs };
  }

  private bird(): void {
    const ctx = this.ctx!;
    const t = ctx.currentTime + 0.01;
    const pan = Math.random() * 1.6 - 0.8;
    const g = ctx.createGain();
    g.gain.value = 0.05 + Math.random() * 0.05;
    const p = ctx.createStereoPanner();
    p.pan.value = pan;
    g.connect(p);
    p.connect(this.amb);
    const s2 = ctx.createGain();
    s2.gain.value = 0.3;
    p.connect(s2);
    s2.connect(this.verb);
    const base = 2600 + Math.random() * 2200;
    const n = 2 + Math.floor(Math.random() * 5);
    for (let i = 0; i < n; i++) {
      const tt = t + i * (0.08 + Math.random() * 0.07);
      const o = ctx.createOscillator();
      o.type = 'sine';
      const up = Math.random() < 0.5;
      o.frequency.setValueAtTime(base * (up ? 0.85 : 1.15), tt);
      o.frequency.exponentialRampToValueAtTime(base * (up ? 1.2 : 0.8), tt + 0.06);
      const e = ctx.createGain();
      this.env(e, tt, 0.006, 1, 0.06);
      o.connect(e);
      e.connect(g);
      o.start(tt);
      o.stop(tt + 0.1);
    }
  }

  // ------------------------------------------------------------------ per frame
  update(dt: number, a: AmbientInput): void {
    const ctx = this.ctx;
    if (!ctx || ctx.state !== 'running') return;
    this.time += dt;
    this.lastAmb = a;
    const t = ctx.currentTime;
    const k = a.muffled ? 0.35 : 1;
    if (this.wind) {
      const gust = 0.55 + 0.45 * Math.sin(this.time * 0.13) * Math.sin(this.time * 0.31 + 1);
      this.wind.g.gain.setTargetAtTime((0.05 + 0.05 * gust + a.rain * 0.05) * k, t, 0.5);
      this.wind.f.frequency.setTargetAtTime(300 + gust * 300 + a.rain * 200, t, 0.5);
    }
    if (this.rain) this.rain.g.gain.setTargetAtTime(a.rain * 0.16 * k, t, 0.8);
    if (this.water) this.water.g.gain.setTargetAtTime(a.water * 0.06 * (0.7 + 0.3 * Math.sin(this.time * 1.3)) * k, t, 0.3);
    if (this.fire) this.fire.g.gain.setTargetAtTime(a.fire * 0.05 * k, t, 0.3);
    if (this.crickets) this.crickets.g.gain.setTargetAtTime(a.night * (1 - a.rain) * 0.012 * (0.6 + 0.4 * Math.sin(this.time * 0.7)) * k, t, 0.5);

    // birds by day (not in the rain), clucking near the hens, the mill creaking, the fire crackling
    this.birdT -= dt;
    if (this.birdT <= 0) {
      this.birdT = 1.2 + Math.random() * 4.5 / Math.max(a.daylight, 0.2);
      if (a.daylight > 0.3 && a.rain < 0.3 && !a.muffled) this.bird();
    }
    this.cluckT -= dt;
    if (this.cluckT <= 0) {
      this.cluckT = 2 + Math.random() * 5;
      if (a.hens > 0.05) this.play('cluck', undefined, a.hens * k);
    }
    this.creakT -= dt;
    if (this.creakT <= 0) {
      this.creakT = 1.8 + Math.random() * 2;
      if (a.mill > 0.05) this.play('creak', undefined, a.mill * 1.5 * k);
    }
    this.crackleT -= dt;
    if (this.crackleT <= 0) {
      this.crackleT = 0.08 + Math.random() * 0.4;
      if (a.fire > 0.05) {
        const o = this.out(0.25 * a.fire * k, undefined, 0);
        this.burst(o, ctx.currentTime + 0.01, 'highpass', 2000 + Math.random() * 3000, 1, 0.5, 0.001, 0.02);
      }
    }

    this.updateMusic(dt, a);
  }

  private updateMusic(dt: number, a: AmbientInput): void {
    const ctx = this.ctx!;
    if (!this.drone) return;
    const t = ctx.currentTime;
    this.drone.g.gain.setTargetAtTime(this.musicOn ? 0.05 * (a.muffled ? 0.4 : 1) : 0, t, 1.5);
    this.musicT -= dt;
    if (this.musicT > 0) return;
    // one bar every ~3.4 s; the chord changes every bar, the melody wanders the pentatonic
    const barLen = 3.4;
    this.musicT = barLen;
    this.bar++;
    this.chordIdx = (this.chordIdx + 1) % CHORDS.length;
    const chord = CHORDS[this.chordIdx]!;
    this.drone.oscs.forEach((o, i) => o.frequency.setTargetAtTime(mtof(chord[i]!), t, 0.6));
    if (!this.musicOn) return;
    const out = ctx.createGain();
    out.gain.value = a.night > 0.5 ? 0.6 : 1;
    out.connect(this.music);
    const s = ctx.createGain();
    s.gain.value = 0.45;
    out.connect(s);
    s.connect(this.verb);
    // a soft broken chord on the downbeat
    chord.forEach((m, i) => this.pluck(out, t + 0.02 + i * 0.12, m + 12, 0.07, 2.2));
    // a short phrase most bars, a rest some
    if (Math.random() < (a.night > 0.5 ? 0.35 : 0.7)) {
      const notes = 2 + Math.floor(Math.random() * 4);
      let idx = Math.floor(Math.random() * D_MAJOR_PENTA.length);
      for (let i = 0; i < notes; i++) {
        idx = Math.max(0, Math.min(D_MAJOR_PENTA.length - 1, idx + Math.floor(Math.random() * 5) - 2));
        const when = t + 0.6 + i * (Math.random() < 0.3 ? 0.42 : 0.28) + (i > 0 ? Math.random() * 0.06 : 0);
        this.pluck(out, when, D_MAJOR_PENTA[idx]!, 0.1, 1.4);
      }
    }
  }

  /** The last ambience input (for tests). */
  get ambient(): AmbientInput | null {
    return this.lastAmb;
  }
}
