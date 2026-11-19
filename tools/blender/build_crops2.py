"""Second crop set: carrot + cabbage (4 growth stages each) and their goods -> public/models/crops2.glb

  blender --background --factory-startup --python tools/blender/build_crops2.py -- [preview_dir|none] [shot,shot]

Always exports public/models/crops2.glb. Pass an ABSOLUTE preview dir to also render previews
(optional 2nd arg filters shots: carrot, cabbage, carrot_close, cabbage_close, top, compare, goods, goods_top).

Conventions follow build_vegetation.py (see kit.py):
- carrot_0..3 / cabbage_0..3: one object fills one 1.2 m field plot, origin at the soil surface centre.
  0 = sprout ... 3 = ripe. Plants are rooted at z=0 so the game's height-based wind sway works.
  Carrots: 3 x 3 plants. Cabbages: 2 x 2 plants. Plant positions are the same in every stage.
- item_carrot / item_cabbage: goods, origin bottom centre (style of item_tomato / item_pumpkin).
- Materials by name only: plant (all foliage, cabbage heads), plant_glossy (carrot roots), rope (twine).
  Vertex colours carry the real colour. Foliage is thin single-sided geometry: render double sided.
- Triangle budget: each stage <= the matching tomato stage (48 / 452 / 1194 / 1756), goods <= 3000.
"""
import sys
import os
import math
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, Euler  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = ARGS[0] if ARGS and ARGS[0] != 'none' else None
ONLY = set(ARGS[1].split(',')) if len(ARGS) > 1 else None
OUT = os.path.join(ROOT, 'public', 'models', 'crops2.glb')

kit.reset()
SHARP = 80
pi = math.pi
rad = math.radians
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


# ---------------------------------------------------------------- helpers ----
def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def tab(T, x):
    """Piecewise-linear lookup in [(x, y), ...]."""
    if x <= T[0][0]:
        return T[0][1]
    for i in range(len(T) - 1):
        if x <= T[i + 1][0]:
            t = (x - T[i][0]) / (T[i + 1][0] - T[i][0])
            return T[i][1] * (1 - t) + T[i + 1][1] * t
    return T[-1][1]


def aim(d):
    """Euler degrees (XYZ) that rotate local +Z onto direction d."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(d).normalized())
    return tuple(math.degrees(a) for a in q.to_euler('XYZ'))


def smooth_profile(ctrl, sub=3):
    """Catmull-Rom through (r,z) control points; keeps end points exactly."""
    P = [Vector((r, z)) for r, z in ctrl]
    out = []
    n = len(P)
    for i in range(n - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, n - 1)]
        for s in range(sub):
            t = s / sub
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
            out.append((max(q.x, 0.0), q.y))
    out.append((P[-1].x, P[-1].y))
    out[0] = (P[0].x, P[0].y)
    return out


def torus(b, R, m, z=0.0, n=10, **kw):
    prof = [(R + m * math.cos(rad(-90 + 360 * k / n)), z + m * math.sin(rad(-90 + 360 * k / n))) for k in range(n + 1)]
    b.lathe(prof, **kw)


class Raw:
    """Loose-geometry accumulator (verts + per-vertex colours + faces), emitted into a Builder in one go."""

    def __init__(self):
        self.v, self.c, self.f = [], [], []

    def add(self, p, col):
        self.v.append((p[0], p[1], p[2]))
        self.c.append(col)
        return len(self.v) - 1

    def tri(self, a, b, c, ca, cb=None, cc=None):
        i = self.add(a, ca)
        self.add(b, cb or ca)
        self.add(c, cc or cb or ca)
        self.f.append((i, i + 1, i + 2))

    def emit(self, b, mat='plant', loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        t = b._new()
        uv, col, _ = b._layers(t)
        bv = [t.verts.new(v) for v in self.v]
        for f in self.f:
            try:
                face = t.faces.new([bv[i] for i in f])
            except ValueError:
                continue
            for l, i in zip(face.loops, f):
                c = self.c[i]
                l[col] = (c[0], c[1], c[2], 1.0)
                l[uv].uv = (self.v[i][0] + self.v[i][1], self.v[i][2])
        t.normal_update()
        b._emit(t, mat, loc, rot, scale)


# ---------------------------------------------------------------- carrots ----
C_G0, C_G1 = srgb(40, 106, 38), srgb(132, 192, 68)      # feathery tops: deep base -> bright tips
C_STEM = srgb(126, 176, 78)
C_OR, C_OR_DEEP, C_OR_HI = srgb(238, 120, 30), srgb(190, 78, 20), srgb(248, 156, 56)
C_CROWN = srgb(150, 146, 58)


def frond(g, r, L, lean0, bend, nseg, npin, pin_len, fork, rw=0.0045, fin=True, t0=0.3, zmin=None, vee=0.3,
          sweep=(28, 48), c0=C_G0, c1=C_G1, c_stem=C_STEM, dark=1.0):
    """Feathery carrot leaf added to Raw `g`, in the frond frame: base at the origin, grows up +Z and arches
    toward +X. lean0 = start angle from vertical, bend = extra arch (degrees). A thin tapering rachis with
    opposite pairs of slim pinnae; fork=True gives every pinna a forward prong (reads as lace)."""
    P = [Vector((0, 0, 0))]
    A = []
    for i in range(nseg):
        a = rad(lean0 + bend * (i + 0.5) / nseg)
        A.append(a)
        P.append(P[-1] + Vector((math.sin(a), 0, math.cos(a))) * (L / nseg))

    def clamp(p):
        if zmin is not None and p.z < zmin:
            p = Vector((p.x, p.y, zmin))
        return p

    def centre(t):
        f = min(max(t, 0.0), 0.9999) * nseg
        i = int(f)
        a = A[i]
        return P[i].lerp(P[i + 1], f - i), Vector((math.sin(a), 0, math.cos(a))), Vector((-math.cos(a), 0, math.sin(a)))

    k = dark * r.uniform(0.9, 1.08)
    cs, c0, c1 = mul(c_stem, k), mul(c0, k), mul(c1, k)
    # rachis: flat strip tapering to a point
    row = []
    for i in range(nseg):
        w = rw * (1 - 0.6 * i / nseg)
        col = mix(cs, c1, 0.7 * i / nseg)
        row.append((g.add(clamp(P[i] - Y * w), col), g.add(clamp(P[i] + Y * w), col)))
    tip = g.add(clamp(P[nseg]), c1)
    for i in range(nseg - 1):
        g.f.append((row[i][0], row[i][1], row[i + 1][1], row[i + 1][0]))
    g.f.append((row[-1][0], row[-1][1], tip))
    if fin:  # perpendicular fin so the leaf stalk does not vanish edge-on
        n0 = Vector((-math.cos(A[0]), 0, math.sin(A[0])))
        g.tri(clamp(P[0] - n0 * rw), clamp(P[0] + n0 * rw), clamp(P[0].lerp(P[1], min(1.0, t0 * nseg))), cs)
    pairs = (npin + 1) // 2
    for kpin in range(npin):
        s = (kpin // 2 + 0.5) / pairs
        side = 1 if kpin % 2 == 0 else -1
        t = t0 + (0.96 - t0) * s + r.uniform(-0.02, 0.02)
        p, T, N = centre(t)
        ln = pin_len * tab([(0, 0.72), (0.25, 1.0), (1.0, 0.34)], s) * r.uniform(0.85, 1.15)
        sw = rad(r.uniform(*sweep))
        d = (Y * side * math.cos(sw) + T * math.sin(sw) + N * vee * r.uniform(0.2, 1.7)).normalized()
        bw = max(ln * 0.16, 0.0032)
        cb = mix(c0, c1, 0.15 + 0.45 * s)
        ct = mix(c0, c1, 0.7 + 0.3 * s)
        g.tri(clamp(p - T * bw), clamp(p + T * bw), clamp(p + d * ln), cb, cb, ct)
        if fork:
            e = (T * 0.85 + d * 0.25 + N * r.uniform(-0.25, 0.5)).normalized()
            g.tri(clamp(p + d * ln * 0.18), clamp(p + d * ln * 0.56), clamp(p + d * ln * 0.42 + e * ln * 0.62), mix(cb, ct, 0.4), mix(cb, ct, 0.5), ct)


def carrot_shoulder(b, loc, r0, h, segs, rings, tilt, k=1.0):
    """Top of a carrot root poking out of the soil (open underneath)."""
    def cf(co):
        c = mix(C_OR_DEEP, C_OR, smooth(-0.012, 0.45 * h, co.z))
        c = mix(c, C_OR_HI, smooth(0.5 * h, 0.9 * h, co.z) * 0.45)
        c = mix(c, C_CROWN, smooth(0.6 * r0, 0.1 * r0, math.hypot(co.x, co.y)) * smooth(0.7 * h, h, co.z) * 0.8)
        return mul(c, k)
    if rings == 2:
        prof = [(r0 * 0.96, -0.012), (r0 * 0.8, 0.72 * h), (0, h)]
    else:
        prof = [(r0 * 0.93, -0.012), (r0, 0.42 * h), (r0 * 0.62, 0.9 * h), (0, h)]
    b.lathe(prof, loc=loc, rot=(tilt[0], tilt[1], 0), mat='plant_glossy', segs=segs, color=cf)


_pr = random.Random(7)
CARROT_POS = [((i - 1) * 0.27 + _pr.uniform(-0.035, 0.035), (j - 1) * 0.27 + _pr.uniform(-0.035, 0.035), _pr.uniform(0, 2 * pi),
               _pr.uniform(0.88, 1.1)) for i in range(3) for j in range(3)]


def carrot(stage):
    b = Builder(f'carrot_{stage}', seed=500 + stage)
    r = b.rng
    for (x, y, yaw0, sc) in CARROT_POS:
        if stage == 0:
            g = Raw()
            for sg in (0, 1):  # two strap-like seed leaves
                a = yaw0 + sg * pi + r.uniform(-0.3, 0.3)
                d = Vector((math.cos(a), math.sin(a), 0))
                sd = Vector((-d.y, d.x, 0))
                ln = r.uniform(0.06, 0.08)
                g.tri(Vector((0, 0, 0)), d * ln * 0.5 + sd * 0.008 + Z * ln * 0.55, d * ln + Z * ln * 0.8,
                      srgb(120, 176, 74), srgb(104, 176, 62), srgb(150, 206, 84))
            g.emit(b, loc=(x, y, 0))
            g = Raw()
            frond(g, r, 0.115 * sc, 6, 30, 1, 2, 0.04, False, rw=0.006, fin=False, t0=0.5, c0=srgb(70, 148, 50), c1=srgb(150, 208, 84))
            g.emit(b, loc=(x, y, 0), rot=(0, 0, math.degrees(yaw0) + 90))
            continue
        nf = (0, 5, 6, 7)[stage]
        Lr = ((0, 0), (0.15, 0.22), (0.27, 0.36), (0.36, 0.45))[stage]
        z0 = 0.0
        if stage == 2:
            carrot_shoulder(b, (x, y, 0), 0.027 * sc, 0.024, 5, 2, (r.uniform(-8, 8), r.uniform(-8, 8)), r.uniform(0.92, 1.06))
            z0 = 0.018
        elif stage == 3:
            carrot_shoulder(b, (x, y, 0), 0.042 * sc, 0.06 * sc, 6, 3, (r.uniform(-9, 9), r.uniform(-9, 9)), r.uniform(0.92, 1.06))
            z0 = 0.05 * sc
        for k in range(nf):
            yaw = yaw0 + k * 2.39996 + r.uniform(-0.25, 0.25)
            inner = k < 2
            L = (Lr[1] if inner else r.uniform(*Lr)) * sc * r.uniform(0.92, 1.0)
            lean = r.uniform(4, 12) if inner else r.uniform(14, 32)
            bend = r.uniform(22, 40) if inner else r.uniform(48, 82)
            g = Raw()
            if stage == 1:
                frond(g, r, L, lean, bend * 0.8, 2, 6, 0.062, False, rw=0.004, fin=False, t0=0.28, c0=srgb(58, 128, 44), c1=srgb(144, 202, 76))
            elif stage == 2:
                frond(g, r, L, lean, bend, 3, 7, 0.086, True, fin=False, t0=0.32, dark=0.92 if not inner else 1.0)
            else:
                frond(g, r, L, lean, bend, 3, 9, 0.098, True, rw=0.005, fin=False, t0=0.33, dark=0.88 if not inner else 1.0)
            off = 0.008 if stage < 3 else 0.012
            g.emit(b, loc=(x + math.cos(yaw) * off, y + math.sin(yaw) * off, z0), rot=(0, 0, math.degrees(yaw)))
    return b.build(sharp_angle=SHARP)


# ---------------------------------------------------------------- cabbage ----
K_EDGE, K_MID, K_RIB = srgb(38, 96, 56), srgb(68, 130, 80), srgb(130, 178, 116)      # dark blue-green outer leaves
K_VEIN = srgb(176, 208, 146)
K_Y_EDGE, K_Y_MID, K_Y_RIB = srgb(56, 120, 82), srgb(92, 152, 100), srgb(148, 194, 132)  # young leaves
K_HEAD_LO, K_HEAD_HI, K_HEAD_RIM = srgb(140, 188, 98), srgb(208, 230, 150), srgb(112, 170, 92)
K_HEAD_VEIN = srgb(226, 238, 180)
CAB = [(0, 0.2), (0.12, 0.5), (0.3, 0.88), (0.5, 1.0), (0.7, 0.93), (0.87, 0.68), (1.0, 0.3)]
WRAP = [(0, 0.4), (0.25, 0.85), (0.55, 1.0), (0.82, 0.82), (1.0, 0.36)]


def sheet(g, S, nu, vrows, colfn):
    """Grid of shared vertices over surface S(u in -1..1, v in 0..1)."""
    idx = []
    for v in vrows:
        idx.append([g.add(S(-1 + 2 * i / nu, v), colfn(-1 + 2 * i / nu, v)) for i in range(nu + 1)])
    for j in range(len(vrows) - 1):
        for i in range(nu):
            g.f.append((idx[j][i], idx[j][i + 1], idx[j + 1][i + 1], idx[j + 1][i]))


def vein(g, S, path, col, lift):
    """Thin raised strip along path [(u, v, du, dv)] (half-width offsets); the last point is the tip."""
    rows = [(g.add(S(u - du, v - dv, lift), col), g.add(S(u + du, v + dv, lift), col)) for (u, v, du, dv) in path[:-1]]
    tip = g.add(S(path[-1][0], path[-1][1], lift), col)
    for i in range(len(rows) - 1):
        g.f.append((rows[i][0], rows[i][1], rows[i + 1][1], rows[i + 1][0]))
    g.f.append((rows[-1][0], rows[-1][1], tip))


def cab_leaf(b, r, loc, yaw, L, W, ang, cup, ruff, nu, vrows, cols, laterals=(), midrib=True, vein_c=K_VEIN, zmin=None,
             shape=CAB, lift=0.004, jit=0.07, lat_segs=1):
    """Broad cabbage leaf. Base at loc, grows outward along the yaw direction; `ang` = [(v, elevation deg)]
    is the midline's angle above horizontal along its length (cradle: rises then flares). cup lifts the
    edges toward the plant axis, ruff waves the rim. cols = (rib, mid, edge). Veins are thin raised strips."""
    FN = 20
    cs = [Vector((0, 0, 0))]
    for i in range(FN):
        a = rad(tab(ang, (i + 0.5) / FN))
        cs.append(cs[-1] + Vector((math.cos(a), 0, math.sin(a))) * (L / FN))
    ph = r.uniform(0, 6.28)
    k = 1.0 + r.uniform(-jit, jit)
    c_rib, c_mid, c_edge = (mul(c, k) for c in cols)

    def S(u, v, lf=0.0):
        f = min(max(v, 0.0), 0.9999) * FN
        i = int(f)
        c = cs[i].lerp(cs[i + 1], f - i)
        a = rad(tab(ang, v))
        n = Vector((-math.sin(a), 0, math.cos(a)))
        w = W / 2 * tab(shape, v)
        off = cup * w * u * u + ruff * W * math.sin(2 * pi * 2.5 * v + ph + (0 if u > 0 else 2.1)) * abs(u) ** 2 * smooth(0.15, 0.5, v)
        p = c + Vector((0, u * w, 0)) + n * (off + lf)
        if zmin is not None:
            p.z = max(p.z, zmin - loc[2] + lf)
        return p

    def colfn(u, v):
        e = max(abs(u), smooth(0.8, 1.0, v) * 0.9)
        c = mix(c_rib, c_mid, min(1.0, abs(u) * 2.2))
        c = mix(c, c_edge, smooth(0.45, 1.0, e))
        return mix(c, c_rib, smooth(0.3, 0.0, v) * 0.6)

    g = Raw()
    sheet(g, S, nu, vrows, colfn)
    vc = mul(vein_c, k)
    if midrib:
        hw = 0.011 / (W / 2)
        path = [(0, v, hw * (1 - 0.75 * v) / max(tab(shape, v), 0.2), 0) for v in vrows[:-1]] + [(0, vrows[-1] * 0.96, 0, 0)]
        vein(g, S, path, vc, lift)
    for v0 in laterals:
        for sg in (-1, 1):
            if lat_segs == 1:
                path = [(0, v0, 0, 0.022), (sg * 0.84, v0 + 0.2, 0, 0)]
            else:
                path = [(0, v0, 0, 0.022), (sg * 0.45, v0 + 0.12, 0, 0.013), (sg * 0.86, v0 + 0.2, 0, 0)]
            vein(g, S, path, vc, lift)
    g.emit(b, loc=loc, rot=(0, 0, math.degrees(yaw)))


def wrap_patch(b, r, C, R, Rz, az, th0, th1, psi, k, nu, vrows, laterals=(), lip=0.04, lift=0.003, tone=1.0):
    """Head wrapper leaf: a patch hugging the ellipsoid (centre C, radii R/Rz) along the meridian at azimuth
    az, from polar angle th0 (near the stalk) to th1 (<0 = folded over the crown); psi = half-width angle.
    The rim lifts slightly so overlapping wrappers read as separate leaves."""
    C = Vector(C)
    e_r = Vector((math.cos(az), math.sin(az), 0))
    e_t = Vector((-math.sin(az), math.cos(az), 0))
    kk0 = tone * (1.0 + r.uniform(-0.05, 0.05))

    def S(u, v, lf=0.0):
        th = th0 + (th1 - th0) * v
        ps = u * psi * tab(WRAP, v)
        rim = max(abs(u) ** 2, smooth(0.75, 1.0, v))
        kk = k + lip * rim * smooth(0.15, 0.6, v) + lf / R
        return C + (math.cos(ps) * (e_r * (math.sin(th) * R) + Z * (math.cos(th) * Rz)) + e_t * (math.sin(ps) * R)) * kk

    def colfn(u, v):
        th = th0 + (th1 - th0) * v
        c = mix(K_HEAD_LO, K_HEAD_HI, smooth(-0.5, 0.9, math.cos(th) * math.cos(u * psi * 0.8)))
        rim = max(abs(u) ** 1.5, smooth(0.7, 1.0, v))
        c = mix(c, K_HEAD_RIM, rim * 0.6)
        c = mix(c, K_HEAD_VEIN, (1 - min(1.0, abs(u) * 2.5)) * 0.35)
        return mul(c, kk0)

    g = Raw()
    sheet(g, S, nu, vrows, colfn)
    hw = 0.008 / (R * psi)
    vcol = mul(mix(K_HEAD_VEIN, K_HEAD_HI, 0.35), kk0)
    path = [(0, v, hw * (1 - 0.7 * v) / tab(WRAP, v), 0) for v in vrows[:-1]] + [(0, vrows[-1] * 0.95, 0, 0)]
    vein(g, S, path, vcol, lift)
    for v0 in laterals:
        for sg in (-1, 1):
            vein(g, S, [(sg * 0.8 * q, v0 + 0.16 * q, 0, 0.013 * (1 - 0.8 * q)) for q in (0, 0.25, 0.5, 0.75, 1.0)], vcol, lift)
    g.emit(b)


def head_core(b, C, R, Rz, segs, thetas):
    def cf(co):
        return mix(K_HEAD_LO, K_HEAD_HI, smooth(C[2] - 0.3 * Rz, C[2] + Rz, co.z))
    b.lathe([(R * math.sin(t), C[2] + Rz * math.cos(t)) for t in thetas], loc=(C[0], C[1], 0), mat='plant', segs=segs, color=cf)


_kr = random.Random(11)
CAB_POS = [((i - 0.5) * 0.55 + _kr.uniform(-0.03, 0.03), (j - 0.5) * 0.55 + _kr.uniform(-0.03, 0.03), _kr.uniform(0, 2 * pi),
            _kr.uniform(0.9, 1.06)) for i in range(2) for j in range(2)]
YOUNG = (K_Y_RIB, K_Y_MID, K_Y_EDGE)
OUTER = (K_RIB, K_MID, K_EDGE)


def cabbage(stage):
    b = Builder(f'cabbage_{stage}', seed=600 + stage)
    r = b.rng
    for (x, y, yaw0, sc) in CAB_POS:
        if stage == 0:
            g = Raw()
            for k in range(4):
                true_leaf = k >= 2
                a = yaw0 + k * pi + (pi / 2 if true_leaf else 0) + r.uniform(-0.25, 0.25)
                d = Vector((math.cos(a), math.sin(a), 0))
                sd = Vector((-d.y, d.x, 0))
                ln, w, up = (0.075, 0.03, 0.9) if true_leaf else (0.065, 0.024, 0.45)
                c0, c1 = (K_Y_RIB, K_Y_MID) if true_leaf else (srgb(130, 184, 96), srgb(104, 172, 84))
                p0 = Vector((0, 0, 0))
                pl = d * ln * 0.55 + sd * w + Z * ln * 0.6 * up
                pr = d * ln * 0.55 - sd * w + Z * ln * 0.6 * up
                tl = d * ln + sd * w * 0.55 + Z * ln * up
                tr = d * ln - sd * w * 0.55 + Z * ln * up
                i0 = g.add(p0, c0)
                il, itl, itr, ir = g.add(pl, c1), g.add(tl, c1), g.add(tr, c1), g.add(pr, c1)
                g.f += [(i0, il, itl), (i0, itl, itr), (i0, itr, ir)]
            g.emit(b, loc=(x, y, 0))
            continue
        with b.at((x, y, 0), (0, 0, math.degrees(yaw0)), sc):
            if stage == 1:
                for k in range(6):
                    yaw = k * 2.39996
                    inner = k >= 4
                    L = r.uniform(0.11, 0.13) if inner else r.uniform(0.16, 0.2)
                    e0 = r.uniform(60, 70) if inner else r.uniform(34, 50)
                    cab_leaf(b, r, (math.cos(yaw) * 0.008, math.sin(yaw) * 0.008, 0.0), yaw, L, L * 0.78,
                             [(0, e0 + 12), (0.5, e0), (1, e0 - 34)], 0.22, 0.03, 2, [0, 0.34, 0.74, 1.0], YOUNG, vein_c=srgb(186, 220, 172))
            elif stage == 2:
                for k in range(5):  # outer leaves opening flat
                    yaw = k * 2 * pi / 5 + r.uniform(-0.2, 0.2)
                    L = r.uniform(0.23, 0.28)
                    cab_leaf(b, r, (math.cos(yaw) * 0.012, math.sin(yaw) * 0.012, 0.005), yaw, L, L * 0.86,
                             [(0, 30), (0.3, 36), (0.7, 22), (1, -8)], 0.2, 0.04, 4, [0, 0.3, 0.58, 0.84, 1.0],
                             (mix(K_RIB, K_Y_RIB, 0.5), mix(K_MID, K_Y_MID, 0.5), mix(K_EDGE, K_Y_EDGE, 0.5)), laterals=(0.3,))
                for k in range(4):  # inner leaves starting to cup
                    yaw = k * 2 * pi / 4 + 0.6 + r.uniform(-0.2, 0.2)
                    L = r.uniform(0.15, 0.17)
                    cab_leaf(b, r, (math.cos(yaw) * 0.01, math.sin(yaw) * 0.01, 0.01), yaw, L, L * 0.95,
                             [(0, 28), (0.4, 62), (1, 100)], 0.34, 0.02, 2, [0, 0.34, 0.74, 1.0],
                             (srgb(170, 208, 140), srgb(120, 176, 110), srgb(84, 148, 96)), vein_c=K_HEAD_VEIN)
                head_core(b, (0, 0, 0.075), 0.05, 0.05, 6, [2.2, 1.0, 0.0])
            else:
                R, Rz = 0.13, 0.118
                C = (0, 0, 0.022 + Rz * 0.93)
                head_core(b, C, R, Rz, 8, [2.55, 1.9, 1.2, 0.55, 0.0])
                vr = [0, 0.28, 0.56, 0.82, 1.0]
                for k, (th1, kk) in enumerate(((-0.55, 1.07), (0.12, 1.045), (0.3, 1.02))):
                    wrap_patch(b, r, C, R, Rz, k * 2 * pi / 3 + 0.4, 2.5, th1, 1.2, kk, 4, vr, tone=(1.0, 0.94, 0.9)[k])
                for k in range(6):
                    yaw = k * 2 * pi / 6 + r.uniform(-0.18, 0.18)
                    low = k % 2 == 1
                    L = r.uniform(0.27, 0.29) if low else r.uniform(0.3, 0.32)
                    ang = [(0, 0), (0.3, 30), (0.7, 26), (1, -14)] if low else [(0, 6), (0.35, 62), (0.7, 60), (1, 8)]
                    cab_leaf(b, r, (math.cos(yaw) * 0.015, math.sin(yaw) * 0.015, 0.008 if low else 0.02), yaw, L, L * 0.9, ang,
                             0.16 if low else 0.26, 0.05, 4, vr, OUTER, laterals=(0.28, 0.52))
    return b.build(sharp_angle=SHARP)


# ------------------------------------------------------------------ goods ----
def recenter(o):
    """Move the mesh so the origin is at the bottom centre of its bounding box."""
    me = o.data
    lo = [min(v.co[i] for v in me.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in me.vertices) for i in range(3)]
    d = Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    for v in me.vertices:
        v.co += d
    me.update()
    return o


def carrot_root(b, tip, crown, r0, k=1.0):
    tip, crown = Vector(tip), Vector(crown)
    L = (crown - tip).length
    ctrl = [(0, 0), (0.12, 0.012), (0.2, 0.06), (0.42, 0.3), (0.7, 0.58), (0.92, 0.8), (1.0, 0.9), (0.9, 0.965), (0.55, 1.0), (0.2, 0.992), (0, 0.985)]
    prof = [(p[0] * r0, p[1] * L) for p in smooth_profile(ctrl, 2)]
    ph = b.rng.uniform(0, 6)

    def ring(z):  # shallow growth rings
        return math.sin(z / L * 38 + ph + 2.0 * math.sin(z / L * 9 + ph))

    def radial(a, z):
        return 1.0 + 0.035 * ring(z) * smooth(0.02, 0.2, z / L) * smooth(1.0, 0.9, z / L) + 0.03 * math.sin(a * 2 + ph + z * 30)

    def cf(co):
        z = co.z / L
        c = mix(C_OR_DEEP, C_OR, smooth(0.0, 0.35, z))
        c = mix(c, C_OR_HI, 0.3 * smooth(0.3, 0.9, z))
        c = mix(c, C_OR_DEEP, 0.4 * smooth(0.2, -0.9, ring(co.z)))
        c = mix(c, C_CROWN, smooth(0.55 * r0, 0.15 * r0, math.hypot(co.x, co.y)) * smooth(0.93, 0.99, z) * 0.85)
        return mul(c, k)

    b.lathe(prof, loc=tip, rot=aim(crown - tip), mat='plant_glossy', segs=10, color=cf, radial=radial)
    # a few hair roots
    for i in range(2):
        t = b.rng.uniform(0.08, 0.45)
        p = tip.lerp(crown, t)
        a = b.rng.uniform(0, 6.28)
        d = Vector((math.cos(a) * 0.4, math.sin(a), abs(math.sin(a * 1.7)) * 0.3)).normalized() * (r0 * tab([(0, 0.2), (1, 1.3)], t) + 0.012)
        b.tube([p, p + d], [0.0012, 0.0005], mat='plant', segs=3, caps=False, color=srgb(214, 150, 80))


def item_carrot():
    b = Builder('item_carrot', seed=71)
    r = b.rng
    tie = Vector((0.07, 0.0, 0.04))
    carrots = [((-0.205, -0.085, 0.011), (-0.008, -0.03, 0.027), 0.027), ((-0.215, 0.07, 0.011), (-0.01, 0.028, 0.026), 0.026),
               ((-0.185, -0.004, 0.05), (0.0, 0.0, 0.07), 0.0245)]
    for ci, (tip, crown, r0) in enumerate(carrots):
        carrot_root(b, tip, crown, r0, k=(1.0, 0.95, 1.05)[ci])
        crown = Vector(crown)
        ax = (crown - Vector(tip)).normalized()
        for k in range(5):
            a = k * 2 * pi / 5 + ci
            off = Vector((0, math.cos(a), math.sin(a))) * 0.008
            p0 = crown - ax * 0.004 + off * 0.9
            p2 = tie + Vector((0, math.cos(a + ci * 2.1), math.sin(a + ci * 2.1))) * 0.007 + Vector((0, (ci - 1) * 0.004 if ci < 2 else 0, 0.004 * (ci == 2)))
            p1 = p0.lerp(p2, 0.5) + ax * 0.006
            b.tube([p0, p1, p2], [0.0036, 0.003, 0.0028], mat='plant', segs=4, caps=False, color=srgb(150, 190, 96), color_top=C_STEM)
            # the leaf carries on past the twine and fans out
            yaw = (ci - 1) * (0.42 if ci < 2 else 0.0) + (k - 2) * 0.2 + r.uniform(-0.12, 0.12) + (0.08 if ci == 2 else 0)
            g = Raw()
            frond(g, r, r.uniform(0.15, 0.2), r.uniform(62, 80), r.uniform(18, 34), 4, 12, 0.055, True, rw=0.003, fin=True, t0=0.2,
                  zmin=0.003 - p2.z, vee=0.45, dark=r.uniform(0.86, 1.02))
            g.emit(b, loc=p2, rot=(r.uniform(-50, 50), 0, math.degrees(yaw)))
    # twine: two wraps round the stalks and a small bow on top
    for dx, tilt in ((-0.0035, 6), (0.0035, -5)):
        with b.at((tie.x + dx, tie.y, tie.z), (tilt, 90, 0)):
            torus(b, 0.0125, 0.0028, 0, n=5, mat='rope', segs=12)
    c = tie + Vector((0, -0.004, 0.0145))
    for sg in (-1, 1):
        s = Vector((0.25 * sg, -1 * sg, 0)).normalized() * sg * sg
        s = Vector((0.3, -1, 0)).normalized() * sg
        loop = [c, c + s * 0.016 + Z * 0.012, c + s * 0.026 + Z * 0.004, c + s * 0.016 - Z * 0.004, c]
        b.tube(loop, 0.0022, mat='rope', segs=4, caps=False)
        b.tube([c, c + s * 0.012 + X * 0.006 * sg - Z * 0.006, c + s * 0.03 + X * 0.012 * sg - Z * 0.02], 0.0021, mat='rope', segs=4, caps=True)
    b.blob(0.0048, loc=c, mat='rope', subdiv=1)
    return recenter(b.build(sharp_angle=SHARP))


def item_cabbage():
    b = Builder('item_cabbage', seed=72)
    r = b.rng
    R, Rz = 0.108, 0.1
    C = (0, 0, Rz * 0.94)
    thetas = [pi * (1 - i / 12) * 0.9 for i in range(13)]
    thetas[-1] = 0.0
    head_core(b, C, R, Rz, 20, thetas)
    vr = [0, 0.14, 0.28, 0.42, 0.56, 0.7, 0.82, 0.92, 1.0]
    wraps = ((0.3, -0.75, 1.15, 1.085, 1.0), (2.5, -0.1, 1.2, 1.065, 0.96), (4.5, 0.18, 1.2, 1.05, 0.93), (1.4, 0.4, 1.1, 1.03, 0.9),
             (3.5, 0.5, 1.15, 1.015, 0.88), (5.5, 0.55, 1.0, 1.0, 0.86))
    for az, th1, psi, kk, tone in wraps:
        wrap_patch(b, r, C, R, Rz, az, 2.6, th1, psi, kk, 8, vr, laterals=(0.24, 0.44), lip=0.028, lift=0.002, tone=tone)
    # cut stalk underneath + loose outer leaves
    b.cyl(0.022, 0.02, loc=(0, 0, 0.0), mat='plant', segs=10, bevel=0.003, color=srgb(206, 222, 170))
    vr2 = [0, 0.14, 0.3, 0.46, 0.62, 0.78, 0.9, 1.0]
    loose = ((0.9, 0.225, [(0, 4), (0.3, 44), (0.65, 66), (1, 24)], 0.3, 0.02), (3.3, 0.23, [(0, 0), (0.3, 16), (0.7, 14), (1, -6)], 0.14, 0.012),
             (5.0, 0.21, [(0, 2), (0.3, 36), (0.7, 50), (1, 8)], 0.26, 0.016))
    for yaw, L, ang, cup, zb in loose:
        cab_leaf(b, r, (math.cos(yaw) * 0.02, math.sin(yaw) * 0.02, zb), yaw, L, L * 0.92, ang, cup, 0.045, 8, vr2, OUTER,
                 laterals=(0.2, 0.36, 0.52, 0.68), zmin=0.002, lift=0.003, lat_segs=2)
    return recenter(b.build(sharp_angle=SHARP))


# ------------------------------------------------------------------ build ----
ASSETS = {}
for s in range(4):
    o = carrot(s)
    ASSETS[o.name] = o
for s in range(4):
    o = cabbage(s)
    ASSETS[o.name] = o
for fn in (item_carrot, item_cabbage):
    o = fn()
    ASSETS[o.name] = o

bpy.context.view_layer.update()
STAGE_BUDGET = (48, 452, 1194, 1756)   # tomato_0..3 in vegetation.glb
print('---- REPORT ----')
for name, o in ASSETS.items():
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    tris = kit.tri_count([o])
    lim = 3000 if name.startswith('item_') else STAGE_BUDGET[int(name[-1])]
    mats = sorted(m.name for m in o.data.materials)
    print(f'{name:14s} size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f}  x[{lo[0]:.2f},{hi[0]:.2f}] y[{lo[1]:.2f},{hi[1]:.2f}] '
          f'z[{lo[2]:.3f},{hi[2]:.3f}]  tris {tris:5d}/{lim}{"  OVER" if tris > lim else ""}  {mats}')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
kit.export_glb(OUT, list(ASSETS.values()))


# --------------------------------------------------------------- previews ----
def render(path, objs, az=35, el=22, size=(1000, 750), zoom=1.0, floor_col=(0.115, 0.075, 0.05)):
    """kit.render_preview with a soil-coloured floor (crops are judged against tilled earth)."""
    sc = bpy.context.scene
    objs = kit._descend(objs)
    pts = []
    for o in objs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    radius = (hi - lo).length / 2
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = 60
    d = radius / math.tan(rad(13)) / zoom
    a, e = rad(az), rad(el)
    cam.location = c + Vector((math.sin(a) * math.cos(e) * d, -math.cos(a) * math.cos(e) * d, math.sin(e) * d))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start = 0.02
    cam.data.clip_end = d * 4
    sc.camera = cam
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.86, 0.68)
    sun.data.angle = rad(4)
    sun.rotation_euler = Euler((rad(58), 0, a + rad(55)))
    fm = bpy.data.meshes.new('_pv_floor')
    fb = bmesh.new()
    bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=radius * 12)
    fb.to_mesh(fm)
    fb.free()
    floor = bpy.data.objects.new('_pv_floor', fm)
    floor.location = (c.x, c.y, min(lo.z, 0.0) - 0.001)
    sc.collection.objects.link(floor)
    fmat = bpy.data.materials.new('_pv_floor')
    fmat.use_nodes = True
    bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bs.inputs['Base Color'].default_value = (*floor_col, 1)
    bs.inputs['Roughness'].default_value = 0.95
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
    print(f'[crops2] preview {path}')


def load_refs():
    """Preview only (after export): pull the existing crops/goods in from their .glb for side-by-side shots."""
    refs = {}
    for f in ('vegetation.glb', 'items.glb'):
        p = os.path.join(ROOT, 'public', 'models', f)
        if not os.path.exists(p):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=p)
        for o in set(bpy.data.objects) - before:
            refs[o.name] = o
            if o.type == 'MESH':
                for i, m in enumerate(o.data.materials):
                    base = m.name.split('.')[0]
                    if base in kit.PREVIEW:
                        o.data.materials[i] = kit.get_mat(base)
    return refs


def shoot(name, objs, spacing=0.0, az=28, el=30, zoom=1.0, size=(1200, 760)):
    if ONLY is not None and name not in ONLY:
        return
    for o in bpy.data.objects:
        o.hide_render = True
    for i, o in enumerate(objs):
        for c in kit._descend([o]):
            c.hide_render = False
        o.location.x = (i - (len(objs) - 1) / 2) * spacing
    bpy.context.view_layer.update()
    render(os.path.join(PREV, name + '.png'), objs, az=az, el=el, size=size, zoom=zoom)
    for o in objs:
        o.location.x = 0


if PREV:
    os.makedirs(PREV, exist_ok=True)
    A = ASSETS
    shoot('carrot', [A[f'carrot_{i}'] for i in range(4)], 1.25, zoom=1.25, size=(1600, 600))
    shoot('cabbage', [A[f'cabbage_{i}'] for i in range(4)], 1.25, zoom=1.25, size=(1600, 600))
    shoot('carrot_close', [A['carrot_2'], A['carrot_3']], 1.25, az=20, el=24, zoom=1.2, size=(1600, 760))
    shoot('cabbage_close', [A['cabbage_2'], A['cabbage_3']], 1.25, az=20, el=28, zoom=1.2, size=(1600, 760))
    shoot('top', [A['carrot_3'], A['cabbage_3']], 1.25, az=30, el=58, zoom=1.2, size=(1600, 860))
    shoot('goods_top', [A['item_carrot'], A['item_cabbage']], 0.45, az=20, el=55, zoom=1.15, size=(1400, 800))
    if ONLY is None or ONLY & {'compare', 'goods'}:
        REF = load_refs()
        if all(n in REF for n in ('wheat_3', 'tomato_3', 'pumpkin_3')):
            shoot('compare', [REF['wheat_3'], A['carrot_3'], REF['tomato_3'], A['cabbage_3'], REF['pumpkin_3']], 1.3, az=15, el=22,
                  zoom=1.3, size=(1800, 700))
        if all(n in REF for n in ('item_tomato', 'item_pumpkin')):
            shoot('goods', [REF['item_tomato'], A['item_carrot'], A['item_cabbage'], REF['item_pumpkin']], 0.42, az=20, el=28, zoom=1.25,
                  size=(1700, 700))
