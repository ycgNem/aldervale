"""First-person arms, inventory goods and the hen -> public/models/items.glb

  blender --background --factory-startup --python tools/blender/build_items.py -- [preview_dir] [group ...]

With no group names everything is built and exported to public/models/items.glb.
With group names (arms, crops, pantry, baked, chicken) only those are built + previewed (no export).
Pass an ABSOLUTE preview dir (Blender resolves relative render paths oddly on Windows).

Conventions: see kit.py. Extra ones for this file
- fp_arm_r / fp_arm_l: origin at the WRIST joint, forearm runs along +Y (back toward the camera),
  the hand points -Y. fp_arm_r is palm-down, closed round a handle that runs along local X
  (marker fp_grip_r = handle centre). fp_arm_l is a half-open hand, palm turned up and inward
  (marker fp_grip_l = palm centre).
- item_*: origin bottom centre. chicken / chicken_white: origin at the feet, facing -Y, the head +
  neck is a child object (chicken_head / chicken_white_head) pivoting at the neck base.
- No new material names: everything uses kit.PREVIEW keys.
"""
import sys
import os
import math

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
OUT = os.path.join(ROOT, 'public', 'models', 'items.glb')

kit.reset()
pi = math.pi


# ================================================================ helpers
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


# ================================================================ FIRST-PERSON ARMS
SKIN = srgb(214, 160, 122)
SKIN_PALM = srgb(226, 176, 146)
SKIN_KNUCKLE = srgb(206, 132, 104)
SKIN_CREASE = srgb(160, 98, 72)
NAIL = srgb(224, 174, 156)
LINEN = srgb(232, 216, 184)
LINEN_D = srgb(176, 156, 122)

RH = 0.0175                    # radius of the handle the right hand is closed around
GRIP_C = (-0.082, -0.031)      # (y, z) of that handle's axis in hand space (axis runs along X)
LEFT_ROLL = 140.0              # forearm roll of the left arm: palm up and turned inward

# hand space = a LEFT hand, palm down: wrist at the origin, fingers toward -Y, back of the hand +Z, thumb at -X
# (the viewer looks along -Y, so -X is the viewer's right). The right arm is this mirrored in X.
FINGERS = [  # name, x, mcp_y, mcp_z, (proximal, middle, distal), base radius, relaxed curls, relaxed splay
    ('index', -0.0290, -0.091, 0.001, (0.044, 0.026, 0.023), 0.0096, (24, 34, 20), -6.0),
    ('middle', -0.0095, -0.096, 0.002, (0.048, 0.030, 0.024), 0.0099, (31, 40, 22), -1.5),
    ('ring', 0.0100, -0.092, 0.001, (0.044, 0.028, 0.023), 0.0093, (38, 44, 24), 3.0),
    ('pinky', 0.0282, -0.082, -0.002, (0.034, 0.020, 0.021), 0.0083, (45, 47, 26), 8.0),
]
ARM_R = [  # y, half width (hand X), half thickness (hand Z)
    (-0.02, 0.0275, 0.0195), (0.0, 0.0275, 0.0195), (0.03, 0.0282, 0.0208), (0.08, 0.031, 0.0255),
    (0.14, 0.036, 0.0315), (0.20, 0.040, 0.0365), (0.32, 0.043, 0.0405)]


def circ_next(P, L, C, R, ccw):
    """2D: the point at distance L from P and R from C, on the side that winds ccw (+1) / cw (-1) about C."""
    vx, vy = C[0] - P[0], C[1] - P[1]
    d = max(math.hypot(vx, vy), 1e-9)
    a = (L * L - R * R + d * d) / (2 * d)
    h = math.sqrt(max(L * L - a * a, 0.0))
    mx, my = P[0] + a * vx / d, P[1] + a * vy / d
    best = None
    for s in (-1, 1):
        q = (mx - s * h * vy / d, my + s * h * vx / d)
        cr = (P[0] - C[0]) * (q[1] - C[1]) - (P[1] - C[1]) * (q[0] - C[0])
        if best is None or cr * ccw > best[0]:
            best = (cr * ccw, q)
    return best[1]


def hand_pose(pose):
    """-> list of fingers: dict(J=[4 joints], rad=[4 radii], lat=Vector|None, hint=Vector|None)."""
    out = []
    for name, x, my, mz, lens, r0, curls, splay in FINGERS:
        J = [Vector((x, my, mz))]
        if pose == 'grip':
            P = (my, mz)
            for L, k in zip(lens, (1.75, 1.2, 1.0)):
                P = circ_next(P, L, GRIP_C, RH + r0 * k, +1)
                J.append(Vector((x, P[0], P[1])))
            lat = Vector((1, 0, 0))
        else:
            a = 0.0
            s = math.radians(splay)
            for L, c in zip(lens, curls):
                a += math.radians(c)
                J.append(J[-1] + Vector((math.sin(s) * math.cos(a), -math.cos(s) * math.cos(a), -math.sin(a))) * L)
            lat = Vector((math.cos(s), math.sin(s), 0))
        r0 *= 1.05
        out.append(dict(name=name, J=J, rad=[r0, r0 * 0.96, r0 * 0.9, r0 * 0.83], lat=lat, hint=None))
    # thumb: metacarpal, proximal, distal
    if pose == 'grip':
        cmc = Vector((-0.029, -0.020, -0.012))
        R0 = RH + 0.0135
        th = math.radians(-100)   # on the camera side of the handle, a little below its axis
        P = (GRIP_C[0] - R0 * math.sin(th), GRIP_C[1] + R0 * math.cos(th))
        J = [cmc, Vector((-0.0485, P[0], P[1]))]
        for L, R, x in ((0.033, RH + 0.0125, -0.0500), (0.028, RH + 0.0108, -0.0490)):
            P = circ_next(P, L, GRIP_C, R, -1)
            J.append(Vector((x, P[0], P[1])))
        out.append(dict(name='thumb', J=J, rad=[0.0135, 0.0118, 0.0106, 0.0092], lat=Vector((-1, 0, 0)), hint=None))
    else:
        cmc = Vector((-0.028, -0.020, -0.010))
        J = [cmc]
        for d, L in (((-0.78, -0.52, -0.34), 0.042), ((-0.58, -0.76, -0.30), 0.033), ((-0.32, -0.89, -0.33), 0.028)):
            J.append(J[-1] + Vector(d).normalized() * L)
        out.append(dict(name='thumb', J=J, rad=[0.0135, 0.0118, 0.0106, 0.0092], lat=None, hint=Vector((-0.62, 0.3, 0.72))))
    return out


def dorsal(f, d):
    d = d.normalized()
    if f['hint'] is not None:
        n = f['hint'] - d * f['hint'].dot(d)
    else:
        n = d.cross(f['lat'])
    return n.normalized()


def finger_tube(b, f):
    J, rad = f['J'], f['rad']
    pts, rr = [J[0].copy()], [rad[0] * 1.04]
    n = len(J) - 1
    for k in range(n):
        A, Bp = J[k], J[k + 1]
        d = Bp - A
        r_a, r_b = rad[k], rad[k + 1]
        last = k == n - 1
        for t, kk in ((0.25, 0.97), (0.5, 0.945), (0.75, 0.97)):
            if last and t > 0.7:
                continue
            pts.append(A + d * t)
            rr.append((r_a * (1 - t) + r_b * t) * kk)
        if not last:
            d2 = J[k + 2] - Bp
            nrm = (dorsal(f, d) + dorsal(f, d2)).normalized()
            pts.append(Bp + nrm * r_b * 0.14)       # knuckle
            rr.append(r_b * 1.08)
        else:
            dn = d.normalized()
            pts.append(Bp - dn * rad[-1] * 1.25 - dorsal(f, d) * rad[-1] * 0.06)   # fleshy pad
            rr.append(rad[-1] * 1.03)
            pts.append(Bp - dn * rad[-1] * 0.9)
            rr.append(rad[-1] * 0.9)
    b.tube(pts, rr, mat='skin', segs=12)


def hand_solid(b, pose, fingers):
    """All the overlapping skin volumes of the hand (they are fused into one skin by fuse())."""
    cup = 0.010 if pose == 'grip' else 0.007

    def slab(c):
        # squarer outline than an ellipse, narrower toward the wrist, arched across
        u, v = c.x / 0.044, c.y / 0.056
        rho = math.hypot(u, v)
        if rho > 1e-6:
            p = 3.2
            k = 1.0 / ((abs(u / rho) ** p + abs(v / rho) ** p) ** (1 / p))
            k = 1.0 + (k - 1.0) * 0.8
            c.x *= k
            c.y *= k
        c.x *= 0.72 + 0.28 * smooth(0.055, -0.035, c.y)
        c.z -= cup * (c.x / 0.044) ** 2
        return c

    b.blob((0.044, 0.056, 0.0138), loc=(0.0, -0.047, 0.0005), mat='skin', subdiv=4, deform=slab)
    for f in fingers[:4]:                                         # knuckles
        p = f['J'][0]
        r = f['rad'][0]
        b.blob((r * 1.04, r * 1.25, r * 0.95), loc=(p.x, p.y + 0.004, p.z + 0.0022), mat='skin', subdiv=3)
    th = fingers[4]['J']
    # heel of the hand: thenar (thumb side) and hypothenar pads
    mid = th[0].lerp(th[1], 0.45)
    b.blob((0.0155, 0.028, 0.0140), loc=(mid.x + 0.006, mid.y + 0.004, mid.z + 0.002), rot=(0, 0, -24), mat='skin', subdiv=3)
    b.blob((0.0150, 0.038, 0.0105), loc=(0.0205, -0.044, -0.0052), rot=(0, 0, 4), mat='skin', subdiv=3)
    # extensor tendons: faint ridges fanning from the wrist to each knuckle
    def back_z(x, y):
        q = 1 - (x / 0.044) ** 2 - ((y + 0.047) / 0.056) ** 2
        return 0.0005 + 0.0138 * math.sqrt(max(q, 0.0)) - cup * (x / 0.044) ** 2
    for f in fingers[:4]:
        k = f['J'][0]
        pts = []
        for t in (0.0, 0.3, 0.6, 0.85, 1.0):
            x = k.x * (0.32 + 0.68 * t)
            y = -0.008 + (k.y + 0.012 + 0.008) * t
            pts.append((x, y, back_z(x, y) - 0.0036 + 0.0015))
        b.tube(pts, 0.0036, mat='skin', segs=8)
    # web between thumb and index
    b.tube([th[1].lerp(th[0], 0.25), fingers[0]['J'][0] + Vector((0.002, 0.012, -0.004))], [0.0105, 0.009], mat='skin', segs=10)
    for f in fingers:
        finger_tube(b, f)
    # wrist stub (disappears under the bracer)
    rx, rz = lerp_table(ARM_R, 0.0)
    b.lathe([(0, -0.050), (0.45, -0.046), (0.78, -0.030), (0.94, -0.012), (1.0, 0.006), (1.03, 0.058), (0.9, 0.066), (0, 0.068)],
            rot=(-90, 0, 0), scale=(rx, rz, 1), mat='skin', segs=24)
    # the knobbly end of the ulna on the little-finger side
    b.blob((0.007, 0.0095, 0.0055), loc=(0.0195, 0.008, 0.0108), mat='skin', subdiv=2)


def fuse(tb, voxel, smooth_it, target_tris):
    """Builder full of overlapping closed volumes -> one fused, smoothed, decimated mesh datablock."""
    obj = tb.build(weighted=False)
    rm = obj.modifiers.new('rm', 'REMESH')
    rm.mode = 'VOXEL'
    rm.voxel_size = voxel
    rm.adaptivity = 0.0
    rm.use_smooth_shade = True
    sm = obj.modifiers.new('sm', 'SMOOTH')
    sm.factor = 0.5
    sm.iterations = smooth_it
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    cur = kit.tri_count([obj])
    if cur > target_tris:
        dc = obj.modifiers.new('dc', 'DECIMATE')
        dc.decimate_type = 'COLLAPSE'
        dc.ratio = target_tris / cur
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(old)
    return me


def emit_skin(b, me, fingers):
    """Add the fused hand mesh to b with painted skin tones: pale palm, ruddy knuckles and tips, dark creases."""
    t = b._new()
    t.from_mesh(me)
    bpy.data.meshes.remove(me)
    uv, col, _ = b._layers(t)
    t.verts.ensure_lookup_table()
    t.normal_update()
    # concavity -> crease shading
    conc = {}
    for v in t.verts:
        nb = [e.other_vert(v) for e in v.link_edges]
        if not nb:
            conc[v] = 0.0
            continue
        avg = sum((n.co for n in nb), Vector()) / len(nb)
        el = sum((n.co - v.co).length for n in nb) / len(nb)
        conc[v] = (avg - v.co).dot(v.normal) / max(el, 1e-6)
    for _ in range(2):
        nxt = {}
        for v in t.verts:
            nb = [e.other_vert(v) for e in v.link_edges]
            nxt[v] = 0.5 * conc[v] + 0.5 * sum(conc[n] for n in nb) / max(len(nb), 1)
        conc = nxt
    red = []   # (point, radius, strength)
    for f in fingers:
        J = f['J']
        is_thumb = f['name'] == 'thumb'
        for k in range(1 if is_thumb else 0, 3):
            d = J[k + 1] - J[k]
            dprev = J[k] - J[k - 1] if k else d
            n = (dorsal(f, d) + dorsal(f, dprev)).normalized()
            red.append((J[k] + n * f['rad'][k] * 0.9, 0.0125, 0.55))
        red.append((J[3], 0.014, 0.42))   # fingertip
    cols = {}
    for v in t.verts:
        c = SKIN
        palm = smooth(-0.15, -0.75, v.normal.z) * smooth(-0.105, -0.085, v.co.y) * smooth(0.03, 0.0, v.co.y)
        c = mix(c, SKIN_PALM, 0.75 * palm)
        k = 0.0
        for p, r, s in red:
            k = max(k, s * math.exp(-((v.co - p).length / r) ** 2))
        c = mix(c, SKIN_KNUCKLE, k)
        cr = smooth(0.04, 0.32, conc[v])
        c = mix(c, SKIN_CREASE, 0.7 * cr)
        cols[v] = c
    for f in t.faces:
        f.smooth = True
        for l in f.loops:
            l[col] = (*cols[l.vert], 1.0)
    b._box_uv(t, None, 1.0)
    b._emit(t, 'skin', (0, 0, 0), (0, 0, 0))


def nails(b, fingers):
    for f in fingers:
        J = f['J']
        d = (J[3] - J[2])
        L = d.length
        dn = d.normalized()
        n = dorsal(f, d)
        r = f['rad'][3]
        lat = n.cross(dn).normalized()
        p = J[3] - dn * (L * 0.36) + n * r * 0.80
        zax = (n + dn * 0.10).normalized()

        def dome(c, r=r):
            c.z -= (c.x / (r * 0.63)) ** 2 * r * 0.24      # wrap round the finger
            return c
        b.blob((r * 0.63, L * 0.27, r * 0.18), loc=p, rot=basis_rot(zax, lat), mat='skin', subdiv=2, deform=dome,
               color=mul(NAIL, 0.93), color_top=NAIL)


def arm_sleeves(b, top_dir):
    """Bracer, bare forearm and the rolled linen sleeve, in hand space. top_dir: hand-space direction
    that ends up facing the camera (where the buckles go)."""
    def R(y, off=0.0):
        rx, rz = lerp_table(ARM_R, y)
        return (rx + off, rz + off)

    def st(lst):
        return [(y, *R(y, off)) for y, off in lst]

    # --- bare forearm between bracer and sleeve
    def skin_c(co):
        return mix(SKIN, SKIN_PALM, 0.5 * smooth(0.2, -0.9, co.z / 0.035))
    loft(b, st([(0.100, 0.0), (0.14, 0.0005), (0.18, 0.0), (0.222, -0.001)]), 'skin', color=skin_c, segs=20)

    # --- leather bracer
    def lea_c(co):
        rim = max(smooth(0.040, 0.030, co.y), smooth(0.106, 0.116, co.y))
        wear = 0.06 * noise.noise(Vector((co.x * 60, co.y * 60, co.z * 60)))
        return mul((1.0, 0.93, 0.86), 0.8 - 0.22 * rim + wear)
    loft(b, st([(0.0315, -0.002), (0.0285, 0.0010), (0.0288, 0.0034), (0.0312, 0.0048), (0.0345, 0.0038), (0.038, 0.0030),
                (0.060, 0.0033), (0.085, 0.0033), (0.108, 0.0030), (0.1115, 0.0038), (0.1148, 0.0048), (0.1172, 0.0034),
                (0.1175, 0.0010), (0.1145, -0.002)]), 'leather', color=lea_c, segs=28)
    ta = math.atan2(top_dir.z, top_dir.x)
    for ys in (0.053, 0.093):
        loft(b, st([(ys - 0.0078, 0.0026), (ys - 0.0066, 0.0052), (ys + 0.0066, 0.0052), (ys + 0.0078, 0.0026)]), 'leather',
             color=(0.52, 0.47, 0.43), segs=28)
        rx, rz = R(ys, 0.0054)
        p = Vector((rx * math.cos(ta), ys, rz * math.sin(ta)))
        nrm = Vector((math.cos(ta) / rx, 0, math.sin(ta) / rz)).normalized()
        tan = Vector((-rx * math.sin(ta), 0, rz * math.cos(ta))).normalized()
        with b.at(p + nrm * 0.0012, basis_rot(nrm, tan)):
            brass = srgb(232, 190, 110)
            for sx, sy, lx, ly in ((0, -0.0088, 0.021, 0.0028), (0, 0.0088, 0.021, 0.0028), (-0.0092, 0, 0.0028, 0.0204), (0.0092, 0, 0.0028, 0.0204)):
                b.box((lx, ly, 0.0028), loc=(sx, sy, 0.0006), mat='metal', bevel=0.0009, segs=1, grain=None, color=brass)
            b.box((0.0125, 0.0018, 0.0018), loc=(-0.003, 0, 0.0018), mat='metal', bevel=0.0006, segs=1, grain=None, color=brass)   # prong
            # strap tail running on past the buckle
            b.box((0.016, 0.0118, 0.0022), loc=(0.017, 0, -0.0003), rot=(0, 8, 0), mat='leather', bevel=0.0009, segs=1, grain=None,
                  color=(0.5, 0.45, 0.41))
    # stitching (thread = rope): short dashes just inside both rims
    for ys in (0.0405, 0.1055):
        rx, rz = R(ys, 0.0037)
        nst = 26
        verts, faces = [], []
        for k in range(nst):
            a0 = 2 * pi * (k + 0.2) / nst
            a1 = 2 * pi * (k + 0.8) / nst
            i0 = len(verts)
            for a, yy in ((a0, ys - 0.0007), (a1, ys - 0.0007), (a1, ys + 0.0007), (a0, ys + 0.0007)):
                verts.append((rx * math.cos(a), yy, rz * math.sin(a)))
            faces.append((i0 + 1, i0, i0 + 3, i0 + 2))
        raw(b, verts, faces, (1.0, 0.95, 0.85), 'rope')

    # --- rolled linen sleeve
    def wr(amp, ph):
        def f(a, y):
            return 1.0 + amp * (0.5 * math.sin(4 * a + 0.8 + 9 * y + ph) + 0.32 * math.sin(7 * a + 2.1 - 14 * y + ph * 2)
                                + 0.18 * math.sin(11 * a + 30 * y))
        return f

    def cloth_c(amp, ph, lo=0.0):
        w = wr(1.0, ph)

        def f(co):
            a = math.atan2(co.z, co.x)
            k = (w(a, co.y) - 1.0)           # -1..1, negative in the valleys
            return mul(mix(LINEN_D, LINEN, 0.62 + 0.5 * k), 1.0 - lo)
        return f

    for yc, off, m, ph in ((0.1935, 0.0060, 0.0098, 0.0), (0.2095, 0.0078, 0.0112, 1.7)):
        ring = []
        for k in range(9):
            phi = math.radians(-90 + 45 * k)
            ring.append((yc + m * math.sin(phi), off + m * math.cos(phi)))
        loft(b, st(ring), 'cloth', color=cloth_c(1.0, ph), segs=26, radial=wr(0.035, ph))
    body = [(0.213, 0.004), (0.219, 0.0125), (0.232, 0.0152), (0.247, 0.0128), (0.260, 0.0178), (0.2725, 0.0215), (0.283, 0.0150),
            (0.292, 0.0172), (0.302, 0.0165), (0.3075, 0.011)]
    S = st(body)
    yl, rxl, rzl = S[-1]
    S += [(yl + 0.0015, rxl * 0.6, rzl * 0.6), (yl + 0.0015, 0.0, 0.0)]
    loft(b, S, 'cloth', color=cloth_c(1.0, 0.6), segs=28, radial=wr(0.05, 0.6))


def build_arm(name, side):
    right = side == 'r'
    pose = 'grip' if right else 'open'
    b = Builder(name, 41 if right else 42)
    frame = dict(rot=(0, 0 if right else LEFT_ROLL, 0), scale=(-1 if right else 1, 1, 1))
    M = kit._mat4((0, 0, 0), frame['rot'], frame['scale'])
    # which hand-space direction faces the first-person camera (up and toward the screen centre)
    cam_dir = Vector((0.45, 0, 0.9)) if right else Vector((-0.55, 0, 0.83))
    top_dir = (M.to_3x3().inverted() @ cam_dir).normalized()
    fingers = hand_pose(pose)
    with b.at(**frame):
        arm_sleeves(b, top_dir)
        nails(b, fingers)
        rest = ntris(b)
        tb = Builder('_skin', 7)
        hand_solid(tb, pose, fingers)
        me = fuse(tb, voxel=0.0017, smooth_it=7, target_tris=max(3000, 8850 - rest))
        emit_skin(b, me, fingers)
    obj = b.build(sharp_angle=100)
    if right:
        g = Vector((-0.006, GRIP_C[0], GRIP_C[1]))
        kit.marker('fp_grip_r', M @ g, parent=obj)
    else:
        kit.marker('fp_grip_l', M @ Vector((0.002, -0.056, -0.020)), parent=obj)
    return obj


# ================================================================ GOODS
# crop colours match build_vegetation.py so harvested goods look like what grew in the field
W_STEM0, W_STEM1 = srgb(186, 150, 66), srgb(222, 176, 78)
W_EAR0, W_EAR1 = srgb(214, 160, 60), srgb(242, 202, 106)
W_AWN = srgb(250, 226, 150)
T_RED, T_ORANGE = srgb(214, 52, 36), srgb(236, 128, 44)
T_SEPAL0, T_SEPAL1 = srgb(86, 140, 56), srgb(52, 108, 42)
P_RIB, P_GROOVE, P_TOP = srgb(236, 124, 32), srgb(184, 78, 20), srgb(246, 156, 52)
CRUST, CRUST_D, CRUST_L = srgb(206, 138, 62), srgb(150, 84, 36), srgb(236, 198, 136)
WHITE = (1.0, 1.0, 1.0)


def wheat_ear(b, loc, d, L, r, awn_len):
    with b.at(loc, aimz(d)):
        prof = [(0, 0), (0.85 * r, 0.07 * L), (r, 0.22 * L), (0.72 * r, 0.36 * L), (0.98 * r, 0.5 * L), (0.66 * r, 0.66 * L),
                (0.8 * r, 0.8 * L), (0, L)]
        b.lathe(prof, scale=(1, 0.74, 1), rot=(0, 0, b.rng.uniform(0, 180)), mat='plant', segs=5, color=W_EAR0, color_top=W_EAR1, jitter=0.07)
        verts, faces, cols = [], [], []
        hw = 0.0028
        for k in range(6):
            zk = L * (0.2 + 0.13 * k)
            s = 1 if k % 2 == 0 else -1
            bx = s * r * 0.7
            i0 = len(verts)
            verts += [(bx, 0, zk - hw), (bx, 0, zk + hw), (s * (r * 0.7 + awn_len * 0.42), b.rng.uniform(-0.006, 0.006), zk + awn_len * 0.95)]
            cols += [W_EAR1, W_EAR1, W_AWN]
            faces.append((i0, i0 + 1, i0 + 2))
        i0 = len(verts)
        verts += [(-hw * 0.7, 0, L * 0.93), (hw * 0.7, 0, L * 0.93), (0, 0, L + awn_len * 0.8)]
        cols += [W_EAR1, W_EAR1, W_AWN]
        faces.append((i0, i0 + 1, i0 + 2))
        raw(b, verts, faces, cols, 'plant')


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


def item_wheat():
    b = Builder('item_wheat', 31)
    r = b.rng
    H, tie = 0.47, 0.165
    flute = lambda a, z: 1.0 + 0.07 * math.sin(11 * a + 6 * z)
    b.lathe([(0, 0.004), (0.046, 0.004), (0.05, 0.02), (0.034, tie), (0.04, 0.25), (0.052, 0.31), (0, 0.32)], mat='plant', segs=14,
            color=mul(W_STEM0, 0.8), color_top=mul(W_STEM1, 0.9), radial=flute)
    N = 30
    tw = 0.45
    for k in range(N):
        a = k * 2.39996
        rho = math.sqrt((k + 0.5) / N)
        rb, rt_, rtop = 0.056 * rho + 0.004, 0.031 * rho + 0.004, 0.125 * rho ** 0.8 + 0.01
        h = H * r.uniform(0.74, 0.86) * (1.0 - 0.12 * rho)
        p0 = Vector((rb * math.cos(a), rb * math.sin(a), r.uniform(0.0, 0.014)))
        p1 = Vector((rt_ * math.cos(a + tw), rt_ * math.sin(a + tw), tie))
        p3 = Vector((rtop * math.cos(a + 2 * tw), rtop * math.sin(a + 2 * tw), h))
        p2 = p1.lerp(p3, 0.5) + Vector((0, 0, 0.012)) - Vector((p3.x, p3.y, 0)) * 0.12
        b.tube([p0, p1, p2, p3], lambda t: 0.0042 * (1 - 0.3 * t), mat='plant', segs=4, caps=False, color=W_STEM0, color_top=W_STEM1, jitter=0.1)
        out = Vector((math.cos(a + 2 * tw), math.sin(a + 2 * tw), 0))
        d = ((p3 - p2).normalized() + out * (0.25 + 0.55 * rho) + Vector((0, 0, -0.1 - 0.35 * rho))).normalized()
        wheat_ear(b, p3, d, r.uniform(0.088, 0.108), 0.0175, 0.06)
    # twine: two wraps and a bow at the front
    for dz, tilt in ((-0.006, 5), (0.006, -4)):
        with b.at((0, 0, tie + dz), (tilt, tilt * 0.6, 0)):
            torus(b, 0.0375, 0.0042, 0, n=6, mat='rope', segs=20)
    bow(b, (0.006, -0.041, tie), (0, -1, 0), r=0.0036, s=0.9)
    return b.build(sharp_angle=80)


def tomato(b, loc, r, col, rot, yaw_calyx=0.0):
    hi = mix(col, srgb(250, 170, 90), 0.5)
    sh = mix(col, srgb(206, 150, 50), 0.55)

    def cf(co):
        c = mix(col, hi, smooth(0.2 * r, 0.75 * r, co.z) * 0.3)
        c = mix(c, sh, smooth(0.55 * r, 0.8 * r, co.z) * smooth(0.5 * r, 0.1 * r, math.hypot(co.x, co.y)) * 0.8)
        return mix(c, mul(col, 0.72), smooth(-0.3 * r, -0.8 * r, co.z) * 0.6)

    prof = smooth_profile([(0, -0.76), (0.42, -0.72), (0.84, -0.44), (1.0, 0.0), (0.92, 0.40), (0.60, 0.70), (0.22, 0.77), (0, 0.70)], 2)
    lobes = lambda a, z: 1.0 + 0.03 * math.cos(5 * a) * smooth(0.0, 0.6, z / r) + 0.012 * math.sin(2 * a + 1)
    with b.at(loc, rot):
        b.lathe([(p[0] * r, p[1] * r) for p in prof], mat='plant_glossy', segs=20, color=cf, radial=lobes)
        for k in range(5):
            b.leaf(r * 0.82, r * 0.42, loc=(0, 0, 0.725 * r), rot=(0, 66 + b.rng.uniform(-8, 8), yaw_calyx + k * 72 + b.rng.uniform(-10, 10)),
                   bend=30 + b.rng.uniform(-22, 10), fold=22, segs=3, color=T_SEPAL0, color_top=T_SEPAL1)
        b.tube([(0, 0, 0.68 * r), (0.01 * r, 0, 0.9 * r), (0.1 * r, 0.04 * r, 1.12 * r)], [0.085 * r, 0.075 * r, 0.085 * r], mat='plant', segs=6,
               color=srgb(98, 142, 60), color_top=srgb(132, 150, 70))


def item_tomato():
    b = Builder('item_tomato', 32)
    tomato(b, (-0.040, -0.012, 0.0335), 0.044, T_RED, (10, -14, 20))
    tomato(b, (0.043, -0.02, 0.030), 0.0395, mix(T_RED, T_ORANGE, 0.22), (16, 12, 110), yaw_calyx=30)
    tomato(b, (0.008, 0.052, 0.0285), 0.0375, T_RED, (-18, 6, 200), yaw_calyx=10)
    return b.build(sharp_angle=80)


def item_pumpkin():
    b = Builder('item_pumpkin', 33)
    R, h, ribs = 0.17, 0.235, 9
    prof = smooth_profile([(0, 0.035), (0.30, 0.006), (0.62, 0.02), (0.89, 0.19), (1.0, 0.47), (0.93, 0.74), (0.68, 0.93), (0.34, 0.995),
                           (0.12, 0.95), (0, 0.9)], 2)

    def rad(a, z):
        return (1 - 0.105 * (1 - abs(math.sin(ribs / 2 * a))) ** 1.5) * (1 + 0.03 * math.sin(a + 1.0) + 0.02 * math.sin(2 * a + 0.4))

    def cf(co):
        a = math.atan2(co.y, co.x)
        g = (1 - abs(math.sin(ribs / 2 * a))) ** 2.2
        c = mix(P_RIB, P_GROOVE, g * 0.9)
        c = mix(c, P_TOP, smooth(0.45 * h, 1.0 * h, co.z) * 0.3 * (1 - g))
        c = mix(c, mul(P_GROOVE, 0.85), smooth(0.2 * h, 0.0, co.z) * 0.5)
        return mix(c, srgb(246, 178, 70), 0.35 * math.exp(-((a - 2.3) / 0.5) ** 2) * smooth(0.1 * h, 0.4 * h, co.z) * (1 - g))   # pale ground spot

    b.lathe([(p[0] * R, p[1] * h) for p in prof], rot=(2, -3, 14), mat='plant_glossy', segs=54, color=cf, radial=rad)
    # stem: flared ribbed collar, then a thick twisting stalk with a cut end
    st0, st1 = srgb(96, 112, 54), srgb(160, 152, 88)
    star5 = lambda a, z: 1.0 + 0.16 * math.cos(5 * a)
    z0 = 0.9 * h
    b.lathe([(0.052, z0 - 0.012), (0.036, z0 + 0.004), (0.026, z0 + 0.02), (0.021, z0 + 0.04), (0, z0 + 0.04)], mat='plant', segs=20,
            color=mul(st0, 0.85), color_top=st0, radial=star5)
    pts = [(0, 0, z0 + 0.03), (0.004, -0.003, z0 + 0.055), (0.018, -0.012, z0 + 0.078), (0.04, -0.024, z0 + 0.09), (0.058, -0.034, z0 + 0.089)]
    b.tube(pts, [0.021, 0.0185, 0.017, 0.0175, 0.0195], mat='plant', segs=7, color=st0, color_top=st1)
    # curly tendril
    tp = []
    for i in range(22):
        t = i / 21
        a = t * 2 * pi * 2.6 + 1.0
        rr = 0.022 * (1 - 0.55 * t)
        tp.append((-0.03 - 0.085 * t + rr * math.cos(a) * 0.5, 0.01 + rr * math.cos(a), z0 + 0.012 + 0.02 * math.sin(t * pi) + rr * math.sin(a) + 0.01))
    tp = [(-0.012, 0.004, z0 + 0.012)] + tp
    b.tube(tp, lambda t: 0.0042 * (1 - 0.55 * t), mat='plant', segs=5, color=srgb(86, 130, 52), color_top=srgb(150, 186, 90))
    # one small leaf still attached
    hub = Vector((0.05, 0.065, z0 + 0.03))
    b.tube([(0.012, 0.012, z0 + 0.012), (0.03, 0.04, z0 + 0.035), tuple(hub)], 0.0045, mat='plant', segs=5, color=srgb(86, 130, 52))
    disc_leaf(b, 0.075, hub, (-14, 8, 55), srgb(104, 158, 64), srgb(58, 118, 44), srgb(42, 96, 40), lobes=5, amp=0.085, n=15, cup=0.16,
              notch=0.42, wav=0.06)
    return b.build(sharp_angle=80)


# ---------------------------------------------------------------- flour sack
SACK_R = (0.118, 0.098, 0.135)
SACK_Z = 0.118
FLOUR_CLOTH, FLOUR_CLOTH_D = srgb(226, 208, 172), srgb(186, 164, 124)
STAMP = srgb(150, 62, 44)


def sack_deform(c):
    c = c.copy()
    a = math.atan2(c.y, c.x)
    t = max(0.0, min(1.0, (c.z - 0.015) / 0.115))
    k = 1.0 - 0.60 * t * t                                        # pinch toward the tied neck
    k *= 1.0 + 0.07 * smooth(0.0, -0.1, c.z)                      # the flour sags into the bottom
    k *= 1.0 + 0.045 * t * math.sin(9 * a + 0.6)                  # gathers under the tie
    k *= 1.0 + 0.02 * math.sin(3 * a + 1.0) * (1 - t)
    return Vector((c.x * k, c.y * k, c.z))


def sack_pt(az, el, lift=0.0):
    """Point on the sack + outward normal. az 0 = front (-Y), el = elevation, both in degrees."""
    def P(a, e):
        a, e = math.radians(a), math.radians(e)
        d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
        if d.z < -0.8:
            d.z = -0.8
        return sack_deform(Vector((d.x * SACK_R[0], d.y * SACK_R[1], d.z * SACK_R[2]))) + Vector((0, 0, SACK_Z - 0.8 * SACK_R[2] * 0 - 0.010))
    p = P(az, el)
    n = (P(az + 2, el) - P(az - 2, el)).cross(P(az, el + 2) - P(az, el - 2)).normalized()
    return p + n * lift, n


def item_flour():
    b = Builder('item_flour', 34)

    def cc(co):
        return mix(FLOUR_CLOTH_D, FLOUR_CLOTH, smooth(-0.11, 0.02, co.z)) if True else FLOUR_CLOTH

    b.blob(SACK_R, loc=(0, 0, SACK_Z - 0.010), mat='cloth', subdiv=4, flatten_bottom=-0.8, deform=sack_deform, color=cc)
    zt = SACK_Z - 0.010 + SACK_R[2]            # top of the body
    zn = zt - 0.012                            # tie height
    ruf = lambda a, z: 1.0 + 0.11 * math.sin(9 * a + 0.6) * smooth(0.0, 0.035, z - zn)
    b.lathe([(0.048, zn - 0.03), (0.039, zn - 0.008), (0.040, zn + 0.006), (0.057, zn + 0.034), (0.072, zn + 0.058), (0.068, zn + 0.061),
             (0.052, zn + 0.038), (0.03, zn + 0.016), (0, zn + 0.016)], mat='cloth', segs=27, color=mul(FLOUR_CLOTH, 0.94),
            color_top=FLOUR_CLOTH, radial=ruf)
    torus(b, 0.041, 0.0055, zn, n=5, mat='rope', segs=16)
    torus(b, 0.0415, 0.0052, zn + 0.008, n=5, mat='rope', segs=16)
    bow(b, (0.012, -0.043, zn + 0.004), (0.2, -1, 0), r=0.0044, s=1.15)
    # flour: a heap in the open neck, a puff spilt down the shoulder, a dusting on the ground
    fl = srgb(250, 247, 238)
    b.blob((0.047, 0.047, 0.026), loc=(0, 0, zn + 0.03), mat='paint', subdiv=3, noise_amp=0.06, noise_scale=2.0, color=mul(fl, 0.9), color_top=fl)
    for az, el, s in ((-62, 46, 1.0), (-78, 35, 0.8), (-52, 31, 0.65)):
        p, n = sack_pt(az, el, 0.002)
        b.blob((0.024 * s, 0.024 * s, 0.009 * s), loc=p, rot=basis_rot(n, (0, 0, 1)), mat='paint', subdiv=2, noise_amp=0.05, color=fl)
    for x, y, s in ((-0.125, -0.075, 1.0), (-0.165, -0.04, 0.6), (-0.09, -0.115, 0.5)):
        b.blob((0.045 * s, 0.038 * s, 0.016 * s), loc=(x, y, 0.004 * s), mat='paint', subdiv=2, noise_amp=0.04, flatten_bottom=-0.3,
               color=mul(fl, 0.92), color_top=fl)
    # stamped wheat-ear motif inside a ring
    b.tube([sack_pt(0, el, 0.0012)[0] for el in (-34, -24, -14, -4, 6, 14)], 0.0022, mat='paint', segs=5, color=STAMP)
    for i, el in enumerate((-12, -4, 4, 12)):
        for sg in (-1, 1):
            p, n = sack_pt(sg * 1.2, el + 1, 0.0012)
            up = Vector((sg * 0.62, 0, 0.78))
            feather(b, p - n * 0.0012, basis_rot(up, up.cross(n)), 0.031 - i * 0.002, 0.0078, 0.0036, mat='paint', color=STAMP, segs=5)
    p, n = sack_pt(0, 21, 0.0012)
    feather(b, p - n * 0.0012, basis_rot((0, 0, 1), (1, 0, 0)), 0.028, 0.0078, 0.0036, mat='paint', color=STAMP, segs=5)
    ring = []
    for k in range(25):
        a = 2 * pi * k / 24
        ring.append(sack_pt(33 * math.sin(a), -6 + 31 * math.cos(a), 0.0012)[0])
    b.tube(ring, 0.0019, mat='paint', segs=4, caps=False, color=STAMP)
    # a stitched side seam and a darker patch
    for sg in (-1, 1):
        b.tube([sack_pt(sg * 88, el, 0.0005)[0] for el in (-40, -22, -4, 14, 30, 44)], 0.0022, mat='cloth', segs=4, caps=False, color=mul(FLOUR_CLOTH_D, 0.9))
    return b.build(sharp_angle=75)


def item_eggs():
    b = Builder('item_eggs', 35)
    r = b.rng
    nz = lambda a, z: 1.0 + 0.045 * math.sin(5 * a + 0.4) + 0.03 * math.sin(9 * a + 1.3)

    def nest_c(co):
        rr = math.hypot(co.x, co.y)
        return mul((1.0, 0.95, 0.84), 0.5 + 0.5 * smooth(0.03, 0.095, rr))

    NS = 0.86
    b.lathe([(0, 0.0), (0.062, 0.0), (0.094, 0.011), (0.108, 0.033), (0.101, 0.052), (0.086, 0.052), (0.071, 0.032), (0.04, 0.019), (0, 0.017)],
            scale=(NS, NS, 1), mat='straw', segs=24, color=nest_c, radial=nz)
    for k in range(64):
        a0 = r.uniform(0, 2 * pi)
        span = r.uniform(0.9, 2.2)
        R0 = r.uniform(0.07, 0.112)
        z0 = 0.008 + 0.05 * smooth(0.062, 0.1, R0) * r.uniform(0.75, 1.15) if R0 < 0.1 else r.uniform(0.012, 0.05)
        tilt = r.uniform(-0.016, 0.016)
        drift = r.uniform(-0.012, 0.012)
        pts = []
        for i in range(5):
            t = i / 4
            a = a0 + span * t
            R1 = R0 + drift * t
            pts.append((NS * R1 * math.cos(a), NS * R1 * math.sin(a), max(0.004, z0 + tilt * math.sin(t * pi) + 0.006 * (t - 0.5))))
        k_ = r.uniform(0.62, 1.12)
        b.tube(pts, r.uniform(0.0022, 0.0032), mat='straw', segs=3, caps=False, color=(k_, k_ * 0.95, k_ * 0.82))
    for k in range(14):            # loose ends poking out
        a = r.uniform(0, 2 * pi)
        R0 = r.uniform(0.085, 0.105)
        p0 = Vector((NS * R0 * math.cos(a), NS * R0 * math.sin(a), r.uniform(0.015, 0.05)))
        d = Vector((math.cos(a + r.uniform(-1.2, 1.2)), math.sin(a + r.uniform(-1.2, 1.2)), r.uniform(-0.1, 0.7))).normalized()
        k_ = r.uniform(0.8, 1.15)
        b.tube([p0, p0 + d * r.uniform(0.025, 0.05)], 0.0022, mat='straw', segs=3, caps=False, color=(k_, k_ * 0.95, k_ * 0.82))
    egg = smooth_profile([(0, 0), (0.55, 0.05), (0.88, 0.22), (1.0, 0.44), (0.9, 0.68), (0.62, 0.88), (0.28, 0.985), (0, 1.0)], 2)
    for (x, y, z), rot, col, s in (((-0.026, -0.018, 0.036), (62, 0, 35), srgb(244, 230, 200), 1.0),
                                   ((0.030, -0.010, 0.035), (-66, 10, 20), srgb(196, 140, 98), 1.04),
                                   ((0.002, 0.030, 0.039), (58, 0, 170), srgb(226, 190, 152), 0.97)):
        rr, L = 0.0225 * s, 0.059 * s

        def ec(co, col=col, L=L):
            return mix(mul(col, 0.9), col, smooth(0.0, 0.5 * L, co.z))
        with b.at((x, y, z), rot):
            b.lathe([(p[0] * rr, (p[1] - 0.45) * L) for p in egg], mat='paint', segs=16, color=ec)
    return b.build(sharp_angle=80)


# ---------------------------------------------------------------- bread
LOAF_R = (0.066, 0.132, 0.056)
LOAF_Z = 0.0415


def loaf_taper(y):
    return 1.0 - 0.3 * abs(y / LOAF_R[1]) ** 3


def loaf_top(x, y):
    k = loaf_taper(y)
    q = 1.0 - (x / (LOAF_R[0] * k)) ** 2 - (y / LOAF_R[1]) ** 2
    return LOAF_Z + LOAF_R[2] * k * math.sqrt(max(q, 0.0))


def item_bread():
    b = Builder('item_bread', 36)

    def shape(c):
        k = loaf_taper(c.y)
        return Vector((c.x * k, c.y, c.z * k if c.z > 0 else c.z))

    def crust(co):
        up = smooth(-0.02, 0.05, co.z)
        c = mix(CRUST_L, CRUST, smooth(-0.045, -0.012, co.z))
        c = mix(c, CRUST_D, 0.75 * up * smooth(0.015, 0.058, co.z))
        blot = noise.noise(Vector((co.x * 26, co.y * 26, co.z * 26)))
        c = mul(c, 1.0 + 0.20 * blot)
        dust = smooth(0.25, 0.6, noise.noise(Vector((co.x * 60 + 3, co.y * 60, co.z * 60)))) * smooth(0.0, 0.04, co.z)
        return mix(c, srgb(244, 232, 206), 0.5 * dust)

    b.blob(LOAF_R, loc=(0, 0, LOAF_Z), mat='paint', subdiv=4, noise_amp=0.035, noise_scale=2.6, seed=3, flatten_bottom=-0.74, deform=shape, color=crust)
    # scores: a pale opened gash with a dark raised ear along one lip
    phi = math.radians(32)
    for yc in (-0.078, -0.027, 0.024, 0.075):
        nu, nv = 9, 4
        verts, cols, faces = [], [], []
        ear_pts = []
        for i in range(nu + 1):
            u = -1 + 2 * i / nu
            w = 0.0125 * (1 - abs(u) ** 2.4) + 0.0015
            for j in range(nv + 1):
                v = -1 + 2 * j / nv
                x = u * 0.043 * math.cos(phi) - v * w * math.sin(phi)
                y = yc + u * 0.043 * math.sin(phi) + v * w * math.cos(phi)
                edge = abs(v) > 0.99 or abs(u) > 0.99
                z = loaf_top(x, y) + (-0.003 if edge else 0.0035 - 0.002 * v * v)
                verts.append((x, y, z))
                cols.append(mix(CRUST_L, srgb(246, 222, 172), 1 - abs(v)) if not edge else CRUST)
                if j == nv and 0 < i < nu:
                    ear_pts.append((x, y, loaf_top(x, y) + 0.0035))
        for i in range(nu):
            for j in range(nv):
                a = i * (nv + 1) + j
                faces.append((a, a + nv + 1, a + nv + 2, a + 1))
        raw(b, verts, faces, cols, 'paint')
        b.tube(ear_pts, lambda t: 0.0042 * (0.45 + 0.55 * math.sin(pi * t)), mat='paint', segs=6, color=mul(CRUST_D, 0.82))
    return b.build(sharp_angle=80)


# ---------------------------------------------------------------- pie
def item_pie():
    b = Builder('item_pie', 37)
    tin = [(0, 0), (0.088, 0), (0.093, 0.003), (0.119, 0.034), (0.128, 0.0355), (0.1295, 0.038), (0.128, 0.0395), (0.118, 0.0385),
           (0.0915, 0.0065), (0.087, 0.0045), (0, 0.0045)]
    b.lathe(tin, mat='metal', segs=40, color=(0.95, 0.95, 0.97))
    A0, A1 = -62.0, 242.0            # the missing slice faces the front
    PIE_F, PIE_F_D, PIE_F_CUT = srgb(204, 116, 44), srgb(160, 78, 32), srgb(224, 142, 60)
    PC, PC_D = srgb(226, 176, 104), srgb(178, 112, 54)

    def crimp(a, z):
        return 1.0 + 0.036 * math.sin(22 * a) * smooth(0.0415, 0.047, z)

    def crust_c(co):
        rr = math.hypot(co.x, co.y)
        a = math.atan2(co.y, co.x)
        peak = 0.5 + 0.5 * math.sin(22 * a)
        c = mix(PC, PC_D, 0.6 * peak * smooth(0.044, 0.053, co.z))
        return mix(c, PC_D, 0.35 * smooth(0.112, 0.104, rr) * smooth(0.04, 0.05, co.z))

    crust = [(0, 0.005), (0.0868, 0.005), (0.0915, 0.0075), (0.1175, 0.039), (0.126, 0.041), (0.131, 0.0445), (0.1305, 0.050), (0.1245, 0.0548),
             (0.116, 0.0555), (0.109, 0.052), (0.1055, 0.045), (0.103, 0.0405), (0.0, 0.0405)]
    plathe(b, crust, A0, A1, 66, 'paint', crust_c, radial=crimp, cap_color=lambda co: PIE_F_CUT if 0.0095 < co.z < 0.0395 and math.hypot(co.x, co.y) < 0.102 else PC)

    def fill_c(co):
        rr = math.hypot(co.x, co.y)
        blot = noise.noise(Vector((co.x * 30, co.y * 30, 0)))
        return mul(mix(PIE_F, PIE_F_D, smooth(0.07, 0.104, rr) * 0.8), 1.0 + 0.08 * blot)

    fill = [(0, 0.040), (0.103, 0.040), (0.1045, 0.0425), (0.098, 0.0445), (0.06, 0.0462), (0, 0.0468)]
    plathe(b, fill, A0, A1, 44, 'plant_glossy', fill_c, cap_color=PIE_F_CUT)
    # whipped cream swirl
    sw = lambda a, z: 1.0 + 0.13 * math.sin(6 * a + z * 170)
    b.lathe([(0, 0), (0.021, 0.001), (0.027, 0.007), (0.024, 0.014), (0.016, 0.02), (0.009, 0.026), (0.004, 0.032), (0, 0.035)],
            loc=(-0.012, 0.042, 0.0455), mat='paint', segs=24, color=srgb(240, 230, 208), color_top=srgb(255, 252, 244), radial=sw)
    # crumbs left in the empty slice
    for x, y, s in ((0.012, -0.05, 1.0), (-0.016, -0.072, 0.7), (0.03, -0.082, 0.8), (0.004, -0.092, 0.55), (-0.004, -0.03, 0.6)):
        b.blob((0.006 * s, 0.005 * s, 0.0035 * s), loc=(x, y, 0.0055), rot=(0, 0, x * 900), mat='paint', subdiv=1, color=mix(PC, PIE_F, 0.3 + 3 * abs(x)))
    return b.build(sharp_angle=60)


# ---------------------------------------------------------------- chutney
def item_chutney():
    b = Builder('item_chutney', 38)
    JR, JH = 0.040, 0.096
    C_DEEP, C_RED, C_BIT = srgb(138, 26, 18), srgb(192, 54, 30), srgb(226, 120, 50)
    GLASS = srgb(196, 220, 210)

    def jar_c(co):
        a = math.atan2(co.y, co.x)
        if co.z < 0.0045 or co.z > 0.079:
            c = GLASS if co.z > 0.079 else mix(C_DEEP, GLASS, 0.45)
        else:
            n1 = noise.noise(Vector((co.x * 55, co.y * 55, co.z * 55)))
            n2 = noise.noise(Vector((co.x * 120 + 5, co.y * 120, co.z * 120)))
            c = mix(C_DEEP, C_RED, 0.5 + 0.9 * n1)
            c = mix(c, C_BIT, smooth(0.28, 0.5, n2) * 0.7)
        hl = math.exp(-((a + 2.2) / 0.16) ** 2) * smooth(0.006, 0.02, co.z) * smooth(0.082, 0.07, co.z)   # fake reflection streak
        return mix(c, srgb(255, 236, 226), 0.38 * hl)

    jar = [(0, 0), (0.033, 0), (0.038, 0.003), (JR, 0.010), (JR, 0.030), (JR, 0.052), (JR, 0.072), (0.0385, 0.079), (0.0345, 0.085),
           (0.0335, 0.088), (0.0345, 0.090), (0.0345, JH), (0, JH)]
    b.lathe(jar, mat='plant_glossy', segs=28, color=jar_c)
    # gingham cloth cap: a square of cloth draped over the lid and cinched with string
    zt, rl, drop = JH + 0.0012, 0.0352, 0.011
    N, cell = 20, 0.0062
    RED, PINK, CREAM = srgb(190, 46, 44), srgb(228, 128, 122), srgb(246, 238, 226)

    def drape(u, v, off):
        rho = math.hypot(u, v)
        a = math.atan2(v, u)
        if rho <= rl - 0.003:
            r_, z_ = rho, zt + 0.0006 * (1 - (rho / rl) ** 2)
        elif rho <= rl + drop:
            t = (rho - (rl - 0.003)) / (drop + 0.003)
            r_ = rl - 0.003 + 0.0042 * math.sin(min(1.0, t * 2.2) * pi / 2) - 0.0012 * smooth(0.5, 1.0, t)
            z_ = zt - (drop) * t ** 1.3
        else:
            s_ = rho - (rl + drop)
            pleat = math.sin(10 * a + 0.7)
            r_ = rl + s_ * (0.62 + 0.20 * pleat) - s_ * s_ * 2.0 + 0.0008
            z_ = zt - drop - s_ * (0.72 - 0.12 * pleat) - s_ * s_ * 7.0
        r_ += off
        return (r_ * math.cos(a), r_ * math.sin(a), z_ + off * 0.3)

    for off, flip in ((0.0, False), (-0.0012, True)):
        verts, faces, fcols, uvs = [], [], [], []
        for i in range(N + 1):
            for j in range(N + 1):
                u, v = (i - N / 2) * cell, (j - N / 2) * cell
                verts.append(drape(u, v, off))
                uvs.append((u, v))
        for i in range(N):
            for j in range(N):
                a_ = i * (N + 1) + j
                q = (a_, a_ + N + 1, a_ + N + 2, a_ + 1)
                faces.append(tuple(reversed(q)) if flip else q)
                k = (i % 2) + (j % 2)
                c = (CREAM, PINK, RED)[k]
                fcols.append(mul(c, 0.8) if flip else c)
        raw(b, verts, faces, WHITE, 'cloth', face_cols=fcols, uvs=uvs)
    zs = zt - drop
    torus(b, rl + 0.0012, 0.0017, zs + 0.0005, n=6, mat='rope', segs=24)
    bow(b, (0.004, -(rl + 0.003), zs), (0, -1, 0), r=0.0017, s=0.5)
    # paper label
    LAB, INK = srgb(240, 230, 204), srgb(96, 70, 52)
    nu = 10
    verts, faces = [], []
    a0, a1, z0, z1 = -36, 36, 0.019, 0.055
    for i in range(nu + 1):
        a = math.radians(-90 + a0 + (a1 - a0) * i / nu)
        for z in (z0, z1):
            verts.append(((JR + 0.0007) * math.cos(a), (JR + 0.0007) * math.sin(a), z))
    for i in range(nu):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    raw(b, verts, faces, LAB, 'paint')
    for zz, half, hw in ((0.0275, 20, 0.0011), (0.0235, 14, 0.0009)):       # two lines of "writing"
        verts, faces = [], []
        for i in range(7):
            a = math.radians(-90 - half + 2 * half * i / 6)
            for z in (zz - hw, zz + hw):
                verts.append(((JR + 0.0011) * math.cos(a), (JR + 0.0011) * math.sin(a), z))
        for i in range(6):
            faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
        raw(b, verts, faces, INK, 'paint')
    b.blob((0.0085, 0.0022, 0.0078), loc=(0, -(JR + 0.0012), 0.042), mat='paint', subdiv=2, color=T_RED)       # little painted tomato
    b.blob((0.0042, 0.0012, 0.002), loc=(0.0005, -(JR + 0.0022), 0.0492), mat='paint', subdiv=1, color=T_SEPAL0)
    return b.build(sharp_angle=60)


# ================================================================ HEN
def build_chicken(name, pal):
    BODY, BREAST, DARK, HACKLE, TAILC, TAILT = pal
    COMB = srgb(204, 42, 38)
    BEAK, LEG = srgb(236, 178, 66), srgb(228, 170, 56)
    b = Builder(name, 51)
    C = Vector((0, 0.02, 0.205))
    BR = (0.104, 0.150, 0.108)

    def body_def(c):
        c = c.copy()
        if c.y > 0:
            t = c.y / BR[1]
            c.z += 0.085 * t * t                       # back sweeps up to the tail
            c.x *= 1.0 - 0.42 * t ** 2.2
        else:
            t = -c.y / BR[1]
            c.z -= 0.012 * t                           # full, low breast
            c.z += 0.03 * t * t * smooth(0.0, 0.08, c.z)
        return c

    def body_c(co):
        up = smooth(-0.06, 0.06, co.z)
        c = mix(BREAST, BODY, up)
        c = mix(c, DARK, 0.5 * smooth(0.06, 0.16, co.y) * up)
        sc = 0.5 + 0.5 * math.sin(co.y * 150 + math.sin(co.x * 90) * 1.5) * math.sin(co.z * 140 + co.x * 60)   # soft feather mottling
        return mul(c, 0.94 + 0.10 * sc)

    b.blob(BR, loc=C, mat='plant', subdiv=4, deform=body_def, color=body_c)
    for s in (-1, 1):
        # fluffy thighs
        b.blob((0.047, 0.055, 0.058), loc=(s * 0.05, 0.022, 0.125), mat='plant', subdiv=3, color=mul(BREAST, 0.96), color_top=BODY)
        # wing: a shield lying on the flank with three flight feathers
        def wing_def(c):
            t = smooth(-0.04, 0.10, c.y)
            return Vector((c.x, c.y, c.z * (1.0 - 0.45 * t) - 0.012 * t))
        with b.at((s * 0.098, 0.022, 0.222), (0, s * 7, s * -7)):
            b.blob((0.026, 0.100, 0.060), mat='plant', subdiv=3, deform=wing_def, color=mul(BODY, 0.80), color_top=mul(BODY, 1.05))
            for k, (dz, L, pit) in enumerate(((0.004, 0.100, 97), (-0.012, 0.100, 103), (-0.027, 0.085, 110))):
                feather(b, (s * 0.012, 0.022, dz), (-pit, 0, 0), L, 0.021, 0.0055, color=mul(BODY, 0.72), color_top=mix(BODY, DARK, 0.75), segs=6)
        # legs
        hip = Vector((s * 0.047, 0.025, 0.105))
        ank = Vector((s * 0.05, 0.02, 0.014))
        b.tube([hip, hip.lerp(ank, 0.5) + Vector((0, 0.004, 0)), ank], [0.0105, 0.008, 0.0085], mat='paint', segs=6, caps=False, color=LEG)
        b.blob(0.0105, loc=ank, mat='paint', subdiv=1, color=mul(LEG, 0.95))
        for yaw, L in ((0, 0.058), (34, 0.05), (-34, 0.05), (180, 0.03)):
            d = Vector((math.sin(math.radians(yaw)) * 1.0, -math.cos(math.radians(yaw)), 0))
            tip = ank + d * L + Vector((0, 0, -0.009))
            b.lathe([(0, 0), (0.0068, 0.004), (0.006, L * 0.6), (0.0035, L * 0.92), (0, L)], loc=ank + Vector((0, 0, -0.005)),
                    rot=aimz(tip - ank), mat='paint', segs=6, color=LEG, color_top=mul(LEG, 0.8))
    # tail: a tented fan
    T = C + Vector((0, 0.128, 0.086))
    for k, (side, pit, L) in enumerate(((0, 62, 0.15), (-1, 54, 0.14), (1, 54, 0.14), (-1, 42, 0.125), (1, 42, 0.125), (-1, 29, 0.105), (1, 29, 0.105),
                                        (-1, 16, 0.085), (1, 16, 0.085))):
        d = Vector((side * 0.20, math.cos(math.radians(pit)), math.sin(math.radians(pit))))
        rot = basis_rot(d, (1, 0, 0) if side == 0 else (side * 0.25, -0.5, 0.8))
        base = T + Vector((side * 0.014, -0.03 + 0.0, -0.012 - 0.0006 * (62 - pit)))
        feather(b, base, rot, L * 1.05, 0.027, 0.0048, color=TAILC, color_top=TAILT, jitter=0.06, segs=7)
    root = b.build(sharp_angle=80)

    # ---- head + neck: separate object pivoting at the neck base
    h = Builder(name + '_head', 52)

    def neck_c(co):
        return mix(BODY, HACKLE, smooth(-0.01, 0.06, co.z))

    h.tube([(0, 0.022, -0.035), (0, 0.0, 0.02), (0, -0.016, 0.062), (0, -0.026, 0.096)], [0.068, 0.056, 0.042, 0.035], mat='plant', segs=12, color=neck_c)
    HC = Vector((0, -0.036, 0.112))
    h.blob((0.034, 0.044, 0.038), loc=HC, mat='plant', subdiv=3, color=mix(HACKLE, BODY, 0.3), color_top=HACKLE)
    # comb: five upright lobes along the crown
    for y, ht, lean in ((-0.070, 0.020, -26), (-0.055, 0.031, -12), (-0.038, 0.037, 0), (-0.020, 0.032, 14), (-0.004, 0.022, 32)):
        z = HC.z + 0.038 * math.sqrt(max(0.0, 1 - ((y - HC.y) / 0.044) ** 2)) - 0.006
        feather(h, (0, y, z), (lean, 0, 0), ht + 0.006, 0.0105, 0.0046, mat='paint', color=mul(COMB, 0.85), color_top=COMB, segs=5)
    for s in (-1, 1):
        # wattles, cheek patch, eye
        h.lathe([(0, 0), (0.006, -0.004), (0.012, -0.018), (0.0095, -0.030), (0, -0.036)], loc=(s * 0.0105, -0.070, 0.097), rot=(10, s * 8, 0),
                scale=(0.6, 1, 1), mat='paint', segs=8, color=mul(COMB, 0.9))
        h.blob((0.004, 0.014, 0.012), loc=(s * 0.0305, -0.052, 0.107), rot=(0, 0, s * 14), mat='paint', subdiv=2, color=mul(COMB, 0.92))
        h.blob((0.004, 0.0078, 0.0078), loc=(s * 0.0312, -0.057, 0.121), rot=(0, 0, s * 16), mat='eye', subdiv=2, color=WHITE)
        h.blob((0.0012, 0.002, 0.002), loc=(s * 0.0348, -0.0595, 0.1238), mat='paint', subdiv=1, color=WHITE)
    # beak
    h.lathe([(0, 0), (0.0135, 0.0), (0.0105, 0.012), (0.005, 0.026), (0, 0.034)], loc=(0, -0.074, 0.112), rot=(104, 0, 0), scale=(1, 0.72, 1),
            mat='paint', segs=10, color=BEAK, color_top=mul(BEAK, 0.82))
    h.lathe([(0, 0), (0.0095, 0.0), (0.006, 0.012), (0, 0.022)], loc=(0, -0.074, 0.1045), rot=(98, 0, 0), scale=(1, 0.5, 1), mat='paint', segs=8,
            color=mul(BEAK, 0.85))
    head = h.build(sharp_angle=80)
    kit.set_parent(head, root, (0, -0.082, 0.262))
    return root


RUSSET = (srgb(158, 82, 42), srgb(196, 122, 66), srgb(84, 44, 30), srgb(208, 134, 58), srgb(70, 40, 30), srgb(28, 34, 30))
SNOWY = (srgb(244, 240, 230), srgb(250, 248, 242), srgb(214, 206, 190), srgb(248, 244, 234), srgb(236, 230, 216), srgb(250, 248, 240))


# ================================================================ registry
ASSETS = {
    'fp_arm_r': lambda: build_arm('fp_arm_r', 'r'),
    'fp_arm_l': lambda: build_arm('fp_arm_l', 'l'),
    'item_wheat': item_wheat, 'item_tomato': item_tomato, 'item_pumpkin': item_pumpkin,
    'item_flour': item_flour, 'item_eggs': item_eggs,
    'item_bread': item_bread, 'item_pie': item_pie, 'item_chutney': item_chutney,
    'chicken': lambda: build_chicken('chicken', RUSSET),
    'chicken_white': lambda: build_chicken('chicken_white', SNOWY),
}
GROUPS = {
    'arms': ['fp_arm_r', 'fp_arm_l'],
    'crops': ['item_wheat', 'item_tomato', 'item_pumpkin'],
    'pantry': ['item_flour', 'item_eggs'],
    'baked': ['item_bread', 'item_pie', 'item_chutney'],
    'chicken': ['chicken', 'chicken_white'],
}


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
    print('[items] preview', sc.render.filepath)


def preview_handle(parent, length=1.1):
    """Preview-only wooden shaft through a grip marker (never exported)."""
    hb = Builder('_pv_handle_' + parent.name, 3)
    hb.tube([(-length * 0.45, 0, 0), (length * 0.55, 0, 0)], RH, mat='wood_light', segs=16)
    h = hb.build()
    h.parent = parent
    return h


def preview_arms(objs):
    r, l = objs['fp_arm_r'], objs['fp_arm_l']
    gr = next(c for c in r.children if c.name == 'fp_grip_r')
    h = preview_handle(gr)
    R = [r]
    shot('arm_r_34', R, az=-40, el=28)
    shot('arm_r_fp', R, cam_pos=(0.15, 0.34, 0.25), target=(0.0, -0.05, -0.01), lens=32, floor=False)
    shot('arm_r_hand_top', R, az=200, el=62, focus=((0, -0.07, -0.01), 0.10), floor=False)
    shot('arm_r_hand_front', R, az=25, el=12, focus=((0, -0.07, -0.02), 0.10), floor=False)
    shot('arm_r_hand_under', R, az=160, el=-40, focus=((0, -0.07, -0.02), 0.10), floor=False)
    shot('arm_r_hand_thumb', R, az=110, el=10, focus=((0, -0.06, -0.02), 0.10), floor=False)
    bpy.data.objects.remove(h)
    L = [l]
    shot('arm_l_34', L, az=40, el=28)
    shot('arm_l_fp', L, cam_pos=(-0.15, 0.34, 0.25), target=(0.0, -0.05, 0.0), lens=32, floor=False)
    shot('arm_l_hand_top', L, az=180, el=70, focus=((0, -0.08, 0.0), 0.12), floor=False)
    shot('arm_l_hand_front', L, az=-20, el=15, focus=((0, -0.08, 0.0), 0.12), floor=False)
    shot('arm_l_hand_side', L, az=-100, el=20, focus=((0, -0.08, 0.0), 0.12), floor=False)
    shot('arm_l_hand_back', L, az=120, el=-25, focus=((0, -0.08, 0.0), 0.12), floor=False)
    # both arms where a first-person camera would see them (camera at the origin looking forward and a bit down)
    r.location, r.rotation_euler = (-0.20, -0.40, -0.24), Euler((math.radians(-24), 0, math.radians(14)))
    l.location, l.rotation_euler = (0.19, -0.42, -0.25), Euler((math.radians(-24), 0, math.radians(-16)))
    bpy.context.view_layer.update()
    h = preview_handle(gr)
    shot('arms_fp', [r, l], cam_pos=(0, 0, 0), target=(0, -1.0, -0.42), lens=22, floor=False, size=(1280, 720))
    bpy.data.objects.remove(h)
    for o in (r, l):
        o.location, o.rotation_euler = (0, 0, 0), Euler((0, 0, 0))
    bpy.context.view_layer.update()


def preview_group(g, objs):
    sel = [objs[m] for m in GROUPS[g]]
    if g == 'arms':
        preview_arms(objs)
        return
    for o in sel:
        shot(o.name, [o], az=35, el=28)
        shot(o.name + '_b', [o], az=-140, el=18)
    sp = max(max(o.dimensions.x for o in sel) * 1.35, 0.2)
    for i, o in enumerate(sel):
        o.location.x = (i - (len(sel) - 1) / 2) * sp
    bpy.context.view_layer.update()
    shot('group_' + g, sel, az=25, el=24)
    for o in sel:
        o.location.x = 0
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
    names = [n for n in names if any(n in GROUPS[g] for g in ONLY)]
objs = {}
for n in names:
    objs[n] = ASSETS[n]()
    report(objs[n])
    print(f'   TOTAL {n} tris={kit.tri_count(kit._descend([objs[n]]))}')

if not ONLY:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    kit.export_glb(OUT, list(objs.values()))

if PREV:
    os.makedirs(PREV, exist_ok=True)
    for g in GROUPS:
        if ONLY and g not in ONLY:
            continue
        preview_group(g, objs)
