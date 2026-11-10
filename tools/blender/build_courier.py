"""Royal courier NPC (stands by the supply wagon) -> public/models/courier.glb

blender --background --factory-startup --python tools/blender/build_courier.py -- <preview_dir>

Faces Blender -Y, character LEFT is +X, origin at the feet. Natural-ish stylised proportions
(about 6.7 heads). The head is a lofted surface (tilted rings between a front and a back profile
curve) with sculpted displacement for sockets, brow, nose, cheeks, lips and chin.

Objects (identity rotation at rest, mesh built around its own pivot):
  courier                 root mesh: torso, tabard, belt, legs, boots
    courier_head          skull + neck + face + hair + cap      (pivot: neck base)
      courier_eye         marker between the eyes
    courier_arm_l / _r    upper arm                               (pivot: shoulder)
      courier_forearm_l/_r  forearm + cuff + hand                 (pivot: elbow)
        courier_hand_r    marker in the right palm (child of courier_forearm_r)
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
PREV = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1 else None
if PREV:
    PREV = os.path.abspath(PREV)             # Blender resolves relative render paths against the drive root
    os.makedirs(PREV, exist_ok=True)

kit.reset()

# ---------------------------------------------------------------- palette (linear)
SKIN = srgb(230, 174, 140)
SKIN_D = srgb(214, 150, 120)
BLUSH = srgb(226, 112, 104)
LIP = srgb(186, 98, 92)
MOUTH = srgb(92, 40, 36)
HAIR = srgb(112, 68, 40)
HAIR_D = srgb(78, 46, 28)
HAIR_L = srgb(150, 100, 62)
GREY = srgb(168, 158, 148)
IRIS = srgb(74, 122, 150)
IRIS_D = srgb(34, 62, 88)
WHITE = (1.0, 1.0, 1.0)
EYEWHITE = srgb(244, 240, 232)
BLUE = srgb(38, 62, 128)
BLUE_D = srgb(26, 44, 96)
BLUE_L = srgb(56, 84, 156)
GOLD = srgb(214, 168, 64)
GOLD_D = srgb(170, 126, 44)
CREAM = srgb(236, 226, 200)
CREAM_D = srgb(206, 192, 162)
TROUSER = srgb(58, 52, 54)
TROUSER_L = srgb(74, 66, 66)
PAPER = srgb(240, 228, 196)
RED = srgb(170, 44, 40)
LEA = (1.0, 0.95, 0.9)          # 'leather' already carries the brown; vertex colour only tints


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
    """signed power"""
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
        Bn = T.cross(N).normalized()
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
    color: tuple or fn(co). facecol(i, j) -> colour or None gives crisp per-face colours."""
    t = b._new()
    uv, col, _ = b._layers(t)
    V = [[t.verts.new(p) for p in row] for row in rows]
    nj, ni = len(V), len(V[0])
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
    for pole, row in ((pole_start, V[0]), (pole_end, V[-1])):
        if pole is None:
            continue
        pv = t.verts.new(pole)
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
                c = color(l.vert.co) if callable(color) else color
            l[col] = (c[0], c[1], c[2], 1.0)
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


# ================================================================ PROPORTIONS (world metres)
NECK_PIVOT = Vector((0.0, 0.0, 1.445))
CHIN_OFF = Vector((0.0, -0.012, 0.045))      # chin-space origin, local to the head pivot (before HEAD_K)
HEAD_K = 1.04                                # head built at this scale about the neck pivot
SHOULDER = Vector((0.180, 0.0, 1.375))       # +X = character left
UPPER_L, FORE_L = 0.285, 0.25
U_DIR = Vector((math.sin(math.radians(10)), 0.0, -math.cos(math.radians(10)))).normalized()
F_DIR = Vector((math.sin(math.radians(4)), -math.sin(math.radians(17)), -1.0)).normalized()
ELBOW = U_DIR * UPPER_L                      # local to the arm (left side; mirror x for right)
WRIST = F_DIR * FORE_L                       # local to the forearm


# ================================================================ HEAD  (chin space: chin z=0, crown z=0.264)
EX, EZ = 0.0330, 0.134                       # eye centre x / z
#        front y, z      back y, z     half-w  pf    pb
HC = [(-0.036, -0.095, 0.058, -0.075, 0.050, 2.0, 2.0),    # neck base (inside the collar)
      (-0.038, -0.050, 0.060, -0.030, 0.0465, 2.0, 2.0),
      (-0.041, -0.018, 0.062, 0.005, 0.046, 2.0, 2.0),     # throat
      (-0.056, -0.003, 0.064, 0.028, 0.0455, 1.9, 2.0),    # under the jaw
      (-0.092, 0.000, 0.068, 0.046, 0.056, 1.70, 2.0),     # jaw line
      (-0.100, 0.016, 0.074, 0.060, 0.061, 1.78, 2.0),     # chin
      (-0.101, 0.040, 0.084, 0.076, 0.0665, 1.92, 2.0),
      (-0.102, 0.060, 0.092, 0.090, 0.0715, 2.05, 2.1),    # mouth
      (-0.102, 0.082, 0.099, 0.108, 0.075, 2.15, 2.1),     # nose base
      (-0.101, 0.108, 0.104, 0.130, 0.078, 2.25, 2.1),     # cheek
      (-0.100, 0.134, 0.106, 0.154, 0.081, 2.3, 2.1),      # eyes
      (-0.103, 0.157, 0.105, 0.176, 0.083, 2.3, 2.1),      # brow
      (-0.102, 0.188, 0.098, 0.202, 0.083, 2.25, 2.1),     # forehead
      (-0.090, 0.222, 0.082, 0.228, 0.076, 2.1, 2.05),
      (-0.062, 0.249, 0.058, 0.249, 0.060, 2.0, 2.0),
      (-0.028, 0.261, 0.032, 0.260, 0.034, 2.0, 2.0),
      (0.003, 0.264, 0.003, 0.264, 0.0, 2.0, 2.0)]
HSUB = [1, 2, 2, 3, 3, 4, 4, 4, 5, 5, 4, 4, 2, 2, 2, 1]
_k = [0.0]
for _i in range(1, len(HC)):
    a, c = HC[_i - 1], HC[_i]
    _k.append(_k[-1] + 0.5 * (math.hypot(c[0] - a[0], c[1] - a[1]) + math.hypot(c[2] - a[2], c[3] - a[3])))
HK = _k
HSP = Spline(HK, HC)
H_TS = []
for _i in range(len(HC) - 1):
    for _s in range(HSUB[_i]):
        H_TS.append(HK[_i] + (HK[_i + 1] - HK[_i]) * _s / HSUB[_i])
H_TS.append(HK[-1])


def head_base(th, t):
    yf, zf, yb, zb, w, pf, pb = HSP(t)
    c, s = math.cos(th), math.sin(th)
    cy, cz = (yf + yb) / 2, (zf + zb) / 2
    a = math.hypot(yb - yf, zb - zf) / 2
    ey, ez = ((yb - yf) / (2 * a), (zb - zf) / (2 * a)) if a > 1e-6 else (1.0, 0.0)
    p = pf if c > 0 else pb
    x = max(w, 0.0) * sp(s, 2 / p)
    al = -a * sp(c, 2 / p)
    return Vector((x, cy + al * ey, cz + al * ez))


def face_features(p, th):
    """Sculpt: displace the base surface (mostly along y) for the facial forms."""
    c = math.cos(th)
    wf = sstep((c - 0.05) / 0.45)
    x, z = p.x, p.z
    ax = abs(x)
    sx = 1.0 if x >= 0 else -1.0
    dy = 0.0
    if wf > 0:
        # eye sockets + brow ridge
        dy += 0.0125 * g(ax - EX, 0.023) * g(z - EZ, 0.016)
        dy -= 0.0050 * g(z - 0.157, 0.011) * math.exp(-(x / 0.060) ** 4)
        dy += 0.0020 * g(x, 0.012) * g(z - 0.142, 0.010)             # nasion dip
        # nose: bridge -> tip, steep underside, wings
        zN, zT = 0.146, 0.090
        if z >= zT:
            tt = clamp((zN - z) / (zN - zT))
            prot = (0.0035 + 0.0255 * tt ** 1.2) if z <= zN else 0.0035 * g(z - zN, 0.012)
            sig = 0.0080 + 0.0050 * tt
        else:
            prot = 0.029 * (1 - sstep((zT - z) / 0.013))
            sig = 0.0130
        dy -= prot * math.exp(-(ax / sig) ** 2.4)
        dy -= 0.0090 * g(ax - 0.0160, 0.0064) * g(z - 0.0855, 0.0075)   # alae
        dy -= 0.0050 * g(x, 0.0115) * g(z - 0.092, 0.009)                # ball of the tip
        # smiling cheeks, muzzle, lips, chin
        dy -= 0.0055 * g(ax - 0.041, 0.021) * g(z - 0.097, 0.019)
        dy -= 0.0040 * g(x, 0.026) * g(z - 0.067, 0.014)
        dy -= 0.0045 * g(x, 0.0165) * g(z - 0.0485, 0.0065)             # lower lip
        dy += 0.0030 * g(ax - 0.029, 0.008) * g(z - 0.060, 0.009)       # mouth corners
        dy += 0.0025 * g(x, 0.016) * g(z - 0.035, 0.007)                # mentolabial groove
        dy -= 0.0060 * g(x, 0.016) * g(z - 0.016, 0.013)                # chin
        dy += 0.0020 * g(ax - 0.024, 0.006) * g(z - 0.078, 0.012)       # nasolabial fold
    q = p.copy()
    q.y += dy * wf
    # cheekbones out, temples in, jaw corners out
    q.x += sx * 0.0045 * g(z - 0.112, 0.017) * g(p.y + 0.062, 0.032)
    q.x -= sx * 0.0030 * g(z - 0.170, 0.022) * g(p.y + 0.060, 0.028)
    q.x += sx * 0.0030 * g(z - 0.030, 0.014) * g(p.y - 0.005, 0.022)
    return q


def head_pt(th, t):
    return face_features(head_base(th, t), th)


def head_nrm(th, t):
    e = 1e-3
    a = head_pt(th + e, t) - head_pt(th - e, t)
    tb = HK[-1]
    b_ = head_pt(th, min(t + e, tb)) - head_pt(th, max(t - e, 0))
    n = a.cross(b_)
    if n.length < 1e-12:
        return Vector((0, 0, 1))
    n.normalize()
    if n.dot(head_pt(th, t) - Vector((0, 0, 0.14))) < 0:
        n = -n
    return n


HEAD_N = 88
H_TH = []
for _i in range(HEAD_N):
    _s = 2 * _i / HEAD_N - 1
    H_TH.append(math.pi * math.copysign(0.42 * abs(_s) + 0.58 * abs(_s) ** 2.6, _s))

_FACE = None


def face_y(x, z):
    """y of the sculpted face surface at (x, z) (front of the head)."""
    global _FACE
    if _FACE is None:
        pts = []
        for t in H_TS[:-1]:
            for th in H_TH:
                if math.cos(th) > 0.2:
                    pts.append(head_pt(th, t))
        kd = kdtree.KDTree(len(pts))
        for i, p in enumerate(pts):
            kd.insert(Vector((p.x, 0, p.z)), i)
        kd.balance()
        _FACE = (kd, pts)
    kd, pts = _FACE
    sw = sy = 0.0
    for co, i, d in kd.find_n(Vector((x, 0, z)), 4):
        w = 1.0 / (d * d + 1e-8)
        sw += w
        sy += w * pts[i].y
    return sy / sw


def fp(x, z, lift=0.0):
    return Vector((x, face_y(x, z) - lift, z))


def skin_col(p):
    c = SKIN
    ax = abs(p.x)
    if p.y < -0.03:
        k = 0.50 * g(ax - 0.046, 0.021) * g(p.z - 0.094, 0.020)
        k = max(k, 0.50 * g(p.x, 0.014) * g(p.z - 0.092, 0.013))
        c = lerp3(c, BLUSH, k)
        c = lerp3(c, LIP, 0.8 * g(p.x, 0.0165) * g(p.z - 0.0485, 0.006))
        c = mul(c, 1 - 0.16 * g(ax - EX, 0.018) * g(p.z - EZ - 0.003, 0.012))
        c = mul(c, 1 - 0.30 * g(p.x, 0.020) * g(p.z - 0.0805, 0.0045))               # under the nose
        c = mul(c, 1 - 0.12 * g(ax - 0.0160, 0.0055) * g(p.z - 0.104, 0.024))          # sides of the bridge
    return c


# hairline height as a function of y (front -> back), chin space
HAIRLINE = [(-0.30, 0.213), (-0.086, 0.213), (-0.070, 0.202), (-0.058, 0.172), (-0.036, 0.108), (-0.010, 0.102),
            (-0.003, 0.152), (0.034, 0.152), (0.041, 0.086), (0.060, 0.062), (0.30, 0.056)]


def hair_mask(p):
    y = p.y
    H = HAIRLINE
    hz = H[-1][1]
    for i in range(len(H) - 1):
        if H[i][0] <= y <= H[i + 1][0]:
            f = (y - H[i][0]) / (H[i + 1][0] - H[i][0])
            hz = H[i][1] * (1 - f) + H[i + 1][1] * f
            break
    return (p.z - hz) / 0.020


def hair_col(p):
    k = 0.5 + 0.5 * noise.noise(Vector((p.x * 60, p.y * 14, p.z * 14)))
    c = lerp3(HAIR_D, HAIR, clamp(0.25 + 0.9 * k))
    c = lerp3(c, HAIR_L, 0.35 * clamp(k * 1.6 - 0.9))
    grey = 0.0        # greying temples / sideburns
    return lerp3(c, GREY, grey)


def build_eye(b):
    """Left eye (x>0) in chin space; call inside a mirrored frame for the right one."""
    R = 0.0176
    ys = face_y(EX, EZ)
    c = Vector((EX, ys + R - 0.0098, EZ))
    with b.at(c, rot=(90, 0, 0)):                                   # local +Z looks forward
        prof = [(R * math.sin(math.radians(a)), R * math.cos(math.radians(a))) for a in (100, 80, 62, 46, 31, 16, 0)]
        b.lathe(prof, mat='paint', segs=16, color=EYEWHITE)
        ri = 0.0088
        am = math.asin(ri / R)
        Ri = R + 0.00035
        prof = [(Ri * math.sin(am * k / 3), Ri * math.cos(am * k / 3)) for k in (3, 2, 1, 0)]
        b.lathe(prof, mat='paint', segs=16, color=lambda co: lerp3(IRIS, IRIS_D, clamp((math.hypot(co.x, co.y) / ri) ** 3)))
        rp = 0.0040
        am = math.asin(rp / R)
        Rp = R + 0.0007
        b.lathe([(Rp * math.sin(am), Rp * math.cos(am)), (Rp * math.sin(am / 2), Rp * math.cos(am / 2)), (0, Rp)], mat='eye', segs=12, color=WHITE)
        b.blob((0.0020, 0.0020, 0.0007), loc=(0.0034, 0.0036, R + 0.0005), rot=(12, -12, 0), mat='paint', subdiv=1, color=WHITE)
    # lids: a sphere shell with an almond opening
    RL = R + 0.0013
    roll = Matrix.Rotation(math.radians(-5), 3, 'Y')
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
            return math.radians(27) * k if upper else math.radians(-18) * k

        far = math.radians(112 if upper else -112)
        rows = [[P(l, edge(l), R + 0.0002) for l in lams], [P(l, edge(l), RL) for l in lams]]
        for f in (0.2, 0.45, 0.72, 1.0):
            rows.append([P(l, edge(l) + (far - edge(l)) * f, RL) for l in lams])
        lidc = lerp3(SKIN, SKIN_D, 0.45) if upper else lerp3(SKIN, SKIN_D, 0.15)
        emit_grid(b, rows, 'skin', lidc, outward=c)
        if upper:                                                   # lash line
            pts = [P(l, edge(l) - 0.01, RL + 0.0002) for l in lams[2:-2]]
            b.tube(pts, [0.0006 + 0.0008 * math.sin(math.pi * i / (len(pts) - 1)) for i in range(len(pts))], mat='hair', segs=5, color=mul(HAIR_D, 0.5))
    return c


def build_ear(b):
    """Left ear."""
    kd_y, kd_z = 0.014, 0.118
    x = max(head_pt(th, t).x for t in H_TS[:-1] for th in H_TH
            if abs(head_pt(th, t).y - kd_y) < 0.012 and abs(head_pt(th, t).z - kd_z) < 0.012)
    with b.at((x - 0.004, kd_y, kd_z), rot=(0, -8, -24)):
        earc = lerp3(SKIN, BLUSH, 0.16)
        b.blob((0.0065, 0.0150, 0.0300), loc=(0.004, 0.006, 0.0), mat='skin', subdiv=2, color=lerp3(SKIN_D, BLUSH, 0.2))
        pts, rad = [], []
        for k in range(11):
            a = math.radians(238 - 300 * k / 10)                   # from the front-bottom, over the top, down the back
            pts.append((0.0085, 0.006 - 0.0155 * math.cos(a), 0.002 + 0.030 * math.sin(a)))
            rad.append(0.0030 + 0.0020 * math.sin(math.pi * k / 10))
        b.tube(pts, rad, mat='skin', segs=6, color=earc)
        b.blob((0.0060, 0.0080, 0.0095), loc=(0.006, 0.003, -0.026), mat='skin', subdiv=1, color=earc)   # lobe
        b.blob((0.0045, 0.0050, 0.0070), loc=(0.006, -0.008, 0.002), mat='skin', subdiv=1, color=earc)    # tragus


def build_hair(b):
    N, M = 56, 30
    t0, t1 = HK[6], HK[-1] - 0.004
    TH = [-math.pi + 2 * math.pi * i / N for i in range(N)]
    TT = [t0 + (t1 - t0) * j / (M - 1) for j in range(M)]
    par = [[(TH[i], TT[j]) for i in range(N)] for j in range(M)]
    mm = [[hair_mask(head_pt(*par[j][i])) for i in range(N)] for j in range(M)]
    ok = [[mm[j][i] > 0 for i in range(N)] for j in range(M)]
    # slide the first row of outside vertices onto the hairline so the shell ends in a clean edge
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
                if hair_mask(head_pt(*q)) > 0:
                    hi = mid
                else:
                    lo = mid
            par[j][i] = (a[0] + (c[0] - a[0]) * hi, a[1] + (c[1] - a[1]) * hi)
            ok[j][i] = True
    t = b._new()
    uv, col, _ = b._layers(t)
    V = {}
    for j in range(M):
        for i in range(N):
            if not ok[j][i]:
                continue
            th, tt = par[j][i]
            pp = head_pt(th, tt)
            m = max(hair_mask(pp), 0.0)
            thick = 0.0100 + 0.0030 * noise.noise(Vector((th * 3.0, tt * 30, 1.7))) + 0.003 * g(pp.z - 0.07, 0.03) * (1 if pp.y > 0.03 else 0)
            V[(i, j)] = t.verts.new(pp + head_nrm(th, tt) * thick * (0.16 + 0.84 * (1 - math.exp(-3.0 * m))))
    for j in range(M - 1):
        for i in range(N):
            i2 = (i + 1) % N
            vs = [V[k] for k in ((i, j), (i2, j), (i2, j + 1), (i, j + 1)) if k in V]
            if len(vs) >= 3:
                try:
                    t.faces.new(vs)
                except ValueError:
                    pass
    pv = t.verts.new(head_pt(0, HK[-1]) + Vector((0, 0, 0.008)))
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
            l[col] = (*hair_col(l.vert.co), 1.0)
    b._emit(t, 'hair', (0, 0, 0), (0, 0, 0))
    # a few locks at the nape and behind the ears to break the outline
    for az, z0, ln, k in ((150, 0.085, 0.040, 1.0), (165, 0.075, 0.045, 1.1), (180, 0.072, 0.048, 1.15), (195, 0.075, 0.045, 1.1), (210, 0.085, 0.040, 1.0),
                          (128, 0.105, 0.036, 0.9), (232, 0.105, 0.036, 0.9)):
        a = math.radians(az)
        d = Vector((math.sin(a), -math.cos(a), 0))
        r0 = 0.079 if abs(az - 180) > 40 else 0.092
        pts = [Vector((d.x * r0 * 0.92, d.y * r0 + 0.004, z0 + 0.02)), Vector((d.x * r0 * 0.9, d.y * r0 * 0.98 + 0.004, z0 - ln * 0.4)),
               Vector((d.x * r0 * 0.84, d.y * r0 * 0.93 + 0.004, z0 - ln))]
        b.tube(pts, [0.012 * k, 0.010 * k, 0.003], mat='hair', segs=7, color=HAIR, color_top=HAIR_D, jitter=0.08)


def build_cap(b):
    """Soft royal-blue cap with a gold band and a cream feather."""
    with b.at((0, 0.007, 0.199), rot=(-6, 6, 0)):
        sx, sy = 0.1005, 0.1165
        b.lathe([(0.88, -0.002), (1.0, -0.006), (1.02, 0.0), (1.02, 0.022), (1.0, 0.028), (0.955, 0.028)], scale=(sx, sy, 1), mat='cloth', segs=30, color=GOLD)

        def flop(c):
            k = sstep(c.z / 0.08)
            c.x -= 0.030 * k
            c.y += 0.014 * k
            d = sstep((-c.x - 0.02) / 0.10) * sstep((c.z - 0.02) / 0.035)
            c.z -= 0.022 * d
            a = math.atan2(c.y, c.x)
            c.z += 0.0035 * math.sin(5 * a + 1.0) * sstep((math.hypot(c.x / sx, c.y / sy) - 0.5) / 0.6)
            return c

        b.deform = flop
        prof = smooth_profile([(0.99, 0.022), (1.17, 0.030), (1.29, 0.047), (1.27, 0.064), (1.05, 0.078), (0.66, 0.086), (0.28, 0.089), (0, 0.089)], 3)
        b.lathe(prof, scale=(sx, sy, 1), mat='cloth', segs=30, color=lambda co: lerp3(BLUE_D, BLUE, clamp(0.35 + co.z / 0.06)))
        b.deform = None
        # feather on the left, sweeping up and back, with a gold brooch at its root
        root = Vector((sx * 1.0, -0.030, 0.012))
        pts, nr = [], []
        for i in range(9):
            t = i / 8
            pts.append(root + Vector((0.012 + 0.030 * t - 0.03 * t * t, 0.215 * t, 0.012 + 0.135 * t - 0.055 * t * t)))
            nr.append(Vector((1.0, -0.15, 0.25 + 0.5 * t)))
        ribbon(b, pts, nr, lambda t: 0.006 + 0.052 * math.sin(math.pi * clamp(t * 0.92 + 0.05)) ** 0.8, 0.007, 'cloth', CREAM, segs=8, color_top=WHITE)
        b.tube([p + nr[i].normalized() * 0.003 for i, p in enumerate(pts)], [0.0026 - 0.002 * i / 8 for i in range(9)], mat='cloth', segs=5, color=CREAM_D)
        b.blob((0.008, 0.014, 0.014), loc=root + Vector((0.004, 0.004, 0.006)), mat='metal', subdiv=2, color=GOLD)


def build_head():
    b = B('courier_head', 3)
    with b.at(CHIN_OFF * HEAD_K, scale=HEAD_K):
        rows = [[head_pt(th, t) for th in H_TH] for t in H_TS[:-1]]
        ctr = sum(rows[0], Vector()) / len(rows[0])
        under = {}
        for row, t in zip(rows, H_TS[:-1]):
            k = 1 - 0.20 * sstep((HK[4] - t) / (HK[4] - HK[3]) * 1.2)
            for q in row:
                under[(round(q.x, 5), round(q.y, 5), round(q.z, 5))] = k

        def skin_col2(co):
            return mul(skin_col(co), under.get((round(co.x, 5), round(co.y, 5), round(co.z, 5)), 1.0))

        emit_grid(b, rows, 'skin', skin_col2, wrap=True, outward='closed', pole_end=head_pt(0, H_TS[-1]), pole_start=ctr)
        for s in (1, -1):
            with b.at(scale=(s, 1, 1)):
                build_eye(b)
                build_ear(b)
                # eyebrow: thick, gently arched
                bp = [(0.0110, 0.1600), (0.020, 0.1645), (0.031, 0.1678), (0.041, 0.1672), (0.050, 0.1632), (0.0565, 0.1580)]
                pts = [fp(x, z, 0.0012) for x, z in bp]
                ribbon(b, pts, Vector((0, -1, 0.15)), lambda t: 0.0030 + 0.0062 * math.sin(math.pi * clamp(0.22 + 0.7 * t)) , 0.0055, 'hair', HAIR_D, segs=8)
                # moustache half: full at the philtrum, tapering to an upturned tip
                mp = [(0.0015, 0.0705, 0.0056), (0.010, 0.0695, 0.0072), (0.020, 0.0665, 0.0068), (0.029, 0.0635, 0.0052), (0.037, 0.0640, 0.0034), (0.043, 0.0685, 0.0016)]
                pts = [fp(x, z, r * 0.45) for x, z, r in mp]
                b.tube(pts, [r for _, _, r in mp], mat='hair', segs=8, color=HAIR, color_top=HAIR_L)
        for sx_ in (-1, 1):                                                          # nostrils
            b.blob((0.0044, 0.0030, 0.0028), loc=fp(sx_ * 0.0085, 0.0822, -0.0012), rot=(0, sx_ * 20, 0), mat='skin', subdiv=1, color=mul(SKIN_D, 0.42))
        # smile line under the moustache
        mpts = [fp(x, 0.0560 + 0.0065 * (abs(x) / 0.027) ** 2, 0.0002) for x in (-0.027, -0.020, -0.012, 0, 0.012, 0.020, 0.027)]
        b.tube(mpts, [0.0012, 0.0021, 0.0025, 0.0026, 0.0025, 0.0021, 0.0012], mat='paint', segs=6, color=MOUTH)
        build_hair(b)
        build_cap(b)
    obj = b.build(sharp_angle=80)
    return obj


# ================================================================ BODY
#        z      half-w  front   back   p
BODY = [(0.800, 0.110, 0.070, 0.080, 2.2, 0.004),
        (0.840, 0.158, 0.098, 0.110, 2.3, 0.004),
        (0.900, 0.170, 0.108, 0.120, 2.3, 0.006),
        (0.980, 0.160, 0.108, 0.108, 2.3, 0.002),
        (1.060, 0.145, 0.109, 0.094, 2.3, -0.004),
        (1.160, 0.150, 0.111, 0.100, 2.3, -0.004),
        (1.260, 0.164, 0.121, 0.110, 2.35, -0.002),
        (1.340, 0.170, 0.116, 0.119, 2.45, 0.004),
        (1.400, 0.162, 0.096, 0.111, 2.5, 0.008),
        (1.432, 0.118, 0.074, 0.086, 2.3, 0.006),
        (1.452, 0.074, 0.058, 0.066, 2.1, 0.003),
        (1.468, 0.052, 0.046, 0.054, 2.0, 0.002)]
TAB = [(0.660, 0.182, 0.126, 0.132, 2.3, 0.004), (0.760, 0.178, 0.120, 0.128, 2.3, 0.005), (0.900, 0.173, 0.112, 0.123, 2.3, 0.006)] + BODY[3:]
BODY_SP = Spline([r[0] for r in BODY], [r[1:] for r in BODY])
TAB_SP = Spline([r[0] for r in TAB], [r[1:] for r in TAB])


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


BELT_Z0, BELT_Z1 = 1.004, 1.050


def tab_off(th, z, seed=0.0):
    off = 0.0105
    tt = clamp((BELT_Z0 - z) / 0.30)
    off += 0.004 * tt + 0.011 * tt * (0.5 + 0.5 * math.sin(math.radians(th) * 9.0 + seed)) ** 1.5
    off += 0.0075 * g(z - 1.092, 0.036)                              # blouses over the belt
    off += 0.0020 * math.sin(math.radians(th) * 6 + 1.3 + seed) * g(z - 1.15, 0.07)
    off -= 0.0050 * g(z - 1.027, 0.022)                              # cinched under the belt
    return off


def tabard_panel(b, front):
    thc = 0.0 if front else 180.0
    seed = 0.4 if front else 2.1

    def wa(z):                                                       # half angle of the panel
        if z >= 1.395:
            return 90.0
        if z >= 1.31:
            return 54.0 + 36.0 * sstep((z - 1.31) / 0.085)
        return 54.0

    us = [0.0, 0.03, 0.105] + [0.105 + 0.79 * i / 10 for i in range(1, 10)] + [0.895, 0.97, 1.0]
    vs = [0.0, 0.035, 0.07] + [0.07 + 0.885 * j / 22 for j in range(1, 22)] + [0.955, 0.985, 1.0]
    nu, nv = len(us), len(vs)

    def z_lo(u):
        return 0.735 - 0.065 * (1 - abs(2 * u - 1)) ** 1.2            # pointed hem

    def z_hi(u):
        return 1.449 - (0.050 if front else 0.012) * math.sin(math.pi * u) ** 1.5

    def pt(i, j, inner=False):
        u, v = us[i], vs[j]
        z = z_lo(u) + (z_hi(u) - z_lo(u)) * v
        th = thc + (2 * u - 1) * wa(z)
        off = tab_off(th, z, seed)
        free = z < BELT_Z0 - 0.02                                    # hangs free below the belt
        trim = (i in (1, 2, nu - 3, nu - 2)) or (j in (1, 2)) or (j in (nv - 3, nv - 2))
        if trim:
            off += 0.0022
        if (i in (0, nu - 1) or j == nv - 1) and not free:
            off = -0.004
        if inner:
            off -= 0.007
        return S(TAB_SP, th, z, off)

    def fcol(i, j):
        if i <= 1 or i >= nu - 3 or j <= 1 or j >= nv - 3:
            return GOLD
        return None

    def col(co):
        k = clamp((co.z - 0.70) / 0.6)
        return lerp3(BLUE_D, BLUE, 0.55 + 0.45 * k)

    rows = [[pt(i, j) for i in range(nu)] for j in range(nv)]
    ctr = Vector((0, 0, 0))
    out = lambda c: Vector((c.x, c.y, 0))
    emit_grid(b, rows, 'cloth', col, outward=out, facecol=fcol)
    # lining so the free-hanging skirt is not see-through from behind
    jmax = max(j for j in range(nv) if z_lo(0.5) + (z_hi(0.5) - z_lo(0.5)) * vs[j] < BELT_Z1 + 0.03)
    rows = [[pt(i, j, True) for i in range(nu)] for j in range(jmax + 1)]
    emit_grid(b, rows, 'cloth', mul(BLUE_D, 0.8), outward=lambda c: -Vector((c.x, c.y, 0)))
    # close the hem and free side edges between face and lining
    edge = [(i, 0) for i in range(nu)]
    for side in (0, nu - 1):
        strip = [[pt(side, j), pt(side, j, True)] for j in range(jmax + 1)]
        emit_grid(b, strip, 'cloth', GOLD_D, outward=out)
    strip = [[pt(i, 0), pt(i, 0, True)] for i in range(nu)]
    emit_grid(b, strip, 'cloth', GOLD_D, outward=lambda c: Vector((0, 0, -1)))


def build_emblem(b):
    """Gold crown on the chest."""
    p = S(TAB_SP, 0, 1.262, tab_off(0, 1.262, 0.4))
    with b.at(p + Vector((0, 0.002, 0)), rot=(3, 0, 0)):
        pts = [(-0.046, 0.0), (0.046, 0.0), (0.060, 0.066), (0.031, 0.034), (0.0, 0.080), (-0.031, 0.034), (-0.060, 0.066)]
        b.prism(pts, 0.014, loc=(0, 0, -0.03), mat='cloth', bevel=0.0025, segs=1, color=GOLD)
        b.box((0.100, 0.017, 0.014), loc=(0, -0.001, -0.026), mat='cloth', bevel=0.003, segs=1, grain=None, color=GOLD_D)
        for x, z in ((-0.060, 0.066), (0.0, 0.080), (0.060, 0.066)):
            b.blob((0.0085, 0.0075, 0.0085), loc=(x, -0.001, z - 0.03 + 0.004), mat='cloth', subdiv=2, color=GOLD)
        for x in (-0.028, 0.0, 0.028):
            b.blob((0.0055, 0.004, 0.0055), loc=(x, -0.0085, -0.026), mat='cloth', subdiv=1, color=lerp3(BLUE_L, WHITE, 0.2) if x == 0 else RED)


def build_belt(b):
    N = 40
    prof = [(BELT_Z0 - 0.002, 0.002), (BELT_Z0, 0.0125), (BELT_Z0 + 0.004, 0.0165), (BELT_Z1 - 0.004, 0.0165), (BELT_Z1, 0.0125), (BELT_Z1 + 0.002, 0.002)]
    rows = [[S(TAB_SP, 360 * i / N, z, o) for i in range(N)] for z, o in prof]
    emit_grid(b, rows, 'leather', LEA, wrap=True, outward=lambda c: Vector((c.x, c.y, 0)))
    zc = (BELT_Z0 + BELT_Z1) / 2
    # buckle
    p = S(TAB_SP, 0, zc, 0.019)
    with b.at(p):
        b.box((0.058, 0.010, 0.064), mat='metal', bevel=0.004, grain=None, color=GOLD)
        b.box((0.034, 0.012, 0.040), loc=(0, -0.001, 0), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.8))
        b.box((0.006, 0.014, 0.046), loc=(0.004, -0.002, 0), mat='metal', bevel=0.002, grain=None, color=GOLD)
        # hanging belt tail
        ribbon(b, [(0.034, 0.002, 0.0), (0.040, -0.004, -0.03), (0.043, -0.006, -0.075), (0.044, -0.004, -0.115)], Vector((0, -1, 0)), 0.034, 0.007, 'leather', LEA, segs=8)
    # pouch on the right hip
    th = -40
    p, n = S(TAB_SP, th, zc, 0.016), S_n(TAB_SP, th, zc)
    with b.at(p, aim(n)):
        b.box((0.040, 0.010, 0.060), loc=(0, -0.004, 0.0), mat='leather', bevel=0.003, grain=None, color=mul(LEA, 0.85))       # belt loop
        b.blob((0.047, 0.026, 0.052), loc=(0, -0.022, -0.062), mat='leather', subdiv=2, color=LEA,
               deform=lambda c: Vector((sp(c.x / 0.047, 0.75) * 0.047, c.y if c.y < 0 else c.y * 0.5, sp(c.z / 0.052, 0.8) * 0.052)))
        b.blob((0.050, 0.029, 0.034), loc=(0, -0.024, -0.036), mat='leather', subdiv=2, color=mul(LEA, 1.25),
               deform=lambda c: Vector((sp(c.x / 0.05, 0.75) * 0.05, c.y if c.y < 0 else c.y * 0.5, c.z if c.z < 0 else c.z * 0.6)))   # flap
        b.blob((0.0075, 0.005, 0.0075), loc=(0, -0.052, -0.058), mat='metal', subdiv=2, color=GOLD)
    # rolled scroll in a leather loop on the left hip
    th = 42
    p, n = S(TAB_SP, th, zc, 0.034), S_n(TAB_SP, th, zc)
    with b.at(p, aim(n)):
        with b.at(rot=(0, -24, 0)):
            b.cyl(0.0165, 0.26, loc=(0, 0, -0.11), mat='paint', segs=14, bevel=0.003, color=PAPER)
            for z in (-0.11, 0.15):
                b.cyl(0.0085, 0.006, loc=(0, 0, z - 0.003 if z < 0 else z - 0.003), mat='paint', segs=10, bevel=0.001, color=mul(PAPER, 0.55))
            b.lathe([(0.0168, 0.085), (0.0185, 0.087), (0.0185, 0.103), (0.0168, 0.105)], mat='cloth', segs=14, color=BLUE)
            b.blob((0.012, 0.006, 0.012), loc=(0, -0.0175, 0.095), mat='paint', subdiv=2, color=RED)                           # wax seal
            b.lathe([(0.017, -0.026), (0.0215, -0.024), (0.0215, 0.024), (0.017, 0.026)], mat='leather', segs=14, color=mul(LEA, 0.9))
        b.box((0.030, 0.022, 0.044), loc=(0, 0.012, 0.0), mat='leather', bevel=0.004, grain=None, color=mul(LEA, 0.9))


def build_leg(b, s):
    with b.at(scale=(s, 1, 1)):
        # trousers
        b.tube([(0.084, 0.004, 0.930), (0.088, 0.002, 0.760), (0.094, -0.008, 0.560), (0.097, -0.010, 0.470), (0.098, -0.004, 0.400)],
               [0.083, 0.081, 0.066, 0.060, 0.054], mat='cloth', segs=14, color=TROUSER, color_top=TROUSER_L)
        with b.at((0.100, 0.0, 0.0), rot=(0, 0, 9)):
            boot = mul(LEA, 0.82)
            # shaft with a folded cuff
            b.tube([(0, 0.012, 0.075), (0, 0.016, 0.170), (0, 0.016, 0.300), (0, 0.004, 0.400), (0, -0.002, 0.448), (0, -0.004, 0.470)],
                   [0.046, 0.049, 0.061, 0.063, 0.066, 0.040], mat='leather', segs=14, color=boot)
            cuff = smooth_profile([(0.062, -0.060), (0.074, -0.062), (0.079, -0.03), (0.080, 0.0), (0.074, 0.010), (0.064, 0.004), (0.050, -0.012)], 2)
            b.lathe(cuff, loc=(0, -0.001, 0.452), rot=(-4, 0, 0), mat='leather', segs=16, color=mul(LEA, 1.2))

            def foot(c):
                t = clamp(-c.y / 0.125)
                if c.z > 0:
                    c.z *= 1.0 - 0.62 * t ** 1.1
                c.x *= 1.0 + 0.10 * math.sin(math.pi * clamp(t * 0.8 + 0.1)) - 0.22 * t ** 3
                return c

            b.blob((0.047, 0.128, 0.060), loc=(0, -0.052, 0.055), mat='leather', subdiv=3, flatten_bottom=-0.62, deform=foot, color=boot)

            def sole(c):
                c.z = clamp(c.z, -0.011, 0.011)
                t = clamp(-c.y / 0.13)
                c.x *= 1.0 + 0.10 * math.sin(math.pi * clamp(t * 0.8 + 0.1)) - 0.18 * t ** 3
                return c

            b.blob((0.051, 0.134, 0.03), loc=(0, -0.052, 0.0125), mat='leather', subdiv=2, deform=sole, color=mul(LEA, 0.3))
            b.box((0.086, 0.062, 0.022), loc=(0, 0.036, 0.011), mat='leather', bevel=0.006, grain=None, color=mul(LEA, 0.3))   # heel


def build_body():
    b = B('courier', 7)
    N = 30
    zs = [0.80, 0.82, 0.845, 0.875, 0.91, 0.95, 0.99, 1.03, 1.07, 1.11, 1.15, 1.19, 1.23, 1.27, 1.31, 1.345, 1.375, 1.40, 1.418, 1.434, 1.448, 1.458, 1.468]
    rows = [[S(BODY_SP, 360 * i / N, z) for i in range(N)] for z in zs]

    def bcol(co):
        if co.z < 0.995:
            return TROUSER
        k = 0.5 + 0.5 * math.sin(co.z * 70 + co.x * 30)
        return lerp3(CREAM_D, CREAM, 0.6 + 0.4 * k)

    emit_grid(b, rows, 'cloth', bcol, wrap=True, outward='closed', pole_start=Vector((0, 0.005, 0.795)), pole_end=Vector((0, 0.004, 1.47)))
    # shirt collar: a soft stand collar open at the front
    Nc = 26
    crow = []
    for z, r, tilt in ((1.434, 1.24, 0), (1.448, 1.17, 0), (1.461, 1.11, 0), (1.471, 1.15, 0), (1.473, 1.07, 0), (1.458, 0.98, 0)):
        row = []
        for i in range(Nc + 1):
            a = math.radians(-180 + 20 + (360 - 40) * i / Nc)     # gap at the front (th=0)
            th = math.degrees(a) + 180
            dz = 0.012 * (1 - abs(math.cos(math.radians(th) / 2))) - 0.010 * abs(math.cos(math.radians(th) / 2)) ** 6
            row.append(Vector((0.0535 * r * math.sin(math.radians(th)), 0.004 - 0.059 * r * math.cos(math.radians(th)), z + (dz if z > 1.455 else 0))))
        crow.append(row)
    emit_grid(b, crow, 'cloth', CREAM, outward=lambda c: Vector((c.x, c.y, 0.0)))
    tabard_panel(b, True)
    tabard_panel(b, False)
    build_emblem(b)
    build_belt(b)
    for s in (1, -1):
        build_leg(b, s)
    return b.build(sharp_angle=60)


# ================================================================ ARMS
def _sleeve(n, r0, r1, wr, f, ph):
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append((r0 + (r1 - r0) * t) * (1 + wr * math.sin(t * f + ph) * sstep(t * 3)))
    return out


def build_arm(name, s):
    b = B(name, 11)
    with b.at(scale=(s, 1, 1)):
        n = 8
        pts = [ELBOW * (i / (n - 1)) for i in range(n)]
        b.tube(pts, _sleeve(n, 0.0585, 0.052, 0.030, 17.0, 0.5), mat='cloth', segs=14, color=CREAM, color_top=lerp3(CREAM_D, CREAM, 0.6))
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


PALM_C = Vector((-0.017, 0.0, -0.056))       # canonical: on the palm surface


def build_hand(b):
    """Canonical left hand: wrist at the origin, fingers along -Z, palm faces -X, thumb toward -Y."""
    def hcol(co):
        return lerp3(SKIN, lerp3(SKIN, BLUSH, 0.22), clamp((-co.z - 0.07) / 0.1))

    def palm(c):
        u = Vector((c.x / 0.0135, c.y / 0.041, c.z / 0.052))
        q = Vector((sp(u.x, 0.85) * 0.0135, sp(u.y, 0.72) * 0.041, sp(u.z, 0.78) * 0.052))
        q.y *= 0.80 + 0.20 * clamp((-q.z + 0.052) / 0.104)          # narrower at the wrist
        q.x += -0.004 * clamp((-q.z) / 0.052) ** 2 * 1.0            # palm cups slightly
        return q

    b.blob((0.0135, 0.041, 0.052), loc=(0, 0, -0.052), mat='skin', subdiv=3, deform=palm, color=SKIN)
    with b.at(scale=(0.74, 1.18, 1)):
        b.tube([(0, 0, 0.03), (0, 0, -0.022)], [0.0235, 0.0205], mat='skin', segs=10, color=SKIN)  # wrist
    # fingers: index .. pinky, relaxed cascade of curl, tips fanning apart a little
    fingers = [(-0.0300, -0.097, 0.073, 0.0096, (8, 28, 44), -7), (-0.0100, -0.101, 0.082, 0.0100, (12, 34, 52), -2),
               (0.0100, -0.098, 0.075, 0.0094, (17, 41, 60), 3), (0.0290, -0.090, 0.060, 0.0083, (22, 48, 68), 9)]
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
    # thumb + thenar: thumb angles forward and slightly toward the palm, tip level with the first knuckles
    b.blob((0.0125, 0.0170, 0.030), loc=(-0.0080, -0.026, -0.040), rot=(-20, 0, 0), mat='skin', subdiv=2, color=SKIN)
    b.tube([(-0.006, -0.028, -0.026), (-0.010, -0.046, -0.050), (-0.016, -0.058, -0.072), (-0.022, -0.063, -0.090)],
           [0.0125, 0.0112, 0.0100, 0.0086], mat='skin', segs=8, color=SKIN, color_top=tipc)


def build_forearm(name, s):
    b = B(name, 12)
    with b.at(scale=(s, 1, 1)):
        n = 9
        e = 0.84
        pts = [WRIST * (e * i / (n - 1)) for i in range(n)]
        rad = [0.052, 0.0545, 0.057, 0.0585, 0.058, 0.056, 0.051, 0.042, 0.031]
        rad = [r * (1 + 0.03 * math.sin(i * 2.3 + 0.7) * (1 if 0 < i < n - 1 else 0)) for i, r in enumerate(rad)]
        b.tube(pts, rad, mat='cloth', segs=14, color=CREAM, color_top=lerp3(CREAM_D, CREAM, 0.5))
        # royal-blue cuff with gold edges
        M = hand_frame()
        eul = tuple(math.degrees(a) for a in M.to_euler('XYZ'))
        with b.at(WRIST, eul):
            b.lathe([(0.026, 0.004), (0.0345, 0.006), (0.0365, 0.012), (0.0365, 0.046), (0.034, 0.052), (0.026, 0.054)], scale=(0.92, 1.08, 1), mat='cloth', segs=16, color=BLUE)
            for z in (0.010, 0.048):
                torus(b, 0.0362, 0.0038, z, n=6, scale=(0.92, 1.08, 1), mat='cloth', segs=16, color=GOLD)
            build_hand(b)
    return b.build(sharp_angle=70)


# ================================================================ ASSEMBLE
courier = build_body()
head = kit.set_parent(build_head(), courier, NECK_PIVOT)
eye_y = face_y(0.0, EZ)
kit.marker('courier_eye', (CHIN_OFF + Vector((0, eye_y, EZ))) * HEAD_K, parent=head)
parts = {'courier': courier, 'courier_head': head}
for side, s in (('l', 1), ('r', -1)):
    arm = kit.set_parent(build_arm(f'courier_arm_{side}', s), courier, (s * SHOULDER.x, SHOULDER.y, SHOULDER.z))
    fore = kit.set_parent(build_forearm(f'courier_forearm_{side}', s), arm, (s * ELBOW.x, ELBOW.y, ELBOW.z))
    parts[arm.name] = arm
    parts[fore.name] = fore
    if s == -1:
        pc = hand_frame() @ PALM_C
        kit.marker('courier_hand_r', (s * pc.x, pc.y, pc.z), parent=fore)
bpy.context.view_layer.update()

objs = [courier] + kit._descend(courier.children)
pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
lo = [round(min(p[i] for p in pts), 3) for i in range(3)]
hi = [round(max(p[i] for p in pts), 3) for i in range(3)]
print('COURIER_TRIS', kit.tri_count(objs), {o.name: kit.tri_count([o]) for o in objs if o.type == 'MESH'})
print('BBOX', lo, hi)
print('MATERIALS', sorted({m.name for o in objs if o.type == 'MESH' for m in o.data.materials}))
for o in objs:
    print('PIVOT', o.name, o.type, 'parent', o.parent.name if o.parent else None, 'local', [round(v, 4) for v in o.location],
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
        bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=12)
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


if PREV:
    if '--cull' in sys.argv:                 # show what a FrontSide game material would show
        for m in bpy.data.materials:
            m.use_backface_culling = True
    WHAT = sys.argv[sys.argv.index('--') + 2] if len(sys.argv) > sys.argv.index('--') + 2 else 'all'
    body_c, body_r = (0, 0, 0.92), 1.0
    FOCUS = NECK_PIVOT + (CHIN_OFF + Vector((0, -0.03, 0.135))) * HEAD_K      # face close-up proxy
    if WHAT in ('all', 'face'):
        shot('face_front', FOCUS, 0.19, az=0, el=0, floor=False)
        shot('face_34', FOCUS, 0.19, az=35, el=5, floor=False)
        shot('face_side', FOCUS, 0.19, az=90, el=0, floor=False)
        shot('face_low', FOCUS, 0.19, az=-25, el=-18, floor=False)
    if WHAT in ('all', 'body'):
        shot('front', body_c, body_r, az=0, el=5)
        shot('34', body_c, body_r, az=35, el=10)
        shot('side', body_c, body_r, az=90, el=5)
        shot('back', body_c, body_r, az=180, el=8)
        shot('bust', (0, 0, 1.38), 0.45, az=20, el=6, floor=False)
        shot('game_3m', (0, 0, 1.25), 0.75, az=10, el=3, floor=True, lens=28, size=(900, 700))
    if WHAT in ('all', 'hands'):
        hw = courier.matrix_world @ Vector((-0.25, -0.03, 0.78))
        shot('hand_r_front', hw, 0.16, az=-20, el=5, floor=False)
        shot('hand_r_side', hw, 0.16, az=-90, el=5, floor=False)
        shot('hand_l_in', (0.25, -0.03, 0.78), 0.16, az=-60, el=10, floor=False)

# ================================================================ EXPORT
if '--no-export' not in sys.argv:
    kit.export_glb(os.path.join(ROOT, 'public', 'models', 'courier.glb'), [courier])
