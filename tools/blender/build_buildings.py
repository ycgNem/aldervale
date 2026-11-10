"""Farm buildings + construction props for the homestead demo.

  blender --background --factory-startup --python tools/blender/build_buildings.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/buildings.glb.
With group names only those groups are built + previewed (no export) for fast iteration.

Assets: windmill (+ child windmill_sails), henhouse, bakehouse, build_site, scaffold, expand_sign.
Extra material names introduced here (the game must provide them): brick, clay, ember.
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'buildings.glb')

# new materials (name only; the game supplies the real PBR material)
kit.PREVIEW.update({'brick': (0.50, 0.21, 0.13), 'clay': (0.70, 0.52, 0.36), 'ember': (1.0, 0.36, 0.05)})
kit.ROUGH.update({'brick': 0.85, 'clay': 0.92, 'ember': 0.6})

kit.reset()

TEAL = srgb(52, 120, 128)
RED = srgb(150, 58, 46)
SAGE = srgb(92, 128, 84)
CREAM = srgb(236, 224, 196)
FLOUR = srgb(216, 204, 176)
HUES = [(1, 1, 1), (1.0, 0.95, 0.88), (0.92, 0.95, 1.0), (0.96, 1.0, 0.93), (1.0, 0.97, 0.92)]
G0, G1 = srgb(48, 100, 38), srgb(112, 168, 62)
MORTAR = (0.5, 0.48, 0.46)
MARKS = {}  # asset name -> [(marker name, pos in root space)]


# ============================================================================================
# helpers (same style as build_structures.py)
# ============================================================================================
def tint(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def R(b, a, c):
    return b.rng.uniform(a, c)


def mark(b, name, local=(0, 0, 0)):
    MARKS.setdefault(b.name, []).append((name, tuple(b.stack[-1] @ Vector(local))))


def nfaces(b):
    return len(b.bm.faces)


_TICK = {}


def tick(b, label):
    """Debug: print triangles added since the previous tick (only when BUILD_TICK is set)."""
    if not os.environ.get('BUILD_TICK'):
        return
    n = sum(len(f.verts) - 2 for f in b.bm.faces)
    print(f'   [{b.name}] {label}: +{n - _TICK.get(b.name, 0)}')
    _TICK[b.name] = n


def swap_uv(b, n0):
    uv = b.bm.loops.layers.uv['UVMap']
    for i, f in enumerate(b.bm.faces):
        if i < n0:
            continue
        for l in f.loops:
            u, v = l[uv].uv
            l[uv].uv = (v, u)


def stone(b, size, loc, rot0=(0, 0, 0), bev=None, segs=2, rj=3.0, mat='stone', jitter=0.15):
    bev = bev if bev is not None else min(0.07, min(size) * 0.3)
    b.box(size, loc=loc, rot=(rot0[0] + R(b, -rj, rj), rot0[1] + R(b, -rj, rj), rot0[2] + R(b, -rj, rj)), mat=mat,
          bevel=bev, segs=segs, grain=None, color=b.rng.choice(HUES), jitter=jitter)


def wood(b, size, loc=(0, 0, 0), rot=(0, 0, 0), mat='wood_plank', bevel=0.012, segs=1, jitter=0.1, rj=0.0, **kw):
    rot = (rot[0] + R(b, -rj, rj), rot[1] + R(b, -rj, rj), rot[2] + R(b, -rj, rj)) if rj else rot
    b.box(size, loc=loc, rot=rot, mat=mat, bevel=bevel, segs=segs, jitter=jitter, **kw)


def beam(b, x0, z0, x1, z1, w=0.17, depth=0.2, y=0.1, mat='wood_dark', bevel=0.018, segs=2):
    """Timber in a wall frame (x along the wall, z up, outward = -Y, timber face at y=0)."""
    dx, dz = x1 - x0, z1 - z0
    ln = math.hypot(dx, dz)
    b.box((ln, depth, w), loc=((x0 + x1) / 2, y, (z0 + z1) / 2),
          rot=(0, -math.degrees(math.atan2(dz, dx)) + R(b, -0.5, 0.5), 0), mat=mat, bevel=bevel, segs=segs,
          jitter=0.1, grain=0)


def beam1(b, *a, **kw):
    beam(b, *a, segs=1, **kw)


def strut(b, p0, p1, w=0.1, d=0.1, mat='wood_dark', bevel=0.015, segs=1, jitter=0.1, **kw):
    """Bevelled timber between two points. w = horizontal width, d = the 'upward' thickness."""
    p0, p1 = Vector(p0), Vector(p1)
    v = p1 - p0
    e = v.to_track_quat('Z', 'Y').to_euler('XYZ')
    b.box((w, d, v.length), loc=tuple((p0 + p1) / 2), rot=tuple(math.degrees(a) for a in e), mat=mat, bevel=bevel,
          segs=segs, jitter=jitter, grain=2, **kw)


def pole(b, p0, p1, r=0.04, r1=None, mat='wood_plank', n=3, wob=0.008, segs=7, caps=True, **kw):
    """Slightly irregular round pole (grain along its length)."""
    p0, p1 = Vector(p0), Vector(p1)
    pts, rad = [], []
    for i in range(n):
        t = i / (n - 1)
        p = p0.lerp(p1, t)
        if 0 < i < n - 1:
            p += Vector((R(b, -wob, wob), R(b, -wob, wob), R(b, -wob, wob)))
        pts.append(tuple(p))
        rad.append((r + ((r if r1 is None else r1) - r) * t) * R(b, 0.94, 1.05))
    n0 = nfaces(b)
    b.tube(pts, rad, mat=mat, segs=segs, jitter=0.1, caps=caps, **kw)
    swap_uv(b, n0)


def flat_poly(b, pts, z, thick=0.05, mat='wood_plank', bevel=0.01, jitter=0.12, **kw):
    """Horizontal slab from a plan-view polygon [(x, y), ...] (grain along local x)."""
    b.prism(pts, thick, loc=(0, 0, z), rot=(-90, 0, 0), mat=mat, bevel=bevel, segs=1, grain=0, jitter=jitter, **kw)


def chev(s=1.0):
    return [(-0.30 * s, -0.27 * s), (-0.25 * s, -0.32 * s), (0, -0.07 * s), (0.25 * s, -0.32 * s),
            (0.30 * s, -0.27 * s), (0, 0.03 * s)]


def gable_roof(b, loc, length, run, pitch, yaw=0, keep=None, row_h=0.33, sw=(0.34, 0.5), thick=0.045,
               barge=True, tails=0.0, cap=1.2, sag=0.0, cap_z=0.2, sides=(0, 180)):
    """Ridge through `loc` along local X (rotated by yaw). Deck, fascia, individual shingles,
    barge boards, rafter tails and ridge caps. keep(world_point) filters shingles.
    sides=(0,) gives a lean-to that falls toward local -Y."""
    pr = math.radians(pitch)
    L = run / math.cos(pr)
    tilt = math.degrees(math.atan2(thick * 1.1, row_h))
    with b.at(loc=loc, rot=(0, 0, yaw)):
        for side in sides:
            with b.at(rot=(pitch, 0, side)):
                b.box((length - 0.06, L, 0.06), loc=(0, -L / 2, -0.03), mat='wood_plank', bevel=0.01, segs=1,
                      grain=0, jitter=0.05)
                b.box((length - 0.05, 0.05, 0.13), loc=(0, -L + 0.01, -0.035), mat='wood_dark', bevel=0.012,
                      segs=1, jitter=0.08)
                rows = int(math.ceil(L / row_h))
                for r in range(rows):
                    y0 = -L + r * row_h
                    x = -length / 2 - 0.03
                    while x < length / 2 - 0.1:
                        w = R(b, *sw)
                        if x + w > length / 2 + 0.03:
                            w = length / 2 + 0.03 - x
                        ln = row_h * 1.7 + R(b, -0.02, 0.06)
                        lo = y0 - 0.05 + R(b, -0.035, 0.03)
                        hi = min(lo + ln, -0.01)
                        ln2 = hi - lo
                        if ln2 > 0.08 and w > 0.08:
                            cz = thick / 2 + (ln2 / 2) * math.sin(math.radians(tilt)) + 0.004
                            c = (x + w / 2, (lo + hi) / 2, cz)
                            if keep is None or keep(b.stack[-1] @ Vector(c)):
                                b.box((w - 0.012, ln2, thick), loc=c,
                                      rot=(-tilt + R(b, -1.5, 1.5), R(b, -2.2, 2.2), R(b, -2.5, 2.5)), mat='roof',
                                      bevel=0.009, segs=1, grain=1, jitter=0.18)
                        x += w
                if barge:
                    for sx in (-1, 1):
                        b.box((0.07, L + 0.14, 0.2), loc=(sx * (length / 2 - 0.02), -L / 2 - 0.03, -0.1),
                              mat='wood_dark', bevel=0.015, segs=2, jitter=0.08, grain=1)
                if tails:
                    n = max(2, int(length / tails))
                    for i in range(n):
                        xi = -length / 2 + 0.35 + i * (length - 0.7) / (n - 1)
                        b.box((0.1, 0.55, 0.11), loc=(xi, -L + 0.33, -0.115), mat='wood_dark', bevel=0.015, segs=1,
                              jitter=0.1, grain=1)
        if cap:
            n = int(math.ceil(length / (0.42 * cap)))
            step = length / n
            for i in range(n):
                x = -length / 2 + (i + 0.5) * step
                dz = -sag * (1 - (2 * x / length) ** 2)
                b.prism(chev(cap), depth=step + 0.1 * cap, loc=(x, 0, dz + cap_z * cap + 0.01),
                        rot=(R(b, 2, 5), R(b, -2, 2), 90 + R(b, -2, 2)), mat='roof', bevel=0.012, segs=1, jitter=0.18,
                        grain=1)


def lantern(b, s=1.0):
    """Hanging lantern; local origin = hanging ring, extends down ~0.34*s. Returns lamp centre (local)."""
    ring = [(0.022 * s * math.cos(a), 0, 0.0 + 0.022 * s * math.sin(a) - 0.022 * s) for a in
            [i * math.pi / 5 for i in range(11)]]
    b.tube(ring, 0.005 * s, mat='metal_dark', segs=8, caps=False)
    b.lathe([(0, -0.115 * s), (0.105 * s, -0.115 * s), (0.11 * s, -0.105 * s), (0.04 * s, -0.06 * s),
             (0.02 * s, -0.04 * s), (0, -0.04 * s)], mat='metal_dark', segs=4, rot=(0, 0, 45))
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((0.014 * s, 0.014 * s, 0.19 * s), loc=(sx * 0.068 * s, sy * 0.068 * s, -0.205 * s), mat='metal_dark',
                  bevel=0.003, segs=1)
    b.box((0.125 * s, 0.125 * s, 0.17 * s), loc=(0, 0, -0.205 * s), mat='glass', bevel=0, grain=None)
    b.box((0.17 * s, 0.17 * s, 0.03 * s), loc=(0, 0, -0.31 * s), mat='metal_dark', bevel=0.008, segs=1)
    b.box((0.16 * s, 0.16 * s, 0.014 * s), loc=(0, 0, -0.113 * s), mat='metal_dark', bevel=0.004, segs=1)
    return (0, 0, -0.205 * s)


def bracket_lantern(b, name, side=1):
    """Iron scroll bracket + lantern. Local frame: wall plane y=0 (outward -Y), origin = bracket root."""
    b.tube([(0, 0.0, 0.0), (0, -0.16, 0.07), (0, -0.3, 0.04), (0, -0.34, -0.02)], 0.012, mat='metal_dark', segs=8)
    b.tube([(0, 0.0, -0.2), (0, -0.12, -0.1), (0, -0.24, 0.04)], 0.009, mat='metal_dark', segs=8)
    with b.at(loc=(0, -0.34, -0.015)):
        mark(b, name, lantern(b))


def flowers(b, span, z0, n=9, trailing=True):
    cols = [srgb(232, 96, 110), srgb(245, 200, 70), srgb(245, 240, 232), srgb(214, 70, 60), srgb(170, 130, 215)]
    for i in range(n):
        x = -span / 2 + (i + 0.5) * span / n + R(b, -0.03, 0.03)
        y = R(b, -0.05, 0.04)
        h = R(b, 0.1, 0.22)
        lx, ly = R(b, -0.04, 0.04), R(b, -0.07, 0.01)
        top = (x + lx, y + ly, z0 + h)
        b.tube([(x, y, z0), (x + lx * 0.4, y + ly * 0.4, z0 + h * 0.55), top], 0.008, mat='plant', segs=5, color=G0,
               color_top=G1, caps=False)
        for _ in range(3):
            b.leaf(R(b, 0.08, 0.14), 0.045, loc=(x, y, z0 + 0.01), rot=(0, R(b, 25, 60), R(b, 0, 360)), color=G0,
                   color_top=G1, bend=50, segs=3, jitter=0.12)
        c = b.rng.choice(cols)
        b.lathe([(0, 0), (0.034, 0.01), (0.014, 0.022), (0, 0.022)], loc=top, rot=(R(b, -25, 25), R(b, -25, 25), R(b, 0, 70)),
                mat='plant_glossy', segs=10, color=c, jitter=0.1, radial=lambda a, z: 1 + 0.35 * math.cos(5 * a))
        b.blob(0.011, loc=(top[0], top[1], top[2] + 0.02), subdiv=1, mat='plant_glossy', color=srgb(250, 205, 60))
    if trailing:
        m = int(span / 0.075)
        for i in range(m):
            x = -span / 2 + (i + 0.5) * span / m + R(b, -0.02, 0.02)
            b.leaf(R(b, 0.12, 0.24), 0.05, loc=(x, -0.07, z0 - 0.005), rot=(0, R(b, 60, 95), -90 + R(b, -30, 30)),
                   color=G0, color_top=G1, bend=80, segs=4, jitter=0.15)


def shutter(b, sw, H, c=TEAL):
    for ex in (-1, 1):
        b.box((0.06, 0.04, H), loc=(ex * (sw / 2 - 0.03), 0, 0), mat='paint', color=c, jitter=0.08, bevel=0.008, segs=1)
    for ez in (-1, 0, 1):
        b.box((sw - 0.1, 0.038, 0.07), loc=(0, 0, ez * (H / 2 - 0.035)), mat='paint', color=c, jitter=0.08,
              bevel=0.008, segs=1)
    b.box((sw - 0.1, 0.012, H - 0.1), loc=(0, 0.008, 0), mat='paint', color=tint(c, 0.5), bevel=0, grain=None)
    n = max(4, int(round(H / 0.13)))
    for i in range(n):
        z = -H / 2 + 0.07 + (i + 0.5) * (H - 0.14) / n
        if abs(z) < 0.05:
            continue
        b.box((sw - 0.11, 0.014, min(0.095, (H - 0.14) / n * 0.85)), loc=(0, -0.004, z), rot=(-28, 0, 0), mat='paint',
              color=c, jitter=0.1, bevel=0.004, segs=1)


def window(b, w=0.8, h=1.0, shutters=True, flower_box=False, sw=0.38, color=TEAL, bars=True, fs=2, nflowers=9):
    """Local frame: wall (plaster) plane y=0, outward -Y, centred on the pane."""
    b.box((w, 0.02, h), loc=(0, -0.012, 0), mat='glass', bevel=0, grain=None)
    for sx in (-1, 1):
        wood(b, (0.09, 0.15, h + 0.12), loc=(sx * (w / 2 + 0.045), -0.055, 0), bevel=0.015, segs=fs, rj=0.6)
    wood(b, (w + 0.3, 0.16, 0.1), loc=(0, -0.06, h / 2 + 0.05), bevel=0.015, segs=fs, rj=0.6)
    wood(b, (w + 0.38, 0.24, 0.08), loc=(0, -0.1, -h / 2 - 0.04), bevel=0.02, segs=fs, rj=0.6)
    if bars:
        wood(b, (0.045, 0.05, h), loc=(0, -0.035, 0), bevel=0.008)
        wood(b, (w, 0.05, 0.045), loc=(0, -0.035, 0.06 if h > 0.7 else 0.0), bevel=0.008)
    mark(b, 'window_light', (0, -0.03, 0))
    if shutters:
        H = h + 0.04
        for sx in (-1, 1):
            with b.at(loc=(sx * (w / 2 + 0.1 + sw / 2), -0.05, R(b, -0.01, 0.01)), rot=(0, R(b, -1.2, 1.2), sx * R(b, -5, -1))):
                shutter(b, sw, H, color)
    if flower_box:
        L = w + 0.3
        with b.at(loc=(0, -0.19, -h / 2 - 0.2)):
            wood(b, (L, 0.03, 0.18), loc=(0, -0.1, 0), rot=(6, 0, 0), bevel=0.01, segs=2, rj=0.8)
            wood(b, (L, 0.03, 0.18), loc=(0, 0.1, 0), bevel=0.01)
            for sx in (-1, 1):
                wood(b, (0.03, 0.2, 0.18), loc=(sx * (L / 2 - 0.015), 0, 0), bevel=0.01, segs=2)
                wood(b, (0.05, 0.3, 0.05), loc=(sx * L * 0.3, 0.05, -0.115), mat='wood_dark', bevel=0.01)
            wood(b, (L, 0.2, 0.03), loc=(0, 0, -0.085), bevel=0.01)
            b.box((L - 0.05, 0.18, 0.05), loc=(0, 0, 0.045), mat='soil', bevel=0.015, segs=1, grain=None)
            flowers(b, L - 0.14, 0.07, n=nflowers)


def door(b, dw=1.0, dh=1.9, color=TEAL, n=5, fs=2):
    """Local frame: timber plane y=0 (outward -Y), origin at the threshold centre."""
    pw = dw / n
    for i in range(n):
        b.box((pw - 0.012, 0.06, dh - R(b, 0, 0.02)), loc=(-dw / 2 + (i + 0.5) * pw, 0.07, dh / 2), mat='paint',
              color=color, jitter=0.1, bevel=0.012, segs=fs, grain=2)
    for sx in (-1, 1):
        wood(b, (0.16, 0.24, dh + 0.06), loc=(sx * (dw / 2 + 0.08), 0.05, dh / 2), mat='wood_dark', bevel=0.02, segs=fs, rj=0.5)
    wood(b, (dw + 0.56, 0.26, 0.2), loc=(0, 0.045, dh + 0.1), mat='wood_dark', bevel=0.025, segs=2, rj=0.5)
    for z in (0.36, dh - 0.36):
        b.box((dw - 0.07, 0.03, 0.12), loc=(0, 0.03, z), mat='paint', color=tint(color, 0.8), jitter=0.06, bevel=0.01, segs=1)
        b.box((dw * 0.62, 0.014, 0.055), loc=(-dw / 2 + dw * 0.33, 0.011, z), mat='metal_dark', bevel=0.005, segs=1)
        b.cyl(0.045, 0.016, loc=(-dw / 2 + dw * 0.64, 0.02, z), rot=(90, 0, 0), mat='metal_dark', segs=10, bevel=0.004)
        for dx in (0.1, 0.3, 0.5):
            b.cyl(0.012, 0.008, loc=(-dw / 2 + dx * dw, 0.006, z), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
    hx, hz = dw / 2 - 0.15, 1.0
    b.cyl(0.05, 0.014, loc=(hx, 0.04, hz), rot=(90, 0, 0), mat='metal_dark', segs=12, bevel=0.004)
    ring = [(hx + 0.055 * math.cos(a), 0.012, hz - 0.045 + 0.055 * math.sin(a)) for a in
            [i * 2 * math.pi / 14 for i in range(15)]]
    b.tube(ring, 0.009, mat='metal_dark', segs=8, caps=False)


def stone_courses(b, xr, z0, z1, y=0.08, depth=0.36, ch=(0.3, 0.42), sw=(0.42, 0.74), gaps=(), segs=1, bev=0.06,
                  rj=2.0):
    """Coursed rubble in a wall frame (wall face y=0, outward -Y). xr = (x0, x1) or fn(z) -> (x0, x1).
    gaps = [(x0, x1, z0, z1)] openings (stones are clipped to the jambs)."""
    z = z0
    while z < z1 - 0.04:
        h = min(R(b, *ch), z1 - z)
        if z1 - (z + h) < ch[0] * 0.55:
            h = z1 - z
        zc = z + h / 2
        xa, xb = xr(zc) if callable(xr) else xr
        x = xa
        first = True
        while x < xb - 0.04:
            w = min(R(b, *sw) * (0.6 if first and b.rng.random() < 0.5 else 1.0), xb - x)
            first = False
            if xb - (x + w) < 0.24:
                w = xb - x
            parts = [(x, x + w)]
            for g0, g1, gz0, gz1 in gaps:
                if gz0 < zc < gz1:
                    new = []
                    for s0, s1 in parts:
                        if s1 <= g0 or s0 >= g1:
                            new.append((s0, s1))
                        else:
                            if s0 < g0:
                                new.append((s0, g0))
                            if s1 > g1:
                                new.append((g1, s1))
                    parts = new
            for s0, s1 in parts:
                if s1 - s0 > 0.1:
                    stone(b, (s1 - s0 - 0.015, depth, h - 0.015), ((s0 + s1) / 2, y + R(b, -0.03, 0.02), zc), segs=segs,
                          bev=min(bev, (s1 - s0) * 0.3), rj=rj)
            x += w
        z += h


def stone_ring(b, Rc, z0, H, ch=(0.2, 0.27), da=(0.5, 0.82), depth=0.26, segs=1):
    z = z0
    while z < H - 0.05:
        h = min(R(b, *ch), H - z)
        if H - (z + h) < 0.14:
            h = H - z
        a = R(b, 0, 1.0)
        a0 = a
        while a < a0 + 2 * math.pi - 0.2:
            d = min(R(b, *da), a0 + 2 * math.pi - a)
            if a0 + 2 * math.pi - (a + d) < da[0] * 0.7:
                d = a0 + 2 * math.pi - a
            am = a + d / 2
            rr = Rc + R(b, -0.02, 0.03)
            stone(b, (d * (rr + depth * 0.4) - 0.02, depth, h - 0.015), (rr * math.cos(am), rr * math.sin(am), z + h / 2),
                  rot0=(0, 0, math.degrees(am) + 90), bev=0.055, rj=2.5, segs=segs)
            a += d
        z += h


def stone_stack(b, half, top, open_from, name=None, z0=-0.05, ch=(0.4, 0.52)):
    """Square rubble chimney centred on the local origin. The x- face (toward the house) is only
    built above z=open_from."""
    hx = hy = half
    ch_rng = ch
    b.box((hx * 2 - 0.12, hy * 2 - 0.12, top - z0), loc=(0, 0, (top + z0) / 2), mat='stone', bevel=0.02, segs=1, grain=None,
          color=MORTAR)
    z = z0
    k = 0
    while z < top - 0.05:
        ch = min(R(b, *ch_rng), top - z)
        if top - (z + ch) < 0.2:
            ch = top - z
        zc = z + ch / 2
        faces = [('x+', hy), ('y-', hx), ('y+', hx)]
        if zc > open_from:
            faces.append(('x-', hy))
        for nm, hl in faces:
            edges = [0.0, R(b, 0.3, 0.7), 1.0] if b.rng.random() < 0.6 else [0.0, 1.0]
            ne = len(edges) - 1
            ext = 0.1 if (k % 2 == 0) == (nm[0] == 'x') else -0.08
            for j in range(ne):
                a = -hl + edges[j] * 2 * hl - (ext if j == 0 else 0)
                c = -hl + edges[j + 1] * 2 * hl + (ext if j == ne - 1 else 0)
                ln, mid = c - a - 0.015, (a + c) / 2
                out = R(b, 0.0, 0.05)
                hgt = ch - 0.015
                if nm == 'x+':
                    stone(b, (0.22, ln, hgt), (hx - 0.07 + out, mid, zc), segs=1, bev=0.05, rj=2.0)
                elif nm == 'x-':
                    stone(b, (0.22, ln, hgt), (-hx + 0.07 - out, mid, zc), segs=1, bev=0.05, rj=2.0)
                elif nm == 'y-':
                    stone(b, (ln, 0.22, hgt), (mid, -hy + 0.07 - out, zc), segs=1, bev=0.05, rj=2.0)
                else:
                    stone(b, (ln, 0.22, hgt), (mid, hy - 0.07 + out, zc), segs=1, bev=0.05, rj=2.0)
        z += ch
        k += 1
    stone(b, (hx * 2 + 0.24, hy * 2 + 0.24, 0.14), (0, 0, top + 0.06), bev=0.04, rj=1.0)
    for sy in (-0.2, 0.2):
        b.lathe([(0.1, 0), (0.13, 0), (0.135, 0.02), (0.105, 0.3), (0.115, 0.33), (0.085, 0.33), (0.08, 0.05), (0, 0.05)],
                loc=(0, sy, top + 0.12), mat='roof', segs=14, jitter=0.15)
    if name:
        mark(b, name, (0, 0, top + 0.5))


def vplanks(b, x0, x1, z0, ztop, pw=0.22, thick=0.035, y=0.0, mat='wood_plank', gaps=(), apex=None, jitter=0.14,
            bevel=0.008, ragged=0.025):
    """Vertical boards in a wall frame (face y=0, outward -Y). ztop(x) -> top height (cut to the
    roof line). gaps = [(x0, x1, z0, z1)]: boards whose centre lies in a gap are cut around it."""
    n = max(1, int(round((x1 - x0) / pw)))
    w = (x1 - x0) / n
    for i in range(n):
        xa, xb = x0 + i * w + 0.004, x0 + (i + 1) * w - 0.004
        xm = (xa + xb) / 2
        zb = z0 - R(b, 0, ragged)
        spans = [(zb, None)]
        for g0, g1, gz0, gz1 in gaps:
            if g0 < xm < g1:
                spans = []
                if gz0 - zb > 0.06:
                    spans.append((zb, gz0))
                spans.append((gz1, None))
        yy = y + R(b, -0.004, 0.004)
        for za, zt in spans:
            if zt is None:
                ta, tb = ztop(xa), ztop(xb)
                if min(ta, tb) - za < 0.04:
                    continue
                pts = [(xa, za), (xb, za), (xb, tb)]
                if apex is not None and xa < apex < xb:
                    pts.append((apex, ztop(apex)))
                pts.append((xa, ta))
            else:
                pts = [(xa, za), (xb, za), (xb, zt), (xa, zt)]
            b.prism(pts, thick, loc=(0, yy - thick / 2, 0), mat=mat, bevel=bevel, segs=1, grain=2, jitter=jitter)


def lattice(b, W, z0, z1, step=0.22, y=0.0, mat='wood_light', w=0.03, t=0.012, bevel=0.003):
    """Diagonal slat lattice filling x in [0, W], z in [z0, z1] of the current frame (two layers)."""
    H = z1 - z0
    s = step * math.sqrt(2)
    for d in (1, -1):
        c = -H + s * (0.5 if d == 1 else 0.85)
        while c < W:
            xa, xb = max(0.0, c), min(W, c + H)
            if xb - xa > 0.07:
                za, zb = z0 + (xa - c), z0 + (xb - c)
                if d == -1:
                    xa, xb = W - xa, W - xb
                strut(b, (xa, y - d * t * 0.55, za), (xb, y - d * t * 0.55, zb), w=t, d=w, mat=mat, bevel=bevel, segs=1,
                      jitter=0.14)
            c += s


def bucket(b, r0=0.13, r1=0.165, h=0.27, handle=0.0):
    n = 12
    segs = n * 2
    tones = [1 + R(b, -0.12, 0.12) for _ in range(n)]

    def col(co):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        k = tones[int(a / (2 * math.pi) * n + 0.25) % n]
        return (k, k, k)

    def rad(a, z):
        return 0.975 if round(a / (2 * math.pi) * segs) % 2 == 0 else 1.0

    n0 = nfaces(b)
    b.lathe([(0, 0.012), (r0 - 0.02, 0.012), (r0 - 0.015, 0), (r0, 0), (r1, h), (r1 - 0.022, h), (r0 - 0.02, 0.035),
             (0, 0.035)], mat='wood_plank', segs=segs, color=col, radial=rad)
    swap_uv(b, n0)
    for z in (0.06, h - 0.07):
        r = r0 + (r1 - r0) * z / h
        b.lathe([(r - 0.004, z - 0.016), (r + 0.006, z - 0.014), (r + 0.007, z + 0.014), (r - 0.003, z + 0.016)],
                mat='metal', segs=segs)
    ha = math.radians(handle)
    arc = []
    for i in range(11):
        t = math.pi * i / 10
        x, zz = -(r1 + 0.004) * math.cos(t), (r1 + 0.03) * math.sin(t)
        arc.append((x, -zz * math.sin(ha), h - 0.03 + zz * math.cos(ha)))
    b.tube(arc, 0.008, mat='metal_dark', segs=8)
    for sx in (-1, 1):
        b.cyl(0.018, 0.012, loc=(sx * (r1 - 0.004), 0, h - 0.03), rot=(0, sx * 90, 0), mat='metal_dark', segs=8, bevel=0.003)
    return h + r1 + 0.03


def sack(b, c=FLOUR, s=1.0, patch=True):
    """Tied sack standing on the local origin (~0.56*s tall)."""
    def rad(a, z):
        return 1 + 0.07 * math.sin(3 * a + z * 6) + 0.04 * math.sin(5 * a + 1.3) + (0.1 * math.cos(a) if z < 0.25 else 0)

    with b.at(scale=(s, s, s)):
        b.lathe([(0, 0), (0.17, 0), (0.235, 0.035), (0.255, 0.13), (0.24, 0.26), (0.19, 0.36), (0.1, 0.43), (0.06, 0.455),
                 (0.052, 0.48), (0.075, 0.515), (0.115, 0.56), (0.11, 0.565), (0.05, 0.53), (0, 0.52)], mat='cloth', segs=14,
                color=tint(c, 0.8), color_top=tint(c, 1.06), radial=rad, rot=(4, -5, 0))
        b.lathe([(0.05, 0.458), (0.068, 0.462), (0.07, 0.482), (0.05, 0.488)], mat='rope', segs=10, rot=(4, -5, 0))
        b.tube([(0.06, -0.03, 0.47), (0.12, -0.06, 0.4), (0.13, -0.07, 0.33)], 0.008, mat='rope', segs=6)
        if patch:
            b.box((0.12, 0.012, 0.1), loc=(-0.03, -0.248, 0.2), rot=(-4, 6, 5), mat='cloth', color=srgb(150, 110, 78),
                  bevel=0.004, segs=1)


def log_piece(b, r, ln, kind, loc, rot):
    """Split log lying along local Y. kind: 'half' | 'quarter' | 'round'."""
    if kind == 'round':
        arc = [(r * math.cos(a) * R(b, 0.93, 1.05), r * math.sin(a) * R(b, 0.93, 1.05)) for a in [i * 2 * math.pi / 10 for i in range(10)]]
        inner = [(x * 0.88, z * 0.88) for x, z in arc]
    else:
        span = math.pi if kind == 'half' else math.pi / 2
        n = 7 if kind == 'half' else 5
        arc = [(r * math.cos(span * i / (n - 1)) * R(b, 0.94, 1.05), r * math.sin(span * i / (n - 1)) * R(b, 0.94, 1.05)) for i in range(n)]
        inner = [(x * 0.9, z * 0.9) for x, z in arc]
        if kind == 'quarter':
            arc.append((0, 0))
            inner = [(inner[0][0], -0.005)] + inner[1:-1] + [(-0.005, inner[-1][1])] + [(-0.005, -0.005)]
        else:
            inner[0] = (inner[0][0], -0.005)
            inner[-1] = (inner[-1][0], -0.005)
    with b.at(loc=loc, rot=rot):
        b.prism(arc, ln, mat='bark', bevel=0.008, segs=1, jitter=0.12, grain=1)
        b.prism(inner, ln + 0.012, mat='wood_light', bevel=0.004, segs=1, jitter=0.12, grain=1)


def woodpile(b, rows=((5, 0.115, 0.05), (4, 0.115, 0.25), (4, 0.105, 0.43), (3, 0.1, 0.6))):
    for sx in (-1, 1):
        wood(b, (0.07, 0.07, 0.75), loc=(sx * 0.6, 0, 0.36), rot=(0, sx * 3, 0), mat='wood_dark', bevel=0.014, segs=2)
    wood(b, (1.3, 0.07, 0.05), loc=(0, -0.14, 0.025), mat='wood_dark', bevel=0.012)
    wood(b, (1.3, 0.07, 0.05), loc=(0, 0.14, 0.025), mat='wood_dark', bevel=0.012)
    kinds = ['half', 'quarter', 'half', 'round', 'quarter', 'half']
    k = 0
    for n, r, z in rows:
        w = 1.08 if n == 5 else (0.9 if n == 4 else 0.62)
        for i in range(n):
            x = -w / 2 + (i + 0.5) * w / n + R(b, -0.015, 0.015)
            kind = kinds[(k * 5 + 2) % len(kinds)]
            ln = R(b, 0.46, 0.56)
            if kind == 'half':
                flip = b.rng.random() < 0.4
                log_piece(b, r * 1.05, ln, kind, (x, R(b, -0.03, 0.03), z + (r * 0.95 if flip else 0.0)),
                          (0, (180 if flip else 0) + R(b, -14, 14), R(b, -4, 4)))
            elif kind == 'quarter':
                log_piece(b, r * 1.5, ln, kind, (x - r * 0.5, R(b, -0.03, 0.03), z), (0, R(b, -12, 12), R(b, -4, 4)))
            else:
                log_piece(b, r * 0.85, ln, kind, (x, R(b, -0.03, 0.03), z + r * 0.85), (0, R(b, 0, 90), R(b, -4, 4)))
            k += 1


def peg(b, loc, h=0.34, s=0.05, c=RED, lean=6):
    """Survey peg: pointed-top stake with a painted band."""
    with b.at(loc=loc, rot=(R(b, -lean, lean), R(b, -lean, lean), R(b, 0, 90))):
        wood(b, (s, s, h + 0.08), loc=(0, 0, h / 2 - 0.04), mat='wood_light', bevel=0.008, segs=1, jitter=0.12)
        wood(b, (s, s, 0.05), loc=(0, 0, h + 0.025), mat='wood_light', bevel=0.008, segs=1, taper=(0.35, 0.35), jitter=0.12)
        b.box((s + 0.006, s + 0.006, 0.07), loc=(0, 0, h - 0.06), mat='paint', color=c, bevel=0.006, segs=1, jitter=0.08)


def rope_span(b, p0, p1, sag=0.08, r=0.012, n=9, segs=6):
    p0, p1 = Vector(p0), Vector(p1)
    pts = []
    for i in range(n):
        t = i / (n - 1)
        p = p0.lerp(p1, t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(tuple(p))
    b.tube(pts, r, mat='rope', segs=segs, jitter=0.06)
    return pts


def rope_wrap(b, loc, r=0.05, turns=3, rr=0.012, pitch=0.022):
    pts = []
    for i in range(turns * 10 + 1):
        a = i * 2 * math.pi / 10
        pts.append((loc[0] + r * math.cos(a), loc[1] + r * math.sin(a), loc[2] + i * pitch / 10))
    b.tube(pts, rr, mat='rope', segs=6, jitter=0.06)


def round_window(b, r=0.26):
    """Local frame: wall plane y=0, outward -Y."""
    b.lathe([(r - 0.01, 0.02), (r, 0), (r + 0.085, 0), (r + 0.1, 0.02), (r + 0.1, 0.1), (r + 0.085, 0.125), (r, 0.125),
             (r - 0.01, 0.1), (r - 0.01, 0.02)], rot=(90, 0, 0), mat='wood_plank', segs=20, jitter=0.05)
    b.cyl(r, 0.012, loc=(0, -0.012, 0), rot=(90, 0, 0), mat='glass', segs=20, bevel=0.003)
    wood(b, (r * 2, 0.04, 0.04), loc=(0, -0.05, 0), bevel=0.008)
    wood(b, (0.04, 0.04, r * 2), loc=(0, -0.05, 0), bevel=0.008)
    mark(b, 'window_light', (0, -0.04, 0))


# ============================================================================================
# WINDMILL (smock mill: battered stone base, gallery, weatherboarded tower, gabled cap)
# ============================================================================================
T8 = math.tan(math.radians(22.5))
C8 = math.cos(math.radians(22.5))
WM_HUB = (0.0, -2.5, 9.5)


def build_sails():
    b = Builder('windmill_sails', seed=102)
    # hub (axle = local Y; front is -Y)
    b.cyl(0.3, 0.62, loc=(0, 0.27, 0), rot=(90, 0, 0), mat='wood_dark', segs=16, bevel=0.03)
    for yr in (0.2, -0.29):
        b.lathe([(0.29, -yr - 0.035), (0.318, -yr - 0.03), (0.318, -yr + 0.03), (0.29, -yr + 0.035)], rot=(90, 0, 0),
                mat='metal_dark', segs=16)
    b.lathe([(0.19, 0.33), (0.2, 0.36), (0.13, 0.46), (0, 0.5)], rot=(90, 0, 0), mat='wood_dark', segs=12)
    b.cyl(0.05, 0.05, loc=(0, -0.48, 0), rot=(90, 0, 0), mat='metal_dark', segs=8, bevel=0.01)
    rs = [1.0 + k * 0.495 for k in range(8)]

    def tw(r):
        return 16.0 - 12.0 * (r - rs[0]) / (rs[-1] - rs[0])

    def P(x, r, yo=-0.085):
        a = math.radians(tw(r))
        return (x * math.cos(a) - yo * math.sin(a), -0.12 + x * math.sin(a) + yo * math.cos(a), r)

    for i in range(4):
        with b.at(rot=(0, 90 * i + 20, 0)):
            # stock / whip
            wood(b, (0.16, 0.13, 4.85), loc=(0, -0.12, 2.3), mat='wood_dark', bevel=0.022, segs=2, taper=(0.62, 0.78))
            b.box((0.2, 0.17, 0.07), loc=(0, -0.12, 0.42), mat='metal_dark', bevel=0.012, segs=1)
            b.box((0.19, 0.16, 0.06), loc=(0, -0.12, 0.8), mat='metal_dark', bevel=0.012, segs=1)
            # sail bars
            for r in rs:
                with b.at(loc=(0, -0.12, r), rot=(0, 0, tw(r))):
                    wood(b, (1.3 + R(b, -0.02, 0.02), 0.035, 0.055), loc=(0.345, -0.085, 0), mat='wood_plank', bevel=0.008,
                         segs=1, jitter=0.14, rj=0.6)
            # uplongs (hem laths)
            for x in (0.97, 0.52, -0.28):
                strut(b, P(x, rs[0] - 0.12, -0.06), P(x, rs[-1] + 0.12, -0.06), w=0.05, d=0.032, mat='wood_plank', bevel=0.008,
                      jitter=0.14)
            # leading board
            with b.at(loc=(0, -0.12, 2.75), rot=(0, 0, 10)):
                wood(b, (0.19, 0.018, 3.56), loc=(-0.175, -0.05, 0), mat='wood_plank', bevel=0.006, jitter=0.12)
            # canvas, one panel per bay, laced behind the bars
            for k in range(len(rs) - 1):
                rm = (rs[k] + rs[k + 1]) / 2
                with b.at(loc=(0, -0.12, rm), rot=(R(b, -1.5, 1.5), 0, tw(rm))):
                    b.box((0.84, 0.014, rs[k + 1] - rs[k] - 0.008), loc=(0.525, -0.052, 0), mat='cloth', color=CREAM,
                          jitter=0.07, bevel=0, grain=None)
    return b.build(sharp_angle=50)


def build_windmill():
    b = Builder('windmill', seed=101)
    ZB = 3.0                        # stone base top
    ZS0, ZS1 = 3.1, 8.35            # smock
    B0, B1 = 1.95, 1.3

    def As(z):
        return 2.3 - 0.25 * z / ZB

    def Bs(z):
        return B0 + (B1 - B0) * (z - ZS0) / (ZS1 - ZS0)

    lean_s = math.degrees(math.atan(0.25 / ZB))
    lean_b = math.degrees(math.atan((B0 - B1) / (ZS1 - ZS0)))
    SL = (ZS1 - ZS0) / math.cos(math.radians(lean_b))

    # ---- stone base -----------------------------------------------------------------------
    b.lathe([(0, -0.05), ((As(0) - 0.18) / C8, -0.05), ((As(ZB) - 0.18) / C8, ZB), (0, ZB)], rot=(0, 0, 22.5), mat='stone',
            segs=8, color=MORTAR)
    for k in range(8):
        gaps = []
        if k == 0:
            gaps = [(-0.74, 0.74, -1, 2.32)]
        elif k in (2, 6):
            gaps = [(-0.42, 0.42, 1.22, 2.2)]
        with b.at(rot=(0, 0, 45 * k)):
            with b.at(loc=(0, -As(0), 0), rot=(-lean_s, 0, 0)):
                stone_courses(b, lambda s: (-T8 * As(s) + 0.14, T8 * As(s) - 0.14), -0.06, ZB, gaps=gaps, ch=(0.4, 0.54),
                              sw=(0.56, 0.95))
                if k == 0:
                    stone(b, (2.0, 0.44, 0.36), (0, 0.04, 2.56), bev=0.06, rj=0.6)
                elif k in (2, 6):
                    stone(b, (1.2, 0.42, 0.24), (0, 0.05, 2.36), bev=0.05, rj=0.6)
                    with b.at(loc=(0, -0.12, 1.7)):
                        window(b, w=0.6, h=0.8, shutters=True, sw=0.3, color=RED)
        # quoins
        with b.at(rot=(0, 0, 45 * k + 22.5)):
            with b.at(loc=(0, -As(0) / C8, 0), rot=(-lean_s / C8, 0, 0)):
                z = -0.06
                while z < ZB - 0.05:
                    h = min(R(b, 0.46, 0.62), ZB - z)
                    if ZB - (z + h) < 0.3:
                        h = ZB - z
                    stone(b, (R(b, 0.46, 0.62), 0.42, h - 0.015), (0, 0.1 + R(b, -0.02, 0.02), z + h / 2), segs=1, bev=0.06,
                          rj=1.5)
                    z += h
    tick(b, 'stone base')
    # entrance
    with b.at(loc=(0, -2.27, 0.14)):
        door(b, dw=1.0, dh=1.9, color=RED)
        with b.at(loc=(0.58, -0.07, 1.78)):
            bracket_lantern(b, 'windmill_lantern_light')
    for (cx, cy, sx_, sy_) in [(-0.45, -2.72, 0.95, 0.66), (0.5, -2.74, 0.9, 0.7)]:
        stone(b, (sx_, sy_, 0.18 + R(b, -0.02, 0.02)), (cx, cy, 0.05), bev=0.035, rj=1.2)
    stone(b, (1.34, 0.4, 0.26), (0, -2.42, 0.09), bev=0.04, rj=0.6)
    mark(b, 'windmill_door', (0, -3.5, 0))

    tick(b, 'entrance')
    # ---- gallery --------------------------------------------------------------------------
    GA0, GA1, ZG = 1.9, 2.86, 3.08
    RG = 2.76 / C8

    def corner(k, r=RG):
        a = math.radians(45 * k + 22.5)
        return Vector((r * math.sin(a), -r * math.cos(a), 0))

    for k in range(8):
        with b.at(rot=(0, 0, 45 * k)):
            n = 3
            for i in range(n):
                a0 = GA0 + (GA1 - GA0) * i / n + 0.005
                a1 = GA0 + (GA1 - GA0) * (i + 1) / n - 0.005
                flat_poly(b, [(-T8 * a0 + 0.004, -a0), (T8 * a0 - 0.004, -a0), (T8 * a1 - 0.004, -a1), (-T8 * a1 + 0.004, -a1)],
                          ZG + R(b, -0.004, 0.004), thick=0.06, bevel=0.012, jitter=0.16)
        with b.at(rot=(0, 0, 45 * k + 22.5)):
            strut(b, (0, -As(2.93) / C8 + 0.15, 2.95), (0, -2.84 / C8, 2.95), w=0.14, d=0.16, bevel=0.02)
            strut(b, (0, -As(1.95) / C8 - 0.06, 1.95), (0, -2.6 / C8, 2.86), w=0.11, d=0.11, bevel=0.018)
            wood(b, (0.13, 0.13, 1.2), loc=(0, -RG, ZG + 0.57), mat='wood_dark', bevel=0.02, segs=1, rj=0.6)
            wood(b, (0.12, 0.12, 0.06), loc=(0, -RG, ZG + 1.2), mat='wood_dark', bevel=0.018, segs=1, taper=(0.45, 0.45))
        p0, p1 = corner(k - 1), corner(k)
        mid = (p0 + p1) / 2
        zt, zl = ZG + 1.02, ZG + 0.2
        strut(b, p0 + Vector((0, 0, zt)), p1 + Vector((0, 0, zt)), w=0.085, d=0.075, mat='wood_plank')
        strut(b, p0 + Vector((0, 0, zl)), p1 + Vector((0, 0, zl)), w=0.07, d=0.07, mat='wood_plank')
        strut(b, p0 + Vector((0, 0, 2.98)), p1 + Vector((0, 0, 2.98)), w=0.07, d=0.15)
        strut(b, mid + Vector((0, 0, zl)), mid + Vector((0, 0, zt)), w=0.07, d=0.07, mat='wood_plank')
        for q in (p0, p1):
            strut(b, q + Vector((0, 0, zl + 0.03)), mid + Vector((0, 0, zt - 0.03)), w=0.045, d=0.05, mat='wood_plank',
                  bevel=0)
            strut(b, q + Vector((0, 0, zt - 0.03)), mid + Vector((0, 0, zl + 0.03)), w=0.045, d=0.05, mat='wood_plank',
                  bevel=0)

    tick(b, 'gallery')
    # ---- smock tower ----------------------------------------------------------------------
    b.lathe([(0, ZS0 - 0.1), ((B0 - 0.02) / C8, ZS0 - 0.1), ((B1 - 0.02) / C8, ZS1), (0, ZS1)], rot=(0, 0, 22.5),
            mat='wood_dark', segs=8, color=(0.45, 0.45, 0.45))
    wins = {0: [3.25], 2: [2.2], 6: [2.2], 4: [2.7]}
    for k in range(8):
        with b.at(rot=(0, 0, 45 * k)):
            with b.at(loc=(0, -B0, ZS0), rot=(-lean_b, 0, 0)):
                def hw(s):
                    return T8 * (B0 - s * math.sin(math.radians(lean_b)))

                gaps = [(-0.3, 0.3, s - 0.42, s + 0.38) for s in wins.get(k, [])]
                if k == 0:
                    gaps.append((-0.5, 0.5, -1, 1.78))
                s = 0.0
                while s < SL - 0.03:
                    h = min(0.34 + R(b, -0.015, 0.015), SL - s)
                    if SL - (s + h) < 0.12:
                        h = SL - s
                    sc = s + h / 2
                    w = hw(sc) - 0.06
                    parts = [(-w, w)]
                    for g0, g1, gs0, gs1 in gaps:
                        if gs0 < sc < gs1:
                            parts = [(-w, g0), (g1, w)]
                    if len(parts) == 1 and b.rng.random() < 0.18:
                        cx = R(b, -0.4, 0.4) * w
                        parts = [(-w, cx), (cx, w)]
                    for a0, a1 in parts:
                        b.box((a1 - a0 - 0.008, 0.03, h + 0.045), loc=((a0 + a1) / 2, -0.03, sc),
                              rot=(-6 + R(b, -1, 1), 0, R(b, -0.3, 0.3)), mat='wood_plank', bevel=0.008 if sc < 2.7 else 0, segs=1, grain=0,
                              jitter=0.16)
                    s += h
                # skirt + frieze
                wood(b, (2 * hw(0) + 0.06, 0.07, 0.24), loc=(0, -0.07, 0.06), rot=(-16, 0, 0), mat='wood_dark', bevel=0.015,
                     segs=1)
                wood(b, (2 * hw(SL) + 0.04, 0.08, 0.2), loc=(0, -0.05, SL - 0.08), mat='wood_dark', bevel=0.015, segs=1)
                for s_ in wins.get(k, []):
                    with b.at(loc=(0, -0.075, s_)):
                        window(b, w=0.5, h=0.7, shutters=False, fs=1)
                        wood(b, (0.86, 0.2, 0.05), loc=(0, -0.08, 0.455), rot=(14, 0, 0), mat='wood_dark', bevel=0.012, segs=1)
                if k == 0:
                    with b.at(loc=(0, -0.05, 0.02)):
                        door(b, dw=0.8, dh=1.66, color=RED, n=4, fs=1)
        with b.at(rot=(0, 0, 45 * k + 22.5)):
            strut(b, (0, -B0 / C8 + 0.03, ZS0 - 0.08), (0, -B1 / C8 + 0.03, ZS1 + 0.04), w=0.21, d=0.21, segs=2, bevel=0.024)

    tick(b, 'smock')
    # ---- cap ------------------------------------------------------------------------------
    CY, CL, CW = -0.15, 1.7, 1.25
    ZC0, ZC1 = 8.5, 9.2
    PC = 48.0
    TPC = math.tan(math.radians(PC))
    ZRC = ZC1 + 0.08 + CW * TPC
    b.lathe([(0, ZS1 - 0.02), (1.5, ZS1 - 0.02), (1.53, ZS1 + 0.01), (1.53, ZS1 + 0.14), (1.5, ZS1 + 0.17), (0, ZS1 + 0.17)],
            mat='wood_dark', segs=16, jitter=0.05)
    b.box((2 * CW + 0.1, 2 * CL + 0.1, 0.16), loc=(0, CY, ZC0 + 0.02), mat='wood_dark', bevel=0.02, segs=2, grain=1)
    b.box((2 * CW - 0.1, 2 * CL - 0.1, ZC1 - ZC0), loc=(0, CY, (ZC0 + ZC1) / 2), mat='wood_dark', bevel=0.01, segs=1, grain=None,
          color=(0.4, 0.4, 0.4))
    b.prism([(-CW + 0.05, ZC1 - 0.05), (CW - 0.05, ZC1 - 0.05), (0, ZRC - 0.2)], 2 * CL - 0.1, loc=(0, CY, 0), mat='wood_dark',
            bevel=0.01, segs=1, color=(0.4, 0.4, 0.4))
    for sx in (-1, 1):
        with b.at(loc=(sx * CW, CY, 0), rot=(0, 0, sx * 90)):
            vplanks(b, -CL, CL, ZC0 + 0.08, lambda x: ZC1 + 0.02, pw=0.3, mat='wood_light')
        for sy in (-1, 1):
            wood(b, (0.15, 0.15, ZC1 - ZC0), loc=(sx * (CW - 0.03), CY + sy * (CL - 0.03), (ZC0 + ZC1) / 2 + 0.05), mat='wood_dark',
                 bevel=0.02, segs=2)
    for sy, yaw in ((-1, 0), (1, 180)):
        with b.at(loc=(0, CY + sy * CL, 0), rot=(0, 0, yaw)):
            vplanks(b, -CW + 0.06, CW - 0.06, ZC0 + 0.08, lambda x: ZC1 + 0.02 + (CW - abs(x)) * TPC - 0.06, pw=0.3,
                    mat='wood_light', apex=0.0)
            beam(b, -CW, ZC1 + 0.02, CW, ZC1 + 0.02, w=0.14, depth=0.12, y=0.02)
            if sy == 1:
                with b.at(loc=(0, -0.03, ZC1 + 0.52)):
                    round_window(b, 0.2)
    gable_roof(b, (0, CY - 0.1, ZRC), 2 * CL + 0.4, CW + 0.32, PC, yaw=90, row_h=0.39, sw=(0.42, 0.62), cap=1.05)
    for sy in (-1, 1):
        wood(b, (0.1, 0.1, 0.5), loc=(0, CY - 0.1 + sy * (CL + 0.2), ZRC + 0.14), mat='wood_dark', bevel=0.02, segs=2,
             taper=(0.5, 0.5))
    # windshaft, breast beam, overhang brackets
    ZH = WM_HUB[2]
    b.cyl(0.17, 0.56, loc=(0, CY - CL + 0.08, ZH), rot=(90, 0, 0), mat='wood_dark', segs=14, bevel=0.02)
    b.lathe([(0.17, -0.03), (0.3, -0.03), (0.32, 0.0), (0.3, 0.07), (0.17, 0.07)], loc=(0, CY - CL - 0.02, ZH), rot=(90, 0, 0),
            mat='wood_dark', segs=14)
    for sx in (-1, 1):
        strut(b, (sx * 0.5, -Bs(7.75) - 0.02, 7.75), (sx * 0.5, CY - CL + 0.1, ZC0 - 0.04), w=0.12, d=0.12, segs=2, bevel=0.018)
        strut(b, (sx * 0.5, Bs(7.75) + 0.02, 7.75), (sx * 0.5, CY + CL - 0.1, ZC0 - 0.04), w=0.12, d=0.12, segs=2, bevel=0.018)
    mark(b, 'windmill_hub', WM_HUB)
    tick(b, 'cap')

    obj = b.build(sharp_angle=50)
    sails = build_sails()
    kit.set_parent(sails, obj, WM_HUB)
    return obj


# ============================================================================================
# HENHOUSE (raised coop + fenced run in front)
# ============================================================================================
def build_henhouse():
    b = Builder('henhouse', seed=202)
    CY = 1.5                        # coop centre; run spans y -2.7 .. 0.3
    HX, HY = 1.5, 1.2
    ZF, WT = 0.7, 1.9
    P = 38.0
    TP = math.tan(math.radians(P))
    ZR = WT + 0.08 + HY * TP
    XD, XW, ZW = -0.75, 0.62, 1.4

    # ---- legs + floor frame ---------------------------------------------------------------
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = sx * (HX - 0.06), CY + sy * (HY - 0.06)
            stone(b, (0.42, 0.42, 0.16), (px, py, 0.04), bev=0.05, rj=3)
            wood(b, (0.17, 0.17, WT - 0.06), loc=(px, py, 0.1 + (WT - 0.06) / 2), mat='wood_dark', bevel=0.022, segs=2, rj=0.5)
            strut(b, (px, py - sy * 0.04, 0.22), (px - sx * 0.42, py - sy * 0.04, ZF - 0.12), w=0.08, d=0.08, bevel=0.014)
            strut(b, (px - sx * 0.04, py, 0.22), (px - sx * 0.04, py - sy * 0.42, ZF - 0.12), w=0.08, d=0.08, bevel=0.014)
    for sy in (-1, 1):
        wood(b, (2 * HX + 0.12, 0.13, 0.16), loc=(0, CY + sy * (HY - 0.03), ZF - 0.07), mat='wood_dark', bevel=0.02, segs=2, rj=0.3)
        wood(b, (2 * HX + 0.3, 0.1, 0.1), loc=(0, CY + sy * (HY + 0.0), WT + 0.0), mat='wood_dark', bevel=0.016, segs=2)
    for sx in (-1, 1):
        wood(b, (0.13, 2 * HY + 0.12, 0.16), loc=(sx * (HX - 0.03), CY, ZF - 0.07), mat='wood_dark', bevel=0.02, segs=2, rj=0.3)
    b.box((2 * HX - 0.1, 2 * HY - 0.1, 0.07), loc=(0, CY, ZF - 0.04), mat='wood_plank', bevel=0.01, segs=1, grain=0)
    # dark inner shell so plank joints read as shadow
    dk = (0.32, 0.32, 0.32)
    b.box((2 * HX - 0.09, 2 * HY - 0.09, WT - ZF), loc=(0, CY, (WT + ZF) / 2), mat='wood_dark', bevel=0.005, segs=1, grain=None, color=dk)
    b.prism([(-HY + 0.045, WT - 0.02), (HY - 0.045, WT - 0.02), (0, ZR - 0.14)], 2 * HX - 0.09, loc=(0, CY, 0), rot=(0, 0, 90),
            mat='wood_dark', bevel=0.005, segs=1, color=dk)

    tick(b, 'legs')
    # ---- walls ----------------------------------------------------------------------------
    with b.at(loc=(0, CY - HY, 0)):                                   # front
        vplanks(b, -HX + 0.14, HX - 0.14, ZF - 0.03, lambda x: WT - 0.03, pw=0.2,
                gaps=[(XD - 0.23, XD + 0.23, ZF - 0.2, ZF + 0.58), (XW - 0.3, XW + 0.3, ZW - 0.25, ZW + 0.25)])
        # pop door with sliding hatch
        b.box((0.46, 0.02, 0.6), loc=(XD, 0.03, ZF + 0.29), mat='wood_dark', bevel=0, grain=None, color=(0.12, 0.12, 0.12))
        for sx in (-1, 1):
            wood(b, (0.06, 0.07, 1.2), loc=(XD + sx * 0.26, -0.05, ZF + 0.56), mat='wood_dark', bevel=0.012, segs=2)
        wood(b, (0.62, 0.07, 0.06), loc=(XD, -0.05, ZF + 1.15), mat='wood_dark', bevel=0.012, segs=2)
        wood(b, (0.66, 0.2, 0.045), loc=(XD, -0.1, ZF - 0.02), mat='wood_dark', bevel=0.012, segs=2)
        for i in range(3):
            b.box((0.148, 0.025, 0.6), loc=(XD - 0.152 + i * 0.152, -0.05, ZF + 0.8), mat='paint', color=TEAL, jitter=0.1,
                  bevel=0.008, segs=1, grain=2)
        b.box((0.42, 0.02, 0.06), loc=(XD, -0.07, ZF + 0.62), mat='paint', color=tint(TEAL, 0.8), bevel=0.006, segs=1)
        b.tube([(XD, -0.07, ZF + 1.1), (XD, -0.075, WT - 0.02)], 0.008, mat='rope', segs=6)
        b.cyl(0.03, 0.03, loc=(XD, -0.06, WT - 0.03), rot=(90, 0, 0), mat='wood_light', segs=10, bevel=0.006)
        with b.at(loc=(XW, -0.035, ZW)):
            window(b, w=0.56, h=0.46, shutters=True, sw=0.28, color=TEAL)
    with b.at(loc=(0, CY + HY, 0), rot=(0, 0, 180)):                  # back
        vplanks(b, -HX + 0.14, HX - 0.14, ZF - 0.03, lambda x: WT - 0.03, pw=0.2)
    for sx in (-1, 1):                                               # gable ends
        with b.at(loc=(sx * HX, CY, 0), rot=(0, 0, sx * 90)):
            vplanks(b, -HY + 0.14, HY - 0.14, ZF - 0.03, lambda x: WT + 0.05 + (HY - abs(x)) * TP - 0.06, pw=0.2, apex=0.0)
            # vent
            b.cyl(0.1, 0.02, loc=(0, -0.03, WT + 0.42), rot=(90, 0, 0), mat='wood_dark', segs=12, bevel=0.003, color=(0.12, 0.12, 0.12))
            b.lathe([(0.1, 0), (0.15, 0), (0.16, 0.012), (0.16, 0.035), (0.15, 0.045), (0.1, 0.045)], loc=(0, -0.035, WT + 0.42),
                    rot=(90, 0, 0), mat='wood_dark', segs=12)
            if sx == -1:
                # clean-out door: trim, Z-brace, strap hinges, latch
                x0, x1, z0, z1 = -0.42, 0.32, ZF + 0.02, ZF + 1.08
                for xx in (x0, x1):
                    wood(b, (0.06, 0.03, z1 - z0 + 0.06), loc=(xx, -0.05, (z0 + z1) / 2), mat='wood_dark', bevel=0.01, segs=2)
                for zz in (z0, z1):
                    wood(b, (x1 - x0 + 0.06, 0.03, 0.06), loc=((x0 + x1) / 2, -0.052, zz), mat='wood_dark', bevel=0.01, segs=2)
                for zz in (z0 + 0.2, z1 - 0.2):
                    wood(b, (x1 - x0 - 0.08, 0.028, 0.1), loc=((x0 + x1) / 2, -0.05, zz), bevel=0.01, segs=2, jitter=0.14)
                    b.box((0.34, 0.012, 0.045), loc=(x0 + 0.2, -0.07, zz), mat='metal_dark', bevel=0.004, segs=1)
                    b.cyl(0.02, 0.1, loc=(x0 + 0.0, -0.07, zz - 0.05), mat='metal_dark', segs=8, bevel=0.004)
                strut(b, (x0 + 0.08, -0.05, z0 + 0.25), (x1 - 0.08, -0.05, z1 - 0.25), w=0.028, d=0.09, mat='wood_plank', bevel=0.01)
                b.box((0.16, 0.014, 0.04), loc=(x1 - 0.02, -0.075, (z0 + z1) / 2), mat='metal_dark', bevel=0.004, segs=1)
                b.cyl(0.018, 0.03, loc=(x1 - 0.08, -0.07, (z0 + z1) / 2), rot=(90, 0, 0), mat='metal_dark', segs=8, bevel=0.003)
            else:
                # nest box with hinged lid
                wood(b, (1.4, 0.52, 0.035), loc=(0, -0.26, 1.0), bevel=0.01, segs=2)
                for zz, hh in ((1.115, 0.2), (1.325, 0.21)):
                    wood(b, (1.4 + R(b, -0.01, 0.01), 0.03, hh), loc=(0, -0.5, zz), bevel=0.01, segs=2, jitter=0.14, rj=0.4)
                for ex in (-1, 1):
                    with b.at(loc=(ex * 0.7, 0, 0), rot=(0, 0, 90)):
                        b.prism([(-0.52, 1.0), (0, 1.0), (0, 1.6), (-0.52, 1.44)], 0.035, mat='wood_plank', bevel=0.008, segs=1,
                                jitter=0.14, grain=0)
                    strut(b, (ex * 0.55, -0.03, 0.72), (ex * 0.55, -0.44, 0.985), w=0.06, d=0.07, bevel=0.012)
                    wood(b, (0.05, 0.05, 0.5), loc=(ex * 0.7, -0.5, 1.2), mat='wood_dark', bevel=0.01, segs=1)
                with b.at(loc=(0, -0.01, 1.645), rot=(11, 0, 0)):
                    for yy in (-0.165, -0.47):
                        b.box((1.54 + R(b, -0.01, 0.01), 0.295, 0.032), loc=(0, yy, 0), mat='wood_light', bevel=0.01, segs=2,
                              grain=0, jitter=0.14)
                    for ex in (-0.45, 0.45):
                        b.box((0.05, 0.3, 0.012), loc=(ex, -0.16, 0.022), mat='metal_dark', bevel=0.004, segs=1)
                        b.cyl(0.02, 0.11, loc=(ex - 0.055, 0.0, 0.02), rot=(0, 90, 0), mat='metal_dark', segs=8, bevel=0.004)
                    b.box((0.05, 0.012, 0.09), loc=(0, -0.625, -0.03), mat='metal_dark', bevel=0.004, segs=1)
                    b.box((0.05, 0.06, 0.012), loc=(0, -0.6, 0.022), mat='metal_dark', bevel=0.004, segs=1)
                for ex in (-0.45, 0.45):
                    b.box((0.05, 0.012, 0.13), loc=(ex, -0.04, 1.7), mat='metal_dark', bevel=0.004, segs=1)
                for _ in range(10):
                    b.leaf(R(b, 0.08, 0.16), 0.016, loc=(R(b, -0.6, 0.6), -0.51, 1.44), rot=(R(b, -20, 20), -(100 + R(b, -30, 30)), 90),
                           mat='straw', bend=R(b, 10, 50), segs=2, jitter=0.2)

    tick(b, 'walls')
    # ---- roof -----------------------------------------------------------------------------
    gable_roof(b, (0, CY, ZR), 2 * HX + 0.7, HY + 0.3, P, row_h=0.33, sw=(0.34, 0.5), thick=0.042, cap=0.9)

    tick(b, 'roof')
    # ---- ramp -----------------------------------------------------------------------------
    ry0, run = CY - HY - 0.16, 1.62
    ang = math.degrees(math.atan2(ZF - 0.03, run))
    Lr = math.hypot(run, ZF - 0.03)
    with b.at(loc=(XD, ry0, ZF - 0.02), rot=(ang, 0, 0)):
        for sx in (-1, 1):
            wood(b, (0.185, Lr + R(b, -0.02, 0.03), 0.032), loc=(sx * 0.095, -Lr / 2, -0.016), bevel=0.008, segs=2, jitter=0.14,
                 grain=1)
            wood(b, (0.04, Lr - 0.05, 0.05), loc=(sx * 0.15, -Lr / 2, -0.055), mat='wood_dark', bevel=0.01, grain=1)
        i = 0
        y = -0.16
        while y > -Lr + 0.05:
            wood(b, (0.37 + R(b, -0.01, 0.01), 0.035, 0.022), loc=(0, y, 0.008), mat='wood_dark', bevel=0.006, rj=1.5)
            y -= 0.19
            i += 1
    mark(b, 'henhouse_door', (XD, ry0 - run - 0.25, 0))

    # ---- run ------------------------------------------------------------------------------
    Y0, Y1, XR = -2.7, CY - HY, 2.0
    ZT, ZL = 1.04, 0.13

    def post(x, y, h=1.22):
        with b.at(loc=(x, y, 0), rot=(R(b, -1.5, 1.5), R(b, -1.5, 1.5), R(b, -4, 4))):
            wood(b, (0.115, 0.115, h + 0.1), loc=(0, 0, h / 2 - 0.05), bevel=0.018, segs=1, taper=(0.9, 0.9), jitter=0.12)
            wood(b, (0.105, 0.105, 0.06), loc=(0, 0, h + 0.03), bevel=0.016, segs=1, taper=(0.4, 0.4), jitter=0.12)

    def panel(p0, p1):
        p0, p1 = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
        d = p1 - p0
        W = d.length
        with b.at(loc=tuple(p0), rot=(0, 0, math.degrees(math.atan2(d.y, d.x)))):
            wood(b, (W - 0.06, 0.05, 0.07), loc=(W / 2, 0, ZT), bevel=0.012, segs=1, jitter=0.12, rj=0.5)
            wood(b, (W - 0.06, 0.05, 0.07), loc=(W / 2, 0, ZL), bevel=0.012, segs=1, jitter=0.12, rj=0.5)
            with b.at(loc=(0.055, 0, 0)):
                lattice(b, W - 0.11, ZL + 0.03, ZT - 0.03, step=0.27)

    xs = [-2.0, -1.0, 0.0, 1.0, 2.0]
    for x in xs:
        post(x, Y0)
    for sx in (-1, 1):
        ys = [Y0, -1.7, -0.7, Y1]
        for y in ys[1:]:
            post(sx * XR, y)
        for i in range(3):
            panel((sx * XR, ys[i]), (sx * XR, ys[i + 1]))
        panel((sx * XR, Y1), (sx * (HX + 0.02), Y1))
    for i in (0, 1, 3):
        panel((xs[i], Y0), (xs[i + 1], Y0))
    # gate (between x=0 and x=1), a touch ajar
    with b.at(loc=(0.075, Y0 - 0.02, 0), rot=(0, 0, -9)):
        GW = 0.84
        for xx in (0.03, GW - 0.03):
            wood(b, (0.06, 0.045, 0.98), loc=(xx, 0, 0.6), bevel=0.012, segs=2, jitter=0.12)
        for zz in (0.15, 1.05):
            wood(b, (GW - 0.1, 0.045, 0.07), loc=(GW / 2, 0, zz), bevel=0.012, segs=2, jitter=0.12)
        with b.at(loc=(0.06, 0.012, 0)):
            lattice(b, GW - 0.12, 0.19, 1.01, step=0.27)
        strut(b, (0.07, -0.03, 0.2), (GW - 0.07, -0.03, 1.0), w=0.025, d=0.07, mat='wood_plank', bevel=0.01)
        for zz in (0.25, 0.95):
            b.box((0.26, 0.012, 0.04), loc=(0.12, -0.03, zz), mat='metal_dark', bevel=0.004, segs=1)
            b.cyl(0.018, 0.09, loc=(-0.02, -0.02, zz - 0.045), mat='metal_dark', segs=8, bevel=0.004)
        b.box((0.16, 0.012, 0.035), loc=(GW - 0.04, -0.03, 0.62), mat='metal_dark', bevel=0.004, segs=1)
        ring = [(GW + 0.03 + 0.035 * math.cos(a), -0.035, 0.6 + 0.035 * math.sin(a)) for a in [i * 2 * math.pi / 10 for i in range(11)]]
        b.tube(ring, 0.006, mat='metal_dark', segs=6, caps=False)
    mark(b, 'henhouse_run', (0, (Y0 + Y1) / 2, 0))

    tick(b, 'ramp+run')
    # ---- life in the run ------------------------------------------------------------------
    with b.at(loc=(1.15, -1.25, 0), rot=(0, 0, 24)):                  # feed trough
        for sy in (-1, 1):
            wood(b, (0.9, 0.025, 0.15), loc=(0, sy * 0.07, 0.13), rot=(-sy * 26, 0, 0), mat='wood_light', bevel=0.008, segs=2, jitter=0.14)
        for ex in (-1, 1):
            b.prism([(-0.14, 0.0), (0.14, 0.0), (0.12, 0.2), (-0.12, 0.2)], 0.03, loc=(ex * 0.44, 0, 0), rot=(0, 0, 90),
                    mat='wood_plank', bevel=0.008, segs=1, jitter=0.12)
        b.box((0.84, 0.13, 0.03), loc=(0, 0, 0.15), mat='straw', bevel=0.012, segs=1, grain=0, jitter=0.1)
    with b.at(loc=(-1.35, -2.0, 0)):                                  # water pan
        b.lathe([(0, 0), (0.2, 0), (0.24, 0.02), (0.26, 0.09), (0.245, 0.09), (0.22, 0.035), (0, 0.03)], mat='metal', segs=18)
        b.cyl(0.235, 0.012, loc=(0, 0, 0.062), mat='water_still', segs=18, bevel=0.003)
    with b.at(loc=(1.3, -0.3, 0), rot=(0, 0, -8)):                    # perch
        for ex in (-1, 1):
            wood(b, (0.07, 0.07, 0.56), loc=(ex * 0.42, 0, 0.26), bevel=0.012, segs=2, rj=2)
        pole(b, (-0.56, 0, 0.5), (0.56, 0, 0.5), r=0.028, n=4)
    for _ in range(46):
        x, y = b.rng.choice([(XD + R(b, -0.6, 0.6), R(b, -1.9, -0.6)), (R(b, -1.2, 1.2), CY + R(b, -0.9, 0.9)), (1.15 + R(b, -0.5, 0.5), -1.25 + R(b, -0.4, 0.4))])
        b.leaf(R(b, 0.1, 0.22), 0.016, loc=(x, y, 0.012), rot=(0, 84 + R(b, -5, 5), R(b, 0, 360)), mat='straw', bend=R(b, -8, 8),
               segs=2, jitter=0.22)
    return b.build(sharp_angle=50)


# ============================================================================================
# BAKEHOUSE
# ============================================================================================
def build_bakehouse():
    b = Builder('bakehouse', seed=303)
    HX, HY = 2.2, 1.9
    WT = 2.75
    ZS = 1.05                       # top of the stone plinth wall
    PITCH = 44.0
    TP = math.tan(math.radians(PITCH))
    ZR = WT + 0.1 + HY * TP
    XD, XW = -1.05, 0.8
    OX = -0.7                       # body offset so the whole footprint (with the oven) is centred
    OVX, OVY = HX + 0.55, -0.4      # oven centre
    CHX, CHY = HX + 0.3, 0.98       # chimney centre

    def keep_main(p):
        return not (p.x - OX > HX - 0.2 and CHY - 0.56 < p.y < CHY + 0.56)

    with b.at(loc=(OX, 0, 0)):
        # ---- body -------------------------------------------------------------------------
        b.box((2 * HX - 0.16, 2 * HY - 0.16, WT - ZS + 0.15), loc=(0, 0, (WT + ZS - 0.15) / 2), mat='plaster', bevel=0.02, segs=1,
              grain=None)
        b.box((2 * HX - 0.5, 2 * HY - 0.5, ZS + 0.05), loc=(0, 0, ZS / 2 - 0.025), mat='stone', bevel=0.02, segs=1, grain=None,
              color=MORTAR)
        gz = ZR - 0.075
        hg = HY - 0.05
        gab = [(-hg, WT - 0.1), (hg, WT - 0.1), (hg, gz - hg * TP), (0, gz), (-hg, gz - hg * TP)]
        for sx in (-1, 1):
            b.prism(gab, 0.2, loc=(sx * (HX - 0.18), 0, 0), rot=(0, 0, 90), mat='plaster', bevel=0.012, segs=1)

        walls = {'front': ((0, -HY, 0), 0, HX), 'right': ((HX, 0, 0), 90, HY), 'back': ((0, HY, 0), 180, HX),
                 'left': ((-HX, 0, 0), -90, HY)}
        # ---- stone plinth -----------------------------------------------------------------
        for name, (loc, yaw, half) in walls.items():
            gaps = []
            if name == 'front':
                gaps = [(XD - 0.64, XD + 0.64, -1, 9)]
            elif name == 'right':
                gaps = [(CHY - 0.42, CHY + 0.42, -1, 9), (OVY - 0.75, OVY + 0.75, -1, 9)]
            with b.at(loc=loc, rot=(0, 0, yaw)):
                stone_courses(b, (-half + 0.3, half - 0.3), -0.06, ZS, y=0.07, depth=0.42, ch=(0.3, 0.4), sw=(0.5, 0.9), gaps=gaps)
        for sx in (-1, 1):
            for sy in (-1, 1):
                z = -0.06
                for h in (0.4, 0.34, 0.37):
                    s = R(b, 0.56, 0.66)
                    stone(b, (s, s + R(b, -0.06, 0.06), h - 0.012), (sx * (HX - 0.12), sy * (HY - 0.12), z + h / 2), bev=0.07, segs=1, rj=2)
                    z += h
        tick(b, 'body+plinth')
        # ---- timber frame -----------------------------------------------------------------
        for sx in (-1, 1):
            for sy in (-1, 1):
                wood(b, (0.23, 0.23, WT - ZS - 0.02), loc=(sx * (HX - 0.105), sy * (HY - 0.105), (WT + ZS) / 2 + 0.03), mat='wood_dark',
                     bevel=0.022, segs=2, rj=0.4)
        ZB, ZP = ZS + 0.09, WT - 0.08
        with b.at(loc=walls['front'][0]):
            beam(b, -HX, ZB, XD - 0.58, ZB)
            beam(b, XD + 0.58, ZB, HX, ZB)
            beam(b, -HX - 0.06, ZP, HX + 0.06, ZP)
            beam(b, -0.22, ZB + 0.09, -0.22, ZP - 0.09)
            beam(b, 1.86, ZB + 0.09, 1.86, ZP - 0.09, w=0.15)
            beam(b, -1.78, ZB + 0.12, -2.06, ZP - 0.14, w=0.13)
            for dx in (-0.3, 0.3):
                beam(b, XW + dx, ZB + 0.09, XW + dx, 1.4, w=0.12)
            with b.at(loc=(XD, 0, 0.2)):
                door(b, dw=0.95, dh=1.82, color=SAGE)
            with b.at(loc=(XW, 0.08, 1.9)):
                window(b, w=0.8, h=0.9, flower_box=True, color=SAGE, nflowers=6)
            # door step
            stone(b, (1.3, 0.5, 0.34), (XD, -0.12, 0.05), bev=0.04, rj=0.6)
            for (cx, sx_, sy_) in [(-0.4, 0.85, 0.6), (0.44, 0.8, 0.64)]:
                stone(b, (sx_, sy_, 0.16 + R(b, -0.02, 0.02)), (XD + cx, -0.66, 0.03), bev=0.035, rj=1.2)
            # awning
            ZA, PA, RA = 2.38, 20.0, 1.02
            gable_roof(b, (XD, -0.03, ZA), 1.85, RA, PA, sides=(0,), cap=0, row_h=0.27, sw=(0.26, 0.4), thick=0.04)
            wood(b, (1.8, 0.07, 0.12), loc=(XD, -0.03, ZA - 0.1), mat='wood_dark', bevel=0.014, segs=2)
            for sx in (-1, 1):
                x = XD + sx * 0.78
                ze = ZA - RA * math.tan(math.radians(PA))
                strut(b, (x, -0.0, ZA - 0.11), (x, -RA + 0.04, ze - 0.09), w=0.08, d=0.1)
                strut(b, (x, -0.02, 1.62), (x, -RA + 0.2, ze - 0.06), w=0.08, d=0.08)
                wood(b, (0.1, 0.06, 0.6), loc=(x, -0.02, 1.86), mat='wood_dark', bevel=0.014, segs=2)
            # hanging pretzel sign on the left corner post
            sx0, sz0 = -HX + 0.1, 2.22
            strut(b, (sx0, 0.0, sz0), (sx0, -0.78, sz0 + 0.03), w=0.07, d=0.08, segs=2)
            strut(b, (sx0, -0.0, sz0 - 0.4), (sx0, -0.42, sz0 - 0.03), w=0.05, d=0.05)
            with b.at(loc=(sx0, -0.47, sz0 - 0.42), rot=(0, 0, 90 + 4)):
                for ex in (-1, 1):
                    b.tube([(ex * 0.14, 0, 0.41), (ex * 0.14, 0, 0.24)], 0.007, mat='metal_dark', segs=6)
                b.cyl(0.27, 0.035, loc=(0, 0.0175, 0), rot=(90, 0, 0), mat='wood_light', segs=20, bevel=0.01, jitter=0.05)
                b.lathe([(0.25, -0.026), (0.285, -0.024), (0.285, 0.024), (0.25, 0.026)], loc=(0, 0.0, 0), rot=(90, 0, 0),
                        mat='wood_dark', segs=20)
                pz = [(0.45, -0.75), (0.12, -0.3), (-0.35, 0.05), (-0.8, 0.2), (-0.97, 0.55), (-0.72, 0.9), (-0.32, 0.9),
                      (0, 0.6), (0.32, 0.9), (0.72, 0.9), (0.97, 0.55), (0.8, 0.2), (0.35, 0.05), (-0.12, -0.3), (-0.45, -0.75)]
                gold = srgb(196, 128, 58)
                for sy in (-1, 1):
                    pts = [(x * 0.17, sy * (0.03 + (0.014 if i < 3 else 0.0)), z * 0.17 - 0.02) for i, (x, z) in enumerate(pz)]
                    b.tube(pts, 0.022, mat='paint', segs=6, color=gold, jitter=0.05)
            with b.at(loc=(XD + 0.74, -0.06, 1.98)):
                bracket_lantern(b, 'bakehouse_lantern_light')
            mark(b, 'bakehouse_door', (XD, -1.6, 0))
            # flour sacks by the door
            with b.at(loc=(-0.2, -0.42, 0), rot=(0, 0, 20)):
                sack(b)
            with b.at(loc=(0.33, -0.4, 0), rot=(0, 0, -35)):
                sack(b, c=tint(FLOUR, 0.94), s=0.92, patch=False)
            with b.at(loc=(0.08, -0.86, 0.19), rot=(82, 0, 62)):
                sack(b, c=tint(FLOUR, 1.02), s=0.9, patch=False)
            # bread peel leaning by the oven side
            pole(b, (1.72, -0.5, 0.02), (1.8, -0.22, 1.5), r=0.019, mat='wood_light')
            with b.at(loc=(1.805, -0.2, 1.5), rot=(-10, 0, 0)):
                b.prism([(-0.04, -0.02), (0.04, -0.02), (0.12, 0.08), (0.125, 0.3), (0.08, 0.38), (-0.08, 0.38), (-0.125, 0.3),
                         (-0.12, 0.08)], 0.018, mat='wood_light', bevel=0.006, segs=1, grain=2, jitter=0.1)
        tick(b, 'front wall')
        with b.at(loc=walls['back'][0], rot=(0, 0, 180)):
            beam1(b, -HX, ZB, HX, ZB)
            beam1(b, -HX - 0.06, ZP, HX + 0.06, ZP)
            for x in (-0.75, 1.0):
                beam1(b, x, ZB + 0.09, x, ZP - 0.09)
            beam1(b, -2.0, ZB + 0.12, -0.9, ZP - 0.14, w=0.14)
            beam1(b, 2.0, ZB + 0.12, 1.15, ZP - 0.14, w=0.14)
            with b.at(loc=(0.1, 0.08, 1.9)):
                window(b, w=0.8, h=0.9, shutters=False)
        for name in ('left', 'right'):
            loc, yaw, half = walls[name]
            with b.at(loc=loc, rot=(0, 0, yaw)):
                if name == 'left':
                    beam1(b, -HY, ZB, HY, ZB)
                    for x in (-1.05, 1.05):
                        beam1(b, x, ZB + 0.09, x, ZP - 0.09)
                    beam1(b, -1.2, ZB + 0.12, -1.66, ZP - 0.14, w=0.14)
                    beam1(b, 1.2, ZB + 0.12, 1.66, ZP - 0.14, w=0.14)
                    with b.at(loc=(0, 0.08, 1.9)):
                        window(b, w=0.7, h=0.9, color=SAGE, sw=0.34)
                    with b.at(loc=(0, 0.065, WT + 0.62)):
                        round_window(b, 0.22)
                    with b.at(loc=(0.0, -0.5, 0)):
                        woodpile(b, rows=((4, 0.125, 0.05), (4, 0.115, 0.26), (3, 0.105, 0.44)))
                else:
                    beam1(b, -HY, ZB, OVY - 0.8, ZB)
                    beam1(b, CHY + 0.4, ZB, HY, ZB)
                    beam1(b, -1.0, ZB + 0.3, -1.6, ZP - 0.14, w=0.14)
                beam1(b, -HY - 0.05, ZP, HY + 0.05, ZP)
                zc = WT + 0.82
                wc = (gz - zc) / TP - 0.12
                beam1(b, -wc, zc, wc, zc, w=0.16)
                beam1(b, 0, zc + 0.08, 0, gz - 0.12, w=0.15)
                if name == 'right':
                    beam1(b, 0, WT, 0, zc - 0.08, w=0.15)
                for s in (-1, 1):
                    beam1(b, s * (HY - 0.6), WT + 0.02, s * 0.3, zc - 0.1, w=0.12)

        tick(b, 'other walls')
        # ---- chimney ----------------------------------------------------------------------
        with b.at(loc=(CHX, CHY, 0)):
            stone_stack(b, 0.42, ZR + 0.8, WT + 0.3, name='bakehouse_smoke')

        tick(b, 'chimney')
        # ---- bread oven -------------------------------------------------------------------
        with b.at(loc=(OVX, OVY, 0)):
            ZO = 0.84
            b.lathe([(0, -0.05), (0.84, -0.05), (0.84, ZO - 0.03), (0, ZO - 0.03)], mat='stone', segs=20, color=MORTAR)
            stone_ring(b, 0.86, -0.05, 0.74, ch=(0.22, 0.3), da=(0.48, 0.75), depth=0.3)
            n = 11
            for i in range(n):
                am = (i + R(b, -0.12, 0.12)) * 2 * math.pi / n
                stone(b, (2 * math.pi * 0.98 / n - 0.012, 0.46, 0.12), (0.84 * math.cos(am), 0.84 * math.sin(am), ZO - 0.07),
                      rot0=(0, 0, math.degrees(am) + 90), bev=0.035, rj=1.5, segs=1)
            # pier under the hearth
            stone(b, (0.5, 0.62, 0.4), (-0.24, -1.2, 0.15), bev=0.06, rj=2, segs=1)
            stone(b, (0.46, 0.6, 0.4), (0.25, -1.22, 0.15), bev=0.06, rj=2, segs=1)
            stone(b, (0.62, 0.58, 0.36), (0.12, -1.2, 0.53), bev=0.06, rj=2, segs=1)
            stone(b, (0.36, 0.56, 0.36), (-0.34, -1.2, 0.53), bev=0.06, rj=2, segs=1)
            stone(b, (1.12, 0.84, 0.12), (0, -1.16, ZO - 0.06), bev=0.035, rj=0.8)
            # clay dome
            b.blob((0.93, 0.93, 1.0), loc=(0, 0, ZO - 0.02), mat='clay', subdiv=4, noise_amp=0.035, noise_scale=2.2,
                   flatten_bottom=0.0, color=(0.9, 0.88, 0.86), color_top=(1.05, 1.03, 1.0))
            nb = 20
            for i in range(nb):
                am = (i + 0.5) * 2 * math.pi / nb
                if abs(((am + math.pi / 2 + math.pi) % (2 * math.pi)) - math.pi) < 0.5:
                    continue
                b.box((2 * math.pi * 0.95 / nb - 0.014, 0.13, 0.085), loc=(0.9 * math.cos(am), 0.9 * math.sin(am), ZO + 0.04),
                      rot=(R(b, -2, 2), R(b, -2, 2), math.degrees(am) + 90 + R(b, -2, 2)), mat='brick', bevel=0.012, segs=1,
                      grain=None, jitter=0.2)
            # mouth: brick arch tunnel
            with b.at(loc=(0, -0.9, ZO)):
                ri, rt = 0.27, 0.19
                zj = 0.2
                nv = 9
                for i in range(nv):
                    a = math.pi * (i + 0.5) / nv
                    rr = ri + rt / 2 + (0.03 if i == nv // 2 else 0)
                    b.box((rt + (0.06 if i == nv // 2 else 0), 0.52 + R(b, -0.02, 0.02), 2 * (ri + rt / 2) * math.sin(math.pi / nv / 2) * 1.0 - 0.012),
                          loc=(rr * math.cos(a), -0.16 + R(b, -0.012, 0.012), zj + rr * math.sin(a)), rot=(0, -math.degrees(a) + R(b, -2, 2), 0),
                          mat='brick', bevel=0.012, segs=1, grain=None, jitter=0.2)
                for sx in (-1, 1):
                    for j in range(2):
                        b.box((rt + 0.02, 0.52 + R(b, -0.02, 0.02), zj / 2 - 0.01), loc=(sx * (ri + rt / 2), -0.16 + R(b, -0.012, 0.012), zj / 4 + j * zj / 2),
                              rot=(0, R(b, -1.5, 1.5), 0), mat='brick', bevel=0.012, segs=1, grain=None, jitter=0.2)
                # glowing inside
                b.box((0.6, 0.02, 0.52), loc=(0, -0.03, 0.25), mat='ember', bevel=0, grain=None, color=(1, 1, 1),
                      color_top=(0.1, 0.035, 0.02))
                b.box((0.58, 0.52, 0.012), loc=(0, -0.16, 0.004), mat='brick', bevel=0, grain=None, color=(0.3, 0.26, 0.24))
                b.blob((0.2, 0.13, 0.06), loc=(0.0, -0.2, 0.03), mat='ember', subdiv=2, noise_amp=0.3, noise_scale=2.5,
                       flatten_bottom=-0.4)
                for (lx, ly, lr, la) in [(-0.07, -0.22, 0.035, 25), (0.07, -0.17, 0.032, -40), (0.0, -0.13, 0.03, 70)]:
                    pole(b, (lx - 0.12 * math.cos(math.radians(la)), ly - 0.12 * math.sin(math.radians(la)), 0.07),
                         (lx + 0.12 * math.cos(math.radians(la)), ly + 0.12 * math.sin(math.radians(la)), 0.1), r=lr, mat='bark',
                         segs=6, color=(0.3, 0.26, 0.24))
            # firewood by the oven
            log_piece(b, 0.11, 0.5, 'half', (-0.75, -1.25, 0.0), (0, 8, 80))
            log_piece(b, 0.1, 0.46, 'round', (-0.82, -1.5, 0.095), (0, 20, 70))
            log_piece(b, 0.11, 0.5, 'half', (-0.72, -1.34, 0.16), (0, 190, 96))
            log_piece(b, 0.15, 0.48, 'quarter', (0.86, -1.1, 0.0), (0, 0, 20))

        tick(b, 'oven')
        # ---- roof -------------------------------------------------------------------------
        gable_roof(b, (0, 0, ZR), 2 * HX + 0.8, HY + 0.4, PITCH, keep=keep_main, tails=0.85, sag=0.04, row_h=0.37,
                   sw=(0.42, 0.64))
        for sx in (-1, 1):
            wood(b, (0.1, 0.1, 0.5), loc=(sx * (HX + 0.38), 0, ZR + 0.12), mat='wood_dark', bevel=0.02, segs=2, taper=(0.5, 0.5))
    return b.build(sharp_angle=50)


# ============================================================================================
# BUILD SITE / SCAFFOLD / EXPAND SIGN
# ============================================================================================
def sawhorse(b, L=1.1, H=0.72):
    wood(b, (L, 0.1, 0.1), loc=(0, 0, H - 0.05), mat='wood_plank', bevel=0.016, segs=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            strut(b, (sx * (L / 2 - 0.14), sy * 0.03, H - 0.07), (sx * (L / 2 - 0.04), sy * 0.3, -0.02), w=0.07, d=0.06,
                  mat='wood_plank', bevel=0.012, segs=2)
        strut(b, (sx * (L / 2 - 0.09), -0.17, 0.33), (sx * (L / 2 - 0.09), 0.17, 0.33), w=0.03, d=0.07, mat='wood_plank', bevel=0.008)
    strut(b, (-L / 2 + 0.1, 0.19, 0.3), (L / 2 - 0.1, 0.19, 0.3), w=0.025, d=0.07, mat='wood_plank', bevel=0.008)


def build_build_site():
    b = Builder('build_site', seed=404)
    S = 2.4
    # corner stakes + rope
    tops = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        lx, ly = R(b, -4, 4), R(b, -4, 4)
        with b.at(loc=(sx * S, sy * S, 0), rot=(lx, ly, R(b, 0, 90))):
            wood(b, (0.075, 0.075, 0.9), loc=(0, 0, 0.37), mat='wood_light', bevel=0.012, segs=2, jitter=0.12)
            wood(b, (0.075, 0.075, 0.07), loc=(0, 0, 0.855), mat='wood_light', bevel=0.012, segs=1, taper=(0.35, 0.35), jitter=0.12)
            b.box((0.082, 0.082, 0.1), loc=(0, 0, 0.74), mat='paint', color=RED, bevel=0.008, segs=1, jitter=0.08)
            rope_wrap(b, (0, 0, 0.6), r=0.05, turns=3, rr=0.011)
            tops.append(tuple(b.stack[-1] @ Vector((0, 0, 0.62))))
    flag_cols = [RED, srgb(232, 190, 80), CREAM]
    for i in range(4):
        p0, p1 = Vector(tops[i]), Vector(tops[(i + 1) % 4])
        d = (p1 - p0).normalized()
        pts = rope_span(b, p0 + d * 0.05, p1 - d * 0.05, sag=0.1, r=0.011, n=11)
        yaw = math.degrees(math.atan2(d.y, d.x))
        for j in (2, 4, 6, 8):
            if i == 0 and j in (4, 6):
                continue
            with b.at(loc=pts[j], rot=(R(b, -8, 8), 0, yaw + R(b, -10, 10))):
                b.prism([(-0.05, 0), (0.05, 0), (0.0, -0.17)], 0.006, mat='cloth', bevel=0.0, color=flag_cols[(i + j) % 3], jitter=0.08)
    # survey pegs + string marking the foundation outline
    pp = [(-1.25, -1.2), (1.2, -1.2), (1.2, 0.55), (-1.25, 0.55)]
    for i, (x, y) in enumerate(pp):
        peg(b, (x, y, 0), lean=5)
    for i in range(4):
        (x0, y0), (x1, y1) = pp[i], pp[(i + 1) % 4]
        b.tube([(x0, y0, 0.2), ((x0 + x1) / 2, (y0 + y1) / 2, 0.185), (x1, y1, 0.2)], 0.005, mat='rope', segs=5, caps=False)
    peg(b, (0.0, -1.2, 0), h=0.26, c=srgb(232, 190, 80))
    peg(b, (1.2, -0.3, 0), h=0.26, c=srgb(232, 190, 80))
    # plank stack (back left)
    with b.at(loc=(-1.05, 1.55, 0), rot=(0, 0, 4)):
        for x in (-0.75, 0.0, 0.75):
            wood(b, (0.09, 0.95, 0.09), loc=(x, 0, 0.045), mat='wood_dark', bevel=0.014, segs=2, rj=1)
        z = 0.09
        for layer in range(4):
            n = 4 if layer < 3 else 2
            for i in range(n):
                wood(b, (2.3 + R(b, -0.06, 0.06), 0.2, 0.046), loc=(R(b, -0.05, 0.05), (i - 1.5) * 0.215 + R(b, -0.006, 0.006), z + 0.023),
                     mat='wood_light', bevel=0.01, segs=2, jitter=0.16, rot=(0, 0, R(b, -0.8, 0.8) + (5 if layer == 3 and i == 1 else 0)))
            z += 0.048
    # cut stone pile (back right)
    with b.at(loc=(1.45, 1.5, 0), rot=(0, 0, -12)):
        for row, (n, z) in enumerate(((3, 0.11), (2, 0.33), (1, 0.55))):
            for i in range(n):
                stone(b, (0.46 + R(b, -0.03, 0.03), 0.3, 0.215), ((i - (n - 1) / 2) * 0.49 + R(b, -0.02, 0.02), R(b, -0.02, 0.02), z),
                      bev=0.03, rj=1.5)
        for i in range(2):
            stone(b, (0.44, 0.3, 0.215), ((i - 0.5) * 0.5, 0.36, 0.11), bev=0.03, rj=2)
        stone(b, (0.44, 0.28, 0.2), (0.95, -0.25, 0.1), rot0=(0, 0, 35), bev=0.03, rj=2)
        stone(b, (0.4, 0.26, 0.2), (-0.85, -0.42, 0.1), rot0=(0, 0, -50), bev=0.03, rj=2)
    # sawhorse with a plank and a saw
    with b.at(loc=(1.35, -0.15, 0), rot=(0, 0, 78)):
        sawhorse(b)
        wood(b, (1.7, 0.2, 0.045), loc=(0.2, 0.0, 0.745), rot=(0, 0, 14), mat='wood_light', bevel=0.01, segs=2, jitter=0.14)
        with b.at(loc=(-0.25, -0.03, 0.775), rot=(0, 0, 100)):
            b.prism([(0, 0), (0.5, 0.02), (0.5, 0.06), (0, 0.13)], 0.004, rot=(-90, 0, 0), mat='metal', bevel=0.0)
            b.box((0.14, 0.11, 0.028), loc=(-0.06, 0.07, 0.0), mat='wood_dark', bevel=0.012, segs=2)
    # mallet + bucket
    with b.at(loc=(-0.3, -0.75, 0), rot=(0, 0, 30)):
        b.cyl(0.07, 0.2, loc=(-0.1, 0, 0.07), rot=(0, 90, 0), mat='wood_dark', segs=12, bevel=0.012)
        pole(b, (0, 0, 0.07), (0, -0.42, 0.03), r=0.02, mat='wood_light', segs=6)
    with b.at(loc=(-1.75, -0.2, 0), rot=(0, 0, 40)):
        bucket(b, handle=75)
    # blank sign board at the front
    with b.at(loc=(0.0, -2.42, 0), rot=(0, 0, 0)):
        wood(b, (0.11, 0.11, 1.62), loc=(0, 0.02, 0.76), mat='wood_dark', bevel=0.018, segs=2, rot=(0, -1.2, 0), taper=(0.88, 0.88))
        wood(b, (0.1, 0.1, 0.06), loc=(0.016, 0.02, 1.6), mat='wood_dark', bevel=0.016, segs=1, taper=(0.4, 0.4))
        for i in range(3):
            wood(b, (0.98 + R(b, -0.03, 0.03), 0.035, 0.185), loc=(R(b, -0.012, 0.012), -0.055, 0.98 + i * 0.19), mat='wood_light',
                 bevel=0.012, segs=2, jitter=0.14, rj=0.7)
        for sx in (-1, 1):
            wood(b, (0.05, 0.03, 0.6), loc=(sx * 0.36, -0.025, 1.17), bevel=0.01, segs=1)
            for i in range(3):
                b.cyl(0.011, 0.008, loc=(sx * 0.36, -0.073, 0.98 + i * 0.19), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
        for sx in (-1, 1):
            wood(b, (0.6, 0.2, 0.035), loc=(sx * 0.26, -0.03, 1.575), rot=(0, sx * 24, 0), bevel=0.012, segs=2, jitter=0.12)
    return b.build(sharp_angle=50)


def build_scaffold():
    b = Builder('scaffold', seed=505)
    O, I = 2.42, 1.72
    L1, L2, TOP = 1.75, 3.5, 5.0

    def ring(h):
        return [(-h, -h), (0, -h), (h, -h), (h, 0), (h, h), (0, h), (-h, h), (-h, 0)]

    outer, inner = ring(O), ring(I)
    for (x, y) in outer:
        b.box((0.3, 0.3, 0.05), loc=(x, y, 0.02), rot=(0, 0, R(b, -10, 10)), mat='wood_plank', bevel=0.01, segs=1, jitter=0.14)
        wood(b, (0.12, 0.12, TOP - 0.03), loc=(x, y, (TOP + 0.03) / 2 + 0.01), mat='wood_plank', bevel=0.018, segs=2, jitter=0.14,
             rot=(R(b, -0.5, 0.5), R(b, -0.5, 0.5), R(b, -3, 3)))
        for z in (L1 - 0.12, 4.5):
            b.lathe([(0.078, -0.05), (0.098, -0.042), (0.1, 0.0), (0.098, 0.042), (0.078, 0.05)], loc=(x, y, z), mat='rope', segs=8,
                    jitter=0.08)
    for (x, y) in inner:
        b.box((0.28, 0.28, 0.05), loc=(x, y, 0.02), rot=(0, 0, R(b, -10, 10)), mat='wood_plank', bevel=0.01, segs=1, jitter=0.14)
        wood(b, (0.11, 0.11, L2 + 0.25), loc=(x, y, (L2 + 0.25) / 2 + 0.03), mat='wood_plank', bevel=0.018, segs=2, jitter=0.14,
             rot=(R(b, -0.5, 0.5), R(b, -0.5, 0.5), R(b, -3, 3)))
    sides = [((0, -1), 0), ((1, 0), 90), ((0, 1), 180), ((-1, 0), -90)]
    for li, z in enumerate((L1, L2)):
        zl = z - 0.12
        for (nx, ny), yaw in sides:
            with b.at(rot=(0, 0, yaw)):
                # local: this side's outer face is at y=-O, the walkway spans y -O..-I
                strut(b, (-O - 0.22, -O - 0.11, zl), (O + 0.22, -O - 0.11, zl), w=0.09, d=0.11, mat='wood_plank', jitter=0.14)
                strut(b, (-I - 0.2, -I + 0.11, zl), (I + 0.2, -I + 0.11, zl), w=0.09, d=0.11, mat='wood_plank', jitter=0.14)
                for x in (-O, -O / 2, 0, O / 2, O):
                    xi = max(-I, min(I, x))
                    if abs(x) == O:
                        continue
                    strut(b, (x, -O - 0.3, zl + 0.1), (x, -I + 0.3, zl + 0.1), w=0.08, d=0.09, mat='wood_plank', jitter=0.14)
                # deck planks
                for j in range(3):
                    y = -O + 0.14 + j * 0.235
                    full = (yaw in (0, 180))
                    x0, x1 = (-O - 0.12, O + 0.12) if full else (-I + 0.1, I - 0.1)
                    if full:
                        cut = R(b, -0.5, 0.5)
                        spans = [(x0 + R(b, -0.08, 0.05), cut + 0.012), (cut - 0.012 + 0.03, x1 + R(b, -0.05, 0.08))]
                    else:
                        spans = [(x0 + R(b, -0.06, 0.06), x1 + R(b, -0.06, 0.06))]
                    for a, c in spans:
                        if li == 1 and yaw == 180 and j == 2 and a < 0:
                            continue  # one plank still missing up top
                        wood(b, (c - a, 0.215, 0.045), loc=((a + c) / 2, y + R(b, -0.006, 0.006), zl + 0.17 + R(b, -0.003, 0.003)),
                             mat='wood_light', bevel=0.01, segs=1, jitter=0.18, rot=(0, 0, R(b, -0.6, 0.6)))
                # guard rail
                gz = z + 0.95 if li == 0 else 4.5
                strut(b, (-O - 0.15, -O - 0.1, gz), (O + 0.15, -O - 0.1, gz), w=0.07, d=0.09, mat='wood_plank', jitter=0.14)
    # corner putlogs
    for z in (L1, L2):
        for sx in (-1, 1):
            for sy in (-1, 1):
                strut(b, (sx * (O + 0.2), sy * (O + 0.2), z - 0.02), (sx * (I - 0.2), sy * (I - 0.2), z - 0.02), w=0.08, d=0.09,
                      mat='wood_plank', jitter=0.14)
    # diagonal braces on the outer faces
    for (nx, ny), yaw in sides:
        with b.at(rot=(0, 0, yaw)):
            if yaw != 0:
                strut(b, (-O, -O - 0.1, 0.15), (0, -O - 0.1, L1 - 0.25), w=0.05, d=0.09, mat='wood_plank', jitter=0.14, bevel=0.01)
            if yaw != 90:
                strut(b, (O, -O - 0.1, L1 + 0.1), (0, -O - 0.1, L2 - 0.25), w=0.05, d=0.09, mat='wood_plank', jitter=0.14, bevel=0.01)
            if yaw in (90, -90):
                strut(b, (0, -O - 0.1, 0.15), (O, -O - 0.1, L1 - 0.25), w=0.05, d=0.09, mat='wood_plank', jitter=0.14, bevel=0.01)

    def ladder(p0, p1, w=0.42, n=None):
        p0, p1 = Vector(p0), Vector(p1)
        v = p1 - p0
        side = v.cross(Vector((0, 0, 1)))
        side = Vector((1, 0, 0)) if side.length < 1e-6 else side.normalized()
        # rails lie in the vertical plane of v, rungs are horizontal along `across`
        across = Vector((0, 0, 1)).cross(side).normalized() if abs(v.normalized().z) > 0.999 else side
        up = v.normalized()
        horiz = Vector((up.x, up.y, 0))
        across = Vector((-horiz.y, horiz.x, 0)).normalized() if horiz.length > 1e-6 else Vector((1, 0, 0))
        for s in (-1, 1):
            strut(b, p0 + across * s * w / 2, p1 + across * s * w / 2, w=0.05, d=0.075, mat='wood_plank', bevel=0.012, segs=2,
                  jitter=0.14)
        n = n or int(v.length / 0.3)
        for i in range(n):
            c = p0 + v * ((i + 0.6) / n)
            pole(b, c - across * (w / 2 + 0.03), c + across * (w / 2 + 0.03), r=0.02, mat='wood_light', n=2, segs=6)

    ladder((0.55, -O - 0.62, 0.0), (0.55, -O - 0.17, L1 + 0.95))
    ladder((O - 0.55, 1.15, L1 + 0.07), (O - 0.35, 0.45, L2 + 0.95), w=0.4)
    # hoist: jib, pulley, rope and bucket
    strut(b, (-O, -O, TOP - 0.25), (-O, -O - 0.75, TOP - 0.12), w=0.09, d=0.1, mat='wood_plank', segs=2)
    strut(b, (-O, -O, TOP - 0.85), (-O, -O - 0.55, TOP - 0.2), w=0.06, d=0.06, mat='wood_plank')
    hx, hy = -O, -O - 0.66
    b.cyl(0.07, 0.04, loc=(hx - 0.02, hy, TOP - 0.3), rot=(0, 90, 0), mat='wood_dark', segs=12, bevel=0.008)
    b.tube([(hx, hy, TOP - 0.13), (hx, hy, TOP - 0.24)], 0.008, mat='metal_dark', segs=6)
    with b.at(loc=(hx, hy - 0.07, 1.1), rot=(0, 0, 30)):
        top = bucket(b)
    b.tube([(hx, hy - 0.07, 1.1 + top - 0.01), (hx, hy - 0.07, TOP - 0.3)], 0.011, mat='rope', segs=6, jitter=0.05)
    b.tube([(hx, hy + 0.07, TOP - 0.3), (hx + 0.03, hy + 0.3, 2.9), (hx + 0.1, -O - 0.12, L1 + 0.95)], 0.011, mat='rope', segs=6, jitter=0.05)
    rope_wrap(b, (hx + 0.1 + 0.0, -O - 0.1, L1 + 0.9), r=0.06, turns=2, rr=0.011)
    # stock on the first deck
    with b.at(loc=(1.2, O - 0.35, L1 + 0.075), rot=(0, 0, 3)):
        for i in range(3):
            stone(b, (0.4, 0.26, 0.2), ((i - 1) * 0.43, 0, 0.1), bev=0.03, rj=1.5)
        stone(b, (0.4, 0.26, 0.2), (-0.2, 0, 0.3), bev=0.03, rj=1.5)
    return b.build(sharp_angle=50)


def build_expand_sign():
    b = Builder('expand_sign', seed=606)
    with b.at(rot=(0, 2.5, 0)):
        wood(b, (0.09, 0.09, 1.3), loc=(0, 0, 0.55), mat='wood_dark', bevel=0.016, segs=2, taper=(0.9, 0.9))
        wood(b, (0.081, 0.081, 0.07), loc=(0, 0, 1.235), mat='wood_dark', bevel=0.014, segs=1, taper=(0.35, 0.35))
        # main board
        for i, z in enumerate((0.86, 1.025)):
            wood(b, (0.62 + R(b, -0.02, 0.02), 0.032, 0.16), loc=(R(b, -0.01, 0.01), -0.062, z), mat='wood_light', bevel=0.012, segs=2,
                 jitter=0.14, rj=1.0)
        for sx in (-1, 1):
            wood(b, (0.045, 0.02, 0.33), loc=(sx * 0.26, -0.086, 0.943), mat='wood_plank', bevel=0.008, segs=1)
        for z in (0.86, 1.025):
            b.cyl(0.011, 0.008, loc=(0.0, -0.08, z), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
        # small hanging tag
        for sx in (-1, 1):
            b.tube([(sx * 0.17, -0.062, 0.79), (sx * 0.172, -0.062, 0.7), (sx * 0.17, -0.062, 0.655)], 0.006, mat='rope', segs=6)
        wood(b, (0.44, 0.026, 0.13), loc=(0, -0.062, 0.6), rot=(0, -2.5, 0), mat='wood_light', bevel=0.01, segs=2, jitter=0.14)
        # pennant + rope tie
        rope_wrap(b, (0, 0, 1.12), r=0.055, turns=2, rr=0.009, pitch=0.02)
        b.prism([(0.05, 1.2), (0.36, 1.13), (0.05, 1.06)], 0.006, loc=(0, 0.0, 0), rot=(0, 0, -14), mat='cloth', bevel=0.0, color=RED)
    # rope coil at the foot
    pts = []
    for i in range(4 * 12 + 1):
        a = i * 2 * math.pi / 12
        r = 0.15 + 0.012 * math.sin(i * 0.9)
        pts.append((0.3 + r * math.cos(a), 0.1 + r * math.sin(a), 0.02 + i * 0.035 / 12))
    b.tube(pts, 0.018, mat='rope', segs=7, jitter=0.06)
    b.tube([pts[-1], (0.2, -0.02, 0.15), (0.1, -0.03, 0.26), (0.04, -0.03, 0.38)], 0.018, mat='rope', segs=7, jitter=0.06)
    rope_wrap(b, (0.01, 0, 0.36), r=0.058, turns=2, rr=0.017, pitch=0.036)
    # marker pegs with a string
    peg(b, (-0.42, -0.28, 0), h=0.3)
    peg(b, (0.42, -0.4, 0), h=0.26, c=srgb(232, 190, 80))
    b.tube([(-0.42, -0.28, 0.2), (0.0, -0.34, 0.16), (0.42, -0.4, 0.17)], 0.005, mat='rope', segs=5, caps=False)
    return b.build(sharp_angle=50)


# ============================================================================================
# REGISTRY / MAIN
# ============================================================================================
ASSETS = {
    'windmill': build_windmill, 'henhouse': build_henhouse, 'bakehouse': build_bakehouse,
    'build_site': build_build_site, 'scaffold': build_scaffold, 'expand_sign': build_expand_sign,
}
# preview groups: name -> (asset names, spacing, views[(az, el)], zoom)
GROUPS = {
    'windmill': (['windmill'], 0, [(28, 14), (-40, 8), (150, 18)], 1.15),
    'henhouse': (['henhouse'], 0, [(30, 24), (-35, 14), (150, 22)], 1.25),
    'bakehouse': (['bakehouse'], 0, [(30, 22), (-40, 16), (150, 24), (75, 12)], 1.25),
    'build_site': (['build_site'], 0, [(30, 30), (-25, 14)], 1.25),
    'scaffold': (['scaffold'], 0, [(30, 22), (-20, 8)], 1.2),
    'expand_sign': (['expand_sign'], 0, [(25, 18), (-150, 16)], 1.2),
}
# close-ups: group -> [(tag, centre, size, az, el)]   (centre z = size/2 keeps the floor at ground level)
FOCUS = {
    'windmill': [('door', (0, -2.6, 1.6), 3.2, -24, 8), ('gallery', (0, -2.4, 2.4), 4.8, 30, 20), ('eye', (0, -1.0, 3.0), 6.0, 12, 2),
                 ('cap', (0, -1.6, 4.9), 9.8, 24, 30)],
    'henhouse': [('coop', (-0.2, 0.2, 1.3), 2.6, -28, 10), ('nest', (1.6, 1.2, 1.25), 2.5, 62, 14), ('eye', (0, -2.7, 1.25), 2.5, 8, 4),
                 ('side', (-1.6, 1.4, 1.2), 2.4, -70, 12)],
    'bakehouse': [('door', (-1.75, -2.2, 1.5), 3.0, -20, 9), ('oven', (2.1, -1.6, 1.3), 2.6, 18, 12), ('eye', (0.3, -2.3, 1.6), 3.2, 6, 3),
                  ('left', (-3.1, 0, 1.3), 2.6, -80, 12)],
    'build_site': [('sign', (0, -2.4, 1.0), 2.0, 15, 8), ('stock', (0.2, 1.4, 0.9), 1.8, 20, 22), ('eye', (0.8, -0.4, 1.2), 2.4, -30, 6)],
    'scaffold': [('base', (0.3, -2.6, 1.5), 3.0, 20, 6), ('deck', (-1.5, -2.4, 2.6), 3.2, -30, 24)],
    'expand_sign': [('close', (0.05, -0.1, 0.65), 1.3, 20, 10)],
}

try:
    em = kit.get_mat('ember')
    bs = next(n for n in em.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Emission Color'].default_value = (1.0, 0.3, 0.04, 1)
    bs.inputs['Emission Strength'].default_value = 2.5
except Exception as ex:  # preview nicety only
    print('ember preview emission skipped:', ex)

names = list(ASSETS)
if ONLY:
    names = [n for n in names if any(n in GROUPS[g][0] for g in ONLY)]
objs = {}
for n in names:
    o = ASSETS[n]()
    objs[n] = o
    idx = 0
    placed = []
    for mname, pos in MARKS.get(n, []):
        if mname == 'window_light':
            idx += 1
            mname = f'{n}_window_light_{idx}'
        kit.marker(mname, pos, parent=o)
        placed.append((mname, pos))
    bpy.context.view_layer.update()
    fam = kit._descend([o])
    pts = [m.matrix_world @ Vector(c) for m in fam if m.type == 'MESH' for c in m.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    print(f'ASSET {n:12s} size=({hi[0] - lo[0]:.2f},{hi[1] - lo[1]:.2f},{hi[2] - lo[2]:.2f}) '
          f'min=({lo[0]:.2f},{lo[1]:.2f},{lo[2]:.2f}) max=({hi[0]:.2f},{hi[1]:.2f},{hi[2]:.2f}) tris={kit.tri_count(fam)} '
          f'mats={sorted({m.name for f in fam if f.type == "MESH" for m in f.data.materials})}')
    for c in o.children:
        if c.type == 'MESH':
            d = c.dimensions
            print(f'   child {c.name} at ({c.location.x:.3f},{c.location.y:.3f},{c.location.z:.3f}) size=({d.x:.2f},{d.y:.2f},{d.z:.2f}) '
                  f'tris={kit.tri_count([c])}')
    for mname, pos in placed:
        print(f'   marker {mname} ({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f})')

if not ONLY:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kit.export_glb(OUT, list(objs.values()))

if PREV:
    os.makedirs(PREV, exist_ok=True)
    for g, (members, spacing, views, zoom) in GROUPS.items():
        if ONLY and g not in ONLY:
            continue
        sel = [objs[m] for m in members]
        fam = kit._descend(sel)
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.hide_render = o not in fam
        for i, o in enumerate(sel):
            o.location.x = (i - (len(sel) - 1) / 2) * spacing
        bpy.context.view_layer.update()
        for az, el in views:
            kit.render_preview(os.path.join(PREV, f'{g}_{az}.png'), sel, az=az, el=el, zoom=zoom)
        for tag, centre, size, az, el in FOCUS.get(g, []):
            pm = bpy.data.meshes.new('_proxy')
            pb = bmesh.new()
            bmesh.ops.create_cube(pb, size=size)
            pb.to_mesh(pm)
            pb.free()
            proxy = bpy.data.objects.new('_proxy', pm)
            proxy.location = centre
            proxy.hide_render = True
            bpy.context.scene.collection.objects.link(proxy)
            bpy.context.view_layer.update()
            kit.render_preview(os.path.join(PREV, f'{g}_{tag}.png'), [proxy], az=az, el=el, zoom=1.5)
            bpy.data.objects.remove(proxy)
            bpy.data.meshes.remove(pm)
        for o in sel:
            o.location.x = 0
    for o in bpy.data.objects:
        o.hide_render = False
