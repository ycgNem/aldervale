import { Color, PerspectiveCamera, Scene, Vector3 } from 'three';
import { AudioEngine } from './audio/audio';
import { Assets } from './core/assets';
import { MaterialLib } from './core/materials';
import { installGlobalShaderPatches, makeNoiseTexture, shared } from './core/shared';
import { Particles } from './fx/particles';
import { FirstPerson } from './game/fp';
import { Game } from './game/game';
import { BUILDING_IDS, CROPS, ITEMS, ITEM_IDS, TOOL_ORDER } from './game/state';
import { ViewModel } from './game/viewmodel';
import { Pipeline } from './render/pipeline';
import { Rain } from './render/rain';
import { Environment } from './render/sky';
import { renderIcons } from './ui/icons';
import { UI } from './ui/ui';
import { Estate } from './world/estate';
import { Field, type CropType } from './world/field';
import { createGrass, makeMaskSampler } from './world/grass';
import { SPAWN } from './world/layout';
import { Life } from './world/life';
import { buildWorld } from './world/props';
import { createTerrain } from './world/terrain';
import { LAYER_REFLECT, LAYER_REFRACT, Pond } from './world/water';

const params = new URLSearchParams(location.search);
const num = (k: string, d: number): number => {
  const v = params.get(k);
  const n = v === null ? NaN : Number(v);
  return Number.isFinite(n) ? n : d;
};

async function boot(): Promise<void> {
  const canvas = document.getElementById('scene') as HTMLCanvasElement;
  const ui = new UI(document.getElementById('ui') as HTMLElement);
  const audio = new AudioEngine();

  installGlobalShaderPatches();
  shared.uNoise.value = makeNoiseTexture();

  const scene = new Scene();
  const camera = new PerspectiveCamera(num('fov', 72), window.innerWidth / window.innerHeight, 0.05, 2400);
  scene.add(camera);
  const pipeline = new Pipeline(canvas, scene, camera, {
    tone: params.get('tone') === 'aces' ? 'aces' : 'agx',
    msaa: num('msaa', 4),
    ao: params.get('ao') !== '0',
    tilt: params.get('tilt') === '1',
  });
  const renderer = pipeline.renderer;
  const env = new Environment(renderer, scene);
  env.dome.layers.enable(LAYER_REFLECT);

  const assets = new Assets(renderer.capabilities.getMaxAnisotropy());
  await assets.load((done, total) => ui.setLoading((done / total) * 0.85));
  if (assets.missing.length) console.warn('[assets] missing:', assets.missing.join(', '));
  const lib = new MaterialLib(assets);
  /** New crops only appear once their models exist. */
  const avail = (c: CropType): boolean => assets.has(`${c}_3`);

  // icons: every good, tool and building rendered from its real model
  const iconModels: Record<string, string> = {};
  for (const id of ITEM_IDS) {
    const d = ITEMS[id];
    iconModels[id] = assets.has(d.model) ? d.model : d.fallback && assets.has(d.fallback) ? d.fallback : d.model;
  }
  const toolAsset: Record<string, string> = { hoe: 'tool_hoe', seeds: 'tool_seed_bag', water: 'tool_watering_can', harvest: 'tool_basket', axe: 'tool_axe', pick: 'tool_pick' };
  for (const t of TOOL_ORDER) iconModels[`tool_${t}`] = toolAsset[t]!;
  for (const b of BUILDING_IDS) iconModels[`bld_${b}`] = b;
  ui.setIcons(renderIcons(assets, lib, iconModels));
  ui.setLoading(0.9);

  const terrain = createTerrain(assets);
  terrain.mesh.layers.enable(LAYER_REFLECT);
  terrain.mesh.layers.enable(LAYER_REFRACT);
  scene.add(terrain.mesh);

  const grass = createGrass(terrain.mask, terrain.grassGround, { density: num('grass', 155), half: 56, chunk: 14 });
  scene.add(grass.group);

  const field = new Field(assets, lib);
  scene.add(field.group);

  const world = buildWorld(scene, assets, lib, makeMaskSampler(terrain.mask));
  const pond = new Pond(renderer, scene, camera, assets.waterNormal);
  pipeline.prePasses.push(() => pond.prePass(env));

  const particles = new Particles(scene);
  const life = new Life(scene, assets, lib, world, particles);
  const estate = new Estate(scene, assets, lib, particles, world.colliders, world.appleTrees);
  const rain = new Rain(scene);

  const fp = new FirstPerson(camera);
  fp.teleport(num('x', SPAWN.x), num('z', SPAWN.z), num('yaw', SPAWN.yaw), num('pitch', -0.08));
  const vm = new ViewModel(camera, assets, lib);

  // ---- time of day
  env.setHour(params.has('time') ? num('time', 9.5) : 9.5);
  if (params.has('freeze')) env.paused = true;
  if (params.has('speed')) env.speed *= num('speed', 1);

  const fresh = params.has('fresh');
  if (fresh) Game.clearSave();
  const hadSave = Game.hasSave();
  const game = new Game(field, fp, vm, estate, particles, ui, camera, env, audio, avail, fresh);
  if (params.has('time')) env.setHour(num('time', 9.5));

  // settings
  const applySettings = (): void => {
    const st = game.settings;
    audio.volumes.master = st.master;
    audio.volumes.music = st.music;
    audio.volumes.sfx = st.sfx;
    audio.applyVolumes();
    fp.sensitivity = 0.0022 * st.sensitivity;
    fp.invertY = st.invertY;
    if (!params.has('fov')) {
      camera.fov = st.fov;
      camera.updateProjectionMatrix();
    }
  };
  applySettings();

  // footsteps + landing
  fp.onStep = (x, y, z) => {
    const surf = game.surface(x, z);
    audio.play(surf === 'dirt' ? 'step_dirt' : surf === 'wood' ? 'step_wood' : 'step_grass', undefined, 0.8 + Math.random() * 0.3);
    if (surf !== 'dirt') return;
    for (let i = 0; i < 2; i++) {
      particles.emit({ x: x + (Math.random() - 0.5) * 0.3, y: y + 0.04, z: z + (Math.random() - 0.5) * 0.3, vx: (Math.random() - 0.5) * 0.4, vy: 0.2 + Math.random() * 0.25, vz: (Math.random() - 0.5) * 0.4, life: 0.7 + Math.random() * 0.4, size: 0.1, sizeEnd: 0.38, r: 0.66, g: 0.52, b: 0.38, alpha: 0.14, sprite: 0, drag: 2, wind: 0.4, rot: Math.random() * 6 });
    }
  };
  fp.onLand = () => audio.play('land');

  // ---- input
  const keys = new Set<string>();
  let showStats = params.has('stats');
  let paused = true;
  const locked = (): boolean => document.pointerLockElement === canvas;
  const lock = (): void => {
    try {
      const r = canvas.requestPointerLock() as unknown as Promise<void> | undefined;
      if (r && typeof r.catch === 'function') r.catch(() => undefined);
    } catch {
      /* not allowed right now: the click-to-look hint covers it */
    }
  };
  const resume = (): void => {
    audio.start();
    audio.suspend(false);
    ui.hideTitle();
    paused = false;
    vm.setForcedLow(false);
    lock();
    game.intro();
  };
  const reset = (): void => {
    Game.clearSave();
    location.search = '?fresh';
  };
  const openSettings = (): void => {
    ui.hideTitle();
    ui.openSettings(
      { ...game.settings },
      (st) => {
        Object.assign(game.settings, st);
        game.saveSettings();
        applySettings();
      },
      () => showMenu(titleMode),
    );
  };
  let titleMode: 'new' | 'continue' | 'pause' = 'new';
  const showMenu = (mode: 'new' | 'continue' | 'pause'): void => {
    titleMode = mode;
    paused = true;
    vm.setForcedLow(true);
    ui.showTitle(mode, resume, mode === 'new' ? null : reset, openSettings);
  };
  ui.onClose = () => {
    vm.setForcedLow(false);
    if (!ui.titleOpen && !paused) lock();
  };
  ui.onClick = () => audio.play('click', undefined, 0.6);
  /** When we let go of the mouse on purpose (menus), the unlock isn't a pause. */
  let releasedAt = -1e9;
  game.onPanel = () => {
    vm.setForcedLow(true);
    releasedAt = performance.now();
    if (locked()) document.exitPointerLock();
  };
  game.onEnding = () => {
    vm.setForcedLow(false);
    lock();
  };

  document.addEventListener('pointerlockchange', () => {
    if (!locked() && !ui.panelOpen && !ui.titleOpen && !paused && performance.now() - releasedAt > 700) {
      game.save();
      showMenu('pause');
    }
  });
  canvas.addEventListener('mousedown', (e) => {
    if (paused || ui.panelOpen) return;
    audio.start();
    if (!locked()) {
      lock();
      return;
    }
    if (e.button === 0) {
      game.useTool();
      game.setHolding(true);
    } else if (e.button === 2) game.interact();
  });
  window.addEventListener('mouseup', (e) => {
    if (e.button === 0) game.setHolding(false);
  });
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  window.addEventListener('mousemove', (e) => {
    if (locked() && !paused) fp.mouse(e.movementX, e.movementY);
  });
  window.addEventListener(
    'wheel',
    (e) => {
      if (!locked() || paused || ui.panelOpen) return;
      game.cycleTool(e.deltaY > 0 ? 1 : -1);
    },
    { passive: true },
  );
  window.addEventListener('keydown', (e) => {
    if ((e.code === 'Escape' || e.code === 'KeyE' || e.code === 'Tab' || e.code === 'KeyJ') && ui.panelOpen) {
      e.preventDefault();
      if (ui.panelName === 'ending') return;
      ui.closePanel();
      return;
    }
    keys.add(e.code);
    if (e.repeat) return;
    if (e.code === 'F3' || e.code === 'Backquote') {
      e.preventDefault();
      showStats = !showStats;
    }
    if (paused || ui.panelOpen) return;
    const n = ['Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6'].indexOf(e.code);
    if (n >= 0) game.selectTool(TOOL_ORDER[n]!);
    else if (e.code === 'KeyQ') game.cycleSeed();
    else if (e.code === 'KeyE' || e.code === 'KeyF') game.interact();
    else if (e.code === 'KeyJ' || e.code === 'Tab') {
      e.preventDefault();
      game.openJournal();
    } else if (e.code === 'Space') {
      e.preventDefault();
      if (fp.jump()) audio.play('jump');
    } else if (e.code === 'KeyM') {
      audio.musicOn = !audio.musicOn;
      audio.applyVolumes();
      ui.toast(audio.musicOn ? 'Music on' : 'Music off');
    } else if (e.code === 'KeyT' && params.has('debug')) env.paused = !env.paused;
    else if (e.code === 'BracketRight' && params.has('debug')) env.setHour(env.hour + 0.5);
    else if (e.code === 'BracketLeft' && params.has('debug')) env.setHour(env.hour - 0.5);
    else if (e.code === 'KeyH') ui.setHudVisible(!ui.hudVisible);
  });
  window.addEventListener('keyup', (e) => keys.delete(e.code));
  window.addEventListener('blur', () => keys.clear());
  window.addEventListener('beforeunload', () => game.save());
  document.addEventListener('visibilitychange', () => audio.suspend(document.hidden));

  const resize = (): void => {
    pipeline.resize(window.innerWidth, window.innerHeight);
    pond.resize();
  };
  window.addEventListener('resize', resize);
  resize();

  const tint = new Color();
  const windDir = shared.uWind.value;
  const fwd = new Vector3();
  let last = performance.now();
  let fpsT = 0;
  let fpsN = 0;
  let fps = 0;
  let ms = 0;
  let frames = 0;
  /** Tests can drive the game without pointer lock. */
  let forceActive = params.has('active');

  const step = (dt: number): void => {
    shared.uTime.value += dt;
    const t = shared.uTime.value;
    windDir.z = 0.9 + 0.22 * Math.sin(t * 0.21) + 0.1 * Math.sin(t * 0.53 + 1.7);

    const live = (!paused && !ui.panelOpen && locked()) || (forceActive && !ui.panelOpen);
    game.active = live;
    ui.setLookHint(!paused && !ui.panelOpen && !locked() && !forceActive && !ui.titleOpen);
    const k = (c: string): number => (live && keys.has(c) ? 1 : 0);
    const running = k('ShiftLeft') + k('ShiftRight') > 0;
    fp.update(dt, { fwd: k('KeyW') + k('ArrowUp') - k('KeyS') - k('ArrowDown'), side: k('KeyD') + k('ArrowRight') - k('KeyA') - k('ArrowLeft'), run: running }, world.colliders, world.deckAt, (x, z) => field.surfaceAt(x, z));
    // tuck the tool away when your nose is against something solid
    fp.forward(fwd);
    const px = fp.pos.x + fwd.x * 0.55;
    const pz = fp.pos.z + fwd.z * 0.55;
    vm.blocked = world.colliders.circles.some((c) => c.r > 0 && Math.hypot(c.x - px, c.z - pz) < c.r + 0.1) || world.colliders.segments.some((sg) => {
      const ex = sg.bx - sg.ax;
      const ez = sg.bz - sg.az;
      const l2 = ex * ex + ez * ez;
      const tt = l2 > 0 ? Math.max(0, Math.min(1, ((px - sg.ax) * ex + (pz - sg.az) * ez) / l2)) : 0;
      return Math.hypot(px - (sg.ax + ex * tt), pz - (sg.az + ez * tt)) < sg.r + 0.12 && sg.r > 0.2;
    });
    vm.update(dt, fp.speed, fp.phase, fp.look.x, fp.look.y, live && running && fp.speed > 4);
    fp.endFrame();

    env.update(dt, camera);
    shared.uCloud.value.x -= windDir.x * dt * 0.028;
    shared.uCloud.value.y -= windDir.y * dt * 0.028;
    shared.uCloud.value.z = 0.62 * env.daylight * env.p.cloud;

    const glow = env.p.glow;
    world.update(dt, fp.pos.x, fp.pos.z, glow);
    lib.setWindowGlow(glow * 2.6);
    field.update(dt);
    estate.update(dt, game.s, fp.pos, glow);
    game.update(dt);
    rain.update(dt, camera, env.rain, env.daylight * 0.7 + 0.3, windDir);

    const up = Math.max(env.lightDir.y, 0);
    particles.light.copy(env.p.hor).multiplyScalar(0.55).add(tint.copy(env.p.sun).multiplyScalar(env.sun.intensity * (0.12 + up * 0.2)));
    life.update(dt, fp.pos, env.daylight * (1 - env.rain * 0.8), env.night);
    particles.update(dt);

    // sound follows the camera
    camera.getWorldDirection(fwd);
    audio.setListener(camera.position, fwd);
    const amb = game.ambience();
    audio.update(dt, { daylight: env.daylight, night: env.night, rain: env.rain, water: amb.water, mill: amb.mill, fire: amb.fire, hens: amb.hens, muffled: paused });
  };

  const frame = (now: number): void => {
    requestAnimationFrame(frame);
    const raw = (now - last) / 1000;
    last = now;
    const dt = Math.min(raw, 0.05);
    const t0 = performance.now();
    step(dt);
    pipeline.render(dt, env);
    ms += performance.now() - t0;
    frames++;
    fpsT += raw;
    fpsN++;
    if (fpsT >= 0.5) {
      fps = fpsN / fpsT;
      const cpu = ms / fpsN;
      fpsT = 0;
      fpsN = 0;
      ms = 0;
      if (showStats) {
        const i = renderer.info;
        ui.setStats(`${fps.toFixed(0)} fps   ${cpu.toFixed(1)} ms cpu\n${i.render.calls} calls   ${(i.render.triangles / 1e6).toFixed(2)} M tris\n${grass.count.toLocaleString()} blades   ${renderer.domElement.width}x${renderer.domElement.height}`);
      } else ui.setStats(null);
    }
  };

  // warm up shaders behind the loading screen, then reveal the title over the live scene
  step(1 / 60);
  pipeline.render(1 / 60, env);
  ui.setLoading(1);
  let revealed = false;
  const reveal = (): void => {
    if (revealed) return;
    revealed = true;
    ui.hideLoading();
    if (params.has('play')) {
      paused = false;
      vm.setForcedLow(false);
    } else showMenu(hadSave && !fresh ? 'continue' : 'new');
  };
  setTimeout(reveal, 1500);
  requestAnimationFrame((now) => {
    last = now;
    reveal();
    frame(now);
  });

  // handles for the console and for automated screenshots
  (window as unknown as { demo: unknown }).demo = {
    scene,
    camera,
    renderer,
    pipeline,
    env,
    fp,
    vm,
    field,
    game,
    estate,
    particles,
    ui,
    grass,
    world,
    life,
    audio,
    rain,
    step,
    crops: CROPS,
    play: (): void => {
      forceActive = true;
      paused = false;
      ui.hideTitle();
      vm.setForcedLow(false);
    },
    menu: (mode: 'new' | 'continue' | 'pause' = 'new'): void => showMenu(mode),
    key: (code: string, down = true): void => {
      if (down) keys.add(code);
      else keys.delete(code);
    },
    look: (x: number, z: number, tx: number, ty: number, tz: number): void => {
      fp.teleport(x, z, 0);
      const ey = fp.pos.y + 1.62;
      fp.yaw = Math.atan2(-(tx - x), -(tz - z));
      fp.pitch = Math.atan2(ty - ey, Math.hypot(tx - x, tz - z));
    },
    stats: () => ({ fps, frames, calls: renderer.info.render.calls, tris: renderer.info.render.triangles }),
    run: (n = 30, dt = 1 / 60): void => {
      for (let i = 0; i < n; i++) {
        step(dt);
        pipeline.render(dt, env);
      }
    },
    shot: async (name: string, w = 1920, h = 1080, crop?: [number, number, number, number]): Promise<string> => {
      renderer.setPixelRatio(1);
      pipeline.composer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      pond.resize();
      for (let i = 0; i < 4; i++) {
        step(1 / 60);
        pipeline.render(1 / 60, env);
      }
      let url: string;
      if (crop) {
        const c2 = document.createElement('canvas');
        c2.width = crop[2];
        c2.height = crop[3];
        c2.getContext('2d')!.drawImage(canvas, crop[0], crop[1], crop[2], crop[3], 0, 0, crop[2], crop[3]);
        url = c2.toDataURL('image/jpeg', 0.93);
      } else url = canvas.toDataURL('image/jpeg', 0.93);
      const res = await fetch(`/__shot?name=${encodeURIComponent(name)}`, { method: 'POST', body: url });
      resize();
      return `${name}: ${res.status}`;
    },
    bench: (n = 60, w = 1920, h = 1080): number => {
      renderer.setPixelRatio(1);
      pipeline.composer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      pond.resize();
      const gl = renderer.getContext();
      const px = new Uint8Array(4);
      for (let i = 0; i < 5; i++) {
        step(1 / 60);
        pipeline.render(1 / 60, env);
      }
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const t0 = performance.now();
      for (let i = 0; i < n; i++) {
        step(1 / 60);
        pipeline.render(1 / 60, env);
      }
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const ms2 = (performance.now() - t0) / n;
      resize();
      return ms2;
    },
  };
}

boot().catch((err: unknown) => {
  console.error(err);
  const sub = document.querySelector('.loading-sub');
  if (sub) sub.textContent = `Could not start: ${err instanceof Error ? err.message : String(err)}`;
});
