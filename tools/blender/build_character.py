"""Player character (jointed hierarchy, animated in code) + hand tools -> public/models/character.glb

blender --background --factory-startup --python tools/blender/build_character.py -- <preview_dir>

Faces Blender -Y, character LEFT is +X. Every joint object has identity rotation at rest and its
mesh is built around its own pivot; limbs run along local -Z.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import bmesh
from mathutils import Vector, Euler
import kit
from kit import Builder, srgb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PREV = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else None
if PREV:
    os.makedirs(PREV, exist_ok=True)

kit.reset()

# ---------------------------------------------------------------- palette (linear)
SKIN = srgb(236, 178, 140)
SKIN_D = srgb(226, 160, 124)
BLUSH = srgb(240, 124, 116)
HAIR = srgb(122, 68, 38)
HAIR_D = srgb(98, 52, 30)
HAIR_TIP = srgb(168, 104, 58)
SHIRT = srgb(232, 196, 120)
SHIRT_L = srgb(242, 214, 150)
DENIM = srgb(72, 104, 150)
DENIM_D = srgb(54, 82, 126)
DENIM_L = srgb(118, 148, 186)
RED = srgb(196, 64, 52)
RED_D = srgb(160, 46, 40)
TEAL = srgb(52, 120, 128)
MOUTH = srgb(110, 46, 40)
WHITE = (1.0, 1.0, 1.0)
SACK = srgb(176, 150, 105)


def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def lerp3(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


# ---------------------------------------------------------------- local kit extensions
class B(Builder):
    """Builder with an optional per-primitive deform hook (primitive-local coords)."""
    deform = None

    def _emit(self, tbm, mat, loc, rot, scale=(1, 1, 1), smooth=True):
        if self.deform is not None:
            for v in tbm.verts:
                v.co = self.deform(v.co.copy())
        super()._emit(tbm, mat, loc, rot, scale, smooth)


def smooth_profile(ctrl, sub=4):
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
    prof = [(R + m * math.cos(math.radians(-90 + 360 * k / n)), z + m * math.sin(math.radians(-90 + 360 * k / n))) for k in range(n + 1)]
    b.lathe(prof, **kw)


def ribbon(b, pts, nrm, width, thick, mat, color, segs=12):
    """Flat strap: an elliptical section swept along pts, flat side facing nrm."""
    t = b._new()
    uv, col, _ = b._layers(t)
    n = len(pts)
    rings = []
    for i in range(n):
        P = Vector(pts[i])
        N = Vector(nrm[i]).normalized()
        T = (Vector(pts[min(i + 1, n - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        Bn = T.cross(N).normalized()
        N2 = Bn.cross(T).normalized()
        w = width if not callable(width) else width(i / (n - 1))
        rings.append([t.verts.new(P + Bn * math.cos(2 * math.pi * k / segs) * w / 2 + N2 * math.sin(2 * math.pi * k / segs) * thick / 2) for k in range(segs)])
    for i in range(n - 1):
        for k in range(segs):
            j = (k + 1) % segs
            t.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
    t.faces.new(rings[0])
    t.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    for f in t.faces:
        for l in f.loops:
            l[uv].uv = (l.vert.co.x * 4, l.vert.co.z * 4)
            l[col] = (*color, 1)
    t.normal_update()
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def patch(b, S, a0, a1, z0, z1, off, mat, color, nu=14, nv=10, sink=0.008, margin=0.07, corner=0.0):
    """Raised panel hugging a parametric surface S(a_deg, z, off) -> Vector (bib, pocket)."""
    t = b._new()
    uv, col, _ = b._layers(t)

    def ts(n):
        inner = [margin + (1 - 2 * margin) * i / (n - 2) for i in range(n - 1)]
        return [0.0] + inner + [1.0]

    us, vs = ts(nu), ts(nv)
    g = []
    for i, u in enumerate(us):
        row = []
        for j, v in enumerate(vs):
            border = i in (0, len(us) - 1) or j in (0, len(vs) - 1)
            uu, vv = u, v
            if corner > 0:  # round the corners a little by pulling them toward the centre
                cu, cv = abs(u - 0.5) * 2, abs(v - 0.5) * 2
                k = max(0.0, cu + cv - (2 - corner)) / corner if corner else 0
                uu = 0.5 + (u - 0.5) * (1 - 0.12 * k)
                vv = 0.5 + (v - 0.5) * (1 - 0.12 * k)
            a = a0 + (a1 - a0) * uu
            z = z0 + (z1 - z0) * vv
            row.append(t.verts.new(S(a, z, -sink if border else off)))
        g.append(row)
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            f = t.faces.new((g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]))
            for l in f.loops:
                l[uv].uv = (l.vert.co.x * 4, l.vert.co.z * 4)
                l[col] = (*color, 1)
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    t.normal_update()
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def aim(n):
    """Euler (deg) that turns local -Y to the direction n."""
    n = Vector(n).normalized()
    return (-math.degrees(math.asin(max(-1, min(1, n.z)))), 0.0, math.degrees(math.atan2(n.x, -n.y)))


# ---------------------------------------------------------------- proportions (metres, Blender coords)
ANKLE_Z = 0.12
SHIN_L = 0.23
THIGH_L = 0.20
HIP_X = 0.082
HIPJ_DZ = -0.03                 # hip joints, local to `hips`
HIPS_Z = ANKLE_Z + SHIN_L + THIGH_L - HIPJ_DZ   # 0.62
WAIST_DZ = 0.06                 # torso pivot, local to hips
NECK_DZ = 0.36                  # head pivot, local to torso
SHOULDER = (0.166, 0.0, 0.262)  # local to torso (+X = left)
UPPER_L = 0.17
FORE_L = 0.16
HEAD_C = Vector((0, 0, 0.175))  # head centre, local to head pivot
HEAD_R = (0.205, 0.192, 0.20)
HEAD_K = 1.1                    # head + hat are built at this scale about their pivots
HAT_PIVOT = (0.0, 0.025 * HEAD_K, 0.352 * HEAD_K)  # local to head


# ================================================================ HEAD
def head_deform(c):
    c = c.copy()
    g = math.exp(-((c.z + 0.055) / 0.08) ** 2)
    c.x *= 1 + 0.075 * g           # chubby cheeks
    if c.y < 0:
        c.y *= 1 + 0.03 * g
    if c.z < -0.12:                # soften the chin a touch
        c.z = -0.12 + (c.z + 0.12) * 0.92
    return c


def hp(az, el, lift=0.0):
    """Point on the head surface (head-local) + outward normal. az 0 = face front, + = character left."""
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    c = head_deform(Vector((d.x * HEAD_R[0], d.y * HEAD_R[1], d.z * HEAD_R[2])))
    n = Vector((c.x / HEAD_R[0] ** 2, c.y / HEAD_R[1] ** 2, c.z / HEAD_R[2] ** 2)).normalized()
    return HEAD_C + c + n * lift, n


def build_head():
    b = B('head', 3)
    with b.at(scale=(HEAD_K, HEAD_K, HEAD_K)):
        _head_parts(b)
    return b.build(sharp_angle=75)


def _head_parts(b):
    blush_pts = [hp(s * 40, -24)[0] - HEAD_C for s in (-1, 1)]

    def skin_col(co):
        k = 0.0
        for p in blush_pts:
            k = max(k, math.exp(-((co - p).length / 0.047) ** 2))
        # slightly warmer/darker toward the underside for form
        shade = 1.0 - 0.10 * max(0.0, min(1.0, (-co.z - 0.08) / 0.12))
        return mul(lerp3(SKIN, BLUSH, 0.62 * k), shade)

    b.blob(HEAD_R, loc=HEAD_C, mat='skin', subdiv=5, deform=head_deform, color=skin_col)
    # ears
    for s in (-1, 1):
        p, n = hp(s * 92, -8, -0.004)
        b.blob((0.034, 0.016, 0.042), loc=p, rot=aim(n), mat='skin', subdiv=2, color=SKIN_D)
    # eyes: big glossy ovals with highlights
    for s in (-1, 1):
        p, n = hp(s * 23.5, -6.5, -0.002)
        r = aim(n)
        with b.at(p, (r[0], s * -4, r[2])):
            b.blob((0.031, 0.013, 0.044), mat='eye', subdiv=3, color=WHITE)
            b.blob((0.0105, 0.005, 0.012), loc=(0.009, -0.0105, 0.017), mat='paint', subdiv=2, color=WHITE)
            b.blob((0.005, 0.003, 0.0055), loc=(-0.010, -0.0105, -0.016), mat='paint', subdiv=2, color=WHITE)
    # eyebrows
    for s in (-1, 1):
        pts = [hp(s * az, el, 0.002)[0] for az, el in ((13, 13.5), (20, 16.5), (27, 16.5), (33, 13.5))]
        b.tube(pts, [0.0058, 0.0072, 0.0068, 0.0045], mat='hair', segs=8, color=HAIR_D)
    # nose + smile
    p, n = hp(0, -17, 0.001)
    b.blob((0.014, 0.011, 0.0105), loc=p, rot=aim(n), mat='skin', subdiv=2, color=lerp3(SKIN, BLUSH, 0.16))
    pts = [hp(az, -30.5 + 3.6 * (abs(az) / 11.0) ** 2, 0.0015)[0] for az in (-11, -7.5, -3.5, 0, 3.5, 7.5, 11)]
    b.tube(pts, [0.0026, 0.0042, 0.0048, 0.005, 0.0048, 0.0042, 0.0026], mat='paint', segs=8, color=MOUTH)

    # ---- hair: a cap + chunky locks
    def hair_col(co):
        return lerp3(HAIR_D, HAIR, max(0.0, min(1.0, (co.z + 0.08) / 0.2)))

    def cap_deform(c):
        if c.z > 0.03:                      # tuck the top of the hair under the hat crown
            k = 1.0 - 0.13 * min(1.0, (c.z - 0.03) / 0.1)
            c.x *= k
            c.y *= k
        return c

    b.blob((0.226, 0.21, 0.205), loc=HEAD_C + Vector((0, 0.024, 0.036)), mat='hair', subdiv=4, flatten_bottom=-0.52, color=hair_col, deform=cap_deform)
    # fringe locks sweeping to the character's right (viewer's left)
    fr = [(-54, -14, 1.0), (-34, -17, 1.1), (-14, -19, 1.2), (4, -18, 1.2), (22, -12, 1.1), (38, 10, 1.0), (54, 14, 0.95)]
    for az0, sweep, k in fr:
        pts = []
        rad = []
        for i in range(6):
            t = i / 5
            el = 62 - 39 * t - 4 * math.sin(t * math.pi)
            pts.append(hp(az0 + sweep * t ** 1.3, el, 0.012 * (1 - 0.5 * t))[0])
            rad.append((0.047 * (1 - t) ** 0.8 + 0.006) * k)
        b.tube(pts, rad, mat='hair', segs=8, color=HAIR, color_top=HAIR_TIP, jitter=0.06)
    # side locks in front of the ears
    for s in (-1, 1):
        for az0, el0, el1, k in ((66, 34, -40, 1.0), (80, 30, -30, 0.85)):
            pts, rad = [], []
            for i in range(6):
                t = i / 5
                pts.append(hp(s * (az0 - 5 * t * t), el0 + (el1 - el0) * t, 0.012)[0])
                rad.append((0.036 * (1 - t) ** 0.7 + 0.006) * k)
            b.tube(pts, rad, mat='hair', segs=8, color=HAIR, color_top=HAIR_TIP, jitter=0.06)
    # nape locks
    for az0 in (118, 142, 166, 194, 218, 242):
        pts, rad = [], []
        for i in range(5):
            t = i / 4
            pts.append(hp(az0 + 4 * t, 8 - 52 * t, 0.014 + 0.012 * t)[0])
            rad.append(0.04 * (1 - t) ** 0.7 + 0.007)
        b.tube(pts, rad, mat='hair', segs=8, color=HAIR, color_top=HAIR_TIP, jitter=0.06)
    # short ponytail with a teal tie
    base = hp(180, -8, 0.0)[0]
    pts = [base + Vector(v) for v in ((0, -0.02, 0.0), (0, 0.045, 0.012), (0, 0.095, -0.012), (0, 0.125, -0.07), (0, 0.128, -0.13))]
    b.tube(pts, [0.036, 0.04, 0.05, 0.043, 0.008], mat='hair', segs=12, color=HAIR, color_top=HAIR_TIP)
    with b.at(base + Vector((0, 0.04, 0.01)), (78, 0, 0)):
        torus(b, 0.036, 0.011, 0, mat='paint', segs=16, color=TEAL)


# ================================================================ HAT
def build_hat():
    b = B('hat', 5)
    R_IN, R_OUT = 0.2, 0.372

    def wave(c):
        r = math.hypot(c.x, c.y)
        if r <= R_IN:
            return c
        w = min(1.0, (r - R_IN) / (R_OUT - R_IN))
        a = math.atan2(c.y, c.x)
        c.z += 0.016 * (w ** 1.4) * math.sin(3 * a + 0.9) + 0.007 * w * math.sin(5 * a + 2.0) - 0.02 * w * w
        return c

    straw = (1.0, 0.97, 0.9)
    with b.at(rot=(-17, 0, 0), scale=(HEAD_K, HEAD_K, HEAD_K)):
        b.deform = wave
        ctrl = [(0.18, -0.046), (0.275, -0.050), (0.362, -0.054), (0.374, -0.047), (0.362, -0.040), (0.275, -0.036),
                (0.206, -0.030)]
        b.lathe(ctrl, mat='straw', segs=36, color=mul(straw, 0.97))
        torus(b, 0.37, 0.0085, -0.047, n=6, mat='straw', segs=36, color=mul(straw, 0.8))
        b.deform = None
        crown = smooth_profile([(0.207, -0.034), (0.203, 0.0), (0.196, 0.04), (0.176, 0.08), (0.13, 0.108), (0.068, 0.121), (0, 0.124)], 3)
        b.lathe(crown, mat='straw', segs=36, color=straw)
        # ribbon band + small bow at the back-left
        b.lathe([(0.2085, -0.03), (0.2115, -0.027), (0.2065, 0.014), (0.2025, 0.017)], mat='paint', segs=36, color=TEAL)
        with b.at((0.126, 0.168, -0.008), (0, 0, -37)):
            b.blob((0.03, 0.014, 0.02), loc=(-0.028, 0.004, 0.004), rot=(0, -18, 0), mat='paint', subdiv=2, color=TEAL)
            b.blob((0.03, 0.014, 0.02), loc=(0.028, 0.004, 0.004), rot=(0, 18, 0), mat='paint', subdiv=2, color=TEAL)
            b.blob((0.012, 0.014, 0.014), loc=(0, 0.004, 0.002), mat='paint', subdiv=2, color=mul(TEAL, 0.8))
    return b.build(sharp_angle=60)


# ================================================================ TORSO
TORSO_SY = 0.9
TORSO_PROF = smooth_profile([(0, -0.072), (0.085, -0.066), (0.128, -0.035), (0.139, 0.02), (0.134, 0.09), (0.128, 0.17),
                             (0.131, 0.238), (0.123, 0.28), (0.094, 0.312), (0.058, 0.328), (0.05, 0.345), (0, 0.345)], 3)


def rT(z):
    P = TORSO_PROF
    if z <= P[0][1]:
        return P[0][0]
    for i in range(len(P) - 1):
        if P[i][1] <= z <= P[i + 1][1] and P[i + 1][1] > P[i][1]:
            t = (z - P[i][1]) / (P[i + 1][1] - P[i][1])
            return P[i][0] * (1 - t) + P[i + 1][0] * t
    return P[-1][0]


def S(a_deg, z, off):
    a = math.radians(a_deg)
    r = rT(z) + off
    return Vector((r * math.cos(a), TORSO_SY * r * math.sin(a), z))


def strap_pt(x, z, side, off):
    """Point on the torso at lateral position x (side -1 front, +1 back) + outward normal."""
    r = rT(z)
    dr = (rT(z + 0.004) - rT(z - 0.004)) / 0.008
    xx = max(-r * 0.999, min(r * 0.999, x))
    y = side * TORSO_SY * math.sqrt(max(r * r - xx * xx, 0.0))
    n = Vector((xx / max(r, 1e-4), y / (TORSO_SY ** 2 * max(r, 1e-4)), -dr)).normalized()
    return Vector((xx, y, z)) + n * off, n


def bandana(b):
    t = b._new()
    uv, col, _ = b._layers(t)
    nu, nv = 12, 8
    g = []
    for i in range(nu + 1):
        u = -1 + 2 * i / nu
        row = []
        for j in range(nv + 1):
            v = 0.04 + 0.96 * j / nv
            a = -90 + u * (50 * v ** 0.85 + 3)
            z = 0.224 + 0.098 * v
            border = i in (0, nu) or j == 0
            p = S(a, z, -0.004 if border else 0.0125 + 0.004 * math.sin(v * math.pi))
            row.append((t.verts.new(p), v))
        g.append(row)
    for i in range(nu):
        for j in range(nv):
            f = t.faces.new((g[i][j][0], g[i + 1][j][0], g[i + 1][j + 1][0], g[i][j + 1][0]))
            for l, vv in zip(f.loops, (g[i][j][1], g[i + 1][j][1], g[i + 1][j + 1][1], g[i][j + 1][1])):
                l[uv].uv = (l.vert.co.x * 4, l.vert.co.z * 4)
                c = lerp3(RED_D, RED, min(1.0, vv * 1.6))
                l[col] = (*c, 1)
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    t.normal_update()
    b._emit(t, 'cloth', (0, 0, 0), (0, 0, 0))


def build_torso():
    b = B('torso', 7)
    b.lathe(TORSO_PROF, scale=(1, TORSO_SY, 1), mat='cloth', segs=32, color=SHIRT)
    # neck
    b.tube([(0, 0, 0.30), (0, 0, 0.375)], 0.05, mat='skin', segs=16, color=SKIN_D)
    # overalls: waist-high shell, bib, pocket, straps, buttons
    shell = smooth_profile([(0, -0.08), (0.09, -0.074), (0.136, -0.038), (0.148, 0.02), (0.144, 0.075), (0.141, 0.098)], 4) + [(0.133, 0.1), (0.13, 0.09)]
    b.lathe(shell, scale=(1, TORSO_SY, 1), mat='cloth', segs=32, color=DENIM)
    patch(b, S, -90 - 37, -90 + 37, 0.07, 0.238, 0.009, 'cloth', DENIM, nu=16, nv=12, corner=0.5)
    patch(b, S, -90 - 16, -90 + 16, 0.118, 0.19, 0.0155, 'cloth', DENIM_D, nu=10, nv=8, sink=-0.006, margin=0.1)
    patch(b, S, -90 - 17, -90 + 17, 0.178, 0.196, 0.0185, 'cloth', DENIM_L, nu=10, nv=4, sink=-0.012, margin=0.12)
    # back panel
    patch(b, S, 90 - 26, 90 + 26, 0.07, 0.17, 0.009, 'cloth', DENIM, nu=12, nv=8, corner=0.5)
    for s in (-1, 1):
        pts, nrm = [], []
        zs_f = [0.20, 0.235, 0.265, 0.29, 0.306, 0.316]
        for z in zs_f:                                   # up the front
            p, n = strap_pt(s * 0.082, z, -1, 0.0085)
            pts.append(p)
            nrm.append(n)
        zs_b = [0.316, 0.306, 0.288, 0.26, 0.225, 0.19, 0.155]
        for i, z in enumerate(zs_b):                      # down the back, converging
            x = s * (0.082 - 0.05 * (i / (len(zs_b) - 1)))
            p, n = strap_pt(x, z, 1, 0.0085)
            pts.append(p)
            nrm.append(n)
        ribbon(b, pts, nrm, 0.036, 0.009, 'cloth', DENIM)
        # brass-ish button where the strap meets the bib
        p, n = strap_pt(s * 0.082, 0.213, -1, 0.014)
        b.blob((0.0135, 0.0055, 0.0135), loc=p, rot=aim(n), mat='metal', subdiv=3, color=srgb(236, 200, 120))
    # neckerchief: ring round the neck + a bandana triangle draped over the chest
    with b.at((0, -0.004, 0.318), (-8, 0, 0)):
        torus(b, 0.058, 0.022, 0, n=8, scale=(1, 0.95, 1), mat='cloth', segs=24, color=RED)
    bandana(b)
    return b.build(sharp_angle=70)


def build_hips():
    b = B('hips', 9)
    b.blob((0.152, 0.136, 0.098), loc=(0, 0, -0.004), mat='cloth', subdiv=3, color=DENIM)
    return b.build(sharp_angle=80)


# ================================================================ LIMBS
def build_upper_arm(name, s):
    b = B(name, 11)
    b.tube([(0, 0, 0), (0, 0, -UPPER_L * 0.5), (0, 0, -UPPER_L)], [0.053, 0.05, 0.047], mat='cloth', segs=16, color=SHIRT)
    torus(b, 0.047, 0.013, -UPPER_L + 0.028, n=10, mat='cloth', segs=18, color=SHIRT_L)   # rolled sleeve
    return b.build(sharp_angle=80)


def build_forearm(name, s):
    b = B(name, 12)
    b.tube([(0, 0, 0), (0, 0, -FORE_L * 0.5), (0, 0, -FORE_L)], [0.043, 0.041, 0.037], mat='skin', segs=16, color=SKIN)
    return b.build(sharp_angle=80)


def build_hand(name, s):
    """Mitten hand. Palm faces the body (-s*X), thumb points forward (-Y)."""
    b = B(name, 13)

    def col(co):
        return lerp3(SKIN, lerp3(SKIN, BLUSH, 0.25), max(0.0, min(1.0, (-co.z) / 0.06)))

    b.blob((0.036, 0.05, 0.058), loc=(0, -0.004, -0.05), mat='skin', subdiv=3, color=col)
    b.blob((0.019, 0.022, 0.03), loc=(-s * 0.012, -0.046, -0.036), rot=(-28, 0, 0), mat='skin', subdiv=2, color=SKIN)
    return b.build(sharp_angle=80)


def build_thigh(name, s):
    b = B(name, 14)
    b.tube([(0, 0, 0), (0, 0, -THIGH_L * 0.5), (0, 0, -THIGH_L)], [0.079, 0.076, 0.071], mat='cloth', segs=18, color=DENIM)
    return b.build(sharp_angle=80)


def build_shin(name, s):
    b = B(name, 15)
    b.tube([(0, 0, 0), (0, 0, -0.09), (0, 0, -0.165)], [0.071, 0.07, 0.072], mat='cloth', segs=18, color=DENIM)
    torus(b, 0.071, 0.0165, -0.168, n=10, mat='cloth', segs=20, color=DENIM_L)           # rolled cuff
    return b.build(sharp_angle=80)


def build_foot(name, s):
    b = B(name, 16)
    lea = (1.0, 0.95, 0.9)
    b.tube([(0, 0, 0.085), (0, 0, -0.03)], 0.061, mat='leather', segs=16, color=lea)      # shaft
    torus(b, 0.061, 0.013, 0.085, n=8, mat='leather', segs=18, color=mul(lea, 1.25))     # cuff

    def boot(c):
        # bulbous toe, lower heel
        t = max(0.0, min(1.0, (-c.y) / 0.115))
        if c.z > 0:
            c.z *= 0.78 + 0.3 * t
        c.x *= 1.0 + 0.1 * t
        return c

    b.blob((0.068, 0.118, 0.072), loc=(0, -0.042, -0.058), mat='leather', subdiv=4, flatten_bottom=-0.62, deform=boot, color=lea)
    # toe cap seam

    b.tube([(-0.066, -0.075, -0.075), (-0.05, -0.088, -0.03), (0, -0.094, -0.008), (0.05, -0.088, -0.03), (0.066, -0.075, -0.075)],
           0.0065, mat='leather', segs=6, color=mul(lea, 0.7))

    def sole(c):
        c.z = max(-0.014, min(0.014, c.z))
        t = max(0.0, min(1.0, (-c.y) / 0.12))
        c.x *= 1.0 + 0.1 * t
        return c

    b.blob((0.075, 0.126, 0.03), loc=(0, -0.042, -0.106), mat='leather', subdiv=3, deform=sole, color=mul(lea, 0.32))
    return b.build(sharp_angle=60)


# ================================================================ TOOLS
def build_hoe():
    b = B('tool_hoe', 21)
    b.tube([(0, 0, -0.46), (0, 0, 0.0), (0, 0, 0.4), (0, 0, 0.66)], [0.0185, 0.017, 0.016, 0.0155], mat='wood_light', segs=12)
    b.lathe([(0.0185, 0.60), (0.0215, 0.605), (0.0205, 0.69), (0.016, 0.70), (0, 0.702)], mat='metal_dark', segs=16)
    b.tube([(0, 0, 0.685), (0, -0.02, 0.725), (0, -0.062, 0.737), (0, -0.1, 0.716), (0, -0.118, 0.672)],
           [0.0105, 0.0095, 0.009, 0.009, 0.0095], mat='metal_dark', segs=10)
    b.box((0.155, 0.008, 0.125), loc=(0, -0.127, 0.612), rot=(-10, 0, 0), mat='metal_dark', bevel=0.003, taper=(0.74, 1.0), grain=None)
    b.box((0.05, 0.014, 0.03), loc=(0, -0.122, 0.668), rot=(-10, 0, 0), mat='metal_dark', bevel=0.004, grain=None)
    return b.build(sharp_angle=50)


def build_can():
    b = B('tool_watering_can', 22)
    m = (1.0, 1.0, 1.0)
    body = [(0, -0.335), (0.098, -0.335), (0.106, -0.327), (0.112, -0.30), (0.103, -0.115), (0.099, -0.104), (0.094, -0.104),
            (0.097, -0.118), (0.104, -0.30), (0.098, -0.318), (0, -0.318)]
    b.lathe(body, mat='metal', segs=32, color=m)
    torus(b, 0.101, 0.007, -0.104, n=8, mat='metal', segs=32, color=mul(m, 0.9))
    for z in (-0.29, -0.16):
        b.lathe([(0.1125 - (z + 0.30) * 0.047 - 0.004, z - 0.008), (0.1125 - (z + 0.30) * 0.047 + 0.0035, z - 0.005),
                 (0.1125 - (z + 0.30) * 0.047 + 0.0035, z + 0.005), (0.1125 - (z + 0.30) * 0.047 - 0.004, z + 0.008)], mat='metal', segs=32, color=mul(m, 0.85))
    # half cover over the front of the opening
    b.blob((0.094, 0.094, 0.03), loc=(0, 0, -0.108), mat='metal', subdiv=3, color=mul(m, 0.95),
           deform=lambda c: Vector((c.x, min(c.y, -0.012), max(c.z, 0.0))))
    # top carry handle (apex at the origin) + back handle
    b.tube([(0, -0.092, -0.106), (0, -0.07, -0.04), (0, -0.03, -0.006), (0, 0, 0.0), (0, 0.03, -0.006), (0, 0.07, -0.04), (0, 0.094, -0.106)],
           0.0095, mat='metal', segs=10, color=mul(m, 0.9))
    b.tube([(0, 0.098, -0.125), (0, 0.15, -0.135), (0, 0.178, -0.19), (0, 0.16, -0.255), (0, 0.108, -0.285)], 0.0095,
           mat='metal', segs=10, color=mul(m, 0.9))
    # spout + brace + rose
    sp = [Vector((0, -0.085, -0.285)), Vector((0, -0.17, -0.245)), Vector((0, -0.25, -0.175)), Vector((0, -0.325, -0.1))]
    b.tube(sp, [0.027, 0.023, 0.019, 0.016], mat='metal', segs=14, color=m)
    b.tube([(0, -0.094, -0.13), (0, -0.225, -0.195)], 0.006, mat='metal', segs=8, color=mul(m, 0.85))
    d = (sp[-1] - sp[-2]).normalized()
    ang = math.degrees(math.atan2(-d.y, d.z))
    with b.at(sp[-1] - d * 0.006, (ang, 0, 0)):
        b.lathe([(0.0155, 0), (0.026, 0.018), (0.046, 0.042), (0.049, 0.047), (0.047, 0.053), (0.03, 0.058), (0, 0.06)], mat='metal', segs=24, color=m)
        for k in range(7):
            a = k * math.pi * 2 / 6
            rr = 0.0 if k == 6 else 0.026
            b.blob((0.0042, 0.0042, 0.002), loc=(rr * math.cos(a), rr * math.sin(a), 0.0585 if k == 6 else 0.0565), mat='metal_dark', subdiv=1, color=WHITE)
    tip = sp[-1] + d * 0.056
    obj = b.build(sharp_angle=50)
    kit.marker('spout_tip', tip, parent=obj)
    return obj


def build_seed_bag():
    b = B('tool_seed_bag', 23)

    def sack(c):
        # pear shaped: pinch toward the neck
        t = max(0.0, min(1.0, (c.z + 0.02) / 0.1))
        k = 1.0 - 0.55 * t * t
        return Vector((c.x * k, c.y * k, c.z))

    b.blob((0.088, 0.072, 0.095), loc=(0, 0, -0.105), mat='cloth', subdiv=4, noise_amp=0.07, noise_scale=2.2, seed=4,
           flatten_bottom=-0.78, deform=sack, color=mul(SACK, 0.92), color_top=SACK)
    ruf = lambda a, z: 1.0 + 0.09 * math.sin(7 * a + 1.0) * max(0.0, min(1.0, (z + 0.0) / 0.04))
    b.lathe([(0.036, -0.03), (0.03, -0.008), (0.031, 0.006), (0.043, 0.03), (0.053, 0.05), (0.0495, 0.052), (0.04, 0.032), (0.024, 0.012), (0, 0.012)],
            mat='cloth', segs=28, color=SACK, radial=ruf)
    torus(b, 0.0325, 0.006, 0.0, n=8, mat='rope', segs=20)
    b.tube([(0.02, -0.027, 0.0), (0.035, -0.045, -0.02), (0.04, -0.05, -0.06)], 0.0045, mat='rope', segs=8)
    b.tube([(-0.012, -0.031, 0.0), (-0.02, -0.052, -0.025), (-0.015, -0.058, -0.075)], 0.0045, mat='rope', segs=8)
    b.blob(0.008, loc=(0.04, -0.05, -0.064), mat='rope', subdiv=2)
    b.blob(0.008, loc=(-0.015, -0.058, -0.079), mat='rope', subdiv=2)
    # seeds heaped in the opening
    seed = srgb(214, 176, 96)
    b.blob((0.034, 0.034, 0.02), loc=(0, 0, 0.022), mat='plant', subdiv=2, color=mul(seed, 0.8))
    for k in range(14):
        a = k * 2.4
        r = 0.006 + 0.022 * ((k * 0.37) % 1.0)
        b.blob((0.0075, 0.005, 0.0045), loc=(r * math.cos(a), r * math.sin(a), 0.036 - r * 0.25), rot=(k * 37, k * 53, k * 71), mat='plant',
               subdiv=1, color=mul(seed, 0.85 + 0.3 * ((k * 0.61) % 1.0)))
    # a little stitched patch
    return b.build(sharp_angle=70)


def build_basket():
    b = B('tool_basket', 24)
    top, bot = -0.2, -0.36
    r_top, r_bot = 0.2, 0.135
    n = 7
    for k in range(n):
        z = bot + 0.012 + (top - bot - 0.02) * k / (n - 1)
        r = r_bot + (r_top - r_bot) * ((z - bot) / (top - bot)) ** 0.8
        ph = (k % 2) * math.pi
        wv = (lambda p: (lambda a, zz: 1.0 + 0.024 * math.sin(10 * a + p)))(ph)
        torus(b, r, 0.0148, z, n=6, mat='straw', segs=40, color=(1, 0.96, 0.88), jitter=0.1, radial=wv)
    # vertical stakes (inside the weave), floor, rim
    for k in range(10):
        a = (k + 0.5) * math.pi * 2 / 10
        b.tube([(r_bot * 0.985 * math.cos(a), r_bot * 0.985 * math.sin(a), bot + 0.006), (r_top * 0.985 * math.cos(a), r_top * 0.985 * math.sin(a), top)],
               0.0065, mat='straw', segs=6, color=(0.8, 0.74, 0.62))
    b.lathe([(0, bot - 0.004), (r_bot - 0.005, bot - 0.004), (r_bot + 0.003, bot + 0.004), (r_bot - 0.004, bot + 0.012), (0, bot + 0.012)], mat='straw', segs=32, color=(0.85, 0.8, 0.7))
    inner = [(r_bot - 0.002, bot + 0.011), (r_top - 0.006, top)]
    b.lathe(list(reversed(inner)), mat='straw', segs=32, color=(0.72, 0.66, 0.54))
    torus(b, r_top + 0.002, 0.0155, top + 0.004, n=10, mat='straw', segs=40, color=(0.92, 0.84, 0.7))
    # arched handle: apex at the origin
    R = 0.2
    for off in (-0.008, 0.008):
        pts = [(R * math.cos(t), off * math.cos(3 * t), top + R * math.sin(t) * (0 - top) / R) for t in [math.pi * i / 12 for i in range(13)]]
        b.tube(pts, 0.0095, mat='straw', segs=8, color=(0.9, 0.82, 0.68))
    for s in (-1, 1):
        b.tube([(s * R, -0.018, top + 0.012), (s * (R + 0.004), 0, top + 0.03), (s * R, 0.018, top + 0.012)], 0.008, mat='rope', segs=8)
    return b.build(sharp_angle=60)


# ================================================================ ASSEMBLE
character = kit.marker('character', (0, 0, 0))
hips = kit.set_parent(build_hips(), character, (0, 0, HIPS_Z))
torso = kit.set_parent(build_torso(), hips, (0, 0, WAIST_DZ))
head = kit.set_parent(build_head(), torso, (0, 0, NECK_DZ))
hat = kit.set_parent(build_hat(), head, HAT_PIVOT)
parts = {'hips': hips, 'torso': torso, 'head': head, 'hat': hat}
for side, s in (('l', 1), ('r', -1)):
    ua = kit.set_parent(build_upper_arm(f'upper_arm_{side}', s), torso, (s * SHOULDER[0], SHOULDER[1], SHOULDER[2]))
    fa = kit.set_parent(build_forearm(f'forearm_{side}', s), ua, (0, 0, -UPPER_L))
    ha = kit.set_parent(build_hand(f'hand_{side}', s), fa, (0, 0, -FORE_L))
    gr = kit.marker(f'grip_{side}', (0, -0.004, -0.05), parent=ha)
    th = kit.set_parent(build_thigh(f'thigh_{side}', s), hips, (s * HIP_X, 0, HIPJ_DZ))
    sh = kit.set_parent(build_shin(f'shin_{side}', s), th, (0, 0, -THIGH_L))
    ft = kit.set_parent(build_foot(f'foot_{side}', s), sh, (0, 0, -SHIN_L))
    parts.update({ua.name: ua, fa.name: fa, ha.name: ha, gr.name: gr, th.name: th, sh.name: sh, ft.name: ft})

tools = {'tool_hoe': build_hoe(), 'tool_watering_can': build_can(), 'tool_seed_bag': build_seed_bag(), 'tool_basket': build_basket()}
bpy.context.view_layer.update()

char_objs = [character] + kit._descend(character.children)
print('CHAR_TRIS', kit.tri_count(char_objs), {o.name: kit.tri_count([o]) for o in char_objs if o.type == 'MESH'})
for n, o in tools.items():
    print('TOOL_TRIS', n, kit.tri_count([o]), [round(v, 3) for v in o.dimensions])
mats = sorted({m.name for o in char_objs + list(tools.values()) if o.type == 'MESH' for m in o.data.materials})
print('MATERIALS', mats)
for o in char_objs:
    print('PIVOT', o.name, 'parent', o.parent.name if o.parent else None, [round(v, 4) for v in o.location])


# ================================================================ PREVIEWS
def shot(name, focus, az=0, el=10, zoom=1.0, only=None, size=(900, 900), floor_z=0.0, pad=1.0):
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    fobjs = kit._descend(focus)
    pts = []
    for o in fobjs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    rad = (hi - lo).length / 2 * pad
    hidden = []
    if only is not None:
        keep = set(kit._descend(only))
        for o in bpy.data.objects:
            if o not in keep and not o.hide_render:
                o.hide_render = True
                hidden.append(o)
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = 70
    d = rad / math.tan(math.radians(11.5)) / zoom
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
    if floor_z is not None:
        fm = bpy.data.meshes.new('_pv_floor')
        fb = bmesh.new()
        bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=12)
        fb.to_mesh(fm)
        fb.free()
        floor = bpy.data.objects.new('_pv_floor', fm)
        floor.location = (c.x, c.y, floor_z - 0.001)
        sc.collection.objects.link(floor)
        fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
        try:
            fmat.use_nodes = True
            bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            bs.inputs['Base Color'].default_value = (0.26, 0.36, 0.17, 1)
            bs.inputs['Roughness'].default_value = 0.9
        except Exception:
            pass
        fm.materials.append(fmat)
        extra.append(floor)
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
    for o in hidden:
        o.hide_render = False


def pose(d):
    for n, r in d.items():
        parts[n].rotation_euler = Euler([math.radians(a) for a in r], 'XYZ')
    bpy.context.view_layer.update()


def unpose():
    for o in parts.values():
        o.rotation_euler = Euler((0, 0, 0), 'XYZ')
    bpy.context.view_layer.update()


if PREV:
    C = [character]
    shot('char_front', C, az=0, el=6, only=C)
    shot('char_34', C, az=35, el=14, only=C)
    shot('char_side', C, az=90, el=6, only=C)
    shot('char_back', C, az=180, el=10, only=C)
    shot('char_game_cam', C, az=25, el=42, only=C)
    shot('char_face', [head], az=12, el=4, only=C, floor_z=None, zoom=1.05)
    shot('char_face_front', [head], az=0, el=0, only=C, floor_z=None, zoom=1.25)
    # posed tests
    pose({'thigh_l': (-38, 0, 0), 'shin_l': (22, 0, 0), 'thigh_r': (30, 0, 0), 'shin_r': (55, 0, 0), 'foot_r': (15, 0, 0),
          'upper_arm_r': (-34, 0, 0), 'forearm_r': (-45, 0, 0), 'upper_arm_l': (28, 0, 0), 'forearm_l': (-20, 0, 0),
          'torso': (4, 0, 6), 'head': (-3, 0, -5)})
    shot('pose_walk_34', C, az=40, el=12, only=C)
    shot('pose_walk_side', C, az=90, el=6, only=C)
    unpose()
    hoe = tools['tool_hoe']
    hoe.parent = parts['grip_r']
    hoe.rotation_euler = Euler((math.radians(-90), 0, 0), 'XYZ')
    pose({'upper_arm_r': (-105, 0, 10), 'forearm_r': (-40, 0, 0), 'upper_arm_l': (-80, 0, -30), 'forearm_l': (-60, 0, 0),
          'torso': (-10, 0, 0), 'thigh_l': (-18, 0, 0), 'shin_l': (18, 0, 0), 'thigh_r': (14, 0, 0), 'shin_r': (10, 0, 0)})
    shot('pose_hoe_34', C + [hoe], az=45, el=10, only=C + [hoe])
    shot('pose_hoe_side', C + [hoe], az=90, el=5, only=C + [hoe])
    pose({'forearm_l': (-125, 0, 0), 'forearm_r': (-125, 0, 0), 'shin_l': (120, 0, 0), 'shin_r': (120, 0, 0),
          'upper_arm_l': (0, 0, 0), 'upper_arm_r': (0, 0, 0), 'thigh_l': (-80, 0, 0), 'thigh_r': (-80, 0, 0), 'torso': (0, 0, 0)})
    shot('pose_joint_limits', C, az=70, el=8, only=C)
    unpose()
    hoe.parent = None
    hoe.rotation_euler = Euler((0, 0, 0), 'XYZ')
    hoe.location = (0, 0, 0)
    bpy.context.view_layer.update()
    for n, o in tools.items():
        shot(n, [o], az=55, el=18, only=[o], floor_z=None, size=(700, 700))
        if n != 'tool_hoe':
            shot(n + '_b', [o], az=-120, el=30, only=[o], floor_z=None, size=(700, 700))

# ================================================================ EXPORT
unpose()
for o in tools.values():
    assert o.parent is None and tuple(o.location) == (0, 0, 0)
out = os.path.join(ROOT, 'public', 'models', 'character.glb')
kit.export_glb(out, [character] + list(tools.values()))
