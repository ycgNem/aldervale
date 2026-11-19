"""Steward-progression goods: raw materials, orchard goods, waste and seed packets -> public/models/goods.glb

  blender --background --factory-startup --python tools/blender/build_goods.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/goods.glb.
With group names (raw, orchard, waste, seeds) only those are built + previewed (no export).
Pass an ABSOLUTE preview dir (Blender resolves relative render paths oddly on Windows).

Conventions: see kit.py. Extra ones for this file
- item_* / seed_*: one mesh object each, origin bottom centre, front = -Y. They sit next to the goods of
  build_items.py (item_wheat ... item_chutney) and share their scale, palette and preview setup; the generic
  helpers below are copied from that file.
- Besides kit.PREVIEW names this file uses `parchment` (seed packets) and `bread` (tart pastry), which the game
  knows (src/core/materials.ts). Preview colours for the game-only names are registered below.
- Seed packet art is flat 'paint' polygons 0.6-2.5 mm proud of the paper, wound to face -Y (paint is single sided).
"""
import sys
import os
import math
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, Matrix, Euler, noise  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'goods.glb')
ITEMS_GLB = os.path.join(ROOT, 'public', 'models', 'items.glb')

# game-side materials that kit.py has no preview entry for (colours as in src/core/materials.ts)
kit.PREVIEW.update({'parchment': (0.98, 0.93, 0.80), 'bread': (1, 1, 1), 'egg': (1, 1, 1),
                    'glass_jar': (0.80, 0.90, 0.86), 'gold': (1.0, 0.72, 0.30)})
kit.ROUGH.update({'parchment': 0.88, 'bread': 0.62, 'egg': 0.45, 'glass_jar': 0.06, 'gold': 0.32})

kit.reset()
pi = math.pi
WHITE = (1.0, 1.0, 1.0)


# ================================================================ helpers (copied from build_items.py)
def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def lerp_table(T, x):
    """T: [(x, a, b, ...)] sorted by x -> interpolated tuple (a, b, ...)."""
    if x <= T[0][0]:
        return T[0][1:]
    for i in range(len(T) - 1):
        if x <= T[i + 1][0]:
            t = (x - T[i][0]) / (T[i + 1][0] - T[i][0])
            return tuple(T[i][k] * (1 - t) + T[i + 1][k] * t for k in range(1, len(T[i])))
    return T[-1][1:]


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


def aimz(d):
    """Euler degrees (XYZ) that rotate local +Z onto direction d."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(d).normalized())
    return tuple(math.degrees(a) for a in q.to_euler('XYZ'))


def basis_rot(zaxis, xhint):
    """Euler degrees for the frame whose local Z is `zaxis` and local X is as close to `xhint` as possible."""
    z = Vector(zaxis).normalized()
    x = Vector(xhint) - z * Vector(xhint).dot(z)
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    M = Matrix((x, y, z)).transposed()
    return tuple(math.degrees(a) for a in M.to_euler('XYZ'))


def raw(b, verts, faces, cols, mat='plant', loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), jitter=0.0, face_cols=None, uvs=None):
    """Emit an arbitrary small mesh with per-vertex colours (list), one colour (tuple) or per-face colours."""
    t = b._new()
    uv, col, _ = b._layers(t)
    bv = [t.verts.new(v) for v in verts]
    j = 1.0 + b.rng.uniform(-jitter, jitter) if jitter else 1.0
    for fi, f in enumerate(faces):
        try:
            face = t.faces.new([bv[i] for i in f])
        except ValueError:
            continue
        fc = face_cols[fi] if face_cols else None
        for l, i in zip(face.loops, f):
            c = fc if fc is not None else (cols[i] if isinstance(cols, list) else cols)
            l[col] = (c[0] * j, c[1] * j, c[2] * j, 1.0)
            l[uv].uv = uvs[i] if uvs else (verts[i][0], verts[i][1])
    t.normal_update()
    b._emit(t, mat, loc, rot, scale)


def loft(b, st, mat, color=(1, 1, 1), segs=24, radial=None, jitter=0.0, uv_scale=1.0):
    """Elliptical tube along local +Y. st: [(y, rx, rz[, cz])]; rx<=0 makes a pole. Trace it like a lathe
    profile: travelling +Y on the outside gives outward normals, so start at the -Y end going outward."""
    t = b._new()
    uv, _, _ = b._layers(t)
    rings = []
    arc = [0.0]
    for i, s in enumerate(st):
        y, rx, rz = s[0], s[1], s[2]
        cz = s[3] if len(s) > 3 else 0.0
        if i:
            arc.append(arc[-1] + math.hypot(y - st[i - 1][0], rx - st[i - 1][1]))
        if rx <= 1e-6:
            rings.append([t.verts.new((0, y, cz))])
        else:
            ring = []
            for k in range(segs):
                a = 2 * pi * k / segs
                m = radial(a, y) if radial else 1.0
                ring.append(t.verts.new((rx * m * math.cos(a), y, cz + rz * m * math.sin(a))))
            rings.append(ring)
    circ = 2 * pi * max(s[1] for s in st)
    for i in range(len(st) - 1):
        A, Bn = rings[i], rings[i + 1]
        for k in range(segs):
            j = (k + 1) % segs
            u0, u1 = k / segs * circ * uv_scale, (k + 1) / segs * circ * uv_scale
            va, vb = arc[i] * uv_scale, arc[i + 1] * uv_scale
            if len(A) == 1 and len(Bn) == 1:
                continue
            if len(A) == 1:
                f = t.faces.new((A[0], Bn[k], Bn[j]))
                dat = [((u0 + u1) / 2, va), (u0, vb), (u1, vb)]
            elif len(Bn) == 1:
                f = t.faces.new((A[j], A[k], Bn[0]))
                dat = [(u1, va), (u0, va), ((u0 + u1) / 2, vb)]
            else:
                f = t.faces.new((A[j], A[k], Bn[k], Bn[j]))
                dat = [(u1, va), (u0, va), (u0, vb), (u1, vb)]
            for l, w in zip(f.loops, dat):
                l[uv].uv = w
    t.normal_update()
    b._color(t, color, None, jitter)
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def plathe(b, profile, a0, a1, segs, mat, color, radial=None, cap_color=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Partial lathe (a pie with a slice missing): closed (r,z) profile that starts and ends on the
    axis, revolved from a0 to a1 degrees, with flat cut faces at both ends."""
    t = b._new()
    uv, col, _ = b._layers(t)
    rings = []
    for k in range(segs + 1):
        a = math.radians(a0 + (a1 - a0) * k / segs)
        ring = []
        for r, z in profile:
            m = radial(a, z) if (radial and 0 < k < segs) else 1.0
            ring.append((r * m * math.cos(a), r * m * math.sin(a), z))
        rings.append(ring)
    np_ = len(profile)
    axis = {}

    def V(k, i):
        r, z = profile[i]
        if r <= 1e-6:
            if i not in axis:
                axis[i] = t.verts.new((0, 0, z))
            return axis[i]
        key = (k, i)
        if key not in axis:
            axis[key] = t.verts.new(rings[k][i])
        return axis[key]

    side = []
    for k in range(segs):
        for i in range(np_ - 1):
            vs = []
            for v in (V(k, i), V(k + 1, i), V(k + 1, i + 1), V(k, i + 1)):
                if v not in vs:
                    vs.append(v)
            if len(vs) >= 3:
                side.append(t.faces.new(vs))
    caps = []
    for k in (0, segs):
        vs = []
        for i in range(np_):
            v = V(k, i)
            if v not in vs:
                vs.append(v)
        caps.append(t.faces.new(vs))
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    res = bmesh.ops.triangulate(t, faces=caps)
    capset = set(res['faces'])
    for f in t.faces:
        for l in f.loops:
            co = l.vert.co
            l[uv].uv = (math.atan2(co.y, co.x) * 0.1, co.z) if f not in capset else (math.hypot(co.x, co.y), co.z)
            if f in capset and cap_color is not None:
                c = cap_color(co) if callable(cap_color) else cap_color
            else:
                c = color(co) if callable(color) else color
            l[col] = (*c, 1.0)
    t.normal_update()
    b._emit(t, mat, loc, rot)


def feather(b, loc, rot, L, w, th, mat='plant', color=(1, 1, 1), color_top=None, segs=8, jitter=0.0):
    """Flat leaf-shaped solid (closed, so it works single sided). Base at loc, grows along local +Z."""
    prof = [(0, 0), (0.55 * w, 0.14 * L), (w, 0.5 * L), (0.78 * w, 0.82 * L), (0.3 * w, 0.97 * L), (0, L)]
    b.lathe(prof, loc=loc, rot=rot, scale=(1, th / w, 1), mat=mat, segs=segs, color=color, color_top=color_top, jitter=jitter)


def disc_leaf(b, r, loc, rot, c_in, c_mid, c_out, lobes=5, amp=0.14, n=10, cup=0.12, notch=0.5, wav=0.05, jitter=0.06, mat='plant'):
    """Round / lobed leaf lying in the local XY plane, hub at the origin, notch toward -X."""
    ph = b.rng.uniform(0, 6.28)
    verts = [(0, 0, 0)]
    cols = [c_in]
    for ring, (s, zc) in enumerate(((0.55, 0.045), (1.0, -cup))):
        for i in range(n):
            th = 2 * pi * i / n
            rr = r * (1 - amp + amp * math.cos(lobes * th)) if lobes else r
            rr *= 1 - notch * math.exp(-((th - pi) / 0.42) ** 2)
            z = r * zc + (r * wav * math.sin(3 * th + ph) if ring == 1 else 0.0)
            verts.append((rr * s * math.cos(th), rr * s * math.sin(th), z))
            cols.append(c_mid if ring == 0 else c_out)
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    faces += [(1 + i, 1 + n + i, 1 + n + (i + 1) % n, 1 + (i + 1) % n) for i in range(n)]
    raw(b, verts, faces, cols, mat, loc, rot, jitter=jitter)


def ntris(b):
    return sum(len(f.verts) - 2 for f in b.bm.faces)


def bow(b, c, out, r=0.0042, s=1.0, mat='rope', color=WHITE, segs=5):
    """Little tied bow at c, facing direction `out` (horizontal)."""
    o = Vector(out).normalized()
    side = Vector((-o.y, o.x, 0))
    c = Vector(c)
    for sg in (-1, 1):
        pts = [c, c + side * sg * 0.022 * s + Vector((0, 0, 0.012 * s)) + o * 0.004, c + side * sg * 0.03 * s + o * 0.006,
               c + side * sg * 0.02 * s - Vector((0, 0, 0.008 * s)) + o * 0.005, c + o * 0.002]
        b.tube(pts, r * 0.85, mat=mat, segs=segs, color=color)
        tail = [c, c + side * sg * 0.012 * s - Vector((0, 0, 0.022 * s)) + o * 0.008, c + side * sg * 0.02 * s - Vector((0, 0, 0.046 * s)) + o * 0.006]
        b.tube(tail, r * 0.85, mat=mat, segs=segs, color=color)
    b.blob(r * 2.0, loc=c + o * 0.003, mat=mat, subdiv=2, color=color)


# ================================================================ helpers (new)
def raw2(b, verts, faces, cols, mat='paint', loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), uvs=None, face_cols=None,
         ref=None, facing=None, jitter=0.0):
    """Like raw(), but fixes the winding: faces are flipped to look along `facing`, or away from the point `ref`."""
    t = b._new()
    uv, col, _ = b._layers(t)
    bv = [t.verts.new(v) for v in verts]
    j = 1.0 + b.rng.uniform(-jitter, jitter) if jitter else 1.0
    made = []
    for fi, f in enumerate(faces):
        try:
            face = t.faces.new([bv[i] for i in f])
        except ValueError:
            continue
        fc = face_cols[fi] if face_cols else None
        for l, i in zip(face.loops, f):
            c = fc if fc is not None else (cols[i] if isinstance(cols, list) else cols)
            l[col] = (c[0] * j, c[1] * j, c[2] * j, 1.0)
            l[uv].uv = uvs[i] if uvs else (verts[i][0], verts[i][2])
        made.append(face)
    t.normal_update()
    bad = []
    for face in made:
        if facing is not None:
            if face.normal.dot(Vector(facing)) < 0:
                bad.append(face)
        elif ref is not None:
            if face.normal.dot(face.calc_center_median() - Vector(ref)) < 0:
                bad.append(face)
    if bad:
        bmesh.ops.reverse_faces(t, faces=bad)
    t.normal_update()
    b._emit(t, mat, loc, rot, scale)


def dirv(yaw, el):
    """Unit vector: yaw degrees from +X toward +Y, el degrees above the ground."""
    y, e = math.radians(yaw), math.radians(el)
    return Vector((math.cos(e) * math.cos(y), math.cos(e) * math.sin(y), math.sin(e)))


def n3(x, y=0.0, z=0.0):
    return noise.noise(Vector((x, y, z)))


def hull2(pts):
    """Convex hull (counter-clockwise) of 2D points."""
    P = sorted(set((round(p[0], 6), round(p[1], 6)) for p in pts))

    def cross(o, a, c):
        return (a[0] - o[0]) * (c[1] - o[1]) - (a[1] - o[1]) * (c[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def broad_leaf(b, L, W, loc, rot, bend=30, fold=14, segs=7, shape=None, c_rib=(1, 1, 1), c_mid=(1, 1, 1), c_edge=(1, 1, 1),
               c_tip=None, wave=0.0, mat='plant', jitter=0.06):
    """Leaf with a painted midrib and wavy margins. Same frame as Builder.leaf: base at the origin, grows along
    +Z, droops toward +X by `bend` degrees."""
    if shape is None:
        def shape(u):
            return max(math.sin(pi * (u ** 0.7)) ** 0.6, 0.1)
    j = 1 + b.rng.uniform(-jitter, jitter)
    ph = b.rng.uniform(0, 6.28)
    verts, cols, faces = [], [], []
    x = z = ang = 0.0
    step = L / segs
    fr = math.radians(fold)
    for i in range(segs + 1):
        u = i / segs
        w = W * 0.5 * shape(u)
        nx_, nz_ = -math.cos(ang), math.sin(ang)
        for s in (-1, -0.14, 0, 0.14, 1):
            lift = math.sin(fr) * w * abs(s) ** 1.3
            if abs(s) == 1:
                lift += wave * W * math.sin(u * 11 + ph + (0 if s < 0 else 2.2))
            verts.append((x + nx_ * lift, math.cos(fr) * w * s, z + nz_ * lift))
            c = c_rib if s == 0 else (c_mid if abs(s) < 0.5 else c_edge)
            if c_tip is not None:
                c = mix(c, c_tip, smooth(0.55, 1.0, u))
            cols.append(mul(c, j))
        ang += math.radians(bend) / segs
        x += math.sin(ang) * step
        z += math.cos(ang) * step
    for i in range(segs):
        for k in range(4):
            a = i * 5 + k
            faces.append((a, a + 1, a + 6, a + 5))
    raw(b, verts, faces, cols, mat, loc, rot)


def jag_leaf(b, L, W, loc, rot, bend=25, fold=24, n=9, c_rib=(1, 1, 1), c_edge=(1, 1, 1), c_tip=(1, 1, 1), mat='plant'):
    """Spiny thistle leaf: the outline zig-zags between lobes and notches. Same frame as Builder.leaf."""
    verts, cols, faces = [], [], []
    x = z = ang = 0.0
    step = L / n
    fr = math.radians(fold)
    for i in range(n + 1):
        u = i / n
        env = math.sin(pi * (0.08 + 0.92 * u) ** 0.8) ** 0.7
        lobe = i % 2 == 1
        w = W * 0.5 * env * (1.0 if lobe else 0.34)
        nx_, nz_ = -math.cos(ang), math.sin(ang)
        fwd = step * 0.35 if lobe else 0.0            # lobes sweep forward
        for s in (-1, 0, 1):
            lift = math.sin(fr) * w * abs(s)
            verts.append((x + nx_ * lift + math.sin(ang) * fwd * abs(s), math.cos(fr) * w * s, z + nz_ * lift + math.cos(ang) * fwd * abs(s)))
            cols.append(c_rib if s == 0 else (c_tip if lobe else c_edge))
        ang += math.radians(bend) / n
        x += math.sin(ang) * step
        z += math.cos(ang) * step
    for i in range(n):
        for k in range(2):
            a = i * 3 + k
            faces.append((a, a + 1, a + 4, a + 3))
    raw(b, verts, faces, cols, mat, loc, rot)


# ================================================================ palette (crop colours match build_items.py)
W_STEM0, W_STEM1 = srgb(186, 150, 66), srgb(222, 176, 78)
W_EAR0, W_EAR1 = srgb(214, 160, 60), srgb(242, 202, 106)
W_AWN = srgb(250, 226, 150)
T_RED, T_ORANGE = srgb(214, 52, 36), srgb(236, 128, 44)
T_SEPAL0, T_SEPAL1 = srgb(86, 140, 56), srgb(52, 108, 42)
P_RIB, P_GROOVE, P_TOP = srgb(236, 124, 32), srgb(184, 78, 20), srgb(246, 156, 52)
CRUST, CRUST_D, CRUST_L = srgb(206, 138, 62), srgb(150, 84, 36), srgb(236, 198, 136)
WHITE = (1.0, 1.0, 1.0)
A_RED, A_DEEP, A_YEL = srgb(198, 30, 34), srgb(134, 14, 28), srgb(224, 200, 84)
A_FLESH, A_GOLD = srgb(252, 220, 124), srgb(238, 166, 62)
LEAF_G, LEAF_D = srgb(86, 146, 58), srgb(44, 100, 40)


# ================================================================ FIREWOOD
WOOD_LIFT = 0.009          # the bundle rests on its rope


def log_radius(R, a0, a1, seed, na, nx):
    def Rf(i, j):
        a = math.radians(a0 + (a1 - a0) * j / na)
        x = i / nx
        return R * (1.0 + 0.07 * n3(a * 4.5 + seed * 3.7, x * 1.3, seed * 1.9) + 0.03 * n3(a * 11.0, x * 5.0 + seed, 7.0))
    return Rf


def split_log(b, L, R, a0, a1, apex, x0, yaw, seed, na=8, nx=6, bt=0.0055):
    """A split length of firewood along X. Cross-section (y,z): a sector with its point at `apex` and bark on the
    arc from a0 to a1 degrees (0 = +Y, 90 = up). Flat split faces and sawn ends are pale wood rimmed with bark."""
    Rf = log_radius(R, a0, a1, seed, na, nx)
    am = math.radians((a0 + a1) / 2)
    ref = (0.0, 0.5 * R * math.cos(am), 0.5 * R * math.sin(am))
    skew = [b.rng.uniform(-0.05, 0.05) for _ in range(4)]

    def X(i, y, z):
        x = -L / 2 + L * i / nx
        if i == 0:
            x += skew[0] * y + skew[1] * z
        elif i == nx:
            x += skew[2] * y + skew[3] * z
        return x

    def P(i, j, r):
        a = math.radians(a0 + (a1 - a0) * j / na)
        y, z = r * math.cos(a), r * math.sin(a)
        return (X(i, y, z), y, z)

    def A(i):
        y, z = 0.003 * n3(i * 0.9, seed), 0.003 * n3(i * 0.9, seed + 9)
        return (X(i, y, z), y, z)

    with b.at((x0, apex[0], apex[1]), (0, 0, yaw)):
        # bark
        verts, cols, uvs, faces = [], [], [], []
        for i in range(nx + 1):
            for j in range(na + 1):
                verts.append(P(i, j, Rf(i, j)))
                k = 0.86 + 0.34 * n3(i * 1.7 + seed, j * 0.9, 3.0)
                cols.append((k, k * 0.97, k * 0.93))
                uvs.append((verts[-1][0], math.radians((a1 - a0) * j / na) * R))
        for i in range(nx):
            for j in range(na):
                a = i * (na + 1) + j
                faces.append((a, a + 1, a + na + 2, a + na + 1))
        raw2(b, verts, faces, cols, 'bark', uvs=uvs, ref=ref)
        # split faces
        for jj in (0, na):
            ang = math.radians(a0 if jj == 0 else a1)
            nrm = (0.0, math.sin(ang), -math.cos(ang)) if jj == 0 else (0.0, -math.sin(ang), math.cos(ang))
            verts, cols, uvs, faces = [], [], [], []
            bverts, bcols, buvs, bfaces = [], [], [], []
            for i in range(nx + 1):
                rw = Rf(i, jj) - bt
                for q, fr in enumerate((0.0, 0.34, 0.68, 1.0)):
                    p = A(i) if q == 0 else P(i, jj, rw * fr)
                    d = 0.006 * n3(i * 1.3 + seed * 2, q * 2.1, jj) if 0 < q < 3 else 0.0
                    verts.append((p[0], p[1] + nrm[1] * d, p[2] + nrm[2] * d))
                    k = 0.9 + 0.26 * n3(q * 2.3 + seed, i * 0.25, jj + 4.0)
                    cols.append((k, k * 0.985, k * 0.95))
                    uvs.append((p[0], rw * fr))
                bverts += [P(i, jj, rw), P(i, jj, Rf(i, jj))]
                bcols += [(0.8, 0.76, 0.72)] * 2
                buvs += [(bverts[-1][0], 0.0), (bverts[-1][0], bt)]
            for i in range(nx):
                for q in range(3):
                    a = i * 4 + q
                    faces.append((a, a + 1, a + 5, a + 4))
                bfaces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
            raw2(b, verts, faces, cols, 'wood_light', uvs=uvs, ref=ref)
            raw2(b, bverts, bfaces, bcols, 'bark', uvs=buvs, ref=ref)
        # sawn ends: heartwood at the point, growth rings as tone steps, a rim of bark
        for i in (0, nx):
            fracs = (0.3, 0.55, 0.8, 1.0)
            tones = ((0.62, 0.52, 0.42), (0.96, 0.91, 0.82), (0.74, 0.67, 0.56), (1.0, 0.97, 0.90), (0.86, 0.80, 0.70))
            verts, cols, uvs, faces = [A(i)], [tones[0]], [(0, 0)], []
            bverts, bcols, buvs, bfaces = [], [], [], []
            for j in range(na + 1):
                rw = Rf(i, j) - bt
                for q, fr in enumerate(fracs):
                    verts.append(P(i, j, rw * fr))
                    cols.append(tones[q + 1])
                    uvs.append((verts[-1][1], verts[-1][2]))
                bverts += [P(i, j, rw), P(i, j, Rf(i, j))]
                bcols += [(0.62, 0.58, 0.54), (0.8, 0.76, 0.72)]
                buvs += [(bverts[-2][1], bverts[-2][2]), (bverts[-1][1], bverts[-1][2])]
            nq = len(fracs)
            for j in range(na):
                a = 1 + j * nq
                faces.append((0, a, a + nq))
                for q in range(nq - 1):
                    faces.append((a + q, a + q + 1, a + nq + q + 1, a + nq + q))
                bfaces.append((2 * j, 2 * j + 1, 2 * j + 3, 2 * j + 2))
            raw2(b, verts, faces, cols, 'wood_light', uvs=uvs, ref=ref)
            raw2(b, bverts, bfaces, bcols, 'bark', uvs=buvs, ref=ref)


def log_outline(R, a0, a1, apex, x0, yaw, seed, xr, L, na=8, nx=6):
    """(y,z) outline of a log where the plane x = xr cuts it (good enough for wrapping the rope)."""
    Rf = log_radius(R, a0, a1, seed, na, nx)
    i = max(0, min(nx, round((xr - x0 + L / 2) / L * nx)))
    dy = (xr - x0) * math.sin(math.radians(yaw))
    out = [(apex[0] + dy, apex[1])]
    for j in range(na + 1):
        a = math.radians(a0 + (a1 - a0) * j / na)
        r = Rf(i, j)
        out.append((apex[0] + dy + r * math.cos(a), apex[1] + r * math.sin(a)))
    return out


def item_wood():
    b = Builder('item_wood', 61)
    LOGS = [  # L, R, a0, a1, apex (y, z), x0, yaw, seed
        (0.350, 0.064, 172, 282, (-0.010, 0.064 + WOOD_LIFT), 0.000, 2.0, 1),      # front: its upper split face is a pale shelf
        (0.318, 0.064, 262, 382, (0.016, 0.064 + WOOD_LIFT), -0.020, -3.0, 2),     # back
        (0.336, 0.056, 22, 148, (0.005, 0.069 + WOOD_LIFT), 0.022, 1.5, 3),        # on top, point down between the other two
    ]
    for L, R, a0, a1, apex, x0, yaw, seed in LOGS:
        split_log(b, L, R, a0, a1, apex, x0, yaw, seed)
    rr = 0.0046
    top = {}
    for xr, slant in ((-0.088, 0.006), (0.094, -0.005)):
        pts = []
        for L, R, a0, a1, apex, x0, yaw, seed in LOGS:
            pts += log_outline(R, a0, a1, apex, x0, yaw, seed, xr, L)
        H = hull2(pts)
        cy = sum(p[0] for p in H) / len(H)
        cz = sum(p[1] for p in H) / len(H)
        ring = []
        for k, p in enumerate(H):
            q = H[(k + 1) % len(H)]
            n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 0.015))
            for s in range(n):
                y, z = p[0] + (q[0] - p[0]) * s / n, p[1] + (q[1] - p[1]) * s / n
                d = Vector((y - cy, z - cz)).normalized()
                ring.append((y + d.x * (rr + 0.0008), max(rr, z + d.y * (rr + 0.0008))))
        k0 = min(range(len(ring)), key=lambda k: ring[k][1])
        ring = ring[k0:] + ring[:k0]
        for w in range(2):                      # two turns side by side
            xo = xr + (w - 0.5) * rr * 2.1
            loop = [(xo + slant * (p[1] - cz) / 0.07, p[0], p[1]) for p in ring]
            b.tube(loop + [loop[0]], rr, mat='rope', segs=4, caps=False)
        top[xr] = max(ring, key=lambda p: p[1] - 0.6 * p[0])     # high on the front shoulder
    (y, z) = top[0.094]
    bow(b, (0.094, y - 0.003, z + 0.002), (0, -1, 0.0), r=0.004, s=1.0, segs=4)
    (y, z) = top[-0.088]
    b.blob(0.0085, loc=(-0.088, y, z + 0.002), mat='rope', subdiv=1)
    b.tube([(-0.088, y, z + 0.002), (-0.100, y - 0.016, z - 0.004), (-0.106, y - 0.03, z - 0.022)], 0.0036, mat='rope', segs=4)
    return b.build(sharp_angle=50)


# ================================================================ BUILDING STONE
def stone_block(b, size, loc, rot, seed, chips, tone=1.0, r=0.007, cuts=4):
    """Squared, tooled block. chips: [((sx, sy, sz), depth)] - corner/edge directions knocked off flat."""
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    h = (hx, hy, hz)
    t = b._new()
    bmesh.ops.create_cube(t, size=2.0)
    bmesh.ops.subdivide_edges(t, edges=t.edges[:], cuts=cuts, use_grid_fill=True)
    _, col, _ = b._layers(t)
    lut = {-1.0: -1.0, -0.6: -2.0, -0.2: -0.3, 0.2: 0.3, 0.6: 2.0, 1.0: 1.0} if cuts == 4 else {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}
    chipped = {}
    for v in t.verts:
        p, inner = [0, 0, 0], [0, 0, 0]
        for a in range(3):
            key = min(lut, key=lambda k: abs(k - v.co[a]))
            m = lut[key]
            if abs(m) == 2.0:
                p[a] = math.copysign(h[a] - r, m)
            else:
                p[a] = m * h[a]
            inner[a] = max(-(h[a] - r), min(h[a] - r, p[a]))
        P, I = Vector(p), Vector(inner)
        d = P - I
        if d.length > 1e-9:
            P = I + d.normalized() * r
        nz = Vector((P.x * 17 + seed * 5.1, P.y * 17 + seed * 2.3, P.z * 17))
        P += P.normalized() * 0.0028 * noise.noise(nz)
        v.co = P
        chipped[v] = 0.0
    for (sx, sy, sz), depth in chips:
        n = Vector((sx, sy, sz)).normalized()
        corner = Vector((math.copysign(hx, sx) if sx else 0.0, math.copysign(hy, sy) if sy else 0.0, math.copysign(hz, sz) if sz else 0.0))
        dd = n.dot(corner) - depth
        for v in t.verts:
            e = n.dot(v.co) - dd
            if e > 0:
                v.co -= n * e * 0.96
                chipped[v] = 1.0
    t.normal_update()
    b._box_uv(t, None, 1.0)
    for f in t.faces:
        for l in f.loops:
            c = l.vert.co
            k = tone * (0.92 + 0.22 * n3(c.x * 9 + seed, c.y * 9, c.z * 9) + 0.10 * n3(c.x * 30, c.y * 30 + seed, c.z * 30))
            k *= 1.0 + 0.2 * chipped[l.vert]
            l[col] = (k, k * 0.985, k * 0.96, 1.0)
    b._emit(t, 'stone', loc, rot)


def item_stone():
    b = Builder('item_stone', 62)
    stone_block(b, (0.240, 0.150, 0.120), (-0.070, 0.045, 0.060), (0, 0, 12), 1,
                [((1, -1, 1), 0.030), ((-1, -1, 0), 0.012), ((-1, 1, 1), 0.022), ((0, -1, -1), 0.009), ((1, 1, 0), 0.014)], tone=0.9)
    stone_block(b, (0.190, 0.140, 0.108), (0.142, -0.010, 0.054), (0, 0, -24), 2,
                [((1, 1, 1), 0.026), ((1, -1, 0), 0.010), ((-1, -1, 1), 0.016), ((1, 0, 1), 0.007)], tone=1.1)
    stone_block(b, (0.205, 0.132, 0.098), (0.030, 0.030, 0.166), (5, -7, 38), 3,
                [((1, -1, 1), 0.024), ((-1, 0, 1), 0.012), ((1, 1, -1), 0.018), ((-1, -1, -1), 0.020)], tone=1.0)
    stone_block(b, (0.135, 0.100, 0.086), (-0.012, -0.142, 0.047), (-9, 0, -14), 4,
                [((1, -1, 1), 0.020), ((-1, -1, 1), 0.012), ((0, 1, 1), 0.008)], tone=0.8)
    # spalls knocked off while squaring them
    for x, y, s, rz in ((0.125, -0.150, 1.0, 20), (0.165, -0.118, 0.6, 70), (-0.165, -0.085, 0.75, -30)):
        stone_block(b, (0.034 * s, 0.024 * s, 0.014 * s), (x, y, 0.006 * s), (4, 6, rz), 9 + int(s * 10),
                    [((1, 1, 1), 0.006 * s), ((-1, -1, 1), 0.007 * s)], tone=1.12, r=0.002 * s, cuts=1)
    return b.build(sharp_angle=38)


# ================================================================ APPLE
def apple(b, loc, rot, R=0.041, H=0.076, segs=18, leaf=True):
    prof = smooth_profile([(0, 0.105), (0.17, 0.05), (0.42, 0.0), (0.70, 0.06), (0.92, 0.27), (1.0, 0.52), (0.95, 0.75), (0.76, 0.92),
                           (0.50, 0.99), (0.27, 0.955), (0.11, 0.875), (0, 0.845)], 2)

    def lobes(a, z):
        return 1.0 + 0.035 * math.cos(5 * a + 0.6) * smooth(0.35 * H, 0.0, z) + 0.02 * math.sin(2 * a + 0.8) + 0.012 * math.sin(3 * a)

    def cf(co):
        a = math.atan2(co.y, co.x)
        zz = co.z / H
        rr = math.hypot(co.x, co.y) / R
        streak = 0.5 + 0.5 * n3(a * 7.0, zz * 0.9, 2.0)
        c = mix(A_RED, A_DEEP, 0.75 * smooth(0.45, 0.9, streak))
        c = mix(c, srgb(226, 70, 50), 0.5 * smooth(0.5, 0.1, streak))
        c = mix(c, srgb(240, 150, 84), 0.42 * smooth(0.55, 0.95, 0.5 + 0.5 * math.sin(a * 19 + 2 * n3(a * 3, 5.0))) * smooth(0.95, 0.35, zz) * smooth(0.05, 0.3, zz))
        # the shaded cheek stays yellow-green, broken into streaks where the red runs into it
        da = (a + 2.5 + pi) % (2 * pi) - pi
        patch = math.exp(-(da / 0.85) ** 2) * smooth(0.1, 0.45, zz) * (0.6 + 0.4 * smooth(0.3, 0.7, 0.5 + 0.5 * math.sin(a * 21 + zz * 3)))
        c = mix(c, A_YEL, 0.85 * patch)
        c = mix(c, srgb(206, 196, 92), 0.9 * smooth(0.52, 0.2, rr) * smooth(0.7, 0.9, zz))       # stem cavity
        c = mix(c, srgb(120, 84, 44), 0.8 * smooth(0.3, 0.08, rr) * smooth(0.2, 0.05, zz))        # calyx end
        return mix(c, mul(c, 0.78), smooth(0.3, 0.0, zz) * 0.6)

    with b.at(loc, rot):
        b.lathe([(p[0] * R, p[1] * H) for p in prof], mat='plant_glossy', segs=segs, color=cf, radial=lobes)
        st0 = Vector((0.0005, 0, 0.85 * H))
        pts = [st0, st0 + Vector((0.001, 0.0, 0.012)), st0 + Vector((0.006, 0.002, 0.024))]
        b.tube(pts, [0.0021, 0.0019, 0.0027], mat='plant', segs=5, color=srgb(92, 62, 36), color_top=srgb(128, 92, 52))
        if leaf:
            broad_leaf(b, 0.046, 0.026, pts[1] - Vector((0, 0, 0.002)), basis_rot(dirv(-128, 38), (0, 0, -1)), bend=42, fold=22, segs=5,
                       c_rib=srgb(150, 190, 96), c_mid=LEAF_G, c_edge=LEAF_D, jitter=0.0)


def item_apple():
    b = Builder('item_apple', 63)
    apple(b, (0, 0, 0.0012), (5, -5, 0))
    return b.build(sharp_angle=80)


# ================================================================ APPLE TART
TART_FL = 28


def apple_slice(b, loc, yaw, tilt, L=0.036, W=0.0135):
    """Glazed crescent of apple: local X = its length, +Y = the red peel edge."""
    n = 5
    verts, cols = [], []
    for i in range(n + 1):
        t = -1 + 2 * i / n
        k = (1 - t * t) ** 0.6
        x = L / 2 * t
        bow_ = -0.22 * L * (1 - t * t)           # the crescent curves round the tart
        for q, (fy, fz, c) in enumerate(((-0.30, 0.0, A_FLESH), (0.25, 0.0034, A_FLESH), (0.66, 0.0032, A_GOLD), (1.0, 0.0008, srgb(190, 36, 30)))):
            verts.append((x, bow_ * (1 if q < 3 else 0.96) + W * (fy * (0.25 + 0.75 * k) if q else fy * k), fz * (0.3 + 0.7 * k)))
            cols.append(c)
    faces = []
    for i in range(n):
        for q in range(3):
            a = i * 4 + q
            faces.append((a, a + 4, a + 5, a + 1))
    raw2(b, verts, faces, cols, 'plant_glossy', loc, (tilt, 0, yaw), facing=None, ref=(0, 0, -1))


def item_tart():
    b = Builder('item_tart', 64)
    flute = lambda a, z: 1.0 + 0.020 * math.cos(TART_FL * a) * smooth(0.002, 0.012, z)
    tin = [(0, 0), (0.096, 0), (0.0985, 0.003), (0.1175, 0.0275), (0.122, 0.0288), (0.1225, 0.0300), (0.117, 0.0300)]
    b.lathe(tin, mat='metal', segs=TART_FL * 2, color=(0.86, 0.86, 0.89), color_top=(1.0, 1.0, 1.0), radial=flute)
    PC, PC_D, PC_L = srgb(228, 172, 96), srgb(170, 100, 44), srgb(244, 206, 136)

    def rim_c(co):
        a = math.atan2(co.y, co.x)
        peak = 0.5 + 0.5 * math.cos(TART_FL * a)
        c = mix(PC, PC_D, 0.55 * peak * smooth(0.033, 0.039, co.z))
        return mul(c, 1.0 + 0.1 * n3(co.x * 40, co.y * 40, 1.0))

    rim = [(0.1165, 0.0290), (0.1205, 0.0335), (0.1195, 0.0385), (0.1140, 0.0408), (0.1080, 0.0385), (0.1045, 0.0330)]
    b.lathe(rim, mat='bread', segs=TART_FL * 2, color=rim_c, radial=lambda a, z: 1.0 + 0.020 * math.cos(TART_FL * a))
    # glazed filling under the fruit
    SYR, SYR_D = srgb(186, 100, 34), srgb(140, 70, 26)
    b.lathe([(0, 0.0338), (0.06, 0.0334), (0.106, 0.0322)], mat='plant_glossy', segs=28,
            color=lambda co: mix(SYR, SYR_D, smooth(0.06, 0.105, math.hypot(co.x, co.y))))
    # apple slices fanned in rings
    r = b.rng
    for R0, cnt, tilt, z0, ph in ((0.085, 17, 24, 0.0348, 0.0), (0.054, 11, 26, 0.0362, 0.3), (0.024, 6, 30, 0.0376, 0.1)):
        for k in range(cnt):
            a = 2 * pi * k / cnt + ph
            apple_slice(b, (R0 * math.cos(a), R0 * math.sin(a), z0 + 0.0006 * (k % 2)), math.degrees(a) - 90 + r.uniform(-7, 7),
                        tilt + r.uniform(-5, 5), L=0.037 if R0 > 0.03 else 0.03)
    b.blob((0.008, 0.008, 0.004), loc=(0, 0, 0.0392), mat='plant_glossy', subdiv=1, color=A_GOLD)
    # woven lattice
    sp, w, th, amp, Rin = 0.050, 0.0150, 0.0036, 0.0027, 0.1095
    zc = lambda x, y: 0.0452 - 0.0075 * (x * x + y * y) / (Rin * Rin)
    with b.at(rot=(0, 0, 28)):
        for axis in (0, 1):
            for i in range(4):
                off = (i - 1.5) * sp
                sg = (1 if i % 2 == 0 else -1) * (1 if axis == 0 else -1)
                ns = 16
                verts, cols, faces = [], [], []
                tone = 1.0 + r.uniform(-0.05, 0.05)
                for s in range(ns + 1):
                    for q, (fv, fz) in enumerate(((-0.5, -0.5), (-0.40, 0.42), (0.0, 0.62), (0.40, 0.42), (0.5, -0.5))):
                        v = off + fv * w
                        half = math.sqrt(max(Rin * Rin - v * v, 1e-6))
                        u = (-1 + 2 * s / ns) * half
                        wave = sg * amp * math.sin(pi * u / sp) * smooth(1.0, 0.86, abs(u) / half)
                        x, y = (u, v) if axis == 0 else (v, u)
                        verts.append((x, y, zc(x, y) + wave + fz * th))
                        crest = 0.5 + 0.5 * sg * math.sin(pi * u / sp)
                        c = mix(PC_L, PC, 0.25 + 0.5 * crest) if q in (1, 2, 3) else PC_D
                        if q == 2:
                            c = mix(c, PC_D, 0.35 * crest)
                        cols.append(mul(c, tone * (1.0 + 0.07 * n3(x * 60, y * 60, 3.0))))
                for s in range(ns):
                    for q in range(4):
                        a = s * 5 + q
                        f = (a, a + 5, a + 6, a + 1)
                        faces.append(f if axis == 0 else tuple(reversed(f)))
                raw(b, verts, faces, cols, 'bread')
    return b.build(sharp_angle=55)


# ================================================================ WEEDS
def thistle_head(b, p, d, s=1.0):
    with b.at(p, aimz(d), scale=(s, s, s)):
        spk = lambda a, z: 1.0 + 0.2 * math.cos(6 * a + z * 300)
        b.lathe([(0, -0.002), (0.0085, 0.001), (0.0135, 0.009), (0.0125, 0.018), (0.008, 0.025), (0, 0.026)], mat='plant', segs=12,
                color=srgb(84, 122, 66), color_top=srgb(130, 158, 96), radial=spk)
        tuft = lambda a, z: 1.0 + 0.10 * math.cos(6 * a) * smooth(0.03, 0.044, z)
        b.lathe([(0.0065, 0.022), (0.0100, 0.030), (0.0180, 0.0425), (0.0165, 0.0475), (0.0075, 0.0465), (0, 0.0440)], mat='plant', segs=12,
                color=srgb(140, 52, 150), color_top=srgb(216, 132, 220), radial=tuft)


def item_weeds():
    b = Builder('item_weeds', 65)
    r = b.rng
    T = Vector((-0.040, 0.0, 0.034))                 # where the bundle is tied
    DOCK_RIB, DOCK_M, DOCK_E = srgb(204, 220, 136), srgb(98, 154, 58), srgb(50, 108, 44)
    RUST = srgb(156, 92, 48)
    ROOT0, ROOT1 = srgb(220, 196, 156), srgb(156, 122, 86)

    def dock_shape(u):
        return max(0.14, min(1.0, 0.22 + 3.4 * u) * (1.0 if u < 0.5 else math.cos((u - 0.5) / 0.5 * pi / 2) ** 0.7))

    crowns = []
    # ---- dock: broad wavy leaves on reddish stalks
    docks = [  # yaw, elevation, length, width, bend, rusty tip
        (-31, 6, 0.165, 0.074, 4, False), (-14, 22, 0.175, 0.082, 30, True), (2, 40, 0.180, 0.078, 52, False), (18, 26, 0.170, 0.078, 34, False),
        (33, 7, 0.155, 0.070, 4, True), (-22, 48, 0.150, 0.066, 62, False), (9, 11, 0.150, 0.068, 10, False)]
    for k, (yaw, el, L, W, bend, rust) in enumerate(docks):
        d = dirv(yaw, el)
        a = k * 2.4
        o = Vector((0, math.cos(a), math.sin(a) * 0.7 + 0.2)) * 0.010
        crown = T + Vector((-0.038 - 0.008 * (k % 3), o.y * 1.5, o.z * 0.8 - 0.006))
        base = T + o + d * 0.036
        b.tube([crown, T + o, base], [0.0050, 0.0042, 0.0034], mat='plant', segs=4, caps=False, color=srgb(156, 66, 56), color_top=srgb(140, 156, 76))
        broad_leaf(b, L, W, base, basis_rot(d, (0, 0, -1)), bend=bend, fold=18, segs=7, shape=dock_shape, c_rib=DOCK_RIB, c_mid=DOCK_M,
                   c_edge=DOCK_E, c_tip=RUST if rust else None, wave=0.04)
        crowns.append(crown)
    # ---- thistle: a stalk with a flower head and spiny leaves
    thc = T + Vector((-0.046, 0.004, 0.002))
    TH0, TH1 = srgb(96, 132, 84), srgb(132, 160, 106)
    sp = [thc, T + Vector((0, 0.002, 0.012)), Vector((0.020, -0.012, 0.086)), Vector((0.068, -0.028, 0.130)), Vector((0.104, -0.038, 0.151))]
    b.tube(sp, [0.0050, 0.0044, 0.0040, 0.0036, 0.0032], mat='plant', segs=5, caps=False, color=TH0, color_top=TH1)
    thistle_head(b, sp[-1], sp[-1] - sp[-2], 1.3)
    for p, yaw, el, L in ((sp[2], -72, 30, 0.105), (sp[2].lerp(sp[3], 0.4), 80, 40, 0.095), (sp[3], -30, 62, 0.070), (sp[1].lerp(sp[2], 0.5), 24, 60, 0.090)):
        jag_leaf(b, L, 0.042, p, basis_rot(dirv(yaw, el), (0, 0, -1)), bend=38, c_rib=srgb(176, 196, 146), c_edge=srgb(80, 120, 74),
                 c_tip=srgb(122, 152, 98))
    crowns.append(thc)
    # ---- a few grass blades to fill the bundle out
    for yaw, el, L in ((-26, 32, 0.17), (14, 50, 0.19)):
        d = dirv(yaw, el)
        b.leaf(L, 0.011, loc=T + d * 0.01, rot=basis_rot(d, (0, 0, -1)), bend=30 + r.uniform(-8, 20), fold=30, segs=4,
               color=srgb(92, 140, 60), color_top=srgb(150, 176, 84), jitter=0.08)
    # ---- roots, with soil still clinging
    for k, c in enumerate(crowns):
        a = -0.5 + k * 0.9
        tip = c + Vector((-0.046 - 0.012 * (k % 3), 0.030 * math.sin(a * 1.7), -c.z + 0.007 + 0.012 * (k % 2)))
        mid = c.lerp(tip, 0.5) + Vector((0, 0.008 * math.cos(a), 0.007))
        b.tube([c + Vector((0.008, 0, 0)), c, mid, tip], [0.0052, 0.0058, 0.0036, 0.0011], mat='plant', segs=4, caps=False, color=ROOT0, color_top=ROOT1)
        p0 = c.lerp(mid, 0.5 + 0.4 * (k % 2))
        dd = Vector((-0.6, r.uniform(-1, 1), r.uniform(-0.4, 0.5))).normalized()
        p1 = p0 + dd * 0.022
        p2 = p1 + (dd + Vector((-0.4, 0, -0.5))).normalized() * 0.022
        b.tube([p0, p1, (p2.x, p2.y, max(p2.z, 0.003))], [0.0020, 0.0014, 0.0006], mat='plant', segs=3, caps=False, color=ROOT1)
    SOIL = lambda co: mul((1.0, 0.95, 0.9), 0.62 + 0.3 * n3(co.x * 70, co.y * 70, co.z * 70))
    for (x, y, z), (rx, ry, rz) in (((-0.106, 0.004, 0.022), (0.029, 0.027, 0.021)), ((-0.128, -0.020, 0.015), (0.019, 0.018, 0.014)),
                                   ((-0.100, -0.026, 0.013), (0.016, 0.014, 0.012))):
        b.blob((rx, ry, rz), loc=(x, y, z), mat='soil', subdiv=2, noise_amp=0.28, noise_scale=2.4, color=SOIL)
    for x, y, s in ((-0.158, 0.012, 1.0), (-0.140, 0.040, 0.7), (-0.150, -0.046, 0.8)):
        b.blob((0.007 * s, 0.006 * s, 0.0045 * s), loc=(x, y, 0.003 * s), mat='soil', subdiv=1, color=(0.7, 0.66, 0.62))
    # ---- loose twine
    with b.at(T + Vector((0.004, 0, 0.004)), (0, 90, 0)):
        with b.at(rot=(10, 0, 0)):
            torus(b, 0.0200, 0.0034, 0, n=4, mat='rope', segs=12, scale=(1.0, 1.12, 1.0))
        with b.at((0, 0, 0.007), rot=(-8, 6, 0)):
            torus(b, 0.0195, 0.0034, 0, n=4, mat='rope', segs=12, scale=(1.0, 1.12, 1.0))
    bow(b, T + Vector((0.008, -0.024, 0.008)), (0, -1, 0), r=0.0034, s=0.85, segs=3)
    return b.build(sharp_angle=80)


# ================================================================ COMPOST BUCKET
def item_compost():
    b = Builder('item_compost', 66)
    r = b.rng
    N, h, rb, rt, th = 14, 0.190, 0.090, 0.116, 0.012
    tilt = math.atan((rt - rb) / h)
    rm = (rb + rt) / 2
    wb, wt = 2 * rb * math.tan(pi / N) + 0.0012, 2 * rt * math.tan(pi / N) + 0.0012
    apo = lambda z: rb + (rt - rb) * z / h + th / 2            # outer face of a stave (apothem)
    corner = lambda z, e=0.0: (apo(z) + e) / math.cos(pi / N)
    for k in range(N):
        ear = 0.036 if k in (0, N // 2) else 0.0
        L = (h + ear) / math.cos(tilt)
        with b.at(rot=(0, 0, 90 + k * 360 / N)):
            b.box((wb, th, L), loc=(0, -(rm + math.sin(tilt) * ear / 2), (h + ear) / 2), rot=(math.degrees(tilt), 0, 0), mat='wood_plank', bevel=0.0035,
                  segs=1, taper=((wt + (wt - wb) * ear / h) / wb, 1), jitter=0.13, color=(0.94, 0.9, 0.86))
    poly = lambda a, z: math.cos(pi / N) / math.cos(((a + pi / N) % (2 * pi / N)) - pi / N)
    for zc, hw in ((0.040, 0.0095), (0.146, 0.0095)):
        b.lathe([(corner(zc - hw, 0.0002), zc - hw - 0.0008), (corner(zc - hw, 0.0026), zc - hw + 0.0008), (corner(zc + hw, 0.0026), zc + hw - 0.0008),
                 (corner(zc + hw, 0.0002), zc + hw + 0.0008)], mat='metal_dark', segs=N * 2, radial=poly, color=(1.0, 0.98, 0.95))
        b.blob((0.004, 0.0025, 0.004), loc=(0.02, -(apo(zc) + 0.003), zc), mat='metal_dark', subdiv=1)        # rivet
    b.lathe([(0, 0.014), (rb + 0.004, 0.014)], mat='wood_dark', segs=N)                                       # floor (seen only from below)
    # the heap
    zc = h - 0.012
    HR, HH = rt - 0.003, 0.074

    def heap_c(co):
        k = 0.56 + 0.30 * n3(co.x * 38, co.y * 38, co.z * 38) + 0.16 * n3(co.x * 90, co.y * 90, co.z * 90)
        return (k, k * 0.94, k * 0.88)

    b.blob((HR, HR, HH), loc=(0, 0, zc), mat='soil', subdiv=3, noise_amp=0.10, noise_scale=2.6, flatten_bottom=-0.15, color=heap_c)

    def top(x, y, e=0.0):
        return zc + HH * math.sqrt(max(1 - (x * x + y * y) / (HR * HR), 0.0)) + e

    for k in range(10):
        a, rho = k * 2.39996, 0.022 + 0.082 * math.sqrt((k + 0.5) / 10)
        x, y = rho * math.cos(a), rho * math.sin(a)
        s = r.uniform(0.7, 1.25)
        kk = r.uniform(0.5, 0.95)
        b.blob((0.012 * s, 0.011 * s, 0.008 * s), loc=(x, y, top(x, y, 0.001)), rot=(r.uniform(-20, 20), r.uniform(-20, 20), a * 57), mat='soil',
               subdiv=1, color=(kk, kk * 0.93, kk * 0.86))
    for k in range(8):                               # straw
        a = r.uniform(0, 2 * pi)
        rho = r.uniform(0.02, 0.085)
        x, y = rho * math.cos(a), rho * math.sin(a)
        dd = Vector((math.cos(a + r.uniform(0.6, 2.4)), math.sin(a + r.uniform(0.6, 2.4)), 0)) * r.uniform(0.022, 0.04)
        p0, p1 = Vector((x, y, 0)) - dd, Vector((x, y, 0)) + dd
        kk = r.uniform(0.8, 1.15)
        b.tube([(p0.x, p0.y, top(p0.x, p0.y, 0.002)), (x, y, top(x, y, 0.006)), (p1.x, p1.y, top(p1.x, p1.y, 0.004))], 0.0021, mat='straw', segs=3,
               caps=False, color=(kk, kk * 0.95, kk * 0.8))
    # kitchen scraps: half an eggshell, peelings, a wilted leaf
    x, y = -0.040, -0.052
    b.lathe([(0.0165, -0.004), (0.0170, 0.004), (0.0135, 0.013), (0.007, 0.0185), (0, 0.020)], loc=(x, y, top(x, y, 0.001)), rot=(24, -18, 0), mat='egg',
            segs=9, color=srgb(226, 206, 176), color_top=srgb(248, 238, 220))
    x, y = 0.046, -0.040
    b.leaf(0.06, 0.016, loc=(x, y, top(x, y, 0.004)), rot=(0, 78, 150), bend=120, fold=34, segs=5, mat='plant', color=srgb(226, 120, 36), color_top=srgb(240, 160, 60))
    x, y = 0.012, 0.050
    broad_leaf(b, 0.07, 0.034, (x, y, top(x, y, 0.004)), (0, 84, 30), bend=30, fold=10, segs=5, c_rib=srgb(150, 150, 80), c_mid=srgb(104, 118, 52),
               c_edge=srgb(120, 92, 44), wave=0.05)
    x, y = -0.012, -0.012
    b.leaf(0.05, 0.014, loc=(x, y, top(x, y, 0.004)), rot=(0, 80, -70), bend=90, fold=30, segs=4, mat='plant', color=srgb(196, 60, 40), color_top=srgb(226, 110, 70))
    # crumbs spilt at the foot
    for x, y, s in ((0.118, -0.070, 1.0), (0.142, -0.040, 0.6), (0.096, -0.098, 0.7)):
        b.blob((0.011 * s, 0.010 * s, 0.006 * s), loc=(x, y, 0.004 * s), mat='soil', subdiv=1, color=(0.62, 0.58, 0.54))
    # rope handle hanging down the front, knotted through the two tall staves
    ze = h + 0.018
    pts = []
    for i in range(13):
        ph = pi * i / 12
        z = ze - 0.085 * math.sin(ph) ** 0.75
        rr = corner(min(z, h), 0.0075) if 0 < i < 12 else apo(h) + 0.004
        pts.append((-rr * math.cos(ph), -rr * math.sin(ph) * (1.0 if 0 < i < 12 else 0.0), z))
    b.tube(pts, 0.0048, mat='rope', segs=5, caps=False)
    for sx in (-1, 1):
        b.blob((0.0085, 0.0095, 0.0095), loc=(sx * (apo(h) + 0.006), 0, ze), mat='rope', subdiv=1)
    return b.build(sharp_angle=48)


# ================================================================ SEED PACKETS
PK_W, PK_H = 0.090, 0.130
KRAFT, KRAFT_D = srgb(226, 196, 146), srgb(190, 156, 108)
INK = srgb(92, 66, 46)


def pk_depth(x, z):
    """Half thickness of the packet at (x, z): the seeds settle into the lower half."""
    ex = max(0.0, 1.0 - (abs(x) / (PK_W / 2)) ** 2.2)
    gz = lerp_table([(0.0, 0.50), (0.018, 0.86), (0.042, 1.0), (0.078, 0.80), (0.108, 0.34), (0.13, 0.20)], z)[0]
    return 0.0011 + 0.0066 * ex ** 0.65 * gz


def surf(x, z, lift=0.0):
    return (x, -(pk_depth(x, z) + lift), z)


def ellipse(cx, cz, rx, rz, n=10, rot=0.0):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for k in range(n):
        a = 2 * pi * k / n
        x, z = rx * math.cos(a), rz * math.sin(a)
        out.append((cx + x * c - z * s, cz + x * s + z * c))
    return out


def decal(b, pts, col, lift, mat='paint'):
    """Flat polygon (star-shaped about its centroid) laid on the packet front."""
    cx = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    verts = [surf(cx, cz, lift)] + [surf(x, z, lift) for x, z in pts]
    n = len(pts)
    faces = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
    raw2(b, verts, faces, col, mat, facing=(0, -1, 0))


def decal_rect(b, x0, z0, x1, z1, col, lift, nx=4, nz=3, mat='paint'):
    verts, faces = [], []
    for i in range(nx + 1):
        for j in range(nz + 1):
            verts.append(surf(x0 + (x1 - x0) * i / nx, z0 + (z1 - z0) * j / nz, lift))
    for i in range(nx):
        for j in range(nz):
            a = i * (nz + 1) + j
            faces.append((a, a + nz + 1, a + nz + 2, a + 1))
    raw2(b, verts, faces, col, mat, facing=(0, -1, 0))


def line(b, p, q, w, col, lift, w1=None):
    """Tapered stroke from p to q."""
    w1 = w if w1 is None else w1
    d = Vector((q[0] - p[0], q[1] - p[1]))
    n = Vector((-d.y, d.x)).normalized()
    decal(b, [(p[0] - n.x * w / 2, p[1] - n.y * w / 2), (q[0] - n.x * w1 / 2, q[1] - n.y * w1 / 2), (q[0] + n.x * w1 / 2, q[1] + n.y * w1 / 2),
              (p[0] + n.x * w / 2, p[1] + n.y * w / 2)], col, lift)


def rot2(p, c, deg):
    a = math.radians(deg)
    x, z = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - z * math.sin(a), c[1] + x * math.sin(a) + z * math.cos(a))


L1, L2, L3, L4, L5 = 0.0013, 0.0017, 0.0021, 0.0025, 0.0029     # paint layers
PIC = (0.0, 0.0705)                                             # centre of the picture


def art_wheat(b):
    base = (0.0, 0.044)
    for ang, L in ((-27, 0.050), (27, 0.050), (0, 0.055)):
        tip = rot2((base[0], base[1] + L), base, -ang)
        ax = Vector((tip[0] - base[0], tip[1] - base[1])).normalized()
        nr = Vector((-ax.y, ax.x))
        line(b, base, (base[0] + ax.x * L * 0.5, base[1] + ax.y * L * 0.5), 0.0022, srgb(160, 118, 44), L1)
        for k in range(5):
            t = 0.42 + 0.115 * k
            for sg in (-1, 1):
                c = (base[0] + ax.x * L * t + nr.x * sg * 0.0036, base[1] + ax.y * L * t + nr.y * sg * 0.0036)
                decal(b, ellipse(c[0], c[1], 0.0026, 0.0052, 7, -ang - sg * 28), srgb(204, 138, 36) if (k + (sg > 0)) % 2 else srgb(236, 180, 70), L2 if sg < 0 else L3)
                if k >= 2:
                    line(b, c, (c[0] + ax.x * 0.012 + nr.x * sg * 0.005, c[1] + ax.y * 0.012 + nr.y * sg * 0.005), 0.0009, srgb(176, 124, 40), L1, 0.0002)
        decal(b, ellipse(tip[0], tip[1], 0.0026, 0.0054, 7, -ang), srgb(236, 180, 70), L4)
        line(b, tip, (tip[0] + ax.x * 0.011, tip[1] + ax.y * 0.011), 0.0009, srgb(176, 124, 40), L1, 0.0002)


def art_tomato(b):
    cx, cz = 0.0, 0.0685
    decal(b, ellipse(cx, cz, 0.0225, 0.0200, 18), T_RED, L1)
    decal(b, ellipse(cx + 0.004, cz - 0.004, 0.0165, 0.0135, 12), mix(T_RED, srgb(150, 26, 24), 0.55), L2)      # shaded underside
    decal(b, ellipse(cx - 0.002, cz + 0.0015, 0.0170, 0.0140, 12), T_RED, L3)
    decal(b, ellipse(cx - 0.0095, cz + 0.007, 0.0050, 0.0030, 8, 35), srgb(252, 168, 140), L4)
    top = (cx, cz + 0.0165)
    for k in range(5):
        a = math.radians(-90 + (k - 2) * 44)
        tip = (top[0] + 0.0125 * math.cos(a), top[1] + 0.0085 * math.sin(a) + 0.0015)
        d = Vector((tip[0] - top[0], tip[1] - top[1]))
        n = Vector((-d.y, d.x)).normalized() * 0.0030
        m = (top[0] + d.x * 0.45, top[1] + d.y * 0.45)
        decal(b, [top, (m[0] - n.x, m[1] - n.y), tip, (m[0] + n.x, m[1] + n.y)], T_SEPAL1 if k % 2 else T_SEPAL0, L5)
    line(b, top, (top[0] + 0.003, top[1] + 0.009), 0.0030, T_SEPAL1, L5, 0.0022)


def art_pumpkin(b):
    cx, cz = 0.0, 0.0655
    for x, rx, rz, c, lift in ((-0.0165, 0.0095, 0.0150, P_GROOVE, L1), (0.0165, 0.0095, 0.0150, P_GROOVE, L1),
                               (-0.0090, 0.0100, 0.0175, P_RIB, L2), (0.0090, 0.0100, 0.0175, P_RIB, L2), (0.0, 0.0082, 0.0188, P_TOP, L3)):
        decal(b, ellipse(cx + x, cz, rx, rz, 12), c, lift)
    decal(b, ellipse(cx - 0.0015, cz + 0.006, 0.0022, 0.0060, 6, 8), srgb(252, 196, 110), L4)
    s0 = (cx, cz + 0.0170)
    decal(b, [(s0[0] - 0.0036, s0[1]), (s0[0] + 0.0036, s0[1]), (s0[0] + 0.0066, s0[1] + 0.0100), (s0[0] + 0.0020, s0[1] + 0.0112)], srgb(104, 118, 54), L5)
    decal(b, ellipse(cx - 0.0125, cz + 0.0205, 0.0080, 0.0044, 8, -18), srgb(78, 136, 56), L4)
    line(b, (cx - 0.0190, cz + 0.0225), (cx - 0.0060, cz + 0.0185), 0.0008, srgb(150, 190, 96), L5)


def art_carrot(b):
    c = (0.002, 0.0700)
    rt = -32
    top, L = 0.012, 0.043                               # the root runs from z=+top down to z=top-L in its own frame
    out = []
    n = 6
    for i in range(n + 1):
        t = i / n
        hw = 0.0088 * (1 - t) ** 0.75 + 0.0005
        if i == 0:
            hw *= 0.72
        out.append((c[0] + hw, c[1] + top - L * t))
    left = [(2 * c[0] - x, z) for x, z in reversed(out)]
    body = [rot2(p, c, rt) for p in out + left]
    decal(b, body, srgb(238, 130, 38), L2)
    hi = [(c[0] - 0.0030, c[1] + top - 0.004), (c[0] - 0.0006, c[1] + top - 0.004), (c[0] - 0.0008, c[1] + top - L * 0.62), (c[0] - 0.0018, c[1] + top - L * 0.62)]
    decal(b, [rot2(p, c, rt) for p in hi], srgb(250, 172, 84), L3)
    for t, sg in ((0.2, 1), (0.38, -1), (0.56, 1)):
        hw = 0.0088 * (1 - t) ** 0.75
        z = c[1] + top - L * t
        p, q = (c[0] + sg * hw * 0.95, z), (c[0] + sg * hw * 0.2, z - 0.0012)
        line(b, rot2(p, c, rt), rot2(q, c, rt), 0.0011, srgb(190, 86, 26), L4, 0.0004)
    crown = (c[0], c[1] + top - 0.001)
    for ang, L_, col in ((-52, 0.020, LEAF_D), (40, 0.019, LEAF_D), (-22, 0.025, LEAF_G), (14, 0.026, srgb(110, 170, 70)), (-4, 0.022, LEAF_G)):
        tip = rot2((crown[0], crown[1] + L_), crown, ang)
        mid = ((crown[0] + tip[0]) / 2, (crown[1] + tip[1]) / 2)
        el = ellipse(mid[0], mid[1], 0.0034, L_ / 2, 8, ang)
        decal(b, [rot2(p, c, rt) for p in el], col, L1 if col == LEAF_D else L3)


def art_cabbage(b):
    cx, cz = 0.0, 0.0680
    G0, G1, G2, G3 = srgb(62, 122, 60), srgb(104, 166, 80), srgb(160, 206, 112), srgb(206, 232, 158)
    decal(b, ellipse(cx - 0.0125, cz - 0.0030, 0.0150, 0.0185, 12, 24), G0, L1)        # outer wrapper leaves
    decal(b, ellipse(cx + 0.0125, cz - 0.0030, 0.0150, 0.0185, 12, -24), G0, L1)
    decal(b, ellipse(cx, cz + 0.0060, 0.0190, 0.0150, 12), mix(G0, G1, 0.4), L1)
    decal(b, ellipse(cx, cz + 0.0005, 0.0178, 0.0170, 16), G1, L2)                     # the head
    decal(b, ellipse(cx - 0.0045, cz + 0.0005, 0.0118, 0.0142, 12, 14), G2, L3)        # overlapping inner leaves
    decal(b, ellipse(cx + 0.0050, cz + 0.0020, 0.0090, 0.0116, 10, -16), mix(G1, G2, 0.55), L4)
    decal(b, ellipse(cx + 0.0005, cz + 0.0040, 0.0056, 0.0074, 9, 8), G3, L5)
    for x0, x1, zz in ((-0.011, -0.004, 0.006), (0.011, 0.005, 0.007), (-0.014, -0.008, -0.004)):                 # creases in the head
        line(b, (cx + x0, cz + zz - 0.006), (cx + x1, cz + zz + 0.006), 0.0009, G0, L5 + 0.0003, 0.0003)
    for ang in (-40, -14, 14, 40):                                                    # veins on the wrapper
        p = (cx, cz - 0.0195)
        q = rot2((cx, cz - 0.0195 + 0.014), p, ang * 1.5)
        line(b, p, q, 0.0011, G2, L2 + 0.0001, 0.0003)


def seed_packet(name, band, art, seed):
    b = Builder(name, seed)
    W, H = PK_W, PK_H
    nx, nz = 8, 10
    paper = lambda x, z: mul(KRAFT, 0.95 + 0.07 * n3(x * 30 + seed, z * 30, 1.0))
    for sg in (-1, 1):
        verts, cols, faces = [], [], []
        for i in range(nx + 1):
            for j in range(nz + 1):
                x, z = -W / 2 + W * i / nx, H * j / nz
                verts.append((x, sg * pk_depth(x, z), z))
                cols.append(paper(x, z) if sg < 0 else mul(paper(x, z), 0.93))
        for i in range(nx):
            for j in range(nz):
                a = i * (nz + 1) + j
                faces.append((a, a + nz + 1, a + nz + 2, a + 1))
        raw2(b, verts, faces, cols, 'parchment', facing=(0, sg, 0))
    # glued edges
    per = [(-W / 2 + W * i / nx, 0.0) for i in range(nx)] + [(W / 2, H * j / nz) for j in range(nz)] + \
          [(W / 2 - W * i / nx, H) for i in range(nx)] + [(-W / 2, H - H * j / nz) for j in range(nz)]
    verts, faces = [], []
    for x, z in per:
        d = pk_depth(x, z)
        verts += [(x, -d, z), (x, d, z)]
    n = len(per)
    for k in range(n):
        a, c = 2 * k, 2 * ((k + 1) % n)
        faces.append((a, a + 1, c + 1, c))
    raw2(b, verts, faces, mul(KRAFT, 0.86), 'parchment', ref=(0, 0, H / 2))
    # folded-over top flap with its shadow, and the back seam
    zf = 0.108
    flap = mul(KRAFT_D, 1.04)
    decal_rect(b, -W / 2, zf - 0.0018, W / 2, zf, mul(KRAFT_D, 0.62), 0.0004, nx=6, nz=1, mat='parchment')
    decal_rect(b, -W / 2, zf, W / 2, H, flap, 0.0014, nx=6, nz=2, mat='parchment')
    verts, faces = [], []
    for i in range(7):
        x = -W / 2 + W * i / 6
        d = pk_depth(x, H)
        verts += [(x, -(d + 0.0014), H), (x, -d, H), (x, -(d + 0.0014), zf), (x, -(d + 0.0002), zf - 0.0002)]
    for i in range(6):
        a = 4 * i
        faces += [(a, a + 1, a + 5, a + 4), (a + 2, a + 3, a + 7, a + 6)]
    raw2(b, verts, faces, mul(flap, 0.8), 'parchment', ref=(0, 0, (H + zf) / 2))
    verts, faces = [], []
    for j in range(7):
        z = 0.002 + (H - 0.004) * j / 6
        verts += [(-0.0045, pk_depth(-0.0045, z) + 0.0007, z), (0.0045, pk_depth(0.0045, z) + 0.0007, z)]
    for j in range(6):
        a = 2 * j
        faces.append((a, a + 1, a + 3, a + 2))
    raw2(b, verts, faces, mul(KRAFT_D, 0.9), 'parchment', facing=(0, 1, 0))
    # printed label: cream panel, coloured band with two lines of "lettering", the crop
    decal_rect(b, -0.0375, 0.0150, 0.0375, 0.1010, WHITE, 0.0006, nx=6, nz=6, mat='parchment')
    decal_rect(b, -0.0375, 0.0150, 0.0375, 0.0400, band, 0.0010, nx=6, nz=2)
    decal_rect(b, -0.0375, 0.0975, 0.0375, 0.1010, band, 0.0010, nx=6, nz=1)
    cream = srgb(250, 240, 214)
    decal_rect(b, -0.0240, 0.0290, 0.0240, 0.0338, cream, 0.0014, nx=4, nz=1)
    decal_rect(b, -0.0150, 0.0215, 0.0150, 0.0250, cream, 0.0014, nx=3, nz=1)
    art(b)
    return b.build(sharp_angle=40)


# ================================================================ CIDER JUG
def item_cider():
    b = Builder('item_cider', 68)
    S = 0.93
    CREAM, BROWN, BROWN_D, FOOT = srgb(226, 208, 170), srgb(156, 90, 40), srgb(104, 56, 28), srgb(196, 170, 132)
    ctrl = [(0, 0.0), (0.050, 0.0), (0.058, 0.004), (0.066, 0.032), (0.0705, 0.072), (0.068, 0.106), (0.058, 0.136), (0.041, 0.156),
            (0.026, 0.166), (0.0205, 0.175), (0.0200, 0.186)]
    body = smooth_profile(ctrl, 2)
    lipz, dip = 0.186, 0.1195            # dip = how far down the jug was dunked in the brown glaze

    def jr(z):
        for k in range(len(body) - 1):
            (r0, z0), (r1, z1) = body[k], body[k + 1]
            if z1 > z0 and z0 <= z <= z1:
                return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        return body[-1][0]

    # two rings close together so the glaze line is crisp
    edge = [(jr(dip - 0.001), dip - 0.001), (jr(dip + 0.001), dip + 0.001)]
    body = [p for p in body if not dip - 0.007 < p[1] < dip + 0.007]
    k = next(i for i, p in enumerate(body) if p[1] > dip)
    body[k:k] = edge
    prof = body + [(0.0250, lipz + 0.003), (0.0262, lipz + 0.008), (0.0240, lipz + 0.0125), (0.0185, lipz + 0.0135), (0.0165, lipz + 0.010), (0, lipz + 0.010)]

    def glaze(co):
        a = math.atan2(co.y, co.x)
        k = smooth(dip - 0.0006, dip + 0.0006, co.z)
        c = mix(CREAM, BROWN, k)
        c = mix(c, BROWN_D, 0.6 * smooth(0.150, 0.172, co.z) * (0.6 + 0.4 * math.sin(5 * a)))
        c = mix(c, BROWN_D, 0.5 * smooth(lipz, lipz + 0.01, co.z))
        c = mul(c, 1.0 + 0.09 * n3(co.x * 70, co.y * 70, co.z * 70))
        c = mix(c, FOOT, smooth(0.010, 0.003, co.z))
        c = mix(c, mul(CREAM, 0.86), 0.5 * smooth(0.05, 0.012, co.z) * (1 - k))
        hl = math.exp(-((a + 2.25) / 0.2) ** 2) * smooth(0.02, 0.05, co.z) * smooth(0.165, 0.13, co.z)       # painted sheen
        return mix(c, srgb(255, 246, 230), 0.22 * hl)

    with b.at(scale=(S, S, S)):
        b.lathe(prof, mat='plant_glossy', segs=20, color=glaze)
        torus(b, jr(dip + 0.003) + 0.0004, 0.0017, dip + 0.003, n=4, mat='plant_glossy', segs=20, color=mul(BROWN, 0.78))      # throwing ring
        # cork
        ck0, ck1 = srgb(176, 128, 82), srgb(214, 172, 120)
        b.lathe([(0.0160, lipz + 0.006), (0.0178, lipz + 0.020), (0.0182, lipz + 0.027), (0.0165, lipz + 0.0295), (0, lipz + 0.0300)], mat='paint', segs=10,
                color=lambda co: mul(mix(ck0, ck1, smooth(lipz + 0.008, lipz + 0.03, co.z)), 1.0 + 0.16 * n3(co.x * 220, co.y * 220, co.z * 220)))
        # painted apple on the cream belly, turned a little toward the three-quarter view
        z0 = 0.066
        yb = -(jr(z0) + 0.0008)
        with b.at(rot=(0, 0, 18)):
            b.blob((0.0200, 0.0034, 0.0186), loc=(0, yb, z0), mat='paint', subdiv=2, color=mul(A_RED, 0.8), color_top=srgb(214, 52, 44))
            b.blob((0.0052, 0.0014, 0.0038), loc=(-0.0075, yb - 0.0026, z0 + 0.007), rot=(0, 30, 0), mat='paint', subdiv=1, color=srgb(250, 170, 150))
            b.tube([(0.0, yb - 0.001, z0 + 0.0155), (0.003, yb - 0.001, z0 + 0.028)], 0.0016, mat='paint', segs=4, color=srgb(96, 62, 40))
            b.blob((0.0100, 0.0016, 0.0046), loc=(0.0110, yb - 0.0006, z0 + 0.0245), rot=(0, -28, 0), mat='paint', subdiv=1, color=LEAF_G)
        # rope: two turns round the neck, a knot, and a carrying loop hanging down over the shoulder
        zn = 0.1785
        rn = jr(zn) + 0.0036
        torus(b, rn, 0.0038, zn - 0.0036, n=4, mat='rope', segs=12)
        torus(b, rn + 0.0003, 0.0038, zn + 0.0036, n=4, mat='rope', segs=12, rot=(3, 2, 0))
        loop = []
        zt, zb, pc = zn - 0.001, 0.104, math.radians(-24)
        for i in range(13):
            th = pi * i / 12                          # down one strand, round the bottom, back up the other
            z = zt - (zt - zb) * math.sin(th) ** 0.8
            ph = pc - math.cos(th) * math.radians(9 + 15 * math.sin(th))
            rr = jr(z) + 0.0046 + 0.004 * smooth(0.166, 0.176, z)
            loop.append((rr * math.cos(ph), rr * math.sin(ph), z))
        b.tube(loop, 0.0042, mat='rope', segs=5)
        kc = Vector((0.004, -(rn + 0.004), zn))
        b.blob((0.0075, 0.006, 0.0075), loc=kc, mat='rope', subdiv=1)
        for sg, ln in ((-1, 0.036), (1, 0.027)):
            b.tube([kc, kc + Vector((sg * 0.010, -0.006, -0.012)), kc + Vector((sg * 0.016, -0.014, -ln)) + Vector((0, -0.006, 0))], 0.0031, mat='rope', segs=3)
    return b.build(sharp_angle=60)


# ================================================================ registry
ASSETS = {
    'item_wood': item_wood, 'item_stone': item_stone,
    'item_apple': item_apple, 'item_tart': item_tart, 'item_cider': item_cider,
    'item_weeds': item_weeds, 'item_compost': item_compost,
    'seed_wheat': lambda: seed_packet('seed_wheat', srgb(206, 150, 44), art_wheat, 71),
    'seed_tomato': lambda: seed_packet('seed_tomato', srgb(196, 48, 38), art_tomato, 72),
    'seed_pumpkin': lambda: seed_packet('seed_pumpkin', srgb(222, 112, 30), art_pumpkin, 73),
    'seed_carrot': lambda: seed_packet('seed_carrot', srgb(74, 138, 66), art_carrot, 74),
    'seed_cabbage': lambda: seed_packet('seed_cabbage', srgb(64, 128, 140), art_cabbage, 75),
}
GROUPS = {
    'raw': ['item_wood', 'item_stone'],
    'orchard': ['item_apple', 'item_tart', 'item_cider'],
    'waste': ['item_weeds', 'item_compost'],
    'seeds': ['seed_wheat', 'seed_tomato', 'seed_pumpkin', 'seed_carrot', 'seed_cabbage'],
}
BUDGET = {'item_wood': 2500, 'item_stone': 1500, 'item_apple': 1000, 'item_tart': 3500, 'item_weeds': 2000, 'item_compost': 2000,
          'item_cider': 2000, 'seed_wheat': 1200, 'seed_tomato': 1200, 'seed_pumpkin': 1200, 'seed_carrot': 1200, 'seed_cabbage': 1200}


# ================================================================ previews
def shot(name, objs, az=35, el=22, zoom=1.0, size=(1000, 800), cam_pos=None, target=None, lens=60, floor=True, focus=None):
    """Render objs (+children) only. focus=(centre, radius) overrides the framing; cam_pos/target give an explicit camera."""
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    objs = kit._descend(objs)
    keep = set(objs)
    hidden = []
    for o in bpy.data.objects:
        if o not in keep and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    pts = []
    for o in objs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    rad = (hi - lo).length / 2
    if focus:
        c, rad = Vector(focus[0]), focus[1]
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = lens
    a, e = math.radians(az), math.radians(el)
    if cam_pos is not None:
        cam.location = Vector(cam_pos)
        c = Vector(target)
        d = (c - cam.location).length
    else:
        d = rad / math.tan(math.radians(13)) / zoom
        cam.location = c + Vector((math.sin(a) * math.cos(e) * d, -math.cos(a) * math.cos(e) * d, math.sin(e) * d))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start = 0.01
    cam.data.clip_end = d * 4 + 10
    sc.camera = cam
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 3.8
    sun.data.color = (1.0, 0.88, 0.72)
    sun.data.angle = math.radians(5)
    sun.rotation_euler = Euler((math.radians(55), 0, a + math.radians(50)))
    extra = [cam, sun]
    if floor:
        fm = bpy.data.meshes.new('_pv_floor')
        fb = bmesh.new()
        bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=max(rad * 14, 2))
        fb.to_mesh(fm)
        fb.free()
        fl = bpy.data.objects.new('_pv_floor', fm)
        fl.location = (c.x, c.y, lo.z - 0.0005)
        sc.collection.objects.link(fl)
        fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
        try:
            fmat.use_nodes = True
            bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            bs.inputs['Base Color'].default_value = (0.30, 0.38, 0.20, 1)
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
    sc.render.filepath = os.path.join(PREV, name + '.png')
    bpy.ops.render.render(write_still=True)
    for o in extra:
        bpy.data.objects.remove(o)
    for o in hidden:
        o.hide_render = False
    print('[goods] preview', sc.render.filepath)


def preview_group(g, objs):
    sel = [objs[m] for m in GROUPS[g]]
    for o in sel:
        shot(o.name, [o], az=35, el=28)
        shot(o.name + '_b', [o], az=-140, el=18)
        if g == 'seeds':
            shot(o.name + '_front', [o], az=8, el=6)
    sp = max(max(o.dimensions.x for o in sel) * 1.35, 0.2)
    for i, o in enumerate(sel):
        o.location.x = (i - (len(sel) - 1) / 2) * sp
    bpy.context.view_layer.update()
    shot('group_' + g, sel, az=25, el=24)
    for o in sel:
        o.location.x = 0
    bpy.context.view_layer.update()


def import_reference(names):
    """Preview only: pull a few existing goods out of items.glb for a scale comparison (never exported)."""
    if not os.path.exists(ITEMS_GLB):
        return []
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ITEMS_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    keep = []
    for o in new:
        if o.name in names and o.type == 'MESH':
            for slot in o.material_slots:
                base = slot.material.name.split('.')[0] if slot.material else None
                if base in kit.PREVIEW:
                    slot.material = kit.get_mat(base) if bpy.data.materials.get(base) is None else bpy.data.materials[base]
            ca = o.data.color_attributes
            if len(ca) and ca.get('Color') is None:
                ca[0].name = 'Color'
            o.parent = None
            keep.append(o)
    for o in new:
        if o not in keep:
            bpy.data.objects.remove(o)
    return keep


def preview_all(objs):
    """All eight kinds of goods together, and again next to some of the existing goods."""
    place = {
        'item_compost': (-0.52, 0.20), 'item_wood': (-0.06, 0.24), 'item_stone': (0.52, 0.22),
        'item_weeds': (-0.60, -0.16), 'item_tart': (-0.22, -0.20), 'item_cider': (0.05, -0.14), 'item_apple': (0.21, -0.24),
        'seed_wheat': (0.36, -0.14), 'seed_tomato': (0.47, -0.17), 'seed_pumpkin': (0.58, -0.20), 'seed_carrot': (0.69, -0.23),
        'seed_cabbage': (0.80, -0.26),
    }
    for n, (x, y) in place.items():
        objs[n].location = (x, y, 0)
        if n.startswith('seed_'):
            objs[n].rotation_euler = Euler((math.radians(-10), 0, math.radians(12)))
    bpy.context.view_layer.update()
    sel = [objs[n] for n in place]
    shot('group_all', sel, az=20, el=27, size=(1600, 1000), zoom=1.15)
    ref = import_reference({'item_pumpkin', 'item_pie', 'item_bread', 'item_chutney', 'item_eggs'})
    for o, (x, y) in zip(sorted(ref, key=lambda o: o.name), ((-0.30, 0.56), (-0.02, 0.58), (0.22, 0.56), (0.48, 0.58), (0.84, 0.50))):
        o.location = (x, y, 0)
        o.rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()
    if ref:
        shot('group_scale', sel + ref, az=20, el=30, size=(1600, 1100), zoom=1.1)
    for o in ref:
        bpy.data.objects.remove(o)
    for n in place:
        objs[n].location = (0, 0, 0)
        objs[n].rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()


# ================================================================ build
def report(o, depth=0):
    bpy.context.view_layer.update()
    pad = '   ' * depth
    if o.type == 'MESH':
        bb = [Vector(c) for c in o.bound_box]
        lo = [min(p[i] for p in bb) for i in range(3)]
        hi = [max(p[i] for p in bb) for i in range(3)]
        print(f'{pad}ASSET {o.name:20s} loc=({o.location.x:.3f},{o.location.y:.3f},{o.location.z:.3f}) '
              f'bbox=({lo[0]:.3f},{lo[1]:.3f},{lo[2]:.3f})..({hi[0]:.3f},{hi[1]:.3f},{hi[2]:.3f}) tris={kit.tri_count([o])} '
              f'mats={[m.name for m in o.data.materials]}')
    else:
        print(f'{pad}MARKER {o.name} ({o.location.x:.4f},{o.location.y:.4f},{o.location.z:.4f})')
    for c in o.children:
        report(c, depth + 1)


names = list(ASSETS)
if ONLY:
    names = [n for n in names if any(n in GROUPS[g] for g in ONLY if g in GROUPS) or n in ONLY]
objs = {}
for n in names:
    objs[n] = ASSETS[n]()
    report(objs[n])
    tris = kit.tri_count([objs[n]])
    print(f'   TOTAL {n} tris={tris} budget={BUDGET[n]}{"  ** OVER BUDGET **" if tris > BUDGET[n] else ""}')

if not ONLY:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kit.export_glb(OUT, list(objs.values()))

if PREV:
    os.makedirs(PREV, exist_ok=True)
    if ONLY:
        for n in names:
            shot(n, [objs[n]], az=35, el=28)
            shot(n + '_b', [objs[n]], az=-140, el=18)
            if n.startswith('seed_'):
                shot(n + '_front', [objs[n]], az=8, el=6)
    else:
        for g in GROUPS:
            preview_group(g, objs)
        preview_all(objs)
