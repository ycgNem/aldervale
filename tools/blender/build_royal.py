"""Royal assets for the homestead demo: far castle, requisition board, supply wagon, banner pole, milestone.

  blender --background --factory-startup --python tools/blender/build_royal.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/royal.glb.
With group names only those groups are built + previewed (no export) for fast iteration.
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, noise  # noqa: E402
import kit  # noqa: E402
from kit import Builder, srgb  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PREV = argv[0] if argv else None
ONLY = set(argv[1:])
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'public', 'models', 'royal.glb')

kit.reset()

# new material names (the game supplies the real PBR materials by name)
kit.PREVIEW.update({'slate': (0.17, 0.23, 0.37), 'gold': (0.86, 0.62, 0.22), 'parchment': (0.86, 0.78, 0.60)})
kit.ROUGH.update({'slate': 0.6, 'gold': 0.32, 'parchment': 0.9})
_g = kit.get_mat('gold')
next(n for n in _g.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs['Metallic'].default_value = 1.0

BLUE = srgb(38, 62, 128)
GOLD = srgb(214, 168, 64)
CREAM = srgb(236, 226, 200)
INK = srgb(58, 42, 32)
WAX = srgb(168, 38, 34)
HUES = [(1, 1, 1), (1.0, 0.95, 0.88), (0.92, 0.95, 1.0), (0.96, 1.0, 0.93), (1.0, 0.97, 0.92)]
G0, G1 = srgb(48, 100, 38), srgb(112, 168, 62)
MARKS = {}     # asset name -> [(marker name, pos)]
CHILDREN = {}  # asset name -> [(child object, local pos)]


def tint(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def R(b, a, c):
    return b.rng.uniform(a, c)


def mark(b, name, local=(0, 0, 0), asset=None):
    MARKS.setdefault(asset or b.name, []).append((name, tuple(b.stack[-1] @ Vector(local))))


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


def stone(b, size, loc, rot0=(0, 0, 0), bev=None, segs=2, rj=3.0, mat='stone', jitter=0.15, k=1.0):
    bev = bev if bev is not None else min(0.07, min(size) * 0.3)
    b.box(size, loc=loc, rot=(rot0[0] + R(b, -rj, rj), rot0[1] + R(b, -rj, rj), rot0[2] + R(b, -rj, rj)), mat=mat,
          bevel=bev, segs=segs, grain=None, color=tint(b.rng.choice(HUES), k), jitter=jitter)


def wood(b, size, loc=(0, 0, 0), rot=(0, 0, 0), mat='wood_plank', bevel=0.012, segs=1, jitter=0.1, rj=0.0, **kw):
    rot = (rot[0] + R(b, -rj, rj), rot[1] + R(b, -rj, rj), rot[2] + R(b, -rj, rj)) if rj else rot
    b.box(size, loc=loc, rot=rot, mat=mat, bevel=bevel, segs=segs, jitter=jitter, **kw)


def chev(s=1.0):
    return [(-0.30 * s, -0.27 * s), (-0.25 * s, -0.32 * s), (0, -0.07 * s), (0.25 * s, -0.32 * s),
            (0.30 * s, -0.27 * s), (0, 0.03 * s)]


def gable_roof(b, loc, length, run, pitch, yaw=0, row_h=0.33, sw=(0.34, 0.5), thick=0.045, barge=True, cap=1.2,
               cap_z=0.2):
    """Same construction as the cottage / well roofs: deck, fascia, individual shingles, barge boards, ridge caps."""
    pr = math.radians(pitch)
    L = run / math.cos(pr)
    tilt = math.degrees(math.atan2(thick * 1.1, row_h))
    with b.at(loc=loc, rot=(0, 0, yaw)):
        for side in (0, 180):
            with b.at(rot=(pitch, 0, side)):
                b.box((length - 0.06, L, 0.05), loc=(0, -L / 2, -0.025), mat='wood_plank', bevel=0.01, segs=1,
                      grain=0, jitter=0.05)
                b.box((length - 0.05, 0.04, 0.1), loc=(0, -L + 0.01, -0.03), mat='wood_dark', bevel=0.012,
                      segs=1, jitter=0.08)
                rows = int(math.ceil(L / row_h))
                for r in range(rows):
                    y0 = -L + r * row_h
                    x = -length / 2 - 0.03
                    while x < length / 2 - 0.1:
                        w = R(b, *sw)
                        if x + w > length / 2 + 0.03:
                            w = length / 2 + 0.03 - x
                        ln = row_h * 1.7 + R(b, -0.02, 0.05)
                        lo = y0 - 0.04 + R(b, -0.03, 0.025)
                        hi = min(lo + ln, -0.01)
                        ln2 = hi - lo
                        if ln2 > 0.06 and w > 0.07:
                            cz = thick / 2 + (ln2 / 2) * math.sin(math.radians(tilt)) + 0.004
                            b.box((w - 0.01, ln2, thick), loc=(x + w / 2, (lo + hi) / 2, cz),
                                  rot=(-tilt + R(b, -1.5, 1.5), R(b, -2.2, 2.2), R(b, -2.5, 2.5)), mat='roof',
                                  bevel=0.008, segs=1, grain=1, jitter=0.18)
                        x += w
                if barge:
                    for sx in (-1, 1):
                        b.box((0.055, L + 0.1, 0.14), loc=(sx * (length / 2 - 0.02), -L / 2 - 0.02, -0.07),
                              mat='wood_dark', bevel=0.014, segs=2, jitter=0.08, grain=1)
        if cap:
            n = int(math.ceil(length / (0.42 * cap)))
            step = length / n
            for i in range(n):
                x = -length / 2 + (i + 0.5) * step
                b.prism(chev(cap), depth=step + 0.1 * cap, loc=(x, 0, cap_z * cap + 0.01),
                        rot=(R(b, 2, 5), R(b, -2, 2), 90 + R(b, -2, 2)), mat='roof', bevel=0.01, segs=1, jitter=0.18,
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


def chisel(b, radii, n, lo=0.52, hi=0.86):
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


def rock(b, radii, loc, yaw=0.0, subdiv=3, planes=12, dark=0.76, light=1.0, flat=-0.42, lo=0.52, hi=0.86):
    b.blob(radii, loc=(loc[0], loc[1], loc[2] + 0.4 * radii[2]), mat='stone', subdiv=subdiv, noise_amp=0.13,
           noise_scale=1.2, flatten_bottom=flat, color=(dark, dark * 0.98, dark * 0.95),
           color_top=(light, light * 0.98, light * 0.95), rot=(0, 0, yaw), deform=chisel(b, radii, planes, lo, hi), jitter=0.05)


def tuft(b, x, y, n=7, h=(0.12, 0.3), z=0.0):
    for _ in range(n):
        b.leaf(R(b, *h), 0.03, loc=(x + R(b, -0.06, 0.06), y + R(b, -0.06, 0.06), z), rot=(0, R(b, 5, 38), R(b, 0, 360)),
               color=G0, color_top=G1, bend=R(b, 20, 60), segs=3, jitter=0.15)


def sheet(b, nu, nv, pos, cellcol, mat='cloth', thick=0.01, loc=(0, 0, 0), rot=(0, 0, 0), uvsize=(1, 1), back=1.0,
          mask=None):
    """Cloth / paper sheet: (nu x nv) quads, pos(u,v)->xyz, cellcol(i,j)->linear rgb (hard-edged per cell).
    With thick > 0 it is a closed double layer (front normal = du x dv), so it works single- or double-sided."""
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
            if thick:
                K[i][j] = t.verts.new(P[i][j] - n * thick / 2)

    def ok(i, j):
        return 0 <= i < nu and 0 <= j < nv and (mask is None or mask(i, j))

    def put(f, ids, c):
        for l, (i, j) in zip(f.loops, ids):
            l[uv].uv = (i / nu * uvsize[0], j / nv * uvsize[1])
            l[col] = (c[0], c[1], c[2], 1.0)

    for i in range(nu):
        for j in range(nv):
            if not ok(i, j):
                continue
            c = cellcol(i, j)
            ids = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            put(t.faces.new([F[a][d] for a, d in ids]), ids, c)
            if thick:
                cb = tint(c, back)
                ids2 = ids[::-1]
                put(t.faces.new([K[a][d] for a, d in ids2]), ids2, cb)
                for k, (ni, nj) in enumerate([(i, j - 1), (i + 1, j), (i, j + 1), (i - 1, j)]):
                    if not ok(ni, nj):
                        a, d = ids[k], ids[(k + 1) % 4]
                        put(t.faces.new((F[d[0]][d[1]], F[a[0]][a[1]], K[a[0]][a[1]], K[d[0]][d[1]])), [d, a, a, d], c)
    loose = [v for v in t.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(t, geom=loose, context='VERTS')
    t.normal_update()
    b._emit(t, mat, loc, rot)


def flat_poly(b, pts, y, mat, color, back=None, yfn=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Flat polygon in the XZ plane (pts ccw seen from the front / -Y) at depth y; `back` adds a reversed copy."""
    t = b._new()
    uv, col, _ = b._layers(t)

    def mk(yy, rev):
        vs = [t.verts.new((x, (yfn(x, z) if yfn else 0.0) + yy, z)) for x, z in pts]
        f = t.faces.new(vs[::-1] if rev else vs)
        for l in f.loops:
            l[uv].uv = (l.vert.co.x, l.vert.co.z)
            l[col] = (color[0], color[1], color[2], 1.0)

    mk(y, False)
    if back is not None:
        mk(back, True)
    t.normal_update()
    b._emit(t, mat, loc, rot)


def xf(pts, cx=0.0, cz=0.0, ang=0.0, s=1.0):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + (x * ca - z * sa) * s, cz + (x * sa + z * ca) * s) for x, z in pts]


def crown_pts(w, h):
    return [(-w * 0.42, 0), (w * 0.42, 0), (w * 0.56, h), (w * 0.27, h * 0.48), (0, h * 1.12), (-w * 0.27, h * 0.48),
            (-w * 0.56, h)]


def shield_pts(w, h):
    return [(0, -h / 2), (w * 0.3, -h * 0.3), (w * 0.46, -h * 0.05), (w / 2, h * 0.2), (w / 2, h / 2), (-w / 2, h / 2),
            (-w / 2, h * 0.2), (-w * 0.46, -h * 0.05), (-w * 0.3, -h * 0.3)]


GRAIN = [(0, -0.5), (0.3, -0.12), (0.26, 0.2), (0, 0.5), (-0.26, 0.2), (-0.3, -0.12)]


def crest(b, s=1.0, wheat=True, field=None, band=None, diamond=None):
    """Royal crest: gold-rimmed blue shield, gold wheat ear, gold crown. Local frame: backing plane y=0, outward -Y,
    origin = shield centre. ~0.36 x 0.5 at s=1."""
    w, h = 0.34 * s, 0.4 * s
    b.prism(shield_pts(w + 0.05 * s, h + 0.05 * s), 0.03 * s, loc=(0, -0.015 * s, 0), mat='gold', bevel=0.006 * s, segs=1)
    b.prism(shield_pts(w, h), 0.03 * s, loc=(0, -0.034 * s, 0), mat='paint', color=field or BLUE, bevel=0.008 * s, segs=2)
    # cream chief band across the top of the shield
    b.box((w - 0.03 * s, 0.012 * s, 0.05 * s), loc=(0, -0.05 * s, h / 2 - 0.05 * s), mat='paint', color=band or CREAM, bevel=0.004 * s,
          segs=1)
    if wheat:
        b.box((0.014 * s, 0.012 * s, 0.24 * s), loc=(0, -0.052 * s, -0.045 * s), mat='gold', bevel=0.004 * s, segs=1)
        for i in range(4):
            for sx in (-1, 1):
                b.lathe([(0, 0), (0.021 * s, 0.03 * s), (0, 0.08 * s)], loc=(sx * 0.014 * s, -0.056 * s, (-0.1 + i * 0.045) * s),
                        rot=(0, sx * 34, 0), scale=(1, 0.5, 1), mat='gold', segs=6)
        b.lathe([(0, 0), (0.02 * s, 0.03 * s), (0, 0.08 * s)], loc=(0, -0.056 * s, 0.07 * s), scale=(1, 0.5, 1), mat='gold', segs=6)
    if diamond:
        b.prism([(0, -0.11 * s), (0.075 * s, -0.02 * s), (0, 0.07 * s), (-0.075 * s, -0.02 * s)], 0.012 * s, loc=(0, -0.052 * s, -0.03 * s),
                mat='paint', color=diamond, bevel=0.003 * s, segs=1)
    # crown
    cz = h / 2 + 0.035 * s
    b.prism(crown_pts(0.26 * s, 0.1 * s), 0.03 * s, loc=(0, -0.03 * s, cz), mat='gold', bevel=0.005 * s, segs=1)
    b.box((0.24 * s, 0.04 * s, 0.028 * s), loc=(0, -0.032 * s, cz + 0.004 * s), mat='gold', bevel=0.006 * s, segs=1)
    for x, z in ((-0.145, 0.1), (0, 0.112), (0.145, 0.1)):
        b.blob(0.017 * s, loc=(x * s, -0.03 * s, cz + z * s + 0.008 * s), mat='gold', subdiv=1)
    for x in (-0.07, 0.0, 0.07):
        b.blob(0.011 * s, loc=(x * s, -0.054 * s, cz + 0.004 * s), mat='paint', subdiv=1, color=WAX if x == 0 else BLUE)


# ============================================================================================
# CASTLE (seen from 200-300 m)
# ============================================================================================
def lancet(b, w=0.9, h=2.2):
    """Pointed window. Local frame: wall plane y=0, outward -Y, origin at the sill centre."""
    def arch(w, h):
        return [(-w / 2, 0), (w / 2, 0), (w / 2, h), (0, h + w * 0.62), (-w / 2, h)]

    b.prism([(x, z - 0.25) for x, z in arch(w + 0.55, h + 0.3)], 0.44, loc=(0, -0.04, 0), mat='stone', bevel=0,
            color=(1, 0.99, 0.96))
    b.prism(arch(w, h), 0.12, loc=(0, -0.24, 0), mat='glass', bevel=0)


def merlon_row(b, L, z, mw=1.15, pitch=2.3, th=0.6, mh=1.05, y=0.0):
    n = max(2, int(round(L / pitch)) + 1)
    for i in range(n):
        x = -L / 2 + mw / 2 + i * (L - mw) / (n - 1)
        b.box((mw, th, mh + R(b, -0.04, 0.04)), loc=(x, y, z + mh / 2), mat='stone', bevel=0, segs=1, grain=None,
              color=tint(b.rng.choice(HUES), 0.95), jitter=0.06)


def finial(b, s=1.0):
    b.lathe([(0, 0), (0.2, 0.0), (0.26, 0.12), (0.12, 0.3), (0.3, 0.55), (0.3, 0.7), (0.1, 0.92), (0.07, 1.7), (0, 2.1)],
            scale=(s, s, s), mat='gold', segs=8)


def cone_roof(b, x, y, z, r_eave, hgt, r_under=None, segs=20, sq=False, scale=(1, 1, 1), fin=1.0, lip=0.14, tilt=1.2):
    rows = max(5, int(hgt / 1.25))
    prof = []
    if r_under is not None:
        prof.append((r_under, 0.3))
    prof.append((r_eave, 0.0))
    for k in range(1, rows):
        t = k / rows
        rr = r_eave * ((1 - t) ** 1.22)
        zz = hgt * t
        prof.append((rr, zz))
        prof.append((rr + lip * (1 - t * 0.6), zz))
    prof.append((0, hgt))
    k = R(b, 0.86, 1.0)
    with b.at(loc=(x, y, z), rot=(R(b, -tilt, tilt), R(b, -tilt, tilt), 0), scale=scale):
        b.lathe(prof, rot=(0, 0, 45 if sq else R(b, 0, 30)), mat='slate', segs=4 if sq else segs,
                color=tint((0.8, 0.82, 0.86), k), color_top=tint((1.0, 1.0, 1.0), k))
        if fin:
            with b.at(loc=(0, 0, hgt - 0.5 * fin)):
                finial(b, fin)


def ring_windows(b, x, y, r, z, n, a0=-90, spread=360, w=0.9, h=2.0):
    for i in range(n):
        a = math.radians(a0 + (i - (n - 1) / 2) * spread / n)
        with b.at(loc=(x + (r - 0.03) * math.cos(a), y + (r - 0.03) * math.sin(a), z), rot=(0, 0, math.degrees(a) + 90)):
            lancet(b, w, h)


def round_tower(b, x, y, r, z0, h, roof, style='hat', wins=(), bands=(), base=3.5, segs=24, fin=1.0, blocks=True):
    zt = z0 + h
    cb = b.rng.choice(HUES)
    R2 = r + 0.75
    prof = [(r + 1.3, z0 - base), (r + 0.5, z0 + 2.4), (r + 0.42, z0 + 2.7), (r, z0 + 3.0), (r, zt - 2.4), (r + 0.12, zt - 2.2),
            (R2, zt - 1.2)]
    if style == 'hat':
        prof += [(R2, zt), (0, zt)]
    else:
        prof += [(R2, zt + 1.0), (R2 - 0.6, zt + 1.0), (R2 - 0.6, zt + 0.2), (0, zt + 0.2)]
    b.lathe(prof, loc=(x, y, 0), mat='stone', segs=segs, color=tint(cb, 0.74), color_top=tint(cb, 0.96))
    for zb in bands:
        b.lathe([(r - 0.05, zb - 0.32), (r + 0.24, zb - 0.2), (r + 0.24, zb + 0.2), (r - 0.05, zb + 0.32)], loc=(x, y, z0),
                mat='stone', segs=segs, color=tint(cb, 0.98))
    # corbel blocks under the flare
    nc = max(8, int(round(2 * math.pi * R2 / 1.5)))
    for i in range(nc):
        a = 2 * math.pi * (i + 0.5) / nc
        b.box((0.55, 0.7, 0.8), loc=(x + (r + 0.3) * math.cos(a), y + (r + 0.3) * math.sin(a), zt - 1.75),
              rot=(0, 0, math.degrees(a) + 90), mat='stone', bevel=0, grain=None, color=tint(cb, 0.85), taper=(1, 0.3))
    if blocks:
        for _ in range(int(r * h / 4.5)):
            a = R(b, 0, 2 * math.pi)
            zz = z0 + R(b, 3.4, h - 3.2)
            b.box((R(b, 1.0, 1.7), 0.4, R(b, 0.5, 0.75)), loc=(x + (r - 0.06) * math.cos(a), y + (r - 0.06) * math.sin(a), zz),
                  rot=(0, 0, math.degrees(a) + 90), mat='stone', bevel=0.06, segs=1, grain=None,
                  color=tint(b.rng.choice(HUES), R(b, 0.8, 1.0)))
    for (zr, n, spread, a0) in wins:
        ring_windows(b, x, y, r, z0 + zr, n, a0=a0, spread=spread)
    if style == 'hat':
        cone_roof(b, x, y, zt - 0.25, r + 1.45, roof, r_under=R2 - 0.2, segs=segs, fin=fin)
    else:
        n = max(6, int(round(2 * math.pi * R2 / 2.3)))
        for i in range(n):
            a = 2 * math.pi * i / n
            b.box((2 * math.pi * R2 / n * 0.55, 0.6, 1.05), loc=(x + (R2 - 0.3) * math.cos(a), y + (R2 - 0.3) * math.sin(a), zt + 1.5),
                  rot=(0, 0, math.degrees(a) + 90), mat='stone', bevel=0, segs=1, grain=None,
                  color=tint(b.rng.choice(HUES), 0.95), jitter=0.06)
        b.lathe([(r - 0.9, zt + 0.2), (r - 0.9, zt + 2.6), (0, zt + 2.6)], loc=(x, y, 0), mat='stone', segs=segs, color=tint(cb, 0.86))
        cone_roof(b, x, y, zt + 2.3, r - 0.25, roof, r_under=r - 0.9, segs=segs, fin=fin)
    return zt


def quoins(b, hw_x, hw_y, z0, z1, step=1.25):
    k = 0
    z = z0
    while z < z1 - 0.3:
        for sx in (-1, 1):
            for sy in (-1, 1):
                lx, ly = (1.6, 1.0) if (k + (sx > 0) + (sy > 0)) % 2 == 0 else (1.0, 1.6)
                b.box((lx, ly, step * 0.6), loc=(sx * (hw_x - lx / 2 + 0.14), sy * (hw_y - ly / 2 + 0.14), z + step * 0.35),
                      mat='stone', bevel=0.07, segs=1, grain=None, color=b.rng.choice(HUES), jitter=0.07)
        z += step
        k += 1


def faces4(b, hw_x, hw_y):
    """yield context managers for the 4 faces of a rectangle (local -Y = outward), with half-length along the face."""
    return [((0, -hw_y, 0), 0, hw_x), ((hw_x, 0, 0), 90, hw_y), ((0, hw_y, 0), 180, hw_x), ((-hw_x, 0, 0), -90, hw_y)]


def parapet(b, hw_x, hw_y, zt, over=0.65, corbels=True, cb=(1, 1, 1)):
    """Corbelled, crenellated top for a rectangular tower whose walls end at zt."""
    b.box((2 * (hw_x + over), 2 * (hw_y + over), 1.1), loc=(0, 0, zt - 0.2), mat='stone', bevel=0.08, segs=1, grain=None,
          color=tint(cb, 0.93))
    for loc, yaw, half in faces4(b, hw_x + over, hw_y + over):
        with b.at(loc=loc, rot=(0, 0, yaw)):
            b.box((2 * half, 0.5, 1.0), loc=(0, 0.27, zt + 0.8), mat='stone', bevel=0, grain=None, color=tint(cb, 0.9))
            merlon_row(b, 2 * half, zt + 1.3, y=0.3)
            if corbels:
                n = max(3, int(half * 2 / 1.5))
                for i in range(n):
                    xx = -half + over + 0.5 + i * (2 * half - 2 * over - 1.0) / (n - 1)
                    b.box((0.55, 0.75, 0.9), loc=(xx, over - 0.3, zt - 1.15), mat='stone', bevel=0, grain=None,
                          color=tint(cb, 0.82), taper=(1, 0.3))


def wall(b, p0, p1, h, th=2.4, centre=(0, 2), slits=True):
    """Crenellated curtain wall between two points; outer face is found from the castle centre."""
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    yaw = math.atan2(dy, dx)
    out = (math.sin(yaw), -math.cos(yaw))
    if out[0] * (mx - centre[0]) + out[1] * (my - centre[1]) < 0:
        yaw += math.pi
    L = math.hypot(dx, dy)
    cb = b.rng.choice(HUES)
    with b.at(loc=(mx, my, 0), rot=(0, 0, math.degrees(yaw))):
        b.box((L, th, h + 3.5), loc=(0, 0, h / 2 - 1.75), mat='stone', bevel=0, grain=None, color=tint(cb, 0.72),
              color_top=tint(cb, 0.95))
        b.box((L, th + 1.6, 4.5), loc=(0, 0, -1.0), mat='stone', bevel=0, grain=None, color=tint(cb, 0.7), color_top=tint(cb, 0.84),
              taper=(1, 0.66))
        b.box((L, th + 0.7, 0.55), loc=(0, 0, h - 0.5), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))
        for sy in (-1, 1):
            b.box((L, 0.5, 1.0), loc=(0, sy * (th / 2 + 0.08), h + 0.3), mat='stone', bevel=0, grain=None, color=tint(cb, 0.9))
            merlon_row(b, L - 1.0, h + 0.8, y=sy * (th / 2 + 0.08))
        # buttresses + protruding blocks + slits on the outer face
        nb = int(L / 8.5)
        for i in range(nb):
            xx = -L / 2 + (i + 1) * L / (nb + 1)
            b.box((1.5, 1.7, h * 0.72 + 3), loc=(xx, -th / 2 - 0.5, h * 0.36 - 1.5), mat='stone', bevel=0.1, segs=1, grain=None,
                  color=tint(cb, 0.8), color_top=tint(cb, 0.98), taper=(0.85, 0.45))
        for _ in range(int(L * h / 11)):
            b.box((R(b, 1.0, 1.9), 0.4, R(b, 0.5, 0.8)), loc=(R(b, -L / 2 + 1.5, L / 2 - 1.5), -th / 2 - 0.02, R(b, 2.6, h - 1.4)),
                  mat='stone', bevel=0.06, segs=1, grain=None, color=tint(b.rng.choice(HUES), R(b, 0.78, 1.0)))
        if slits:
            ns = max(1, int(L / 6))
            for i in range(ns):
                xx = -L / 2 + (i + 0.5) * L / ns + R(b, -0.5, 0.5)
                with b.at(loc=(xx + 1.6, -th / 2, h - 3.6)):
                    lancet(b, 0.55, 1.5)


def slab_roof(b, loc, length, run, pitch, yaw=0, row=1.15, thick=0.2, segw=(2.2, 4.2)):
    """Steep slate gable roof for the far castle: big overlapping slate courses (ridge along local X)."""
    pr = math.radians(pitch)
    L = run / math.cos(pr)
    tilt = math.degrees(math.atan2(thick, row))
    with b.at(loc=loc, rot=(0, 0, yaw)):
        for side in (0, 180):
            with b.at(rot=(pitch, 0, side)):
                b.box((length - 0.1, L, 0.3), loc=(0, -L / 2, -0.15), mat='slate', bevel=0, grain=None, color=(0.7, 0.7, 0.72))
                rows = int(math.ceil(L / row))
                for r in range(rows):
                    y0 = -L + r * row
                    x = -length / 2
                    while x < length / 2 - 0.2:
                        w = min(R(b, *segw), length / 2 - x)
                        if length / 2 - (x + w) < 1.2:
                            w = length / 2 - x
                        lo = y0 - 0.2
                        hi = min(lo + row * 1.3, -0.02)
                        if hi - lo > 0.2:
                            cz = thick / 2 + (hi - lo) / 2 * math.sin(math.radians(tilt)) + 0.01
                            b.box((w - 0.06, hi - lo, thick), loc=(x + w / 2, (lo + hi) / 2, cz), rot=(-tilt + R(b, -1, 1), 0, R(b, -0.6, 0.6)),
                                  mat='slate', bevel=0.05, segs=1, grain=1, color=tint((1, 1, 1), R(b, 0.8, 1.0)))
                        x += w
        b.box((length + 0.3, 0.55, 0.45), loc=(0, 0, 0.12), mat='slate', bevel=0.12, segs=1, grain=0, color=(0.82, 0.82, 0.84))


def pennant(b, x, y, z, pole=3.2, ln=4.2, hg=1.5, yaw=0.0, c0=BLUE, c1=GOLD):
    with b.at(loc=(x, y, z), rot=(0, 0, yaw)):
        b.cyl(0.085, pole, mat='metal_dark', segs=6, bevel=0.01, r_top=0.06)
        b.blob(0.16, loc=(0, 0, pole + 0.08), mat='gold', subdiv=1)

        def pos(u, v):
            return (0.06 + u * ln, 0.32 * math.sin(u * 7.5) * u, pole - 0.1 - hg / 2 + (v - 0.5) * hg * (1 - 0.88 * u) - 0.9 * u * u)

        sheet(b, 9, 3, pos, lambda i, j: (c1 if j == 1 else c0), mat='cloth', thick=0.06, uvsize=(ln, hg))


def hanging_banner(b, w, h, emblem=True):
    """Long wall banner. Local frame: wall plane y=0, outward -Y, origin = top centre."""
    b.box((w + 0.5, 0.22, 0.22), loc=(0, -0.2, 0.05), mat='wood_dark', bevel=0.05, segs=1)
    for sx in (-1, 1):
        b.blob(0.2, loc=(sx * (w / 2 + 0.28), -0.2, 0.05), mat='gold', subdiv=1)
    nu, nv = 5, 9

    def pos(u, v):
        vv = 1 - v
        notch = 0.14 * h * (1 - abs(2 * u - 1)) * (1 if v == 0 else 0)
        return ((u - 0.5) * w, -0.2 - 0.12 * math.sin(vv * 2.6) - 0.05 * math.sin(u * math.pi), -vv * h + notch)

    def colr(i, j):
        if i in (0, nu - 1) or j == nv - 1:
            return CREAM
        if j == 0:
            return GOLD
        return BLUE

    sheet(b, nu, nv, pos, colr, mat='cloth', thick=0.08, uvsize=(w, h))
    if emblem:
        s = w * 0.3
        b.prism([(0, -s), (s * 0.72, 0), (0, s), (-s * 0.72, 0)], 0.08, loc=(0, -0.37, -h * 0.42), mat='cloth', color=GOLD, bevel=0)


def build_castle():
    b = Builder('castle', seed=61)
    stone_dark = (0.56, 0.54, 0.5)

    # ---- rocky plinth (sinks ~4.5 m into the hilltop) ---------------------------------------
    def rad(a, z):
        d = Vector((math.cos(a) * 2.4, math.sin(a) * 2.4, z * 0.2))
        return 1 + 0.05 * noise.noise(d) + 0.03 * noise.noise(d * 3.1 + Vector((3, 1, 7))) + 0.012 * noise.noise(d * 9 + Vector((0, 0, z)))

    b.lathe([(38.2, -4.7), (36.6, -3.6), (36.2, -2.4), (34.9, -1.5), (34.4, -0.5), (33.4, 0), (0, 0)], scale=(1, 0.93, 1), mat='stone', segs=64,
            color=(0.4, 0.38, 0.35), color_top=(0.58, 0.56, 0.5), radial=rad)
    for (x, y, rx, ry, rz, yw) in [(-29, -17, 6.5, 5, 6.5, 20), (-13, -24.5, 7, 4, 4.6, 5), (14, -25, 8, 4, 5.4, -8),
                                   (30, -13, 5, 6.5, 7.5, 70), (31.5, 11, 4.5, 7, 6.5, 95), (26, 22, 6.5, 5, 6, 140),
                                   (1, 27, 9, 4, 5.5, 180), (-26, 19, 6, 6, 8, 215), (-31.5, -5, 4.5, 7.5, 6, 270),
                                   (27, -22, 5, 3.5, 5, 30), (-26, -22.5, 4.5, 3.5, 4, 160)]:
        rock(b, (rx, ry, rz), (x, y, -2.6), yaw=yw, dark=0.4, light=0.66, planes=26, lo=0.38, hi=0.82)

    # ---- inner terrace -------------------------------------------------------------------------
    TZ = 5.0
    with b.at(loc=(3, 8, 0)):
        b.box((32, 18, TZ + 1), loc=(0, 0, TZ / 2 - 0.5), mat='stone', bevel=0, grain=None, color=(0.7, 0.68, 0.64), color_top=(0.9, 0.89, 0.86))
        b.box((33.6, 19.6, 3.2), loc=(0, 0, 0.9), mat='stone', bevel=0, grain=None, color=(0.66, 0.64, 0.6), color_top=(0.8, 0.79, 0.76),
              taper=(0.96, 0.93))
        b.box((32.6, 18.6, 0.5), loc=(0, 0, TZ - 0.3), mat='stone', bevel=0.1, segs=1, grain=None, color=(0.95, 0.94, 0.9))
        for loc, yaw, half in faces4(b, 16, 9):
            with b.at(loc=loc, rot=(0, 0, yaw)):
                b.box((2 * half, 0.5, 0.9), loc=(0, 0.2, TZ + 0.4), mat='stone', bevel=0, grain=None, color=(0.88, 0.87, 0.84))
                merlon_row(b, 2 * half, TZ + 0.8, y=0.2)
                for i in range(int(half / 3.2)):
                    xx = -half + 2 + i * (2 * half - 4) / max(1, int(half / 3.2) - 1)
                    b.box((1.3, 1.4, TZ + 0.5), loc=(xx, -0.5, TZ / 2 - 0.4), mat='stone', bevel=0.08, segs=1, grain=None,
                          color=(0.72, 0.7, 0.66), color_top=(0.95, 0.94, 0.9), taper=(0.85, 0.4))

    # ---- curtain walls ---------------------------------------------------------------------------
    T1, T2, T3, T4, T5, T6 = (-23, -18), (23, -18), (25.5, 3), (19, 20), (-18, 21), (-25.5, 4)
    WH = 9.0
    for p0, p1 in [(T1, (-4, -20)), ((4, -20), T2), (T2, T3), (T3, T4), (T4, T5), (T5, T6), (T6, T1)]:
        wall(b, p0, p1, WH)

    # ---- outer towers ----------------------------------------------------------------------------
    F3 = [(6.0, 3, 200, -90), (10.5, 3, 240, -90)]
    round_tower(b, *T1, 4.2, 0, 16.5, 9.5, 'hat', wins=F3 + [(13.2, 6, 360, -90)], bands=(8.6,))
    zt2 = round_tower(b, *T2, 4.8, 0, 19.5, 8.5, 'crenel', wins=F3 + [(15.0, 5, 300, -90)], bands=(8.6, 13.5))
    round_tower(b, *T4, 5.2, 0, 13.5, 7.0, 'crenel', wins=[(6.0, 4, 360, 45), (9.6, 4, 360, 0)], bands=(8.0,))
    zt5 = round_tower(b, *T5, 3.4, 0, 26, 10.5, 'hat', wins=[(7, 3, 360, -90), (13, 3, 360, -30), (18.5, 3, 360, -90), (22.6, 6, 360, -90)],
                      bands=(10.5, 17))
    round_tower(b, *T6, 3.6, 0, 13.5, 7.5, 'hat', wins=[(5.5, 3, 300, -150), (10.0, 5, 360, -90)], bands=(8.2,))
    # square tower (east)
    with b.at(loc=(T3[0], T3[1], 0)):
        hw, h3 = 3.75, 17.5
        cb = (1.0, 0.97, 0.92)
        b.box((2 * hw, 2 * hw, h3 + 3.5), loc=(0, 0, h3 / 2 - 1.75), mat='stone', bevel=0, grain=None, color=tint(cb, 0.72), color_top=tint(cb, 0.95))
        b.box((2 * hw + 1.8, 2 * hw + 1.8, 6.5), loc=(0, 0, -0.25), mat='stone', bevel=0, grain=None, color=tint(cb, 0.7), color_top=tint(cb, 0.85),
              taper=(0.86, 0.86))
        quoins(b, hw, hw, 3.2, h3 - 1.2)
        b.box((2 * hw + 0.5, 2 * hw + 0.5, 0.5), loc=(0, 0, 9.5), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))
        parapet(b, hw, hw, h3, cb=cb)
        for loc, yaw, half in faces4(b, hw, hw):
            with b.at(loc=loc, rot=(0, 0, yaw)):
                for z in (5.5, 11.2):
                    with b.at(loc=(0, 0, z)):
                        lancet(b, 1.0, 2.4)
                for sx in (-1.5, 1.5):
                    with b.at(loc=(sx, 0, 14.0)):
                        lancet(b, 0.7, 1.6)
        b.box((2 * hw - 1.2, 2 * hw - 1.2, 2.4), loc=(0, 0, h3 + 1.2), mat='stone', bevel=0, grain=None, color=tint(cb, 0.86))
        cone_roof(b, 0, 0, h3 + 2.2, (hw - 0.35) * math.sqrt(2), 9.0, r_under=(hw - 0.7) * math.sqrt(2), sq=True)

    # ---- gatehouse -------------------------------------------------------------------------------
    with b.at(loc=(0, -20, 0)):
        gw, gd, gh = 4.6, 3.3, 13.0
        cb = (1.0, 0.97, 0.92)
        b.box((2 * gw, 2 * gd, gh + 3.5), loc=(0, 0, gh / 2 - 1.75), mat='stone', bevel=0, grain=None, color=tint(cb, 0.74), color_top=tint(cb, 0.96))
        b.box((2 * gw + 0.5, 2 * gd + 0.5, 0.5), loc=(0, 0, 9.3), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))
        parapet(b, gw, gd, gh, cb=cb)
        with b.at(scale=(1, 0.62, 1)):
            cone_roof(b, 0, 0, gh + 0.7, (gw - 0.5) * math.sqrt(2), 6.5, r_under=(gw - 1.0) * math.sqrt(2), sq=True, fin=0.8, tilt=0.5)
        with b.at(loc=(0, -gd, 0)):
            dw, dh = 3.8, 3.4
            arch = [(-dw / 2, 0), (dw / 2, 0), (dw / 2, dh)] + [(dw / 2 * math.cos(a), dh + dw / 2 * math.sin(a) * 1.15) for a in
                                                                 [math.pi * i / 8 for i in range(1, 8)]] + [(-dw / 2, dh)]
            b.prism(arch, 0.5, loc=(0, 0.02, 0), mat='wood_dark', bevel=0, color=(0.75, 0.75, 0.75))
            b.box((0.14, 0.2, dh + 1.9), loc=(0, -0.24, (dh + 1.9) / 2), mat='metal_dark', bevel=0, grain=None)
            for z in (1.2, 3.2):
                b.box((dw - 0.2, 0.16, 0.26), loc=(0, -0.26, z), mat='metal_dark', bevel=0, grain=None)
            for sx in (-1, 1):
                for i in range(4):
                    stone(b, (1.0, 0.9, dh / 4 - 0.04), (sx * (dw / 2 + 0.45), -0.2, (i + 0.5) * dh / 4), bev=0.08, segs=1, rj=1.2)
            for i in range(9):
                a = math.pi * (i + 0.5) / 9
                stone(b, (0.95, 0.9, 0.82), ((dw / 2 + 0.45) * math.cos(a), -0.2, dh + (dw / 2 + 0.45) * math.sin(a) * 1.15),
                      rot0=(0, -math.degrees(a) + 90, 0), bev=0.08, segs=1, rj=1.2)
            with b.at(loc=(0, 0, 12.0)):
                hanging_banner(b, 2.3, 4.6)
            for sx in (-1, 1):
                with b.at(loc=(sx * 2.25, 0, 8.6)):
                    lancet(b, 0.7, 1.8)
            mark(b, 'castle_gate', (0, -2.6, 0))
        for sx in (-1, 1):
            round_tower(b, sx * 5.0, -2.6, 2.3, 0, 15.5, 6.5, 'hat', wins=[(6.5, 2, 150, -90), (11.5, 3, 220, -90)], bands=(9.3,), fin=0.8,
                        segs=18, blocks=False)
            pennant(b, sx * 5.0, -2.6, 15.5 + 6.2 + 1.2, pole=2.6, ln=3.4, hg=1.3, yaw=8 * sx, c0=GOLD if sx > 0 else BLUE,
                    c1=BLUE if sx > 0 else GOLD)

    # ---- keep ------------------------------------------------------------------------------------
    KX, KY, KW, KT = -6.0, 9.0, 5.5, 27.0
    with b.at(loc=(KX, KY, 0)):
        cb = (1.0, 0.98, 0.94)
        b.box((2 * KW, 2 * KW, KT - TZ + 1), loc=(0, 0, (KT + TZ) / 2 - 0.5), mat='stone', bevel=0, grain=None, color=tint(cb, 0.72),
              color_top=tint(cb, 0.97))
        b.box((2 * KW + 1.6, 2 * KW + 1.6, 4.5), loc=(0, 0, TZ + 1.6), mat='stone', bevel=0, grain=None, color=tint(cb, 0.7), color_top=tint(cb, 0.84),
              taper=(0.88, 0.88))
        quoins(b, KW, KW, TZ + 4.0, KT - 1.2)
        for z in (13.2, 20.2):
            b.box((2 * KW + 0.55, 2 * KW + 0.55, 0.5), loc=(0, 0, z), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))
        parapet(b, KW, KW, KT, over=0.8, cb=cb)
        for loc, yaw, half in faces4(b, KW, KW):
            with b.at(loc=loc, rot=(0, 0, yaw)):
                for z, xs, w, h in ((9.5, (-2.2, 2.2), 0.9, 2.2), (15.0, (-2.6, 0, 2.6), 1.0, 2.8), (21.6, (-2.2, 0, 2.2), 0.9, 2.4)):
                    for xx in xs:
                        with b.at(loc=(xx, 0, z)):
                            lancet(b, w, h)
        with b.at(loc=(0, -KW, 20.0)):
            for sx in (-1, 1):
                with b.at(loc=(sx * 4.0, 0, 0)):
                    hanging_banner(b, 1.5, 6.5, emblem=False)
        # corner bartizans
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (KW + 0.2), sy * (KW + 0.2)
                b.lathe([(0, KT - 6.0), (0.5, KT - 5.6), (1.75, KT - 3.2), (1.75, KT + 2.6), (0, KT + 2.6)], loc=(x, y, 0), mat='stone',
                        segs=14, color=tint(cb, 0.78), color_top=tint(cb, 0.98))
                b.lathe([(1.7, KT - 0.25), (1.98, KT - 0.15), (1.98, KT + 0.15), (1.7, KT + 0.25)], loc=(x, y, 0), mat='stone', segs=14)
                ring_windows(b, x, y, 1.75, KT + 0.6, 3, a0=math.degrees(math.atan2(sy, sx)), spread=250, w=0.55, h=1.2)
                cone_roof(b, x, y, KT + 2.45, 2.4, 5.2, r_under=1.6, segs=14, fin=0.6)
        # central spire
        b.lathe([(4.4, KT + 0.3), (4.4, KT + 3.0), (0, KT + 3.0)], mat='stone', segs=8, rot=(0, 0, 22.5), color=tint(cb, 0.88))
        ring_windows(b, 0, 0, 4.4 * math.cos(math.pi / 8), KT + 0.9, 8, a0=-90, spread=360, w=0.7, h=1.1)
        cone_roof(b, 0, 0, KT + 2.7, 5.4, 11.0, r_under=4.3, segs=8, fin=1.1, tilt=0.6)
        pennant(b, 0, 0, KT + 2.7 + 11.0 + 1.5, pole=2.6, ln=5.0, hg=1.7, yaw=6)

    # ---- great hall ------------------------------------------------------------------------------
    HXc, HYc, HL, HW, HE = 7.5, 9.0, 16.0, 4.5, 15.0
    with b.at(loc=(HXc, HYc, 0)):
        cb = (0.96, 0.97, 1.0)
        b.box((HL, 2 * HW, HE - TZ + 1), loc=(0, 0, (HE + TZ) / 2 - 0.5), mat='stone', bevel=0, grain=None, color=tint(cb, 0.74),
              color_top=tint(cb, 0.96))
        b.box((HL + 0.4, 2 * HW + 0.5, 0.5), loc=(0, 0, HE - 0.3), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))
        pitch = 58.0
        rise = (HW + 0.5) * math.tan(math.radians(pitch))
        slab_roof(b, (0, 0, HE + rise - 0.1), HL + 0.2, HW + 0.6, pitch)
        # crow-stepped east gable
        gx = HL / 2
        nst = 7
        for i in range(nst):
            wdt = 2 * (HW + 0.6) * (1 - i / nst)
            b.box((1.0, wdt, rise / nst + 0.9), loc=(gx + 0.1, 0, HE + (i + 0.5) * rise / nst + 0.45), mat='stone', bevel=0.08, segs=1,
                  grain=None, color=tint(b.rng.choice(HUES), 0.92))
        with b.at(loc=(gx + 0.6, 0, 0), rot=(0, 0, 90)):
            for xx in (-2, 2):
                with b.at(loc=(xx, 0, 8.5)):
                    lancet(b, 1.0, 3.0)
            with b.at(loc=(0, 0, 16.5)):
                lancet(b, 1.1, 2.4)
        for sy, yaw in ((-1, 0), (1, 180)):
            with b.at(loc=(0, sy * HW, 0), rot=(0, 0, yaw)):
                for i in range(5):
                    xx = (-5.6 + i * 2.8) * (1 if sy < 0 else -1)
                    with b.at(loc=(xx, 0, 8.6)):
                        lancet(b, 1.05, 3.6)
                    if i < 4:
                        b.box((0.9, 1.1, HE - TZ - 1), loc=(xx + 1.4 * (1 if sy < 0 else -1), -0.4, (HE + TZ) / 2 - 0.6), mat='stone', bevel=0.08,
                              segs=1, grain=None, color=tint(cb, 0.8), color_top=tint(cb, 0.98), taper=(0.9, 0.5))
        # dormers on both slopes
        for sy in (-1, 1):
            for xx in (-4.4, 0.0, 4.4):
                dz = HE + 2.6
                dy = sy * (HW + 0.5 - 2.6 / math.tan(math.radians(pitch)) + 0.5)
                b.box((1.9, 2.0, 2.4), loc=(xx, dy + sy * -0.4, dz + 0.5), mat='stone', bevel=0, grain=None, color=tint(cb, 0.92))
                with b.at(loc=(xx, dy + sy * 0.6, dz - 0.3), rot=(0, 0, 0 if sy < 0 else 180)):
                    lancet(b, 0.8, 1.2)
                cone_roof(b, xx, dy - sy * 0.4, dz + 1.6, 1.75, 2.6, sq=True, fin=0.0, lip=0.08, tilt=0)
        # chimneys
        for xx, yy, zz in ((-3.0, 1.6, 0), (5.2, -1.4, 0)):
            b.box((1.3, 1.3, 7.0), loc=(xx, yy, HE + rise - 2.0), mat='stone', bevel=0.08, segs=1, grain=None, color=tint(cb, 0.86))
            b.box((1.7, 1.7, 0.45), loc=(xx, yy, HE + rise + 1.6), mat='stone', bevel=0.1, segs=1, grain=None, color=tint(cb, 0.98))

    # ---- inner round towers ----------------------------------------------------------------------
    zts = round_tower(b, 16.5, 14.5, 2.8, TZ, 23, 8.5, 'hat', wins=[(6, 2, 200, -90), (11.5, 3, 300, -60), (16, 2, 200, -90), (19.6, 6, 360, -90)],
                      bands=(11.5,), base=1.0, segs=20, blocks=False)
    round_tower(b, -13, -1, 2.5, 0, 14.5, 6.0, 'hat', wins=[(7.5, 3, 240, -90), (11.2, 5, 360, -90)], bands=(5.2,), segs=18, fin=0.8, blocks=False)
    round_tower(b, 19, -1, 2.2, 0, 10.5, 4.5, 'crenel', wins=[(6.8, 3, 240, -60)], bands=(5.2,), segs=18, fin=0.7, blocks=False)

    # ---- pennants on the tall spires -------------------------------------------------------------
    pennant(b, T5[0], T5[1], zt5 - 0.25 + 10.5 + 1.3, pole=2.4, ln=4.0, hg=1.5, yaw=10, c0=GOLD, c1=BLUE)
    pennant(b, 16.5, 14.5, zts - 0.25 + 8.5 + 1.3, pole=2.4, ln=3.8, hg=1.4, yaw=4)
    pennant(b, T2[0], T2[1], zt2 + 2.3 + 8.5 + 1.3, pole=2.4, ln=3.8, hg=1.4, yaw=7, c0=GOLD, c1=BLUE)
    pennant(b, T1[0], T1[1], 16.5 - 0.25 + 9.5 + 1.3, pole=2.2, ln=3.6, hg=1.3, yaw=9)
    return b.build(sharp_angle=32)


# ============================================================================================
# NOTICE BOARD
# ============================================================================================
def note(b, w, h, loc, rot=(0, 0, 0), curl=0.012, flick=0.03, lines=5, header=None, seal=False, tone=(1, 1, 1), pin='gold'):
    """Paper pinned at its top centre. Local frame: board face y=0, outward -Y, origin = pin."""
    def lift(v):
        return curl * (1 - v) ** 2

    def pos(u, v):
        fl = flick * max(0.0, (u - 0.35) / 0.65) ** 2 * max(0.0, (0.5 - v) / 0.5) ** 2
        return ((u - 0.5) * w, -0.004 - lift(v) - fl - 0.002 * math.sin(u * 5 + v * 3), (v - 1) * h + 0.02)

    with b.at(loc=loc, rot=rot):
        k = R(b, 0.9, 1.0)
        sheet(b, 5, 6, pos, lambda i, j: tint(tone, k), mat='parchment', thick=0.003, uvsize=(w, h), back=0.8)
        z = -0.035
        if header:
            b.box((w * 0.84, 0.002, 0.03), loc=(0, -0.0058 - lift(1 + z / h), z - 0.005), mat='paint', color=header, bevel=0)
            z -= 0.045
        nlines = lines
        step = min(0.03, (h * 0.78 + z) / max(nlines, 1))
        for i in range(nlines):
            zz = z - i * step
            v = 1 + (zz - 0.02) / h
            if v < 0.3:
                break
            y = -0.0058 - lift(v)
            x = -w * 0.4
            last = (i == nlines - 1)
            end = w * (0.05 if last else 0.4)
            while x < end - 0.02:
                lw = min(R(b, 0.03, 0.09), end - x)
                b.box((lw, 0.002, 0.007), loc=(x + lw / 2, y, zz), mat='paint', color=INK, bevel=0)
                x += lw + 0.012
        if seal:
            v = 0.12
            b.lathe([(0, 0), (0.024, 0), (0.026, 0.004), (0.016, 0.008), (0, 0.009)], loc=(-w * 0.22, -0.006 - lift(v), -h * 0.86),
                    rot=(90, 0, R(b, 0, 60)), mat='paint', segs=10, color=WAX, radial=lambda a, zz: 1 + 0.1 * math.sin(5 * a))
        pm = 'gold' if pin == 'gold' else 'metal_dark'
        b.lathe([(0, 0), (0.011, 0), (0.013, 0.004), (0.006, 0.009), (0, 0.01)], loc=(R(b, -0.01, 0.01), -0.006, 0.0), rot=(90, 0, 0),
                mat=pm, segs=8)


def build_notice_board():
    b = Builder('notice_board', seed=62)
    PX = 0.95
    # stones + grass at the post feet
    for sx in (-1, 1):
        for i in range(4):
            a = i * 2 * math.pi / 4 + 0.5 + sx
            stone(b, (R(b, 0.24, 0.33), R(b, 0.2, 0.27), R(b, 0.16, 0.26)), (sx * PX + 0.19 * math.cos(a), 0.19 * math.sin(a), 0.06),
                  rot0=(0, 0, math.degrees(a)), bev=0.06, rj=8)
        tuft(b, sx * PX + 0.05, -0.3, n=6)
        tuft(b, sx * (PX + 0.3), 0.1, n=5)
    tuft(b, 0.2, 0.05, n=5, h=(0.1, 0.22))
    tuft(b, -0.45, 0.02, n=4, h=(0.1, 0.2))
    # posts
    for sx in (-1, 1):
        wood(b, (0.18, 0.18, 2.18), loc=(sx * PX, 0, 0.97), mat='wood_dark', bevel=0.024, segs=2, taper=(0.9, 0.9), rot=(0, sx * 0.6, 0))
        wood(b, (0.24, 0.24, 0.07), loc=(sx * PX, 0, 0.5), mat='wood_dark', bevel=0.02, segs=2)   # chamfer collar
        wood(b, (0.13, 1.0, 0.12), loc=(sx * PX, 0, 2.03), mat='wood_dark', bevel=0.02, segs=2, rj=0.5)
        for sy in (-1, 1):
            wood(b, (0.085, 0.5, 0.085), loc=(sx * PX, sy * 0.25, 1.82), rot=(sy * 48, 0, 0), mat='wood_dark', bevel=0.015, segs=2)
        b.prism([(-0.44, 2.08), (0.44, 2.08), (0, 2.08 + 0.44 * 0.7265 - 0.01)], 0.05, loc=(sx * PX, 0, 0), rot=(0, 0, 90),
                mat='wood_plank', bevel=0.01, segs=1, jitter=0.08)
    wood(b, (2.3, 0.1, 0.11), loc=(0, 0, 2.33), mat='wood_dark', bevel=0.018, segs=2)
    gable_roof(b, (0, 0, 2.475), 2.46, 0.52, 36, row_h=0.2, sw=(0.19, 0.3), thick=0.032, cap=0.62)

    # the board: frame + planks (dark backing so no daylight shows through the plank joints)
    BZ0, BZ1 = 0.74, 1.62
    b.box((2 * PX - 0.22, 0.02, BZ1 - BZ0 - 0.04), loc=(0, 0.028, (BZ0 + BZ1) / 2), mat='wood_dark', bevel=0, color=(0.6, 0.6, 0.6))
    n = 8
    pw = (2 * (PX - 0.1)) / n
    for i in range(n):
        wood(b, (pw - 0.008, 0.04, BZ1 - BZ0 + R(b, -0.015, 0.015)), loc=(-PX + 0.1 + (i + 0.5) * pw, 0.005 + R(b, -0.004, 0.004), (BZ0 + BZ1) / 2),
             mat='wood_plank', bevel=0.01, segs=1, jitter=0.13, rj=0.35, grain=2)
    wood(b, (2 * PX - 0.14, 0.085, 0.1), loc=(0, -0.012, BZ1 + 0.03), mat='wood_dark', bevel=0.016, segs=2, rj=0.3)
    wood(b, (2 * PX - 0.14, 0.085, 0.1), loc=(0, -0.012, BZ0 - 0.03), mat='wood_dark', bevel=0.016, segs=2, rj=0.3)
    for sx in (-1, 1):
        wood(b, (0.06, 0.07, BZ1 - BZ0 - 0.04), loc=(sx * (PX - 0.125), -0.012, (BZ0 + BZ1) / 2), mat='wood_dark', bevel=0.012, segs=2)
        for z in (BZ0 - 0.03, BZ1 + 0.03):   # iron corner straps + studs
            b.box((0.16, 0.012, 0.06), loc=(sx * (PX - 0.2), -0.058, z), mat='metal_dark', bevel=0.004, segs=1)
            for dx in (0.15, 0.24):
                b.cyl(0.011, 0.008, loc=(sx * (PX - dx), -0.064, z), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
    # header plaque (royal blue with gold line + studs) and the crest
    HZ = BZ1 + 0.03
    b.box((1.2, 0.03, 0.15), loc=(0, -0.062, HZ + 0.005), mat='paint', color=BLUE, bevel=0.01, segs=2, jitter=0.05)
    for z in (-0.05, 0.06):
        b.box((1.14, 0.008, 0.012), loc=(0, -0.079, HZ + z), mat='gold', bevel=0.003, segs=1)
    for sx in (-1, 1):
        b.prism([(0, -0.1), (0.07, 0), (0, 0.1), (-0.07, 0)], 0.03, loc=(sx * 0.63, -0.062, HZ + 0.005), mat='gold', bevel=0.006, segs=1)
        b.box((0.36, 0.008, 0.01), loc=(sx * 0.4, -0.079, HZ + 0.005), mat='gold', bevel=0.003, segs=1)
        for i in range(5):   # gold laurel sprays either side of the shield
            for s2 in (-1, 1):
                b.lathe([(0, 0), (0.017, 0.03), (0, 0.075)], loc=(sx * (0.235 + 0.075 * i), -0.082, HZ + 0.005 + s2 * 0.006),
                        rot=(0, sx * (90 - s2 * 38), 0), scale=(1, 0.45, 1), mat='gold', segs=6)
    with b.at(loc=(0, -0.078, HZ + 0.075)):
        crest(b, 0.86)

    # notes -------------------------------------------------------------------------------------
    y0 = -0.017
    P1, P2, P3 = (1.0, 0.98, 0.93), (0.96, 0.9, 0.78), (1.0, 0.95, 0.84)
    # the big royal decree in the middle: blue header band, wax seal, ribbon tails
    note(b, 0.34, 0.5, (0.02, y0, 1.46), rot=(0, 1.5, 0), lines=9, header=BLUE, seal=True, tone=P1, curl=0.01, flick=0.035)
    for dx, rz in ((-0.014, -13), (0.014, 11)):
        b.box((0.022, 0.003, 0.11), loc=(0.02 - 0.34 * 0.22 + dx * 1.6, y0 - 0.016, 1.46 - 0.5 * 0.86 - 0.05), rot=(0, rz, 0), mat='cloth',
              color=BLUE, bevel=0)
    note(b, 0.2, 0.27, (-0.5, y0, 1.50), rot=(0, -4, 0), lines=6, tone=P2, flick=0.02)
    note(b, 0.24, 0.2, (-0.56, y0 - 0.006, 1.16), rot=(0, 5, 0), lines=4, tone=P3, flick=0.03, pin='iron', seal=True)
    note(b, 0.17, 0.22, (-0.27, y0, 1.08), rot=(0, -7, 0), lines=5, tone=P1, flick=0.012, pin='iron')
    note(b, 0.22, 0.3, (0.44, y0, 1.52), rot=(0, 3, 0), lines=7, header=GOLD, tone=P3, flick=0.045)
    note(b, 0.18, 0.2, (0.62, y0 - 0.006, 1.17), rot=(0, -6, 0), lines=4, tone=P2, flick=0.02, pin='iron')
    note(b, 0.15, 0.17, (0.37, y0, 1.04), rot=(0, 9, 0), lines=3, tone=P1, flick=0.03, seal=True)
    note(b, 0.13, 0.1, (-0.33, y0 - 0.004, 1.53), rot=(0, 12, 0), lines=2, tone=P3, flick=0.01, pin='iron')
    # a torn-off scrap still under its nail
    note(b, 0.09, 0.06, (0.7, y0, 1.50), rot=(0, -15, 0), lines=1, tone=P2, flick=0.02, pin='iron')

    # little shelf with an inkpot, quill and a rolled scroll -------------------------------------
    SZ = 0.63
    wood(b, (1.3, 0.17, 0.035), loc=(0, -0.1, SZ), mat='wood_plank', bevel=0.012, segs=2, rj=0.4)
    for sx in (-1, 1):
        b.prism([(0, 0), (0.13, 0), (0, -0.15)], 0.035, loc=(sx * 0.5, -0.03, SZ - 0.018), rot=(0, 0, 90), mat='wood_dark', bevel=0.008, segs=1)
    with b.at(loc=(0.42, -0.11, SZ + 0.018)):
        b.lathe([(0, 0), (0.034, 0), (0.04, 0.012), (0.038, 0.04), (0.02, 0.052), (0.02, 0.062), (0.026, 0.066), (0.014, 0.066), (0.012, 0.03),
                 (0, 0.03)], mat='metal_dark', segs=12)
        with b.at(loc=(0, 0, 0.03), rot=(0, 24, 30)):
            b.tube([(0, 0, 0), (0, 0, 0.26)], [0.004, 0.002], mat='parchment', segs=5)
            for s in (-1, 1):
                b.leaf(0.2, 0.05, loc=(0, 0, 0.07), rot=(0, 0, 90 * s), mat='cloth', bend=6, fold=28 * s, segs=4, color=CREAM,
                       shape=lambda u: 0.25 + 0.75 * math.sin(math.pi * min(1, u * 1.15)) ** 0.6 if u < 0.87 else 0.25)
    with b.at(loc=(-0.3, -0.1, SZ + 0.018 + 0.03), rot=(0, 0, 12)):
        n0 = nfaces(b)
        b.lathe([(0, -0.14), (0.026, -0.14), (0.03, -0.135), (0.03, 0.135), (0.026, 0.14), (0, 0.14)], rot=(0, 90, 0), mat='parchment', segs=10,
                color=(0.98, 0.94, 0.86))
        b.lathe([(0.029, -0.014), (0.033, -0.012), (0.033, 0.012), (0.029, 0.014)], rot=(0, 90, 0), mat='cloth', segs=10, color=BLUE)
        b.lathe([(0, 0), (0.016, 0), (0.017, 0.004), (0, 0.007)], loc=(0, -0.031, 0), rot=(90, 0, 0), mat='paint', segs=8, color=WAX)

    # lantern on an iron scroll bracket, front of the left post --------------------------------
    lx = -PX
    b.tube([(lx, -0.09, 1.5), (lx, -0.2, 1.56), (lx, -0.31, 1.57), (lx, -0.37, 1.53), (lx, -0.36, 1.49)], 0.011, mat='metal_dark', segs=8)
    b.tube([(lx, -0.09, 1.33), (lx, -0.16, 1.4), (lx, -0.24, 1.53)], 0.008, mat='metal_dark', segs=8)
    b.box((0.05, 0.012, 0.28), loc=(lx, -0.094, 1.42), mat='metal_dark', bevel=0.004, segs=1)
    with b.at(loc=(lx, -0.36, 1.492)):
        lc = lantern(b, 0.9)
        mark(b, 'board_lantern_light', lc)
    mark(b, 'board_front', (0, -1.2, 0))
    return b.build(sharp_angle=50)


# ============================================================================================
# WAGON
# ============================================================================================
def barrel(b, s=1.0):
    n = 14
    segs = n * 2
    tones = [1 + R(b, -0.13, 0.13) for _ in range(n)]
    H = 0.82 * s

    def rz(z):
        return (0.27 + 0.068 * math.sin(math.pi * max(0, min(1, z / H)))) * s

    def col(co):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        k = tones[int(a / (2 * math.pi) * n + 0.25) % n]
        return (k, k, k)

    def rad(a, z):
        return 0.972 if round(a / (2 * math.pi) * segs) % 2 == 0 else 1.0

    prof = [(0, 0.03 * s), (0.225 * s, 0.03 * s), (0.232 * s, 0.0)]
    for i in range(9):
        z = H * i / 8
        prof.append((rz(z), z))
    prof += [(0.232 * s, H), (0.225 * s, H - 0.04 * s), (0, H - 0.04 * s)]
    n0 = nfaces(b)
    b.lathe(prof, mat='wood_plank', segs=segs, color=col, radial=rad)
    swap_uv(b, n0)
    for z in (0.09, 0.25, 0.57, 0.73):
        z *= s
        r0, r1 = rz(z - 0.024 * s), rz(z + 0.024 * s)
        b.lathe([(r0 - 0.004, z - 0.026 * s), (r0 + 0.007, z - 0.024 * s), (r1 + 0.007, z + 0.024 * s), (r1 - 0.004, z + 0.026 * s)],
                mat='metal', segs=segs)
    b.cyl(0.02 * s, 0.03 * s, loc=(0.1 * s, -0.05 * s, H - 0.045 * s), mat='wood_dark', segs=8, bevel=0.005)


def crate(b, S=0.6, open_top=False):
    b.box((S - 0.07, S - 0.07, S - 0.09), loc=(0, 0, S / 2 - 0.02), mat='wood_dark', bevel=0.005, segs=1, grain=None, color=(0.55, 0.55, 0.55))
    hgt = S / 3 - 0.03
    for k in range(4):
        with b.at(rot=(0, 0, k * 90)):
            for i in range(3):
                z = S / 6 + i * S / 3
                wood(b, (S - 0.03 + R(b, -0.01, 0.01), 0.026, hgt), loc=(R(b, -0.006, 0.006), -S / 2 + 0.02, z), mat='wood_light', bevel=0.009,
                     segs=1, jitter=0.12, rj=0.7)
            for sx in (-1, 1):
                wood(b, (0.07, 0.03, S - 0.01), loc=(sx * (S / 2 - 0.042), -S / 2 - 0.006, S / 2), mat='wood_light', bevel=0.009, segs=1, jitter=0.1)
            if k % 2 == 0:
                L = math.hypot(S - 0.16, S - 0.03)
                wood(b, (L, 0.024, 0.065), loc=(0, -S / 2 - 0.008, S / 2), rot=(0, -math.degrees(math.atan2(S - 0.03, S - 0.16)), 0),
                     mat='wood_light', bevel=0.009, segs=1, jitter=0.1)
    if not open_top:
        for i in range(4):
            y = -S / 2 + 0.085 + i * (S - 0.17) / 3
            wood(b, (S - 0.02, (S - 0.17) / 3 - 0.012, 0.026), loc=(0, y, S - 0.004), mat='wood_light', bevel=0.009, segs=1, jitter=0.12, rj=0.8)


def sack(b, s=1.0, c=None):
    c = c or srgb(176, 150, 105)
    ph = R(b, 0, 6)

    def rad(a, z):
        return 1 + 0.07 * math.sin(3 * a + z * 6 + ph) + 0.04 * math.sin(5 * a + 1.3) + (0.1 * math.cos(a) if z < 0.25 * s else 0)

    P = [(0, 0), (0.17, 0), (0.235, 0.035), (0.255, 0.13), (0.24, 0.26), (0.19, 0.36), (0.1, 0.43), (0.06, 0.455), (0.052, 0.48), (0.075, 0.515),
         (0.115, 0.56), (0.11, 0.565), (0.05, 0.53), (0, 0.52)]
    b.lathe([(r * s, z * s) for r, z in P], mat='cloth', segs=16, color=tint(c, 0.8), color_top=tint(c, 1.06), radial=rad, rot=(4, -5, 0))
    b.lathe([(0.05 * s, 0.458 * s), (0.068 * s, 0.462 * s), (0.07 * s, 0.482 * s), (0.05 * s, 0.488 * s)], mat='rope', segs=10, rot=(4, -5, 0))


def build_wheel(name, r, side, seed):
    """Wheel with its origin at the hub, spinning about local X. side=+1: outer face toward +X."""
    b = Builder(name, seed=seed)
    ri, ro, w = r - 0.095, r - 0.012, 0.036
    nf = 6
    tones = [1 + R(b, -0.12, 0.12) for _ in range(nf)]
    segs = 36

    def col(co):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        k = tones[int(a / (2 * math.pi) * nf + 0.1) % nf]
        return (k, k, k)

    with b.at(rot=(0, 90 * side, 0)):
        n0 = nfaces(b)
        b.lathe([(ri, -w), (ro, -w + 0.004), (ro, w - 0.004), (ri, w), (ri, -w)], mat='wood_plank', segs=segs, color=col)
        swap_uv(b, n0)
        b.lathe([(ro - 0.004, -w - 0.005), (ro + 0.013, -w - 0.003), (ro + 0.013, w + 0.003), (ro - 0.004, w + 0.005)], mat='metal_dark',
                segs=segs)
        for i in range(nf):   # felloe joint plates
            a = 2 * math.pi * (i + 0.02) / nf
            b.box((0.012, 0.07, 0.085), loc=((ri + ro) / 2 * math.cos(a), (ri + ro) / 2 * math.sin(a), 0), rot=(0, 0, math.degrees(a) + 90 - 90),
                  mat='metal_dark', bevel=0.003, segs=1, taper=(1, 1))
        b.lathe([(0, -0.1), (0.05, -0.1), (0.062, -0.085), (0.088, -0.045), (0.095, 0.0), (0.09, 0.05), (0.066, 0.1), (0.055, 0.135), (0, 0.135)],
                mat='wood_dark', segs=14)
        for z in (-0.075, 0.085):
            b.lathe([(0.064, z - 0.014), (0.076, z - 0.012), (0.076, z + 0.012), (0.064, z + 0.014)], mat='metal_dark', segs=14)
        b.lathe([(0.03, 0.13), (0.046, 0.132), (0.044, 0.15), (0.03, 0.166), (0.012, 0.176), (0, 0.178)], mat='gold', segs=12)
        ns = 12
        for i in range(ns):
            a = 360.0 * (i + 0.5) / ns
            with b.at(rot=(0, 0, a)):
                ln = ri - 0.07 + 0.012
                b.box((0.036, 0.03, ln), loc=(0.075 + ln / 2, 0, 0.004), rot=(0, 90, 0), mat='wood_light', bevel=0.009, segs=1, jitter=0.12,
                      taper=(0.8, 0.9))
    return b.build(sharp_angle=40)


def build_wagon():
    b = Builder('wagon', seed=63)
    FZ = 0.92
    LB, WB = 2.9, 1.3
    YF, YB, RF, RB, WX = -0.98, 0.94, 0.46, 0.58, 0.88
    FL = 7.0   # side flare in degrees
    # ---- undercarriage -------------------------------------------------------------------------
    for y, r in ((YF, RF), (YB, RB)):
        wood(b, (2 * WX - 0.2, 0.11, 0.11), loc=(0, y, r), mat='wood_dark', bevel=0.02, segs=2)
        for sx in (-1, 1):
            b.cyl(0.028, 0.28, loc=(sx * (WX - 0.14), y, r), rot=(0, sx * 90, 0), mat='metal_dark', segs=8, bevel=0.004)
        top = r + 0.055
        hgt = FZ - 0.215 - top
        if y == YB:
            wood(b, (1.2, 0.13, hgt), loc=(0, y, top + hgt / 2), mat='wood_dark', bevel=0.016, segs=2)
        else:
            wood(b, (1.2, 0.13, 0.08), loc=(0, y, top + 0.04), mat='wood_dark', bevel=0.016, segs=2)
            b.cyl(0.3, 0.03, loc=(0, y, top + 0.08), mat='metal_dark', segs=20, bevel=0.006)
            wood(b, (1.2, 0.13, hgt - 0.11), loc=(0, y, top + 0.11 + (hgt - 0.11) / 2), mat='wood_dark', bevel=0.016, segs=2)
    # reach pole
    ln = math.hypot(YB - YF, RB - RF)
    wood(b, (0.075, ln, 0.08), loc=(0, (YF + YB) / 2, (RF + RB) / 2 + 0.06), rot=(math.degrees(math.atan2(RB - RF, YB - YF)), 0, 0),
         mat='wood_dark', bevel=0.014, segs=2)
    # tongue (hitch pole), hounds and singletree
    ty, tz = -2.72, 0.7
    ln = math.hypot(ty - YF, tz - RF)
    ang = math.degrees(math.atan2(RF - tz, YF - ty))
    wood(b, (0.075, ln, 0.085), loc=(0, (YF + ty) / 2, (RF + tz) / 2), rot=(ang, 0, 0), mat='wood_dark', bevel=0.016, segs=2)
    for sx in (-1, 1):
        wood(b, (0.05, 0.78, 0.055), loc=(sx * 0.2, YF - 0.33, RF + 0.035), rot=(ang, 0, sx * 31), mat='wood_dark', bevel=0.012, segs=1)
    sy_ = -1.72
    sz_ = RF + (tz - RF) * (sy_ - YF) / (ty - YF) + 0.075
    n0 = nfaces(b)
    b.tube([(-0.5, sy_, sz_), (0, sy_ + 0.012, sz_ + 0.006), (0.5, sy_, sz_)], [0.026, 0.034, 0.026], mat='wood_light', segs=8)
    swap_uv(b, n0)
    b.box((0.1, 0.09, 0.016), loc=(0, sy_, sz_ + 0.03), mat='metal_dark', bevel=0.004, segs=1)
    for sx in (-1, 1):
        ring = [(sx * 0.47 + 0.03 * math.cos(a), sy_ - 0.02 - 0.035 + 0.035 * math.cos(a) * 0, sz_ + 0.03 * math.sin(a) - 0.05) for a in
                [i * 2 * math.pi / 10 for i in range(11)]]
        b.tube(ring, 0.006, mat='metal_dark', segs=6, caps=False)
        b.lathe([(0.028, -0.02), (0.033, -0.018), (0.033, 0.018), (0.028, 0.02)], loc=(sx * 0.44, sy_, sz_), rot=(0, 90, 0), mat='metal_dark', segs=8)
    with b.at(loc=(0, ty, tz), rot=(ang + 90, 0, 0)):
        b.lathe([(0.05, -0.1), (0.058, -0.095), (0.058, 0.0), (0.045, 0.03), (0.03, 0.05), (0, 0.058)], mat='gold', segs=10)
    ring = [(0.045 * math.cos(a), ty - 0.07, tz - 0.07 + 0.045 * math.sin(a)) for a in [i * 2 * math.pi / 12 for i in range(13)]]
    b.tube(ring, 0.008, mat='metal_dark', segs=6, caps=False)

    # ---- bed -------------------------------------------------------------------------------------
    for sx in (-1, 1):
        wood(b, (0.09, LB - 0.08, 0.11), loc=(sx * 0.42, 0, FZ - 0.16), mat='wood_dark', bevel=0.016, segs=2)
    BY = (-1.3, -0.45, 0.4, 1.3)
    for y in BY:
        wood(b, (WB + 0.24, 0.07, 0.07), loc=(0, y, FZ - 0.07), mat='wood_dark', bevel=0.014, segs=2, rj=0.3)
    npl = 6
    for i in range(npl):
        wood(b, (WB / npl - 0.008, LB + R(b, -0.03, 0.03), 0.035), loc=(-WB / 2 + (i + 0.5) * WB / npl, R(b, -0.01, 0.01), FZ - 0.0175),
             bevel=0.01, segs=1, jitter=0.14, rj=0.25)
    for sx in (-1, 1):
        with b.at(loc=(sx * WB / 2, 0, FZ), rot=(0, sx * FL, 0)):
            for z, ln_ in ((0.105, LB), (0.315, LB + 0.02)):
                b.box((0.036, ln_ + R(b, -0.01, 0.01), 0.2), loc=(R(b, -0.003, 0.003), 0, z), rot=(0, 0, R(b, -0.2, 0.2)), mat='paint',
                      color=BLUE, jitter=0.1, bevel=0.012, segs=2, grain=1)
            wood(b, (0.055, LB + 0.1, 0.05), loc=(0.0, 0, 0.44), mat='wood_dark', bevel=0.014, segs=2)
            b.box((0.01, LB - 0.14, 0.022), loc=(sx * 0.022, 0, 0.365), mat='gold', bevel=0.003, segs=1)
            b.box((0.01, LB - 0.14, 0.022), loc=(sx * 0.022, 0, 0.045), mat='gold', bevel=0.003, segs=1)
            for y in BY:
                wood(b, (0.05, 0.065, 0.66), loc=(sx * 0.045, y, 0.2), mat='wood_dark', bevel=0.014, segs=2, rj=0.4)
                b.cyl(0.012, 0.008, loc=(sx * 0.07, y, 0.31), rot=(0, sx * 90, 0), mat='metal_dark', segs=6, bevel=0.002)
                b.cyl(0.012, 0.008, loc=(sx * 0.07, y, 0.1), rot=(0, sx * 90, 0), mat='metal_dark', segs=6, bevel=0.002)
            with b.at(loc=(sx * 0.02, 1.04, 0.19), rot=(0, 0, sx * 90)):
                crest(b, 0.62, wheat=False, field=CREAM, band=GOLD, diamond=BLUE)
    fl = math.tan(math.radians(FL))
    for y, hgt, mat_, c in ((-LB / 2 + 0.02, 0.44, 'paint', BLUE), (LB / 2 - 0.02, 0.4, 'wood_plank', (1, 1, 1))):
        sgn = -1 if y < 0 else 1
        with b.at(loc=(0, y, FZ), rot=(sgn * -5 if y > 0 else 0, 0, 0)):
            for k in range(2):
                z0, z1 = k * hgt / 2 + 0.004, (k + 1) * hgt / 2 - 0.004
                b.prism([(-WB / 2 - z0 * fl, z0), (WB / 2 + z0 * fl, z0), (WB / 2 + z1 * fl, z1), (-WB / 2 - z1 * fl, z1)], 0.036, mat=mat_,
                        color=c, jitter=0.1, bevel=0.01, segs=2, grain=0)
            for sx in (-0.38, 0.38):
                wood(b, (0.07, 0.03, hgt - 0.02), loc=(sx, sgn * 0.03, hgt / 2), mat='wood_dark', bevel=0.01, segs=1)
                if y > 0:   # tailgate strap hinges
                    b.box((0.045, 0.012, hgt * 0.8), loc=(sx, sgn * 0.05, hgt * 0.42), mat='metal_dark', bevel=0.004, segs=1)
            if y < 0:
                b.box((WB - 0.1, 0.01, 0.022), loc=(0, -0.022, hgt - 0.06), mat='gold', bevel=0.003, segs=1)
    # tailgate chains
    for sx in (-1, 1):
        b.tube([(sx * 0.55, LB / 2 - 0.34, FZ + 0.42), (sx * 0.56, LB / 2 - 0.18, FZ + 0.31), (sx * 0.5, LB / 2 + 0.005, FZ + 0.36)], 0.007,
               mat='metal_dark', segs=6)
    # footboard + seat with a blue cushion
    wood(b, (WB - 0.1, 0.3, 0.03), loc=(0, -LB / 2 - 0.13, FZ + 0.03), rot=(22, 0, 0), bevel=0.01, segs=2)
    SY = -1.14
    for sx in (-1, 1):
        wood(b, (0.05, 0.3, 0.2), loc=(sx * 0.66, SY, FZ + 0.52), mat='wood_dark', bevel=0.012, segs=2)
    wood(b, (1.56, 0.36, 0.04), loc=(0, SY, FZ + 0.635), bevel=0.014, segs=2, rj=0.3)
    wood(b, (1.4, 0.035, 0.2), loc=(0, SY + 0.2, FZ + 0.83), rot=(-10, 0, 0), bevel=0.012, segs=2)
    for sx in (-1, 1):
        wood(b, (0.045, 0.045, 0.34), loc=(sx * 0.6, SY + 0.21, FZ + 0.78), rot=(-10, 0, 0), mat='wood_dark', bevel=0.01, segs=1)
    b.box((0.95, 0.28, 0.07), loc=(0, SY - 0.02, FZ + 0.69), mat='cloth', color=BLUE, bevel=0.03, segs=2, jitter=0.05)
    for sx in (-1, 1):
        b.blob(0.02, loc=(sx * 0.475, SY - 0.16, FZ + 0.69), mat='cloth', subdiv=1, color=GOLD)
        b.blob(0.02, loc=(sx * 0.475, SY + 0.12, FZ + 0.69), mat='cloth', subdiv=1, color=GOLD)

    # ---- canopy: hoops + striped canvas ------------------------------------------------------------
    A = WB / 2 + 0.47 * fl + 0.035
    Z0 = FZ + 0.47
    HG = 0.98
    Y0, Y1 = -0.8, 0.72
    HOOPS = (-0.76, -0.27, 0.22, 0.68)

    def arch(t, a, hg):
        c, s = math.cos(t), math.sin(t)
        return (a * (1 if c >= 0 else -1) * abs(c) ** 0.72, Z0 + hg * abs(s) ** 0.78)

    for hy in HOOPS:
        pts = [(A + 0.025, hy, FZ + 0.1), (A + 0.005, hy, Z0 - 0.15)]
        for i in range(17):
            x, z = arch(math.pi * i / 16, A, HG)
            pts.append((x, hy, z))
        pts += [(-A - 0.005, hy, Z0 - 0.15), (-A - 0.025, hy, FZ + 0.1)]
        n0 = nfaces(b)
        b.tube(pts, 0.021, mat='wood_light', segs=6, jitter=0.1)
        swap_uv(b, n0)
    n0 = nfaces(b)
    b.tube([(0, Y0 - 0.2, Z0 + HG - 0.03), (0, (Y0 + Y1) / 2, Z0 + HG - 0.022), (0, Y1 + 0.24, Z0 + HG - 0.03)], 0.022, mat='wood_light', segs=8)
    swap_uv(b, n0)
    for y, d in ((Y0 - 0.2, -1), (Y1 + 0.24, 1)):
        b.lathe([(0.02, 0), (0.03, 0.005), (0.03, 0.02), (0.02, 0.03), (0.036, 0.055), (0.03, 0.08), (0, 0.092)], loc=(0, y, Z0 + HG - 0.03),
                rot=(-90 * d, 0, 0), mat='gold', segs=10)
    NU, NV = 21, 24
    LEN = Y1 - Y0 + 0.14

    def cpos(u, v):
        y = Y0 - 0.07 + u * LEN
        d = min(abs(y - h) for h in HOOPS)
        sag = 1 - 0.05 * math.sin(min(d / 0.25, 1.0) * math.pi / 2) ** 2
        edge = 1 + 0.035 * max(0.0, 1 - min(u, 1 - u) * NU) ** 2    # flared lip at both ends
        a, hg = (A + 0.03) * edge, (HG + 0.03) * sag * edge
        w = v
        hem = 2.0 / NV
        if w < hem:
            k = 1 - w / hem
            return (a + 0.012 * k, y, Z0 - 0.17 * k)
        if w > 1 - hem:
            k = 1 - (1 - w) / hem
            return (-a - 0.012 * k, y, Z0 - 0.17 * k)
        x, z = arch(math.pi * (w - hem) / (1 - 2 * hem), a, hg)
        return (x, y, z)

    def ccol(i, j):
        if j == 0 or j == NV - 1:
            return GOLD
        base = BLUE if (i // 3) % 2 == 0 else CREAM
        t = min(j, NV - 1 - j) / (NV / 2)
        return tint(base, 0.8 + 0.2 * min(1.0, t * 1.6))

    sheet(b, NU, NV, cpos, ccol, mat='cloth', thick=0.012, uvsize=(LEN, 3.2), back=0.62)
    # rope ties from the hem to the stakes
    for hy in HOOPS:
        for sx in (-1, 1):
            b.tube([(sx * (A + 0.045), hy + 0.05, Z0 - 0.15), (sx * (A + 0.04), hy + 0.03, Z0 - 0.26), (sx * (A + 0.0), hy + 0.01, Z0 - 0.33)], 0.006,
                   mat='rope', segs=5)
    # lantern under the rear end of the ridge pole
    b.tube([(0, Y1 + 0.17, Z0 + HG - 0.05), (0, Y1 + 0.17, Z0 + HG - 0.1)], 0.005, mat='metal_dark', segs=6)
    with b.at(loc=(0, Y1 + 0.17, Z0 + HG - 0.09)):
        lc = lantern(b, 0.75)
        mark(b, 'wagon_lantern_light', lc)

    # ---- cargo -------------------------------------------------------------------------------------
    with b.at(loc=(-0.3, -0.42, FZ), rot=(0, 0, 5)):
        crate(b, 0.56)
    with b.at(loc=(0.31, -0.4, FZ), rot=(0, 0, -7)):
        crate(b, 0.5)
    with b.at(loc=(-0.22, -0.42, FZ + 0.565), rot=(0, 0, 17)):
        crate(b, 0.4)
    with b.at(loc=(0.33, 0.18, FZ), rot=(0, 0, 40)):
        sack(b, 1.0)
    with b.at(loc=(-0.3, 0.2, FZ), rot=(0, 0, 200)):
        sack(b, 1.08, srgb(190, 164, 118))
    with b.at(loc=(0.02, 0.36, FZ + 0.33), rot=(78, 0, 100)):
        sack(b, 0.9, srgb(168, 140, 98))
    with b.at(loc=(-0.32, 1.06, FZ), rot=(0, 0, 30)):
        barrel(b, 0.86)
    with b.at(loc=(0.33, 1.08, FZ), rot=(0, 0, -6)):
        crate(b, 0.52, open_top=True)
        apple = [srgb(196, 48, 40), srgb(214, 70, 44), srgb(178, 36, 40), srgb(200, 160, 50)]
        for i in range(14):
            a = i * 2.4
            rr = 0.17 * math.sqrt((i + 0.5) / 14)
            b.blob((0.055, 0.055, 0.05), loc=(rr * math.cos(a) * 1.15, rr * math.sin(a) * 1.15, 0.5 + R(b, 0.0, 0.03) + (0.04 if i < 4 else 0)),
                   mat='plant_glossy', subdiv=2 if i < 6 else 1, color=b.rng.choice(apple), jitter=0.08)
    with b.at(loc=(0.02, 0.72, FZ), rot=(0, 0, 120)):
        sack(b, 0.8, srgb(182, 156, 112))
    mark(b, 'wagon_back', (0, LB / 2 + 0.9, 0))
    root = b.build(sharp_angle=50)
    CHILDREN['wagon'] = [
        (build_wheel('wagon_wheel_fl', RF, 1, 71), (WX, YF, RF)),
        (build_wheel('wagon_wheel_fr', RF, -1, 72), (-WX, YF, RF)),
        (build_wheel('wagon_wheel_bl', RB, 1, 73), (WX, YB, RB)),
        (build_wheel('wagon_wheel_br', RB, -1, 74), (-WX, YB, RB)),
    ]
    return root


# ============================================================================================
# BANNER POLE
# ============================================================================================
BW, BL_ = 0.92, 2.25   # banner cloth width / length


def build_banner_cloth():
    """Origin at the centre of the top edge, hangs down -Z in the XZ plane, faces -Y."""
    b = Builder('banner_cloth', seed=65)
    NU, NV = 12, 20
    notch = 0.3

    def yfn(x, z):
        v = -z / BL_
        return -0.05 * math.sin(v * 2.4) * v - 0.012 * math.sin(x * 7 + v * 5) * v

    def pos(u, v):   # v = 0 at the bottom
        x = (u - 0.5) * BW
        top = 1 - v
        zb = -BL_ + notch * (1 - abs(2 * u - 1))
        z = zb * top
        return (x, yfn(x, z), z)

    def colr(i, j):
        if i in (0, NU - 1) or j == NV - 1:
            return CREAM
        if j == 0:
            return GOLD
        if i in (1, NU - 2) or j == NV - 2 or j == 1:
            return tint(BLUE, 0.78)
        return BLUE

    sheet(b, NU, NV, pos, colr, mat='cloth', thick=0.008, uvsize=(BW, BL_), back=0.9)

    def emb(pts, sub=None):
        flat_poly(b, pts, -0.0075, 'cloth', GOLD, back=0.0075, yfn=yfn)

    # crown (band + three points, split so it follows the cloth)
    cz = -0.66
    emb([(-0.2, cz), (0.0, cz), (0.0, cz + 0.06), (-0.2, cz + 0.06)])
    emb([(0.0, cz), (0.2, cz), (0.2, cz + 0.06), (0.0, cz + 0.06)])
    emb([(-0.2, cz + 0.06), (-0.085, cz + 0.06), (-0.14, cz + 0.13), (-0.25, cz + 0.21)])
    emb([(0.085, cz + 0.06), (0.2, cz + 0.06), (0.25, cz + 0.21), (0.14, cz + 0.13)])
    emb([(-0.085, cz + 0.06), (0.085, cz + 0.06), (0.06, cz + 0.15), (0.0, cz + 0.25), (-0.06, cz + 0.15)])
    emb([(-0.14, cz + 0.13), (-0.085, cz + 0.06), (-0.06, cz + 0.15)])
    emb([(0.085, cz + 0.06), (0.14, cz + 0.13), (0.06, cz + 0.15)])
    # wheat ear
    for k in range(6):
        z0 = -1.72 + k * 0.1
        emb([(-0.014, z0), (0.014, z0), (0.014, z0 + 0.1), (-0.014, z0 + 0.1)])
    for k in range(5):
        z0 = -1.34 + k * 0.105
        for sx in (-1, 1):
            emb(xf(GRAIN, sx * 0.062, z0 + 0.03, -sx * 34, 0.17))
    emb(xf(GRAIN, 0, -0.8, 0, 0.17))
    for sx in (-1, 1):   # two curved leaves at the stem base
        emb([(sx * 0.014, -1.66), (sx * 0.1, -1.58), (sx * 0.17, -1.47), (sx * 0.085, -1.54)][::sx])
        emb([(sx * 0.17, -1.47), (sx * 0.215, -1.36), (sx * 0.15, -1.44), (sx * 0.085, -1.54)][::sx])
    return b.build(sharp_angle=50)


def build_banner_pole():
    b = Builder('banner_pole', seed=64)
    for i in range(6):
        a = i * 2 * math.pi / 6 + 0.4
        stone(b, (R(b, 0.22, 0.32), R(b, 0.2, 0.26), R(b, 0.18, 0.3)), (0.2 * math.cos(a), 0.2 * math.sin(a), 0.07),
              rot0=(0, 0, math.degrees(a)), bev=0.06, rj=8)
    tuft(b, 0.3, -0.2, n=6)
    tuft(b, -0.32, 0.1, n=5)
    H = 4.86
    n0 = nfaces(b)
    b.tube([(0, 0, -0.1), (0.006, 0, 1.2), (-0.004, 0.004, 2.6), (0.004, 0, 3.9), (0, 0, H)], [0.075, 0.07, 0.062, 0.054, 0.046],
           mat='wood_dark', segs=10, jitter=0.05)
    swap_uv(b, n0)
    for z in (0.42, H - 0.42):
        b.lathe([(0.05, -0.03), (0.082, -0.026), (0.082, 0.026), (0.05, 0.03)], loc=(0, 0, z), mat='metal_dark', segs=10)
    for z, c in ((1.5, BLUE), (1.58, GOLD), (1.66, CREAM), (1.74, GOLD), (1.82, BLUE)):
        b.lathe([(0.062, -0.04), (0.071, -0.036), (0.071, 0.036), (0.062, 0.04)], loc=(0, 0, z), mat='paint', segs=10, color=c)
    # gold finial: collar, ball, spear point
    b.lathe([(0.03, 0), (0.058, 0.0), (0.062, 0.03), (0.04, 0.05), (0.03, 0.075), (0.075, 0.12), (0.085, 0.165), (0.07, 0.21), (0.03, 0.245),
             (0.022, 0.27), (0.045, 0.3), (0.036, 0.36), (0, 0.5)], loc=(0, 0, H - 0.02), mat='gold', segs=12)
    # cross bar the banner hangs from
    CZ, CY = 4.42, -0.085
    with b.at(loc=(0, CY, CZ)):
        n0 = nfaces(b)
        b.lathe([(0, -0.58), (0.022, -0.58), (0.025, -0.5), (0.027, 0.0), (0.025, 0.5), (0.022, 0.58), (0, 0.58)], rot=(0, 90, 0),
                mat='wood_light', segs=10)
        swap_uv(b, n0)
        for sx in (-1, 1):
            b.lathe([(0.02, 0), (0.032, 0.004), (0.032, 0.018), (0.02, 0.026), (0.04, 0.055), (0.034, 0.085), (0, 0.1)], loc=(sx * 0.575, 0, 0),
                    rot=(0, sx * 90, 0), mat='gold', segs=10)
            # ropes up to the pole
            b.tube([(sx * 0.5, 0, 0.02), (sx * 0.25, 0.03, 0.2), (0, 0.05, 0.36)], 0.007, mat='rope', segs=6)
        # iron bracket holding the bar
        b.box((0.07, 0.11, 0.05), loc=(0, 0.035, 0), mat='metal_dark', bevel=0.008, segs=1)
        b.lathe([(0.026, -0.03), (0.036, -0.028), (0.036, 0.028), (0.026, 0.03)], rot=(0, 90, 0), mat='metal_dark', segs=10)
        # cloth loops over the bar
        nl = 5
        for i in range(nl):
            x = -BW / 2 + 0.07 + i * (BW - 0.14) / (nl - 1)
            b.lathe([(0.028, -0.045), (0.034, -0.043), (0.034, 0.043), (0.028, 0.045)], loc=(x, 0, 0), rot=(0, 90, 0), scale=(1, 1.0, 1.25),
                    mat='cloth', segs=10, color=CREAM)
    b.lathe([(0.06, -0.025), (0.076, -0.02), (0.076, 0.02), (0.06, 0.025)], loc=(0, 0, CZ + 0.36), mat='rope', segs=10)
    root = b.build(sharp_angle=50)
    CHILDREN['banner_pole'] = [(build_banner_cloth(), (0, CY, CZ - 0.04))]
    return root


# ============================================================================================
# MILESTONE
# ============================================================================================
def build_milestone():
    b = Builder('milestone', seed=66)
    # footing: a few rough blocks rather than one clean slab
    stone(b, (0.5, 0.56, 0.22), (-0.2, 0.0, 0.06), bev=0.06, rj=2.5, k=0.88)
    stone(b, (0.44, 0.5, 0.19), (0.24, 0.02, 0.05), bev=0.06, rj=3.5, k=0.82)
    stone(b, (0.3, 0.2, 0.14), (0.02, -0.29, 0.03), bev=0.05, rj=6, k=0.85)
    w, sh, d, AF = 0.3, 0.6, 0.34, 0.82
    arc = [(w * math.cos(a) * (1 + 0.035 * math.sin(a * 2.3 + 0.6)), sh + w * math.sin(a) * AF * (1 + 0.05 * math.sin(a * 1.7 + 2.0)))
           for a in [math.pi * i / 10 for i in range(11)]]
    with b.at(loc=(0, 0, 0.12), rot=(-4, 2.5, 3)):
        b.prism([(-w - 0.03, 0), (w + 0.025, 0)] + arc, d, mat='stone', bevel=0.05, segs=2, color=(0.74, 0.72, 0.68), color_top=(1, 0.99, 0.95))
        # chipped corners: small chiselled lumps breaking the clean outline
        for (x, y, z, r) in ((-w - 0.0, -0.1, 0.1, 0.07), (0.14, 0.13, sh + 0.2, 0.06)):
            b.blob((r, r * 0.9, r * 1.2), loc=(x, y, z), mat='stone', subdiv=2, noise_amp=0.2, noise_scale=2.0, color=(0.8, 0.78, 0.74),
                   color_top=(0.98, 0.97, 0.93), deform=chisel(b, (r, r * 0.9, r * 1.2), 6))
        fy = -d / 2
        # carved moulding around the face
        ins = 0.055
        path = [(-(w - ins), fy, 0.07)] + [((w - ins) * math.cos(a), fy, sh + (w - ins) * math.sin(a) * AF) for a in
                                             [math.pi * (10 - i) / 10 for i in range(11)]] + [((w - ins), fy, 0.07), (-(w - ins), fy, 0.07)]
        b.tube(path, 0.016, mat='stone', segs=6, caps=False, color=(0.97, 0.96, 0.93))
        # crown in low relief with worn gold paint
        b.prism(crown_pts(0.24, 0.1), 0.03, loc=(0, fy - 0.004, sh - 0.02), mat='paint', color=tint(GOLD, 0.9), bevel=0.006, segs=1)
        b.box((0.22, 0.03, 0.03), loc=(0, fy - 0.006, sh - 0.016), mat='paint', color=tint(GOLD, 0.9), bevel=0.006, segs=1)
        for x in (-0.132, 0, 0.132):
            b.blob(0.016, loc=(x, fy - 0.006, sh + 0.1 + (0.012 if x == 0 else 0)), mat='paint', subdiv=1, color=tint(GOLD, 0.9))
        # little castle tower relief
        b.box((0.13, 0.024, 0.17), loc=(0, fy - 0.002, sh - 0.2), mat='stone', bevel=0.006, segs=1, grain=None, color=(1, 1, 0.98))
        for x in (-0.05, 0, 0.05):
            b.box((0.032, 0.024, 0.035), loc=(x, fy - 0.002, sh - 0.1), mat='stone', bevel=0.005, segs=1, grain=None, color=(1, 1, 0.98))
        b.prism([(-0.022, 0), (0.022, 0), (0.022, 0.05), (0, 0.075), (-0.022, 0.05)], 0.012, loc=(0, fy - 0.012, sh - 0.27), mat='stone', bevel=0,
                color=(0.42, 0.4, 0.38))
        # direction chevrons (point +X) and three tally notches (leagues to the castle)
        for i in range(3):
            x = -0.12 + i * 0.09
            for s in (-1, 1):
                b.box((0.075, 0.02, 0.022), loc=(x + 0.02, fy - 0.002, 0.245 + s * 0.022), rot=(0, s * 38, 0), mat='stone', bevel=0.005, segs=1,
                      grain=None, color=(1, 1, 0.98))
        for i in range(3):
            b.box((0.02, 0.012, 0.085), loc=(-0.06 + i * 0.06, fy - 0.001, 0.135), rot=(0, R(b, -5, 5), 0), mat='stone', bevel=0.004, segs=1,
                  grain=None, color=(0.45, 0.43, 0.41))
        # moss on the shoulder
        for (x, y, z, r) in ((-0.2, 0.02, sh + 0.15, 0.08), (-0.27, -0.06, sh + 0.03, 0.055), (0.2, 0.08, sh + 0.16, 0.05), (-0.3, 0.1, 0.12, 0.09),
                             (0.28, -0.12, 0.06, 0.07), (-0.05, 0.12, sh + 0.24, 0.07)):
            b.blob((r, r * 0.9, r * 0.5), loc=(x, y, z), mat='plant', subdiv=2, noise_amp=0.25, noise_scale=2.5, color=srgb(70, 104, 48),
                   color_top=srgb(120, 150, 62))
    # wooden arrow sign on a stake behind the stone, pointing +X (toward the castle)
    px, py = -0.36, 0.2
    wood(b, (0.075, 0.075, 1.36), loc=(px, py, 0.6), rot=(1.5, -2.5, 8), mat='wood_dark', bevel=0.014, segs=2, taper=(0.85, 0.85))
    wood(b, (0.07, 0.07, 0.04), loc=(px - 0.028, py + 0.016, 1.295), rot=(1.5, -2.5, 8), mat='wood_dark', bevel=0.012, segs=2, taper=(0.4, 0.4))
    with b.at(loc=(px + 0.2, py - 0.058, 1.13), rot=(0, -5, 0)):
        arrow = [(-0.3, -0.075), (0.2, -0.075), (0.2, -0.125), (0.37, 0), (0.2, 0.125), (0.2, 0.075), (-0.3, 0.075), (-0.25, 0)]
        b.prism(arrow, 0.036, mat='wood_light', bevel=0.008, segs=1, grain=0, jitter=0.05)
        b.prism([(0.215, -0.1), (0.35, 0), (0.215, 0.1)], 0.006, loc=(0, -0.019, 0), mat='paint', color=BLUE, bevel=0)
        b.box((0.03, 0.006, 0.14), loc=(-0.2, -0.019, 0), mat='paint', color=BLUE, bevel=0)
        b.prism(crown_pts(0.13, 0.055), 0.006, loc=(-0.02, -0.019, -0.03), mat='paint', color=GOLD, bevel=0)
        for x in (-0.24, -0.16):
            b.cyl(0.009, 0.006, loc=(x + 0.06, -0.02, 0.04 if x < -0.2 else -0.04), rot=(90, 0, 0), mat='metal_dark', segs=6, bevel=0.002)
    rock(b, (0.16, 0.13, 0.12), (0.42, -0.14, -0.01), yaw=30, subdiv=2, planes=7)
    rock(b, (0.1, 0.09, 0.08), (0.3, 0.2, -0.01), yaw=80, subdiv=2, planes=6)
    tuft(b, -0.4, -0.2, n=7)
    tuft(b, 0.36, 0.08, n=6)
    tuft(b, 0.05, 0.3, n=6, h=(0.14, 0.34))
    tuft(b, -0.15, -0.27, n=4, h=(0.08, 0.16))
    return b.build(sharp_angle=50)


# ============================================================================================
# REGISTRY / MAIN
# ============================================================================================
ASSETS = {'castle': build_castle, 'notice_board': build_notice_board, 'wagon': build_wagon, 'banner_pole': build_banner_pole,
          'milestone': build_milestone}
# preview groups: name -> (asset names, spacing, views[(az, el)], zoom)
GROUPS = {
    'castle': (['castle'], 0, [(0, 4), (28, 4), (-35, 6), (30, 22), (150, 20)], 1.25),
    'board': (['notice_board'], 0, [(20, 12), (-30, 14), (160, 16)], 1.25),
    'wagon': (['wagon'], 0, [(35, 18), (-50, 14), (145, 20), (90, 6)], 1.25),
    'banner': (['banner_pole'], 0, [(20, 10), (160, 10)], 1.2),
    'milestone': (['milestone'], 0, [(20, 16), (-35, 20), (150, 20)], 1.25),
}
# close-ups: group -> [(tag, centre, size, az, el)]
FOCUS = {
    'castle': [('gate', (0, -22, 8), 24, 12, 8), ('keep', (-2, 5, 26), 30, 20, 10)],
    'board': [('crest', (0, -0.1, 1.9), 1.0, 12, 4), ('notes', (0, -0.1, 1.35), 1.3, -14, 6), ('fp', (0, 0, 1.4), 2.6, 8, 3)],
    'wagon': [('cargo', (0, 1.0, 1.3), 1.9, 160, 22), ('front', (0, -1.3, 1.2), 2.4, 25, 12), ('wheel', (0.9, 0.9, 0.7), 1.5, 70, 10)],
    'banner': [('cloth', (0, -0.1, 3.4), 2.6, 12, 4), ('base', (0, 0, 0.4), 1.2, 25, 15)],
    'milestone': [('face', (0, -0.1, 0.65), 1.0, 8, 8)],
}

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
