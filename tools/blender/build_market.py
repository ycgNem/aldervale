"""Market / steward props for Aldervale: peddler stall, royal delivery crate, mill hopper, compost bay, hay bed, nest box.

  blender --background --factory-startup --python tools/blender/build_market.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/market.glb.
With group names only those groups are built + previewed (no export) for fast iteration.
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, Euler  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'market.glb')

kit.reset()
kit.PREVIEW.update({'slate': (0.17, 0.23, 0.37), 'gold': (0.86, 0.62, 0.22), 'parchment': (0.86, 0.78, 0.60)})
kit.ROUGH.update({'slate': 0.6, 'gold': 0.32, 'parchment': 0.9})

BLUE = srgb(38, 62, 128)
GOLD = srgb(214, 168, 64)
CREAM = srgb(236, 226, 200)
GREEN = srgb(64, 116, 74)
BURLAP = srgb(176, 150, 105)
GRAIN_C = (1.0, 0.84, 0.56)
APPLE = [srgb(196, 48, 40), srgb(214, 70, 44), srgb(178, 36, 40), srgb(200, 160, 50), srgb(206, 92, 48)]
PACKET = [srgb(222, 122, 44), srgb(196, 52, 44), srgb(92, 142, 62), srgb(226, 184, 70), srgb(128, 84, 150),
          srgb(70, 118, 160), srgb(214, 120, 140), srgb(150, 170, 70)]
QUILT = [srgb(176, 58, 46), srgb(214, 140, 60), srgb(226, 188, 104), srgb(150, 60, 54), srgb(232, 214, 180),
         srgb(196, 98, 62), srgb(112, 128, 96), srgb(206, 164, 84)]
MARKS = {}     # asset name -> [(marker name, pos)]
CHILDREN = {}  # asset name -> [(child object, local pos)]


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


def nverts(b):
    return len(b.bm.verts)


def deform_since(b, v0, fn):
    """Move every vertex added since v0 (builder space) through fn(co)->co."""
    for v in list(b.bm.verts)[v0:]:
        v.co = fn(v.co.copy())


def aim(d):
    """Euler degrees that turn local +Z onto direction d."""
    e = Vector(d).normalized().to_track_quat('Z', 'Y').to_euler('XYZ')
    return tuple(math.degrees(a) for a in e)


def wood(b, size, loc=(0, 0, 0), rot=(0, 0, 0), mat='wood_plank', bevel=0.012, segs=1, jitter=0.1, rj=0.0, **kw):
    rot = (rot[0] + R(b, -rj, rj), rot[1] + R(b, -rj, rj), rot[2] + R(b, -rj, rj)) if rj else rot
    b.box(size, loc=loc, rot=rot, mat=mat, bevel=bevel, segs=segs, jitter=jitter, **kw)


def pole(b, pts, r, mat='wood_light', segs=7, jitter=0.1):
    n0 = nfaces(b)
    b.tube(pts, r, mat=mat, segs=segs, jitter=jitter)
    swap_uv(b, n0)


def lantern(b, s=1.0):
    """Hanging lantern; local origin = hanging ring, extends down ~0.34*s. Returns lamp centre (local)."""
    ring = [(0.022 * s * math.cos(a), 0, 0.0 + 0.022 * s * math.sin(a) - 0.022 * s) for a in
            [i * math.pi / 5 for i in range(11)]]
    b.tube(ring, 0.005 * s, mat='metal_dark', segs=6, caps=False)
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


def sheet(b, nu, nv, pos, cellcol, mat='cloth', thick=0.01, loc=(0, 0, 0), rot=(0, 0, 0), uvsize=(1, 1), back=1.0):
    """Cloth sheet: (nu x nv) quads, pos(u,v)->xyz, cellcol(i,j)->linear rgb (hard-edged per cell).
    Closed double layer (front normal = du x dv)."""
    t = b._new()
    uv, col, _ = b._layers(t)
    P = [[Vector(pos(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
    F = [[None] * (nv + 1) for _ in range(nu + 1)]
    K = [[None] * (nv + 1) for _ in range(nu + 1)]
    for i in range(nu + 1):
        for j in range(nv + 1):
            du = P[min(i + 1, nu)][j] - P[max(i - 1, 0)][j]
            dv = P[i][min(j + 1, nv)] - P[i][max(j - 1, 0)]
            n = du.cross(dv)
            n = n.normalized() if n.length > 1e-12 else Vector((0, -1, 0))
            F[i][j] = t.verts.new(P[i][j] + n * thick / 2)
            K[i][j] = t.verts.new(P[i][j] - n * thick / 2)

    def put(f, ids, c):
        for l, (i, j) in zip(f.loops, ids):
            l[uv].uv = (i / nu * uvsize[0], j / nv * uvsize[1])
            l[col] = (c[0], c[1], c[2], 1.0)

    for i in range(nu):
        for j in range(nv):
            c = cellcol(i, j)
            ids = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            put(t.faces.new([F[a][d] for a, d in ids]), ids, c)
            ids2 = ids[::-1]
            put(t.faces.new([K[a][d] for a, d in ids2]), ids2, tint(c, back))
            for k, (ni, nj) in enumerate([(i, j - 1), (i + 1, j), (i, j + 1), (i - 1, j)]):
                if not (0 <= ni < nu and 0 <= nj < nv):
                    a, d = ids[k], ids[(k + 1) % 4]
                    put(t.faces.new((F[d[0]][d[1]], F[a[0]][a[1]], K[a[0]][a[1]], K[d[0]][d[1]])), [d, a, a, d], c)
    t.normal_update()
    b._emit(t, mat, loc, rot)


def crown_pts(w, h):
    return [(-w * 0.42, 0), (w * 0.42, 0), (w * 0.56, h), (w * 0.27, h * 0.48), (0, h * 1.12), (-w * 0.27, h * 0.48),
            (-w * 0.56, h)]


def shield_pts(w, h):
    return [(0, -h / 2), (w * 0.3, -h * 0.3), (w * 0.46, -h * 0.05), (w / 2, h * 0.2), (w / 2, h / 2), (-w / 2, h / 2),
            (-w / 2, h * 0.2), (-w * 0.46, -h * 0.05), (-w * 0.3, -h * 0.3)]


def stencil_crest(b, s=1.0):
    """Flat (stencilled) royal crest: gold-edged blue shield, cream chief, gold wheat ear and crown.
    Local frame: surface plane y=0, outward -Y, origin = shield centre. ~0.38 x 0.56 at s=1."""
    w, h = 0.34 * s, 0.4 * s
    b.prism(shield_pts(w + 0.045 * s, h + 0.045 * s), 0.006, loc=(0, -0.003, 0), mat='gold', bevel=0)
    b.prism(shield_pts(w, h), 0.006, loc=(0, -0.006, 0), mat='paint', color=BLUE, bevel=0)
    b.box((w - 0.03 * s, 0.004, 0.05 * s), loc=(0, -0.0095, h / 2 - 0.05 * s), mat='paint', color=CREAM, bevel=0, grain=None)
    b.box((0.014 * s, 0.004, 0.23 * s), loc=(0, -0.0095, -0.05 * s), mat='gold', bevel=0, grain=None)
    for i in range(4):
        for sx in (-1, 1):
            b.lathe([(0, 0), (0.021 * s, 0.03 * s), (0, 0.08 * s)], loc=(sx * 0.014 * s, -0.0095, (-0.1 + i * 0.045) * s),
                    rot=(0, sx * 34, 0), scale=(1, 0.18, 1), mat='gold', segs=6)
    b.lathe([(0, 0), (0.02 * s, 0.03 * s), (0, 0.08 * s)], loc=(0, -0.0095, 0.07 * s), scale=(1, 0.18, 1), mat='gold', segs=6)
    cz = h / 2 + 0.04 * s
    b.prism(crown_pts(0.26 * s, 0.1 * s), 0.006, loc=(0, -0.004, cz), mat='gold', bevel=0)
    b.box((0.25 * s, 0.008, 0.028 * s), loc=(0, -0.005, cz + 0.006 * s), mat='gold', bevel=0.002, segs=1)
    for x in (-0.07, 0.0, 0.07):
        b.box((0.018 * s, 0.004, 0.018 * s), loc=(x * s, -0.0105, cz + 0.006 * s), rot=(0, 45, 0), mat='paint',
              color=BLUE if x else srgb(168, 38, 34), bevel=0, grain=None)


def straw(b, loc, rot, ln=None, w=None, col=(1, 1, 1), bend=None):
    b.leaf(ln or R(b, 0.07, 0.17), w or R(b, 0.012, 0.02), loc=loc, rot=rot, mat='straw',
           bend=R(b, -30, 40) if bend is None else bend, fold=25, segs=2, color=col, jitter=0.22)


def grain(b, loc, s=1.0, rot=None):
    b.lathe([(0, 0), (0.0075 * s, 0.01 * s), (0, 0.026 * s)], loc=loc, rot=rot or (R(b, 60, 120), R(b, -30, 30), R(b, 0, 360)),
            mat='straw', segs=5, color=GRAIN_C, jitter=0.15)


def wheat_stalk(b, p, d, L=0.34):
    with b.at(loc=p, rot=aim(d)):
        b.tube([(0, 0, 0), (0.006, 0, L * 0.5), (0, 0, L)], 0.0035, mat='straw', segs=4, color=(1, 0.95, 0.8), jitter=0.1)
        for i in range(9):
            sx = 1 if i % 2 else -1
            b.lathe([(0, 0), (0.009, 0.012), (0, 0.032)], loc=(sx * 0.005, (i % 3 - 1) * 0.003, L - 0.005 + i * 0.011),
                    rot=(0, sx * 24, 0), mat='straw', segs=5, color=GRAIN_C, jitter=0.12)
        for i in range(5):
            b.leaf(R(b, 0.05, 0.09), 0.004, loc=(0, 0, L + 0.03 + i * 0.016), rot=(0, R(b, 8, 24), i * 137.0), mat='straw',
                   bend=8, fold=0, segs=1, color=(1, 0.95, 0.8))


def sack(b, s=1.0, c=None, segs=16):
    c = c or BURLAP
    ph = R(b, 0, 6)

    def rad(a, z):
        return 1 + 0.07 * math.sin(3 * a + z * 6 + ph) + 0.04 * math.sin(5 * a + 1.3) + (0.1 * math.cos(a) if z < 0.25 * s else 0)

    P = [(0, 0), (0.17, 0), (0.235, 0.035), (0.255, 0.13), (0.24, 0.26), (0.19, 0.36), (0.1, 0.43), (0.06, 0.455), (0.052, 0.48),
         (0.075, 0.515), (0.115, 0.56), (0.11, 0.565), (0.05, 0.53), (0, 0.52)]
    b.lathe([(r * s, z * s) for r, z in P], mat='cloth', segs=segs, color=tint(c, 0.8), color_top=tint(c, 1.06), radial=rad, rot=(4, -5, 0))
    b.lathe([(0.05 * s, 0.458 * s), (0.068 * s, 0.462 * s), (0.07 * s, 0.482 * s), (0.05 * s, 0.488 * s)], mat='rope', segs=10, rot=(4, -5, 0))


def open_sack(b, s=1.0, c=None, fill=GRAIN_C):
    """Sack with a rolled-down open top, full of grain / seed."""
    c = c or BURLAP
    ph = R(b, 0, 6)

    def rad(a, z):
        return 1 + 0.06 * math.sin(3 * a + z * 6 + ph) + 0.035 * math.sin(5 * a + 1.3)

    P = [(0, 0), (0.17, 0), (0.235, 0.035), (0.255, 0.13), (0.245, 0.25), (0.228, 0.32), (0.25, 0.345), (0.262, 0.375), (0.25, 0.405),
         (0.222, 0.41), (0.205, 0.385), (0.2, 0.34), (0, 0.33)]
    b.lathe([(r * s, z * s) for r, z in P], mat='cloth', segs=16, color=tint(c, 0.8), color_top=tint(c, 1.08), radial=rad)
    b.blob((0.205 * s, 0.205 * s, 0.075 * s), loc=(0, 0, 0.345 * s), mat='straw', subdiv=2, noise_amp=0.1, noise_scale=3.0, color=tint(fill, 0.8),
           color_top=fill, flatten_bottom=-0.2)


def basket(b, r=0.2, h=0.17, handle=False):
    """Round wicker basket standing on local z=0."""
    rows = 7
    segs = 32
    wick = (0.86, 0.72, 0.56)

    def rad(a, z):
        k = int(round(z / (h / rows)))
        return 1 + 0.055 * math.sin(8 * a + math.pi * k) if 0.004 < z < h - 0.004 else 1.0

    def wcol(co):
        k = int(round(co.z / (h / rows)))
        s_ = math.sin(8 * math.atan2(co.y, co.x) + math.pi * k)
        t = 0.62 + 0.2 * co.z / h + 0.2 * s_
        return tint(wick, t)

    prof = [(0, 0), (r * 0.7, 0)]
    for i in range(rows + 1):
        t = i / rows
        prof.append((r * (0.74 + 0.26 * math.sin(t * math.pi / 2) ** 0.8), h * t))
    prof += [(r - 0.02, h), (r * 0.72, 0.02), (0, 0.02)]
    b.lathe(prof, mat='straw', segs=segs, color=wcol, radial=rad)
    for zz, rr_, th in ((h, r - 0.004, 0.014), (0.012, r * 0.76, 0.011)):
        ring = [(rr_ * math.cos(a), rr_ * math.sin(a), zz) for a in [i * 2 * math.pi / 16 for i in range(17)]]
        b.tube(ring, th, mat='straw', segs=6, caps=False, color=tint(wick, 0.6))
    if handle:
        arc = [((r - 0.006) * math.cos(t), 0, h + (r * 0.95) * math.sin(t)) for t in [math.pi * i / 10 for i in range(11)]]
        b.tube(arc, 0.011, mat='straw', segs=6, color=tint(wick, 0.6))


def apples(b, r, z, n=11, hi=3):
    for i in range(n):
        a = i * 2.4
        rr = r * math.sqrt((i + 0.5) / n)
        b.blob((0.052, 0.052, 0.047), loc=(rr * math.cos(a), rr * math.sin(a), z + R(b, 0.0, 0.02) + 0.05 * (1 - rr / r)),
               mat='plant_glossy', subdiv=2 if i < hi else 1, color=b.rng.choice(APPLE), jitter=0.08)


def wheel(b, r, ns=10, segs=28):
    """Cart wheel in the local XY plane (axis = local Z, outer face +Z), hub at the origin."""
    ri, ro, w = r - 0.085, r - 0.012, 0.034
    nf = 5
    tones = [1 + R(b, -0.12, 0.12) for _ in range(nf)]

    def col(co):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        k = tones[int(a / (2 * math.pi) * nf + 0.1) % nf]
        return (k, k, k)

    n0 = nfaces(b)
    b.lathe([(ri, -w), (ro, -w + 0.004), (ro, w - 0.004), (ri, w), (ri, -w)], mat='wood_plank', segs=segs, color=col)
    swap_uv(b, n0)
    b.lathe([(ro - 0.004, -w - 0.005), (ro + 0.013, -w - 0.003), (ro + 0.013, w + 0.003), (ro - 0.004, w + 0.005)], mat='metal_dark', segs=segs)
    b.lathe([(0, -0.09), (0.048, -0.09), (0.06, -0.075), (0.082, -0.04), (0.088, 0.0), (0.084, 0.045), (0.062, 0.09), (0.052, 0.12), (0, 0.12)],
            mat='wood_dark', segs=12)
    b.lathe([(0.06, 0.072), (0.072, 0.074), (0.072, 0.098), (0.06, 0.1)], mat='metal_dark', segs=12)
    b.lathe([(0.026, 0.118), (0.04, 0.12), (0.038, 0.136), (0.02, 0.15), (0, 0.153)], mat='metal_dark', segs=8)
    for i in range(ns):
        with b.at(rot=(0, 0, 360.0 * (i + 0.5) / ns + R(b, -1.5, 1.5))):
            ln = ri - 0.065 + 0.012
            b.box((0.036, 0.03, ln), loc=(0.07 + ln / 2, 0, 0.004), rot=(0, 90, 0), mat='wood_light', bevel=0.009, segs=1, jitter=0.12,
                  taper=(0.8, 0.9))


# ============================================================================================
# PEDDLER STALL
# ============================================================================================
def packet(b, loc, lean=-12):
    c = b.rng.choice(PACKET)
    with b.at(loc=loc, rot=(lean + R(b, -5, 5), R(b, -4, 4), R(b, -6, 6))):
        b.box((0.078, 0.012, 0.11), loc=(0, 0, 0.055), mat='parchment', bevel=0, grain=None, jitter=0.08)
        b.box((0.066, 0.004, 0.056), loc=(0, -0.007, 0.07), mat='paint', color=c, bevel=0, grain=None, jitter=0.08)
        b.box((0.03, 0.004, 0.012), loc=(0, -0.007, 0.022), mat='paint', color=tint(c, 0.55), bevel=0, grain=None)


def seed_tray(b, L, n, rows=2):
    """Shallow wooden display tray, local z = tray normal, front lip at -Y."""
    wood(b, (L, 0.27, 0.016), loc=(0, 0, 0), mat='wood_light', bevel=0.005, jitter=0.12)
    wood(b, (L + 0.01, 0.018, 0.05), loc=(0, -0.135, 0.02), mat='wood_light', bevel=0.006, jitter=0.12, rj=0.6)
    wood(b, (L + 0.01, 0.018, 0.12), loc=(0, 0.135, 0.052), mat='wood_light', bevel=0.006, jitter=0.12, rj=0.6)
    for sx in (-1, 1):
        b.prism([(-0.143, -0.008), (0.143, -0.008), (0.143, 0.112), (-0.143, 0.045)], 0.018, loc=(sx * L / 2, 0, 0), rot=(0, 0, 90),
                mat='wood_light', bevel=0.005, segs=1, jitter=0.12)
    wood(b, (L - 0.03, 0.012, 0.05), loc=(0, 0.01, 0.03), mat='wood_plank', bevel=0.004)
    for r in range(rows):
        for i in range(n):
            x = -L / 2 + 0.06 + (i + 0.5) * (L - 0.12) / n + R(b, -0.006, 0.006)
            if b.rng.random() < 0.08:
                continue
            packet(b, (x, -0.1 + r * 0.135, 0.008))


def herb_bundle(b, c0, c1, ln=0.26, n=15, w=0.046):
    """Dried bunch hanging upside-down from the local origin (tie point at z=-0.05)."""
    b.tube([(0, 0, 0.0), (0.004, 0, -0.03), (0, 0, -0.055)], 0.004, mat='rope', segs=4)
    for i in range(5):
        a = i * 1.3
        b.tube([(0.006 * math.cos(a), 0.006 * math.sin(a), -0.03), (0.012 * math.cos(a), 0.012 * math.sin(a), -0.1)], 0.003, mat='plant',
               segs=3, caps=False, color=tint(c0, 0.8))
    b.lathe([(0.012, -0.064), (0.017, -0.062), (0.017, -0.048), (0.012, -0.046)], mat='rope', segs=6)
    for i in range(n):
        b.leaf(ln * R(b, 0.75, 1.2), w * R(b, 0.8, 1.2), loc=(R(b, -0.008, 0.008), R(b, -0.008, 0.008), -0.06),
               rot=(R(b, -20, 20), 180 + R(b, -20, 20), R(b, 0, 360)), mat='plant', bend=R(b, -25, 25), fold=30, segs=3,
               color=c0, color_top=c1, jitter=0.18)


def stool(b):
    tones = [1 + R(b, -0.1, 0.1) for _ in range(3)]
    b.lathe([(0, 0.385), (0.15, 0.385), (0.165, 0.395), (0.168, 0.42), (0.155, 0.432), (0, 0.436)], mat='wood_plank', segs=16,
            color=lambda co: (tones[int((co.x + 0.17) / 0.115) % 3],) * 3)
    for i in range(3):
        a = math.radians(90 + i * 120 + 8)
        pole(b, [(0.085 * math.cos(a), 0.085 * math.sin(a), 0.4), (0.15 * math.cos(a), 0.15 * math.sin(a), 0.2),
                 (0.2 * math.cos(a), 0.2 * math.sin(a), 0.012)], [0.02, 0.022, 0.018], mat='wood_dark', segs=7)
    for i in range(3):
        a0, a1 = math.radians(98 + i * 120), math.radians(98 + (i + 1) * 120)
        pole(b, [(0.14 * math.cos(a0), 0.14 * math.sin(a0), 0.22), (0.14 * math.cos(a1), 0.14 * math.sin(a1), 0.22)], 0.011,
             mat='wood_dark', segs=5)


def balance(b):
    """Small brass balance scale; local origin on the counter."""
    wood(b, (0.17, 0.085, 0.022), loc=(0, 0, 0.011), mat='wood_dark', bevel=0.006)
    b.lathe([(0, 0.02), (0.022, 0.02), (0.012, 0.035), (0.007, 0.05), (0.007, 0.225), (0.012, 0.235), (0, 0.245)], mat='gold', segs=8)
    tilt = 7.0
    with b.at(loc=(0, 0, 0.215), rot=(0, tilt, 0)):
        b.box((0.27, 0.008, 0.012), mat='gold', bevel=0.003, segs=1, grain=None)
    for sx in (-1, 1):
        ex, ez = sx * 0.13 * math.cos(math.radians(tilt)), 0.215 - sx * 0.13 * math.sin(math.radians(tilt))
        pz = ez - 0.13
        b.lathe([(0, 0), (0.04, 0.003), (0.052, 0.016), (0.049, 0.017), (0.038, 0.007), (0, 0.005)], loc=(ex, 0, pz), mat='gold', segs=10)
        for k in range(3):
            a = k * 2.094 + 0.5
            b.tube([(ex, 0, ez), (ex + 0.05 * math.cos(a), 0.05 * math.sin(a), pz + 0.016)], 0.0018, mat='metal_dark', segs=3, caps=False)
    b.cyl(0.018, 0.022, loc=(-0.13 * math.cos(math.radians(tilt)), 0, 0.215 + 0.13 * math.sin(math.radians(tilt)) - 0.125), mat='metal_dark',
          segs=8, bevel=0.004)


def build_peddler_stall():
    b = Builder('peddler_stall', seed=81)
    FZ, BX, Y0, Y1, WR = 0.90, 1.1, -0.30, 0.45, 0.41
    YC = (Y0 + Y1) / 2
    PX = 1.045
    with b.at(loc=(-0.25, 0, 0)):
        # ---- undercarriage: axle, wheels, frame + shafts, prop legs ---------------------------
        wood(b, (0.1, 1.2, 0.1), loc=(0, YC, WR), mat='wood_dark', bevel=0.02, segs=2)
        for y, d in ((Y0 - 0.125, 90), (Y1 + 0.125, -90)):
            with b.at(loc=(0, y, WR), rot=(d, 0, R(b, 0, 60))):
                wheel(b, WR)
        for y in (-0.2, 0.35):
            wood(b, (0.13, 0.08, 0.32), loc=(0, y, 0.61), mat='wood_dark', bevel=0.014, segs=1)
            b.box((0.15, 0.09, 0.012), loc=(0, y, 0.5), mat='metal_dark', bevel=0.003, segs=1)
            wood(b, (2.2, 0.07, 0.09), loc=(0, y, 0.815), mat='wood_dark', bevel=0.018, segs=2)
            # shafts: continue the frame beams, dipping a little toward the handle bar
            wood(b, (0.82, 0.062, 0.075), loc=(1.48, y, 0.795), rot=(0, 3.5, 0), mat='wood_dark', bevel=0.02, segs=2, taper=(1, 1))
        pole(b, [(1.84, Y0 - 0.02, 0.772), (1.845, YC, 0.775), (1.84, Y1 + 0.02, 0.772)], 0.024, mat='wood_light', segs=8)
        for x in (-1.02, -0.4, 0.4, 1.02):
            wood(b, (0.06, 0.8, 0.06), loc=(x, YC, 0.83), mat='wood_dark', bevel=0.012, rj=0.3)
        for sy, y in ((-1, -0.2), (1, 0.35)):
            wood(b, (0.06, 0.06, 0.8), loc=(-0.97, y + sy * 0.03, 0.385), rot=(sy * 4, 2, 0), mat='wood_dark', bevel=0.014, segs=2, taper=(1, 1))
            wood(b, (0.05, 0.05, 0.8), loc=(1.5, y + sy * 0.035, 0.375), rot=(sy * 5, -4, 0), mat='wood_dark', bevel=0.012, segs=1)
        wood(b, (0.04, 0.62, 0.045), loc=(-0.985, YC, 0.3), mat='wood_dark', bevel=0.01)
        wood(b, (0.04, 0.66, 0.04), loc=(1.515, YC, 0.26), mat='wood_dark', bevel=0.01)
        # ---- bed ------------------------------------------------------------------------------
        for i in range(5):
            wood(b, (2.2 + R(b, -0.02, 0.02), 0.142, 0.04), loc=(R(b, -0.008, 0.008), Y0 + 0.075 + i * 0.15, FZ - 0.02), bevel=0.01,
                 jitter=0.14, rj=0.25)
        for k in range(2):
            z = FZ + 0.072 + k * 0.142
            b.box((2.2 + R(b, -0.01, 0.01), 0.03, 0.136), loc=(0, Y1 - 0.005, z), rot=(R(b, -0.5, 0.5), 0, 0), mat='paint', color=GREEN,
                  jitter=0.1, bevel=0.011, segs=2, grain=0)
            for sx in (-1, 1):
                b.box((0.03, 0.75 + R(b, -0.01, 0.01), 0.136), loc=(sx * (BX - 0.005), YC, z), rot=(0, R(b, -0.5, 0.5), 0), mat='paint',
                      color=GREEN, jitter=0.1, bevel=0.011, segs=2, grain=1)
        wood(b, (2.26, 0.045, 0.035), loc=(0, Y1 - 0.005, FZ + 0.3), mat='wood_dark', bevel=0.012, segs=2)
        for sx in (-1, 1):
            wood(b, (0.045, 0.8, 0.035), loc=(sx * (BX - 0.005), YC, FZ + 0.3), mat='wood_dark', bevel=0.012, segs=2)
            b.box((0.006, 0.66, 0.02), loc=(sx * (BX + 0.012), YC, FZ + 0.142), mat='paint', color=CREAM, bevel=0, grain=None)
        b.box((2.06, 0.006, 0.02), loc=(0, Y1 + 0.012, FZ + 0.142), mat='paint', color=CREAM, bevel=0, grain=None)
        # ---- fold-down counter flap (the cart's customer-side board) ------------------------------
        for k in range(2):
            wood(b, (2.14 + R(b, -0.02, 0.02), 0.2, 0.035), loc=(R(b, -0.006, 0.006), Y0 - 0.115 - k * 0.205, FZ - 0.0175 + R(b, -0.003, 0.002)),
                 bevel=0.011, segs=2, jitter=0.14, rj=0.3)
        for x in (-0.72, 0.72):
            wood(b, (0.06, 0.38, 0.028), loc=(x, Y0 - 0.215, FZ - 0.05), mat='wood_dark', bevel=0.008)
        b.box((2.14, 0.022, 0.06), loc=(0, Y0 - 0.43, FZ - 0.025), mat='paint', color=GREEN, jitter=0.08, bevel=0.008, segs=1, grain=0)
        b.box((2.0, 0.006, 0.016), loc=(0, Y0 - 0.443, FZ - 0.025), mat='paint', color=CREAM, bevel=0, grain=None)
        for x in (-0.85, 0.0, 0.85):
            b.box((0.05, 0.2, 0.008), loc=(x, Y0 - 0.01, FZ + 0.003), mat='metal_dark', bevel=0.003, segs=1)
            b.cyl(0.011, 0.07, loc=(x - 0.035, Y0 - 0.012, FZ + 0.006), rot=(0, 90, 0), mat='metal_dark', segs=6, bevel=0.002)
        for sx in (-1, 1):
            b.tube([(sx * 1.03, Y0 - 0.4, FZ + 0.005), (sx * (PX - 0.005), Y0 - 0.01, 1.52)], 0.006, mat='metal_dark', segs=5)
            b.cyl(0.016, 0.012, loc=(sx * 1.03, Y0 - 0.4, FZ), mat='metal_dark', segs=8, bevel=0.003)
        # ---- awning frame -----------------------------------------------------------------------------
        YR, ZR_ = 0.1, 2.5
        YF, ZF = -0.92, 2.02
        YB, ZB = 0.78, 2.2
        for sx in (-1, 1):
            for y, top in ((Y0 + 0.03, 2.31), (Y1 - 0.03, 2.35)):
                wood(b, (0.065, 0.065, top - 0.78), loc=(sx * PX, y, (top + 0.78) / 2), mat='wood_dark', bevel=0.014, segs=2, rj=0.4)
            wood(b, (0.05, 0.84, 0.06), loc=(sx * PX, YC, 2.08), mat='wood_dark', bevel=0.012, segs=1)
            lf = math.hypot(YR - YF, ZR_ - ZF)
            wood(b, (0.05, lf + 0.08, 0.055), loc=(sx * PX, (YR + YF) / 2, (ZR_ + ZF) / 2), rot=(math.degrees(math.atan2(ZR_ - ZF, YR - YF)), 0, 0),
                 mat='wood_dark', bevel=0.012, segs=1)
            lb = math.hypot(YB - YR, ZR_ - ZB)
            wood(b, (0.05, lb + 0.08, 0.055), loc=(sx * PX, (YR + YB) / 2, (ZR_ + ZB) / 2), rot=(-math.degrees(math.atan2(ZR_ - ZB, YB - YR)), 0, 0),
                 mat='wood_dark', bevel=0.012, segs=1)
            # brace from the front pole out to the eave
            wood(b, (0.04, 0.6, 0.04), loc=(sx * PX, -0.52, 1.83), rot=(38, 0, 0), mat='wood_dark', bevel=0.01, segs=1)
        pole(b, [(-1.43, YR, ZR_ + 0.04), (0, YR, ZR_ + 0.028), (1.43, YR, ZR_ + 0.04)], 0.026, segs=8)
        pole(b, [(-1.41, YF, ZF + 0.028), (0, YF, ZF + 0.018), (1.41, YF, ZF + 0.028)], 0.02, segs=7)
        pole(b, [(-1.41, YB, ZB + 0.028), (0, YB, ZB + 0.02), (1.41, YB, ZB + 0.028)], 0.02, segs=7)
        # ---- striped canvas with a dagged valance ---------------------------------------------------------
        NU, NV = 24, 17
        sf = (ZR_ - ZF) / (YR - YF)
        sb = (ZR_ - ZB) / (YB - YR)
        ZT = ZR_ + 0.072
        jit = [1 + R(b, -0.05, 0.05) for _ in range(NU)]

        def cpos(u, v):
            i, j = int(round(u * NU)), int(round(v * NV))
            x = -1.39 + u * 2.78
            edge = max(0.0, abs(x) - PX) / 0.345
            if j <= 2:
                k = 2 - j
                y0 = YF - 0.04
                z = ZT - (YR - y0) * sf - 0.085 * k - 0.03 * edge ** 2
                if j == 0 and i % 2 == 0:
                    z += 0.06
                return (x, y0 - 0.014 * k - 0.01 * math.sin(x * 9.0) * k, z)
            if j <= 10:
                t = (j - 2) / 8
                y = (YF - 0.04) + t * (YR - YF + 0.04)
                z = ZT - (YR - y) * sf
            elif j <= 15:
                t = 1 - (j - 10) / 5
                y = YR + (1 - t) * (YB - YR + 0.03)
                z = ZT - (y - YR) * sb
            else:
                k = j - 15
                return (x, YB + 0.03 + 0.012 * k, ZT - (YB + 0.03 - YR) * sb - 0.055 * k - 0.03 * edge ** 2)
            sag = math.sin(math.pi * t) * (0.02 + 0.065 * max(0.0, math.cos(math.pi * x / (2 * PX))) + 0.008 * math.sin(x * 7.0 + j * 0.9))
            return (x, y, z - sag - 0.045 * edge ** 2)

        def ccol(i, j):
            base = GREEN if (i // 2) % 2 == 0 else CREAM
            k = 0.86 if j < 2 else (0.93 if j > 9 else 1.0)
            return tint(base, k * jit[(i // 2) * 2])

        sheet(b, NU, NV, cpos, ccol, mat='cloth', thick=0.012, uvsize=(2.78, 2.2), back=0.6)
        for sx in (-1, 1):
            for y, z in ((YF, ZF), (YB, ZB)):
                b.tube([(sx * 1.36, y + 0.0, z + 0.06), (sx * 1.4, y, z + 0.0), (sx * 1.36, y, z - 0.03), (sx * 1.33, y, z + 0.03)], 0.005,
                       mat='rope', segs=4)
        # ---- seed rack (left half) ---------------------------------------------------------------------
        for x in (-0.97, -0.03):
            wood(b, (0.045, 0.045, 1.13), loc=(x, 0.345, FZ + 0.565), bevel=0.01, segs=1, rj=0.4)
        wood(b, (1.02, 0.04, 0.05), loc=(-0.5, 0.345, FZ + 1.11), bevel=0.01, segs=1)
        for tz in (1.4, 1.76):
            for x in (-0.97, -0.03):
                wood(b, (0.03, 0.3, 0.03), loc=(x, 0.21, tz - 0.022), rot=(32, 0, 0), mat='wood_dark', bevel=0.007)
            with b.at(loc=(-0.5, 0.2, tz), rot=(32, 0, 0)):
                seed_tray(b, 0.9, 8)
        with b.at(loc=(-0.6, -0.5, FZ + 0.055), rot=(20, 0, -5)):
            seed_tray(b, 0.6, 5)
        wood(b, (0.5, 0.05, 0.085), loc=(-0.6, -0.4, FZ + 0.04), rot=(0, 0, -5), mat='wood_plank', bevel=0.01)
        # ---- goods on the bed ------------------------------------------------------------------------------
        with b.at(loc=(-0.74, 0.1, FZ), rot=(0, 0, 40)):
            open_sack(b, 0.62)
        with b.at(loc=(-0.3, 0.14, FZ), rot=(0, 0, 150)):
            open_sack(b, 0.56, srgb(190, 164, 118), fill=srgb(96, 70, 48))
        with b.at(loc=(0.36, 0.02, FZ), rot=(0, 0, 20)):
            basket(b, 0.2, 0.16)
            apples(b, 0.135, 0.12)
        wood(b, (0.4, 0.3, 0.13), loc=(0.8, 0.18, FZ + 0.065), rot=(0, 0, -6), mat='wood_light', bevel=0.012, segs=2)
        with b.at(loc=(0.8, 0.13, FZ + 0.145), rot=(17, 0, -10)):
            basket(b, 0.19, 0.15)
            apples(b, 0.13, 0.11)
        for x, y in ((0.6, -0.47), (0.69, -0.42), (0.635, -0.56), (0.26, -0.36)):
            b.blob((0.05, 0.05, 0.045), loc=(x, y, FZ + 0.045), mat='plant_glossy', subdiv=2, color=b.rng.choice(APPLE), jitter=0.08)
        with b.at(loc=(0.1, -0.52, FZ), rot=(0, 0, 8)):
            balance(b)
        with b.at(loc=(0.95, -0.52, FZ), rot=(0, 0, 60)):
            basket(b, 0.13, 0.1, handle=True)
            for i in range(5):   # eggs-sized onions / bulbs
                a = i * 1.3
                b.blob((0.034, 0.034, 0.04), loc=(0.05 * math.cos(a), 0.05 * math.sin(a), 0.085 + (0.02 if i == 0 else 0)), mat='plant_glossy',
                       subdiv=1, color=srgb(214, 170, 96), jitter=0.12)
        # ---- under the counter ---------------------------------------------------------------------------
        with b.at(loc=(-1.08, -0.6, 0), rot=(0, 0, 100)):
            sack(b, 1.0)
            b.box((0.11, 0.012, 0.1), loc=(-0.02, -0.25, 0.2), rot=(-4, 8, 6), mat='cloth', color=srgb(120, 96, 70), bevel=0.004, segs=1)
        with b.at(loc=(-0.6, -0.57, 0), rot=(0, 0, 250)):
            sack(b, 0.86, srgb(198, 174, 130))
        # travelling kit: bedroll strapped across the shafts
        with b.at(loc=(1.3, YC, 0.955)):
            roll = srgb(150, 72, 58)
            b.lathe([(0, -0.33), (0.085, -0.33), (0.108, -0.31), (0.112, 0.0), (0.108, 0.31), (0.085, 0.33), (0, 0.33)], rot=(90, 0, 0), mat='cloth',
                    segs=14, color=tint(roll, 0.8), color_top=roll, radial=lambda a, z: 1 + 0.035 * math.sin(3 * a + z * 9) + 0.02 * math.sin(a * 5))
            for y in (-0.33, 0.33):
                b.cyl(0.05, 0.008, loc=(0, y + (0.004 if y > 0 else -0.004), 0), rot=(90 if y < 0 else -90, 0, 0), mat='cloth', segs=10, bevel=0.002,
                      color=tint(roll, 0.5))
            for y in (-0.17, 0.17):
                b.lathe([(0.108, -0.016), (0.119, -0.014), (0.119, 0.014), (0.108, 0.016)], loc=(0, y, 0), rot=(90, 0, 0), mat='leather', segs=14)
                b.box((0.03, 0.012, 0.022), loc=(-0.02, y, 0.118), mat='metal_dark', bevel=0.003, segs=1)
        with b.at(loc=(0.78, -0.6, 0), rot=(0, 0, 0)):
            basket(b, 0.22, 0.2)
            apples(b, 0.14, 0.14, n=7, hi=0)
        # ---- hanging herbs + garlic on a cord between the front poles ------------------------------------------
        cy = Y0 + 0.03

        def cord_z(x):
            return 2.03 + 0.04 * (x / PX) ** 2

        b.tube([(x, cy, cord_z(x)) for x in (-PX, -0.6, 0, 0.6, PX)], 0.006, mat='rope', segs=5, caps=False)
        herbs = [(-0.52, srgb(96, 112, 70), srgb(150, 160, 104), 0.25), (-0.24, srgb(104, 100, 70), srgb(134, 104, 168), 0.3),
                 (0.2, srgb(120, 104, 60), srgb(204, 170, 84), 0.27), (0.5, srgb(84, 104, 66), srgb(128, 150, 92), 0.24),
                 (0.78, srgb(110, 84, 58), srgb(176, 110, 70), 0.29)]
        for x, c0, c1, ln in herbs:
            with b.at(loc=(x, cy, cord_z(x) - 0.004), rot=(R(b, -5, 5), R(b, -5, 5), R(b, 0, 360))):
                herb_bundle(b, c0, c1, ln)
        with b.at(loc=(-0.8, cy, cord_z(-0.8))):
            b.tube([(0, 0, 0), (0.004, 0, -0.14), (0, 0, -0.3)], 0.005, mat='rope', segs=4)
            for i in range(7):
                a = i * 2.2
                b.blob((0.03, 0.03, 0.034), loc=(0.026 * math.cos(a), 0.026 * math.sin(a), -0.07 - i * 0.036), mat='plant', subdiv=1,
                       color=srgb(232, 222, 196), jitter=0.08)
        # ---- lantern on an iron bracket, front-left pole --------------------------------------------------------
        lx, ly = -PX, Y0 + 0.0
        b.tube([(lx, ly, 1.97), (lx, ly - 0.16, 2.02), (lx, ly - 0.27, 2.0), (lx, ly - 0.3, 1.95)], 0.011, mat='metal_dark', segs=6)
        b.tube([(lx, ly, 1.8), (lx, ly - 0.12, 1.9), (lx, ly - 0.2, 2.0)], 0.008, mat='metal_dark', segs=5)
        with b.at(loc=(lx, ly - 0.3, 1.955)):
            lc = lantern(b, 0.85)
            mark(b, 'stall_lantern_light', lc)
        # ---- hanging sign board on the front-right pole (blank panel: the game draws the text) ---------------------
        sx0 = PX
        wood(b, (0.8, 0.045, 0.05), loc=(sx0 + 0.37, cy, 1.93), rot=(0, -2, 0), mat='wood_dark', bevel=0.012, segs=2)
        wood(b, (0.42, 0.035, 0.04), loc=(sx0 + 0.16, cy, 1.78), rot=(0, -45, 0), mat='wood_dark', bevel=0.01, segs=1)
        with b.at(loc=(sx0 + 0.44, cy, 1.64), rot=(0, 2.5, 3)):
            for k, z in enumerate((0.085, -0.085)):
                wood(b, (0.6 + R(b, -0.015, 0.02), 0.035, 0.165), loc=(R(b, -0.008, 0.008), 0, z), mat='wood_light', bevel=0.012, segs=2,
                     jitter=0.12, rj=0.6)
            for sy in (-1, 1):
                b.box((0.5, 0.006, 0.24), loc=(0, sy * 0.02, 0), mat='paint', color=CREAM, bevel=0, grain=None, jitter=0.04)
                for z in (-0.13, 0.13):
                    b.box((0.54, 0.01, 0.022), loc=(0, sy * 0.021, z), mat='paint', color=GREEN, bevel=0.003, segs=1)
                for x in (-0.26, 0.26):
                    b.box((0.022, 0.01, 0.28), loc=(x, sy * 0.021, 0), mat='paint', color=GREEN, bevel=0.003, segs=1)
            for x in (-0.22, 0.22):
                b.tube([(x, 0, 0.165), (x + 0.004, 0, 0.215), (x, 0, 0.27)], 0.006, mat='metal_dark', segs=5)
        # ---- stool behind the cart --------------------------------------------------------------------------------
        with b.at(loc=(1.02, 0.72, 0), rot=(0, 0, 25)):
            stool(b)
        mark(b, 'stall_front', (0, Y0 - 0.42 - 1.3, 0))
        mark(b, 'stall_keeper', (0.2, Y1 + 0.5, 0))
    return b.build(sharp_angle=50)


# ============================================================================================
# ROYAL DELIVERY CRATE
# ============================================================================================
def build_delivery_crate():
    b = Builder('delivery_crate', seed=82)
    W, D, H = 0.86, 0.6, 0.55
    for x in (-0.28, 0.28):
        wood(b, (0.085, D + 0.02, 0.04), loc=(x, 0, 0.02), mat='wood_dark', bevel=0.01, segs=1)
    b.box((W - 0.03, D - 0.03, 0.02), loc=(0, 0, 0.05), mat='wood_plank', bevel=0, grain=0, color=(0.7, 0.7, 0.7))
    ph = (H - 0.045) / 3
    for k, (L, off) in enumerate(((W, D / 2), (D, W / 2), (W, D / 2), (D, W / 2))):
        with b.at(rot=(0, 0, k * 90)):
            for i in range(3):
                wood(b, (L - 0.03 + R(b, -0.008, 0.008), 0.026, ph - 0.008), loc=(R(b, -0.005, 0.005), -off + 0.014, 0.042 + (i + 0.5) * ph),
                     mat='wood_light', bevel=0.01, segs=1, jitter=0.13, rj=0.6)
            b.box((L - 0.07, 0.006, H - 0.07), loc=(0, -off + 0.03, 0.045 + (H - 0.07) / 2), mat='wood_dark', bevel=0, grain=None,
                  color=(0.6, 0.6, 0.6))
            for sx in (-1, 1):
                wood(b, (0.075, 0.03, H - 0.03), loc=(sx * (L / 2 - 0.04), -off - 0.012, H / 2 + 0.012), mat='wood_plank', bevel=0.011, segs=1,
                     jitter=0.1, rj=0.4)
            # royal blue cap rail with a gold line
            b.box((L + 0.035, 0.05, 0.026), loc=(0, -off + 0.004, H + 0.006), mat='paint', color=BLUE, jitter=0.08, bevel=0.009, segs=2, grain=0)
            if k % 2 == 0:
                b.box((L - 0.17, 0.005, 0.012), loc=(0, -off - 0.0005, H - 0.035), mat='gold', bevel=0, grain=None)
                for sx in (-1, 1):
                    for z in (0.085, H - 0.075):
                        b.box((0.085, 0.007, 0.075), loc=(sx * (L / 2 - 0.04), -off - 0.029, z), mat='metal_dark', bevel=0.003, segs=1)
                        for dx, dz in ((-0.022, 0.02), (0.022, -0.02)):
                            b.box((0.014, 0.008, 0.014), loc=(sx * (L / 2 - 0.04) + dx, -off - 0.034, z + dz), rot=(0, 45, 0), mat='metal',
                                  bevel=0, grain=None)
            else:
                # rope handle through a cleat
                wood(b, (0.32, 0.03, 0.085), loc=(0, -off - 0.012, 0.36), mat='wood_plank', bevel=0.01, segs=2)
                o = -off - 0.028
                arc = [(-0.1 * math.cos(t), o - 0.014 - 0.04 * math.sin(t), 0.362 - 0.1 * math.sin(t) ** 1.3) for t in
                       [math.pi * i / 10 for i in range(11)]]
                b.tube([(-0.1, o + 0.02, 0.365)] + arc + [(0.1, o + 0.02, 0.365)], 0.014, mat='rope', segs=7, jitter=0.06)
                for sx in (-1, 1):
                    b.blob(0.021, loc=(sx * 0.1, o - 0.004, 0.364), mat='rope', subdiv=1)
    # stencilled crest + stencil bars on the front
    with b.at(loc=(0, -D / 2 - 0.0005, 0.262)):
        stencil_crest(b, 0.62)
        for sx in (-1, 1):
            for z, ln in ((0.03, 0.15), (-0.015, 0.11)):
                b.box((ln, 0.004, 0.02), loc=(sx * (0.2 + ln / 2), -0.002, z), mat='paint', color=BLUE, bevel=0, grain=None)
    # straw packing
    zs = 0.385
    b.box((W - 0.07, D - 0.07, 0.3), loc=(0, 0, zs - 0.15), mat='straw', bevel=0.045, segs=2, grain=0, jitter=0.05)
    for i in range(3):
        b.blob((R(b, 0.16, 0.22), R(b, 0.13, 0.17), 0.035), loc=(-0.26 + i * 0.26 + R(b, -0.03, 0.03), R(b, -0.07, 0.07), zs - 0.008),
               mat='straw', subdiv=2, noise_amp=0.25, noise_scale=2.2, color=(0.86, 0.86, 0.86), color_top=(1.05, 1.05, 1.05))
    for _ in range(50):
        straw(b, (R(b, -W / 2 + 0.07, W / 2 - 0.07), R(b, -D / 2 + 0.07, D / 2 - 0.07), zs + R(b, 0.0, 0.03)),
              (R(b, 62, 100) * b.rng.choice((-1, 1)), R(b, -25, 25), R(b, 0, 360)), ln=R(b, 0.09, 0.2))
    for _ in range(16):   # wisps poking over the rim
        k = b.rng.randrange(4)
        L, off = ((W, D / 2), (D, W / 2))[k % 2]
        with b.at(rot=(0, 0, k * 90)):
            straw(b, (R(b, -L / 2 + 0.08, L / 2 - 0.08), -off + 0.05, zs + 0.01), (R(b, 20, 50), R(b, -30, 30), 0), ln=R(b, 0.14, 0.22),
                  bend=R(b, 30, 70))
    mark(b, 'crate_inside', (0, 0, zs + 0.02))
    return b.build(sharp_angle=50)


# ============================================================================================
# MILL HOPPER
# ============================================================================================
def build_mill_hopper():
    b = Builder('mill_hopper', seed=83)
    Z0, Z1 = 0.80, 1.25
    TX, TY, BXh, BYh, TH = 0.36, 0.31, 0.12, 0.11, 0.026

    def hx(z):
        return BXh + (TX - BXh) * (z - Z0) / (Z1 - Z0)

    def hy(z):
        return BYh + (TY - BYh) * (z - Z0) / (Z1 - Z0)

    # ---- funnel: four leaning walls of three planks each -------------------------------------------
    for k in range(4):
        wt, wb, ot, ob = (TX, BXh, TY, BYh) if k % 2 == 0 else (TY, BYh, TX, BXh)
        a = math.degrees(math.atan2(ot - ob, Z1 - Z0))
        L = math.hypot(ot - ob, Z1 - Z0)
        with b.at(rot=(0, 0, k * 90)):
            with b.at(loc=(0, -ob, Z0), rot=(a, 0, 0)):
                for i in range(3):
                    z0, z1 = i * L / 3 + 0.003, (i + 1) * L / 3 - 0.003
                    w0 = wb + (wt - wb) * z0 / L + 0.012 + R(b, 0, 0.006)
                    w1 = wb + (wt - wb) * z1 / L + 0.012 + R(b, 0, 0.006)
                    b.prism([(-w0, z0), (w0, z0), (w1, z1), (-w1, z1)], TH, loc=(0, TH / 2 + R(b, -0.002, 0.002), 0), mat='wood_plank',
                            bevel=0.008, segs=1, grain=0, jitter=0.14)
                # corner cleats
                for sx in (-1, 1):
                    ang = math.degrees(math.atan2(wt - wb, L))
                    wood(b, (0.035, 0.02, L - 0.03), loc=(sx * ((wt + wb) / 2 - 0.012), -0.008, L / 2), rot=(0, sx * ang, 0), mat='wood_dark',
                         bevel=0.006, jitter=0.1)
    for sy in (-1, 1):
        wood(b, (2 * TX + 0.1, 0.055, 0.05), loc=(0, sy * (TY + 0.005), Z1 + 0.005), mat='wood_dark', bevel=0.014, segs=2, rj=0.5)
    for sx in (-1, 1):
        wood(b, (0.055, 2 * TY + 0.0, 0.05), loc=(sx * (TX + 0.005), 0, Z1 + 0.005), mat='wood_dark', bevel=0.014, segs=2, rj=0.5)
    b.box((2 * BXh + 0.07, 2 * BYh + 0.07, 0.06), loc=(0, 0, Z0 - 0.005), mat='metal_dark', bevel=0.008, segs=1, grain=None)
    wood(b, (2 * BXh, 2 * BYh, 0.07), loc=(0, 0, Z0 - 0.055), mat='wood_plank', bevel=0.008)
    # ---- stand ---------------------------------------------------------------------------------------
    LT = 1.06
    for sx in (-1, 1):
        for sy in (-1, 1):
            wood(b, (0.075, 0.075, LT + 0.01), loc=(sx * 0.33, sy * 0.295, LT / 2), rot=(sy * 3.8, -sx * 3.2, 0), mat='wood_dark', bevel=0.016,
                 segs=2, rj=0.5)
    zt = 1.0
    for sy in (-1, 1):
        wood(b, (0.72, 0.04, 0.085), loc=(0, sy * (hy(zt) + 0.047), zt), bevel=0.012, segs=2, rj=0.4)
    for sx in (-1, 1):
        wood(b, (0.04, 0.6, 0.085), loc=(sx * (hx(zt) + 0.05), 0, zt), bevel=0.012, segs=2, rj=0.4)
        wood(b, (0.04, 0.7, 0.06), loc=(sx * 0.343, 0, 0.32), bevel=0.012, segs=1, rj=0.5)
    wood(b, (0.74, 0.04, 0.06), loc=(0, 0.312, 0.32), bevel=0.012, segs=1, rj=0.5)
    wood(b, (0.94, 0.03, 0.055), loc=(0, 0.325, 0.66), rot=(0, -43, 0), bevel=0.01, segs=1)
    wood(b, (0.74, 0.045, 0.05), loc=(0, -0.3, 0.52), mat='wood_dark', bevel=0.012, segs=1)
    # ---- lid, hinged at the back, propped open -----------------------------------------------------------
    A = 54.0
    hinge = Vector((0, TY + 0.03, Z1 + 0.035))
    lidrot = Euler((math.radians(-A), 0, 0), 'XYZ').to_matrix()
    with b.at(loc=hinge, rot=(-A, 0, 0)):
        for i in range(4):
            wood(b, (0.8 + R(b, -0.015, 0.015), 0.158, 0.024), loc=(R(b, -0.006, 0.006), -0.085 - i * 0.163, 0.012), bevel=0.01, segs=2,
                 jitter=0.14, rj=0.4)
        for x in (-0.25, 0.25):
            wood(b, (0.055, 0.6, 0.022), loc=(x, -0.34, -0.011), mat='wood_dark', bevel=0.008)
            b.box((0.04, 0.24, 0.007), loc=(x, -0.115, 0.027), mat='metal_dark', bevel=0.003, segs=1)
            b.cyl(0.013, 0.08, loc=(x - 0.04, 0.0, 0.012), rot=(0, 90, 0), mat='metal_dark', segs=6, bevel=0.003)
    tip = hinge + lidrot @ Vector((0.33, -0.5, -0.022))
    pole(b, [(0.335, -TY + 0.01, Z1 + 0.03), tuple(tip)], 0.012, mat='wood_light', segs=6)
    # ---- grain inside + spill -----------------------------------------------------------------------------
    b.box((0.5, 0.43, 0.08), loc=(0, 0, 1.14), mat='straw', bevel=0.02, segs=1, grain=None, taper=(1.17, 1.17), color=tint(GRAIN_C, 0.85))
    b.blob((0.27, 0.22, 0.03), loc=(-0.03, 0.02, 1.172), mat='straw', subdiv=3, noise_amp=0.1, noise_scale=3.5, color=tint(GRAIN_C, 0.8),
           color_top=GRAIN_C)
    b.blob((0.1, 0.04, 0.012), loc=(-0.2, -TY - 0.005, Z1 + 0.03), mat='straw', subdiv=2, noise_amp=0.3, noise_scale=4.0, color=GRAIN_C)
    for _ in range(26):
        grain(b, (-0.2 + R(b, -0.12, 0.12), -TY - 0.008 + R(b, -0.03, 0.03), Z1 + 0.034 + R(b, 0, 0.01)), s=1.2)
    b.blob((0.13, 0.1, 0.022), loc=(-0.24, -0.58, 0.004), mat='straw', subdiv=2, noise_amp=0.25, noise_scale=3.0, flatten_bottom=-0.2,
           color=tint(GRAIN_C, 0.82), color_top=GRAIN_C)
    for _ in range(26):
        a, rr = R(b, 0, 6.28), R(b, 0.05, 0.24)
        grain(b, (-0.24 + rr * math.cos(a), -0.58 + rr * math.sin(a) * 0.8, 0.006), s=1.2)
    wheat_stalk(b, (0.02, -TY + 0.03, Z1 + 0.04), (-0.55, -0.75, -0.12), 0.3)
    wheat_stalk(b, (-0.12, -TY + 0.06, Z1 + 0.045), (-0.2, -0.95, -0.2), 0.27)
    wheat_stalk(b, (-0.5, -0.6, 0.012), (0.9, -0.3, 0.02), 0.3)
    # ---- chute + sack hooks + empty sack ---------------------------------------------------------------------
    ca = 22.5
    with b.at(loc=(0, 0.07, 0.715), rot=(ca, 0, 0)):
        for i, x in enumerate((-0.065, 0.065)):
            wood(b, (0.128, 0.7 + R(b, -0.01, 0.02), 0.02), loc=(x, -0.34, 0), mat='wood_light', bevel=0.007, jitter=0.14)
        for sx in (-1, 1):
            wood(b, (0.02, 0.7, 0.1), loc=(sx * 0.138, -0.34, 0.035), mat='wood_light', bevel=0.007, jitter=0.14, rj=0.4)
        wood(b, (0.3, 0.02, 0.1), loc=(0, 0.015, 0.035), mat='wood_light', bevel=0.007, jitter=0.12)
        b.box((0.31, 0.03, 0.008), loc=(0, -0.55, -0.014), mat='metal_dark', bevel=0.003, segs=1)
        # a trickle of grain in the chute
        for _ in range(10):
            grain(b, (R(b, -0.08, 0.08), R(b, -0.6, -0.1), 0.014))
    ey, ez = 0.07 - 0.69 * math.cos(math.radians(ca)), 0.715 - 0.69 * math.sin(math.radians(ca))
    b.tube([(-0.17, ey, ez - 0.02), (0.17, ey, ez - 0.02)], 0.008, mat='metal_dark', segs=6)
    for sx in (-1, 1):
        x = sx * 0.135
        b.tube([(x, ey, ez - 0.02), (x, ey - 0.012, ez - 0.07), (x, ey - 0.035, ez - 0.085), (x, ey - 0.05, ez - 0.06)], 0.006, mat='metal_dark',
               segs=5)
    mz = ez - 0.07   # sack mouth height
    SH = mz - 0.035

    def srad(a, z):
        t = z / SH
        return 1 + 0.06 * math.sin(4 * a + z * 11) * (1 - t) + 0.05 * math.sin(2 * a + 1.0) - 0.12 * math.sin(math.pi * min(1, t * 1.15)) ** 2

    v0 = nverts(b)
    b.lathe([(0, 0), (0.1, 0.004), (0.15, 0.04), (0.158, 0.13), (0.15, SH * 0.6), (0.146, SH * 0.88), (0.152, SH), (0.14, SH + 0.004),
             (0.132, SH * 0.88), (0.12, SH * 0.7), (0, SH * 0.66)], loc=(0, ey - 0.035, 0.035), scale=(1, 0.36, 1), mat='cloth', segs=16,
            color=tint(BURLAP, 0.78), color_top=tint(BURLAP, 1.06), radial=srad)
    sy0 = ey - 0.035

    def limp(c):
        t = max(0.0, min(1.0, (c.z - 0.035) / SH))
        u = max(-1.0, min(1.0, c.x / 0.15))
        if t > 0.6:   # the mouth sags between the two hooks
            c.z -= 0.075 * ((t - 0.6) / 0.4) ** 1.5 * (1 - u * u)
        c.y = sy0 + (c.y - sy0) * (0.55 + 0.75 * (1 - t) ** 1.5) - 0.02 * math.sin(t * 2.6)
        c.x += 0.012 * math.sin(t * 5.0)
        return c

    deform_since(b, v0, limp)
    mark(b, 'hopper_top', (0, 0, Z1))
    mark(b, 'hopper_out', (0, ey - 0.5, 0))
    return b.build(sharp_angle=50)


# ============================================================================================
# COMPOST BAY (+ separate heap)
# ============================================================================================
HEAP_R = (0.56, 0.43, 0.36)


def heap_z(x, y):
    rx, ry, rz = HEAP_R
    d = 1 - (x / rx) ** 2 - (y / ry) ** 2
    return 0.3 * rz + rz * math.sqrt(max(d, 0.0)) if d > 0 else 0.0


def build_compost_heap():
    b = Builder('compost_heap', seed=85)
    rx, ry, rz = HEAP_R
    b.blob(HEAP_R, loc=(0, 0, 0.3 * rz), mat='soil', subdiv=4, noise_amp=0.13, noise_scale=2.6, flatten_bottom=-0.3, color=(0.72, 0.7, 0.68),
           color_top=(1.1, 1.05, 1.0))
    for _ in range(34):
        a, k = R(b, 0, 6.28), R(b, 0.25, 0.92)
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        s = R(b, 0.025, 0.06)
        b.blob((s, s * R(b, 0.7, 1.0), s * 0.7), loc=(x, y, heap_z(x, y) * 0.97), mat='soil', subdiv=1, noise_amp=0.25, color=(R(b, 0.75, 1.1),) * 3,
               rot=(R(b, 0, 90), 0, R(b, 0, 180)))
    for _ in range(46):
        a, k = R(b, 0, 6.28), math.sqrt(R(b, 0.02, 0.85))
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        straw(b, (x, y, heap_z(x, y) + 0.012), (R(b, 55, 95) * b.rng.choice((-1, 1)), R(b, -30, 30), R(b, 0, 360)), ln=R(b, 0.08, 0.2))
    scraps = [srgb(120, 134, 62), srgb(112, 84, 46), srgb(150, 120, 54), srgb(84, 110, 56), srgb(170, 96, 50)]
    for _ in range(12):
        a, k = R(b, 0, 6.28), math.sqrt(R(b, 0.02, 0.7))
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        c = b.rng.choice(scraps)
        b.leaf(R(b, 0.09, 0.16), R(b, 0.05, 0.08), loc=(x, y, heap_z(x, y) + 0.015), rot=(R(b, 60, 85) * b.rng.choice((-1, 1)), R(b, -20, 20), R(b, 0, 360)),
               mat='plant', bend=R(b, 20, 70), fold=25, segs=3, color=tint(c, 0.8), color_top=c, jitter=0.15)
    return b.build(sharp_angle=70)


def build_compost_bay():
    b = Builder('compost_bay', seed=84)
    PXc, PYc = 0.63, 0.47
    tops = {(-1, 1): 0.86, (1, 1): 0.9, (-1, -1): 0.84, (1, -1): 0.88}
    for (sx, sy), top in tops.items():
        wood(b, (0.095, 0.095, top + 0.02), loc=(sx * PXc, sy * PYc, top / 2 - 0.01), mat='wood_dark', bevel=0.018, segs=2, rj=1.2, taper=(0.94, 0.94))
        wood(b, (0.089, 0.089, 0.05), loc=(sx * PXc, sy * PYc, top + 0.02), mat='wood_dark', bevel=0.018, segs=2, taper=(0.45, 0.45), jitter=0.1)
    for i in range(4):
        z = 0.115 + i * 0.185
        wood(b, (1.4 + R(b, -0.05, 0.03), 0.03, 0.14 + R(b, -0.012, 0.008)), loc=(R(b, -0.02, 0.02), PYc + 0.062, z + R(b, -0.008, 0.008)),
             bevel=0.012, segs=2, jitter=0.16, rj=1.0)
        for sx in (-1, 1):
            slip = (0, 0, 0) if not (i == 3 and sx == 1) else (2.6, 0, 0)
            wood(b, (0.03, 1.08 + R(b, -0.05, 0.03), 0.14 + R(b, -0.012, 0.008)), loc=(sx * (PXc + 0.062), R(b, -0.02, 0.02), z + R(b, -0.008, 0.008)),
                 rot=slip, bevel=0.012, segs=2, jitter=0.16, rj=1.0)
    # nail heads
    for i in range(4):
        z = 0.115 + i * 0.185
        for sx in (-1, 1):
            b.box((0.016, 0.006, 0.016), loc=(sx * PXc, PYc + 0.079, z + 0.02), rot=(0, 45, 0), mat='metal_dark', bevel=0, grain=None)
            for sy in (-1, 1):
                b.box((0.006, 0.016, 0.016), loc=(sx * (PXc + 0.079), sy * PYc, z + 0.02), rot=(45, 0, 0), mat='metal_dark', bevel=0, grain=None)
    # spilled straw + crumbs at the open front
    for _ in range(14):
        straw(b, (R(b, -0.5, 0.5), R(b, -0.72, -0.45), 0.008), (R(b, 75, 100) * b.rng.choice((-1, 1)), R(b, -10, 10), R(b, 0, 360)), ln=R(b, 0.1, 0.2))
    for _ in range(5):
        s = R(b, 0.025, 0.045)
        b.blob((s, s, s * 0.7), loc=(R(b, -0.45, 0.45), R(b, -0.68, -0.5), s * 0.4), mat='soil', subdiv=1, noise_amp=0.2)
    # ---- pitchfork: tines on the ground, shaft resting on the front-right post -----------------------------
    G = Vector((1.0, -0.86, 0.0))
    d = (Vector((PXc + 0.058, -PYc - 0.058, 0.875)) - G).normalized()
    side = d.cross(Vector((0, 0, 1))).normalized()
    nrm = side.cross(d).normalized()
    T = G + d * 1.5
    mid = G + d * 0.9 + nrm * 0.006
    pole(b, [tuple(G + d * 0.33), tuple(mid), tuple(T)], [0.019, 0.018, 0.017], mat='wood_light', segs=8)
    b.tube([tuple(G + d * 0.27), tuple(G + d * 0.4)], 0.023, mat='metal_dark', segs=8)
    b.tube([tuple(G + d * 0.29 - side * 0.105), tuple(G + d * 0.3), tuple(G + d * 0.29 + side * 0.105)], 0.009, mat='metal_dark', segs=6)
    for k in (-1.5, -0.5, 0.5, 1.5):
        o = side * (0.07 * k)
        b.tube([tuple(G + d * 0.29 + o), tuple(G + d * 0.2 + o * 1.02 - nrm * 0.012), tuple(G + d * 0.1 + o * 1.04 - nrm * 0.016),
                tuple(G + o * 1.05 + nrm * 0.004)], [0.008, 0.0075, 0.006, 0.003], mat='metal_dark', segs=5)
    mark(b, 'compost_front', (0, -PYc - 0.75, 0))
    root = b.build(sharp_angle=50)
    CHILDREN['compost_bay'] = [(build_compost_heap(), (0.0, 0.03, 0.0))]
    return root


# ============================================================================================
# HAY BED
# ============================================================================================
def build_hay_bed():
    b = Builder('hay_bed', seed=86)
    LX, WY = 0.9, 0.355
    for sx, top in ((-1, 0.8), (1, 0.52)):
        for sy in (-1, 1):
            wood(b, (0.085, 0.085, top), loc=(sx * LX, sy * WY, top / 2), mat='wood_dark', bevel=0.018, segs=2, rj=0.6)
            wood(b, (0.08, 0.08, 0.045), loc=(sx * LX, sy * WY, top + 0.018), mat='wood_dark', bevel=0.016, segs=2, taper=(0.5, 0.5))
    for sy in (-1, 1):
        wood(b, (1.74 + R(b, -0.01, 0.01), 0.04, 0.15), loc=(0, sy * (WY + 0.005), 0.3), bevel=0.014, segs=2, rj=0.4, jitter=0.12)
    wood(b, (0.036, 0.64, 0.15), loc=(-LX, 0, 0.3), bevel=0.012, segs=2, jitter=0.12)
    wood(b, (0.036, 0.64, 0.15), loc=(LX, 0, 0.3), bevel=0.012, segs=2, jitter=0.12)
    wood(b, (0.036, 0.64, 0.1), loc=(LX, 0, 0.44), bevel=0.012, segs=2, jitter=0.12, rj=0.6)
    for z, h in ((0.5, 0.14), (0.66, 0.15)):
        wood(b, (0.036, 0.64 + R(b, -0.01, 0.01), h), loc=(-LX, 0, z), bevel=0.012, segs=2, jitter=0.14, rj=0.7)
    for i in range(6):
        wood(b, (0.15, 0.7, 0.024), loc=(-0.75 + i * 0.3 + R(b, -0.02, 0.02), 0, 0.345), bevel=0.008, jitter=0.14, rj=0.8)
    # straw layer + ticking mattress
    b.box((1.72, 0.68, 0.11), loc=(0, 0, 0.41), mat='straw', bevel=0.04, segs=2, grain=0, jitter=0.05)
    mz = 0.595
    linen = srgb(204, 190, 158)
    b.box((1.7, 0.66, 0.14), loc=(0, 0, mz - 0.07), mat='cloth', color=tint(linen, 0.82), color_top=linen, bevel=0.05, segs=3, grain=0)
    b.box((0.16, 0.008, 0.075), loc=(0.2, -0.332, mz - 0.07), rot=(0, 5, 0), mat='cloth', color=srgb(150, 120, 86), bevel=0.003, segs=1)
    for _ in range(56):
        sy = b.rng.choice((-1, 1))
        if b.rng.random() < 0.8:
            straw(b, (R(b, -0.84, 0.84), sy * 0.335, 0.4 + R(b, -0.03, 0.05)), (-sy * R(b, 60, 125), R(b, -35, 35), 0), ln=R(b, 0.08, 0.18))
        else:
            sx = b.rng.choice((-1, 1))
            straw(b, (sx * 0.85, R(b, -0.3, 0.3), 0.42 + R(b, -0.02, 0.04)), (R(b, -30, 30), sx * R(b, 60, 120), 0), ln=R(b, 0.07, 0.14))
    # pillow at the head (-X)
    pr = (0.17, 0.26, 0.075)

    def pillow(c):
        ux, uy = c.x / pr[0], c.y / pr[1]
        sq = lambda u: math.copysign(abs(u) ** 0.6, u)   # noqa: E731
        edge = max(abs(ux), abs(uy))
        return Vector((sq(ux) * pr[0], sq(uy) * pr[1], c.z * (1 - 0.35 * edge ** 3) - 0.012 * math.exp(-(ux * ux + uy * uy) * 5)))

    b.blob(pr, loc=(-0.6, 0.01, mz + 0.062), rot=(0, 3, 7), mat='cloth', subdiv=3, color=tint(CREAM, 0.84), color_top=CREAM, deform=pillow)
    # folded patchwork quilt at the foot (+X)
    path = []
    z1, z2, z3 = 0.022, 0.085, 0.146
    for i in range(6):
        path.append((0.84 - i * 0.108, z1))
    path += [(0.268, z1 + 0.012), (0.258, (z1 + z2) / 2), (0.268, z2 - 0.012)]
    for i in range(5):
        path.append((0.3 + i * 0.108, z2))
    path += [(0.765, z2 + 0.012), (0.775, (z2 + z3) / 2), (0.765, z3 - 0.012)]
    for i in range(5):
        path.append((0.733 - i * 0.1, z3))
    NVq = len(path) - 1
    NUq = 6
    cols = [[b.rng.choice(QUILT) for _ in range(NVq)] for _ in range(NUq)]

    def qpos(u, v):
        j = int(round(v * NVq))
        x, z = path[j]
        y = -0.31 + u * 0.62
        puff = 0.006 * math.sin(u * NUq * math.pi) ** 2
        return (x + 0.01 * math.sin(u * 5 + j), y, mz + z + 0.006 * math.sin(x * 14 + u * 4) + puff)

    def qcol(i, j):
        c = cols[i][j]
        if (j in (6, 7, 8, 14, 15, 16)):
            c = cols[i][5 if j < 9 else 13]
        return tint(c, R(b, 0.92, 1.05))

    with b.at(loc=(0.02, 0.0, 0), rot=(0, 0, 3.5)):
        sheet(b, NUq, NVq, qpos, qcol, mat='cloth', thick=0.034, uvsize=(0.62, 2.0), back=0.9)
    return b.build(sharp_angle=50)


# ============================================================================================
# NEST BOX
# ============================================================================================
def build_nest_box():
    b = Builder('nest_box', seed=87)
    W, D, HF, HB = 0.45, 0.36, 0.3, 0.39
    for x in (-0.15, 0.15):
        wood(b, (0.05, D + 0.02, 0.035), loc=(x, 0, 0.0175), mat='wood_dark', bevel=0.008)
    wood(b, (W - 0.01, D - 0.01, 0.02), loc=(0, 0, 0.045), bevel=0.006, jitter=0.12)
    for sx in (-1, 1):
        with b.at(loc=(sx * (W / 2 - 0.011), 0, 0), rot=(0, 0, 90)):
            b.prism([(-D / 2, 0.036), (D / 2, 0.036), (D / 2, 0.2), (-D / 2, 0.2)], 0.022, mat='wood_plank', bevel=0.008, segs=1, grain=0, jitter=0.15)
            b.prism([(-D / 2, 0.205), (D / 2, 0.205), (D / 2, HB), (-D / 2, HF)], 0.022, mat='wood_plank', bevel=0.008, segs=1, grain=0, jitter=0.15)
    for z0, z1 in ((0.036, 0.2), (0.205, HB)):
        wood(b, (W - 0.046, 0.02, z1 - z0), loc=(0, D / 2 - 0.01, (z0 + z1) / 2), bevel=0.008, jitter=0.15, rj=0.5)
    wood(b, (W + 0.012, 0.022, 0.085), loc=(0, -D / 2 + 0.006, 0.079), bevel=0.01, segs=2, jitter=0.12, rj=0.6)
    wood(b, (W + 0.012, 0.022, 0.055), loc=(0, -D / 2 + 0.006, HF - 0.03), bevel=0.01, segs=2, jitter=0.12, rj=0.6)
    # sloping plank roof
    sl = math.degrees(math.atan2(HB - HF, D))
    with b.at(loc=(0, 0, (HF + HB) / 2 + 0.016), rot=(sl, 0, 0)):
        for i in range(3):
            wood(b, (W + 0.07 + R(b, -0.012, 0.012), 0.146, 0.02), loc=(R(b, -0.006, 0.006), -0.175 + i * 0.151, R(b, -0.002, 0.002)), mat='wood_dark',
                 bevel=0.008, segs=2, jitter=0.14, rj=0.6)
    # perch
    for sx in (-1, 1):
        wood(b, (0.022, 0.09, 0.022), loc=(sx * 0.17, -D / 2 - 0.04, 0.05), mat='wood_dark', bevel=0.006)
    pole(b, [(-0.21, -D / 2 - 0.075, 0.06), (0.21, -D / 2 - 0.075, 0.062)], 0.012, mat='wood_light', segs=6)
    # straw nest: a padded floor + a woven ring
    b.box((W - 0.05, D - 0.05, 0.05), loc=(0, 0, 0.078), mat='straw', bevel=0.02, segs=1, grain=0, color=(0.8, 0.8, 0.8))
    NR, RY = 0.135, 0.8
    ring = []
    for i in range(15):
        a = i * 2 * math.pi / 14
        ring.append((NR * math.cos(a) * R(b, 0.96, 1.04), NR * RY * math.sin(a) * R(b, 0.96, 1.04), 0.118 + R(b, -0.006, 0.006)))
    ring[-1] = ring[0]
    b.tube(ring, 0.05, mat='straw', segs=7, caps=False, color=(0.92, 0.92, 0.92), jitter=0.05)
    b.blob((0.1, 0.085, 0.02), loc=(0, 0, 0.1), mat='straw', subdiv=2, color=(0.72, 0.72, 0.72))
    for _ in range(54):
        a = R(b, 0, 6.28)
        rr = NR + R(b, -0.04, 0.045)
        up = R(b, 0.0, 0.05)
        straw(b, (rr * math.cos(a), rr * RY * math.sin(a), 0.135 + up),
              (R(b, 70, 100) * b.rng.choice((-1, 1)), R(b, -14, 14), math.degrees(a) + R(b, -22, 22)), ln=R(b, 0.08, 0.16), bend=R(b, 10, 45))
    for _ in range(10):
        straw(b, (R(b, -0.17, 0.17), -D / 2 + 0.02, 0.125), (R(b, 30, 75), R(b, -30, 30), 0), ln=R(b, 0.08, 0.14), bend=R(b, 30, 70))
    mark(b, 'nest_eggs', (0, 0.0, 0.12))
    return b.build(sharp_angle=50)


# ============================================================================================
# REGISTRY / MAIN
# ============================================================================================
ASSETS = {'peddler_stall': build_peddler_stall, 'delivery_crate': build_delivery_crate, 'mill_hopper': build_mill_hopper,
          'compost_bay': build_compost_bay, 'hay_bed': build_hay_bed, 'nest_box': build_nest_box}
# preview groups: name -> (asset names, spacing, views[(az, el)], zoom)
GROUPS = {
    'stall': (['peddler_stall'], 0, [(30, 16), (-35, 14), (150, 20)], 1.25),
    'crate': (['delivery_crate'], 0, [(25, 28), (-150, 30)], 1.25),
    'hopper': (['mill_hopper'], 0, [(30, 16), (-40, 20), (150, 22)], 1.25),
    'compost': (['compost_bay'], 0, [(25, 24), (-40, 30)], 1.25),
    'bed': (['hay_bed'], 0, [(25, 26), (-145, 28)], 1.25),
    'nest': (['nest_box'], 0, [(22, 22), (-30, 30)], 1.25),
}
# close-ups: group -> [(tag, centre, size, az, el)]
FOCUS = {
    'stall': [('counter', (-0.25, -0.35, 1.2), 1.7, 14, 16), ('rack', (-0.75, 0.0, 1.6), 1.3, -8, 6), ('under', (-0.25, -0.6, 0.5), 1.8, 10, 8),
              ('sign', (1.1, -0.3, 1.8), 1.2, 20, 6)],
    'hopper': [('top', (0, 0, 1.3), 1.1, 20, 34), ('chute', (0, -0.45, 0.45), 1.1, 35, 12)],
    'crate': [('crest', (0, -0.3, 0.3), 0.75, 8, 10)],
    'compost': [('heap', (0, 0, 0.4), 1.3, 12, 30)],
    'bed': [('quilt', (0.45, 0, 0.65), 0.9, 30, 30)],
}
# first-person shots: group -> [(tag, camera position, look-at, lens mm)]
EYES = {
    'stall': [('eye', (-0.25, -3.72, 1.6), (-0.25, 0, 1.3), 24), ('eye_near', (-0.25, -2.02, 1.6), (-0.25, 0, 1.25), 22)],
    'hopper': [('eye', (0.5, -2.4, 1.6), (0, 0, 0.9), 30)],
    'compost': [('eye', (0.2, -2.6, 1.6), (0, 0, 0.45), 30)],
    'bed': [('eye', (0.3, -2.3, 1.6), (0, 0, 0.45), 30)],
}


def render_view(path, cam_loc, target, lens=28.0, size=(1000, 750)):
    """Like kit.render_preview but with an explicit camera (first-person shots)."""
    sc = bpy.context.scene
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = lens
    cam.location = Vector(cam_loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start = 0.05
    cam.data.clip_end = 200
    sc.camera = cam
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.86, 0.68)
    sun.data.angle = math.radians(4)
    sun.rotation_euler = Euler((math.radians(58), 0, math.radians(65)))
    fm = bpy.data.meshes.new('_pv_floor')
    fb = bmesh.new()
    bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=60)
    fb.to_mesh(fm)
    fb.free()
    floor = bpy.data.objects.new('_pv_floor', fm)
    floor.location = (0, 0, -0.001)
    sc.collection.objects.link(floor)
    fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
    try:
        fmat.use_nodes = True
        bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bs.inputs['Base Color'].default_value = (0.30, 0.38, 0.20, 1)
        bs.inputs['Roughness'].default_value = 0.9
    except Exception:
        pass
    fm.materials.append(fmat)
    w = sc.world or bpy.data.worlds.new('_pv_world')
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.55, 0.68, 0.85, 1)
        bg.inputs[1].default_value = 0.9
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'CYCLES'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    try:
        sc.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in (cam, sun, floor):
        bpy.data.objects.remove(o)
    print(f'[market] view {path}')


names = list(ASSETS)
if ONLY:
    names = [n for n in names if any(n in GROUPS[g][0] for g in ONLY)]
objs = {}
for n in names:
    o = ASSETS[n]()
    objs[n] = o
    for ch, loc in CHILDREN.get(n, []):
        kit.set_parent(ch, o, loc)
    for mname, pos in MARKS.get(n, []):
        kit.marker(mname, pos, parent=o)
    bpy.context.view_layer.update()
    fam = kit._descend([o])
    pts = [m.matrix_world @ Vector(c) for m in fam if m.type == 'MESH' for c in m.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    print(f'ASSET {n:14s} tris={kit.tri_count(fam)} bbox=({lo[0]:.2f},{lo[1]:.2f},{lo[2]:.2f})..({hi[0]:.2f},{hi[1]:.2f},{hi[2]:.2f}) '
          f'mats={sorted({m.name for f_ in fam if f_.type == "MESH" for m in f_.data.materials})}')
    for ch, loc in CHILDREN.get(n, []):
        print(f'   child  {ch.name} ({loc[0]:.3f},{loc[1]:.3f},{loc[2]:.3f}) tris={kit.tri_count([ch])}')
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
        fam = kit._descend(sel)
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.hide_render = o not in fam
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
        for tag, cam_loc, target, lens in EYES.get(g, []):
            render_view(os.path.join(PREV, f'{g}_{tag}.png'), cam_loc, target, lens)
    for o in bpy.data.objects:
        o.hide_render = False
