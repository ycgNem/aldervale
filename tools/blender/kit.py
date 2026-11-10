"""Shared modelling kit for the homestead demo (Blender 5.x, runs headless).

Conventions
- Metres. Blender Z-up while authoring; glTF export converts to Y-up.
- An asset's FRONT faces Blender -Y (becomes +Z in three.js). Origin = centre of its footprint on the ground.
- One Builder == one mesh object with several material slots (one glTF primitive per material).
- Materials are referenced BY NAME only (see PREVIEW). The game replaces them with its own PBR materials,
  so nothing here needs textures. UVs are in metres (1 UV unit == 1 m), wood grain runs along U.
- Vertex colours (attribute "Color", linear RGB) multiply the albedo in game:
    * hard-surface materials: near white, used for per-plank / per-stone tone variation
    * plant / plant_glossy / leaf / cloth / skin / hair / paint: carry the real colour (use srgb()).
"""
import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix, Euler, noise

# name -> preview colour (linear-ish), only used for Blender previews
PREVIEW = {
    'wood_plank': (0.42, 0.25, 0.13), 'wood_dark': (0.16, 0.09, 0.05), 'wood_light': (0.62, 0.45, 0.27),
    'bark': (0.20, 0.14, 0.10), 'stone': (0.45, 0.43, 0.40), 'roof': (0.45, 0.16, 0.10),
    'plaster': (0.80, 0.74, 0.62), 'paint': (1, 1, 1), 'glass': (0.35, 0.50, 0.60),
    'metal': (0.62, 0.63, 0.65), 'metal_dark': (0.08, 0.08, 0.09), 'rope': (0.55, 0.42, 0.25),
    'straw': (0.75, 0.58, 0.25), 'cloth': (1, 1, 1), 'skin': (1, 1, 1), 'hair': (1, 1, 1),
    'eye': (0.02, 0.02, 0.025), 'leather': (0.25, 0.13, 0.07), 'leaf': (1, 1, 1), 'plant': (1, 1, 1),
    'plant_glossy': (1, 1, 1), 'water_still': (0.10, 0.25, 0.32), 'soil': (0.14, 0.09, 0.06),
}
ROUGH = {'glass': 0.1, 'metal': 0.35, 'plant_glossy': 0.3, 'eye': 0.08, 'water_still': 0.05}


def srgb(r, g, b):
    """sRGB 0-255 -> linear RGB tuple (what vertex colours must contain)."""
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def get_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    if name not in PREVIEW:
        raise KeyError(f'unknown material "{name}" - use one of {sorted(PREVIEW)}')
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    vc = nt.nodes.new('ShaderNodeVertexColor')
    vc.layer_name = 'Color'
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1.0
    a = next(s for s in mix.inputs if s.identifier == 'A_Color')
    b = next(s for s in mix.inputs if s.identifier == 'B_Color')
    out = next(s for s in mix.outputs if s.identifier == 'Result_Color')
    a.default_value = (*PREVIEW[name], 1.0)
    nt.links.new(vc.outputs['Color'], b)
    nt.links.new(out, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = ROUGH.get(name, 0.75)
    if name in ('metal', 'metal_dark'):
        bsdf.inputs['Metallic'].default_value = 1.0
    return m


def _mat4(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    R = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix().to_4x4()
    S = Matrix.Diagonal((*scale, 1.0))
    return Matrix.Translation(Vector(loc)) @ R @ S


class Builder:
    """Accumulates primitives into one mesh. All `rot` values are XYZ euler DEGREES."""

    def __init__(self, name, seed=0):
        self.name = name
        self.rng = random.Random(seed)
        self.mats = []
        self.bm = bmesh.new()
        self._layers(self.bm)
        self.stack = [Matrix.Identity(4)]

    # ---- plumbing -------------------------------------------------------------
    @staticmethod
    def _layers(bm):
        uv = bm.loops.layers.uv.get('UVMap') or bm.loops.layers.uv.new('UVMap')
        col = bm.loops.layers.float_color.get('Color') or bm.loops.layers.float_color.new('Color')
        cn = bm.loops.layers.float_vector.get('cn') or bm.loops.layers.float_vector.new('cn')
        return uv, col, cn

    def _mi(self, mat):
        get_mat(mat)
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    class _Ctx:
        def __init__(self, b, m):
            self.b, self.m = b, m

        def __enter__(self):
            self.b.stack.append(self.b.stack[-1] @ self.m)

        def __exit__(self, *a):
            self.b.stack.pop()

    def at(self, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        """with b.at(loc, rot, scale): ... -> everything inside is placed in that local frame."""
        return Builder._Ctx(self, _mat4(loc, rot, scale))

    def _color(self, tbm, color, color_top, jitter, axis=2):
        _, col, _ = self._layers(tbm)
        j = 1.0 + self.rng.uniform(-jitter, jitter) if jitter else 1.0
        if not tbm.verts:
            return
        lo = min(v.co[axis] for v in tbm.verts)
        hi = max(v.co[axis] for v in tbm.verts)
        span = max(hi - lo, 1e-6)
        for f in tbm.faces:
            for l in f.loops:
                if callable(color):
                    c = color(l.vert.co)
                elif color_top is not None:
                    t = (l.vert.co[axis] - lo) / span
                    c = [color[i] * (1 - t) + color_top[i] * t for i in range(3)]
                else:
                    c = color
                l[col] = (c[0] * j, c[1] * j, c[2] * j, 1.0)

    def _box_uv(self, tbm, grain=None, uv_scale=1.0):
        uv, _, _ = self._layers(tbm)
        ou, ov = self.rng.random() * 7.0, self.rng.random() * 7.0
        for f in tbm.faces:
            n = f.normal
            a = max(range(3), key=lambda i: abs(n[i]))
            p, q = [i for i in range(3) if i != a]
            if grain is not None and grain != a:
                p, q = grain, (p if q == grain else q)
            for l in f.loops:
                l[uv].uv = (l.vert.co[p] * uv_scale + ou, l.vert.co[q] * uv_scale + ov)

    def _emit(self, tbm, mat, loc, rot, scale=(1, 1, 1), smooth=True):
        mi = self._mi(mat)
        M = self.stack[-1] @ _mat4(loc, rot, scale)
        flip = M.determinant() < 0
        N = M.to_3x3().inverted_safe().transposed()
        _, _, cn = self._layers(tbm)
        for v in tbm.verts:
            v.co = M @ v.co
        for f in tbm.faces:
            f.material_index = mi
            f.smooth = smooth
            for l in f.loops:
                c = Vector(l[cn])
                if c.length_squared > 0:
                    l[cn] = (N @ c).normalized()
        if flip:
            bmesh.ops.reverse_faces(tbm, faces=tbm.faces[:])
        tmp = bpy.data.meshes.new('_tmp')
        tbm.to_mesh(tmp)
        tbm.free()
        self.bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)

    def _new(self):
        t = bmesh.new()
        self._layers(t)
        return t

    # ---- primitives -----------------------------------------------------------
    def box(self, size, loc=(0, 0, 0), rot=(0, 0, 0), mat='wood_plank', bevel=0.012, segs=2,
            grain='auto', color=(1, 1, 1), color_top=None, jitter=0.0, taper=(1, 1), uv_scale=1.0):
        """Bevelled box centred on `loc`. size=(x,y,z). grain: 'auto' (longest axis), 0/1/2 or None.
        taper=(sx,sy) scales the top face (for tapered posts / shingles)."""
        t = self._new()
        bmesh.ops.create_cube(t, size=1.0)
        for v in t.verts:
            v.co.x *= size[0]
            v.co.y *= size[1]
            v.co.z *= size[2]
            if v.co.z > 0:
                v.co.x *= taper[0]
                v.co.y *= taper[1]
        b = min(bevel, min(size) * 0.45)
        if b > 1e-5:
            bmesh.ops.bevel(t, geom=t.edges[:], offset=b, offset_type='OFFSET', segments=segs,
                            profile=0.5, affect='EDGES', clamp_overlap=True)
        t.normal_update()
        g = max(range(3), key=lambda i: size[i]) if grain == 'auto' else grain
        self._box_uv(t, g, uv_scale)
        self._color(t, color, color_top, jitter)
        self._emit(t, mat, loc, rot)

    def prism(self, pts, depth, loc=(0, 0, 0), rot=(0, 0, 0), mat='plaster', bevel=0.01, segs=2,
              grain=None, color=(1, 1, 1), color_top=None, jitter=0.0, uv_scale=1.0):
        """Extrude a convex-ish 2D polygon (list of (x,z), counter-clockwise seen from -Y/front)
        along Y by `depth` (centred). Good for gable walls, roof slabs, signs."""
        t = self._new()
        front = [t.verts.new((x, -depth / 2, z)) for x, z in pts]
        back = [t.verts.new((x, depth / 2, z)) for x, z in pts]
        n = len(pts)
        t.faces.new(front)
        t.faces.new(list(reversed(back)))
        for i in range(n):
            j = (i + 1) % n
            t.faces.new((front[j], front[i], back[i], back[j]))
        bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
        if bevel > 1e-5:
            bmesh.ops.bevel(t, geom=t.edges[:], offset=bevel, offset_type='OFFSET', segments=segs,
                            profile=0.5, affect='EDGES', clamp_overlap=True)
        t.normal_update()
        self._box_uv(t, grain, uv_scale)
        self._color(t, color, color_top, jitter)
        self._emit(t, mat, loc, rot)

    def lathe(self, profile, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), mat='wood_plank', segs=24,
              color=(1, 1, 1), color_top=None, jitter=0.0, uv_scale=1.0, radial=None):
        """Revolve profile [(r,z),...] around local Z. Trace the profile counter-clockwise in the
        (r,z) half plane: start at the bottom, go outward and up (then inward and down for an
        inside wall). r=0 points become poles. Put two points close together for a crisp edge.
        radial(angle, z) -> multiplier on r (for lobes: pumpkins, fluting)."""
        t = self._new()
        uv, _, _ = self._layers(t)
        rmax = max(r for r, _ in profile) * max(abs(scale[0]), abs(scale[1]))
        arc = [0.0]
        for k in range(1, len(profile)):
            dr = (profile[k][0] - profile[k - 1][0]) * scale[0]
            dz = (profile[k][1] - profile[k - 1][1]) * scale[2]
            arc.append(arc[-1] + math.hypot(dr, dz))
        rings = []
        for r, z in profile:
            if r <= 1e-6:
                rings.append([t.verts.new((0, 0, z * scale[2]))])
            else:
                ring = []
                for i in range(segs):
                    a = 2 * math.pi * i / segs
                    m = radial(a, z) if radial else 1.0
                    ring.append(t.verts.new((r * m * math.cos(a) * scale[0], r * m * math.sin(a) * scale[1], z * scale[2])))
                rings.append(ring)
        ou, ov = self.rng.random() * 5, self.rng.random() * 5
        circ = 2 * math.pi * rmax

        def U(i):
            return i / segs * circ * uv_scale + ou

        for k in range(len(profile) - 1):
            A, B = rings[k], rings[k + 1]
            va, vb = arc[k] * uv_scale + ov, arc[k + 1] * uv_scale + ov
            for i in range(segs):
                j = (i + 1) % segs
                if len(A) == 1 and len(B) == 1:
                    continue
                if len(A) == 1:
                    f = t.faces.new((A[0], B[j], B[i]))
                    uvs = [(U(i + 0.5), va), (U(i + 1), vb), (U(i), vb)]
                elif len(B) == 1:
                    f = t.faces.new((A[i], A[j], B[0]))
                    uvs = [(U(i), va), (U(i + 1), va), (U(i + 0.5), vb)]
                else:
                    f = t.faces.new((A[i], A[j], B[j], B[i]))
                    uvs = [(U(i), va), (U(i + 1), va), (U(i + 1), vb), (U(i), vb)]
                for l, w in zip(f.loops, uvs):
                    l[uv].uv = w
        t.normal_update()
        self._color(t, color, color_top, jitter)
        self._emit(t, mat, loc, rot)

    def cyl(self, r, h, loc=(0, 0, 0), rot=(0, 0, 0), mat='wood_plank', segs=20, bevel=0.01, r_top=None, **kw):
        """Capped cylinder / cone frustum standing on local z=0 with rounded rims."""
        rt = r if r_top is None else r_top
        b = min(bevel, r * 0.4, h * 0.4)
        prof = [(0, 0), (max(r - b, 1e-4), 0), (r, b), (rt, h - b), (max(rt - b, 1e-4), h), (0, h)]
        self.lathe(prof, loc, rot, mat=mat, segs=segs, **kw)

    def tube(self, pts, radius, loc=(0, 0, 0), rot=(0, 0, 0), mat='plant', segs=8, caps=True,
             color=(1, 1, 1), color_top=None, jitter=0.0, uv_scale=1.0):
        """Sweep a circle along a polyline. radius: number, list (per point) or fn(t in 0..1).
        caps=True rounds both ends. Use for stems, vines, handles, limbs, rope."""
        t = self._new()
        uv, col, _ = self._layers(t)
        P = [Vector(p) for p in pts]
        n = len(P)

        def rad(i):
            if callable(radius):
                return radius(i / max(n - 1, 1))
            if isinstance(radius, (list, tuple)):
                return radius[i]
            return radius

        tang = []
        for i in range(n):
            d = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)])
            tang.append(d.normalized() if d.length > 1e-9 else Vector((0, 0, 1)))
        ref = Vector((1, 0, 0)) if abs(tang[0].x) < 0.9 else Vector((0, 1, 0))
        nx = (ref - tang[0] * ref.dot(tang[0])).normalized()
        frames = []
        for i in range(n):
            if i > 0:
                nx = (nx - tang[i] * nx.dot(tang[i]))
                nx = nx.normalized() if nx.length > 1e-9 else frames[-1][0]
            frames.append((nx.copy(), tang[i].cross(nx).normalized()))
        # stations: (centre, radius, frame index, v, t)
        st = []
        length = [0.0]
        for i in range(1, n):
            length.append(length[-1] + (P[i] - P[i - 1]).length)
        total = max(length[-1], 1e-6)
        if caps:
            r0 = rad(0)
            st.append((P[0] - tang[0] * r0, 0.0, 0, -r0, 0.0))
            for a in (0.35, 0.7):
                st.append((P[0] - tang[0] * r0 * math.cos(a * math.pi / 2), r0 * math.sin(a * math.pi / 2), 0, -r0 * (1 - a), 0.0))
        for i in range(n):
            st.append((P[i], rad(i), i, length[i], length[i] / total))
        if caps:
            r1 = rad(n - 1)
            for a in (0.7, 0.35):
                st.append((P[-1] + tang[-1] * r1 * math.cos(a * math.pi / 2), r1 * math.sin(a * math.pi / 2), n - 1, length[-1] + r1 * (1 - a), 1.0))
            st.append((P[-1] + tang[-1] * r1, 0.0, n - 1, length[-1] + r1, 1.0))
        rings = []
        for c, r, fi, v, tt in st:
            if r <= 1e-7:
                rings.append([t.verts.new(c)])
            else:
                fx, fy = frames[fi]
                rings.append([t.verts.new(c + (fx * math.cos(2 * math.pi * k / segs) + fy * math.sin(2 * math.pi * k / segs)) * r) for k in range(segs)])
        rr = max(s[1] for s in st)
        circ = 2 * math.pi * rr
        ou = self.rng.random() * 5
        j = 1.0 + self.rng.uniform(-jitter, jitter) if jitter else 1.0

        def C(tt):
            if callable(color):
                return None
            if color_top is None:
                return (color[0] * j, color[1] * j, color[2] * j, 1)
            return tuple((color[i] * (1 - tt) + color_top[i] * tt) * j for i in range(3)) + (1,)

        for k in range(len(st) - 1):
            A, B = rings[k], rings[k + 1]
            va, vb = st[k][3] * uv_scale, st[k + 1][3] * uv_scale
            ca, cb = C(st[k][4]), C(st[k + 1][4])
            for i in range(segs):
                jn = (i + 1) % segs
                u0, u1 = i / segs * circ * uv_scale + ou, (i + 1) / segs * circ * uv_scale + ou
                if len(A) == 1 and len(B) == 1:
                    continue
                if len(A) == 1:
                    f = t.faces.new((A[0], B[jn], B[i]))
                    dat = [((u0 + u1) / 2, va, ca), (u1, vb, cb), (u0, vb, cb)]
                elif len(B) == 1:
                    f = t.faces.new((A[i], A[jn], B[0]))
                    dat = [(u0, va, ca), (u1, va, ca), ((u0 + u1) / 2, vb, cb)]
                else:
                    f = t.faces.new((A[i], A[jn], B[jn], B[i]))
                    dat = [(u0, va, ca), (u1, va, ca), (u1, vb, cb), (u0, vb, cb)]
                for l, (uu, vv, cc) in zip(f.loops, dat):
                    l[uv].uv = (uu, vv)
                    if cc is not None:
                        l[col] = cc
        bmesh.ops.recalc_face_normals(t, faces=t.faces[:])
        t.normal_update()
        if callable(color):
            self._color(t, color, None, jitter)
        self._emit(t, mat, loc, rot)

    def blob(self, radii=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0), mat='stone', subdiv=3, noise_amp=0.0,
             noise_scale=1.5, seed=None, flatten_bottom=None, color=(1, 1, 1), color_top=None,
             jitter=0.0, uv_scale=1.0, deform=None):
        """Smooth ellipsoid with optional noise displacement: rocks, heads, fruit, canopy cores.
        radii may be a single number. flatten_bottom=z clamps everything below z (in unit-sphere
        space, e.g. -0.4) to make things sit on the ground. deform(co)->co runs last (local metres)."""
        if isinstance(radii, (int, float)):
            radii = (radii, radii, radii)
        t = self._new()
        bmesh.ops.create_icosphere(t, subdivisions=subdiv, radius=1.0)
        off = Vector((self.rng.random() * 50, self.rng.random() * 50, self.rng.random() * 50)) if seed is None \
            else Vector((seed * 3.1, seed * 7.7, seed * 1.3))
        for v in t.verts:
            d = v.co.normalized()
            k = 1.0
            if noise_amp:
                k += noise_amp * (noise.noise(d * noise_scale + off) + 0.5 * noise.noise(d * noise_scale * 2.3 + off))
            c = d * k
            if flatten_bottom is not None and c.z < flatten_bottom:
                c.z = flatten_bottom
            c = Vector((c.x * radii[0], c.y * radii[1], c.z * radii[2]))
            v.co = deform(c) if deform else c
        t.normal_update()
        self._box_uv(t, None, uv_scale)
        self._color(t, color, color_top, jitter)
        self._emit(t, mat, loc, rot)

    def leaf(self, length, width, loc=(0, 0, 0), rot=(0, 0, 0), mat='plant', bend=40, fold=20, segs=5,
             shape=None, color=(1, 1, 1), color_top=None, jitter=0.0, tip=0.0):
        """A real leaf/blade strip. Base at local origin, grows along +Z and droops toward +X by
        `bend` degrees in total. `fold` degrees of V-crease along the midrib. shape(t)->half-width
        factor 0..1 (default: pointed oval). tip: width fraction kept at the tip (0 = pointed).
        Aim it with rot: (0, pitch, yaw). Render double sided."""
        t = self._new()
        uv, col, _ = self._layers(t)
        if shape is None:
            def shape(u):
                return max(math.sin(math.pi * (u ** 0.75)) ** 0.8, tip if u > 0.5 else 0.12)
        j = 1.0 + self.rng.uniform(-jitter, jitter) if jitter else 1.0
        rows = []
        x = z = 0.0
        ang = 0.0
        step = length / segs
        fr = math.radians(fold)
        for i in range(segs + 1):
            u = i / segs
            w = width * 0.5 * shape(u)
            dx, dz = math.sin(ang), math.cos(ang)  # direction of growth in XZ
            nx, nz = -dz, dx  # blade "up" normal in XZ plane (points -X at base)
            lift = math.sin(fr) * w
            cw = math.cos(fr) * w
            c = Vector((x, 0, z))
            up = Vector((nx, 0, nz))
            rows.append((t.verts.new(c + Vector((0, -cw, 0)) + up * lift), t.verts.new(c),
                         t.verts.new(c + Vector((0, cw, 0)) + up * lift), u))
            ang += math.radians(bend) / segs
            x += math.sin(ang) * step
            z += math.cos(ang) * step
        for i in range(segs):
            a, b = rows[i], rows[i + 1]
            for s in (0, 1):
                f = t.faces.new((a[s], a[s + 1], b[s + 1], b[s]))
                dat = [(s * 0.5, a[3]), (s * 0.5 + 0.5, a[3]), (s * 0.5 + 0.5, b[3]), (s * 0.5, b[3])]
                for l, (uu, vv) in zip(f.loops, dat):
                    l[uv].uv = (uu * width, vv * length)
                    if color_top is not None:
                        c = [color[k] * (1 - vv) + color_top[k] * vv for k in range(3)]
                    else:
                        c = color
                    l[col] = (c[0] * j, c[1] * j, c[2] * j, 1)
        bmesh.ops.remove_doubles(t, verts=t.verts[:], dist=1e-6)
        t.normal_update()
        self._emit(t, mat, loc, rot)

    def card(self, w, h, loc=(0, 0, 0), rot=(0, 0, 0), mat='leaf', normal=None, color=(1, 1, 1),
             uv_rect=(0, 0, 1, 1), anchor_bottom=False):
        """Textured quad in the local XZ plane facing -Y. UVs span uv_rect. `normal` (world-space
        vector in the current frame) overrides the shading normal (fluffy foliage trick)."""
        t = self._new()
        uv, col, cn = self._layers(t)
        z0 = 0 if anchor_bottom else -h / 2
        vs = [t.verts.new((-w / 2, 0, z0)), t.verts.new((w / 2, 0, z0)), t.verts.new((w / 2, 0, z0 + h)), t.verts.new((-w / 2, 0, z0 + h))]
        f = t.faces.new(vs)
        u0, v0, u1, v1 = uv_rect
        for l, w_ in zip(f.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
            l[uv].uv = w_
            l[col] = (*color, 1)
        t.normal_update()
        M = _mat4(loc, rot)
        if normal is not None:
            # normal is given in the builder's current frame; pre-undo the card's own rotation
            inv = M.to_3x3().inverted_safe()
            nl = (inv @ Vector(normal)).normalized()
            for l in f.loops:
                l[cn] = nl
        self._emit(t, mat, loc, rot, smooth=True)

    def foliage(self, center, radii, count=60, size=0.5, mat='leaf', color=(1, 1, 1), color_top=None,
                up_bias=0.25, tilt=45):
        """Fluffy canopy cluster: `count` leaf cards scattered over an ellipsoid, with shading
        normals pointing away from its centre. color -> color_top is a bottom-to-top gradient
        (make the bottom darker for fake occlusion). The leaf texture is a cluster of leaves on a
        transparent square, so cards read as leaf tufts."""
        if isinstance(radii, (int, float)):
            radii = (radii, radii, radii)
        c = Vector(center)
        for _ in range(count):
            while True:
                d = Vector((self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), self.rng.uniform(-1, 1)))
                if 0.05 < d.length <= 1:
                    break
            d.normalize()
            p = c + Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2]))
            n = (d + Vector((0, 0, up_bias))).normalized()
            yaw = math.degrees(math.atan2(d.y, d.x)) + 90 + self.rng.uniform(-tilt, tilt)
            pitch = -math.degrees(math.asin(max(-1, min(1, d.z)))) * 0.7 + self.rng.uniform(-tilt, tilt) * 0.5
            roll = self.rng.uniform(0, 360)
            tt = (d.z + 1) / 2
            col = color if color_top is None else tuple(color[i] * (1 - tt) + color_top[i] * tt for i in range(3))
            k = self.rng.uniform(0.9, 1.1)
            s = size * self.rng.uniform(0.75, 1.25)
            self.card(s, s, loc=p, rot=(pitch, roll, yaw), mat=mat, normal=n, color=(col[0] * k, col[1] * k, col[2] * k))

    # ---- finish ---------------------------------------------------------------
    def build(self, sharp_angle=42, weighted=True):
        """-> bpy object at the world origin, linked to the scene."""
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(get_mat(m))
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        me.set_sharp_from_angle(angle=math.radians(sharp_angle))
        if weighted and len(me.polygons):
            mod = obj.modifiers.new('wn', 'WEIGHTED_NORMAL')
            mod.keep_sharp = True
            mod.weight = 50
            bpy.context.view_layer.objects.active = obj
            with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
                bpy.ops.object.modifier_apply(modifier=mod.name)
        cn = me.attributes.get('cn')
        if cn is not None:
            n = len(me.loops)
            over = [0.0] * (n * 3)
            cn.data.foreach_get('vector', over)
            if any(over):
                cur = [0.0] * (n * 3)
                me.corner_normals.foreach_get('vector', cur)
                out = []
                for i in range(n):
                    o = over[i * 3:i * 3 + 3]
                    out.append(tuple(o) if (o[0] or o[1] or o[2]) else tuple(cur[i * 3:i * 3 + 3]))
                me.normals_split_custom_set(out)
            me.attributes.remove(me.attributes.get('cn'))
        ca = me.color_attributes.get('Color')
        if ca is not None:
            me.color_attributes.active_color = ca
            try:
                me.color_attributes.render_color_index = list(me.color_attributes).index(ca)
            except Exception:
                pass
        return obj


def marker(name, loc, parent=None):
    """Empty used as an attachment point (smoke emitter, hand grip, door hinge...)."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.1
    bpy.context.scene.collection.objects.link(e)
    e.location = Vector(loc)
    if parent is not None:
        e.parent = parent
    return e


def set_parent(child, parent, loc=(0, 0, 0)):
    """Parent `child` (built around its own pivot at the origin) under `parent` at local `loc`."""
    child.parent = parent
    child.location = Vector(loc)
    return child


def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for o in objs:
        if o.type == 'MESH':
            n += sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons)
    return n


def _descend(objs):
    out = []
    for o in objs:
        out.append(o)
        out.extend(_descend(o.children))
    return out


def export_glb(path, roots):
    """Export root objects (and all their children) as one .glb."""
    bpy.ops.object.select_all(action='DESELECT')
    objs = _descend(roots)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    want = dict(filepath=path, export_format='GLB', use_selection=True, export_apply=True, export_yup=True,
                export_normals=True, export_tangents=False, export_materials='EXPORT',
                export_vertex_color='ACTIVE', export_all_vertex_colors=False,
                export_active_vertex_color_when_no_material=True, export_cameras=False, export_lights=False,
                export_animations=False, export_extras=False, export_texcoords=True)
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    bpy.ops.export_scene.gltf(**{k: v for k, v in want.items() if k in props})
    print(f'[kit] exported {path}: {len(objs)} objects, {tri_count(objs)} tris')


def render_preview(path, objs, az=35, el=22, size=(1000, 750), zoom=1.0):
    """Quick lit preview of `objs` (and children) to a PNG. az/el in degrees (az 0 = front view)."""
    sc = bpy.context.scene
    objs = _descend(objs)
    pts = []
    for o in objs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    rad = (hi - lo).length / 2
    for n in ('_pv_cam', '_pv_sun', '_pv_fill', '_pv_floor'):
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o)
    cam = bpy.data.objects.new('_pv_cam', bpy.data.cameras.new('_pv_cam'))
    sc.collection.objects.link(cam)
    cam.data.lens = 60
    d = rad / math.tan(math.radians(13)) / zoom
    a, e = math.radians(az), math.radians(el)
    cam.location = c + Vector((math.sin(a) * math.cos(e) * d, -math.cos(a) * math.cos(e) * d, math.sin(e) * d))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_end = d * 4
    sc.camera = cam
    sun = bpy.data.objects.new('_pv_sun', bpy.data.lights.new('_pv_sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.86, 0.68)
    sun.data.angle = math.radians(4)
    sun.rotation_euler = Euler((math.radians(58), 0, a + math.radians(55)))
    fm = bpy.data.meshes.new('_pv_floor')
    fb = bmesh.new()
    bmesh.ops.create_grid(fb, x_segments=1, y_segments=1, size=rad * 12)
    fb.to_mesh(fm)
    fb.free()
    floor = bpy.data.objects.new('_pv_floor', fm)
    floor.location = (c.x, c.y, lo.z - 0.001)
    sc.collection.objects.link(floor)
    fmat = bpy.data.materials.get('_pv_floor') or bpy.data.materials.new('_pv_floor')
    fmat.diffuse_color = (0.35, 0.42, 0.25, 1)
    try:
        fmat.use_nodes = True
        b = next(n for n in fmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b.inputs['Base Color'].default_value = (0.30, 0.38, 0.20, 1)
        b.inputs['Roughness'].default_value = 0.9
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
    for o in (cam, sun, floor):
        bpy.data.objects.remove(o)
    print(f'[kit] preview {path}')
