"""Buildings + props for the homestead demo.

  blender --background --factory-startup --python tools/blender/build_structures.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/structures.glb.
With group names only those groups are built + previewed (no export) for fast iteration.
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'structures.glb')

kit.reset()

TEAL = srgb(52, 120, 128)
STRAW = (1, 1, 1)
HUES = [(1, 1, 1), (1.0, 0.95, 0.88), (0.92, 0.95, 1.0), (0.96, 1.0, 0.93), (1.0, 0.97, 0.92)]
G0, G1 = srgb(48, 100, 38), srgb(112, 168, 62)
MARKS = {}  # asset name -> [(marker name, world pos)]


def tint(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def R(b, a, c):
    return b.rng.uniform(a, c)


def mark(b, name, local=(0, 0, 0)):
    MARKS.setdefault(b.name, []).append((name, tuple(b.stack[-1] @ Vector(local))))


def nfaces(b):
    return len(b.bm.faces)


def swap_uv(b, n0):
    """Swap U/V on faces added since n0 (so wood grain runs along a tube / lathe axis)."""
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


def beam(b, x0, z0, x1, z1, w=0.17, depth=0.2, y=0.1, mat='wood_dark', bevel=0.018):
    """Timber in a wall frame (x along the wall, z up, outward = -Y, timber face at y=0)."""
    dx, dz = x1 - x0, z1 - z0
    ln = math.hypot(dx, dz)
    b.box((ln, depth, w), loc=((x0 + x1) / 2, y, (z0 + z1) / 2),
          rot=(0, -math.degrees(math.atan2(dz, dx)) + R(b, -0.5, 0.5), 0), mat=mat, bevel=bevel, segs=2,
          jitter=0.1, grain=0)


def chev(s=1.0):
    return [(-0.30 * s, -0.27 * s), (-0.25 * s, -0.32 * s), (0, -0.07 * s), (0.25 * s, -0.32 * s),
            (0.30 * s, -0.27 * s), (0, 0.03 * s)]


def gable_roof(b, loc, length, run, pitch, yaw=0, keep=None, row_h=0.33, sw=(0.34, 0.5), thick=0.045,
               barge=True, tails=0.0, cap=1.2, sag=0.0, cap_z=0.2):
    """Ridge through `loc` along local X (rotated by yaw). Deck, fascia, individual shingles,
    barge boards, rafter tails and ridge caps. keep(world_point) filters shingles."""
    pr = math.radians(pitch)
    L = run / math.cos(pr)
    tilt = math.degrees(math.atan2(thick * 1.1, row_h))
    with b.at(loc=loc, rot=(0, 0, yaw)):
        for side in (0, 180):
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


def shutter(b, sw, H):
    c = TEAL
    for ex in (-1, 1):
        b.box((0.06, 0.04, H), loc=(ex * (sw / 2 - 0.03), 0, 0), mat='paint', color=c, jitter=0.08, bevel=0.008, segs=1)
    for ez in (-1, 0, 1):
        b.box((sw - 0.1, 0.038, 0.07), loc=(0, 0, ez * (H / 2 - 0.035)), mat='paint', color=c, jitter=0.08,
              bevel=0.008, segs=1)
    b.box((sw - 0.1, 0.012, H - 0.1), loc=(0, 0.008, 0), mat='paint', color=tint(c, 0.5), bevel=0, grain=None)
    n = 8
    for i in range(n):
        z = -H / 2 + 0.07 + (i + 0.5) * (H - 0.14) / n
        if abs(z) < 0.05:
            continue
        b.box((sw - 0.11, 0.014, 0.095), loc=(0, -0.004, z), rot=(-28, 0, 0), mat='paint', color=c, jitter=0.1,
              bevel=0.004, segs=1)


def window(b, w=0.8, h=1.0, shutters=True, flower_box=False):
    """Local frame: wall (plaster) plane y=0, outward -Y, centred on the pane."""
    b.box((w, 0.02, h), loc=(0, -0.012, 0), mat='glass', bevel=0, grain=None)
    for sx in (-1, 1):
        wood(b, (0.09, 0.15, h + 0.12), loc=(sx * (w / 2 + 0.045), -0.055, 0), bevel=0.015, segs=2, rj=0.6)
    wood(b, (w + 0.3, 0.16, 0.1), loc=(0, -0.06, h / 2 + 0.05), bevel=0.015, segs=2, rj=0.6)
    wood(b, (w + 0.38, 0.24, 0.08), loc=(0, -0.1, -h / 2 - 0.04), bevel=0.02, segs=2, rj=0.6)
    wood(b, (0.045, 0.05, h), loc=(0, -0.035, 0), bevel=0.008)
    wood(b, (w, 0.05, 0.045), loc=(0, -0.035, 0.06), bevel=0.008)
    mark(b, 'window_light', (0, -0.03, 0))
    if shutters:
        sw, H = 0.38, h + 0.04
        for sx in (-1, 1):
            with b.at(loc=(sx * (w / 2 + 0.1 + sw / 2), -0.05, R(b, -0.01, 0.01)), rot=(0, R(b, -1.2, 1.2), sx * R(b, -5, -1))):
                shutter(b, sw, H)
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
            flowers(b, L - 0.14, 0.07, n=9)


# ============================================================================================
# COTTAGE
# ============================================================================================
HX, HY = 3.25, 2.6
PITCH = 44.0
TP = math.tan(math.radians(PITCH))
ZR = 2.7 + HY * TP           # main deck ridge height (deck passes 0.1 above the 2.6 m wall top)
XC, ZD = 1.25, 4.42          # front gable (dormer) centre x and ridge z
XD, ZP, PPITCH = -1.7, 3.03, 38.0
TPP = math.tan(math.radians(PPITCH))
CHX, CHY = 3.62, 0.9         # chimney centre


def main_z(y):
    return ZR - abs(y) * TP


def dorm_z(x):
    return ZD - abs(x - XC) * TP


def porch_z(x):
    return ZP - abs(x - XD) * TPP


def keep_main(p):
    if p.y < 0:
        if abs(p.x - XC) < 1.5 and p.y > -2.5 and p.z < dorm_z(p.x) - 0.02:
            return False
        if abs(p.x - XD) < 1.0 and p.z < porch_z(p.x) - 0.02:
            return False
    elif p.x > 3.0 and CHY - 0.6 < p.y < CHY + 0.6:
        return False
    return True


def keep_above_main(p):
    return p.y < -HY - 0.42 or p.z > main_z(p.y) - 0.03


def foundation(b, half, gaps=()):
    x = -half + 0.26
    end = half - 0.26
    while x < end - 0.05:
        w = min(R(b, 0.36, 0.68), end - x)
        if end - (x + w) < 0.22:
            w = end - x
        cx = x + w / 2
        if not any(g0 < cx < g1 for g0, g1 in gaps):
            yo = 0.08 + R(b, -0.035, 0.02)
            if b.rng.random() < 0.3:
                stone(b, (w - 0.015, 0.36, 0.53 + R(b, -0.03, 0.02)), (cx, yo, 0.2))
            else:
                h1 = R(b, 0.2, 0.3)
                stone(b, (w - 0.015, 0.36, h1 + 0.06), (cx, yo, h1 / 2 - 0.03))
                h2 = 0.475 - h1 + R(b, -0.03, 0.015)
                if w > 0.5 and b.rng.random() < 0.6:
                    s = R(b, 0.4, 0.6)
                    stone(b, (w * s - 0.012, 0.34, h2), (x + w * s / 2, yo + R(b, -0.02, 0.02), h1 + h2 / 2))
                    stone(b, (w * (1 - s) - 0.012, 0.34, h2 + R(b, -0.02, 0.02)), (x + w * s + w * (1 - s) / 2, yo + R(b, -0.02, 0.02), h1 + h2 / 2))
                else:
                    stone(b, (w - 0.02, 0.34, h2), (cx, yo + R(b, -0.02, 0.02), h1 + h2 / 2))
        x += w


def chimney(b):
    def half(z):
        if z < 2.0:
            return 0.5, 0.7
        if z < 2.9:
            t = (z - 2.0) / 0.9
            return 0.5 - 0.08 * t, 0.7 - 0.25 * t
        return 0.42, 0.45

    top = 6.05
    with b.at(loc=(CHX, CHY, 0)):
        # dark core (reads as mortar between the stones)
        b.box((0.88, 1.28, 2.1), loc=(0, 0, 1.0), mat='stone', bevel=0.02, segs=1, grain=None, color=(0.5, 0.48, 0.46))
        b.prism([(-0.64, 2.0), (0.64, 2.0), (0.39, 2.95), (-0.39, 2.95)], 0.86, loc=(0, 0, 0), rot=(0, 0, 90), mat='stone',
                bevel=0.02, segs=1, color=(0.5, 0.48, 0.46))
        b.box((0.72, 0.78, top - 2.9), loc=(0, 0, (top + 2.9) / 2), mat='stone', bevel=0.02, segs=1, grain=None,
              color=(0.5, 0.48, 0.46))
        z = -0.05
        k = 0
        while z < top - 0.05:
            ch = min(R(b, 0.3, 0.4), top - z)
            if top - (z + ch) < 0.2:
                ch = top - z
            zc = z + ch / 2
            hx, hy = half(zc)
            faces = [('x+', hy), ('y-', hx), ('y+', hx)]
            if zc > 3.5:
                faces.append(('x-', hy))
            for name, hl in faces:
                n = 2 if hl < 0.5 else b.rng.choice((2, 3))
                cuts = sorted(R(b, 0.3, 0.7) if n == 2 else R(b, 0.25, 0.42) + j * 0.33 for j in range(n - 1))
                edges = [0.0] + cuts + [1.0]
                # alternate which faces own the corners so the quoins interlock
                ext = 0.1 if (k % 2 == 0) == (name[0] == 'x') else -0.08
                for j in range(n):
                    a = -hl + edges[j] * 2 * hl - (ext if j == 0 else 0)
                    c = -hl + edges[j + 1] * 2 * hl + (ext if j == n - 1 else 0)
                    ln, mid = c - a - 0.015, (a + c) / 2
                    out = R(b, 0.0, 0.05)
                    hgt = ch - 0.015
                    if name == 'x+':
                        stone(b, (0.22, ln, hgt), (hx - 0.07 + out, mid, zc), segs=1, bev=0.05, rj=2.0)
                    elif name == 'x-':
                        stone(b, (0.22, ln, hgt), (-hx + 0.07 - out, mid, zc), segs=1, bev=0.05, rj=2.0)
                    elif name == 'y-':
                        stone(b, (ln, 0.22, hgt), (mid, -hy + 0.07 - out, zc), segs=1, bev=0.05, rj=2.0)
                    else:
                        stone(b, (ln, 0.22, hgt), (mid, hy - 0.07 + out, zc), segs=1, bev=0.05, rj=2.0)
            z += ch
            k += 1
        stone(b, (1.06, 1.12, 0.14), (0, 0, top + 0.06), bev=0.04, rj=1.0)
        for sy in (-0.24, 0.24):
            b.lathe([(0.1, 0), (0.13, 0), (0.135, 0.02), (0.105, 0.3), (0.115, 0.33), (0.085, 0.33), (0.08, 0.05), (0, 0.05)],
                    loc=(0, sy, top + 0.12), mat='roof', segs=14, jitter=0.15)
        mark(b, 'smoke_emitter', (0, 0, top + 0.5))


def door(b):
    """Local frame: timber plane y=0 (outward -Y), origin at the threshold centre."""
    dw, dh = 1.0, 1.9
    n = 5
    pw = dw / n
    for i in range(n):
        b.box((pw - 0.012, 0.06, dh - R(b, 0, 0.02)), loc=(-dw / 2 + (i + 0.5) * pw, 0.07, dh / 2), mat='paint',
              color=TEAL, jitter=0.1, bevel=0.012, segs=2, grain=2)
    for sx in (-1, 1):
        wood(b, (0.16, 0.24, dh + 0.06), loc=(sx * (dw / 2 + 0.08), 0.05, dh / 2), mat='wood_dark', bevel=0.02, segs=2, rj=0.5)
    wood(b, (dw + 0.56, 0.26, 0.2), loc=(0, 0.045, dh + 0.1), mat='wood_dark', bevel=0.025, segs=2, rj=0.5)
    for z in (0.36, 1.54):
        b.box((dw - 0.07, 0.03, 0.12), loc=(0, 0.03, z), mat='paint', color=tint(TEAL, 0.8), jitter=0.06, bevel=0.01, segs=1)
        b.box((0.62, 0.014, 0.055), loc=(-dw / 2 + 0.33, 0.011, z), mat='metal_dark', bevel=0.005, segs=1)
        b.cyl(0.045, 0.016, loc=(-dw / 2 + 0.64, 0.02, z), rot=(90, 0, 0), mat='metal_dark', segs=10, bevel=0.004)
        for dx in (0.1, 0.3, 0.5):
            b.cyl(0.012, 0.008, loc=(-dw / 2 + dx, 0.006, z), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
    hx, hz = dw / 2 - 0.15, 1.0
    b.cyl(0.05, 0.014, loc=(hx, 0.04, hz), rot=(90, 0, 0), mat='metal_dark', segs=12, bevel=0.004)
    ring = [(hx + 0.055 * math.cos(a), 0.012, hz - 0.045 + 0.055 * math.sin(a)) for a in
            [i * 2 * math.pi / 14 for i in range(15)]]
    b.tube(ring, 0.009, mat='metal_dark', segs=8, caps=False)


def build_cottage():
    b = Builder('cottage', seed=7)
    # --- plaster body + gables ---------------------------------------------------------
    b.box((6.34, 5.04, 2.45), loc=(0, 0, 1.4), mat='plaster', bevel=0.02, segs=1, grain=None)
    gz = ZR - 0.075
    gab = [(-2.55, 2.5), (2.55, 2.5), (2.55, gz - 2.55 * TP), (0, gz), (-2.55, gz - 2.55 * TP)]
    for sx in (-1, 1):
        b.prism(gab, 0.2, loc=(sx * 3.07, 0, 0), rot=(0, 0, 90), mat='plaster', bevel=0.012, segs=1)
    # front gable (wall dormer) body, 1.5 cm proud of the wall
    dw = [(-1.25, 2.45), (1.25, 2.45), (1.25, 3.1), (0, 3.1 + 1.25 * TP), (-1.25, 3.1)]
    b.prism(dw, 1.9, loc=(XC, -2.535 + 0.95, 0), mat='plaster', bevel=0.012, segs=1)

    # --- foundation ---------------------------------------------------------------------
    walls = {'front': ((0, -HY, 0), 0, HX), 'right': ((HX, 0, 0), 90, HY), 'back': ((0, HY, 0), 180, HX),
             'left': ((-HX, 0, 0), -90, HY)}
    for name, (loc, yaw, half) in walls.items():
        with b.at(loc=loc, rot=(0, 0, yaw)):
            gaps = [(XD - 0.66, XD + 0.66)] if name == 'front' else ([(CHY - 0.75, CHY + 0.75)] if name == 'right' else [])
            foundation(b, half, gaps)
    for sx in (-1, 1):
        for sy in (-1, 1):
            stone(b, (0.56, 0.56, 0.56), (sx * (HX - 0.13), sy * (HY - 0.13), 0.19), bev=0.07)

    # --- timber frame -------------------------------------------------------------------
    for sx in (-1, 1):
        for sy in (-1, 1):
            wood(b, (0.23, 0.23, 2.2), loc=(sx * (HX - 0.105), sy * (HY - 0.105), 1.53), mat='wood_dark', bevel=0.022,
                 segs=2, rj=0.4)
    with b.at(loc=walls['front'][0]):
        beam(b, -HX, 0.54, XD - 0.6, 0.54)
        beam(b, XD + 0.6, 0.54, HX, 0.54)
        beam(b, -HX - 0.06, 2.52, HX + 0.06, 2.52)
        beam(b, -0.82, 0.63, -0.82, 2.43)
        beam(b, -2.36, 0.66, -2.98, 2.4, w=0.14)
        for wx in (0.35, 2.15):
            for dx in (-0.28, 0.28):
                beam(b, wx + dx, 0.63, wx + dx, 0.95, w=0.12)
        # front gable timbers
        beam(b, XC - 1.27, 3.02, XC + 1.27, 3.02, w=0.16)
        beam(b, XC, 3.93, XC, 4.22, w=0.14)
        for s in (-1, 1):
            beam(b, XC + s * 1.02, 3.1, XC + s * 0.56, 3.72, w=0.12)
            beam(b, XC + s * 1.17, 2.61, XC + s * 1.17, 3.0, w=0.15)
        with b.at(loc=(XD, 0, 0.3)):
            door(b)
        for wx in (0.35, 2.15):
            with b.at(loc=(wx, 0.08, 1.5)):
                window(b, flower_box=True)
        # round attic window
        with b.at(loc=(XC, 0.065, 3.5)):
            b.lathe([(0.25, 0.02), (0.26, 0), (0.345, 0), (0.36, 0.02), (0.36, 0.1), (0.345, 0.125), (0.26, 0.125),
                     (0.25, 0.1), (0.25, 0.02)], rot=(90, 0, 0), mat='wood_plank', segs=24, jitter=0.05)
            b.cyl(0.26, 0.012, loc=(0, -0.012, 0), rot=(90, 0, 0), mat='glass', segs=24, bevel=0.003)
            wood(b, (0.52, 0.04, 0.04), loc=(0, -0.05, 0), bevel=0.008)
            wood(b, (0.04, 0.04, 0.52), loc=(0, -0.05, 0), bevel=0.008)
            mark(b, 'window_light', (0, -0.04, 0))
    with b.at(loc=walls['back'][0], rot=(0, 0, 180)):
        beam(b, -HX, 0.54, HX, 0.54)
        beam(b, -HX - 0.06, 2.52, HX + 0.06, 2.52)
        for x in (-1.3, 1.3):
            beam(b, x, 0.63, x, 2.43)
        beam(b, -3.0, 0.66, -1.42, 2.4, w=0.14)
        beam(b, 3.0, 0.66, 1.42, 2.4, w=0.14)
        with b.at(loc=(0, 0.08, 1.5)):
            window(b)
    for name, wy in (('left', 0.0), ('right', -1.05)):
        loc, yaw, half = walls[name]
        with b.at(loc=loc, rot=(0, 0, yaw)):
            if name == 'left':
                beam(b, -HY, 0.54, HY, 0.54)
                beam(b, -1.75, 0.66, -2.38, 2.4, w=0.14)
                beam(b, 1.75, 0.66, 2.38, 2.4, w=0.14)
                for x in (-1.05, 1.05):
                    beam(b, x, 0.63, x, 2.43)
            else:
                beam(b, -HY, 0.54, CHY - 0.6, 0.54)
                beam(b, CHY + 0.6, 0.54, HY, 0.54)
                beam(b, 0.12, 0.63, 0.12, 2.43)
                beam(b, 1.75, 0.66, 2.38, 2.4, w=0.14)
            beam(b, -HY - 0.05, 2.52, HY + 0.05, 2.52)
            # gable: collar beam, king post, struts
            beam(b, -1.52, 3.72, 1.52, 3.72, w=0.16)
            beam(b, 0, 3.8, 0, gz - 0.12, w=0.15)
            beam(b, 0, 2.61, 0, 3.64, w=0.15)
            for s in (-1, 1):
                beam(b, s * 1.25, 2.62, s * 0.2, 3.62, w=0.12)
            with b.at(loc=(wy, 0.08, 1.5)):
                window(b)

    # --- chimney --------------------------------------------------------------------------
    chimney(b)

    # --- roofs ----------------------------------------------------------------------------
    gable_roof(b, (0, 0, ZR), 7.4, HY + 0.4, PITCH, keep=keep_main, tails=0.8, sag=0.05)
    gable_roof(b, (XC, -1.875, ZD), 2.25, 1.55, PITCH, yaw=90, keep=keep_above_main, row_h=0.3, sw=(0.3, 0.44))
    gable_roof(b, (XD, -3.07, ZP), 1.75, 1.02, PPITCH, yaw=90, keep=keep_above_main, row_h=0.27, sw=(0.26, 0.38),
               cap=0.85)
    # finials
    for sx in (-1, 1):
        wood(b, (0.1, 0.1, 0.5), loc=(sx * 3.69, 0, ZR + 0.12), mat='wood_dark', bevel=0.02, segs=2, taper=(0.5, 0.5))
    wood(b, (0.09, 0.09, 0.42), loc=(XC, -2.99, ZD + 0.1), mat='wood_dark', bevel=0.02, segs=2, taper=(0.5, 0.5))

    # --- porch ----------------------------------------------------------------------------
    py = -3.72
    for i, (cx, cy, sx_, sy_) in enumerate([(-0.52, -2.95, 0.98, 0.62), (0.5, -2.93, 1.0, 0.6), (-0.55, -3.6, 0.9, 0.66),
                                            (0.42, -3.62, 1.02, 0.64), (1.0, -3.3, 0.36, 1.2), (-1.08, -3.3, 0.32, 1.15)]):
        stone(b, (sx_, sy_, 0.2 + R(b, -0.02, 0.02)), (XD + cx, cy, 0.06), bev=0.035, rj=1.2)
    stone(b, (1.3, 0.42, 0.34), (XD, -2.8, 0.13), bev=0.04, rj=0.6)
    for sx in (-1, 1):
        px = XD + sx * 0.8
        stone(b, (0.36, 0.36, 0.2), (px, py, 0.14), bev=0.05, rj=2)
        wood(b, (0.17, 0.17, 1.94), loc=(px, py, 1.2), mat='wood_dark', bevel=0.022, segs=2, rj=0.5)
        wood(b, (0.14, 1.2, 0.16), loc=(px, -3.13, 2.24), mat='wood_dark', bevel=0.02, segs=2, rj=0.4)
        # knee braces
        wood(b, (0.5, 0.1, 0.1), loc=(px - sx * 0.2, py, 1.96), rot=(0, sx * 45, 0), mat='wood_dark', bevel=0.015, segs=2)
        wood(b, (0.1, 0.5, 0.1), loc=(px, py + 0.2, 1.96), rot=(45, 0, 0), mat='wood_dark', bevel=0.015, segs=2)
    wood(b, (2.0, 0.17, 0.18), loc=(XD, py, 2.24), mat='wood_dark', bevel=0.022, segs=2)
    b.prism([(-0.86, 2.3), (0.86, 2.3), (0, 2.3 + 0.86 * TPP - 0.03)], 0.06, loc=(XD, py - 0.02, 0), mat='wood_plank',
            bevel=0.01, segs=1, jitter=0.05)
    wood(b, (0.12, 0.14, 0.62), loc=(XD, py - 0.05, 2.62), mat='wood_dark', bevel=0.018, segs=2)
    # lantern on an iron bracket on the right porch post
    lx = XD + 0.8
    b.tube([(lx + 0.08, py, 2.0), (lx + 0.22, py, 2.06), (lx + 0.36, py, 2.03), (lx + 0.4, py, 1.97)], 0.012,
           mat='metal_dark', segs=8)
    b.tube([(lx + 0.08, py, 1.8), (lx + 0.2, py, 1.9), (lx + 0.3, py, 2.03)], 0.009, mat='metal_dark', segs=8)
    with b.at(loc=(lx + 0.4, py, 1.975)):
        lc = lantern(b)
        mark(b, 'lantern_light', lc)
    mark(b, 'door_point', (XD, -HY - 1.0 - 0.6, 0))

    obj = b.build(sharp_angle=50)
    return obj


# ============================================================================================
# WELL / TROUGH
# ============================================================================================
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


def build_well():
    b = Builder('well', seed=11)
    Rc, H = 0.64, 0.82
    b.lathe([(0.5, -0.05), (0.7, -0.05), (0.7, H - 0.02), (0.5, H - 0.02), (0.5, 0.3), (0, 0.3)], mat='stone', segs=24,
            color=(0.5, 0.48, 0.46))
    z = -0.04
    k = 0
    while z < H - 0.05:
        ch = min(R(b, 0.19, 0.25), H - z)
        if H - (z + ch) < 0.14:
            ch = H - z
        a = R(b, 0, 1.0)
        a0 = a
        while a < a0 + 2 * math.pi - 0.2:
            da = min(R(b, 0.5, 0.82), a0 + 2 * math.pi - a)
            if a0 + 2 * math.pi - (a + da) < 0.35:
                da = a0 + 2 * math.pi - a
            am = a + da / 2
            rr = Rc + R(b, -0.02, 0.035)
            stone(b, (da * (rr + 0.1) - 0.02, 0.26, ch - 0.015), (rr * math.cos(am), rr * math.sin(am), z + ch / 2),
                  rot0=(0, 0, math.degrees(am) + 90), bev=0.055, rj=2.5)
            a += da
        z += ch
        k += 1
    n = 9
    for i in range(n):
        am = (i + R(b, -0.12, 0.12)) * 2 * math.pi / n
        rr = 0.665
        stone(b, (2 * math.pi * 0.72 / n - 0.012, 0.4, 0.11), (rr * math.cos(am), rr * math.sin(am), H + 0.045),
              rot0=(0, 0, math.degrees(am) + 90), bev=0.035, rj=1.5)
    b.cyl(0.52, 0.02, loc=(0, 0, 0.62), mat='water_still', segs=24, bevel=0.004)
    # frame
    for sx in (-1, 1):
        wood(b, (0.16, 0.16, 2.3), loc=(sx * 0.95, 0, 1.1), mat='wood_dark', bevel=0.022, segs=2, rj=0.6)
        wood(b, (0.13, 1.42, 0.13), loc=(sx * 0.95, 0, 2.2), mat='wood_dark', bevel=0.02, segs=2, rj=0.5)
        for sy in (-1, 1):
            wood(b, (0.09, 0.62, 0.09), loc=(sx * 0.95, sy * 0.3, 1.93), rot=(sy * 48, 0, 0), mat='wood_dark', bevel=0.015, segs=2)
        b.prism([(-0.6, 2.27), (0.6, 2.27), (0, 2.27 + 0.6 * 0.84 - 0.02)], 0.05, loc=(sx * 0.95, 0, 0), rot=(0, 0, 90),
                mat='wood_plank', bevel=0.01, segs=1, jitter=0.08)
    wood(b, (2.2, 0.12, 0.13), loc=(0, 0, 2.3 + 0.62 * 0.84 - 0.1), mat='wood_dark', bevel=0.02, segs=2)
    gable_roof(b, (0, 0, 2.3 + 0.68 * 0.839), 2.5, 0.86, 40, row_h=0.24, sw=(0.22, 0.34), thick=0.038, cap=0.75)
    # windlass
    zw = 1.42
    with b.at(loc=(0, 0, zw), rot=(0, 90, 0)):
        n0 = nfaces(b)
        b.lathe([(0, -1.04), (0.045, -1.04), (0.05, -0.42), (0.1, -0.4), (0.105, 0.0), (0.1, 0.4), (0.05, 0.42),
                 (0.045, 1.12), (0, 1.12)], mat='wood_plank', segs=14, jitter=0.05)
        swap_uv(b, n0)
        turns, r = 7, 0.118
        pts = []
        z0, z1 = -0.32, 0.12
        tot = turns * 2 * math.pi
        steps = turns * 12
        for i in range(steps + 1):
            t = i / steps
            ang = -math.pi / 2 - tot + tot * t
            pts.append((r * math.cos(ang), r * math.sin(ang), z0 + (z1 - z0) * t))
        b.tube(pts, 0.017, mat='rope', segs=8, jitter=0.05)
        for zz in (-0.4, 0.4):
            b.lathe([(0.1, zz - 0.012), (0.135, zz - 0.012), (0.14, zz), (0.135, zz + 0.012), (0.1, zz + 0.012)],
                    mat='wood_dark', segs=14)
    bx, by = 0.12, -0.118
    with b.at(loc=(bx, by, 0.74), rot=(3, 4, 25)):
        top = bucket(b)
    b.tube([(bx, by, zw), (bx, by, 0.74 + top - 0.008)], 0.016, mat='rope', segs=8, jitter=0.05)
    # crank
    b.tube([(1.1, 0, zw), (1.2, 0, zw), (1.22, 0, zw - 0.26), (1.3, 0, zw - 0.28)], 0.016, mat='metal_dark', segs=8)
    n0 = nfaces(b)
    b.tube([(1.29, 0, zw - 0.28), (1.5, 0, zw - 0.28)], 0.03, mat='wood_light', segs=8)
    swap_uv(b, n0)
    obj = b.build(sharp_angle=50)
    return obj


def build_trough():
    b = Builder('trough', seed=12)
    for sx in (-1, 1):
        wood(b, (0.13, 0.66, 0.15), loc=(sx * 0.6, 0, 0.075), mat='wood_dark', bevel=0.02, segs=2, rj=1.0)
        wood(b, (0.1, 0.1, 0.42), loc=(sx * 0.6, -0.3, 0.3), rot=(12, 0, 0), mat='wood_dark', bevel=0.015, segs=1)
        wood(b, (0.1, 0.1, 0.42), loc=(sx * 0.6, 0.3, 0.3), rot=(-12, 0, 0), mat='wood_dark', bevel=0.015, segs=1)
    wood(b, (1.72, 0.4, 0.05), loc=(0, 0, 0.17), bevel=0.012, segs=1)
    for sy in (-1, 1):
        wood(b, (1.8 + R(b, -0.03, 0.03), 0.045, 0.205), loc=(R(b, -0.01, 0.01), sy * 0.218, 0.27), rot=(-sy * 12, 0, 0),
             bevel=0.012, segs=2, rj=0.4)
        wood(b, (1.8 + R(b, -0.03, 0.03), 0.045, 0.2), loc=(R(b, -0.01, 0.01), sy * 0.26, 0.47), rot=(-sy * 12, 0, 0),
             bevel=0.012, segs=2, rj=0.4)
    for sx in (-1, 1):
        b.prism([(-0.2, 0.15), (0.2, 0.15), (0.295, 0.585), (-0.295, 0.585)], 0.05, loc=(sx * 0.85, 0, 0), rot=(0, 0, 90),
                mat='wood_plank', bevel=0.012, segs=2, jitter=0.1)
    for x in (-0.42, 0.42):
        b.box((0.045, 0.46, 0.008), loc=(x, 0, 0.142), mat='metal', bevel=0.002, segs=1)
        for sy in (-1, 1):
            b.box((0.045, 0.008, 0.44), loc=(x, sy * 0.268, 0.365), rot=(-sy * 12, 0, 0), mat='metal', bevel=0.002, segs=1)
    b.box((1.66, 0.46, 0.02), loc=(0, 0, 0.49), mat='water_still', bevel=0, grain=None)
    return b.build(sharp_angle=50)


# ============================================================================================
# FENCE KIT
# ============================================================================================
def build_fence_post():
    b = Builder('fence_post', seed=21)
    wood(b, (0.16, 0.16, 1.3), loc=(0, 0, 0.5), bevel=0.022, segs=2, taper=(0.86, 0.86), jitter=0.0)
    wood(b, (0.15, 0.15, 0.07), loc=(0, 0, 1.165), bevel=0.02, segs=2, taper=(0.45, 0.45), jitter=0.0)
    return b.build(sharp_angle=50)


def rail(b, x0, x1, z, r=0.055, seed_phase=0.0):
    n = 7
    pts = []
    rad = []
    for i in range(n):
        t = i / (n - 1)
        pts.append((x0 + (x1 - x0) * t, R(b, -0.012, 0.012), (z + R(b, -0.012, 0.012)) / 1.3))
        rad.append(r * R(b, 0.86, 1.1))
    n0 = nfaces(b)
    with b.at(scale=(1, 0.72, 1.3)):
        b.tube(pts, rad, mat='wood_plank', segs=9, jitter=0.08)
    swap_uv(b, n0)


def build_fence_rails():
    b = Builder('fence_rails', seed=22)
    rail(b, -1.3, 1.3, 0.45)
    rail(b, -1.28, 1.29, 0.85)
    return b.build(sharp_angle=50)


def build_gate_leaf():
    b = Builder('gate_leaf', seed=23)
    W, H = 2.3, 1.05
    wood(b, (0.1, 0.075, H), loc=(0.07, 0, H / 2 + 0.1), bevel=0.016, segs=2, rj=0.4)
    wood(b, (0.1, 0.075, H - 0.04), loc=(W - 0.05, 0, H / 2 + 0.1), bevel=0.016, segs=2, rj=0.4)
    wood(b, (0.085, 0.07, H - 0.2), loc=(W * 0.5, 0.0, H / 2 + 0.1), bevel=0.014, segs=2, rj=0.4)
    for z in (0.24, 0.5, 0.77, 1.04):
        wood(b, (W - 0.06 + R(b, -0.02, 0.02), 0.045, 0.115), loc=(W / 2, -0.055, z), bevel=0.014, segs=2, rj=0.5)
    ang = math.degrees(math.atan2(0.8, W - 0.25))
    wood(b, (math.hypot(0.8, W - 0.25), 0.04, 0.1), loc=(W / 2, -0.095, 0.64), rot=(0, -ang, 0), bevel=0.014, segs=2)
    for z in (0.3, 0.98):
        b.box((0.42, 0.014, 0.05), loc=(0.2, -0.085, z), mat='metal_dark', bevel=0.004, segs=1)
        b.cyl(0.022, 0.12, loc=(0.0, -0.03, z - 0.06), mat='metal_dark', segs=8, bevel=0.004)
        b.box((0.07, 0.07, 0.03), loc=(0.02, -0.045, z), mat='metal_dark', bevel=0.004, segs=1)
    b.box((0.2, 0.016, 0.045), loc=(W - 0.06, -0.085, 0.77), mat='metal_dark', bevel=0.004, segs=1)
    ring = [(W + 0.02 + 0.04 * math.cos(a), -0.09, 0.74 + 0.04 * math.sin(a)) for a in [i * 2 * math.pi / 12 for i in range(13)]]
    b.tube(ring, 0.007, mat='metal_dark', segs=8, caps=False)
    return b.build(sharp_angle=50)


# ============================================================================================
# PROPS
# ============================================================================================
def build_barrel():
    b = Builder('barrel', seed=31)
    n = 16
    segs = n * 3
    tones = [1 + R(b, -0.13, 0.13) for _ in range(n)]
    H = 0.82

    def rz(z):
        return 0.27 + 0.068 * math.sin(math.pi * max(0, min(1, z / H)))

    def col(co):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        k = tones[int(a / (2 * math.pi) * n + 0.17) % n]
        return (k, k, k)

    def rad(a, z):
        return 0.972 if round(a / (2 * math.pi) * segs) % 3 == 0 else 1.0

    prof = [(0, 0.03), (0.225, 0.03), (0.232, 0.0)]
    for i in range(13):
        z = H * i / 12
        prof.append((rz(z), z))
    prof += [(0.232, H), (0.225, H - 0.04), (0, H - 0.04)]
    n0 = nfaces(b)
    b.lathe(prof, mat='wood_plank', segs=segs, color=col, radial=rad)
    swap_uv(b, n0)
    for z in (0.09, 0.25, 0.57, 0.73):
        r0, r1 = rz(z - 0.024), rz(z + 0.024)
        b.lathe([(r0 - 0.004, z - 0.026), (r0 + 0.007, z - 0.024), (r1 + 0.007, z + 0.024), (r1 - 0.004, z + 0.026)],
                mat='metal', segs=segs)
    b.cyl(0.02, 0.03, loc=(0.1, -0.05, H - 0.045), mat='wood_dark', segs=8, bevel=0.005)
    return b.build(sharp_angle=50)


def build_crate():
    b = Builder('crate', seed=32)
    S = 0.6
    b.box((S - 0.07, S - 0.07, S - 0.07), loc=(0, 0, S / 2), mat='wood_dark', bevel=0.005, segs=1, grain=None,
          color=(0.55, 0.55, 0.55))
    for k in range(4):
        with b.at(rot=(0, 0, k * 90)):
            for i in range(3):
                z = 0.105 + i * 0.195
                wood(b, (S - 0.03 + R(b, -0.01, 0.01), 0.028, 0.17), loc=(R(b, -0.006, 0.006), -S / 2 + 0.02, z), mat='wood_light',
                     bevel=0.01, segs=2, jitter=0.12, rj=0.7)
            wood(b, (0.075, 0.03, S - 0.01), loc=(-S / 2 + 0.045, -S / 2 - 0.006, S / 2), mat='wood_light', bevel=0.01, segs=2, jitter=0.1)
            wood(b, (0.075, 0.03, S - 0.01), loc=(S / 2 - 0.045, -S / 2 - 0.006, S / 2), mat='wood_light', bevel=0.01, segs=2, jitter=0.1)
            if k % 2 == 0:
                L = math.hypot(S - 0.16, S - 0.03)
                wood(b, (L, 0.026, 0.07), loc=(0, -S / 2 - 0.008, S / 2), rot=(0, -math.degrees(math.atan2(S - 0.03, S - 0.16)), 0),
                     mat='wood_light', bevel=0.01, segs=1, jitter=0.1)
    for i in range(4):
        y = -S / 2 + 0.085 + i * (S - 0.17) / 3
        wood(b, (S - 0.02, 0.13, 0.028), loc=(0, y, S - 0.004), mat='wood_light', bevel=0.01, segs=2, jitter=0.12, rj=0.8)
    return b.build(sharp_angle=50)


def build_bench():
    b = Builder('bench', seed=33)
    for y in (-0.105, 0.095):
        wood(b, (1.42 + R(b, -0.03, 0.03), 0.185, 0.055), loc=(R(b, -0.01, 0.01), y, 0.46), bevel=0.016, segs=2, rj=0.8)
    for sx in (-1, 1):
        x = sx * 0.52
        wood(b, (0.07, 0.36, 0.44), loc=(x, 0, 0.215), rot=(0, sx * 6, 0), mat='wood_dark', bevel=0.018, segs=2)
        wood(b, (0.075, 0.075, 0.95), loc=(x, 0.2, 0.47), rot=(-8, 0, 0), mat='wood_dark', bevel=0.018, segs=2)
        wood(b, (0.06, 0.34, 0.06), loc=(x, 0.03, 0.62), rot=(8, 0, 0), mat='wood_dark', bevel=0.014, segs=2)
        wood(b, (0.065, 0.065, 0.2), loc=(x, -0.14, 0.56), mat='wood_dark', bevel=0.014, segs=2)
    wood(b, (1.0, 0.06, 0.09), loc=(0, 0, 0.2), mat='wood_dark', bevel=0.016, segs=2)
    for z, r in ((0.72, -8), (0.9, -8)):
        wood(b, (1.3 + R(b, -0.03, 0.03), 0.04, 0.14), loc=(0, 0.2 + (z - 0.47) * 0.14 - 0.055, z), rot=(r, 0, 0), bevel=0.014,
             segs=2, rj=0.6)
    return b.build(sharp_angle=50)


def build_hay_bale():
    b = Builder('hay_bale', seed=34)
    for i in range(5):
        b.box((0.205 + R(b, -0.008, 0.008), 0.5 + R(b, -0.025, 0.025), 0.44 + R(b, -0.02, 0.02)),
              loc=(-0.4 + i * 0.2, R(b, -0.01, 0.01), 0.235), rot=(R(b, -2, 2), R(b, -2, 2), R(b, -2, 2)), mat='straw',
              bevel=0.04, segs=2, jitter=0.1, grain=1)
    for y in (-0.13, 0.13):
        x, z0, z1 = 0.51, 0.008, 0.468
        b.tube([(-x + 0.04, y, z0), (x - 0.04, y, z0), (x, y, z0 + 0.04), (x, y, z1 - 0.04), (x - 0.04, y, z1), (-x + 0.04, y, z1),
                (-x, y, z1 - 0.04), (-x, y, z0 + 0.04), (-x + 0.04, y, z0)], 0.011, mat='rope', segs=8, caps=False)

    def st(loc, rot, ln=None):
        b.leaf(ln or R(b, 0.07, 0.17), R(b, 0.012, 0.02), loc=loc, rot=rot, mat='straw', bend=R(b, -30, 40), fold=25,
               segs=2, color=(1, 1, 1), jitter=0.22)

    for _ in range(46):
        st((R(b, -0.47, 0.47), R(b, -0.22, 0.22), 0.44), (R(b, -75, 75), R(b, -35, 35), R(b, 0, 360)))
    for sy in (-1, 1):
        for _ in range(22):
            st((R(b, -0.47, 0.47), sy * 0.235, R(b, 0.05, 0.42)), (sy * -(90 + R(b, -60, 60)), R(b, -40, 40), 0))
    for sx in (-1, 1):
        for _ in range(36):
            st((sx * 0.49, R(b, -0.22, 0.22), R(b, 0.04, 0.42)), (R(b, -35, 35), sx * (90 + R(b, -35, 35)), 0), ln=R(b, 0.04, 0.1))
    return b.build(sharp_angle=50)


def build_bucket():
    b = Builder('bucket', seed=35)
    bucket(b, r0=0.125, r1=0.16, h=0.28, handle=72)
    return b.build(sharp_angle=50)


def build_sack():
    b = Builder('sack', seed=36)
    c = srgb(176, 150, 105)

    def rad(a, z):
        return 1 + 0.07 * math.sin(3 * a + z * 6) + 0.04 * math.sin(5 * a + 1.3) + (0.1 * math.cos(a) if z < 0.25 else 0)

    b.lathe([(0, 0), (0.17, 0), (0.235, 0.035), (0.255, 0.13), (0.24, 0.26), (0.19, 0.36), (0.1, 0.43), (0.06, 0.455),
             (0.052, 0.48), (0.075, 0.515), (0.115, 0.56), (0.11, 0.565), (0.05, 0.53), (0, 0.52)], mat='cloth', segs=22,
            color=tint(c, 0.82), color_top=tint(c, 1.08), radial=rad, rot=(4, -5, 0))
    b.lathe([(0.05, 0.458), (0.068, 0.462), (0.07, 0.482), (0.05, 0.488)], mat='rope', segs=12, rot=(4, -5, 0), loc=(0.0, 0.0, 0.0))
    b.tube([(0.06, -0.03, 0.47), (0.12, -0.06, 0.4), (0.13, -0.07, 0.33)], 0.008, mat='rope', segs=8)
    b.box((0.11, 0.012, 0.1), loc=(-0.05, -0.243, 0.2), rot=(-4, 8, 6), mat='cloth', color=srgb(120, 96, 70), bevel=0.004, segs=1)
    return b.build(sharp_angle=50)


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


def build_woodpile():
    b = Builder('woodpile', seed=37)
    for sx in (-1, 1):
        wood(b, (0.07, 0.07, 0.75), loc=(sx * 0.6, 0, 0.36), rot=(0, sx * 3, 0), mat='wood_dark', bevel=0.014, segs=2)
    wood(b, (1.3, 0.07, 0.05), loc=(0, -0.14, 0.025), mat='wood_dark', bevel=0.012)
    wood(b, (1.3, 0.07, 0.05), loc=(0, 0.14, 0.025), mat='wood_dark', bevel=0.012)
    rows = [(5, 0.115, 0.05), (4, 0.115, 0.25), (4, 0.105, 0.43), (3, 0.1, 0.6)]
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
                log_piece(b, r * 1.05, ln, kind, (x, R(b, -0.03, 0.03), z + (r * 0.95 if flip else 0.0) + 0.0),
                          (0, (180 if flip else 0) + R(b, -14, 14), R(b, -4, 4)))
            elif kind == 'quarter':
                log_piece(b, r * 1.5, ln, kind, (x - r * 0.5, R(b, -0.03, 0.03), z), (0, R(b, -12, 12), R(b, -4, 4)))
            else:
                log_piece(b, r * 0.85, ln, kind, (x, R(b, -0.03, 0.03), z + r * 0.85), (0, R(b, 0, 90), R(b, -4, 4)))
            k += 1
    return b.build(sharp_angle=50)


def build_signpost():
    b = Builder('signpost', seed=38)
    wood(b, (0.13, 0.13, 2.05), loc=(0, 0, 0.92), mat='wood_dark', bevel=0.02, segs=2, taper=(0.85, 0.85), rot=(0, 1.2, 0))
    wood(b, (0.12, 0.12, 0.07), loc=(0.02, 0, 1.98), mat='wood_dark', bevel=0.02, segs=2, taper=(0.4, 0.4))
    wood(b, (0.95, 0.085, 0.09), loc=(0.38, 0, 1.72), mat='wood_dark', bevel=0.016, segs=2, rot=(0, -2, 0))
    wood(b, (0.5, 0.06, 0.07), loc=(0.2, 0, 1.52), rot=(0, -48, 0), mat='wood_dark', bevel=0.014, segs=2)
    bx, bz = 0.47, 1.33
    for i, z in enumerate((0.1, -0.1)):
        wood(b, (0.66 + R(b, -0.02, 0.03), 0.04, 0.19), loc=(bx + R(b, -0.01, 0.01), 0, bz + z), mat='wood_light', bevel=0.014,
             segs=2, jitter=0.12, rj=0.8)
    for sx in (-1, 1):
        wood(b, (0.05, 0.05, 0.42), loc=(bx + sx * 0.27, -0.0, bz), mat='wood_plank', bevel=0.01, segs=1)
        b.tube([(bx + sx * 0.24, 0, 1.68), (bx + sx * 0.245, 0, 1.6), (bx + sx * 0.24, 0, 1.53)], 0.008, mat='rope', segs=8)
    # painted wheat-ear emblem
    gold = srgb(226, 178, 72)
    b.box((0.012, 0.01, 0.26), loc=(bx, -0.024, bz - 0.02), rot=(0, 8, 0), mat='paint', color=gold, bevel=0.003, segs=1)
    for i in range(4):
        for s in (-1, 1):
            b.lathe([(0, 0), (0.02, 0.03), (0, 0.075)], loc=(bx + 0.006 + s * 0.012 + i * 0.008, -0.028, bz + 0.0 + i * 0.035),
                    rot=(0, s * 32 + 8, 0), scale=(1, 0.35, 1), mat='paint', segs=6, color=gold)
    return b.build(sharp_angle=50)


def build_scarecrow():
    b = Builder('scarecrow', seed=39)
    shirt = srgb(176, 72, 58)
    burlap = srgb(190, 160, 110)
    wood(b, (0.085, 0.085, 2.05), loc=(0, 0, 0.9), rot=(0, 1.5, 0), mat='wood_dark', bevel=0.016, segs=2)
    wood(b, (1.56, 0.07, 0.07), loc=(0, 0, 1.36), rot=(0, -3, 0), mat='wood_dark', bevel=0.016, segs=2)
    b.lathe([(0, 0.76), (0.2, 0.78), (0.27, 0.9), (0.255, 1.2), (0.225, 1.38), (0.1, 1.46), (0, 1.46)], mat='cloth', segs=16,
            color=tint(shirt, 0.8), color_top=shirt, scale=(1, 0.62, 1),
            radial=lambda a, z: 1 + 0.05 * math.sin(3 * a + z * 9) + 0.03 * math.sin(7 * a))
    for sx in (-1, 1):
        dz = sx * 0.035
        b.tube([(sx * 0.16, 0, 1.37 + dz * 0.2), (sx * 0.45, 0, 1.36 + dz * 0.6 - 0.01), (sx * 0.7, 0, 1.36 + dz)],
               [0.105, 0.098, 0.088], mat='cloth', segs=10, color=shirt)
        for _ in range(18):
            b.leaf(R(b, 0.16, 0.32), 0.024, loc=(sx * 0.74, R(b, -0.03, 0.03), 1.36 + dz + R(b, -0.03, 0.03)),
                   rot=(R(b, -30, 30), sx * (90 + R(b, -30, 30)), 0), mat='straw', bend=R(b, -15, 30), segs=3, jitter=0.2)
    for _ in range(22):
        a = R(b, 0, 2 * math.pi)
        b.leaf(R(b, 0.16, 0.3), 0.024, loc=(0.2 * math.cos(a), 0.12 * math.sin(a), 0.82),
               rot=(R(b, -25, 25), 180 + R(b, -25, 25), R(b, 0, 360)), mat='straw', bend=R(b, -10, 25), segs=3, jitter=0.2)
    b.lathe([(0.255, 0.93), (0.275, 0.935), (0.277, 0.965), (0.255, 0.97)], mat='rope', segs=16, scale=(1, 0.63, 1))
    b.box((0.1, 0.012, 0.1), loc=(0.1, -0.163, 1.08), rot=(0, 12, 0), mat='cloth', color=srgb(70, 105, 140), bevel=0.004, segs=1)
    b.box((0.08, 0.012, 0.07), loc=(-0.12, -0.155, 1.26), rot=(0, -8, 0), mat='cloth', color=srgb(200, 170, 90), bevel=0.004, segs=1)
    # head
    hz = 1.63
    b.blob((0.175, 0.165, 0.195), loc=(0, 0, hz), mat='cloth', subdiv=3, noise_amp=0.06, noise_scale=2.0, color=tint(burlap, 0.85),
           color_top=burlap)
    b.lathe([(0.09, 1.455), (0.125, 1.46), (0.127, 1.485), (0.09, 1.49)], mat='rope', segs=12)
    for _ in range(12):
        a = R(b, 0, 2 * math.pi)
        b.leaf(R(b, 0.08, 0.15), 0.02, loc=(0.1 * math.cos(a), 0.09 * math.sin(a), 1.46),
               rot=(R(b, -30, 30), 180 + R(b, -50, 50), R(b, 0, 360)), mat='straw', bend=10, segs=2, jitter=0.2)
    for sx in (-1, 1):
        b.cyl(0.03, 0.014, loc=(sx * 0.065, -0.152, hz + 0.03), rot=(90 - 8, 0, sx * 14), mat='eye', segs=10, bevel=0.004)
    for i in range(5):
        t = (i - 2) / 2
        b.box((0.012, 0.01, 0.035), loc=(t * 0.07, -0.158 + abs(t) * 0.012, hz - 0.07 + t * t * 0.03), rot=(0, t * 25, 0),
              mat='metal_dark', bevel=0.002, segs=1)
    b.box((0.16, 0.008, 0.01), loc=(0, -0.16, hz - 0.058), mat='metal_dark', bevel=0.002, segs=1)
    # hat
    with b.at(loc=(0.01, 0.01, hz + 0.12), rot=(9, -7, 0)):
        b.lathe([(0, 0), (0.33, -0.015), (0.345, -0.005), (0.33, 0.012), (0.18, 0.035), (0.165, 0.13), (0.125, 0.185), (0, 0.2)],
                mat='straw', segs=22, jitter=0.0, radial=lambda a, z: 1 + (0.06 * math.sin(3 * a) + 0.03 * math.sin(7 * a)) * (1 if z < 0.03 else 0.2))
        b.lathe([(0.168, 0.04), (0.19, 0.042), (0.186, 0.085), (0.166, 0.09)], mat='cloth', segs=22, color=shirt)
        for _ in range(16):
            a = R(b, 0, 2 * math.pi)
            b.leaf(R(b, 0.05, 0.1), 0.016, loc=(0.33 * math.cos(a), 0.33 * math.sin(a), 0.0),
                   rot=(0, 90 + R(b, -20, 20), math.degrees(a) + R(b, -25, 25)), mat='straw', bend=10, segs=2, jitter=0.2)
    return b.build(sharp_angle=50)


def build_lantern_post():
    b = Builder('lantern_post', seed=40)
    for i in range(5):
        a = i * 2 * math.pi / 5 + 0.3
        stone(b, (R(b, 0.2, 0.28), R(b, 0.18, 0.24), R(b, 0.16, 0.26)), (0.17 * math.cos(a), 0.17 * math.sin(a), 0.06),
              rot0=(0, 0, math.degrees(a)), bev=0.06, rj=8)
    wood(b, (0.15, 0.15, 2.15), loc=(0, 0, 0.98), mat='wood_dark', bevel=0.022, segs=2, taper=(0.82, 0.82), rot=(0, -1, 0))
    wood(b, (0.14, 0.14, 0.07), loc=(-0.02, 0, 2.08), mat='wood_dark', bevel=0.02, segs=2, taper=(0.4, 0.4))
    wood(b, (0.7, 0.085, 0.095), loc=(0.26, 0, 1.9), rot=(0, -4, 0), mat='wood_dark', bevel=0.016, segs=2)
    wood(b, (0.46, 0.06, 0.07), loc=(0.19, 0, 1.72), rot=(0, -50, 0), mat='wood_dark', bevel=0.014, segs=2)
    hx = 0.5
    b.tube([(hx, 0, 1.9), (hx, 0, 1.84), (hx + 0.015, 0, 1.815), (hx, 0, 1.79)], 0.007, mat='metal_dark', segs=8)
    with b.at(loc=(hx, 0, 1.81)):
        lc = lantern(b, 1.15)
        mark(b, 'lantern_post_light', lc)
    return b.build(sharp_angle=50)


def build_dock():
    b = Builder('dock', seed=41)
    n = 13
    for i in range(n):
        y = -0.1 - i * (2.5 / (n - 1))
        wood(b, (1.2 + R(b, -0.05, 0.06), 0.185, 0.055), loc=(R(b, -0.02, 0.02), y, 0.322 + R(b, -0.004, 0.004)), bevel=0.014,
             segs=2, jitter=0.14, rj=1.2)
    for sx in (-1, 1):
        wood(b, (0.1, 2.6, 0.13), loc=(sx * 0.42, -1.3, 0.23), mat='wood_dark', bevel=0.016, segs=2)
    for sx in (-1, 1):
        for y in (-0.85, -2.45):
            n0 = nfaces(b)
            b.tube([(sx * 0.6, y, -1.6), (sx * 0.6 + R(b, -0.01, 0.01), y, -0.4), (sx * 0.6 + R(b, -0.02, 0.02), y + R(b, -0.02, 0.02), 0.62 + R(b, -0.05, 0.08))],
                   [0.085, 0.08, 0.075], mat='wood_dark', segs=10, jitter=0.1)
            swap_uv(b, n0)
        wood(b, (0.09, 0.09, 0.12), loc=(sx * 0.42, -0.02, 0.2), mat='wood_dark', bevel=0.014)
    # rope wrap on one bollard
    px, py = 0.6, -2.45
    pts = []
    for i in range(3 * 12 + 1):
        a = i * 2 * math.pi / 12
        pts.append((px + 0.092 * math.cos(a), py + 0.092 * math.sin(a), 0.44 + i * 0.0032))
    b.tube(pts, 0.016, mat='rope', segs=8, jitter=0.05)
    b.tube([(px - 0.09, py, 0.47), (px - 0.16, py + 0.1, 0.4), (px - 0.2, py + 0.25, 0.362), (px - 0.12, py + 0.4, 0.36)], 0.016,
           mat='rope', segs=8)
    return b.build(sharp_angle=50)


def chisel(b, radii, n, lo=0.52, hi=0.86):
    """deform fn: cut the blob with n random planes -> flat chipped facets with soft transitions."""
    planes = []
    for _ in range(n):
        d = Vector((R(b, -1, 1), R(b, -1, 1), R(b, -0.25, 1))).normalized()
        planes.append((d, R(b, lo, hi)))

    def f(c):
        u = Vector((c.x / radii[0], c.y / radii[1], c.z / radii[2]))
        for d, h in planes:
            t = u.dot(d) - h
            if t > 0:
                u -= d * (t * 0.92)
        return Vector((u.x * radii[0], u.y * radii[1], u.z * radii[2]))

    return f


def build_rock(name, radii, seed, lumps=(), subdiv=4, planes=14):
    b = Builder(name, seed=seed)
    rz = radii[2]
    b.blob(radii, loc=(0, 0, 0.4 * rz - 0.02), mat='stone', subdiv=subdiv, noise_amp=0.13, noise_scale=1.1, flatten_bottom=-0.42,
           color=(0.78, 0.76, 0.74), color_top=(1.06, 1.04, 1.0), rot=(0, 0, seed * 40), deform=chisel(b, radii, planes))
    for (dx, dy, s, sd) in lumps:
        r = (radii[0] * s, radii[1] * s, radii[2] * s * 0.9)
        b.blob(r, loc=(dx, dy, 0.4 * r[2] - 0.02), mat='stone', subdiv=max(3, subdiv - 1), noise_amp=0.13, noise_scale=1.3,
               flatten_bottom=-0.42, color=(0.76, 0.75, 0.73), color_top=(1.02, 1.0, 0.98), rot=(0, 0, sd * 70), jitter=0.06,
               deform=chisel(b, r, 10))
    return b.build(sharp_angle=32)


def build_stepping_stone():
    b = Builder('stepping_stone', seed=55)

    def flat(c):
        z = max(min(c.z, 0.034), -0.03)
        return Vector((c.x, c.y, z + 0.012 * (1 - (c.x / 0.3) ** 2 - (c.y / 0.26) ** 2) if c.z > 0 else z))

    b.blob((0.27, 0.23, 0.11), loc=(0, 0, 0.03), mat='stone', subdiv=3, noise_amp=0.22, noise_scale=1.3, deform=flat,
           color=(0.92, 0.9, 0.88))
    return b.build(sharp_angle=60)


# ============================================================================================
# REGISTRY / MAIN
# ============================================================================================
ASSETS = {
    'cottage': build_cottage, 'well': build_well, 'trough': build_trough,
    'fence_post': build_fence_post, 'fence_rails': build_fence_rails, 'gate_leaf': build_gate_leaf,
    'barrel': build_barrel, 'crate': build_crate, 'bench': build_bench, 'hay_bale': build_hay_bale,
    'bucket': build_bucket, 'sack': build_sack, 'woodpile': build_woodpile, 'signpost': build_signpost,
    'scarecrow': build_scarecrow, 'lantern_post': build_lantern_post, 'dock': build_dock,
    'rock_a': lambda: build_rock('rock_a', (0.29, 0.24, 0.23), 1, subdiv=3, planes=8),
    'rock_b': lambda: build_rock('rock_b', (0.5, 0.4, 0.37), 2, lumps=[(0.32, -0.2, 0.5, 3)]),
    'rock_c': lambda: build_rock('rock_c', (0.76, 0.6, 0.56), 3, lumps=[(-0.55, 0.3, 0.5, 5), (0.52, 0.32, 0.38, 7)]),
    'stepping_stone': build_stepping_stone,
}
# preview groups: name -> (asset names, spacing, views[(az, el)], zoom)
GROUPS = {
    'cottage': (['cottage'], 0, [(30, 22), (-40, 18), (150, 25), (75, 12)], 1.25),
    'well': (['well'], 0, [(30, 20), (-120, 14)], 1.3),
    'fence': (['fence_post', 'fence_rails', 'gate_leaf'], 2.0, [(25, 20)], 1.25),
    'props1': (['barrel', 'crate', 'bucket', 'sack'], 0.95, [(25, 24)], 1.3),
    'props1b': (['hay_bale', 'bench', 'trough'], 1.9, [(25, 24), (-150, 24)], 1.25),
    'props2': (['woodpile', 'signpost', 'scarecrow', 'lantern_post'], 1.7, [(25, 16)], 1.25),
    'rocks': (['rock_a', 'rock_b', 'rock_c', 'stepping_stone'], 1.35, [(30, 24)], 1.3),
    'dock': (['dock'], 0, [(35, 28)], 1.2),
}
# close-ups: group -> [(tag, centre, size, az, el)]
FOCUS = {
    'cottage': [('door', (-1.7, -3.3, 1.3), 3.2, -22, 10), ('windows', (1.25, -2.9, 1.5), 3.0, 18, 8),
                ('corner', (-3.0, -2.6, 0.9), 2.4, -35, 14)],
    'well': [('top', (0, 0, 0.9), 1.9, 20, 22)],
}

names = list(ASSETS)
if ONLY:
    names = [n for n in names if any(n in GROUPS[g][0] for g in ONLY)]
objs = {}
for n in names:
    o = ASSETS[n]()
    objs[n] = o
    idx = 0
    for mname, pos in MARKS.get(n, []):
        if mname == 'window_light':
            idx += 1
            mname = f'window_light_{idx}'
        kit.marker(mname, pos, parent=o)
    d = o.dimensions
    print(f'ASSET {n:16s} size=({d.x:.2f},{d.y:.2f},{d.z:.2f}) tris={kit.tri_count([o])} mats={[m.name for m in o.data.materials]}')
    for mname, pos in MARKS.get(n, []):
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
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.hide_render = o not in sel
        for i, o in enumerate(sel):
            o.location.x = (i - (len(sel) - 1) / 2) * spacing
        bpy.context.view_layer.update()
        for az, el in views:
            kit.render_preview(os.path.join(PREV, f'{g}_{az}.png'), sel, az=az, el=el, zoom=zoom)
        for tag, centre, size, az, el in FOCUS.get(g, []):
            import bmesh
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
