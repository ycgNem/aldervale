"""Vegetation kit: trees, bushes, crops (3 x 4 stages), ground cover, bird, butterfly.

  blender --background --factory-startup --python tools/blender/build_vegetation.py -- <preview_dir> [group,group]

Exports public/models/vegetation.glb. Previews (optional 2nd arg filters which groups get rendered;
pass "none" to skip rendering).
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Quaternion
import kit
from kit import Builder, srgb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGS[0] if ARGS else os.path.join(HERE, '_preview')
ONLY = set(ARGS[1].split(',')) if len(ARGS) > 1 else None
os.makedirs(OUT, exist_ok=True)

kit.reset()
SHARP = 80  # plants are low-poly and round: keep almost everything smooth
pi = math.pi


# ---------------------------------------------------------------- helpers ----
def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def aim(d):
    """Euler degrees (XYZ) that rotate local +Z onto direction d."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(d).normalized())
    return tuple(math.degrees(a) for a in q.to_euler('XYZ'))


def raw(b, verts, faces, cols, mat='plant', loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), jitter=0.0, face_cols=None):
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
            l[uv].uv = (verts[i][0], verts[i][1])
    t.normal_update()
    b._emit(t, mat, loc, rot, scale)


def star(b, r, n, loc, rot, c_center, c_tip, z_center=0.0, z_tip=0.0, inner=0.42, mat='plant', jitter=0.0):
    """n-pointed star / petal rosette in the local XY plane (normal +Z)."""
    verts = [(0, 0, z_center)]
    cols = [c_center]
    for i in range(2 * n):
        a = pi * i / n
        rr = r if i % 2 == 0 else r * inner
        z = z_tip if i % 2 == 0 else (z_center + z_tip) * 0.5
        verts.append((rr * math.cos(a), rr * math.sin(a), z))
        cols.append(c_tip if i % 2 == 0 else mix(c_center, c_tip, 0.5))
    faces = [(0, 1 + i, 1 + (i + 1) % (2 * n)) for i in range(2 * n)]
    raw(b, verts, faces, cols, mat, loc, rot, jitter=jitter)


def rosette(b, r, n, loc, rot, c_in, c_out, cup=0.0, inner=0.6, mat='plant', jitter=0.0, wav=0.0):
    """Flower made of n broad rounded petals: centre -> mid ring -> scalloped rim. cup lifts the rim."""
    m = 2 * n
    verts = [(0, 0, 0)]
    cols = [c_in]
    for i in range(m):
        a = 2 * pi * i / m
        verts.append((r * 0.5 * math.cos(a), r * 0.5 * math.sin(a), cup * r * 0.45))
        cols.append(mix(c_in, c_out, 0.7))
    for i in range(m):
        a = 2 * pi * i / m
        rr = r if i % 2 == 0 else r * inner
        verts.append((rr * math.cos(a), rr * math.sin(a), cup * r + wav * r * math.sin(a * 3)))
        cols.append(c_out)
    faces = [(0, 1 + i, 1 + (i + 1) % m) for i in range(m)]
    faces += [(1 + i, 1 + m + i, 1 + m + (i + 1) % m, 1 + (i + 1) % m) for i in range(m)]
    raw(b, verts, faces, cols, mat, loc, rot, jitter=jitter)


def disc_leaf(b, r, loc, rot, c_in, c_mid, c_out, lobes=5, amp=0.14, n=10, cup=0.12, notch=0.5,
              wav=0.05, jitter=0.06, mat='plant'):
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


def ball(b, r, loc, mat, color, segs=6, squash=1.0):
    p = [(0, -r * squash), (0.8 * r, -0.5 * r * squash), (0.8 * r, 0.5 * r * squash), (0, r * squash)]
    b.lathe(p, loc=loc, mat=mat, segs=segs, color=color)


def ROUND(u):
    return max(0.3, math.sin(pi * min(1.0, 0.06 + u * 0.9)) ** 0.55)


def OVAL(u):
    return max(0.22, math.sin(pi * min(1.0, 0.04 + u * 0.94)) ** 0.7)


def LEAFLET(u):
    """Ovate leaflet in 8 tris (use with segs=3): pinched base and tip, two wide rows."""
    return 0.0 if (u < 0.01 or u > 0.99) else (1.0 if u < 0.5 else 0.8)


def fol(b, center, radii, count, size, colfn, zcut=-1.0, up_bias=0.25, tilt=50):
    """Leaf-tuft cards spread evenly (fibonacci) over an ellipsoid, tangent to it with random
    roll/tilt. Shading normals point away from the centre. colfn(z) -> colour. zcut skips the underside."""
    c = Vector(center)
    r = b.rng
    ga = pi * (3 - math.sqrt(5))
    off = r.uniform(0, 6.28)
    for i in range(count):
        z = 1 - (i + 0.5) / count * (1 - zcut)
        rad = math.sqrt(max(0.0, 1 - z * z))
        a = i * ga + off
        d = Vector((math.cos(a) * rad, math.sin(a) * rad, z))
        d = (d + Vector((r.uniform(-.2, .2), r.uniform(-.2, .2), r.uniform(-.2, .2)))).normalized()
        p = c + Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2])) * r.uniform(0.84, 1.05)
        n = (d + Vector((0, 0, up_bias))).normalized()
        q = Vector((0, -1, 0)).rotation_difference(d)
        q = Quaternion(d, r.uniform(0, 2 * pi)) @ q
        q = Quaternion(d.orthogonal().normalized(), math.radians(r.uniform(-tilt, tilt))) @ q
        q = Quaternion(d, r.uniform(0, 2 * pi)) @ q
        e = tuple(math.degrees(x) for x in q.to_euler('XYZ'))
        col = colfn(p.z)
        k = r.uniform(0.88, 1.1)
        s = size * r.uniform(0.8, 1.25)
        b.card(s, s, loc=p, rot=e, mat='leaf', normal=n, color=(col[0] * k, col[1] * k, col[2] * k))


# ------------------------------------------------------------------ trees ----
BARK_LO, BARK_HI = (0.82, 0.80, 0.78), (1.0, 1.0, 1.0)
CANOPY_CORE = srgb(38, 72, 30)


def trunk(b, pts, r0, flare=0.75, segs=10):
    b.tube(pts, lambda t: r0 * ((1 - 0.5 * t) + flare * math.exp(-9 * t)), mat='bark', segs=segs, caps=False,
           color=BARK_LO, color_top=BARK_HI)


def roots(b, r0, n=5, spread=2.7):
    for k in range(n):
        a = 2 * pi * k / n + b.rng.uniform(-0.3, 0.3)
        c, s = math.cos(a), math.sin(a)
        L = spread * b.rng.uniform(0.8, 1.15)
        b.tube([(c * 0.6 * r0, s * 0.6 * r0, 1.5 * r0), (c * 1.5 * r0, s * 1.5 * r0, 0.45 * r0), (c * L * r0, s * L * r0, -0.02)],
               [0.55 * r0, 0.4 * r0, 0.16 * r0], mat='bark', segs=6, color=BARK_LO)


def limb(b, a, c, r0, r1, sag=0.14, segs=6):
    a, c = Vector(a), Vector(c)
    d = c - a
    out = Vector((d.x, d.y, 0))
    mid = a.lerp(c, 0.55) + (out.normalized() * 0.12 * d.length if out.length > 1e-6 else Vector()) - Vector((0, 0, sag * d.length))
    b.tube([a, mid, c], [r0, (r0 + r1) * 0.55, r1], mat='bark', segs=segs, color=(0.9, 0.9, 0.88), color_top=BARK_HI)


def canopy(b, clusters, lo, hi, zmin, zmax, size, core=0.66, subdiv=3):
    """clusters: [(centre, radii, card_count)]. Colour gradient runs over the whole tree height."""
    def colfn(z):
        return mix(lo, hi, smooth(0.0, 1.0, (z - zmin) / (zmax - zmin)))
    for c, rad, n in clusters:
        b.blob((rad[0] * core, rad[1] * core, rad[2] * core), loc=c, mat='plant', subdiv=subdiv, noise_amp=0.18,
               color=CANOPY_CORE, color_top=mix(CANOPY_CORE, lo, 0.7))
    for c, rad, n in clusters:
        fol(b, c, rad, n, size, colfn)


APPLE_RED, APPLE_DEEP, APPLE_YG = srgb(196, 48, 40), srgb(150, 28, 30), srgb(190, 196, 78)


def apple(b, loc, s=1.0, yaw=0.0):
    r = 0.047 * s

    def col(co):
        side = smooth(0.15 * r, 0.95 * r, co.x)
        c = mix(APPLE_RED, APPLE_YG, side * 0.85)
        return mix(c, APPLE_DEEP, smooth(0.6, 0.0, (co.z + 0.085 * s) / (0.085 * s)) * 0.35 * (1 - side))

    prof = [(0, 0.012), (0.022, 0.0), (0.040, 0.014), (0.047, 0.042), (0.042, 0.068), (0.026, 0.084), (0.009, 0.082), (0, 0.074)]
    with b.at(loc, (0, 0, yaw)):
        b.lathe([(p[0] * s, p[1] * s - 0.085 * s) for p in prof], mat='plant_glossy', segs=10, color=col)
        b.tube([(0, 0, -0.012 * s), (0.004, 0.002, 0.012 * s), (0.008, 0.0, 0.03 * s)], 0.0035 * s, mat='bark', segs=4, caps=False, color=(0.8, 0.8, 0.8))


def hang_apples(b, clusters, count, s=1.65, zband=(-0.7, 0.4), push=1.12):
    placed = []
    tries = 0
    while len(placed) < count and tries < 6000:
        tries += 1
        c, rad, _ = clusters[b.rng.randrange(len(clusters))]
        d = Vector((b.rng.uniform(-1, 1), b.rng.uniform(-1, 1), b.rng.uniform(zband[0], zband[1])))
        if d.length < 0.3:
            continue
        d.normalize()
        p = Vector(c) + Vector((d.x * rad[0], d.y * rad[1], d.z * rad[2])) * push
        inside = False
        for c2, r2, _ in clusters:
            if c2 is c:
                continue
            q = p - Vector(c2)
            if (q.x / r2[0]) ** 2 + (q.y / r2[1]) ** 2 + (q.z / r2[2]) ** 2 < 1.25:
                inside = True
                break
        if inside or any((p - q).length < 0.34 for q in placed):
            continue
        placed.append(p)
        apple(b, p, s, b.rng.uniform(0, 360))


def tree_apple_a():
    b = Builder('tree_apple_a', seed=11)
    r0 = 0.16
    trunk(b, [(0, 0, -0.05), (0.02, 0.0, 0.22), (0.10, -0.03, 0.75), (0.16, 0.02, 1.25), (0.10, 0.06, 1.7), (0.02, 0.08, 2.1)], r0)
    roots(b, r0, 5)
    cl = [((1.15, 0.1, 2.45), (0.9, 0.85, 0.68), 66), ((-0.95, 0.4, 2.7), (0.85, 0.8, 0.66), 62),
          ((0.1, -1.0, 2.55), (0.8, 0.8, 0.62), 58), ((-0.15, 1.0, 2.8), (0.82, 0.82, 0.66), 58),
          ((0.6, 0.6, 3.25), (0.75, 0.75, 0.6), 52), ((-0.35, -0.3, 3.4), (0.95, 0.95, 0.72), 74),
          ((-1.5, -0.35, 2.2), (0.58, 0.56, 0.46), 40)]
    limb(b, (0.14, 0.0, 1.3), (1.0, 0.1, 2.25), 0.09, 0.04)
    limb(b, (0.12, 0.04, 1.5), (-0.85, 0.35, 2.5), 0.08, 0.04)
    limb(b, (0.14, -0.02, 1.15), (0.1, -0.9, 2.35), 0.075, 0.035)
    limb(b, (0.06, 0.07, 1.85), (-0.12, 0.9, 2.6), 0.07, 0.035)
    limb(b, (0.02, 0.08, 2.05), (-0.25, -0.2, 3.1), 0.075, 0.04, sag=0.02)
    limb(b, (0.13, 0.03, 1.4), (-1.35, -0.3, 2.05), 0.06, 0.03)
    canopy(b, cl, srgb(48, 96, 36), srgb(126, 172, 62), 1.85, 4.1, 0.6)
    hang_apples(b, cl, 22)
    return b.build(sharp_angle=SHARP)


def tree_apple_b():
    b = Builder('tree_apple_b', seed=23)
    r0 = 0.15
    trunk(b, [(0, 0, -0.05), (-0.02, 0.01, 0.2), (-0.12, 0.04, 0.6), (-0.2, 0.02, 0.95), (-0.22, -0.02, 1.25)], r0)
    roots(b, r0, 4)
    # low fork into two leaning main limbs -> wide, flat-topped orchard silhouette
    limb(b, (-0.2, 0.0, 1.0), (0.75, -0.15, 1.75), 0.10, 0.06, sag=0.06, segs=8)
    limb(b, (-0.21, 0.0, 1.1), (-1.0, 0.25, 1.8), 0.095, 0.055, sag=0.05, segs=8)
    limb(b, (0.75, -0.15, 1.75), (1.35, 0.1, 2.25), 0.06, 0.03)
    limb(b, (-1.0, 0.25, 1.8), (-1.3, -0.35, 2.3), 0.055, 0.03)
    limb(b, (-0.22, -0.02, 1.2), (-0.1, 0.85, 2.15), 0.07, 0.035)
    limb(b, (0.4, -0.15, 1.5), (0.25, -0.7, 2.15), 0.055, 0.03)
    cl = [((1.3, 0.1, 2.3), (0.85, 0.8, 0.6), 68), ((-1.3, -0.25, 2.3), (0.85, 0.82, 0.6), 68),
          ((-0.1, 0.95, 2.3), (0.85, 0.8, 0.6), 64), ((0.25, -0.75, 2.35), (0.8, 0.78, 0.58), 60),
          ((-0.55, 0.15, 2.75), (0.9, 0.88, 0.6), 68), ((0.5, 0.2, 2.8), (0.82, 0.8, 0.56), 60)]
    canopy(b, cl, srgb(48, 96, 36), srgb(126, 172, 62), 1.7, 3.4, 0.58)
    hang_apples(b, cl, 20)
    return b.build(sharp_angle=SHARP)


def tree_oak():
    b = Builder('tree_oak', seed=31)
    r0 = 0.36
    trunk(b, [(0, 0, -0.08), (0.0, 0.0, 0.3), (0.06, 0.03, 1.0), (0.02, 0.08, 1.9), (-0.05, 0.04, 2.7), (-0.02, 0.0, 3.4)], r0, flare=0.6, segs=12)
    roots(b, r0, 6, spread=2.4)
    cl = [((2.0, 0.2, 4.0), (1.7, 1.6, 1.3), 70), ((-2.0, 0.5, 4.1), (1.7, 1.6, 1.3), 70),
          ((0.3, -2.0, 3.9), (1.6, 1.6, 1.25), 66), ((-0.2, 2.1, 4.2), (1.6, 1.65, 1.3), 66),
          ((1.4, 1.5, 4.9), (1.5, 1.5, 1.2), 60), ((-1.4, -1.3, 4.9), (1.55, 1.5, 1.2), 60),
          ((1.3, -1.3, 4.7), (1.4, 1.4, 1.1), 54), ((-1.3, 1.5, 4.8), (1.4, 1.4, 1.1), 54),
          ((0.0, 0.1, 5.6), (1.9, 1.9, 1.35), 84)]
    for k, (c, rad, n) in enumerate(cl[:8]):
        z0 = 1.9 + 0.18 * k
        limb(b, (0.0, 0.04, z0), (c[0] * 0.85, c[1] * 0.85, c[2] - 0.5), 0.17 - 0.008 * k, 0.07, sag=0.08, segs=7)
    limb(b, (-0.02, 0.0, 3.3), (0, 0.1, 5.0), 0.16, 0.08, sag=0.0, segs=7)
    canopy(b, cl, srgb(40, 84, 34), srgb(112, 158, 58), 2.6, 7.0, 0.98, core=0.62)
    return b.build(sharp_angle=SHARP)


def tree_far():
    b = Builder('tree_far', seed=41)
    b.tube([(0, 0, -0.1), (0.05, 0, 1.2), (0.0, 0.05, 2.6)], [0.3, 0.2, 0.13], mat='bark', segs=5, caps=False, color=BARK_LO)
    b.blob((1.6, 1.55, 1.45), loc=(0, 0, 3.7), mat='plant', subdiv=3, noise_amp=0.22, color=srgb(40, 82, 32), color_top=srgb(84, 132, 48))
    b.blob((1.1, 1.05, 1.0), loc=(0.35, 0.2, 5.0), mat='plant', subdiv=2, noise_amp=0.15, color=srgb(54, 100, 38), color_top=srgb(100, 148, 54))

    def cf(z):
        return mix(srgb(44, 90, 34), srgb(124, 170, 62), smooth(2.4, 6.3, z))
    fol(b, (0, 0, 3.75), (1.95, 1.9, 1.7), 56, 1.45, cf, zcut=-0.8)
    fol(b, (0.35, 0.2, 5.05), (1.4, 1.35, 1.2), 30, 1.25, cf, zcut=-0.2)
    return b.build(sharp_angle=SHARP)


def bush(name, seed, berries=False):
    b = Builder(name, seed=seed)
    if not berries:
        lobes = [((0, 0, 0.42), (0.52, 0.48, 0.46), 130)]
        hi = srgb(128, 172, 64)
    else:
        lobes = [((-0.2, 0.0, 0.42), (0.46, 0.43, 0.44), 90), ((0.3, 0.05, 0.32), (0.37, 0.37, 0.34), 66)]
        hi = srgb(104, 158, 70)

    def cf(z):
        return mix(srgb(40, 86, 36), hi, smooth(0.05, 0.85, z))
    for c, rad, n in lobes:
        b.blob((rad[0] * 0.74, rad[1] * 0.74, rad[2] * 0.76), loc=c, mat='plant', subdiv=3, noise_amp=0.15,
               flatten_bottom=-0.9, color=srgb(34, 66, 30), color_top=srgb(52, 96, 38))
        fol(b, c, rad, n, 0.33, cf, zcut=-0.55)
    if berries:
        placed = 0
        while placed < 22:
            c, rad, _ = lobes[b.rng.randrange(2)]
            d = Vector((b.rng.uniform(-1, 1), b.rng.uniform(-1, 1), b.rng.uniform(-0.2, 1)))
            if d.length < 0.3:
                continue
            d.normalize()
            p = Vector(c) + Vector((d.x * rad[0], d.y * rad[1], d.z * rad[2])) * 1.06
            ball(b, 0.034, p, 'plant_glossy', mix(srgb(196, 36, 44), srgb(232, 80, 60), b.rng.random()))
            placed += 1
    return b.build(sharp_angle=SHARP)


# ------------------------------------------------------------------ wheat ----
def wheat_ear(b, loc, d, L, r, c0, c1, awn_c, awn_len, lumpy=True):
    with b.at(loc, aim(d)):
        if lumpy:
            prof = [(0, 0), (0.85 * r, 0.07 * L), (r, 0.22 * L), (0.72 * r, 0.36 * L), (0.98 * r, 0.5 * L), (0.66 * r, 0.66 * L),
                    (0.8 * r, 0.8 * L), (0, L)]
        else:
            prof = [(0, 0), (0.8 * r, 0.08 * L), (r, 0.25 * L), (0.8 * r, 0.42 * L), (0.96 * r, 0.58 * L), (0.6 * r, 0.8 * L), (0, L)]
        b.lathe(prof, scale=(1, 0.74, 1), mat='plant', segs=5, color=c0, color_top=c1, jitter=0.06)
        verts, faces, cols = [], [], []
        hw = 0.006
        for k in range(6):
            zk = L * (0.2 + 0.13 * k)
            s = 1 if k % 2 == 0 else -1
            bx = s * r * 0.7
            i0 = len(verts)
            verts += [(bx, 0, zk - hw), (bx, 0, zk + hw),
                      (s * (r * 0.7 + awn_len * 0.42), b.rng.uniform(-0.012, 0.012), zk + awn_len * 0.95)]
            cols += [c1, c1, awn_c]
            faces.append((i0, i0 + 1, i0 + 2))
        i0 = len(verts)
        verts += [(-hw * 0.7, 0, L * 0.93), (hw * 0.7, 0, L * 0.93), (0, 0, L + awn_len * 0.8)]
        cols += [c1, c1, awn_c]
        faces.append((i0, i0 + 1, i0 + 2))
        raw(b, verts, faces, cols, 'plant')


def wheat(stage):
    b = Builder(f'wheat_{stage}', seed=100 + stage)
    r = b.rng
    if stage <= 1:
        for gx in range(3):
            for gy in range(3):
                x = (gx - 1) * 0.27 + r.uniform(-0.04, 0.04)
                y = (gy - 1) * 0.27 + r.uniform(-0.04, 0.04)
                if stage == 0:
                    for k in range(5):
                        b.leaf(r.uniform(0.10, 0.15), 0.036, loc=(x + r.uniform(-.015, .015), y + r.uniform(-.015, .015), 0),
                               rot=(0, r.uniform(4, 28), k * 72 + r.uniform(-25, 25)), bend=r.uniform(20, 60), fold=28, segs=2,
                               color=srgb(92, 164, 56), color_top=srgb(176, 220, 98), jitter=0.08)
                else:
                    n = 8
                    for k in range(n):
                        b.leaf(r.uniform(0.24, 0.34), 0.05, loc=(x + r.uniform(-.03, .03), y + r.uniform(-.03, .03), 0),
                               rot=(0, r.uniform(3, 24), k * 360 / n + r.uniform(-25, 25)), bend=r.uniform(35, 80), fold=28, segs=3,
                               color=srgb(62, 132, 44), color_top=srgb(146, 200, 76), jitter=0.08)
        return b.build(sharp_angle=SHARP)

    ripe = stage == 3
    stem0, stem1 = (srgb(186, 150, 66), srgb(222, 176, 78)) if ripe else (srgb(62, 128, 46), srgb(120, 172, 68))
    ear0, ear1 = (srgb(214, 160, 60), srgb(242, 202, 106)) if ripe else (srgb(118, 170, 70), srgb(164, 200, 94))
    awn = srgb(250, 226, 150) if ripe else srgb(184, 214, 116)
    bl0, bl1 = (srgb(150, 150, 58), srgb(230, 192, 92)) if ripe else (srgb(58, 128, 44), srgb(140, 196, 74))
    spots = [((i - 1.5) * 0.24 + r.uniform(-0.05, 0.05), (j - 1.5) * 0.24 + r.uniform(-0.05, 0.05)) for i in range(4) for j in range(4)]
    r.shuffle(spots)
    spots = spots[:14] if ripe else spots
    for (x, y) in spots:
        h = r.uniform(0.72, 0.86) if ripe else r.uniform(0.56, 0.66)
        lean = r.uniform(0.10, 0.22) if ripe else r.uniform(0.02, 0.08)
        yaw = r.uniform(0, 2 * pi)
        reach = lean * h + (0.24 if ripe else 0.05)
        if abs(x + math.cos(yaw) * reach) > 0.55 or abs(y + math.sin(yaw) * reach) > 0.55:
            yaw = math.atan2(-y, -x) + r.uniform(-0.9, 0.9)
        dx, dy = math.cos(yaw), math.sin(yaw)
        p0 = Vector((x, y, 0))
        tip = Vector((x + dx * lean * h, y + dy * lean * h, h))
        ctrl = Vector((x + dx * lean * h * 0.15, y + dy * lean * h * 0.15, h * (1.08 if ripe else 0.6)))
        n = 5 if ripe else 4
        pts = []
        for k in range(n):
            t = k / (n - 1)
            pts.append(p0 * (1 - t) ** 2 + ctrl * (2 * t * (1 - t)) + tip * t ** 2)
        b.tube(pts, lambda t: 0.014 * (1 - 0.4 * t), mat='plant', segs=3, caps=False, color=stem0, color_top=stem1, jitter=0.06)
        tang = (tip - ctrl).normalized()
        if ripe:
            d_ear = (tang + Vector((dx * 0.25, dy * 0.25, -0.35))).normalized()  # ears nod over
            wheat_ear(b, tip, d_ear, 0.2, 0.042, ear0, ear1, awn, 0.11)
        else:
            wheat_ear(b, tip, tang, 0.115, 0.022, ear0, ear1, awn, 0.065, lumpy=False)
            f = r.uniform(0.25, 0.8)
            b.leaf(r.uniform(0.26, 0.36), 0.046, loc=p0.lerp(ctrl, f), rot=(0, r.uniform(10, 30), math.degrees(math.atan2(-y, -x)) + r.uniform(-100, 100)),
                   bend=r.uniform(60, 105), fold=26, segs=3, color=bl0, color_top=bl1, jitter=0.08)
    # body: upright wide blades that fill the patch below the ears
    for k in range(60 if ripe else 34):
        x, y = r.uniform(-0.46, 0.46), r.uniform(-0.46, 0.46)
        L = r.uniform(0.4, 0.74) if ripe else r.uniform(0.32, 0.54)
        byaw = r.uniform(0, 360) if max(abs(x), abs(y)) < 0.26 else math.degrees(math.atan2(-y, -x)) + r.uniform(-75, 75)
        b.leaf(L, 0.06, loc=(x, y, 0), rot=(0, r.uniform(2, 13), byaw), bend=r.uniform(12, 48), fold=28, segs=2,
               color=bl0, color_top=bl1, jitter=0.1)
    return b.build(sharp_angle=SHARP)


# ----------------------------------------------------------------- tomato ----
TL0, TL1 = srgb(44, 102, 42), srgb(100, 154, 62)
T_STEM0, T_STEM1 = srgb(70, 120, 48), srgb(112, 160, 66)
T_RED, T_ORANGE, T_GREEN = srgb(214, 52, 36), srgb(236, 128, 44), srgb(128, 174, 72)


def compound_leaf(b, loc, pitch, yaw, size, pairs=2, c0=TL0, c1=TL1):
    """Tomato-style pinnate leaf: terminal leaflet + side pairs of ovate leaflets, 8 tris each."""
    r = b.rng
    with b.at(loc, (r.uniform(-14, 14), pitch, yaw)):
        b.leaf(size * 0.56, size * 0.4, loc=(0, 0, size * 0.44), rot=(0, 8, 0), bend=40, fold=16, segs=3, shape=LEAFLET,
               color=c0, color_top=c1, jitter=0.1)
        for k in range(pairs):
            z = size * (0.1 + 0.24 * k)
            s = size * (0.5 - 0.05 * k)
            for sg in (-1, 1):
                b.leaf(s, s * 0.66, loc=(0, 0, z), rot=(sg * r.uniform(54, 70), 0, 0), bend=36, fold=16, segs=3, shape=LEAFLET,
                       color=c0, color_top=c1, jitter=0.1)


def tomato_fruit(b, loc, r, col, yaw=0.0):
    hi = mix(col, srgb(250, 170, 90), 0.5)

    def cf(co):
        return mix(col, hi, smooth(0.25 * r, 0.8 * r, co.z) * 0.35)

    prof = [(0, -0.80 * r), (0.68 * r, -0.64 * r), (r, -0.05 * r), (0.86 * r, 0.52 * r), (0.36 * r, 0.80 * r), (0, 0.72 * r)]
    with b.at(loc, (b.rng.uniform(-14, 14), b.rng.uniform(-14, 14), yaw)):
        b.lathe(prof, mat='plant_glossy', segs=7, color=cf)
        star(b, r * 0.72, 5, (0, 0, 0.75 * r), (0, 0, b.rng.uniform(0, 72)), srgb(86, 140, 56), srgb(52, 108, 42),
             z_center=0.03 * r, z_tip=-0.16 * r, inner=0.3)


def truss(b, base, yaw, reach, fruits, drop=0.07):
    """Fruit stalk leaving the stem at `base`, arching out and down, with `fruits` [(r, colour)]."""
    dx, dy = math.cos(yaw), math.sin(yaw)
    base = Vector(base)
    end = base + Vector((dx * reach, dy * reach, -drop))
    mid = base.lerp(end, 0.5) + Vector((0, 0, 0.05))
    b.tube([base, mid, end], 0.007, mat='plant', segs=3, caps=False, color=T_STEM0, color_top=T_STEM1)
    n = len(fruits)
    for k, (fr, col) in enumerate(fruits):
        a = yaw + (k - (n - 1) / 2) * 1.3
        off = Vector((math.cos(a), math.sin(a), 0)) * (fr * 0.8 if n > 1 else 0.0)
        top = end + off + Vector((0, 0, -0.012 - 0.04 * (k % 2)))
        b.tube([end, top], 0.0045, mat='plant', segs=3, caps=False, color=T_STEM1)
        tomato_fruit(b, top - Vector((0, 0, fr * 0.72)), fr, col, yaw=b.rng.uniform(0, 360))


def tomato(stage):
    b = Builder(f'tomato_{stage}', seed=200 + stage)
    r = b.rng
    if stage == 0:
        b.tube([(0, 0, 0), (0.005, 0.002, 0.05), (0, 0, 0.095)], 0.008, mat='plant', segs=4, caps=False,
               color=srgb(150, 180, 110), color_top=srgb(110, 170, 70))
        for k in range(2):
            b.leaf(0.11, 0.046, loc=(0, 0, 0.088), rot=(0, 70, k * 180 + 20), bend=22, fold=10, segs=2, shape=OVAL,
                   color=srgb(86, 160, 58), color_top=srgb(128, 192, 80))
        for k in range(2):
            b.leaf(0.075, 0.05, loc=(0, 0, 0.096), rot=(0, 36, k * 180 + 110), bend=30, fold=18, segs=3, shape=LEAFLET,
                   color=TL0, color_top=TL1)
        return b.build(sharp_angle=SHARP)

    H = (0.0, 0.32, 0.70, 0.94)[stage]
    N = (0, 8, 15, 22)[stage]
    size_lo, size_hi = ((0, 0), (0.2, 0.15), (0.31, 0.21), (0.37, 0.25))[stage]
    Rmax = (0, 0.05, 0.12, 0.17)[stage]
    stake_h = (0, 0.48, 1.1, 1.14)[stage]
    sx, sy = 0.045, 0.05
    b.box((0.038, 0.038, stake_h), loc=(sx, sy, stake_h / 2 - 0.02), rot=(1.5, -2.0, 18), mat='wood_light', bevel=0.006, segs=1,
          taper=(0.8, 0.8), jitter=0.08)
    wob = [(0, 0, 0), (0.018, 0.008, 0.26 * H), (-0.016, 0.016, 0.52 * H), (0.01, -0.008, 0.78 * H), (0.0, 0.0, H)]
    b.tube(wob, lambda t: (0.008 + 0.01 * H) * (1 - 0.55 * t), mat='plant', segs=5, caps=False, color=T_STEM0, color_top=T_STEM1)
    if stage >= 2:  # twine ties
        for z in (0.34 * H, 0.72 * H):
            b.lathe([(0.032, -0.007), (0.037, 0.0), (0.032, 0.007)], loc=(sx * 0.5, sy * 0.5, z), rot=(8, 4, 0), mat='plant', segs=6,
                    color=srgb(196, 168, 112))

    def stem_at(h):
        t = max(0.0, min(0.999, h / H)) * 4
        i = int(t)
        return Vector(wob[i]).lerp(Vector(wob[i + 1]), t - i)

    truss_yaws = {2: [0.5, 3.4], 3: [0.35, 2.5, 4.55]}.get(stage, [])
    truss_h = {2: [0.36, 0.5], 3: [0.44, 0.56, 0.38]}.get(stage, [])
    for i in range(N):
        f = i / max(N - 1, 1)
        h = H * (0.2 + 0.8 * f)
        yaw = i * 2.39996 + 0.7
        # keep the sight line to fruit trusses clear: pull in leaves that sit right above them
        blocked = any(abs(((yaw - ty + pi) % (2 * pi)) - pi) < 0.55 and -0.02 < h - th < 0.3 for ty, th in zip(truss_yaws, truss_h))
        dx, dy = math.cos(yaw), math.sin(yaw)
        size = (size_lo + (size_hi - size_lo) * f) * (0.8 if blocked else 1.0)
        rho = Rmax * math.sin(pi * (0.18 + 0.74 * f)) ** 0.7 * (0.3 if blocked else 1.0) * r.uniform(0.75, 1.1)
        e = Vector((dx * rho, dy * rho, h))
        a = stem_at(h - rho * 0.6)
        b.tube([a, e], 0.005 + 0.003 * H, mat='plant', segs=3, caps=False, color=T_STEM0, color_top=T_STEM1)
        pitch = 88 - 64 * f ** 1.6 + r.uniform(-8, 8)
        compound_leaf(b, e, pitch, math.degrees(yaw), size)
    if stage == 2:
        for ty, th, fr in zip(truss_yaws, truss_h, ([(0.032, T_GREEN), (0.027, T_GREEN)], [(0.031, T_GREEN), (0.025, T_GREEN)])):
            truss(b, stem_at(th), ty, 0.27, fr, drop=0.04)
        for k in range(6):
            yaw = k * 1.1 + 1.4
            h = H * (0.5 + 0.08 * k)
            d = Vector((math.cos(yaw), math.sin(yaw), 0.5))
            p = stem_at(h) + Vector((d.x, d.y, 0)) * (0.27 - 0.025 * k) + Vector((0, 0, 0.06))
            star(b, 0.034, 5, p, aim(d), srgb(250, 196, 40), srgb(250, 228, 84), z_center=-0.006, z_tip=0.004, inner=0.36)
    if stage == 3:
        sets = [[(0.064, T_RED), (0.057, T_RED), (0.05, T_ORANGE)], [(0.065, T_RED), (0.056, T_RED), (0.052, T_RED)],
                [(0.062, T_RED), (0.054, T_ORANGE)]]
        for ty, th, fr in zip(truss_yaws, truss_h, sets):
            truss(b, stem_at(th), ty, 0.36, fr, drop=0.06)
    return b.build(sharp_angle=SHARP)


# ---------------------------------------------------------------- pumpkin ----
PL_IN, PL_MID, PL_OUT = srgb(104, 158, 64), srgb(58, 118, 44), srgb(42, 96, 40)
P_VINE0, P_VINE1 = srgb(72, 124, 48), srgb(118, 164, 66)


def pumpkin_fruit(b, loc, w, h, ribs, c_rib, c_groove, c_top, segs, yaw=0.0, tilt=(0, 0)):
    R = w / 2
    prof = [(0, 0.06), (0.5, 0.0), (0.86, 0.15), (1.0, 0.45), (0.9, 0.76), (0.56, 0.96), (0.2, 1.0), (0, 0.93)]

    def rad(a, z):
        return 1 - 0.11 * (1 - abs(math.sin(ribs / 2 * a))) ** 1.6

    def cf(co):
        a = math.atan2(co.y, co.x)
        g = (1 - abs(math.sin(ribs / 2 * a))) ** 2.2
        c = mix(c_rib, c_groove, g * 0.9)
        return mix(c, c_top, smooth(0.45 * h, 1.0 * h, co.z) * 0.3 * (1 - g))

    b.lathe([(p[0] * R, p[1] * h) for p in prof], loc=loc, rot=(tilt[0], tilt[1], yaw), mat='plant_glossy', segs=segs, color=cf, radial=rad)


def pumpkin_leaf(b, hub, r, yaw, yellow=0.0, tilt=18):
    c_out = mix(PL_OUT, srgb(170, 160, 62), yellow)
    c_mid = mix(PL_MID, srgb(118, 140, 54), yellow * 0.7)
    disc_leaf(b, r, hub, (b.rng.uniform(-tilt, tilt), b.rng.uniform(-tilt, tilt) - 8, yaw), PL_IN, c_mid, c_out, lobes=5, amp=0.085,
              n=15, cup=0.16, notch=0.42, wav=0.06, jitter=0.08)


def petiole(b, base, hub, r=0.011):
    base, hub = Vector(base), Vector(hub)
    mid = base.lerp(hub, 0.5) + Vector((0, 0, 0.25 * (hub - base).length))
    b.tube([base, mid, hub], r, mat='plant', segs=3, caps=False, color=P_VINE0, color_top=P_VINE1)


def tendril(b, base, yaw, s=1.0):
    pts = []
    for k in range(9):
        t = k / 8
        a = t * 4.2 * pi
        rr = 0.03 * s * (1 - 0.5 * t)
        ax = Vector((math.cos(yaw), math.sin(yaw), 0.35))
        side = Vector((-math.sin(yaw), math.cos(yaw), 0))
        up = Vector((0, 0, 1))
        pts.append(Vector(base) + ax * (0.13 * s * t) + side * (rr * math.cos(a)) + up * (rr * math.sin(a) + 0.035 * s))
    b.tube(pts, lambda t: 0.005 * (1 - 0.5 * t), mat='plant', segs=3, caps=False, color=P_VINE1, color_top=srgb(160, 196, 90))


def vine(b, start, a0, length, wig, seed_phase, r0=0.014, n=7):
    pts = []
    for k in range(n):
        t = k / (n - 1)
        a = a0 + wig * math.sin(t * 3.2 + seed_phase)
        rr = length * t
        pts.append(Vector(start) + Vector((math.cos(a) * rr, math.sin(a) * rr, 0.016 + 0.012 * math.sin(t * 9 + seed_phase))))
    b.tube(pts, lambda t: r0 * (1 - 0.55 * t), mat='plant', segs=4, caps=False, color=P_VINE0, color_top=P_VINE1)
    return pts


def clampxy(p, lim=0.42):
    return Vector((max(-lim, min(lim, p.x)), max(-lim, min(lim, p.y)), p.z))


def pumpkin(stage):
    b = Builder(f'pumpkin_{stage}', seed=300 + stage)
    r = b.rng
    if stage == 0:
        b.tube([(0, 0, 0), (0.008, 0, 0.05), (0, 0, 0.095)], 0.011, mat='plant', segs=4, caps=False, color=srgb(170, 196, 120),
               color_top=srgb(116, 170, 70))
        for k in range(2):
            b.leaf(0.13, 0.085, loc=(0, 0, 0.09), rot=(0, 66, k * 180 + 35), bend=18, fold=12, segs=2, shape=ROUND,
                   color=srgb(78, 150, 56), color_top=srgb(124, 186, 76))
        disc_leaf(b, 0.04, (0.005, 0.005, 0.11), (0, -12, 120), PL_IN, PL_MID, PL_OUT, n=10, cup=0.2, amp=0.08)
        return b.build(sharp_angle=SHARP)
    if stage == 1:
        for k in range(5):
            yaw = k * 2 * pi / 5 + r.uniform(-0.25, 0.25)
            reach = r.uniform(0.12, 0.2)
            hh = r.uniform(0.17, 0.25) if k else 0.27
            hub = Vector((math.cos(yaw) * reach, math.sin(yaw) * reach, hh))
            petiole(b, (math.cos(yaw) * 0.012, math.sin(yaw) * 0.012, 0), hub, 0.011)
            pumpkin_leaf(b, hub, r.uniform(0.115, 0.14), math.degrees(yaw), tilt=14)
        tendril(b, (0, 0, 0.1), 0.6, 0.8)
        return b.build(sharp_angle=SHARP)

    yel = 0.0 if stage == 2 else 0.45
    if stage == 2:
        fruit_c = Vector((0.27, -0.25, 0))
        pumpkin_fruit(b, fruit_c, 0.17, 0.125, 8, srgb(62, 112, 48), srgb(152, 180, 92), srgb(96, 150, 62), 16, yaw=20, tilt=(8, 6))
        b.tube([fruit_c + Vector((0, 0, 0.115)), fruit_c + Vector((-0.02, 0.02, 0.15)), fruit_c + Vector((-0.07, 0.06, 0.13))],
               [0.014, 0.011, 0.009], mat='plant', segs=4, color=P_VINE0, color_top=P_VINE1)
        starts = [((0, 0, 0), 0.5, 0.46), ((0, 0, 0), 2.7, 0.46), ((0, 0, 0), 4.45, 0.44)]
        leaf_r = (0.10, 0.13)
        n_leaf = [4, 4, 4]
        keep = 0.25
    else:
        fruit_c = Vector((0.04, -0.05, 0))
        pumpkin_fruit(b, fruit_c, 0.46, 0.33, 10, srgb(236, 124, 32), srgb(184, 78, 20), srgb(246, 156, 52), 40, yaw=12, tilt=(3, -4))
        top = fruit_c + Vector((0, 0, 0.305))
        b.tube([top, top + Vector((0.012, 0.0, 0.05)), top + Vector((0.05, 0.02, 0.09)), top + Vector((0.105, 0.045, 0.085)),
                top + Vector((0.13, 0.07, 0.05))], [0.034, 0.026, 0.021, 0.019, 0.021], mat='plant', segs=6,
               color=srgb(96, 112, 54), color_top=srgb(156, 150, 84))
        starts = [((0.2, 0.14, 0), 0.9, 0.3), ((-0.16, 0.12, 0), 2.6, 0.3), ((-0.1, -0.24, 0), 4.3, 0.28), ((0.24, -0.16, 0), 5.6, 0.26)]
        leaf_r = (0.13, 0.165)
        n_leaf = [3, 3, 2, 2]
        keep = 0.37
    for vi, (st, a0, ln) in enumerate(starts):
        pts = vine(b, st, a0, ln, 0.55, vi * 2.1 + stage)
        for k in range(n_leaf[vi]):
            t = (k + 0.8) / n_leaf[vi]
            i = min(len(pts) - 1, int(round(t * (len(pts) - 1))))
            base = pts[i]
            side = 1 if (k + vi) % 2 == 0 else -1
            d = (pts[i] - pts[max(i - 1, 0)]).normalized()
            perp = Vector((-d.y, d.x, 0)) * side
            hub = base + perp * r.uniform(0.07, 0.12) + Vector((0, 0, r.uniform(0.1, 0.17) + (0.03 if stage == 3 else 0)))
            fd = Vector((hub.x - fruit_c.x, hub.y - fruit_c.y, 0))
            if fd.length < keep:  # keep leaves off the fruit so it stays readable
                hub += fd.normalized() * (keep - fd.length) if fd.length > 1e-4 else Vector((keep, 0, 0))
            hub = clampxy(hub)
            petiole(b, base, hub)
            pumpkin_leaf(b, hub, r.uniform(*leaf_r), math.degrees(math.atan2(perp.y, perp.x)), yellow=yel * r.uniform(0.3, 1.0))
        if vi < 3:
            tendril(b, pts[-2], a0 + 0.8, 0.9)
        if stage == 2:
            p = pts[3]
            d = Vector((math.cos(a0 + 1.9) * 0.35, math.sin(a0 + 1.9) * 0.35, 1.0)).normalized()
            fp = clampxy(p + d * 0.24)
            b.tube([p, p.lerp(fp, 0.5) + Vector((0.01, 0.01, 0)), fp], 0.007, mat='plant', segs=3, caps=False, color=P_VINE1)
            rosette(b, 0.078, 5, fp, aim(d), srgb(236, 138, 28), srgb(252, 200, 50), cup=0.45, inner=0.62, jitter=0.05)
    return b.build(sharp_angle=SHARP)


# ----------------------------------------------------------- ground cover ----
def flower_daisy():
    b = Builder('flower_daisy', seed=401)
    r = b.rng
    heads = [(-0.07, 0.02, 0.27), (0.06, -0.05, 0.22), (0.03, 0.08, 0.3), (-0.02, -0.09, 0.17)]
    for (x, y, h) in heads:
        base = Vector((x * 0.3, y * 0.3, 0))
        top = Vector((x, y, h))
        b.tube([base, base.lerp(top, 0.5) + Vector((x * 0.2, y * 0.2, 0)), top], 0.005, mat='plant', segs=3, caps=False,
               color=srgb(70, 130, 50), color_top=srgb(120, 170, 70))
        d = Vector((x * 1.5, y * 1.5, 1)).normalized()
        e = aim(d)
        star(b, 0.055, 8, top, e, srgb(240, 236, 226), srgb(255, 253, 246), z_center=0.004, z_tip=-0.002, inner=0.55)
        b.lathe([(0.018, 0.0), (0.012, 0.01), (0, 0.014)], loc=top, rot=e, mat='plant', segs=6, color=srgb(240, 180, 30), color_top=srgb(250, 214, 60))
    for k in range(7):
        b.leaf(r.uniform(0.09, 0.14), 0.03, loc=(0, 0, 0), rot=(0, r.uniform(30, 60), k * 51 + 10), bend=50, fold=20, segs=2,
               color=srgb(54, 112, 42), color_top=srgb(110, 164, 62), jitter=0.08)
    return b.build(sharp_angle=SHARP)


def flower_poppy():
    b = Builder('flower_poppy', seed=402)
    r = b.rng
    heads = [(-0.06, 0.03, 0.36), (0.07, 0.02, 0.29), (0.0, -0.08, 0.23)]
    for i, (x, y, h) in enumerate(heads):
        base = Vector((x * 0.2, y * 0.2, 0))
        top = Vector((x, y, h))
        b.tube([base, base.lerp(top, 0.55) + Vector((x * 0.3, y * 0.3, 0)), top], 0.005, mat='plant', segs=3, caps=False,
               color=srgb(74, 128, 54), color_top=srgb(126, 170, 78))
        d = Vector((x * 1.2, y * 1.2, 1)).normalized()
        e = aim(d)
        rosette(b, 0.062, 5, top, e, srgb(150, 24, 26), srgb(224, 54, 38), cup=0.5, inner=0.8, jitter=0.06, wav=0.1)
        b.lathe([(0.013, 0.004), (0.009, 0.016), (0, 0.02)], loc=top, rot=e, mat='plant', segs=5, color=srgb(30, 26, 30), color_top=srgb(90, 110, 50))
    # a nodding bud
    b.tube([(0.01, 0.02, 0), (0.05, 0.07, 0.17), (0.075, 0.1, 0.165)], 0.0045, mat='plant', segs=3, caps=False, color=srgb(74, 128, 54))
    b.lathe([(0, 0), (0.014, 0.012), (0.012, 0.03), (0, 0.04)], loc=(0.075, 0.1, 0.17), rot=(120, 0, 40), mat='plant', segs=5,
            color=srgb(96, 146, 70), color_top=srgb(150, 60, 44))
    for k in range(5):
        b.leaf(r.uniform(0.1, 0.16), 0.036, loc=(0, 0, 0), rot=(0, r.uniform(25, 55), k * 72 + 15), bend=55, fold=22, segs=2,
               color=srgb(60, 112, 54), color_top=srgb(120, 162, 84), jitter=0.08)
    return b.build(sharp_angle=SHARP)


def flower_lavender():
    b = Builder('flower_lavender', seed=403)
    r = b.rng
    for k in range(7):
        a = k * 2.4
        lean = r.uniform(0.04, 0.13)
        h = r.uniform(0.26, 0.34)
        base = Vector((math.cos(a) * 0.02, math.sin(a) * 0.02, 0))
        top = Vector((math.cos(a) * lean, math.sin(a) * lean, h))
        b.tube([base, top], 0.004, mat='plant', segs=3, caps=False, color=srgb(96, 132, 92), color_top=srgb(132, 150, 120))
        d = (top - base).normalized()
        L = r.uniform(0.09, 0.115)
        b.lathe([(0, 0), (0.015, 0.14 * L), (0.01, 0.4 * L), (0.014, 0.58 * L), (0, L)], loc=top, rot=aim(d),
                mat='plant', segs=5, color=srgb(112, 84, 176), color_top=srgb(172, 146, 226), jitter=0.08)
    for k in range(6):
        b.leaf(r.uniform(0.1, 0.17), 0.018, loc=(0, 0, 0), rot=(0, r.uniform(15, 50), k * 60 + 8), bend=30, fold=18, segs=2,
               color=srgb(96, 132, 92), color_top=srgb(150, 172, 130), jitter=0.06)
    return b.build(sharp_angle=SHARP)


def reed_clump():
    b = Builder('reed_clump', seed=404)
    r = b.rng
    for k in range(5):
        a = k * 2.5 + 0.4
        x, y = math.cos(a) * r.uniform(0.03, 0.12), math.sin(a) * r.uniform(0.03, 0.12)
        h = r.uniform(0.95, 1.22)
        lx, ly = x + math.cos(a) * 0.06, y + math.sin(a) * 0.06
        b.tube([(x, y, 0), ((x + lx) / 2, (y + ly) / 2, h * 0.5), (lx, ly, h)], 0.0075, mat='plant', segs=3, caps=False,
               color=srgb(74, 120, 54), color_top=srgb(136, 160, 84))
        d = Vector((lx - x, ly - y, h)).normalized()
        e = aim(d)
        top = Vector((lx, ly, h))
        b.lathe([(0, 0), (0.021, 0.012), (0.024, 0.075), (0.021, 0.14), (0, 0.152)], loc=top, rot=e, mat='plant', segs=6,
                color=srgb(92, 56, 34), color_top=srgb(124, 80, 46), jitter=0.06)
        tip = top + d * 0.15
        raw(b, [tuple(tip + Vector((0.004, 0, 0))), tuple(tip - Vector((0.004, 0, 0))), tuple(tip + d * 0.09)], [(0, 1, 2)], srgb(150, 150, 90))
    for k in range(12):
        a = k * 30 + r.uniform(-12, 12)
        b.leaf(r.uniform(0.7, 1.05), 0.036, loc=(math.cos(math.radians(a)) * 0.05, math.sin(math.radians(a)) * 0.05, 0),
               rot=(0, r.uniform(6, 22), a), bend=r.uniform(14, 48), fold=26, segs=3, color=srgb(60, 112, 48),
               color_top=srgb(150, 180, 84), jitter=0.08)
    return b.build(sharp_angle=SHARP)


def lily_pad():
    b = Builder('lily_pad', seed=405)
    pads = [((0.0, 0.0), 0.2, 30), ((0.33, 0.12), 0.15, 160), ((0.1, -0.3), 0.13, 250)]
    for (x, y), rad, yaw in pads:
        disc_leaf(b, rad, (x, y, 0.004), (0, 0, yaw), srgb(96, 150, 60), srgb(66, 128, 52), srgb(48, 104, 46), lobes=0, n=12,
                  cup=-0.04, notch=0.88, wav=0.012, jitter=0.06, mat='plant_glossy')
    c = Vector((0.2, -0.08, 0.008))
    for ring, (n, L, pitch, col0, col1) in enumerate(((6, 0.105, 64, srgb(238, 150, 176), srgb(252, 214, 226)),
                                                     (5, 0.08, 30, srgb(244, 176, 196), srgb(255, 232, 238)))):
        for k in range(n):
            b.leaf(L, 0.05, loc=c, rot=(0, pitch, k * 360 / n + ring * 30), bend=-28, fold=24, segs=2, shape=OVAL, color=col0, color_top=col1)
    b.lathe([(0.018, 0.0), (0.014, 0.02), (0, 0.026)], loc=c, mat='plant', segs=6, color=srgb(244, 190, 50))
    return b.build(sharp_angle=SHARP)


# --------------------------------------------------------------- wildlife ----
BIRD_S = 0.76
B_BACK, B_CAP, B_BELLY, B_BREAST, B_DARK = srgb(118, 90, 64), srgb(84, 62, 46), srgb(238, 224, 198), srgb(228, 116, 52), srgb(52, 40, 32)


def bird():
    """Origin = body centre (it flies). Faces -Y. Wings are children hinged at the shoulders (flap about Y)."""
    b = Builder('bird', seed=501)
    L, R = 0.088, 0.035

    def body_c(co):
        up = co.y / R
        f = co.z / L
        c = mix(B_BELLY, B_BACK, smooth(-0.2, 0.4, up))
        br = smooth(0.35, 0.7, f) * (1 - smooth(-0.15, 0.45, up))
        return mix(c, B_BREAST, br)

    hr = 0.027

    def head_c(co):
        up = co.y / hr
        f = co.z / (2 * hr)
        c = mix(B_BELLY, B_CAP, smooth(0.0, 0.45, up))
        return mix(c, B_BREAST, (1 - smooth(-0.75, -0.25, up)) * smooth(0.2, 0.6, f))

    with b.at(scale=(BIRD_S, BIRD_S, BIRD_S)):
        prof = [(0, 0), (0.013, 0.004), (0.027, 0.02), (R, 0.046), (0.032, 0.068), (0.02, 0.082), (0, L)]
        b.lathe(prof, loc=(0, 0.042, 0), rot=(90, 0, 0), mat='plant', segs=12, color=body_c)
        hp = [(0, 0), (0.6 * hr, 0.2 * hr), (0.95 * hr, 0.65 * hr), (hr, hr), (0.92 * hr, 1.4 * hr), (0.55 * hr, 1.85 * hr), (0, 2 * hr)]
        b.lathe(hp, loc=(0, -0.022, 0.024), rot=(90, 0, 0), mat='plant', segs=10, color=head_c)
        b.lathe([(0.0075, 0), (0.0045, 0.009), (0, 0.02)], loc=(0, -0.073, 0.022), rot=(98, 0, 0), mat='plant_glossy', segs=5,
                color=srgb(236, 176, 64), color_top=srgb(120, 80, 40))
        for sx in (-1, 1):
            ball(b, 0.0052, (sx * 0.0195, -0.06, 0.031), 'plant_glossy', srgb(16, 13, 12), segs=6)
        raw(b, [(-0.009, 0.03, 0.006), (0.009, 0.03, 0.006), (0.02, 0.098, 0.016), (-0.02, 0.098, 0.016), (0, 0.108, 0.016), (0, 0.03, 0.012)],
            [(0, 1, 2, 3), (3, 2, 4), (0, 5, 1)], [B_BACK, B_BACK, B_DARK, B_DARK, B_DARK, B_BACK])
    root = b.build(sharp_angle=SHARP)
    for name, sx in (('bird_wing_l', 1), ('bird_wing_r', -1)):
        w = Builder(name, seed=502)
        s = BIRD_S
        verts = [(0, -0.02, 0), (0, 0.024, 0), (0.034, -0.027, 0.004), (0.036, 0.034, 0.002), (0.068, -0.02, 0.006), (0.066, 0.04, 0.002),
                 (0.1, 0.016, 0.004), (0.085, 0.036, 0.003)]
        faces = [(0, 2, 3, 1), (2, 4, 5, 3), (4, 6, 7, 5)]
        cols = [B_BACK, B_BACK, B_BACK, B_CAP, B_CAP, B_DARK, B_DARK, B_DARK]
        raw(w, verts, faces, cols, 'plant', scale=(sx * s, s, s))
        wo = w.build(sharp_angle=SHARP)
        kit.set_parent(wo, root, (sx * 0.024 * s, -0.012 * s, 0.014 * s))
    return root


def butterfly():
    """Origin = body centre. Faces -Y. Wings are children hinged on the body line (flap about Y)."""
    b = Builder('butterfly', seed=511)
    DARK = srgb(34, 24, 20)
    b.tube([(0, -0.011, 0), (0, -0.005, 0.0006), (0, 0.003, 0.0004), (0, 0.012, 0)], [0.0010, 0.0026, 0.0022, 0.0007], mat='plant',
           segs=4, caps=False, color=DARK)
    raw(b, [(0.0006, -0.011, 0.0005), (-0.0006, -0.011, 0.0005), (0.004, -0.02, 0.004), (-0.004, -0.02, 0.004)], [(0, 1, 2), (1, 0, 3)], DARK)
    root = b.build(sharp_angle=SHARP)
    ORANGE_IN, ORANGE, PALE = srgb(210, 108, 30), srgb(248, 156, 42), srgb(252, 242, 220)
    fore = [(0, -0.008), (0.014, -0.024), (0.031, -0.033), (0.043, -0.027), (0.040, -0.013), (0.024, -0.002), (0, 0.002)]
    hind = [(0, 0.0), (0.019, 0.0), (0.031, 0.007), (0.031, 0.02), (0.021, 0.029), (0.008, 0.025), (0, 0.012)]
    rings = [(0.55, 'i'), (0.78, 'o'), (0.82, 'd'), (0.89, 'd'), (0.95, 'd'), (1.0, 'd')]
    for name, sx in (('butterfly_wing_l', 1), ('butterfly_wing_r', -1)):
        w = Builder(name, seed=512)
        for wi, (outline, root_pt, zoff) in enumerate(((fore, (0.0, -0.003), 0.0004), (hind, (0.0, 0.004), 0.0))):
            n = len(outline)
            verts, cols, faces, fcols = [(root_pt[0], root_pt[1], zoff)], [ORANGE_IN], [], []
            for s, kind in rings:
                for (x, y) in outline:
                    verts.append((root_pt[0] + (x - root_pt[0]) * s, root_pt[1] + (y - root_pt[1]) * s, zoff))
                    cols.append(mix(ORANGE_IN, ORANGE, 0.6) if kind == 'i' else (ORANGE if kind == 'o' else DARK))
            for i in range(n - 1):
                faces.append((0, 1 + i, 2 + i))
                fcols.append(None)
            for ri in range(len(rings) - 1):
                a0, b0 = 1 + ri * n, 1 + (ri + 1) * n
                for i in range(n - 1):
                    faces.append((a0 + i, b0 + i, b0 + i + 1, a0 + i + 1))
                    fcols.append(PALE if (ri == 3 and ((wi == 0 and i in (1, 3)) or (wi == 1 and i == 3))) else None)
            raw(w, verts, faces, cols, 'plant', scale=(sx, 1, 1), face_cols=fcols)
        wo = w.build(sharp_angle=SHARP)
        kit.set_parent(wo, root, (sx * 0.0012, 0, 0.001))
    return root


# ------------------------------------------------------------------ build ----
ASSETS = {}


def add(obj):
    ASSETS[obj.name] = obj
    return obj


for fn in (tree_apple_a, tree_apple_b, tree_oak, tree_far):
    add(fn())
add(bush('bush_a', 61))
add(bush('bush_b', 62, berries=True))
for s in range(4):
    add(wheat(s))
for s in range(4):
    add(tomato(s))
for s in range(4):
    add(pumpkin(s))
for fn in (flower_daisy, flower_poppy, flower_lavender, reed_clump, lily_pad, bird, butterfly):
    add(fn())

bpy.context.view_layer.update()
BUDGET = {'tree_apple_a': 9000, 'tree_apple_b': 9000, 'tree_oak': 10000, 'tree_far': 700, 'bush_a': 2000, 'bush_b': 2000,
          'flower_daisy': 300, 'flower_poppy': 300, 'flower_lavender': 300, 'reed_clump': 500, 'lily_pad': 300, 'bird': 600,
          'butterfly': 300}
print('---- REPORT ----')
for name, o in ASSETS.items():
    objs = kit._descend([o])
    pts = [ob.matrix_world @ Vector(c) for ob in objs for c in ob.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    tris = kit.tri_count(objs)
    lim = BUDGET.get(name, 1800)
    mats = sorted({m.name for ob in objs for m in ob.data.materials})
    print(f'{name:18s} size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f}  z[{lo[2]:.2f},{hi[2]:.2f}]  tris {tris:5d}/{lim}'
          f'{"  OVER" if tris > lim else ""}  {mats}')

os.makedirs(os.path.join(ROOT, 'public', 'models'), exist_ok=True)
kit.export_glb(os.path.join(ROOT, 'public', 'models', 'vegetation.glb'), list(ASSETS.values()))


# --------------------------------------------------------------- previews ----
def leaf_preview_texture():
    """Preview only (after export): give the `leaf` material a leaf-tuft alpha so canopies read like in game."""
    import numpy as np
    N = 256
    img = bpy.data.images.new('_leaf_pv', N, N, alpha=True)
    yy, xx = np.mgrid[0:N, 0:N]
    u = (xx + 0.5) / N - 0.5
    v = (yy + 0.5) / N - 0.5
    a = np.zeros((N, N))
    shade = np.ones((N, N))
    leaves = [(k * 2 * pi / 8 + 0.3, 0.22, 0.26, 0.15) for k in range(8)] + [(0.9, 0.05, 0.2, 0.13), (3.6, 0.06, 0.2, 0.13)]
    for i, (ang, dist, la, lb) in enumerate(leaves):
        cx, cy = dist * math.cos(ang), dist * math.sin(ang)
        du, dv = u - cx, v - cy
        lr = du * math.cos(ang) + dv * math.sin(ang)
        lt = -du * math.sin(ang) + dv * math.cos(ang)
        m = (lr / la) ** 2 + (lt / (lb * (1 - 0.35 * lr / la))) ** 2 < 1
        a[m] = 1
        shade[m] = 0.82 + 0.18 * ((i * 37) % 10) / 10
    px = np.zeros((N, N, 4), dtype=np.float32)
    px[..., 0] = px[..., 1] = px[..., 2] = shade
    px[..., 3] = a
    img.pixels.foreach_set(px.ravel())
    mat = bpy.data.materials.get('leaf')
    if not mat:
        return
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    mixn = next(n for n in nt.nodes if n.type == 'MIX')
    nt.links.new(tex.outputs['Color'], next(s for s in mixn.inputs if s.identifier == 'A_Color'))


def shoot(name, names, spacing=0.0, az=28, el=30, zoom=1.0, size=(1200, 760)):
    if ONLY is not None and name not in ONLY:
        return
    objs = [ASSETS[n] for n in names]
    for o in bpy.data.objects:
        o.hide_render = True
    for i, o in enumerate(objs):
        for c in kit._descend([o]):
            c.hide_render = False
        o.location.x = (i - (len(objs) - 1) / 2) * spacing
    bpy.context.view_layer.update()
    kit.render_preview(os.path.join(OUT, name + '.png'), objs, az=az, el=el, size=size, zoom=zoom)
    for o in objs:
        o.location = (0, 0, 0)


if ONLY != {'none'}:
    leaf_preview_texture()
    shoot('wheat', [f'wheat_{i}' for i in range(4)], 1.25, zoom=1.25, size=(1600, 600))
    shoot('tomato', [f'tomato_{i}' for i in range(4)], 1.2, zoom=1.25, size=(1600, 600))
    shoot('pumpkin', [f'pumpkin_{i}' for i in range(4)], 1.25, zoom=1.25, size=(1600, 560))
    shoot('ripe_top', ['wheat_3', 'tomato_3', 'pumpkin_3'], 1.3, az=40, el=52, zoom=1.25)
    shoot('ripe_close', ['wheat_3', 'tomato_3', 'pumpkin_3'], 1.2, az=15, el=18, zoom=1.3, size=(1600, 700))
    shoot('tree_apple_a', ['tree_apple_a'], az=30, el=20, size=(900, 900), zoom=1.25)
    shoot('tree_apple_b', ['tree_apple_b'], az=30, el=20, size=(900, 900), zoom=1.25)
    shoot('trees_top', ['tree_apple_a', 'tree_apple_b'], 4.8, az=40, el=48, zoom=1.4)
    shoot('tree_oak', ['tree_oak', 'tree_far'], 9.0, az=30, el=18, zoom=1.4)
    shoot('bushes', ['bush_a', 'bush_b'], 1.7, az=25, el=28, zoom=1.3)
    shoot('flowers', ['flower_daisy', 'flower_poppy', 'flower_lavender'], 0.5, az=20, el=26, zoom=1.2)
    shoot('pond', ['reed_clump', 'lily_pad'], 0.9, az=25, el=32, zoom=1.2)
    shoot('bird', ['bird'], az=40, el=25, size=(900, 700), zoom=1.0)
    shoot('butterfly', ['butterfly'], az=30, el=55, size=(900, 700), zoom=1.0)
