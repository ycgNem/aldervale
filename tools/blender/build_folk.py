"""Folk of Aldervale: Wren the travelling peddler + the royal supply pony -> public/models/folk.glb

blender --background --factory-startup --python tools/blender/build_folk.py -- [preview_dir] [all|peddler|face|pony|wagon] [--no-export]

Both face Blender -Y, +X is their LEFT, origin on the ground (feet / centre under the body).
Every surface is a loft between two profile curves (see Loft) with sculpted displacement, the same
technique the courier's head uses (tools/blender/build_courier.py).

Objects (identity rotation at rest, each mesh is built around its own pivot):
  peddler                     torso, bodice, skirts, apron, satchel, boots
    peddler_head              head + neck + hair + braid + headscarf     (pivot: neck base)
      peddler_eye             marker between the eyes
    peddler_arm_l / _r        upper arm (blouse sleeve)                  (pivot: shoulder)
      peddler_forearm_l / _r  rolled cuff + bare forearm + hand          (pivot: elbow)
  pony                        barrel, collar, harness, traces, swingletree
    pony_head                 neck + head + mane + forelock + bridle     (pivot: base of the neck)
    pony_leg_fl/fr/bl/br      whole leg, hoof and feather                (pivot: shoulder / hip)
    pony_tail                 dock + tail hair                           (pivot: tail root)
    pony_hitch                marker behind the pony where the wagon pole meets the swingletree
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import bmesh
from mathutils import Vector, Euler, Matrix, kdtree, noise
import kit
from kit import Builder, srgb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
_pos = [a for a in ARGV if not a.startswith('--')]
PREV = os.path.abspath(_pos[0]) if _pos else None
WHAT = _pos[1] if len(_pos) > 1 else 'all'
if PREV:
    os.makedirs(PREV, exist_ok=True)

kit.reset()
kit.PREVIEW.update({'gold': (0.86, 0.62, 0.22)})
kit.ROUGH.update({'gold': 0.32})
_g = kit.get_mat('gold')
next(n for n in _g.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs['Metallic'].default_value = 1.0

WHITE = (1.0, 1.0, 1.0)
LEA = (1.0, 0.95, 0.9)          # 'leather' already carries the brown; vertex colour only tints
BLUE = srgb(38, 62, 128)
BLUE_D = srgb(26, 44, 96)
GOLD = srgb(214, 168, 64)
GOLD_D = srgb(170, 126, 44)


# ================================================================ helpers (from build_courier.py)
def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def lerp3(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def sstep(v):
    v = clamp(v)
    return v * v * (3 - 2 * v)


def g(d, s):
    return math.exp(-(d / s) ** 2)


def sp(c, e):
    return math.copysign(abs(c) ** e, c)


def aim(n):
    """Euler (deg) that turns local -Y to the direction n."""
    n = Vector(n).normalized()
    return (-math.degrees(math.asin(clamp(n.z, -1, 1))), 0.0, math.degrees(math.atan2(n.x, -n.y)))


class Spline:
    """Cubic Hermite through rows of numbers at non-uniform knots (finite-difference tangents)."""

    def __init__(self, knots, rows):
        self.k, self.r = list(knots), [list(r) for r in rows]
        n = len(self.k)
        self.m = []
        for i in range(n):
            a, b = max(i - 1, 0), min(i + 1, n - 1)
            dk = self.k[b] - self.k[a]
            self.m.append([(self.r[b][c] - self.r[a][c]) / dk for c in range(len(self.r[0]))])

    def __call__(self, t):
        k = self.k
        t = clamp(t, k[0], k[-1])
        i = 0
        while i < len(k) - 2 and t > k[i + 1]:
            i += 1
        h = k[i + 1] - k[i]
        s = (t - k[i]) / h
        h00, h10 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s
        h01, h11 = -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
        return [h00 * self.r[i][c] + h10 * h * self.m[i][c] + h01 * self.r[i + 1][c] + h11 * h * self.m[i + 1][c]
                for c in range(len(self.r[0]))]


class B(Builder):
    """Builder with an optional per-primitive deform hook (primitive-local coords)."""
    deform = None

    def _emit(self, tbm, mat, loc, rot, scale=(1, 1, 1), smooth=True):
        if self.deform is not None:
            for v in tbm.verts:
                v.co = self.deform(v.co.copy())
        super()._emit(tbm, mat, loc, rot, scale, smooth)


def smooth_profile(ctrl, sub=4):
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


def smooth_path(ctrl, sub=4):
    """Catmull-Rom through 3D points."""
    P = [Vector(p) for p in ctrl]
    out = []
    n = len(P)
    for i in range(n - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, n - 1)]
        for s in range(sub):
            t = s / sub
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1].copy())
    return out


def torus(b, R, m, z=0.0, n=10, **kw):
    prof = [(R + m * math.cos(math.radians(-90 + 360 * k / n)), z + m * math.sin(math.radians(-90 + 360 * k / n))) for k in range(n + 1)]
    b.lathe(prof, **kw)


def ribbon(b, pts, nrm, width, thick, mat, color, segs=10, color_top=None):
    """Flat strap: an elliptical section swept along pts, flat side facing nrm."""
    t = b._new()
    uv, col, _ = b._layers(t)
    n = len(pts)
    rings = []
    for i in range(n):
        P = Vector(pts[i])
        N = Vector(nrm[i] if isinstance(nrm, list) else nrm).normalized()
        T = (Vector(pts[min(i + 1, n - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        Bn = T.cross(N)
        Bn = Bn.normalized() if Bn.length > 1e-6 else Vector((1, 0, 0))
        N2 = Bn.cross(T).normalized()
        w = width if not callable(width) else width(i / (n - 1))
        th = thick if not callable(thick) else thick(i / (n - 1))
        rings.append([t.verts.new(P + Bn * math.cos(2 * math.pi * k / segs) * w / 2 + N2 * math.sin(2 * math.pi * k / segs) * th / 2) for k in range(segs)])
    for i in range(n - 1):
        for k in range(segs):
            j = (k + 1) % segs
            f = t.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
            ca = color if color_top is None else lerp3(color, color_top, i / (n - 1))
            cb = color if color_top is None else lerp3(color, color_top, (i + 1) / (n - 1))
            for l, c in zip(f.loops, (ca, ca, cb, cb)):
                l[col] = (*c, 1)
    for ring, c in ((rings[0], color), (list(reversed(rings[-1])), color_top or color)):
        f = t.faces.new(ring)
        for l in f.loops:
            l[col] = (*c, 1)
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    t.normal_update()
    b._box_uv(t, None, 1.0)
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def emit_grid(b, rows, mat, color, wrap=False, outward='closed', facecol=None, skip=None, pole_start=None, pole_end=None):
    """rows[j][i] of Vectors -> quad grid. wrap closes i. pole_*: point that fan-closes the first/last
    row. outward: 'closed' (recalc), a Vector centre the normals must point away from, or fn(p)->dir.
    color: tuple, fn(co) or a rows-shaped list of colours. facecol(i, j) -> colour or None."""
    t = b._new()
    uv, col, _ = b._layers(t)
    V = [[t.verts.new(p) for p in row] for row in rows]
    nj, ni = len(V), len(V[0])
    vc = None
    if isinstance(color, list):
        vc = {V[j][i]: color[j][i] for j in range(nj) for i in range(ni)}
    fc = {}
    for j in range(nj - 1):
        for i in range(ni if wrap else ni - 1):
            i2 = (i + 1) % ni
            if skip and skip(i, j):
                continue
            quad = (V[j][i], V[j][i2], V[j + 1][i2], V[j + 1][i])
            if len({v.co.copy().freeze() for v in quad}) < 4:
                continue
            f = t.faces.new(quad)
            if facecol:
                c = facecol(i, j)
                if c is not None:
                    fc[f] = c
    for pole, row, cr in ((pole_start, V[0], 0), (pole_end, V[-1], -1)):
        if pole is None:
            continue
        pv = t.verts.new(pole)
        if vc is not None:
            vc[pv] = color[cr][0]
        for i in range(ni if wrap else ni - 1):
            t.faces.new((pv, row[i], row[(i + 1) % ni]))
    t.normal_update()
    if outward == 'closed':
        bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    else:
        s = 0.0
        for f in t.faces:
            c = f.calc_center_median()
            d = outward(c) if callable(outward) else (c - Vector(outward))
            s += f.normal.dot(d) * f.calc_area()
        if s < 0:
            bmesh.ops.reverse_faces(t, faces=t.faces[:])
    t.normal_update()
    b._box_uv(t, None, 1.0)
    for f in t.faces:
        for l in f.loops:
            c = fc.get(f)
            if c is None:
                if vc is not None:
                    c = vc[l.vert]
                else:
                    c = color(l.vert.co) if callable(color) else color
            l[col] = (c[0], c[1], c[2], 1.0)
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


class Loft:
    """Surface lofted through tilted rings. rows: (ay, az, by, bz, half_width[, pa, pb]) - each ring spans
    from point a (th = 0) to point b (th = pi) in the YZ plane and +-half_width in X, as a superellipse
    (pa / pb = exponent of the a / b half). Rings are spline-interpolated; sub = extra rings per span.
    A first / last row with half_width 0 becomes a pole. sculpt(p, th, t) -> p displaces the surface."""

    def __init__(self, rows, sub=2, n=32, sculpt=None, front_bias=False):
        self.rows = [tuple(r) + (2.0, 2.0) if len(r) == 5 else tuple(r) for r in rows]
        k = [0.0]
        for i in range(1, len(self.rows)):
            a, c = self.rows[i - 1], self.rows[i]
            k.append(k[-1] + max(0.5 * (math.hypot(c[0] - a[0], c[1] - a[1]) + math.hypot(c[2] - a[2], c[3] - a[3])), 1e-4))
        self.K = k
        self.sp = Spline(k, self.rows)
        subs = sub if isinstance(sub, (list, tuple)) else [sub] * (len(self.rows) - 1)
        self.TS = []
        for i in range(len(self.rows) - 1):
            for s in range(subs[i]):
                self.TS.append(k[i] + (k[i + 1] - k[i]) * s / subs[i])
        self.TS.append(k[-1])
        self.TH = []
        for i in range(n):
            s = 2 * i / n - 1
            self.TH.append(math.pi * (math.copysign(0.42 * abs(s) + 0.58 * abs(s) ** 2.6, s) if front_bias else s))
        self.sculpt = sculpt
        self._kd = {}

    def tk(self, f):
        i = min(int(f), len(self.K) - 2)
        return self.K[i] + (self.K[i + 1] - self.K[i]) * (f - i)

    def base(self, th, t):
        yf, zf, yb, zb, w, pf, pb = self.sp(t)
        c, s = math.cos(th), math.sin(th)
        cy, cz = (yf + yb) / 2, (zf + zb) / 2
        a = math.hypot(yb - yf, zb - zf) / 2
        ey, ez = ((yb - yf) / (2 * a), (zb - zf) / (2 * a)) if a > 1e-6 else (1.0, 0.0)
        p = pf if c > 0 else pb
        x = max(w, 0.0) * sp(s, 2 / p)
        al = -a * sp(c, 2 / p)
        return Vector((x, cy + al * ey, cz + al * ez))

    def ctr(self, t):
        yf, zf, yb, zb = self.sp(t)[:4]
        return Vector((0, (yf + yb) / 2, (zf + zb) / 2))

    def pt(self, th, t):
        p = self.base(th, t)
        return self.sculpt(p, th, t) if self.sculpt else p

    def nrm(self, th, t):
        e = 1e-3
        a = self.pt(th + e, t) - self.pt(th - e, t)
        b_ = self.pt(th, min(t + e, self.K[-1])) - self.pt(th, max(t - e, 0))
        n = a.cross(b_)
        if n.length < 1e-12:
            return Vector((0, 0, 1))
        n.normalize()
        if n.dot(self.pt(th, t) - self.ctr(t)) < 0:
            n = -n
        return n

    def on(self, th_deg, f, off=0.0):
        """Point on the surface at angle th_deg / row position f (fractional row index), lifted by off."""
        th, t = math.radians(th_deg), self.tk(f)
        p = self.pt(th, t)
        return p + self.nrm(th, t) * off if off else p

    def emit(self, b, mat, color=WHITE, col_tt=None):
        ts = list(self.TS)
        ps = pe = None
        if self.rows[0][4] < 1e-6:
            ps = self.pt(0, ts[0])
            ts = ts[1:]
        if self.rows[-1][4] < 1e-6:
            pe = self.pt(0, ts[-1])
            ts = ts[:-1]
        grid = [[self.pt(th, t) for th in self.TH] for t in ts]
        if ps is None:
            ps = sum(grid[0], Vector()) / len(grid[0])
        if pe is None:
            pe = sum(grid[-1], Vector()) / len(grid[-1])
        cols = [[col_tt(grid[j][i], self.TH[i], ts[j]) for i in range(len(self.TH))] for j in range(len(ts))] if col_tt else color
        emit_grid(b, grid, mat, cols, wrap=True, outward='closed', pole_start=ps, pole_end=pe)

    def _tree(self, key, keep, proj):
        if key not in self._kd:
            pts = [self.pt(th, t) for t in self.TS for th in self.TH if keep(th)]
            kd = kdtree.KDTree(len(pts))
            for i, p in enumerate(pts):
                kd.insert(proj(p), i)
            kd.balance()
            self._kd[key] = (kd, pts)
        return self._kd[key]

    def front_y(self, x, z):
        """y of the a-side surface at (x, z)."""
        kd, pts = self._tree('y', lambda th: math.cos(th) > 0.2, lambda p: Vector((p.x, 0, p.z)))
        sw = sy = 0.0
        for co, i, d in kd.find_n(Vector((x, 0, z)), 4):
            w = 1.0 / (d * d + 1e-8)
            sw += w
            sy += w * pts[i].y
        return sy / sw

    def side_x(self, y, z):
        """x of the +X side surface at (y, z)."""
        kd, pts = self._tree('x', lambda th: 0.1 < th < math.pi - 0.1, lambda p: Vector((0, p.y, p.z)))
        sw = sx = 0.0
        for co, i, d in kd.find_n(Vector((0, y, z)), 4):
            w = 1.0 / (d * d + 1e-8)
            sw += w
            sx += w * pts[i].x
        return sx / sw


def loft_band(b, loft, f, th0, th1, n, off, width, thick, mat, color, f1=None):
    """Strap lying on a loft from (th0, f) to (th1, f1 or f) (degrees / fractional row index)."""
    pts, nr = [], []
    for i in range(n + 1):
        u = i / n
        th = math.radians(th0 + (th1 - th0) * u)
        t = loft.tk(f + ((f1 if f1 is not None else f) - f) * u)
        nn = loft.nrm(th, t)
        pts.append(loft.pt(th, t) + nn * off)
        nr.append(nn)
    ribbon(b, pts, nr, width, thick, mat, color, segs=8)
    return pts, nr


# ####################################################################################################
#                                           W R E N
# ####################################################################################################
SKIN = srgb(206, 146, 108)
SKIN_D = srgb(176, 114, 82)
BLUSH = srgb(212, 104, 88)
LIP = srgb(176, 78, 74)
MOUTH = srgb(74, 30, 28)
HAIR = srgb(66, 42, 30)
HAIR_D = srgb(40, 26, 20)
HAIR_L = srgb(104, 70, 48)
GREY = srgb(176, 166, 154)
IRIS = srgb(132, 86, 44)
IRIS_D = srgb(54, 30, 18)
EYEWHITE = srgb(244, 240, 232)
CREAM = srgb(238, 228, 204)
CREAM_D = srgb(204, 190, 160)
RUST = srgb(166, 66, 40)
RUST_D = srgb(122, 44, 30)
SC_GREEN = srgb(64, 112, 72)
SC_GREEN_D = srgb(40, 78, 52)
OCHRE = srgb(214, 164, 62)
OCHRE_D = srgb(168, 120, 44)
TEAL = srgb(52, 92, 88)
TEAL_D = srgb(34, 64, 64)
PAPER = srgb(240, 228, 196)

W_NECK = Vector((0.0, 0.0, 1.372))
CHIN_OFF = Vector((0.0, -0.012, 0.045))
HEAD_K = 0.97
W_SHOULDER = Vector((0.168, 0.0, 1.298))
W_UPPER_L, W_FORE_L = 0.268, 0.232
U_DIR = Vector((math.sin(math.radians(9)), 0.0, -math.cos(math.radians(9)))).normalized()
F_DIR = Vector((math.sin(math.radians(3)), -math.sin(math.radians(24)), -1.0)).normalized()
ELBOW = U_DIR * W_UPPER_L
WRIST = F_DIR * W_FORE_L

EX, EZ = 0.0325, 0.134
#        front y, z      back y, z     half-w  pf    pb          (chin space: chin z=0, crown z=0.264)
HC = [(-0.031, -0.095, 0.052, -0.075, 0.0415, 2.0, 2.0),
      (-0.033, -0.050, 0.054, -0.030, 0.0380, 2.0, 2.0),
      (-0.037, -0.018, 0.057, 0.005, 0.0375, 2.0, 2.0),
      (-0.053, -0.003, 0.060, 0.028, 0.0390, 1.9, 2.0),
      (-0.088, 0.001, 0.066, 0.046, 0.0495, 1.80, 2.0),    # jaw line
      (-0.0965, 0.016, 0.073, 0.060, 0.0555, 1.88, 2.0),   # chin
      (-0.099, 0.040, 0.084, 0.076, 0.0640, 2.0, 2.0),
      (-0.101, 0.060, 0.092, 0.090, 0.0710, 2.1, 2.1),     # mouth
      (-0.102, 0.082, 0.099, 0.108, 0.0765, 2.2, 2.1),     # nose base
      (-0.101, 0.108, 0.104, 0.130, 0.0790, 2.25, 2.1),    # cheek
      (-0.100, 0.134, 0.106, 0.154, 0.0805, 2.3, 2.1),     # eyes
      (-0.1015, 0.157, 0.105, 0.176, 0.0820, 2.3, 2.1),    # brow
      (-0.101, 0.188, 0.098, 0.202, 0.0820, 2.25, 2.1),    # forehead
      (-0.090, 0.222, 0.082, 0.228, 0.076, 2.1, 2.05),
      (-0.062, 0.249, 0.058, 0.249, 0.060, 2.0, 2.0),
      (-0.028, 0.261, 0.032, 0.260, 0.034, 2.0, 2.0),
      (0.003, 0.264, 0.003, 0.264, 0.0, 2.0, 2.0)]
HSUB = [1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 4, 4, 2, 2, 2, 1]
MZ0 = 0.0575                                   # mouth line height at the centre


def mouth_z(x):
    return MZ0 + 0.0085 * (abs(x) / 0.031) ** 2


def wren_face(p, th, t):
    c = math.cos(th)
    wf = sstep((c - 0.05) / 0.45)
    x, z = p.x, p.z
    ax = abs(x)
    sx = 1.0 if x >= 0 else -1.0
    dy = 0.0
    if wf > 0:
        dy += 0.0108 * g(ax - EX, 0.023) * g(z - EZ, 0.016)             # eye sockets
        dy -= 0.0026 * g(z - 0.160, 0.012) * math.exp(-(x / 0.060) ** 4)  # soft brow
        dy += 0.0022 * g(x, 0.012) * g(z - 0.142, 0.010)                # nasion
        zN, zT = 0.146, 0.094                                           # short, slightly upturned nose
        if z >= zT:
            tt = clamp((zN - z) / (zN - zT))
            prot = (0.0030 + 0.0205 * tt ** 1.35) if z <= zN else 0.0030 * g(z - zN, 0.012)
            sig = 0.0070 + 0.0052 * tt
        else:
            prot = 0.0235 * (1 - sstep((zT - z) / 0.012))
            sig = 0.0122
        dy -= prot * math.exp(-(ax / sig) ** 2.4)
        dy -= 0.0075 * g(ax - 0.0150, 0.0062) * g(z - 0.0885, 0.0070)   # alae
        dy -= 0.0060 * g(x, 0.0110) * g(z - 0.0965, 0.0085)             # round tip
        dy -= 0.0085 * g(ax - 0.040, 0.021) * g(z - 0.101, 0.019)       # apple cheeks
        dy -= 0.0040 * g(x, 0.027) * g(z - 0.066, 0.015)                # muzzle
        dy -= 0.0030 * g(x, 0.017) * g(z - 0.0650, 0.0050)              # upper lip
        dy -= 0.0050 * g(x, 0.019) * g(z - 0.0500, 0.0065)              # lower lip
        dy += 0.0040 * g(ax - 0.033, 0.008) * g(z - 0.062, 0.009)       # tucked mouth corners
        dy += 0.0022 * g(x, 0.016) * g(z - 0.037, 0.007)                # mentolabial groove
        dy -= 0.0045 * g(x, 0.017) * g(z - 0.018, 0.013)                # soft chin
        dy += 0.0026 * g(ax - 0.026, 0.006) * g(z - 0.080, 0.013)       # smile fold
    q = p.copy()
    q.y += dy * wf
    q.x += sx * 0.0050 * g(z - 0.112, 0.018) * g(p.y + 0.062, 0.032)    # cheekbones
    q.x -= sx * 0.0030 * g(z - 0.172, 0.022) * g(p.y + 0.060, 0.028)    # temples
    q.x += sx * 0.0015 * g(z - 0.030, 0.014) * g(p.y - 0.005, 0.022)
    return q


HEAD = Loft(HC, HSUB, n=80, sculpt=wren_face, front_bias=True)


def fp(x, z, lift=0.0):
    return Vector((x, HEAD.front_y(x, z) - lift, z))


def skin_col(p):
    c = SKIN
    ax = abs(p.x)
    if p.y < -0.03:
        k = 0.55 * g(ax - 0.045, 0.021) * g(p.z - 0.098, 0.020)
        k = max(k, 0.42 * g(p.x, 0.014) * g(p.z - 0.096, 0.013))
        c = lerp3(c, BLUSH, k)
        c = mul(c, 1 - 0.18 * g(ax - EX, 0.019) * g(p.z - EZ - 0.003, 0.012))
        c = mul(c, 1 - 0.28 * g(p.x, 0.018) * g(p.z - 0.0850, 0.0042))               # under the nose
        c = mul(c, 1 - 0.10 * g(ax - 0.0150, 0.0055) * g(p.z - 0.106, 0.024))
        c = mul(c, 1 - 0.12 * g(ax - 0.034, 0.006) * g(p.z - 0.064, 0.008))          # dimples
    return c


def interp_line(H, y):
    hz = H[-1][1]
    for i in range(len(H) - 1):
        if H[i][0] <= y <= H[i + 1][0]:
            f = (y - H[i][0]) / (H[i + 1][0] - H[i][0])
            hz = H[i][1] * (1 - f) + H[i + 1][1] * f
            break
    return hz


# hairline / scarf edge height as a function of y (front -> back), chin space
HAIRLINE = [(-0.30, 0.206), (-0.086, 0.206), (-0.072, 0.195), (-0.058, 0.166), (-0.040, 0.140), (-0.022, 0.130),
            (-0.003, 0.146), (0.034, 0.146), (0.041, 0.080), (0.060, 0.050), (0.30, 0.045)]
SCARFLINE = [(-0.30, 0.2400), (-0.066, 0.2400), (-0.046, 0.218), (-0.022, 0.184), (0.004, 0.160), (0.032, 0.130),
             (0.056, 0.092), (0.075, 0.074), (0.30, 0.070)]


def hair_mask(p):
    hz = interp_line(HAIRLINE, p.y)
    if p.y < -0.05:
        hz -= 0.020 * sstep((abs(p.x) - 0.004) / 0.050)                 # centre part: hair sweeps down to the temples
        hz += 0.004 * noise.noise(Vector((p.x * 60, 0.3, 0.7)))
    return (p.z - hz) / 0.020


def scarf_mask(p):
    hz = interp_line(SCARFLINE, p.y)
    if p.y < -0.03:
        hz -= 0.012 * sstep(abs(p.x) / 0.06)
    return (p.z - hz) / 0.020


def hair_col(p):
    k = 0.5 + 0.5 * noise.noise(Vector((p.x * 26, p.y * 90, p.z * 22)))
    c = lerp3(HAIR_D, HAIR, clamp(0.10 + 1.1 * k))
    c = lerp3(c, HAIR_L, 0.35 * clamp(k * 1.6 - 0.9))
    grey = 0.22 * clamp(k * 2.2 - 1.3)                                  # a few silver strands
    return lerp3(c, GREY, grey)


def scarf_col(p):
    m = scarf_mask(p)
    a = math.atan2(p.x, -p.y + 0.02)
    k = 0.5 + 0.5 * noise.noise(Vector((p.x * 30, p.y * 30, p.z * 30)))
    c = lerp3(SC_GREEN_D, SC_GREEN, 0.5 + 0.5 * k)
    if 0.55 < m < 1.75:
        return OCHRE                                                    # border band
    if 1.75 <= m < 2.15:
        return SC_GREEN_D
    d = math.sin(a * 8.0) * math.sin(p.z * 118.0 + 1.2)
    if d > 0.62:
        return OCHRE
    if d < -0.80:
        return lerp3(CREAM, OCHRE, 0.3)
    return c


def build_eye(b):
    """Left eye (x>0) in chin space; call inside a mirrored frame for the right one."""
    R = 0.0180
    ys = HEAD.front_y(EX, EZ)
    c = Vector((EX, ys + R - 0.0098, EZ))
    with b.at(c, rot=(90, 0, 0)):
        prof = [(R * math.sin(math.radians(a)), R * math.cos(math.radians(a))) for a in (100, 80, 62, 46, 31, 16, 0)]
        b.lathe(prof, mat='paint', segs=16, color=EYEWHITE)
        ri = 0.0098
        am = math.asin(ri / R)
        Ri = R + 0.00035
        prof = [(Ri * math.sin(am * k / 3), Ri * math.cos(am * k / 3)) for k in (3, 2, 1, 0)]
        b.lathe(prof, mat='paint', segs=16, color=lambda co: lerp3(IRIS, IRIS_D, clamp((math.hypot(co.x, co.y) / ri) ** 3)))
        rp = 0.0042
        am = math.asin(rp / R)
        Rp = R + 0.0007
        b.lathe([(Rp * math.sin(am), Rp * math.cos(am)), (Rp * math.sin(am / 2), Rp * math.cos(am / 2)), (0, Rp)], mat='eye', segs=12, color=WHITE)
        b.blob((0.0022, 0.0022, 0.0007), loc=(0.0036, 0.0038, R + 0.0005), rot=(12, -12, 0), mat='paint', subdiv=1, color=WHITE)
    RL = R + 0.0013
    roll = Matrix.Rotation(math.radians(-7), 3, 'Y')                   # outer corner a little higher: smiling eyes
    lam_m = math.radians(62)
    nl = 15
    lams = [math.radians(-86 + 172 * i / (nl - 1)) for i in range(nl)]

    def P(l, ph, r):
        return c + roll @ Vector((r * math.sin(l), -r * math.cos(l) * math.cos(ph), r * math.cos(l) * math.sin(ph)))

    for upper in (True, False):
        def edge(l):
            q = abs(l - math.radians(-4 if upper else 3)) / lam_m
            if q >= 1:
                return 0.0
            k = (1 - q * q) ** 0.7
            return math.radians(29) * k if upper else math.radians(-13.5) * k

        far = math.radians(112 if upper else -112)
        rows = [[P(l, edge(l), R + 0.0002) for l in lams], [P(l, edge(l), RL) for l in lams]]
        for f in (0.2, 0.45, 0.72, 1.0):
            rows.append([P(l, edge(l) + (far - edge(l)) * f, RL) for l in lams])
        lidc = lerp3(SKIN, SKIN_D, 0.6) if upper else lerp3(SKIN, SKIN_D, 0.15)
        emit_grid(b, rows, 'skin', lidc, outward=c)
        if upper:                                                       # lash line with an outer flick
            pts = [P(l, edge(l) - 0.01, RL + 0.0003) for l in lams[2:-2]]
            pts.append(P(lams[-2] + 0.05, math.radians(7), RL + 0.0008))
            n = len(pts)
            b.tube(pts, [0.0007 + 0.0013 * math.sin(math.pi * clamp(i / (n - 1) * 0.86 + 0.02)) for i in range(n)], mat='hair', segs=5, color=mul(HAIR_D, 0.45))
    return c


def build_ear(b):
    kd_y, kd_z = 0.014, 0.118
    x = max(HEAD.pt(th, t).x for t in HEAD.TS[:-1] for th in HEAD.TH
            if abs(HEAD.pt(th, t).y - kd_y) < 0.012 and abs(HEAD.pt(th, t).z - kd_z) < 0.012)
    with b.at((x - 0.004, kd_y, kd_z), rot=(0, -8, -22)):
        earc = lerp3(SKIN, BLUSH, 0.16)
        b.blob((0.0060, 0.0140, 0.0280), loc=(0.004, 0.006, 0.0), mat='skin', subdiv=2, color=lerp3(SKIN_D, BLUSH, 0.2))
        pts, rad = [], []
        for k in range(11):
            a = math.radians(238 - 300 * k / 10)
            pts.append((0.0080, 0.006 - 0.0145 * math.cos(a), 0.002 + 0.028 * math.sin(a)))
            rad.append(0.0028 + 0.0019 * math.sin(math.pi * k / 10))
        b.tube(pts, rad, mat='skin', segs=6, color=earc)
        b.blob((0.0056, 0.0075, 0.0090), loc=(0.006, 0.003, -0.024), mat='skin', subdiv=1, color=earc)
        b.blob((0.0042, 0.0048, 0.0066), loc=(0.006, -0.008, 0.002), mat='skin', subdiv=1, color=earc)
        with b.at((0.008, 0.002, -0.041), rot=(90, 0, 20)):                                             # gold hoop
            torus(b, 0.0105, 0.0017, n=6, mat='gold', segs=12, color=WHITE)


def build_shell(b, mask, thick, colfn, mat, N=56, M=30, f0=6, top=0.008):
    """Shell hugging the head above the line where mask(p) = 0 (hair, headscarf)."""
    H = HEAD
    t0, t1 = H.K[f0], H.K[-1] - 0.004
    TH = [-math.pi + 2 * math.pi * i / N for i in range(N)]
    TT = [t0 + (t1 - t0) * j / (M - 1) for j in range(M)]
    par = [[(TH[i], TT[j]) for i in range(N)] for j in range(M)]
    mm = [[mask(H.pt(*par[j][i])) for i in range(N)] for j in range(M)]
    ok = [[mm[j][i] > 0 for i in range(N)] for j in range(M)]
    for j in range(M):
        for i in range(N):
            if mm[j][i] > 0:
                continue
            best = None
            for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                jj, ii = j + dj, (i + di) % N
                if 0 <= jj < M and mm[jj][ii] > 0 and (best is None or mm[jj][ii] > best[0]):
                    best = (mm[jj][ii], TH[i] + di * 2 * math.pi / N, TT[jj])
            if best is None:
                continue
            a, c = (TH[i], TT[j]), (best[1], best[2])
            lo, hi = 0.0, 1.0
            for _ in range(14):
                mid = (lo + hi) / 2
                q = (a[0] + (c[0] - a[0]) * mid, a[1] + (c[1] - a[1]) * mid)
                if mask(H.pt(*q)) > 0:
                    hi = mid
                else:
                    lo = mid
            par[j][i] = (a[0] + (c[0] - a[0]) * hi, a[1] + (c[1] - a[1]) * hi)
            ok[j][i] = True
    t = b._new()
    uv, col, _ = b._layers(t)
    V = {}
    cols = {}
    for j in range(M):
        for i in range(N):
            if not ok[j][i]:
                continue
            th, tt = par[j][i]
            pp = H.pt(th, tt)
            m = max(mask(pp), 0.0)
            v = t.verts.new(pp + H.nrm(th, tt) * thick(pp, th, tt, m))
            V[(i, j)] = v
            cols[v] = colfn(pp)
    for j in range(M - 1):
        for i in range(N):
            i2 = (i + 1) % N
            vs = [V[k] for k in ((i, j), (i2, j), (i2, j + 1), (i, j + 1)) if k in V]
            if len(vs) >= 3:
                try:
                    t.faces.new(vs)
                except ValueError:
                    pass
    pp = H.pt(0, H.K[-1])
    pv = t.verts.new(pp + Vector((0, 0, top)))
    cols[pv] = colfn(pp)
    for i in range(N):
        t.faces.new((pv, V[(i, M - 1)], V[((i + 1) % N, M - 1)]))
    t.normal_update()
    sgn = sum(f.normal.dot(f.calc_center_median() - Vector((0, 0, 0.15))) * f.calc_area() for f in t.faces)
    if sgn < 0:
        bmesh.ops.reverse_faces(t, faces=t.faces[:])
    t.normal_update()
    b._box_uv(t, None, 1.0)
    for f in t.faces:
        for l in f.loops:
            l[col] = (*cols[l.vert], 1.0)
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def hair_thick(pp, th, tt, m):
    base = 0.0115 + 0.0030 * noise.noise(Vector((th * 3.0, tt * 30, 1.7)))
    base += 0.0050 * g(pp.y + 0.070, 0.035) * sstep((abs(pp.x) - 0.004) / 0.025)   # volume either side of the part
    base *= 1 - 0.45 * g(pp.x, 0.0035) * sstep((-pp.y + 0.02) / 0.05)             # the parting
    base *= 1 + 0.10 * math.sin(abs(pp.x) * 260 + pp.z * 40)                      # combed strands
    return base * (0.10 + 0.90 * (1 - math.exp(-1.5 * m)))


def scarf_thick(pp, th, tt, m):
    wr = 0.0016 * math.sin(pp.x * 150 + pp.y * 60) * sstep(m / 3)
    return 0.0162 + 0.0055 * (1 - math.exp(-1.6 * m)) + 0.0035 * g(m - 1.0, 0.8) + wr


def braid(b, path, out, r, amp, freq, fade=0.12):
    """Three interwoven strands along path (list of Vectors); out = per-point outward direction."""
    n = len(path)
    L = [0.0]
    for i in range(1, n):
        L.append(L[-1] + (path[i] - path[i - 1]).length)
    for k in range(3):
        pts, rad = [], []
        for i in range(n):
            T = (path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized()
            O = Vector(out[i])
            O = (O - T * O.dot(T)).normalized()
            U = T.cross(O).normalized()
            ph = L[i] * freq + 2 * math.pi * k / 3
            s = L[i] / L[-1]
            env = sstep(s / fade) * (1.0 - 0.25 * s)
            pts.append(path[i] + U * amp * env * math.sin(ph) + O * amp * 0.55 * env * math.sin(2 * ph))
            rad.append(r * (0.72 + 0.28 * sstep(s / fade)) * (1.0 - 0.22 * s))
        b.tube(pts, rad, mat='hair', segs=7, color=lambda co: hair_col(co * 3.0))


# ---------------------------------------------------------------- body profiles (world metres)
#        z      half-w  front   back   p      cy
WBODY = [(0.940, 0.140, 0.095, 0.100, 2.3, 0.002),
         (0.985, 0.136, 0.094, 0.098, 2.3, 0.000),
         (1.030, 0.128, 0.092, 0.092, 2.3, -0.002),
         (1.090, 0.136, 0.100, 0.096, 2.3, -0.004),
         (1.160, 0.150, 0.120, 0.102, 2.3, -0.004),
         (1.215, 0.156, 0.124, 0.108, 2.35, -0.002),
         (1.270, 0.158, 0.108, 0.112, 2.45, 0.004),
         (1.325, 0.150, 0.090, 0.105, 2.5, 0.008),
         (1.357, 0.110, 0.070, 0.082, 2.3, 0.006),
         (1.377, 0.068, 0.054, 0.062, 2.1, 0.003),
         (1.393, 0.048, 0.043, 0.050, 2.0, 0.002)]
WSKIRT = [(0.100, 0.262, 0.205, 0.250, 2.1, 0.012),
          (0.350, 0.240, 0.190, 0.228, 2.1, 0.010),
          (0.600, 0.212, 0.168, 0.196, 2.15, 0.008),
          (0.800, 0.186, 0.142, 0.160, 2.2, 0.006),
          (0.920, 0.166, 0.118, 0.128, 2.3, 0.004),
          (0.985, 0.142, 0.099, 0.103, 2.3, 0.000),
          (1.030, 0.131, 0.094, 0.094, 2.3, -0.002)]
BODY_SP = Spline([r[0] for r in WBODY], [r[1:] for r in WBODY])
SKIRT_SP = Spline([r[0] for r in WSKIRT], [r[1:] for r in WSKIRT])
WAIST = 0.998


def S(spl, th_deg, z, off=0.0):
    hw, f, bk, p, cy = spl(z)
    a = math.radians(th_deg)
    s, c = math.sin(a), math.cos(a)
    d = f if c > 0 else bk
    x = hw * sp(s, 2 / p)
    y = -d * sp(c, 2 / p)
    n = Vector((sp(x / hw, p - 1) / hw, sp(y / d, p - 1) / d, 0))
    n = n.normalized() if n.length > 1e-9 else Vector((0, -1, 0))
    return Vector((x, y + cy, z)) + n * off


def S_n(spl, th_deg, z):
    return (S(spl, th_deg, z, 0.01) - S(spl, th_deg, z, 0.0)).normalized()


def SB(th, z, off=0.0):
    """Torso above the waist, skirt below."""
    return S(BODY_SP if z >= WAIST else SKIRT_SP, th, z, off)


def SB_n(th, z):
    return S_n(BODY_SP if z >= WAIST else SKIRT_SP, th, z)


def neckline(th):
    c = math.cos(math.radians(th))
    return 1.350 - 0.052 * max(c, 0) ** 2 - 0.006 * max(-c, 0)


def bodice_top(th):
    a = abs((th + 180) % 360 - 180)
    z = 1.236 + 0.100 * sstep((a - 20) / 44)
    if a > 108:
        z = 1.336 - 0.040 * sstep((a - 108) / 55)
    return min(z, neckline(th) - 0.012)


def under_fold(th, z):
    t = clamp((WAIST - z) / 0.9)
    v = (0.5 + 0.5 * math.sin(math.radians(th) * 11 + 0.6 + 1.3 * math.sin(z * 4.0))) ** 1.4
    return 0.030 * t ** 1.25, v


def over_hem(th):
    d = abs((th + 78 + 180) % 360 - 180)
    return 0.375 + 0.022 * math.sin(math.radians(th) * 3 + 1.0) + 0.175 * g(d, 40)


def over_fold(th, z):
    t = clamp((WAIST - z) / 0.62)
    v = (0.5 + 0.5 * math.sin(math.radians(th) * 8 + 2.2 + 2.0 * math.sin(z * 5.0))) ** 1.3
    return 0.020 * t ** 1.15, v


def under_off(th, z):
    a, v = under_fold(th, z)
    return 0.006 + a * v


def over_off(th, z):
    a, _ = under_fold(th, z)
    a2, v2 = over_fold(th, z)
    return 0.006 + a + 0.009 + a2 * v2


def apron_off(th, z):
    a, _ = under_fold(th, z)
    a2, _ = over_fold(th, z)
    return 0.006 + a + 0.009 + a2 + 0.007 + 0.003 * math.sin(math.radians(th) * 5 + z * 9)


def build_wren_body():
    b = B('peddler', 21)
    N = 30
    THS = [360 * i / N for i in range(N)]
    # ---- blouse (cloth) up to a wide gathered neckline, skin above it
    vs = [0.0, 0.07, 0.15, 0.23, 0.31, 0.39, 0.47, 0.55, 0.63, 0.71, 0.79, 0.86, 0.92, 0.97, 1.0]
    z0 = 0.975
    rows = [[S(BODY_SP, th, z0 + (neckline(th) - z0) * v, 0.004 + 0.004 * g(z0 + (neckline(th) - z0) * v - 1.262, 0.03)) for th in THS] for v in vs]

    def bcol(co):
        k = 0.5 + 0.5 * math.sin(co.z * 70 + co.x * 30)
        return lerp3(CREAM_D, CREAM, 0.6 + 0.4 * k)

    emit_grid(b, rows, 'cloth', bcol, wrap=True, outward=lambda c: Vector((c.x, c.y, 0)), pole_start=Vector((0, 0, 0.97)))
    vs2 = [0.0, 0.3, 0.6, 0.85, 1.0]
    rows = [[S(BODY_SP, th, neckline(th) - 0.004 + (1.393 - neckline(th) + 0.004) * v) for th in THS] for v in vs2]
    emit_grid(b, rows, 'skin', lambda co: lerp3(SKIN_D, SKIN, clamp(0.55 + (co.z - 1.30) * 6)), wrap=True,
              outward=lambda c: Vector((c.x, c.y, 0.3)), pole_end=Vector((0, 0.004, 1.395)))
    # gathered neckline trim
    pts = [S(BODY_SP, 360 * i / 40, neckline(360 * i / 40) - 0.002, 0.0065) + Vector((0, 0, 0.0025 * math.sin(i * 2.4))) for i in range(41)]
    b.tube(pts, [0.0062 + 0.0014 * math.sin(i * 3.1) for i in range(41)], mat='cloth', segs=6, caps=False, color=CREAM)

    # ---- rust bodice, laced at the front
    NB = 44
    TB = [360 * i / NB for i in range(NB)]
    zb0 = 0.990
    vb = [0.0, 0.10, 0.22, 0.34, 0.46, 0.58, 0.70, 0.82, 0.91, 0.97, 1.0]

    def bod(th, v, lip=False):
        z = zb0 + (bodice_top(th) - zb0) * v
        off = 0.0125 + 0.0015 * math.sin(math.radians(th) * 2) ** 2
        a = abs((th + 180) % 360 - 180)
        off -= 0.0030 * g(a, 3.5)                                       # centre front seam
        if v >= 0.97:
            off += 0.0025
        if lip:
            off = 0.003
        return S(BODY_SP, th, z, off)

    rows = [[bod(th, v) for th in TB] for v in vb] + [[bod(th, 1.0, True) for th in TB]]

    def bodcol(co):
        k = clamp((co.z - 1.0) / 0.3)
        c = lerp3(RUST_D, RUST, 0.45 + 0.55 * k)
        return mul(c, 1 - 0.35 * g(co.x, 0.006) * (1 if co.y < 0 else 0))

    emit_grid(b, rows, 'cloth', bodcol, wrap=True, outward=lambda c: Vector((c.x, c.y, 0)),
              facecol=lambda i, j: OCHRE if j >= len(vb) - 3 else None)
    # lacing + eyelets
    zs = [1.018 + 0.036 * k for k in range(6)]
    for k, z in enumerate(zs):
        for sx in (-1, 1):
            p = S(BODY_SP, sx * 9.5, z, 0.0135)
            b.blob((0.0042, 0.0026, 0.0042), loc=p, mat='gold', subdiv=1, color=WHITE)
        if k < len(zs) - 1:
            for sx in (-1, 1):
                pa, pb = S(BODY_SP, sx * 9.5, z, 0.0150), S(BODY_SP, -sx * 9.5, zs[k + 1], 0.0150)
                pm = S(BODY_SP, 0, (z + zs[k + 1]) / 2, 0.0135 + (0.0012 if sx > 0 else 0.0))
                b.tube([pa, pm, pb], 0.0022, mat='cloth', segs=5, color=CREAM)
    # little bow at the top of the lacing
    p = S(BODY_SP, 0, zs[-1] + 0.006, 0.016)
    for sx in (-1, 1):
        b.tube([p, p + Vector((sx * 0.016, -0.004, 0.012)), p + Vector((sx * 0.026, -0.003, 0.002)), p + Vector((sx * 0.012, -0.003, -0.004)), p],
               0.0024, mat='cloth', segs=5, color=CREAM)
        b.tube([p, p + Vector((sx * 0.010, -0.004, -0.022)), p + Vector((sx * 0.014, -0.003, -0.040))], [0.0024, 0.0022, 0.0016], mat='cloth', segs=5, color=CREAM)

    # ---- underskirt (ochre), closed at the hem
    NS = 48
    TSK = [360 * i / NS for i in range(NS)]
    zu = [0.105, 0.125, 0.16, 0.22, 0.29, 0.36, 0.44, 0.52, 0.60, 0.68, 0.76, 0.84, 0.91, 0.96, 1.0]
    rows = [[S(SKIRT_SP, th, z, under_off(th, z)) for th in TSK] for z in zu]
    cols = [[mul(lerp3(OCHRE_D, OCHRE, 0.25 + 0.75 * under_fold(th, z)[1]), 0.80 + 0.2 * clamp((z - 0.1) / 0.4)) for th in TSK] for z in zu]
    emit_grid(b, rows, 'cloth', cols, wrap=True, outward=lambda c: Vector((c.x, c.y, 0)),
              facecol=lambda i, j: RUST_D if j == 1 else None)
    rows = [[S(SKIRT_SP, th, 0.105, under_off(th, 0.105)) for th in TSK], [S(SKIRT_SP, th, 0.135, -0.05) for th in TSK]]
    emit_grid(b, rows, 'cloth', mul(OCHRE_D, 0.35), wrap=True, outward=lambda c: Vector((0, 0, -1)), pole_end=Vector((0, 0.01, 0.14)))

    # ---- overskirt (teal), tucked up at her right hip
    vo = [0.0, 0.035, 0.08, 0.16, 0.26, 0.37, 0.49, 0.61, 0.73, 0.84, 0.93, 1.0]

    def ov(th, v, inner=False):
        z = over_hem(th) + (1.0 - over_hem(th)) * v
        return S(SKIRT_SP, th, z, under_off(th, z) + 0.001 if inner else over_off(th, z))

    rows = [[ov(th, v) for th in TSK] for v in vo]
    cols = []
    for v in vo:
        row = []
        for th in TSK:
            z = over_hem(th) + (1.0 - over_hem(th)) * v
            row.append(lerp3(TEAL_D, TEAL, 0.2 + 0.8 * over_fold(th, z)[1]))
        cols.append(row)
    emit_grid(b, rows, 'cloth', cols, wrap=True, outward=lambda c: Vector((c.x, c.y, 0)),
              facecol=lambda i, j: OCHRE if j == 1 else None)
    rows = [[ov(th, 0.0) for th in TSK], [ov(th, 0.0, True) for th in TSK]]
    emit_grid(b, rows, 'cloth', TEAL_D, wrap=True, outward=lambda c: Vector((0, 0, -1)))

    # ---- leather apron with a double pocket
    A0, A1 = -47.0, 47.0
    us = [0.0, 0.03, 0.09] + [0.09 + 0.82 * i / 10 for i in range(1, 10)] + [0.91, 0.97, 1.0]
    va = [0.0, 0.03, 0.08] + [0.08 + 0.88 * j / 12 for j in range(1, 12)] + [0.96, 1.0]
    nu, nv = len(us), len(va)

    def ap(i, j):
        u, v = us[i], va[j]
        zl = 0.455 + 0.060 * abs(2 * u - 1) ** 5
        z = zl + (1.004 - zl) * v
        th = A0 + (A1 - A0) * u
        off = apron_off(th, z)
        if i in (0, nu - 1) or j == 0:
            off -= 0.010
        return S(SKIRT_SP, th, z, off)

    rows = [[ap(i, j) for i in range(nu)] for j in range(nv)]
    emit_grid(b, rows, 'leather', lambda co: mul(LEA, 0.95 + 0.25 * noise.noise(co * 9.0)), outward=lambda c: Vector((c.x, c.y, 0)),
              facecol=lambda i, j: mul(LEA, 0.62) if (i in (1, nu - 3) or j == 1) else None)
    PZ0, PZ1 = 0.640, 0.800
    pu = [0.0, 0.04, 0.14, 0.26, 0.38, 0.47, 0.50, 0.53, 0.62, 0.74, 0.86, 0.96, 1.0]
    pv_ = [0.0, 0.05, 0.25, 0.5, 0.75, 0.93, 1.0]

    def pocket_off(u, v):
        bulge = 0.012 + 0.012 * v
        bulge *= 0.35 + 0.65 * abs(math.sin(math.pi * 2 * min(u, 1 - u) * 1.0)) ** 0.5 if abs(u - 0.5) < 0.04 else 1.0
        return bulge

    def pk(i, j):
        u, v = pu[i], pv_[j]
        th = -31 + 62 * u
        z = PZ0 + (PZ1 - PZ0) * v + 0.012 * abs(2 * u - 1) ** 3 * (1 - v)
        off = apron_off(th, z) + pocket_off(u, v)
        if i in (0, len(pu) - 1) or j == 0:
            off = apron_off(th, z) - 0.002
        return S(SKIRT_SP, th, z, off)

    rows = [[pk(i, j) for i in range(len(pu))] for j in range(len(pv_))]
    emit_grid(b, rows, 'leather', mul(LEA, 1.18), outward=lambda c: Vector((c.x, c.y, 0)),
              facecol=lambda i, j: mul(LEA, 0.62) if (j >= len(pv_) - 2 or i in (5, 6)) else None)
    # ledger (her right pocket) and pencil (left pocket)
    th, z = -15.0, PZ1 - 0.012
    p, n = S(SKIRT_SP, th, z, apron_off(th, z) + 0.011), S_n(SKIRT_SP, th, z)
    with b.at(p, aim(n)):
        with b.at(rot=(0, -7, 0)):
            b.box((0.082, 0.017, 0.112), loc=(0, 0, 0.020), mat='paint', bevel=0.003, segs=1, grain=None, color=PAPER)
            b.box((0.088, 0.0045, 0.118), loc=(0, -0.0105, 0.020), mat='leather', bevel=0.002, segs=1, grain=None, color=mul(RUST, 2.2))
            b.box((0.088, 0.0045, 0.118), loc=(0, 0.0105, 0.020), mat='leather', bevel=0.002, segs=1, grain=None, color=mul(RUST, 2.2))
            b.box((0.006, 0.024, 0.118), loc=(-0.043, 0, 0.020), mat='leather', bevel=0.002, segs=1, grain=None, color=mul(RUST, 1.8))
            b.box((0.090, 0.0052, 0.012), loc=(0, -0.0108, 0.052), mat='gold', bevel=0.001, segs=1, grain=None, color=WHITE)
    th = 13.0
    p, n = S(SKIRT_SP, th, z, apron_off(th, z) + 0.012), S_n(SKIRT_SP, th, z)
    with b.at(p, aim(n)):
        with b.at(rot=(0, 9, 0)):
            b.cyl(0.0048, 0.125, loc=(0, 0, -0.045), mat='paint', segs=6, bevel=0.0008, color=OCHRE)
            b.cyl(0.0048, 0.016, loc=(0, 0, 0.080), mat='paint', segs=6, bevel=0.0008, r_top=0.0012, color=PAPER)
            b.cyl(0.0014, 0.005, loc=(0, 0, 0.094), mat='paint', segs=5, bevel=0.0004, r_top=0.0003, color=mul(HAIR_D, 0.5))
    # ---- belt over the apron band, with a brass buckle
    BZ0, BZ1 = 0.984, 1.020
    prof = [(BZ0 - 0.002, 0.004), (BZ0, 0.0125), (BZ0 + 0.004, 0.0160), (BZ1 - 0.004, 0.0160), (BZ1, 0.0125), (BZ1 + 0.002, 0.004)]
    rows = [[S(SKIRT_SP, 360 * i / 40, z, o + 0.012) for i in range(40)] for z, o in prof]
    emit_grid(b, rows, 'leather', mul(LEA, 0.8), wrap=True, outward=lambda c: Vector((c.x, c.y, 0)))
    zc = (BZ0 + BZ1) / 2
    p, n = S(SKIRT_SP, 22, zc, 0.030), S_n(SKIRT_SP, 22, zc)
    with b.at(p, aim(n)):
        b.box((0.046, 0.008, 0.050), mat='gold', bevel=0.004, grain=None, color=WHITE)
        b.box((0.026, 0.010, 0.030), loc=(0, -0.001, 0), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.7))
        b.box((0.005, 0.012, 0.036), loc=(0.003, -0.002, 0), mat='gold', bevel=0.002, grain=None, color=WHITE)
        ribbon(b, [(0.026, 0.004, 0.0), (0.034, -0.002, -0.03), (0.038, -0.004, -0.072), (0.039, -0.003, -0.105)], Vector((0, -1, 0)), 0.028, 0.006, 'leather', mul(LEA, 0.8), segs=8)
    # coin purse on her right hip
    p, n = S(SKIRT_SP, -58, zc, 0.028), S_n(SKIRT_SP, -58, zc)
    with b.at(p, aim(n)):
        b.box((0.030, 0.008, 0.050), loc=(0, -0.002, 0.0), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.7))
        b.blob((0.040, 0.030, 0.046), loc=(0, -0.020, -0.062), mat='leather', subdiv=2, color=mul(LEA, 1.3),
               deform=lambda c: Vector((c.x * (1 - 0.45 * clamp(c.z / 0.046)), c.y * (1 - 0.45 * clamp(c.z / 0.046)), c.z)))
        torus(b, 0.019, 0.0045, z=-0.026, n=6, loc=(0, -0.020, 0), mat='rope', segs=10, color=WHITE)
        b.blob((0.022, 0.018, 0.010), loc=(0, -0.020, -0.016), mat='leather', subdiv=1, color=mul(LEA, 1.2))

    # ---- satchel strap: right shoulder -> left hip, satchel behind the left hip
    def strap(th0, th1, z0, z1, n=14, off=0.0185):
        pts, nr = [], []
        for i in range(n + 1):
            u = i / n
            th, z = th0 + (th1 - th0) * u, z0 + (z1 - z0) * u
            o = off + (0.014 if z < WAIST + 0.03 else 0.0) * sstep((WAIST + 0.03 - z) / 0.03)
            pts.append(SB(th, z, o))
            nr.append(SB_n(th, z))
        return pts, nr

    fp_, fn_ = strap(-66, 118, 1.338, 0.955)
    bp_, bn_ = strap(-114, -236, 1.338, 0.955)
    top = Vector((-0.112, 0.006, 1.372))
    pts = list(reversed(bp_)) + [top] + fp_
    nrs = list(reversed(bn_)) + [Vector((-0.35, 0, 1))] + fn_
    ribbon(b, pts, nrs, 0.030, 0.007, 'leather', mul(LEA, 0.9), segs=8)
    p, n = fp_[5], fn_[5]
    with b.at(p + n * 0.003, aim(n)):
        b.box((0.040, 0.007, 0.034), rot=(0, -38, 0), mat='gold', bevel=0.003, grain=None, color=WHITE)
        b.box((0.024, 0.009, 0.018), rot=(0, -38, 0), mat='leather', bevel=0.002, grain=None, color=mul(LEA, 0.8))
    th, z = 121.0, 0.86
    p, n = S(SKIRT_SP, th, z, over_off(th, z) + 0.048), S_n(SKIRT_SP, th, z)
    with b.at(p, aim(n)):
        def bag(c):
            return Vector((sp(c.x / 0.115, 0.72) * 0.115, sp(c.y / 0.046, 0.8) * 0.046, sp(c.z / 0.095, 0.72) * 0.095))

        b.blob((0.115, 0.046, 0.095), mat='leather', subdiv=3, deform=bag, color=lambda co: mul(LEA, 0.95 + 0.2 * noise.noise(co * 14)))
        b.blob((0.119, 0.050, 0.060), loc=(0, -0.003, 0.040), mat='leather', subdiv=2, color=mul(LEA, 1.3),
               deform=lambda c: Vector((sp(c.x / 0.119, 0.72) * 0.119, c.y, c.z if c.z > 0 else c.z * 1.25 * (1 - 0.3 * abs(c.x) / 0.119))))
        b.box((0.026, 0.008, 0.070), loc=(0, -0.050, -0.010), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.75))
        b.box((0.034, 0.008, 0.030), loc=(0, -0.054, -0.036), mat='gold', bevel=0.003, grain=None, color=WHITE)
        # a roll of cloth and a sprig poking out of the top
        b.cyl(0.022, 0.15, loc=(-0.075, 0.004, 0.075), rot=(0, 90, 0), mat='cloth', segs=10, bevel=0.006, color=SC_GREEN)

    # ---- boots under the hem
    boot = mul(LEA, 0.80)
    for s in (1, -1):
        with b.at(scale=(s, 1, 1)):
            with b.at((0.088, -0.070, 0.0), rot=(0, 0, 10)):
                b.tube([(0, 0.012, 0.070), (0, 0.016, 0.160), (0, 0.016, 0.240)], [0.043, 0.045, 0.050], mat='leather', segs=10, color=boot)

                def foot(c):
                    t = clamp(-c.y / 0.120)
                    if c.z > 0:
                        c.z *= 1.0 - 0.60 * t ** 1.1
                    c.x *= 1.0 + 0.10 * math.sin(math.pi * clamp(t * 0.8 + 0.1)) - 0.24 * t ** 3
                    return c

                b.blob((0.044, 0.122, 0.058), loc=(0, -0.050, 0.053), mat='leather', subdiv=2, flatten_bottom=-0.62, deform=foot, color=boot)

                def sole(c):
                    c.z = clamp(c.z, -0.010, 0.010)
                    t = clamp(-c.y / 0.125)
                    c.x *= 1.0 + 0.10 * math.sin(math.pi * clamp(t * 0.8 + 0.1)) - 0.20 * t ** 3
                    return c

                b.blob((0.048, 0.128, 0.03), loc=(0, -0.050, 0.0115), mat='leather', subdiv=2, deform=sole, color=mul(LEA, 0.3))
                b.box((0.080, 0.058, 0.024), loc=(0, 0.036, 0.012), mat='leather', bevel=0.006, grain=None, color=mul(LEA, 0.3))
    return b.build(sharp_angle=60)


def build_wren_head():
    b = B('peddler_head', 3)
    H = HEAD
    with b.at(CHIN_OFF * HEAD_K, scale=HEAD_K):
        def hcol(p, th, t):
            k = 1 - 0.20 * sstep((H.K[4] - t) / (H.K[4] - H.K[3]) * 1.2)
            return mul(skin_col(p), k)

        H.emit(b, 'skin', col_tt=hcol)
        for s in (1, -1):
            with b.at(scale=(s, 1, 1)):
                build_eye(b)
                build_ear(b)
                bp = [(0.0125, 0.1640), (0.021, 0.1688), (0.031, 0.1722), (0.041, 0.1722), (0.050, 0.1690), (0.0575, 0.1635)]
                pts = [fp(x, z, 0.0010) for x, z in bp]
                ribbon(b, pts, Vector((0, -1, 0.15)), lambda t: 0.0022 + 0.0042 * math.sin(math.pi * clamp(0.25 + 0.62 * t)), 0.0048, 'hair', lerp3(HAIR_D, HAIR, 0.5), segs=8)
        for sx_ in (-1, 1):                                                          # nostrils
            b.blob((0.0038, 0.0028, 0.0024), loc=fp(sx_ * 0.0078, 0.0868, -0.0012), rot=(0, sx_ * 24, 0), mat='skin', subdiv=1, color=mul(SKIN_D, 0.40))
        # freckles across the nose and cheeks
        rng = b.rng
        for _ in range(26):
            x = rng.uniform(-0.050, 0.050)
            z = 0.106 + rng.uniform(-0.010, 0.012) - 0.10 * abs(x) * abs(x) / 0.05
            if abs(x) < 0.006:
                z = 0.112 + rng.uniform(-0.004, 0.006)
            r = rng.uniform(0.0008, 0.0014)
            p0 = fp(x, z, 0.0)
            e = 0.002
            nx = Vector((2 * e, HEAD.front_y(x + e, z) - HEAD.front_y(x - e, z), 0)).cross(Vector((0, HEAD.front_y(x, z + e) - HEAD.front_y(x, z - e), 2 * e)))
            nx = -nx.normalized() if nx.y > 0 else nx.normalized()
            with b.at(p0 + nx * 0.0002, tuple(a + 90 if i == 0 else a for i, a in enumerate(aim(nx)))):
                b.lathe([(r, 0.0), (r * 0.6, 0.00025), (0, 0.00035)], mat='skin', segs=6, color=lerp3(SKIN_D, HAIR, 0.35))
        # smile: dark opening, teeth, upper and lower lip
        xs = [-0.031, -0.026, -0.019, -0.010, 0.0, 0.010, 0.019, 0.026, 0.031]
        b.tube([fp(x, mouth_z(x), -0.0012) for x in xs], [0.0010, 0.0022, 0.0031, 0.0036, 0.0037, 0.0036, 0.0031, 0.0022, 0.0010], mat='paint', segs=6, color=MOUTH)
        xt = [-0.019, -0.012, -0.004, 0.004, 0.012, 0.019]
        b.tube([fp(x, mouth_z(x) + 0.0012, 0.0003) for x in xt], [0.0011, 0.0021, 0.0024, 0.0024, 0.0021, 0.0011], mat='paint', segs=6, color=EYEWHITE)
        xu = [-0.0305, -0.024, -0.016, -0.007, 0.0, 0.007, 0.016, 0.024, 0.0305]
        wu = [0.0016, 0.0042, 0.0062, 0.0076, 0.0066, 0.0076, 0.0062, 0.0042, 0.0016]
        pts = [fp(x, mouth_z(x) + 0.0020 + w * 0.5, 0.0008) for x, w in zip(xu, wu)]
        ribbon(b, pts, Vector((0, -1, 0.25)), lambda t: wu[min(int(t * 8 + 0.5), 8)], 0.0056, 'skin', LIP, segs=8)
        xl = [-0.0270, -0.020, -0.011, 0.0, 0.011, 0.020, 0.0270]
        wl = [0.0018, 0.0058, 0.0086, 0.0096, 0.0086, 0.0058, 0.0018]
        pts = [fp(x, MZ0 - 0.0024 + 0.0060 * (abs(x) / 0.027) ** 2 - w * 0.5 + 0.0016, 0.0006) for x, w in zip(xl, wl)]
        ribbon(b, pts, Vector((0, -1, -0.2)), lambda t: wl[min(int(t * 6 + 0.5), 6)], 0.0066, 'skin', lerp3(LIP, BLUSH, 0.25), segs=8)
        # hair, then the headscarf over it
        build_shell(b, hair_mask, hair_thick, hair_col, 'hair', N=56, M=28)
        build_shell(b, scarf_mask, scarf_thick, scarf_col, 'cloth', N=64, M=32, top=0.022)
        # scarf knot and tails at the nape
        b.blob((0.021, 0.015, 0.016), loc=(0, 0.112, 0.090), mat='cloth', subdiv=2, color=SC_GREEN_D)
        for s in (1, -1):
            pts = [(s * 0.008, 0.114, 0.088), (s * 0.026, 0.118, 0.066), (s * 0.032, 0.110, 0.040), (s * 0.034, 0.100, 0.018)]
            ribbon(b, pts, Vector((s * 0.3, 1, 0.1)), lambda t: 0.016 + 0.016 * math.sin(math.pi * clamp(t * 0.8 + 0.1)), 0.006, 'cloth', SC_GREEN, segs=8, color_top=SC_GREEN_D)
    # ---- braid: nape -> over the left shoulder -> down the chest (pivot-local = world - neck pivot)
    ctrl = [Vector((0.018, 0.070, 1.485)), Vector((0.040, 0.086, 1.440)), Vector((0.076, 0.070, 1.402)), Vector((0.104, 0.018, 1.386)),
            Vector((0.110, -0.050, 1.360))]
    outs = [Vector((0.1, 1, 0)), Vector((0.3, 1, 0.2)), Vector((0.5, 0.6, 0.7)), Vector((0.4, 0, 1)), Vector((0.3, -0.7, 0.7))]
    for th, z in ((46, 1.305), (41, 1.255), (37, 1.205), (34, 1.160), (32, 1.120)):
        ctrl.append(S(BODY_SP, th, z, 0.036))
        outs.append(S_n(BODY_SP, th, z))
    path = [p - W_NECK for p in smooth_path(ctrl, 5)]
    out = smooth_path(outs, 5)
    braid(b, path, out, 0.0165, 0.0135, 2 * math.pi / 0.085)
    end, e_out = path[-1], out[-1].normalized()
    dn = (path[-1] - path[-3]).normalized()
    eul = Vector((0, 0, 1)).rotation_difference(dn).to_euler('XYZ')
    with b.at(end - dn * 0.012, tuple(math.degrees(a) for a in eul)):
        torus(b, 0.0175, 0.0065, n=6, mat='cloth', segs=12, color=RUST)
        b.tube([(0, 0, 0.0), (0.002, 0, 0.030), (0.004, 0, 0.062), (0.005, 0, 0.082)], [0.019, 0.024, 0.015, 0.003], mat='hair', segs=8, color=HAIR, color_top=HAIR_L)
    return b.build(sharp_angle=80)


def _sleeve(n, r0, r1, wr, f, ph):
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append((r0 + (r1 - r0) * t) * (1 + wr * math.sin(t * f + ph) * sstep(t * 3)))
    return out


def build_wren_arm(name, s):
    b = B(name, 11)
    with b.at(scale=(s, 1, 1)):
        n = 8
        pts = [ELBOW * (i / (n - 1)) for i in range(n)]
        rad = _sleeve(n, 0.058, 0.050, 0.035, 15.0, 0.5)
        rad[1] *= 1.06
        b.tube(pts, rad, mat='cloth', segs=14, color=CREAM, color_top=lerp3(CREAM_D, CREAM, 0.6))
    return b.build(sharp_angle=70)


def hand_frame():
    """Matrix (left side) taking the canonical hand (fingers -Z, palm -X, thumb -Y) to the wrist."""
    Zc = -F_DIR
    tw = math.radians(-20)
    Xc = Vector((math.cos(tw), math.sin(tw), 0))
    Xc = (Xc - Zc * Xc.dot(Zc)).normalized()
    Yc = Zc.cross(Xc).normalized()
    R = Matrix((Xc, Yc, Zc)).transposed()
    return Matrix.Translation(WRIST) @ R.to_4x4()


def build_hand(b):
    """Canonical left hand: wrist at the origin, fingers along -Z, palm faces -X, thumb toward -Y."""
    def palm(c):
        u = Vector((c.x / 0.0135, c.y / 0.041, c.z / 0.052))
        q = Vector((sp(u.x, 0.85) * 0.0135, sp(u.y, 0.72) * 0.041, sp(u.z, 0.78) * 0.052))
        q.y *= 0.80 + 0.20 * clamp((-q.z + 0.052) / 0.104)
        q.x += -0.004 * clamp((-q.z) / 0.052) ** 2 * 1.0
        return q

    b.blob((0.0135, 0.041, 0.052), loc=(0, 0, -0.052), mat='skin', subdiv=2, deform=palm, color=SKIN)
    with b.at(scale=(0.74, 1.18, 1)):
        b.tube([(0, 0, 0.03), (0, 0, -0.022)], [0.0235, 0.0205], mat='skin', segs=10, color=SKIN)
    fingers = [(-0.0300, -0.097, 0.073, 0.0092, (8, 28, 44), -7), (-0.0100, -0.101, 0.082, 0.0096, (12, 34, 52), -2),
               (0.0100, -0.098, 0.075, 0.0090, (17, 41, 60), 3), (0.0290, -0.090, 0.060, 0.0080, (22, 48, 68), 9)]
    tipc = lerp3(SKIN, BLUSH, 0.25)
    for y, z, L, r, angs, splay in fingers:
        p = Vector((-0.0010, y, z))
        pts = [p + Vector((0.0015, 0, 0.020)), p.copy()]
        rad = [r * 1.04, r * 1.05]
        for frac, a, k in zip((0.44, 0.30, 0.26), angs, (0.98, 0.93, 0.80)):
            ar, sr = math.radians(a), math.radians(splay)
            d = Vector((-math.sin(ar), math.sin(sr) * math.cos(ar), -math.cos(ar) * math.cos(sr)))
            pts.append(p + d * (L * frac * 0.5))
            rad.append(r * (k + rad[-1] / r) / 2 * 0.97)
            p = p + d * (L * frac)
            pts.append(p.copy())
            rad.append(r * k)
        b.tube(pts, rad, mat='skin', segs=7, color=SKIN, color_top=tipc)
    b.blob((0.0125, 0.0170, 0.030), loc=(-0.0080, -0.026, -0.040), rot=(-20, 0, 0), mat='skin', subdiv=2, color=SKIN)
    b.tube([(-0.006, -0.028, -0.026), (-0.010, -0.046, -0.050), (-0.016, -0.058, -0.072), (-0.022, -0.063, -0.090)],
           [0.0125, 0.0112, 0.0100, 0.0086], mat='skin', segs=8, color=SKIN, color_top=tipc)


def build_wren_forearm(name, s):
    b = B(name, 12)
    with b.at(scale=(s, 1, 1)):
        # rolled-up sleeve just below the elbow
        b.tube([WRIST * 0.0, WRIST * 0.10, WRIST * 0.20, WRIST * 0.27], [0.049, 0.053, 0.050, 0.040], mat='cloth', segs=14, color=CREAM, color_top=CREAM_D)
        d = F_DIR
        eul = Vector((0, 0, 1)).rotation_difference(-d).to_euler('XYZ')
        with b.at(WRIST * 0.27, tuple(math.degrees(a) for a in eul)):
            torus(b, 0.0400, 0.0125, n=8, scale=(1.0, 1.0, 1.25), mat='cloth', segs=16, color=lerp3(CREAM, CREAM_D, 0.25))
            torus(b, 0.0395, 0.0085, z=-0.014, n=6, mat='cloth', segs=16, color=CREAM)
        # bare forearm
        n = 7
        pts = [WRIST * (0.20 + 0.70 * i / (n - 1)) for i in range(n)]
        b.tube(pts, [0.0400, 0.0405, 0.0385, 0.0350, 0.0310, 0.0275, 0.0250], mat='skin', segs=12, color=SKIN)
        M = hand_frame()
        eul = tuple(math.degrees(a) for a in M.to_euler('XYZ'))
        with b.at(WRIST, eul, scale=0.93):
            build_hand(b)
            # a braided cord bracelet
            torus(b, 0.0235, 0.0030, z=0.012, n=6, scale=(0.80, 1.22, 1), mat='cloth', segs=14, color=OCHRE)
    return b.build(sharp_angle=70)


def build_peddler():
    root = build_wren_body()
    head = kit.set_parent(build_wren_head(), root, W_NECK)
    eye_y = HEAD.front_y(0.0, EZ)
    kit.marker('peddler_eye', (CHIN_OFF + Vector((0, eye_y, EZ))) * HEAD_K, parent=head)
    for side, s in (('l', 1), ('r', -1)):
        arm = kit.set_parent(build_wren_arm(f'peddler_arm_{side}', s), root, (s * W_SHOULDER.x, W_SHOULDER.y, W_SHOULDER.z))
        kit.set_parent(build_wren_forearm(f'peddler_forearm_{side}', s), arm, (s * ELBOW.x, ELBOW.y, ELBOW.z))
    return root


# ####################################################################################################
#                                           P O N Y
# ####################################################################################################
CH = srgb(150, 80, 40)            # chestnut
CH_D = srgb(112, 56, 28)
CH_L = srgb(178, 108, 60)
FLAX = srgb(232, 204, 148)
FLAX_D = srgb(196, 160, 100)
FLAX_L = srgb(246, 230, 190)
SOCK = srgb(240, 232, 214)
MUZZLE = srgb(96, 66, 56)
PINK = srgb(206, 150, 138)
HOOF = srgb(70, 56, 46)
P_HEAD = Vector((0.0, -0.45, 1.15))            # base of the neck
P_TAIL = Vector((0.0, 0.725, 1.215))
LEG_FX, LEG_BX = 0.165, 0.180
P_LEG_F = Vector((LEG_FX, -0.46, 0.98))
P_LEG_B = Vector((LEG_BX, 0.50, 1.02))
P_HITCH = Vector((0.0, 1.10, 0.85))


def body_sculpt(p, th, t):
    q = p.copy()
    s = 1.0 if p.x >= 0 else -1.0
    k = clamp(abs(p.x) / 0.18)
    q.x += s * 0.024 * g(p.y + 0.47, 0.15) * g(p.z - 1.00, 0.20) * k        # shoulder
    q.x += s * 0.022 * g(p.y - 0.50, 0.17) * g(p.z - 1.04, 0.22) * k        # quarters
    q.x -= s * 0.014 * g(p.y - 0.23, 0.085) * g(p.z - 0.98, 0.14) * k       # flank hollow
    q.x += s * 0.012 * g(p.y - 0.02, 0.20) * g(p.z - 0.82, 0.14) * k        # round belly
    q.z -= 0.012 * g(p.y + 0.02, 0.22) * sstep((0.80 - p.z) / 0.1)
    return q


#          top y, z        bottom y, z   half-w  p_top p_bot
PBODY = [(-0.640, 1.060, -0.640, 0.950, 0.0, 2.0, 2.0),
         (-0.625, 1.150, -0.630, 0.840, 0.135, 2.0, 2.0),
         (-0.585, 1.240, -0.595, 0.750, 0.222, 2.1, 2.1),
         (-0.500, 1.310, -0.510, 0.690, 0.275, 2.2, 2.2),
         (-0.390, 1.350, -0.400, 0.655, 0.300, 2.1, 2.3),          # withers
         (-0.250, 1.325, -0.250, 0.625, 0.320, 2.3, 2.3),
         (-0.050, 1.290, -0.050, 0.600, 0.340, 2.4, 2.3),          # back / barrel
         (0.150, 1.290, 0.150, 0.610, 0.344, 2.4, 2.3),
         (0.320, 1.315, 0.320, 0.660, 0.332, 2.4, 2.2),            # loin
         (0.480, 1.345, 0.480, 0.720, 0.334, 2.5, 2.2),            # croup
         (0.620, 1.320, 0.620, 0.760, 0.314, 2.4, 2.2),
         (0.715, 1.230, 0.720, 0.810, 0.255, 2.2, 2.1),
         (0.765, 1.120, 0.765, 0.880, 0.150, 2.0, 2.0),
         (0.780, 1.000, 0.780, 0.990, 0.0, 2.0, 2.0)]
PB = Loft(PBODY, [2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2], n=32, sculpt=body_sculpt)

#          crest y, z      throat y, z    half-w
PNECK = [(-0.280, 1.320, -0.560, 0.880, 0.215, 2.0, 2.2),
         (-0.400, 1.418, -0.650, 1.030, 0.192, 1.9, 2.2),
         (-0.510, 1.512, -0.705, 1.170, 0.160, 1.8, 2.2),
         (-0.615, 1.588, -0.750, 1.290, 0.132, 1.8, 2.2),
         (-0.705, 1.636, -0.780, 1.380, 0.110, 1.8, 2.2),
         (-0.780, 1.640, -0.820, 1.430, 0.066, 2.0, 2.0)]
PN = Loft(PNECK, [3, 3, 3, 3, 2], n=24)

#          forehead / nasal y, z   jaw y, z      half-w
PHEADR = [(-0.745, 1.682, -0.700, 1.560, 0.062, 2.0, 2.0),          # poll
          (-0.812, 1.670, -0.715, 1.462, 0.102, 2.1, 2.1),
          (-0.868, 1.614, -0.745, 1.386, 0.119, 2.15, 2.0),         # forehead / eyes / jowl
          (-0.915, 1.532, -0.800, 1.338, 0.109, 2.1, 1.9),
          (-0.955, 1.450, -0.860, 1.303, 0.089, 2.0, 1.9),
          (-0.990, 1.374, -0.910, 1.260, 0.077, 2.0, 2.0),          # narrow of the nose
          (-1.022, 1.304, -0.946, 1.210, 0.080, 2.1, 2.1),          # nostrils
          (-1.041, 1.252, -0.970, 1.174, 0.077, 2.2, 2.2),          # muzzle
          (-1.036, 1.208, -0.990, 1.164, 0.060, 2.0, 2.0),
          (-1.014, 1.178, -1.012, 1.176, 0.0, 2.0, 2.0)]
_HK, _HP = 1.07, (-0.745, 1.682)                                    # a pony's head is big for its body
PHEADR = [(_HP[0] + (r[0] - _HP[0]) * _HK, _HP[1] + (r[1] - _HP[1]) * _HK, _HP[0] + (r[2] - _HP[0]) * _HK, _HP[1] + (r[3] - _HP[1]) * _HK,
           r[4] * _HK) + r[5:] for r in PHEADR]
_PH0 = Loft(PHEADR, 1, n=8)
EYE_TH, EYE_F = 66.0, 2.05
P_EYE = _PH0.base(math.radians(EYE_TH), _PH0.tk(EYE_F))            # left eye, on the unsculpted surface
P_NOS = _PH0.base(math.radians(48.0), _PH0.tk(6.25))


def phead_sculpt(p, th, t):
    q = p.copy()
    s = 1.0 if p.x >= 0 else -1.0
    m = Vector((abs(p.x), p.y, p.z))
    d = (m - P_EYE).length
    q.x -= s * 0.0060 * g(d, 0.030)                                          # socket
    up = P_EYE + Vector((-0.012, -0.022, 0.040))
    q.x += s * 0.0110 * g((m - up).length, 0.034)                            # brow bone
    q.x += s * 0.0100 * g(m.y + 0.777, 0.064) * g(m.z - 1.423, 0.070) * clamp(abs(p.x) / 0.05)   # jowl
    q.x += s * 0.0080 * g((m - P_NOS).length, 0.030)                         # nostril flare
    q.x -= s * 0.0060 * g(m.y + 0.938, 0.043) * g(m.z - 1.380, 0.048) * clamp(abs(p.x) / 0.04)   # hollow above the mouth
    return q


PH = Loft(PHEADR, [2, 3, 3, 3, 3, 3, 3, 2, 1], n=36, sculpt=phead_sculpt)


def coat(p, dark=0.0):
    k = 0.5 + 0.5 * noise.noise(Vector((p.x * 5, p.y * 5, p.z * 5)))
    c = lerp3(CH_D, CH, clamp(0.55 + 0.6 * k - dark))
    c = lerp3(c, CH_L, 0.30 * sstep((0.86 - p.z) / 0.2) * sstep((p.z - 0.5) / 0.1))
    return c


def phead_col(p, th, t):
    c = coat(p)
    f = PH.tk
    c = lerp3(c, MUZZLE, 0.85 * sstep((t - f(5.6)) / (f(7.0) - f(5.6))))
    ax = abs(p.x)
    if math.cos(th) > 0.0:                                                    # blaze: star, stripe and snip
        u = clamp((t - f(1.3)) / (f(7.6) - f(1.3)))
        if 0.0 < u < 1.0:
            w = 0.020 + 0.022 * g(u - 0.12, 0.10) + 0.016 * g(u - 0.86, 0.12) - 0.008 * g(u - 0.55, 0.2)
            k = 1 - sstep((ax - w) / 0.008)
            k *= sstep(u / 0.05) * sstep((1 - u) / 0.05)
            c = lerp3(c, lerp3(SOCK, PINK, 0.55 * sstep((u - 0.84) / 0.1)), k)
    return c


def build_pony_body():
    b = B('pony', 41)
    PB.emit(b, 'hair', col_tt=lambda p, th, t: coat(p, 0.10 * sstep((p.z - 1.24) / 0.08)))
    # ---- royal saddle cloth + back pad + girth
    def t_at(y):
        lo, hi = 0.0, PB.K[-1]
        for _ in range(30):
            mid = (lo + hi) / 2
            if PB.ctr(mid).y < y:
                lo = mid
            else:
                hi = mid
        return lo

    ta, tb = t_at(-0.385), t_at(-0.115)
    us = [0.0, 0.04, 0.10] + [0.10 + 0.80 * i / 6 for i in range(1, 6)] + [0.90, 0.96, 1.0]
    vs = [0.0, 0.03, 0.08] + [0.08 + 0.84 * i / 12 for i in range(1, 12)] + [0.92, 0.97, 1.0]

    def sc(i, j):
        t = ta + (tb - ta) * us[i]
        th = math.radians(-74 + 148 * vs[j])
        off = 0.011
        if i in (0, len(us) - 1) or j in (0, len(vs) - 1):
            off = 0.001
        return PB.pt(th, t) + PB.nrm(th, t) * off

    rows = [[sc(i, j) for i in range(len(us))] for j in range(len(vs))]
    emit_grid(b, rows, 'cloth', BLUE, outward=lambda c: Vector((c.x, 0, c.z - 0.95)),
              facecol=lambda i, j: GOLD if (i in (1, len(us) - 3) or j in (1, len(vs) - 3)) else None)
    tg = t_at(-0.250)
    fg = None
    for i in range(len(PB.K) - 1):
        if PB.K[i] <= tg <= PB.K[i + 1]:
            fg = i + (tg - PB.K[i]) / (PB.K[i + 1] - PB.K[i])
    loft_band(b, PB, fg, -180, 180, 40, 0.014, 0.075, 0.012, 'leather', mul(LEA, 0.85))
    top = PB.on(0, fg, 0.018)
    b.blob((0.105, 0.085, 0.030), loc=top + Vector((0, 0, 0.004)), mat='leather', subdiv=2, color=mul(LEA, 1.15))
    for s in (1, -1):
        p = PB.on(s * 16, fg, 0.030)
        with b.at(p, rot=(0, s * 14, 0)):                                     # brass terrets
            b.cyl(0.006, 0.022, mat='gold', segs=6, bevel=0.001, color=WHITE)
            with b.at((0, 0, 0.040), rot=(0, 90, 0)):
                torus(b, 0.018, 0.0042, n=6, mat='gold', segs=12, color=WHITE)
        p = PB.on(s * 96, fg, 0.022)
        with b.at(p, aim(PB.nrm(math.radians(s * 96), PB.tk(fg)))):          # girth buckles
            b.box((0.060, 0.008, 0.050), mat='gold', bevel=0.004, grain=None, color=WHITE)
            b.box((0.036, 0.010, 0.028), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.7))
    # ---- padded collar around the base of the neck, brass hames
    FC = 0.62
    path, rad, hame = [], [], {1: None, -1: None}
    nC = 28

    def collar_pt(th, fwd=0.0, out=0.0):
        t = PN.tk(FC)
        n = PN.nrm(th, t)
        ax = (PN.pt(th, t + 0.01) - PN.pt(th, t - 0.01)).normalized()       # up the neck
        r = 0.050 + 0.010 * (0.5 - 0.5 * math.cos(th))                        # fuller at the bottom
        return PN.pt(th, t) + n * (r * 0.50 + out * r) + ax * (fwd * r), r

    for i in range(nC + 1):
        q, r = collar_pt(2 * math.pi * i / nC)
        path.append(q)
        rad.append(r)
    b.tube(path, rad, mat='leather', segs=10, caps=False, color=lambda co: mul(LEA, 0.60 + 0.12 * noise.noise(co * 12)))
    for s in (1, -1):
        pts = [collar_pt(math.radians(s * (10 + 160 * k / 16)), 0.62, 0.74)[0] for k in range(17)]
        top_ = pts[0] + Vector((s * 0.006, -0.016, 0.052))
        b.tube([top_] + pts, 0.0125, mat='gold', segs=7, color=WHITE)
        b.blob(0.019, loc=top_, mat='gold', subdiv=2, color=WHITE)
        hame[s] = pts[9]
    a_, c_ = collar_pt(math.radians(170), 0.62, 0.74)[0], collar_pt(math.radians(-170), 0.62, 0.74)[0]
    b.tube([a_, (a_ + c_) / 2 + Vector((0, -0.004, -0.004)), c_], 0.008, mat='gold', segs=6, color=WHITE)
    a_, c_ = collar_pt(math.radians(10), 0.62, 0.74)[0], collar_pt(math.radians(-10), 0.62, 0.74)[0]
    ribbon(b, [a_, (a_ + c_) / 2 + Vector((0, -0.006, 0.010)), c_], Vector((0, -0.5, 1)), 0.026, 0.008, 'leather', mul(LEA, 0.8), segs=6)
    # ---- traces to a swingletree behind the pony
    for s in (1, -1):
        h = hame[s]
        b.blob(0.020, loc=h, mat='gold', subdiv=1, color=WHITE)
        ye = P_HITCH.y - 0.075
        ctrl = [h] + [Vector((s * x_, y_, h.z + (0.852 - h.z) * (y_ - h.y) / (ye - h.y))) for x_, y_ in
                      ((0.300, -0.575), (0.338, -0.47), (0.352, -0.34), (0.388, -0.10), (0.396, 0.25), (0.386, 0.60), (0.352, 0.88), (0.330, ye))]
        pts = smooth_path(ctrl, 4)
        ribbon(b, pts, Vector((s, 0, 0.1)), 0.046, 0.010, 'leather', mul(LEA, 0.8), segs=8)
        # trace carrier hanging from the back band
        a = PB.on(s * 84, fg, 0.016)
        cpt = Vector((s * 0.372, -0.245, h.z + (0.852 - h.z) * (-0.245 - h.y) / (ye - h.y)))
        ribbon(b, [a, (a + cpt) / 2 + Vector((s * 0.012, 0, 0)), cpt + Vector((0, 0, -0.03))], Vector((s, 0, 0)), 0.030, 0.008, 'leather', mul(LEA, 0.8), segs=6)
        e = pts[-1]
        ring = [(e.x + 0.0, e.y + 0.028 - 0.028 * math.cos(a_), e.z + 0.028 * math.sin(a_)) for a_ in [i * 2 * math.pi / 10 for i in range(11)]]
        b.tube(ring, 0.0055, mat='metal', segs=6, caps=False, color=WHITE)
    yb = P_HITCH.y - 0.045
    b.tube([(-0.39, yb, 0.850), (-0.20, yb + 0.006, 0.852), (0, yb + 0.010, 0.853), (0.20, yb + 0.006, 0.852), (0.39, yb, 0.850)],
           [0.022, 0.028, 0.032, 0.028, 0.022], mat='wood_dark', segs=8, color=WHITE)
    for sx in (-0.33, 0.33, 0.0):
        b.lathe([(0.026 + (0.008 if sx == 0 else 0), -0.022), (0.031 + (0.008 if sx == 0 else 0), -0.019), (0.031 + (0.008 if sx == 0 else 0), 0.019), (0.026 + (0.008 if sx == 0 else 0), 0.022)],
                loc=(sx, yb + (0.010 if sx == 0 else 0.001), 0.851), rot=(0, 90, 0), mat='metal', segs=10, color=WHITE)
    ring = [(0.0, yb + 0.062 + 0.030 * math.cos(a_), 0.851 + 0.030 * math.sin(a_)) for a_ in [i * 2 * math.pi / 12 for i in range(13)]]
    b.tube(ring, 0.0065, mat='metal', segs=6, caps=False, color=WHITE)
    return b.build(sharp_angle=60)


def pony_ear(b):
    """Left ear in its own frame: base at the origin, tip along +Z, cup opening toward -Y."""
    rows = [(-0.016, -0.02, 0.020, -0.02, 0.026), (-0.020, 0.012, 0.022, 0.012, 0.036), (-0.020, 0.050, 0.020, 0.050, 0.038),
            (-0.016, 0.090, 0.014, 0.092, 0.030), (-0.009, 0.126, 0.007, 0.128, 0.016), (-0.002, 0.150, 0.000, 0.150, 0.0)]

    def sc(p, th, t):
        q = p.copy()
        if math.cos(th) > 0 and p.z > 0:
            w = 0.040
            q.y += 0.024 * max(0.0, 1 - (p.x / w) ** 2) * math.sin(math.pi * clamp(p.z / 0.150)) ** 0.7
        return q

    L = Loft(rows, [1, 2, 2, 2, 1], n=14, sculpt=sc)

    def col(p, th, t):
        c = coat(Vector((p.x, p.y, p.z + 1.2)), 0.1)
        if math.cos(th) > 0.25 and p.z > 0.005:
            c = lerp3(c, lerp3(MUZZLE, PINK, 0.35), 0.85 * sstep((math.cos(th) - 0.25) / 0.3))
        return c

    L.emit(b, 'hair', col_tt=col)


def build_pony_head():
    b = B('pony_head', 43)
    with b.at(-P_HEAD):
        PN.emit(b, 'hair', col_tt=lambda p, th, t: coat(p, 0.08 * sstep((math.cos(th) - 0.7) / 0.3)))
        PH.emit(b, 'hair', col_tt=phead_col)
        for s in (1, -1):
            with b.at(scale=(s, 1, 1)):
                # ---- eye: big dark globe, lids, a lash fringe
                th, t = math.radians(EYE_TH), PH.tk(EYE_F)
                n = PH.nrm(th, t)
                ps = PH.pt(th, t)
                d = (PH.pt(th, t + 0.02) - PH.pt(th, t - 0.02)).normalized()       # toward the nose
                u = n.cross(d).normalized()
                if u.z < 0:
                    u = -u
                R = 0.0265
                ec = ps - n * (R - 0.0115)
                b.blob(R, loc=ec, mat='eye', subdiv=2, color=WHITE)
                b.blob((0.0042, 0.0042, 0.0016), loc=ec + n * (R - 0.0006) + u * 0.008 - d * 0.006, rot=aim(n), mat='paint', subdiv=1, color=WHITE)
                for upper in (True, False):
                    pts, rad = [], []
                    for k in range(13):
                        a = math.pi * k / 12
                        hgt = (0.0180 if upper else -0.0140) * math.sin(a) ** 0.75
                        q = ps + d * (-math.cos(a) * 0.0310 + 0.002) + u * (hgt + 0.003 * math.cos(a))
                        dd = (q - ec)
                        q = ec + dd.normalized() * max(dd.length, R + 0.0010)
                        pts.append(q)
                        rad.append((0.0026 if upper else 0.0022) + (0.0040 if upper else 0.0020) * math.sin(a))
                    b.tube(pts, rad, mat='hair', segs=6, color=mul(CH_D, 0.42) if upper else mul(CH_D, 0.70))
                # ---- nostril
                th2, t2 = math.radians(47.0), PH.tk(6.30)
                n2 = PH.nrm(th2, t2)
                b.blob((0.0120, 0.0090, 0.0210), loc=PH.pt(th2, t2) - n2 * 0.0040, rot=(-28, 22, 0), mat='hair', subdiv=2, color=mul(MUZZLE, 0.20))
                # ---- mouth line
                pts = [PH.on(th_, f_, -0.0006) for th_, f_ in ((176, 7.75), (150, 7.55), (128, 7.15), (120, 6.6), (118, 6.05), (120, 5.6))]
                b.tube(pts, [0.0030, 0.0036, 0.0036, 0.0032, 0.0026, 0.0012], mat='hair', segs=5, color=mul(MUZZLE, 0.25))
                # ---- ear
                base = PH.on(38, 0.62, -0.006)
                with b.at(base, rot=(-14, 20, -26)):
                    pony_ear(b)
                # ---- bridle: cheek piece, bit ring, rosette
                loft_band(b, PH, 1.30, 104, 112, 10, 0.004, 0.022, 0.007, 'leather', mul(LEA, 0.8), f1=6.55)
                br = PH.on(112, 6.62, 0.008)
                nb = PH.nrm(math.radians(112), PH.tk(6.62))
                with b.at(br, aim(nb)):
                    with b.at(rot=(90, 0, 0)):
                        torus(b, 0.022, 0.0042, n=6, mat='gold', segs=12, color=WHITE)
                ro = PH.on(100, 1.32, 0.008)
                with b.at(ro, aim(PH.nrm(math.radians(100), PH.tk(1.32)))):
                    b.lathe([(0.021, 0.0), (0.021, 0.004), (0.014, 0.009), (0, 0.011)], rot=(90, 0, 0), mat='gold', segs=12, color=WHITE)
                    b.blob((0.008, 0.005, 0.008), loc=(0, -0.010, 0), mat='cloth', subdiv=1, color=BLUE)
        # ---- royal brow band: blue with gold diamonds
        pts, nr = loft_band(b, PH, 1.30, -100, 100, 20, 0.004, 0.034, 0.008, 'cloth', BLUE)
        for k in range(2, 19, 2):
            with b.at(pts[k] + nr[k] * 0.004, aim(nr[k])):
                b.box((0.017, 0.006, 0.017), rot=(0, 45, 0), mat='gold', bevel=0.002, segs=1, grain=None, color=WHITE)
        for off_ in (-0.019, 0.019):
            tdir = [(pts[min(k + 1, 20)] - pts[max(k - 1, 0)]).normalized().cross(nr[k]).normalized() for k in range(21)]
            b.tube([pts[k] + tdir[k] * off_ + nr[k] * 0.003 for k in range(21)], 0.0036, mat='gold', segs=5, color=WHITE)
        # crown piece behind the ears, throat lash, noseband
        loft_band(b, PH, 0.50, -108, 108, 16, 0.005, 0.024, 0.007, 'leather', mul(LEA, 0.8))
        loft_band(b, PH, 1.55, 100, 260, 14, 0.004, 0.018, 0.006, 'leather', mul(LEA, 0.8))
        loft_band(b, PH, 4.75, -180, 180, 24, 0.004, 0.026, 0.008, 'leather', mul(LEA, 0.8))
        # ---- forelock
        rng = b.rng
        for k, th_ in enumerate((-30, -17, -5, 7, 19, 31)):
            ln = 2.35 + 0.5 * rng.random() - 0.012 * abs(th_)
            pts = [PH.on(th_ * 0.5, 0.05, 0.016)] + [PH.on(th_ * (0.7 + 0.22 * i), 0.3 + (ln - 0.3) * i / 4, 0.020 - 0.003 * i) for i in range(5)]
            b.tube(pts, [0.016, 0.024, 0.025, 0.021, 0.014, 0.004], mat='hair', segs=6, color=FLAX_D, color_top=FLAX_L, jitter=0.06)
        # ---- mane: a ridge along the crest and heavy locks falling on the near (left) side
        crest = [PN.on(0, f_, 0.012) for f_ in (0.55, 1.0, 1.6, 2.2, 2.8, 3.4, 4.0, 4.5)]
        b.tube(crest + [Vector((0, -0.755, 1.680))], [0.030, 0.036, 0.036, 0.034, 0.032, 0.030, 0.028, 0.026, 0.020], mat='hair', segs=8, color=FLAX_D)
        nl = 15
        for k in range(nl):
            f_ = 0.80 + 3.75 * k / (nl - 1)
            c0 = PN.on(0, f_, 0.026)
            L = (0.36 - 0.11 * (k / (nl - 1)) ** 1.5) * (0.86 + 0.28 * rng.random()) * (0.72 if k < 2 else 1.0)
            sway = rng.uniform(-0.035, 0.035)
            pts, nrm_ = [c0 + Vector((-0.004, 0, 0.002))], [Vector((0.4, 0, 1))]
            m = 6
            for i in range(1, m + 1):
                v = i / m
                z = c0.z - L * v
                y = c0.y + sway * v * v + 0.020 * v
                x = max(PN.side_x(y, max(z, 0.0)), 0.02) if z > 1.02 else 0.0
                x = max(x, PN.side_x(y, c0.z - L * min(v, 0.55)) * (1.0 - 0.15 * v)) + 0.020 + 0.006 * math.sin(k * 1.7 + i)
                if i == 1:
                    x = min(x, 0.075)
                pts.append(Vector((x, y, z)))
                nrm_.append(Vector((1, 0, 0.35 * (1 - v))))
            ribbon(b, pts, nrm_, lambda t: 0.050 + 0.045 * math.sin(math.pi * clamp(t * 0.80 + 0.12)) ** 0.8 * (1 - 0.75 * t ** 3) - 0.040 * t ** 4, 0.024,
                   'hair', lerp3(FLAX_D, FLAX, rng.random()), segs=6, color_top=FLAX_L)
        for k in range(7):                                                   # short wisps on the off side
            f_ = 1.1 + 3.2 * k / 6
            c0 = PN.on(0, f_, 0.024)
            L = 0.12 + 0.05 * rng.random()
            pts = [c0, Vector((-max(PN.side_x(c0.y, c0.z - L * 0.5), 0.02) - 0.016, c0.y + 0.01, c0.z - L * 0.5)),
                   Vector((-max(PN.side_x(c0.y, c0.z - L), 0.02) - 0.014, c0.y + 0.02, c0.z - L))]
            ribbon(b, pts, Vector((-1, 0, 0.3)), lambda t: 0.060 * (1 - 0.8 * t * t), 0.020, 'hair', FLAX_D, segs=6, color_top=FLAX)
    return b.build(sharp_angle=70)


#           front y, z      back y, z    half-w
LEG_F = [(-0.610, 1.030, -0.300, 1.030, 0.098, 2.0, 2.0),
         (-0.596, 0.880, -0.322, 0.880, 0.100, 2.1, 2.1),
         (-0.566, 0.740, -0.376, 0.755, 0.088, 2.1, 2.0),
         (-0.540, 0.590, -0.410, 0.590, 0.067, 2.0, 2.0),
         (-0.527, 0.470, -0.428, 0.470, 0.055, 2.0, 2.0),
         (-0.536, 0.405, -0.424, 0.405, 0.058, 2.2, 2.0),          # knee
         (-0.523, 0.340, -0.433, 0.340, 0.047, 2.0, 2.0),
         (-0.517, 0.245, -0.436, 0.245, 0.041, 2.0, 2.0),          # cannon
         (-0.526, 0.165, -0.424, 0.168, 0.050, 2.0, 2.0),          # fetlock
         (-0.550, 0.108, -0.452, 0.114, 0.050, 2.0, 2.0),          # pastern
         (-0.566, 0.078, -0.458, 0.078, 0.057, 2.0, 2.0)]
LEG_B = [(0.250, 1.070, 0.745, 1.050, 0.118, 2.0, 2.0),
         (0.262, 0.910, 0.760, 0.925, 0.124, 2.2, 2.1),
         (0.305, 0.785, 0.752, 0.805, 0.110, 2.1, 2.0),            # stifle
         (0.420, 0.665, 0.736, 0.685, 0.083, 2.0, 2.0),            # gaskin
         (0.545, 0.565, 0.732, 0.575, 0.063, 2.0, 2.0),
         (0.602, 0.492, 0.750, 0.505, 0.057, 2.0, 2.2),            # hock
         (0.617, 0.420, 0.728, 0.420, 0.048, 2.0, 2.0),
         (0.616, 0.275, 0.702, 0.275, 0.041, 2.0, 2.0),            # cannon
         (0.600, 0.170, 0.702, 0.172, 0.050, 2.0, 2.0),            # fetlock
         (0.574, 0.110, 0.676, 0.116, 0.050, 2.0, 2.0),
         (0.556, 0.078, 0.668, 0.078, 0.057, 2.0, 2.0)]


def _stocky(rows, kw=1.20, kd=1.16):
    out = []
    for i, r in enumerate(rows):
        if i < 2:
            out.append(r)
            continue
        c = (r[0] + r[2]) / 2
        out.append((c + (r[0] - c) * kd, r[1], c + (r[2] - c) * kd, r[3], r[4] * kw) + tuple(r[5:]))
    return out


LEG_F, LEG_B = _stocky(LEG_F), _stocky(LEG_B)


def leg_col(p, th, t):
    c = coat(p, 0.10 + 0.20 * sstep((0.62 - p.z) / 0.2))
    k = sstep((0.335 - p.z + 0.03 * math.sin(th * 3)) / 0.07)
    return lerp3(c, SOCK, k)


def build_pony_leg(name, rows, pivot, s, seed):
    b = B(name, seed)
    with b.at((0, -pivot.y, -pivot.z)):
        L = Loft(rows, [2, 2, 2, 2, 2, 2, 2, 2, 2, 1], n=16)
        L.emit(b, 'hair', col_tt=leg_col)
        # hoof
        r = rows[-1]
        fy, by = r[0], r[2]
        hoof = Loft([(fy + 0.004, 0.084, by - 0.004, 0.084, 0.055), (fy - 0.006, 0.068, by + 0.004, 0.070, 0.061),
                     (fy - 0.040, 0.004, by + 0.016, 0.004, 0.074), (fy - 0.037, 0.0, by + 0.014, 0.0, 0.071)], [1, 2, 1], n=16)
        hoof.emit(b, 'paint', color=lambda co: lerp3(HOOF, mul(HOOF, 1.5), clamp(co.z / 0.08)))
        # feather: long silky hair around the fetlock, heaviest at the back
        rng = b.rng
        cy = (rows[-3][0] + rows[-3][2]) / 2
        for k in range(10):
            a = math.radians(48 + 264 * k / 9)                                 # 0 = front, 180 = back
            dx, dy = math.sin(a), -math.cos(a)
            back = 0.5 - 0.5 * math.cos(a)
            r0, r1 = 0.054, 0.080 + 0.034 * back
            z0 = 0.215 + 0.04 * back + rng.uniform(-0.01, 0.01)
            z1 = 0.050 - 0.030 * back + rng.uniform(0.0, 0.012)
            cyb = (rows[-1][0] + rows[-1][2]) / 2
            pts = [Vector((dx * r0 * 0.8, cy + dy * r0, z0)),
                   Vector((dx * (r0 + 0.018), cy + dy * (r0 + 0.018) * 1.05, z0 - (z0 - z1) * 0.38)),
                   Vector((dx * r1 * 0.96, (cy + cyb) / 2 + dy * r1, z0 - (z0 - z1) * 0.76)),
                   Vector((dx * r1 * 1.04, cyb + dy * r1 * 1.08, z1))]
            b.tube(pts, [0.016, 0.030, 0.027, 0.006], mat='hair', segs=5, color=lerp3(SOCK, FLAX, 0.35 * rng.random()), color_top=lerp3(SOCK, FLAX_L, 0.6), jitter=0.04)
    return b.build(sharp_angle=60)


def build_pony_tail():
    b = B('pony_tail', 47)
    rng = b.rng
    b.tube([(0, -0.110, 0.030), (0, -0.030, 0.020), (0, 0.040, -0.012), (0, 0.085, -0.060), (0, 0.105, -0.130)], [0.040, 0.052, 0.050, 0.044, 0.034], mat='hair', segs=8, color=CH, color_top=FLAX_D)
    n = 11
    for k in range(n):
        a = 2 * math.pi * k / (n - 1) if k < n - 1 else 0.0
        rr = 0.0 if k == n - 1 else 1.0
        dx, dy = math.sin(a) * rr, math.cos(a) * rr
        L = 0.84 + rng.uniform(-0.06, 0.08)
        pts = [Vector((dx * 0.012, 0.030 + dy * 0.010, -0.010)),
               Vector((dx * 0.040, 0.095 + dy * 0.022, -0.110)),
               Vector((dx * 0.066, 0.125 + dy * 0.040, -0.30)),
               Vector((dx * 0.078, 0.120 + dy * 0.048 + rng.uniform(-0.01, 0.01), -0.55)),
               Vector((dx * 0.066 + rng.uniform(-0.01, 0.01), 0.100 + dy * 0.044, -0.76)),
               Vector((dx * 0.040, 0.085 + dy * 0.030, -L - 0.06))]
        b.tube(pts, [0.026, 0.040, 0.048, 0.050, 0.040, 0.007], mat='hair', segs=6, color=lerp3(FLAX_D, FLAX, rng.random()), color_top=FLAX_L, jitter=0.05)
    return b.build(sharp_angle=70)


def build_pony():
    root = build_pony_body()
    kit.set_parent(build_pony_head(), root, P_HEAD)
    for name, rows, piv, s in (('pony_leg_fl', LEG_F, P_LEG_F, 1), ('pony_leg_fr', LEG_F, P_LEG_F, -1),
                               ('pony_leg_bl', LEG_B, P_LEG_B, 1), ('pony_leg_br', LEG_B, P_LEG_B, -1)):
        leg = build_pony_leg(name, rows, piv, s, 50 + len(name) + s)
        kit.set_parent(leg, root, (s * piv.x, piv.y, piv.z))
    kit.set_parent(build_pony_tail(), root, P_TAIL)
    kit.marker('pony_hitch', P_HITCH, parent=root)
    return root


# ================================================================ BUILD + REPORT
BUILD = {'all': ('peddler', 'pony'), 'peddler': ('peddler',), 'face': ('peddler',), 'pony': ('pony',), 'wagon': ('pony',)}[WHAT]
roots = {}
if 'peddler' in BUILD:
    roots['peddler'] = build_peddler()
if 'pony' in BUILD:
    roots['pony'] = build_pony()
bpy.context.view_layer.update()
for name, r in roots.items():
    objs = kit._descend([r])
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
    lo = [round(min(p[i] for p in pts), 3) for i in range(3)]
    hi = [round(max(p[i] for p in pts), 3) for i in range(3)]
    print('ASSET', name, 'TRIS', kit.tri_count(objs), {o.name: kit.tri_count([o]) for o in objs if o.type == 'MESH'})
    print('  BBOX', lo, hi)
    print('  MATERIALS', sorted({m.name for o in objs if o.type == 'MESH' for m in o.data.materials}))
    for o in objs:
        print('  PIVOT', o.name, o.type, 'parent', o.parent.name if o.parent else None, 'local', [round(v, 4) for v in o.location],
              'world', [round(v, 4) for v in o.matrix_world.translation])


# ================================================================ PREVIEWS
def shot(name, center, radius, az=0, el=10, size=(900, 900), floor=True, lens=70):
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    c = Vector(center)
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = lens
    d = radius / math.tan(math.atan(18.0 / lens) * 0.92)
    a, e = math.radians(az), math.radians(el)
    cam.location = c + Vector((math.sin(a) * math.cos(e) * d, -math.cos(a) * math.cos(e) * d, math.sin(e) * d))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start = 0.02
    cam.data.clip_end = d * 4 + 10
    sc.camera = cam
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 3.6
    sun.data.color = (1.0, 0.9, 0.76)
    sun.data.angle = math.radians(6)
    sun.rotation_euler = Euler((math.radians(52), 0, a + math.radians(40)))
    extra = [cam, sun]
    if floor:
        fm = bpy.data.meshes.new('_pv_floor')
        fb = bmesh.new()
        bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=24)
        fb.to_mesh(fm)
        fb.free()
        fl = bpy.data.objects.new('_pv_floor', fm)
        fl.location = (0, 0, -0.001)
        sc.collection.objects.link(fl)
        fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
        try:
            fmat.use_nodes = True
            bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            bs.inputs['Base Color'].default_value = (0.26, 0.36, 0.17, 1)
            bs.inputs['Roughness'].default_value = 0.9
        except Exception:
            pass
        fm.materials.append(fmat)
        extra.append(fl)
    w = sc.world or bpy.data.worlds.new('_pv_world')
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.6, 0.72, 0.88, 1)
        bg.inputs[1].default_value = 1.0
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
    sc.render.filepath = os.path.join(PREV, name + '.png')
    bpy.ops.render.render(write_still=True)
    for o in extra:
        bpy.data.objects.remove(o)


def only(*rs):
    fam = kit._descend([r for r in rs if r is not None])
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.hide_render = o not in fam


# ================================================================ EXPORT (before the preview scene gets extra objects)
if '--no-export' not in ARGV and WHAT == 'all':
    kit.export_glb(os.path.join(ROOT, 'public', 'models', 'folk.glb'), [roots['peddler'], roots['pony']])

if PREV:
    if '--cull' in ARGV:
        for m in bpy.data.materials:
            m.use_backface_culling = True
    ped, pony = roots.get('peddler'), roots.get('pony')
    if ped and WHAT in ('all', 'peddler', 'face'):
        only(ped)
        FOCUS = W_NECK + (CHIN_OFF + Vector((0, -0.03, 0.135))) * HEAD_K
        shot('wren_face_front', FOCUS, 0.19, az=0, el=0, floor=False)
        shot('wren_face_34', FOCUS, 0.19, az=35, el=5, floor=False)
        shot('wren_face_side', FOCUS, 0.19, az=90, el=0, floor=False)
        shot('wren_face_34b', FOCUS, 0.19, az=-30, el=-8, floor=False)
        if WHAT != 'face':
            c, r = (0, 0, 0.87), 0.96
            shot('wren_front', c, r, az=0, el=5)
            shot('wren_34', c, r, az=35, el=10)
            shot('wren_side', c, r, az=90, el=5)
            shot('wren_back', c, r, az=180, el=8)
            shot('wren_bust', (0, 0, 1.28), 0.45, az=-20, el=6, floor=False)
            shot('wren_apron', (0, -0.1, 0.80), 0.40, az=12, el=12, floor=False)
            shot('wren_game_3m', (0, 0, 1.15), 0.75, az=10, el=3, floor=True, lens=28, size=(900, 700))
    if pony and WHAT in ('all', 'pony'):
        only(pony)
        c, r = (0, -0.12, 0.86), 1.22
        shot('pony_side', c, r, az=90, el=4, size=(1100, 900))
        shot('pony_34', c, r, az=38, el=10, size=(1100, 900))
        shot('pony_front', c, r, az=0, el=6)
        shot('pony_back34', c, r, az=140, el=14, size=(1100, 900))
        shot('pony_head_side', (0, -0.92, 1.45), 0.42, az=80, el=4, floor=False)
        shot('pony_head_34', (0, -0.92, 1.45), 0.42, az=35, el=6, floor=False)
        shot('pony_head_front', (0, -0.92, 1.45), 0.42, az=0, el=4, floor=False)
        shot('pony_game_3m', (0, -0.2, 1.0), 1.3, az=40, el=6, floor=True, lens=28, size=(900, 700))
    if pony and WHAT in ('all', 'wagon'):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, 'public', 'models', 'royal.glb'))
        new = [o for o in bpy.data.objects if o not in before]
        wagon = next(o for o in new if o.name.split('.')[0] == 'wagon')
        wfam = kit._descend([wagon])
        for o in new:
            o.hide_render = o not in wfam
        for o in bpy.data.objects:
            if o.type == 'MESH' and o not in new:
                o.hide_render = o not in kit._descend([pony])
        tip_y = -2.72 - 0.11
        pony.location = (0, tip_y - P_HITCH.y, 0)
        bpy.context.view_layer.update()
        shot('pony_wagon_34', (0, -1.75, 1.05), 3.3, az=52, el=12, size=(1300, 850))
        shot('pony_wagon_side', (0, -1.75, 1.05), 3.3, az=90, el=5, size=(1300, 850))
        if ped:
            ped.location = (1.6, -3.4, 0)
            ped.rotation_euler = (0, 0, math.radians(-50))
            for o in kit._descend([ped]):
                o.hide_render = False
            shot('folk_scene', (0.3, -2.2, 1.05), 3.3, az=40, el=9, size=(1300, 850), lens=50)
        pony.location = (0, 0, 0)
