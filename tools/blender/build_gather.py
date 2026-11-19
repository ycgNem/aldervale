"""Gathering kit: clearing tools (pick-mattock, axe) and the things you clear with them
(weed clump, field stone, fallen log, tree stump, branch pile).

  blender --background --factory-startup --python tools/blender/build_gather.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/gather.glb.
With group names only those groups are built + previewed (no export) for fast iteration.

Tool convention (identical to tool_hoe in build_character.py): origin = where the right hand grips,
haft along +Z, head at the top, working edge (adze blade / axe bit) pointing -Y.
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, Euler, Matrix, noise  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'gather.glb')

kit.reset()
pi = math.pi


# ============================================================================================
# HELPERS
# ============================================================================================
def R(b, a, c):
    return b.rng.uniform(a, c)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def aim(d):
    """Euler degrees (XYZ) that rotate local +Z onto direction d."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(d).normalized())
    return tuple(math.degrees(a) for a in q.to_euler('XYZ'))


def table(tab, u):
    """Smooth interpolation through [(u, v0, v1, ...), ...] -> tuple of values."""
    if u <= tab[0][0]:
        return tab[0][1:]
    for k in range(len(tab) - 1):
        a, c = tab[k], tab[k + 1]
        if u <= c[0]:
            t = (u - a[0]) / (c[0] - a[0])
            t = t * t * (3 - 2 * t) * 0.5 + t * 0.5
            return tuple(a[i] * (1 - t) + c[i] * t for i in range(1, len(a)))
    return tab[-1][1:]


def nfaces(b):
    return len(b.bm.faces)


def swap_uv(b, n0):
    uv = b.bm.loops.layers.uv['UVMap']
    for i, f in enumerate(b.bm.faces):
        if i < n0:
            continue
        for l in f.loops:
            u, v = l[uv].uv
            l[uv].uv = (v, u)


def raw(b, verts, faces, cols, mat='plant', loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), jitter=0.0):
    """Arbitrary small mesh with per-vertex colours (list) or one colour (tuple)."""
    t = b._new()
    uv, col, _ = b._layers(t)
    bv = [t.verts.new(v) for v in verts]
    j = 1.0 + b.rng.uniform(-jitter, jitter) if jitter else 1.0
    for f in faces:
        try:
            face = t.faces.new([bv[i] for i in f])
        except ValueError:
            continue
        for l, i in zip(face.loops, f):
            c = cols[i] if isinstance(cols, list) else cols
            l[col] = (c[0] * j, c[1] * j, c[2] * j, 1.0)
            l[uv].uv = (verts[i][0], verts[i][2])
    t.normal_update()
    b._emit(t, mat, loc, rot, scale)


def loft(b, rings, mat, color=(1, 1, 1), cap0=True, cap1=True, along_u=True, jitter=0.0, out_dir=None,
         loc=(0, 0, 0), rot=(0, 0, 0)):
    """Skin a list of closed rings (same vertex count). UV: U along / V around (along_u) or swapped.
    color: tuple or fn(co)->rgb. Winding is fixed so normals point away from the centre line
    (or along out_dir when given)."""
    t = b._new()
    uvl, col, _ = b._layers(t)
    RR = [[Vector(p) for p in ring] for ring in rings]
    n = len(RR[0])
    V = [[t.verts.new(p) for p in ring] for ring in RR]
    cen = [sum(ring, Vector()) / n for ring in RR]
    L = [0.0]
    for k in range(1, len(RR)):
        L.append(L[-1] + (cen[k] - cen[k - 1]).length)
    big = max(RR, key=lambda ring: sum((ring[i] - ring[i - 1]).length for i in range(n)))
    per = [0.0]
    for i in range(n):
        per.append(per[-1] + (big[(i + 1) % n] - big[i]).length)
    ou, ov = b.rng.random() * 5, b.rng.random() * 5
    side = []
    for k in range(len(RR) - 1):
        for i in range(n):
            i2 = (i + 1) % n
            try:
                f = t.faces.new((V[k][i], V[k][i2], V[k + 1][i2], V[k + 1][i]))
            except ValueError:
                continue
            side.append((f, k))
            dat = [(L[k], per[i]), (L[k], per[i + 1]), (L[k + 1], per[i + 1]), (L[k + 1], per[i])]
            for l, (a, c) in zip(f.loops, dat):
                l[uvl].uv = (a + ou, c + ov) if along_u else (c + ou, a + ov)
    for cap, k in ((cap0, 0), (cap1, len(RR) - 1)):
        if not cap:
            continue
        cv = t.verts.new(cen[k])
        nrm = (RR[k][1] - cen[k]).cross(RR[k][0] - cen[k])
        nrm = nrm.normalized() if nrm.length > 1e-12 else Vector((0, 0, 1))
        ux = nrm.orthogonal().normalized()
        uy = nrm.cross(ux)
        for i in range(n):
            i2 = (i + 1) % n
            try:
                f = t.faces.new((cv, V[k][i2], V[k][i]) if k == 0 else (cv, V[k][i], V[k][i2]))
            except ValueError:
                continue
            for l in f.loops:
                d = l.vert.co - cen[k]
                l[uvl].uv = (d.dot(ux) + ou, d.dot(uy) + ov)
    bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
    t.normal_update()
    if out_dir is not None:
        od = Vector(out_dir)
        s = sum(f.normal.dot(od) * f.calc_area() for f in t.faces)
    else:
        s = sum(f.normal.dot(f.calc_center_median() - (cen[k] + cen[k + 1]) / 2) * f.calc_area() for f, k in side)
    if s < 0:
        bmesh.ops.reverse_faces(t, faces=t.faces[:])
        t.normal_update()
    j = 1.0 + b.rng.uniform(-jitter, jitter) if jitter else 1.0
    for f in t.faces:
        for l in f.loops:
            c = color(l.vert.co) if callable(color) else color
            l[col] = (c[0] * j, c[1] * j, c[2] * j, 1.0)
    b._emit(t, mat, loc, rot)


def disc(b, ring, pith, fracs, mat, tones, out_dir, base=(1, 1, 1), rounder=True):
    """Flat end-grain: concentric annuli between `pith` and `ring`, one tone per annulus (growth rings)."""
    t = b._new()
    uvl, col, _ = b._layers(t)
    ring = [Vector(p) for p in ring]
    pith = Vector(pith)
    n = len(ring)
    od = Vector(out_dir).normalized()
    ux = od.orthogonal().normalized()
    uy = od.cross(ux)
    layers = []
    for f in fracs:
        if f <= 1e-6:
            layers.append([t.verts.new(pith)])
        else:
            mean = sum((p - pith).length for p in ring) / n
            row = []
            for p in ring:
                d = p - pith
                r = d.length
                k = (mean + (r - mean) * f ** 3) / r if (rounder and r > 1e-9) else 1.0   # inner rings are rounder than the bark line
                row.append(t.verts.new(pith + d * (f * k)))
            layers.append(row)
    for k in range(len(fracs) - 1):
        A, B = layers[k], layers[k + 1]
        tone = tones[k % len(tones)] * R(b, 0.96, 1.04)
        for i in range(n):
            i2 = (i + 1) % n
            f = t.faces.new((A[0], B[i], B[i2])) if len(A) == 1 else t.faces.new((A[i], B[i], B[i2], A[i2]))
            for l in f.loops:
                l[col] = (base[0] * tone, base[1] * tone, base[2] * tone, 1.0)
                d = l.vert.co - pith
                l[uvl].uv = (d.dot(ux), d.dot(uy))
    t.normal_update()
    if sum(f.normal.dot(od) * f.calc_area() for f in t.faces) < 0:
        bmesh.ops.reverse_faces(t, faces=t.faces[:])
        t.normal_update()
    b._emit(t, mat, (0, 0, 0), (0, 0, 0))


def oval(cx, cy, z, rx, ry, n=16, ph=0.0):
    return [(cx + rx * math.cos(2 * pi * i / n + ph), cy + ry * math.sin(2 * pi * i / n + ph), z) for i in range(n)]


def bleaf(b, length, width, loc, rot, c0, c1, bend=40, fold=20, segs=5, shape=None, c_edge=None, edge_from=0.5,
          c_rib=None, wave=0.0, wave_n=2.5, mat='plant', jitter=0.08):
    """Leaf like kit.leaf (base at origin, grows +Z, droops to +X) but with wavy margins, a paler
    midrib and discoloured edges, all in vertex colours."""
    if shape is None:
        def shape(u):
            return max(math.sin(pi * (u ** 0.75)) ** 0.8, 0.12 if u < 0.5 else 0.0)
    verts, cols, faces = [], [], []
    x = z = 0.0
    ang = 0.0
    step = length / segs
    fr = math.radians(fold)
    ph = R(b, 0, 6.28)
    for i in range(segs + 1):
        u = i / segs
        w = width * 0.5 * shape(u)
        dx, dz = math.sin(ang), math.cos(ang)
        nx, nz = -dz, dx
        cw = math.cos(fr) * w
        base = mix(c0, c1, u)
        for s in (-1, 0, 1):
            lift = 0.0
            if s:
                lift = math.sin(fr) * w + wave * width * math.sin(u * wave_n * 2 * pi + ph + (0 if s < 0 else 2.1)) * min(1.0, u * 3)
            verts.append((x + nx * lift, s * cw, z + nz * lift))
            if s == 0:
                cols.append(mix(base, c_rib, 0.6) if c_rib else base)
            else:
                cols.append(mix(base, c_edge, smooth(edge_from, 1.0, u)) if c_edge else mul(base, 0.92))
        ang += math.radians(bend) / segs
        x += math.sin(ang) * step
        z += math.cos(ang) * step
    for i in range(segs):
        a, c = i * 3, (i + 1) * 3
        faces.append((a, a + 1, c + 1, c))
        faces.append((a + 1, a + 2, c + 2, c + 1))
    raw(b, verts, faces, cols, mat, loc, rot, jitter=jitter)


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


MOSS0, MOSS1, MOSS_Y = srgb(46, 84, 32), srgb(112, 156, 56), srgb(164, 172, 70)


def moss_col(seed):
    off = Vector((seed * 1.7, seed * 0.9, seed * 2.3))

    def f(co):
        n = noise.noise(co * 9.0 + off)
        c = mix(MOSS0, MOSS1, 0.5 + 0.9 * n)
        return mix(c, MOSS_Y, max(0.0, noise.noise(co * 5.0 - off)) * 0.7)

    return f


def lobed(seed, amt=0.16):
    """deform fn: irregular, lobed outline for a flat cushion (so moss does not read as a disc)."""
    p1, p2 = seed * 1.9, seed * 4.3

    def f(c):
        th = math.atan2(c.y, c.x)
        k = 1 + amt * math.sin(3 * th + p1) + amt * 0.6 * math.sin(5 * th + p2) + amt * 0.35 * math.sin(8 * th + p1 * 2)
        return Vector((c.x * k, c.y * k, c.z))

    return f


def moss(b, radii, loc, normal, seed=1, subdiv=2, amp=0.16):
    """Moss cushion: lumpy flattened blob whose local +Z is the surface normal."""
    b.blob(radii, loc=loc, rot=aim(normal), mat='plant', subdiv=subdiv, noise_amp=amp, noise_scale=1.9,
           flatten_bottom=-0.35, color=moss_col(seed), deform=lobed(seed))


# ============================================================================================
# TOOLS
# ============================================================================================
def crect(hx, hz, ch):
    """Chamfered rectangle (x, z) with 8 corners, counter-clockwise seen from +Y."""
    c = min(ch, 0.42 * min(hx, hz))
    return [(hx - c, hz), (hx, hz - c), (hx, -hz + c), (hx - c, -hz), (-hx + c, -hz), (-hx, -hz + c), (-hx, hz - c), (-hx + c, hz)]


def iron(seed, lo=0.9, hi=1.08):
    off = Vector((seed * 3.1, seed * 1.7, seed * 0.7))

    def f(co):
        k = (lo + hi) / 2 + (hi - lo) * 0.9 * noise.noise(co * 28.0 + off)
        return (k, k, k * 0.99)

    return f


def grip_wrap(b, z0, z1, rxy, turns, n=16):
    """Leather strip wound round the haft: one soft ridge per turn. rxy(z) -> (rx, ry, cy)."""
    rings = []
    h = (z1 - z0) / turns
    for k in range(turns):
        za = z0 + k * h
        for dz, d in ((0.05, 0.0012), (0.28, 0.0034), (0.74, 0.003), (0.95, 0.0014)):
            z = za + dz * h
            rx, ry, cy = rxy(z)
            rings.append(oval(0, cy, z, rx + d, ry + d, n))
    rx, ry, cy = rxy(z0)
    rings.insert(0, oval(0, cy, z0 - 0.001, rx - 0.001, ry - 0.001, n))
    rx, ry, cy = rxy(z1)
    rings.append(oval(0, cy, z1 + 0.001, rx - 0.001, ry - 0.001, n))
    lea = (1.0, 0.95, 0.9)
    tones = [R(b, 0.86, 1.1) for _ in range(turns + 1)]
    loft(b, rings, 'leather', color=lambda co: mul(lea, tones[min(turns, max(0, int((co.z - z0) / h)))]), cap0=False, cap1=False)


def build_pick():
    b = Builder('tool_pick', seed=61)
    ZB, ZT, ZH = -0.45, 0.40, 0.357          # haft bottom / top, head centre line

    # --- ash haft: oval, swelling toward the eye and a little at the butt -------------------
    tab = [(-0.45, 0.0195, 0.0235), (-0.40, 0.0185, 0.0225), (-0.2, 0.0172, 0.0208), (0.0, 0.0168, 0.0202),
           (0.18, 0.0175, 0.0215), (0.30, 0.0195, 0.0245), (0.40, 0.0215, 0.0275)]

    def rxy(z):
        rx, ry = table(tab, z)
        return rx, ry, 0.0

    rings = [oval(0, 0, ZB - 0.006, 0.011, 0.014), oval(0, 0, ZB - 0.003, 0.0165, 0.02)]
    for i in range(12):
        z = ZB + 0.004 + (ZT - 0.004 - ZB) * i / 11
        rx, ry, _ = rxy(z)
        wob = 1 + 0.012 * math.sin(i * 2.3)
        rings.append(oval(0.0009 * math.sin(i * 1.7), 0, z, rx * wob, ry / wob))
    rings += [oval(0, 0, ZT + 0.0045, 0.0205, 0.0262), oval(0, 0, ZT + 0.0065, 0.0185, 0.024)]
    loft(b, rings, 'wood_light', color=lambda co: mul((1, 1, 1), 0.93 + 0.1 * smooth(-0.45, 0.4, co.z) + 0.05 * noise.noise(co * 14)))
    # iron wedge driven into the haft top (diagonal, as a smith would set it)
    b.box((0.033, 0.0055, 0.006), loc=(0, 0, ZT + 0.0065), rot=(0, 0, 58), mat='metal', bevel=0.0012, segs=1, grain=None,
          color=(0.9, 0.9, 0.9))

    # --- forged head: eye sleeve + pick arm (+Y) + adze arm (-Y) -----------------------------
    ex, ey = 0.0305, 0.0395
    eye = [oval(0, 0, z, ex + d, ey + d, 20) for z, d in (
        (0.3185, -0.0035), (0.322, 0.0018), (0.3295, 0.0018), (0.3325, 0.0), (ZH, 0.0012), (0.3815, 0.0), (0.3845, 0.0018),
        (0.392, 0.0018), (0.3955, -0.0035))]
    loft(b, eye, 'metal_dark', color=iron(1))

    def arm(stations, zfn, mat, color, cap0, cap1, ch=0.0045):
        rr = []
        for y, hx, hz in stations:
            zc = zfn(y)
            rr.append([(x, y, zc + z) for x, z in crect(hx, hz, ch)])
        loft(b, rr, mat, color=color, cap0=cap0, cap1=cap1)

    def zpick(y):
        return ZH - 0.5 * y * y

    def zadze(y):
        return ZH - 1.15 * y * y - 0.9 * max(0.0, -y - 0.12) ** 2 * 4

    arm([(0.0, 0.024, 0.028), (0.036, 0.0235, 0.027), (0.058, 0.0205, 0.0235), (0.10, 0.0175, 0.02), (0.15, 0.0145, 0.0165),
         (0.20, 0.0112, 0.0128), (0.24, 0.0082, 0.0092)], zpick, 'metal_dark', iron(2), True, False)
    # worn bright point
    arm([(0.24, 0.0082, 0.0092), (0.265, 0.0058, 0.0064), (0.283, 0.003, 0.0034), (0.291, 0.0011, 0.0012)], zpick, 'metal',
        lambda co: mul((1, 1, 1), 0.72 + 0.3 * smooth(0.24, 0.29, co.y)), False, True, ch=0.002)
    arm([(0.0, 0.024, 0.028), (-0.036, 0.0235, 0.025), (-0.058, 0.0205, 0.019), (-0.082, 0.0215, 0.0135), (-0.11, 0.03, 0.0095),
         (-0.14, 0.04, 0.007), (-0.17, 0.0465, 0.0052), (-0.192, 0.049, 0.0038)], zadze, 'metal_dark', iron(3), True, False,
        ch=0.0034)
    # honed adze edge (bright steel band)
    arm([(-0.192, 0.049, 0.0038), (-0.203, 0.05, 0.0022), (-0.2105, 0.0505, 0.0005)], zadze, 'metal',
        lambda co: mul((1, 1, 1), 0.78 + 0.25 * smooth(-0.192, -0.21, co.y)), False, True, ch=0.0012)

    # --- leather grip wrap + tail ------------------------------------------------------------
    grip_wrap(b, -0.075, 0.075, rxy, 8)
    b.tube([(0.0165, 0.006, -0.071), (0.0215, 0.012, -0.082), (0.022, 0.014, -0.102), (0.0205, 0.011, -0.118)],
           [0.0032, 0.0032, 0.0028, 0.0022], mat='leather', segs=6, color=(0.95, 0.9, 0.85))
    return b.build(sharp_angle=50)


def build_axe():
    b = Builder('tool_axe', seed=62)
    ZT, LEN = 0.326, 0.75
    U0 = ZT / LEN                                                  # u at the grip (z = 0)

    def bow(u):
        return 0.02 * math.sin(1.25 * pi * u) ** 2 - 0.225 * max(0.0, u - 0.55) ** 2

    def yc(z):
        return bow((ZT - z) / LEN) - bow(U0)

    # (u, rx, ry): slim in the eye, belly, throat, fawn's-foot knob
    tab = [(0.0, 0.0112, 0.0235), (0.09, 0.0118, 0.0235), (0.16, 0.0138, 0.0215), (0.30, 0.0152, 0.0205), (0.5, 0.0158, 0.0198),
           (0.72, 0.015, 0.0185), (0.86, 0.0142, 0.0178), (0.94, 0.0162, 0.0215), (0.985, 0.0182, 0.0262), (1.0, 0.0178, 0.0262)]

    def rxy(z):
        rx, ry = table(tab, (ZT - z) / LEN)
        return rx, ry, yc(z)

    rings = []
    N = 22
    for i in range(N + 1):
        u = i / N
        z = ZT - LEN * u
        rx, ry, cy = rxy(z)
        rings.append(oval(0, cy, z, rx, ry))
    zb = ZT - LEN
    yb = yc(zb)
    rings += [oval(0, yb - 0.0015, zb - 0.006, 0.0155, 0.0225), oval(0, yb - 0.002, zb - 0.0095, 0.0105, 0.0155)]
    y0 = yc(ZT)
    rings = [oval(0, y0, ZT + 0.0075, 0.0095, 0.021), oval(0, y0, ZT + 0.0055, 0.0112, 0.0232)] + rings
    loft(b, rings, 'wood_light', color=lambda co: mul((1.0, 0.97, 0.93), 0.92 + 0.1 * smooth(-0.42, 0.3, co.z) + 0.05 * noise.noise(co * 14)))
    # wedge: hardwood along the eye + iron cross wedge
    b.box((0.0045, 0.036, 0.004), loc=(0, y0, ZT + 0.008), mat='wood_dark', bevel=0.001, segs=1, grain=1)
    b.box((0.017, 0.0045, 0.005), loc=(0, y0 - 0.004, ZT + 0.0085), rot=(0, 0, 24), mat='metal', bevel=0.001, segs=1, grain=None,
          color=(0.9, 0.9, 0.9))

    # --- bearded head --------------------------------------------------------------------------
    ZC = 0.287
    # (y, z_top, z_bot, half thickness, edge bulge)
    st = [(0.043, 0.022, -0.022, 0.0125, 0.0), (0.038, 0.027, -0.027, 0.017, 0.0), (0.02, 0.0295, -0.0295, 0.0192, 0.0),
          (0.0, 0.0305, -0.031, 0.0198, 0.0), (-0.024, 0.0305, -0.032, 0.0185, 0.0), (-0.044, 0.031, -0.035, 0.014, 0.001),
          (-0.062, 0.0325, -0.046, 0.0105, 0.002), (-0.08, 0.035, -0.067, 0.0082, 0.004), (-0.098, 0.038, -0.092, 0.0064, 0.006),
          (-0.116, 0.0415, -0.109, 0.0048, 0.009), (-0.130, 0.0445, -0.117, 0.0036, 0.011)]
    edge = [(-0.130, 0.0445, -0.117, 0.0036, 0.011), (-0.139, 0.046, -0.1205, 0.0019, 0.0125), (-0.1455, 0.047, -0.1225, 0.00035, 0.0135)]
    NZ = 7

    def head_ring(y, zt, zb_, w, bulge):
        c = min(0.0042, 0.45 * w)
        pts = [(w - c, y0 + y - bulge * 0.1, ZC + zt)]
        side = []
        for k in range(NZ):
            v = k / (NZ - 1)
            z = (zt - c) + ((zb_ + c) - (zt - c)) * v
            yy = y0 + y - bulge * (1 - (2 * v - 1) ** 2) - bulge * 0.1
            side.append((yy, ZC + z))
        pts += [(w, yy, z) for yy, z in side]
        pts.append((w - c, side[-1][0], ZC + zb_))
        pts.append((-(w - c), side[-1][0], ZC + zb_))
        pts += [(-w, yy, z) for yy, z in reversed(side)]
        pts.append((-(w - c), y0 + y - bulge * 0.1, ZC + zt))
        return pts

    body_c = iron(4, 0.86, 1.06)
    loft(b, [head_ring(*s) for s in st], 'metal_dark',
         color=lambda co: mul(body_c(co), 0.9 + 0.16 * smooth(0.0, -0.13, co.y - y0)), cap0=True, cap1=False)
    loft(b, [head_ring(*s) for s in edge], 'metal',
         color=lambda co: mul((1, 1, 1), 0.74 + 0.3 * smooth(-0.128, -0.15, co.y - y0)), cap0=False, cap1=True)

    # --- grip wrap ----------------------------------------------------------------------------
    grip_wrap(b, -0.06, 0.06, rxy, 7)
    return b.build(sharp_angle=50)


# ============================================================================================
# WEEDS
# ============================================================================================
DK0, DK1, DK_RIB, DK_Y = srgb(40, 92, 38), srgb(102, 152, 58), srgb(168, 186, 110), srgb(190, 176, 72)
TH0, TH1, TH_ST = srgb(58, 104, 60), srgb(128, 162, 104), srgb(104, 140, 88)
GR0, GR1, GR_Y = srgb(60, 112, 48), srgb(150, 180, 84), srgb(204, 190, 100)
DN0, DN1 = srgb(52, 110, 40), srgb(116, 168, 62)


def DOCK(u):
    if u < 0.2:
        return 0.13
    v = (u - 0.2) / 0.8
    return max(0.2, math.sin(pi * (0.08 + 0.9 * v) ** 0.85) ** 0.6)


def TOOTH(k=0.45, n=4.0):
    def f(u):
        if u < 0.02:
            return 0.1
        env = math.sin(pi * (0.1 + 0.9 * u) ** 1.25) ** 0.7
        return env * (1.0 if int(u * n * 2 + 0.5) % 2 == 1 else k)
    return f


def grass_tuft(b, x, y, n=7, h=(0.2, 0.42), yellow=0.25):
    for k in range(n):
        a = k * 360 / n + R(b, -25, 25)
        top = GR_Y if b.rng.random() < yellow else GR1
        b.leaf(R(b, *h), R(b, 0.013, 0.02), loc=(x + R(b, -0.02, 0.02), y + R(b, -0.02, 0.02), 0),
               rot=(0, R(b, 3, 20), a), bend=R(b, 15, 60), fold=28, segs=3, color=GR0, color_top=top, jitter=0.1)


def thistle_head(b, p, d, s=1.0):
    e = aim(d)
    zig = lambda a, z: 1.0 if round(a / (2 * pi) * 16) % 2 == 0 else 0.8  # noqa: E731
    b.lathe([(0, 0), (0.016 * s, 0.002 * s), (0.03 * s, 0.018 * s), (0.031 * s, 0.034 * s), (0.021 * s, 0.05 * s), (0.014 * s, 0.056 * s)],
            loc=p, rot=e, mat='plant', segs=16, color=srgb(70, 112, 62), color_top=srgb(120, 150, 92), radial=zig)
    # spiny bracts
    for k in range(7):
        a = k * 360 / 7 + R(b, -10, 10)
        with b.at(loc=p, rot=e):
            b.leaf(0.034 * s, 0.011 * s, loc=(0.024 * s * math.cos(math.radians(a)), 0.024 * s * math.sin(math.radians(a)), 0.014 * s),
                   rot=(0, 62, a), bend=-25, fold=10, segs=2, color=srgb(80, 124, 66), color_top=srgb(160, 180, 120))
    top = Vector(p) + Vector(d).normalized() * 0.05 * s
    # shaving-brush tuft of purple florets
    b.lathe([(0.013 * s, 0), (0.023 * s, 0.016 * s), (0.035 * s, 0.04 * s), (0.032 * s, 0.052 * s), (0.018 * s, 0.06 * s), (0, 0.063 * s)],
            loc=top, rot=e, mat='plant', segs=16, color=srgb(120, 50, 140), color_top=srgb(214, 132, 222), radial=zig)


def seed_spike(b, base, d, L, r, segs=6):
    """Dock seed head: a stalk strung with rusty bead-like whorls, thinning to the tip."""
    c0, c1 = srgb(118, 60, 36), srgb(178, 108, 60)
    n = max(3, int(L / 0.03))
    prof = [(r * 0.25, 0.0)]
    for i in range(n):
        z = i * L / n
        rr = r * (1 - 0.6 * (i / n) ** 1.3) * (0.85 + 0.3 * b.rng.random())
        h = L / n
        prof += [(rr * 0.45, z + h * 0.06), (rr, z + h * 0.42), (rr * 0.5, z + h * 0.9)]
    prof.append((0, L + 0.006))
    ph = R(b, 0, 6)
    b.lathe(prof, loc=tuple(base), rot=aim(d), mat='plant', segs=segs, color=c0, color_top=c1, jitter=0.08,
            radial=lambda a, z: 1 + 0.16 * math.sin(3 * a + z * 55 + ph))


def build_weeds():
    b = Builder('weed_clump', seed=71)
    # --- broad-leaved dock (back right) -------------------------------------------------------
    dx, dy = 0.06, 0.05
    for k in range(9):
        a = k * 360 / 9 + R(b, -14, 14)
        big = k % 2 == 0
        L = R(b, 0.27, 0.33) if big else R(b, 0.18, 0.24)
        old = k in (2, 5)
        bleaf(b, L, L * R(b, 0.38, 0.46), (dx + R(b, -0.012, 0.012), dy + R(b, -0.012, 0.012), 0), (0, R(b, 16, 30) if big else R(b, 6, 18), a),
              DK0, mix(DK1, DK_Y, 0.35 if old else 0.0), bend=R(b, 75, 110) if big else R(b, 35, 60), fold=R(b, 14, 24), segs=6,
              shape=DOCK, c_edge=DK_Y if old else mix(DK1, DK_Y, 0.25), edge_from=0.35 if old else 0.7, c_rib=DK_RIB,
              wave=0.06, wave_n=R(b, 2.2, 3.2))
    # rusty seed spikes on a ribbed stalk
    sp = [Vector((dx, dy, 0)), Vector((dx + 0.008, dy + 0.004, 0.14)), Vector((dx + 0.016, dy + 0.012, 0.27))]
    b.tube(sp, [0.0085, 0.007, 0.0055], mat='plant', segs=5, caps=False, color=srgb(96, 124, 58), color_top=srgb(140, 92, 54))
    seed_spike(b, sp[2] - Vector((0, 0, 0.02)), (0.05, 0.05, 1), 0.24, 0.02, segs=5)
    for (z, a, L) in ((0.17, 200, 0.13), (0.22, 50, 0.11)):
        d = Vector((math.cos(math.radians(a)) * 0.42, math.sin(math.radians(a)) * 0.42, 1))
        seed_spike(b, Vector((dx + 0.01, dy + 0.006, z)), d, L, 0.013, segs=4)

    # --- thistle (left of centre, leaning out) -----------------------------------------------
    tx, ty = -0.09, 0.0
    stem = [Vector((tx, ty, 0)), Vector((tx - 0.01, ty + 0.004, 0.16)), Vector((tx - 0.024, ty - 0.004, 0.32)), Vector((tx - 0.034, ty - 0.012, 0.44))]
    b.tube(stem, [0.012, 0.0102, 0.0086, 0.0072], mat='plant', segs=6, caps=False, color=TH_ST, color_top=mix(TH_ST, TH1, 0.6))
    for k in range(9):
        t = k / 8
        zz = 0.015 + 0.36 * t ** 1.1
        seg = min(2, int(zz / 0.16))
        f = (zz - stem[seg].z) / (stem[seg + 1].z - stem[seg].z)
        p = stem[seg].lerp(stem[seg + 1], f)
        L = 0.21 - 0.13 * t + R(b, -0.012, 0.012)
        bleaf(b, L, L * 0.46, tuple(p), (0, 40 + 24 * (1 - t) + R(b, -8, 8), k * 137.5 + R(b, -12, 12)), TH0, TH1,
              bend=R(b, 40, 70), fold=30, segs=8, shape=TOOTH(0.4), c_edge=mul(TH1, 1.15), edge_from=0.0, c_rib=srgb(176, 196, 156),
              wave=0.05, wave_n=4)
    thistle_head(b, tuple(stem[-1]), stem[-1] - stem[-2], 1.05)
    sb = stem[2] + Vector((0, 0, -0.03))
    se = sb + Vector((0.07, -0.045, 0.1))
    b.tube([sb, sb.lerp(se, 0.5) + Vector((0.012, -0.006, -0.01)), se], [0.006, 0.0052, 0.0046], mat='plant', segs=5, caps=False,
           color=TH_ST, color_top=mix(TH_ST, TH1, 0.6))
    thistle_head(b, tuple(se), Vector((0.3, -0.2, 1)), 0.72)

    # --- dandelion rosette (front) ------------------------------------------------------------
    nx, ny = 0.04, -0.13
    for k in range(10):
        a = k * 36 + R(b, -12, 12)
        L = R(b, 0.11, 0.16)
        bleaf(b, L, L * 0.34, (nx, ny, 0.004), (0, R(b, 58, 78), a), DN0, DN1, bend=R(b, 8, 30), fold=14, segs=6, shape=TOOTH(0.38, 3.0),
              c_rib=srgb(170, 196, 120), c_edge=mul(DN1, 1.05), edge_from=0.2)
    for (ox, oy, h, kind) in ((0.03, -0.012, 0.19, 'flower'), (-0.04, -0.03, 0.14, 'flower'), (-0.01, 0.03, 0.26, 'clock')):
        top = Vector((nx + ox, ny + oy, h))
        mid = Vector((nx + ox * 0.8, ny + oy * 0.8, h * 0.5))
        b.tube([(nx, ny, 0), mid, top], 0.0048, mat='plant', segs=5, caps=False, color=srgb(150, 176, 104), color_top=srgb(172, 168, 120))
        d = (top - mid).normalized() + Vector((ox * 2, oy * 2 - 0.12, 0.5))
        e = aim(d)
        if kind == 'flower':
            zig = lambda a, z: 1.0 if round(a / (2 * pi) * 16) % 2 == 0 else 0.76  # noqa: E731
            b.lathe([(0.005, -0.014), (0.015, -0.004), (0.012, 0.004)], loc=top, rot=e, mat='plant', segs=8, color=srgb(74, 128, 52))
            b.lathe([(0.008, 0.0), (0.033, 0.003), (0.034, 0.007), (0.022, 0.011)], loc=top, rot=e, mat='plant', segs=16,
                    color=srgb(236, 170, 20), color_top=srgb(255, 214, 50), radial=zig)
            b.lathe([(0.023, 0.008), (0.02, 0.014), (0.01, 0.018), (0, 0.019)], loc=top, rot=(e[0], e[1], e[2] + 11), mat='plant', segs=16,
                    color=srgb(250, 204, 40), color_top=srgb(255, 232, 96), radial=zig)
        else:
            b.blob(0.034, loc=tuple(top + (top - mid).normalized() * 0.024), mat='plant', subdiv=2, noise_amp=0.1, noise_scale=4,
                   color=srgb(190, 190, 178), color_top=srgb(246, 246, 238))

    # --- grass tufts round the edge -----------------------------------------------------------
    for (gx, gy, n, h) in ((-0.16, -0.12, 8, (0.2, 0.38)), (0.19, -0.07, 7, (0.18, 0.32)), (-0.13, 0.15, 8, (0.22, 0.42)),
                           (0.17, 0.16, 6, (0.16, 0.3)), (-0.01, 0.2, 6, (0.2, 0.36)), (-0.21, 0.03, 5, (0.14, 0.26))):
        grass_tuft(b, gx, gy, n, h)
    # low filler leaves so the ground under the clump is not bare
    for k in range(6):
        a = k * 60 + R(b, -15, 15)
        rr = R(b, 0.08, 0.2)
        bleaf(b, R(b, 0.08, 0.12), 0.055, (rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a)), 0.003),
              (0, R(b, 50, 75), a + R(b, -40, 40)), DN0, mix(DN1, DK_Y, R(b, 0, 0.4)), bend=25, fold=16, segs=3)
    obj = b.build(sharp_angle=80)
    obj.data.transform(Matrix.Diagonal((0.86, 0.86, 0.92, 1.0)))     # pull the whole clump in to ~0.6 m across
    return obj


# ============================================================================================
# FIELD STONE
# ============================================================================================
def stone_col(seed, z0, z1, moss_amt=0.85):
    off = Vector((seed * 2.3, seed * 1.1, seed * 4.7))

    def f(co):
        t = max(0.0, min(1.0, (co.z - z0) / (z1 - z0)))
        k = 0.72 + 0.34 * t
        base = (k, k * 0.985, k * 0.96)
        n = noise.noise(co * 6.0 + off) + 0.4 * noise.noise(co * 15.0 - off)
        m = smooth(-0.12, 0.22, n) * smooth(0.45, 0.8, t) * moss_amt
        c = mix(base, (k * 0.5, k * 0.8, k * 0.3), m)
        ly = smooth(0.2, 0.36, noise.noise(co * 17.0 + off * 2)) * smooth(0.25, 0.6, t)
        return mix(c, (k * 1.1, k * 1.0, k * 0.55), ly * 0.85)

    return f


def build_field_stone():
    b = Builder('field_stone', seed=81)
    radii = (0.35, 0.275, 0.335)
    zc = 0.105
    b.blob(radii, loc=(0, 0, zc), mat='stone', subdiv=4, noise_amp=0.14, noise_scale=1.1, flatten_bottom=-0.6,
           color=stone_col(1, -0.1, 0.24), rot=(0, 0, 14), deform=chisel(b, radii, 15, lo=0.5, hi=0.84))
    r2 = (0.17, 0.125, 0.115)
    b.blob(r2, loc=(0.2, -0.2, 0.005), mat='stone', subdiv=3, noise_amp=0.16, noise_scale=1.3, flatten_bottom=-0.8,
           color=stone_col(2, -0.1, 0.08, 0.5), rot=(0, 0, 25), deform=chisel(b, r2, 9))
    r3 = (0.085, 0.07, 0.07)
    b.blob(r3, loc=(-0.3, 0.17, 0.005), mat='stone', subdiv=2, noise_amp=0.14, noise_scale=1.3, flatten_bottom=-0.8,
           color=stone_col(3, -0.06, 0.05, 0.3), rot=(0, 0, 20), deform=chisel(b, r3, 6))
    return b.build(sharp_angle=32)


# ============================================================================================
# FALLEN LOG
# ============================================================================================
def build_fallen_log():
    b = Builder('fallen_log', seed=91)
    SEG = 24
    X0, X1 = -1.1, 1.02
    off = Vector((3.3, 8.1, 1.7))

    def centre(x):
        return Vector((x, 0.03 * math.sin(x * 1.2 + 0.4), 0.192 + 0.01 * math.sin(x * 2.1 + 1.0)))

    def radius(x):
        return 0.214 - 0.012 * (x - X0) / (X1 - X0) + 0.008 * math.sin(x * 3.1)

    def pt(x, i, rr=1.0, dx=0.0, lump=1.0):
        a = 2 * pi * i / SEG
        ca, sa = math.cos(a), math.sin(a)
        k = 1 + lump * (0.055 * noise.noise(Vector((ca * 1.5, sa * 1.5, x * 1.2)) + off) + 0.028 * noise.noise(Vector((ca * 4.2, sa * 4.2, x * 3.3)) - off))
        k += lump * 0.03 * math.sin(a * 8 + 2.6 * noise.noise(Vector((x * 1.4, 0.3, 0.7)) + off) + 1.2 * math.sin(x * 2.2))   # bark ridges
        r = radius(x) * rr * k
        c = centre(x)
        return Vector((x + dx, c.y + r * sa, c.z + r * ca))

    def bark_col(co):
        up = smooth(0.02, 0.36, co.z)
        k = 0.74 + 0.3 * up + 0.07 * noise.noise(co * 5.0 + off)
        g = smooth(0.05, 0.4, noise.noise(co * 2.6 + off * 2)) * smooth(0.22, 0.36, co.z)   # green film near the moss
        return mix((k, k, k), (k * 0.7, k * 0.95, k * 0.5), g * 0.75)

    xs = [X0, X0 + 0.014] + [X0 + 0.13 + i * (X1 - 0.12 - X0 - 0.13) / 15 for i in range(16)]
    rings = [[pt(x, i, 0.972 if k == 0 else 1.0) for i in range(SEG)] for k, x in enumerate(xs)]
    jag = [R(b, -0.1, 0.11) for _ in range(SEG)]
    for i in range(0, SEG, 6):
        jag[i] = R(b, 0.12, 0.2)                          # a few long splinters of bark
    end = [pt(X1, i, 1.0, jag[i]) for i in range(SEG)]
    rings.append(end)
    loft(b, rings, 'bark', color=bark_col, cap0=False, cap1=False, along_u=False)

    # sawn end: growth rings (alternating tone), darker cambium at the rim
    c0 = centre(X0)
    disc(b, rings[0], c0 + Vector((0, 0.022, -0.012)), [0, 0.09, 0.2, 0.3, 0.41, 0.51, 0.62, 0.72, 0.82, 0.9, 0.955, 1.0], 'wood_light',
         [1.02, 0.8, 1.06, 0.82, 1.04, 0.78, 1.05, 0.8, 1.0, 0.74, 0.5], (-1, 0, 0), base=(1.0, 0.96, 0.9))

    # broken end: splintered heartwood
    def split_col(co):
        k = 0.62 + 0.5 * smooth(X1 - 0.12, X1 + 0.2, co.x)
        return (k, k * 0.95, k * 0.86)

    inner = [[pt(X1, i, 0.93, jag[i] - 0.004, 0.6) for i in range(SEG)]]
    inner.append([pt(X1, i, 0.7, jag[i] * 0.5 + (R(b, 0.04, 0.2) if i % 2 == 0 else R(b, -0.14, 0.0)), 0.3) for i in range(SEG)])
    inner.append([pt(X1, i, 0.42, (R(b, 0.1, 0.3) if i % 3 == 0 else R(b, -0.12, 0.04)), 0.0) for i in range(SEG)])
    inner.append([pt(X1, i, 0.14, R(b, -0.02, 0.1), 0.0) for i in range(SEG)])
    loft(b, [end] + inner[:1], 'bark', color=lambda co: mul(bark_col(co), 0.8), cap0=False, cap1=False, out_dir=(1, 0, 0))
    loft(b, inner, 'wood_light', color=split_col, cap0=False, cap1=True, out_dir=(1, 0, 0))

    # stub branch (front, upper side) with a snapped end
    xb, ang = 0.28, math.radians(-48)
    c = centre(xb)
    rad = Vector((0, math.sin(ang), math.cos(ang)))
    base = c + rad * (radius(xb) * 0.72)
    d = (rad + Vector((0.75, -0.1, 0.0))).normalized()
    p1, p2 = base + d * 0.15, base + d * 0.27 + Vector((0.01, 0, 0.012))
    b.tube([base, base + d * 0.07, p1, p2], [0.082, 0.058, 0.046, 0.041], mat='bark', segs=10, caps=False,
           color=(0.82, 0.82, 0.82), color_top=(1.02, 1.02, 1.02))
    b.lathe([(0.041, 0.0), (0.036, 0.004), (0.03, 0.022), (0.018, 0.008), (0.008, 0.03), (0, 0.012)], loc=tuple(p2), rot=aim(d),
            mat='wood_light', segs=10, color=(0.78, 0.74, 0.66), color_top=(1.05, 1.0, 0.9),
            radial=lambda a, z: 1.0 + (0.25 * math.sin(3 * a + 1) if z > 0.006 else 0.0))
    # an old knot scar
    kc = centre(-0.55)
    kd = Vector((0, math.sin(math.radians(-70)), math.cos(math.radians(-70))))
    b.lathe([(0.062, -0.01), (0.056, 0.012), (0.038, 0.02), (0.026, 0.012), (0, 0.008)], loc=tuple(kc + kd * (radius(-0.55) * 0.985)),
            rot=aim(kd), mat='bark', segs=10, color=(0.8, 0.8, 0.8), color_top=(0.62, 0.6, 0.58))

    # moss: cushions wrapped round the top of the log
    def wrap(x0, a0, sink, seed):
        lob = lobed(seed, 0.15)

        def f(cc):
            cc = lob(cc)
            x = x0 + cc.x
            cen = centre(x)
            a = a0 + cc.y / radius(x)
            r = radius(x) * 1.02 + cc.z - sink
            return Vector((x, cen.y + r * math.sin(a), cen.z + r * math.cos(a)))
        return f

    patches = [(-0.7, -10, 0.27, 0.17, 0.045, 3), (-0.3, 30, 0.17, 0.12, 0.038, 3), (-0.04, -34, 0.15, 0.1, 0.036, 3),
               (0.44, 12, 0.24, 0.15, 0.046, 3), (0.76, -30, 0.13, 0.09, 0.032, 2), (0.82, 36, 0.12, 0.09, 0.03, 2),
               (-0.98, 30, 0.09, 0.09, 0.03, 2), (0.12, 56, 0.11, 0.07, 0.026, 2), (-0.5, -60, 0.12, 0.065, 0.026, 2),
               (-0.86, -52, 0.08, 0.06, 0.024, 2), (0.3, -70, 0.09, 0.05, 0.022, 2)]
    for k, (x0, a0, sx, sy, th, sd) in enumerate(patches):
        b.blob((sx, sy, th), mat='plant', subdiv=sd, noise_amp=0.16, noise_scale=1.8, flatten_bottom=-0.4, color=moss_col(k + 3),
               deform=wrap(x0, math.radians(a0), 0.008, k + 1))
    return b.build(sharp_angle=42)


# ============================================================================================
# TREE STUMP
# ============================================================================================
def mushroom(b, base, h, r, lean=(0, 0), cap=srgb(172, 104, 56), cap_hi=srgb(222, 170, 104)):
    base = Vector(base)
    top = base + Vector((lean[0], lean[1], h))
    mid = base.lerp(top, 0.5) + Vector((lean[0] * -0.2, lean[1] * -0.2, 0))
    cream = srgb(226, 208, 176)
    b.tube([base, mid, top], [r * 0.3, r * 0.24, r * 0.22], mat='plant', segs=6, caps=False, color=mul(cream, 0.75), color_top=cream)
    d = (top - mid).normalized() + Vector((0, 0, 0.6))

    def col(co):
        if co.z < 0.07 * r:
            return mul(cream, 0.82)
        return mix(cap, cap_hi, smooth(0.1 * r, 0.6 * r, co.z))

    b.lathe([(0.2 * r, -0.02 * r), (0.9 * r, -0.05 * r), (1.0 * r, 0.05 * r), (0.86 * r, 0.3 * r), (0.5 * r, 0.52 * r), (0, 0.6 * r)],
            loc=tuple(top), rot=aim(d), mat='plant', segs=10, color=col, jitter=0.08)


def build_tree_stump():
    b = Builder('tree_stump', seed=101)
    SEG = 32
    off = Vector((5.1, 2.2, 9.4))
    NR = 6
    roots = [k * 2 * pi / NR + R(b, -0.22, 0.22) for k in range(NR)]
    rk = [R(b, 0.75, 1.15) for _ in range(NR)]
    TILT = 0.06

    def rad(a, z):
        base = 0.2 + 0.05 * math.exp(-max(z, 0) / 0.13) + 0.012 * (1 - smooth(0.3, 0.45, z))
        lobe = sum(rk[k] * math.exp(-((math.atan2(math.sin(a - roots[k]), math.cos(a - roots[k]))) / 0.3) ** 2) for k in range(NR))
        fl = math.exp(-max(z + 0.03, 0) / 0.11)
        ca, sa = math.cos(a), math.sin(a)
        nz = 0.05 * noise.noise(Vector((ca * 1.4, sa * 1.4, z * 2.5)) + off) + 0.03 * noise.noise(Vector((ca * 4, sa * 4, z * 7)) - off)
        furrow = 0.014 * math.sin(a * 11 + 3 * noise.noise(Vector((z * 3, 0, 0)) + off)) * smooth(0.02, 0.2, z)
        return base * (1 + 0.05 * math.sin(2 * a + 1.0) + 0.035 * math.sin(3 * a + 0.3)) * (1 + 0.5 * lobe * fl + nz) + furrow

    def pt(i, z, rr=1.0):
        a = 2 * pi * i / SEG
        r = rad(a, z) * rr
        x, y = r * math.cos(a), r * math.sin(a)
        return Vector((x, y, z + (TILT * x * smooth(0.3, 0.44, z))))

    def bark_col(co):
        k = 0.7 + 0.34 * smooth(-0.02, 0.42, co.z) + 0.07 * noise.noise(co * 6.0 + off)
        g = smooth(0.0, 0.35, noise.noise(co * 3.0 + off * 3)) * (1 - smooth(0.06, 0.3, co.z)) * smooth(-0.6, 0.2, co.y * -2.0)
        return mix((k, k, k), (k * 0.68, k * 0.94, k * 0.48), g * 0.8)

    zs = [-0.06, -0.01, 0.035, 0.085, 0.15, 0.22, 0.3, 0.37, 0.425, 0.447]
    rings = [[pt(i, z) for i in range(SEG)] for z in zs]
    rings.append([pt(i, 0.452, 0.972) for i in range(SEG)])
    loft(b, rings, 'bark', color=bark_col, cap0=False, cap1=False, along_u=False)
    top = rings[-1]
    cen = sum(top, Vector()) / SEG
    pith = cen + Vector((0.03, -0.025, 0.0))
    pith.z = 0.452 + TILT * pith.x
    inner = [pith.lerp(p, 0.93) for p in top]
    disc(b, top, pith, [0.93, 1.0], 'bark', [0.62], (0, 0, 1), rounder=False)
    disc(b, inner, pith, [0, 0.1, 0.22, 0.34, 0.46, 0.58, 0.7, 0.81, 0.91, 1.0], 'wood_light',
         [1.04, 0.8, 1.06, 0.82, 1.03, 0.78, 1.04, 0.8, 0.6], (0, 0, 1), base=(0.98, 0.93, 0.86))
    # weather crack across the rings + felling hinge splinters along the back edge
    for (a, r0, r1, w) in ((2.3, 0.02, 0.17, 0.007), (5.2, 0.05, 0.14, 0.005)):
        d = Vector((math.cos(a), math.sin(a), 0))
        s = Vector((-d.y, d.x, 0))
        v = [pith + d * r0, pith + d * (r0 + r1) / 2 + s * w, pith + d * r1, pith + d * (r0 + r1) / 2 - s * w]
        v = [(p.x, p.y, 0.4535 + TILT * p.x) for p in v]
        raw(b, v, [(0, 3, 2, 1)], (0.2, 0.17, 0.14), mat='wood_light')
    for k in range(11):
        x = -0.115 + k * 0.023 + R(b, -0.005, 0.005)
        y = 0.13 + 0.022 * math.cos(x * 9) + R(b, -0.006, 0.006)
        h = R(b, 0.008, 0.03) * (1.6 if k in (3, 7) else 1.0)
        b.box((R(b, 0.02, 0.034), R(b, 0.012, 0.022), h), loc=(x, y, 0.45 + TILT * x + h / 2), rot=(R(b, -10, 10), R(b, -8, 8), R(b, -25, 25)),
              mat='wood_light', bevel=0, taper=(R(b, 0.2, 0.8), R(b, 0.3, 0.7)), grain=2, color=(0.92, 0.86, 0.76), jitter=0.14)

    # roots running out and diving into the soil
    for k in range(NR):
        a = roots[k]
        c, s = math.cos(a), math.sin(a)
        L = 0.4 * rk[k] / 1.0
        L = max(0.36, min(0.44, L))
        side = R(b, -0.05, 0.05)
        px, py = -s * side, c * side
        b.tube([(c * 0.2, s * 0.2, 0.15), (c * 0.275 + px * 0.4, s * 0.275 + py * 0.4, 0.07), (c * 0.35 + px, s * 0.35 + py, 0.018),
                (c * L + px * 1.6, s * L + py * 1.6, -0.05)], [0.07, 0.056, 0.04, 0.02], mat='bark', segs=7, caps=False,
               color=(0.84, 0.84, 0.84), color_top=(0.72, 0.72, 0.72))
        if k % 2 == 0:   # a forked rootlet
            a2 = a + R(b, 0.45, 0.7) * (1 if k % 4 == 0 else -1)
            b.tube([(c * 0.29, s * 0.29, 0.045), (c * 0.3 + math.cos(a2) * 0.07, s * 0.3 + math.sin(a2) * 0.07, 0.012),
                    (c * 0.3 + math.cos(a2) * 0.13, s * 0.3 + math.sin(a2) * 0.13, -0.03)], [0.03, 0.022, 0.012], mat='bark', segs=5,
                   caps=False, color=(0.76, 0.76, 0.76))

    # moss: on the cut rim, in the root crotches, creeping up the shady side
    def surf(a, z, push=0.0):
        r = rad(a, z) + push
        return Vector((r * math.cos(a), r * math.sin(a), z))

    def nrm(a, up=0.3):
        return Vector((math.cos(a), math.sin(a), up))

    moss(b, (0.11, 0.075, 0.03), tuple(Vector((-0.1, -0.12, 0.452 - TILT * 0.1))), (0, 0, 1), seed=1, subdiv=3)
    moss(b, (0.06, 0.045, 0.022), (0.13, 0.06, 0.462), (0, 0, 1), seed=2)
    for k, (a, z, sx, sy, th) in enumerate(((4.3, 0.33, 0.1, 0.085, 0.034), (3.4, 0.14, 0.12, 0.1, 0.038), (5.3, 0.1, 0.1, 0.08, 0.03),
                                            (1.2, 0.07, 0.11, 0.07, 0.03), (0.2, 0.2, 0.07, 0.07, 0.024), (2.4, 0.3, 0.07, 0.06, 0.022))):
        moss(b, (sx, sy, th), tuple(surf(a, z, -0.006)), nrm(a, 0.25 + 0.5 * math.exp(-z / 0.1)), seed=k + 5, subdiv=3 if k < 2 else 2)

    # mushroom cluster at the foot (front) + two little ones on the bark
    ma = -1.75
    for (da, dr, h, r, lx, ly) in ((0.0, 0.03, 0.105, 0.05, 0.01, -0.02), (0.22, 0.05, 0.075, 0.038, 0.02, -0.012),
                                   (-0.2, 0.06, 0.06, 0.03, -0.015, -0.014), (0.1, 0.1, 0.045, 0.024, 0.0, -0.01),
                                   (-0.1, 0.11, 0.03, 0.018, -0.006, -0.006)):
        a = ma + da
        p = surf(a, 0.0, dr)
        mushroom(b, (p.x, p.y, -0.01), h, r, (lx, ly))
    for (a, z, r) in ((-0.9, 0.2, 0.026), (-0.78, 0.26, 0.019)):
        p = surf(a, z, -0.01)
        mushroom(b, tuple(p), 0.03, r, (math.cos(a) * 0.03, math.sin(a) * 0.03), cap=srgb(196, 150, 96), cap_hi=srgb(236, 208, 160))
    return b.build(sharp_angle=46)


# ============================================================================================
# BRANCH PILE
# ============================================================================================
def branch(b, p0, p1, r0, r1, wig=0.03, sag=0.0, forks=(), mat='bark', tone=1.0, n=6):
    """Dead branch from thick end p0 to thin end p1 with wiggle, optional side twigs, snapped butt."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    dn = d.normalized()
    side = Vector((-dn.y, dn.x, 0)).normalized()
    up = dn.cross(side)
    pts, rad = [], []
    for i in range(n):
        t = i / (n - 1)
        w = 0 if i in (0, n - 1) else 1
        p = p0 + d * t + side * (R(b, -wig, wig) * w) + up * (R(b, -wig, wig) * 0.4 * w) - Vector((0, 0, sag * math.sin(pi * t)))
        pts.append(p)
        rad.append((r0 + (r1 - r0) * t ** 0.8) * R(b, 0.92, 1.1))
    rad[-1] = max(0.0025, r1 * 0.55)
    c = (tone * R(b, 0.86, 1.04),) * 3
    b.tube(pts, rad, mat=mat, segs=8 if r0 > 0.019 else (6 if r0 > 0.012 else 5), caps=False, color=mul(c, 0.86), color_top=mul(c, 1.08))
    # snapped butt end
    e = aim(pts[0] - pts[1])
    b.lathe([(rad[0], 0.0), (rad[0] * 0.8, 0.003), (rad[0] * 0.55, 0.012 + r0 * 0.3), (0, 0.004)], loc=tuple(pts[0]), rot=e,
            mat='wood_light', segs=8 if r0 > 0.019 else 6, color=(0.74, 0.7, 0.62), color_top=(1.0, 0.95, 0.86),
            radial=lambda a, z: 1.0 + (0.3 * math.sin(2 * a + r0 * 90) if z > 0.004 else 0.0))
    for (t, sgn, ln, lift) in forks:
        i = min(n - 2, int(t * (n - 1)))
        f = t * (n - 1) - i
        base = pts[i].lerp(pts[i + 1], f)
        rb = (rad[i] * (1 - f) + rad[i + 1] * f) * 0.62
        fd = (dn * 0.75 + side * sgn * 0.62 + Vector((0, 0, lift))).normalized()
        q1 = base + fd * ln * 0.5 + side * sgn * R(b, -0.015, 0.02)
        q2 = base + fd * ln + Vector((0, 0, R(b, -0.02, 0.03)))
        b.tube([base, q1, q2], [rb, rb * 0.7, 0.0022], mat=mat, segs=5, caps=False, color=mul(c, 0.9), color_top=mul(c, 1.1))
        if ln > 0.2:
            fd2 = (fd * 0.7 - side * sgn * 0.6 + Vector((0, 0, 0.15))).normalized()
            b.tube([q1, q1 + fd2 * ln * 0.25, q1 + fd2 * ln * 0.5], [rb * 0.55, rb * 0.4, 0.002], mat=mat, segs=4, caps=False,
                   color=mul(c, 1.0))


def build_branch_pile():
    b = Builder('branch_pile', seed=111)
    # (p0 thick end, p1 thin end, r0, r1, forks[(t, side, length, lift)], material, tone)
    BR = [
        ((-0.48, -0.1, 0.034), (0.44, -0.02, 0.03), 0.034, 0.02, [(0.55, 1, 0.24, 0.05), (0.78, -1, 0.16, 0.1)], 'bark', 0.95),
        ((0.46, 0.14, 0.03), (-0.42, 0.22, 0.03), 0.028, 0.014, [(0.5, -1, 0.22, 0.12), (0.72, 1, 0.16, 0.2)], 'bark', 1.0),
        ((-0.36, -0.36, 0.026), (0.3, 0.3, 0.1), 0.026, 0.011, [(0.45, 1, 0.2, 0.2), (0.7, -1, 0.18, 0.05)], 'wood_light', 0.72),
        ((0.3, -0.4, 0.024), (-0.2, 0.4, 0.12), 0.023, 0.01, [(0.6, 1, 0.2, 0.25)], 'bark', 1.05),
        ((-0.5, 0.05, 0.085), (0.36, 0.12, 0.115), 0.02, 0.009, [(0.4, -1, 0.2, 0.3), (0.66, 1, 0.2, 0.1)], 'bark', 0.9),
        ((0.48, -0.2, 0.02), (-0.3, -0.05, 0.13), 0.018, 0.007, [(0.5, -1, 0.22, 0.2), (0.8, 1, 0.12, 0.3)], 'bark', 1.0),
        ((0.05, 0.46, 0.018), (0.14, -0.36, 0.17), 0.016, 0.006, [(0.5, 1, 0.2, 0.3), (0.7, -1, 0.16, 0.1)], 'wood_light', 0.76),
        ((-0.3, 0.4, 0.016), (0.1, -0.3, 0.2), 0.014, 0.005, [(0.45, -1, 0.18, 0.35), (0.7, 1, 0.14, 0.2)], 'bark', 1.08),
        ((0.4, 0.34, 0.014), (-0.32, -0.14, 0.22), 0.012, 0.004, [(0.55, 1, 0.2, 0.3)], 'bark', 0.95),
        ((-0.44, -0.26, 0.13), (0.3, -0.1, 0.24), 0.01, 0.004, [(0.4, -1, 0.16, 0.2), (0.65, 1, 0.14, 0.4)], 'bark', 1.0),
        ((-0.1, 0.3, 0.17), (0.34, -0.12, 0.27), 0.009, 0.004, [(0.5, 1, 0.14, 0.3)], 'bark', 1.1),
    ]
    for p0, p1, r0, r1, forks, mat, tone in BR:
        branch(b, p0, p1, r0, r1, wig=0.028 if r0 > 0.02 else 0.04, sag=0.012, forks=forks, mat=mat, tone=tone)
    # short broken bits lying round the foot of the heap
    for (x, y, yaw, ln, r) in ((-0.3, -0.42, 20, 0.2, 0.011), (0.4, 0.3, 130, 0.24, 0.012), (0.1, 0.46, 80, 0.16, 0.009),
                               (-0.46, 0.34, -40, 0.18, 0.01), (0.34, -0.44, -15, 0.14, 0.008)):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        branch(b, (x - c * ln / 2, y - s * ln / 2, r), (x + c * ln / 2, y + s * ln / 2, r * 0.7), r, r * 0.6, wig=0.012, n=4,
               forks=[(0.5, 1, 0.07, 0.1)] if ln > 0.17 else ())
    # dry leaves caught in the pile
    d0, d1 = srgb(120, 78, 40), srgb(190, 140, 66)
    for k in range(12):
        a = R(b, 0, 2 * pi)
        rr = R(b, 0.05, 0.46)
        z = 0.004 + max(0.0, 0.2 * (1 - rr / 0.3)) * R(b, 0.0, 1.0)
        bleaf(b, R(b, 0.06, 0.09), 0.045, (rr * math.cos(a), rr * math.sin(a), z), (R(b, -20, 20), R(b, 60, 100), R(b, 0, 360)),
              mul(d0, R(b, 0.8, 1.2)), mul(d1, R(b, 0.8, 1.15)), bend=R(b, -30, 50), fold=R(b, 10, 40), segs=3, c_rib=d0)
    return b.build(sharp_angle=60)


# ============================================================================================
# PREVIEW (kit.render_preview + free camera / focus box)
# ============================================================================================
def render(path, objs, az=35, el=22, size=(1000, 750), zoom=1.0, focus=None, cam=None, ground=True):
    """focus=(centre, size) frames a box instead of the whole selection. cam=(loc, target, lens) is a free camera."""
    sc = bpy.context.scene
    pts = []
    for o in objs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    floor_z = lo.z
    if focus:
        c = Vector(focus[0])
        rad = focus[1] * 0.87
    else:
        c = (lo + hi) / 2
        rad = (hi - lo).length / 2
    camo = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(camo)
    a, e = math.radians(az), math.radians(el)
    if cam:
        camo.location = Vector(cam[0])
        camo.rotation_euler = (Vector(cam[1]) - camo.location).to_track_quat('-Z', 'Y').to_euler()
        camo.data.lens = cam[2]
        camo.data.clip_start = 0.02
        camo.data.clip_end = 50
    else:
        camo.data.lens = 60
        d = rad / math.tan(math.radians(13)) / zoom
        camo.location = c + Vector((math.sin(a) * math.cos(e) * d, -math.cos(a) * math.cos(e) * d, math.sin(e) * d))
        camo.rotation_euler = (c - camo.location).to_track_quat('-Z', 'Y').to_euler()
        camo.data.clip_start = min(0.1, d * 0.1)
        camo.data.clip_end = d * 4
    sc.camera = camo
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.86, 0.68)
    sun.data.angle = math.radians(4)
    sun.rotation_euler = Euler((math.radians(58), 0, a + math.radians(55)))
    fm = bpy.data.meshes.new('_pv_floor')
    fb = bmesh.new()
    bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=max(rad, 1.0) * 12)
    fb.to_mesh(fm)
    fb.free()
    floor = bpy.data.objects.new('_pv_floor', fm)
    floor.location = (c.x, c.y, (0.0 if ground else floor_z - 0.001) if not cam else floor_z - 0.6)
    sc.collection.objects.link(floor)
    fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
    try:
        fmat.use_nodes = True
        bs = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bs.inputs['Base Color'].default_value = (0.30, 0.38, 0.20, 1)
        bs.inputs['Roughness'].default_value = 0.9
    except Exception:
        pass
    if not fm.materials:
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
    if sc.render.engine == 'CYCLES':
        sc.cycles.samples = 24
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in (camo, sun, floor):
        bpy.data.objects.remove(o)
    print(f'[gather] preview {path}')


# ============================================================================================
# REGISTRY / MAIN
# ============================================================================================
ASSETS = {
    'tool_pick': build_pick, 'tool_axe': build_axe, 'weed_clump': build_weeds, 'field_stone': build_field_stone,
    'fallen_log': build_fallen_log, 'tree_stump': build_tree_stump, 'branch_pile': build_branch_pile,
}
BUDGET = {'tool_pick': 3000, 'tool_axe': 3000, 'weed_clump': 3000, 'field_stone': 2000, 'fallen_log': 5000,
          'tree_stump': 4000, 'branch_pile': 2500}
PORT = (750, 1000)
# preview groups: name -> (asset names, spacing, shots)
# shot = (tag, kwargs for render())
GROUPS = {
    'tools': (['tool_pick', 'tool_axe'], 0.5, [
        ('34', dict(az=62, el=12, size=PORT, zoom=1.25)),
        ('side', dict(az=90, el=4, size=PORT, zoom=1.25)),
        ('back', dict(az=-118, el=14, size=PORT, zoom=1.25)),
        ('heads', dict(az=58, el=22, focus=((0, 0, 0.32), 0.42), zoom=1.0)),
        ('heads_top', dict(az=110, el=52, focus=((0, 0, 0.33), 0.42), zoom=1.0)),
        ('grips', dict(az=70, el=10, focus=((0, 0, -0.02), 0.34), zoom=1.0)),
    ]),
    'weeds': (['weed_clump'], 0, [('30', dict(az=30, el=20, zoom=1.2)), ('-140', dict(az=-140, el=24, zoom=1.2)),
                                  ('top', dict(az=10, el=62, zoom=1.2)), ('eye', dict(az=-20, el=8, zoom=1.3))]),
    'stone': (['field_stone'], 0, [('30', dict(az=30, el=24, zoom=1.2)), ('-150', dict(az=-150, el=20, zoom=1.2)),
                                   ('eye', dict(az=80, el=42, zoom=1.2))]),
    'log': (['fallen_log'], 0, [('30', dict(az=30, el=20, zoom=1.3)), ('-150', dict(az=-150, el=22, zoom=1.3)),
                                ('sawn', dict(az=-62, el=14, focus=((-0.95, 0, 0.2), 0.75))),
                                ('broken', dict(az=62, el=16, focus=((0.95, 0, 0.2), 0.75))),
                                ('top', dict(az=5, el=58, zoom=1.3))]),
    'stump': (['tree_stump'], 0, [('30', dict(az=30, el=22, zoom=1.2)), ('-150', dict(az=-150, el=26, zoom=1.2)),
                                  ('top', dict(az=-10, el=58, zoom=1.2)), ('shrooms', dict(az=8, el=14, focus=((0, -0.28, 0.1), 0.42)))]),
    'branches': (['branch_pile'], 0, [('30', dict(az=30, el=24, zoom=1.25)), ('-140', dict(az=-140, el=18, zoom=1.25)),
                                      ('top', dict(az=0, el=65, zoom=1.25))]),
    'all': (['field_stone', 'weed_clump', 'branch_pile', 'tree_stump', 'fallen_log'], 1.45, [('30', dict(az=28, el=20, zoom=1.35))]),
}

names = list(ASSETS)
if ONLY:
    names = [n for n in names if any(n in GROUPS[g][0] for g in ONLY)]
objs = {}
for n in names:
    o = ASSETS[n]()
    objs[n] = o
    o.data.update()
    bb = [v.co for v in o.data.vertices]
    lo = [min(p[i] for p in bb) for i in range(3)]
    hi = [max(p[i] for p in bb) for i in range(3)]
    tris = kit.tri_count([o])
    flag = '' if tris <= BUDGET[n] else f'  !!! OVER BUDGET ({BUDGET[n]})'
    print(f'ASSET {n:12s} min=({lo[0]:.3f},{lo[1]:.3f},{lo[2]:.3f}) max=({hi[0]:.3f},{hi[1]:.3f},{hi[2]:.3f}) '
          f'size=({hi[0] - lo[0]:.3f},{hi[1] - lo[1]:.3f},{hi[2] - lo[2]:.3f}) tris={tris} mats={[m.name for m in o.data.materials]}{flag}')

if not ONLY:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kit.export_glb(OUT, list(objs.values()))

if PREV:
    os.makedirs(PREV, exist_ok=True)
    if os.environ.get('GATHER_CULL'):       # debug: show what a FrontSide material would draw
        for m in bpy.data.materials:
            m.use_backface_culling = True
    for g, (members, spacing, shots) in GROUPS.items():
        if (ONLY and g not in ONLY) or any(m not in objs for m in members):
            continue
        sel = [objs[m] for m in members]
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.hide_render = o not in sel
        xs = []
        x = 0.0
        for i, o in enumerate(sel):
            if spacing and i:
                x += spacing if g == 'tools' else (sel[i - 1].dimensions.x + o.dimensions.x) / 2 + 0.3
            xs.append(x)
        for o, xx in zip(sel, xs):
            o.location.x = xx - xs[-1] / 2
        bpy.context.view_layer.update()
        for tag, kw in shots:
            render(os.path.join(PREV, f'{g}_{tag}.png'), sel, ground=g != 'tools', **kw)
        for o in sel:
            o.location.x = 0
        bpy.context.view_layer.update()
        if g == 'tools':
            # first person: eye behind / above the grip, looking along the haft toward the head
            for o in sel:
                for oo in sel:
                    oo.hide_render = oo is not o
                render(os.path.join(PREV, f'{o.name}_fp.png'), [o], cam=((-0.13, 0.2, -0.36), (0.0, -0.03, 0.3), 30), size=(1000, 750))
                render(os.path.join(PREV, f'{o.name}_fp2.png'), [o], cam=((0.2, 0.1, -0.2), (0.0, -0.04, 0.3), 30), size=(1000, 750))
    for o in bpy.data.objects:
        o.hide_render = False
