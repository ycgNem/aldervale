"""Procedural, seamlessly tileable PBR textures for the homestead demo.

Run:  uv run --no-project --with numpy --with pillow --with scipy python tools/textures/gen_textures.py
      [--only grass,wood] [--preview <dir>]   (preview writes 2x2 tiling montages at half size)

Writes public/textures/<name>_albedo.png (sRGB), <name>_normal.png (OpenGL, +Y up), <name>_rough.png.
Everything is periodic by construction: FFT spectral noise, wrapped Voronoi (cKDTree boxsize),
wrapped blurs / warps, and strokes that are stamped at the 9 wrap offsets.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

N = 1024
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'public', 'textures')
PREVIEW = None


# ----------------------------------------------------------------------------- helpers
def grid(n=N):
    a = (np.arange(n) + 0.5) / n
    return np.meshgrid(a, a)  # X along columns (U), Y along rows (down)


def norm01(a, p=0.5):
    lo, hi = np.percentile(a, [p, 100 - p])
    return np.clip((a - lo) / (hi - lo + 1e-12), 0, 1)


def _freq(n, aniso=(1, 1)):
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    f[0, 0] = 1
    return f


def spectral(beta=2.0, seed=0, aniso=(1, 1), lo=0.0, hi=None, n=N):
    """1/f^beta noise in 0..1. aniso=(a,1) with a>1 stretches features along X."""
    r = np.random.default_rng(seed)
    F = np.fft.fft2(r.standard_normal((n, n)))
    f = _freq(n, aniso)
    amp = f ** (-beta / 2)
    if lo > 0:
        amp *= 1 - np.exp(-(f / lo) ** 4)
    if hi:
        amp *= np.exp(-(f / hi) ** 4)
    amp[0, 0] = 0
    return norm01(np.real(np.fft.ifft2(F * amp)))


def band(f0, bw, seed=0, aniso=(1, 1), n=N):
    """Band-limited noise (blobs of ~n/f0 px) in 0..1."""
    r = np.random.default_rng(seed)
    F = np.fft.fft2(r.standard_normal((n, n)))
    f = _freq(n, aniso)
    amp = np.exp(-((f - f0) / bw) ** 2)
    amp[0, 0] = 0
    return norm01(np.real(np.fft.ifft2(F * amp)))


def blur(a, s):
    return ndi.gaussian_filter(a, s, mode='wrap')


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-12), 0, 1)
    return t * t * (3 - 2 * t)


def soft_steps(x, n, soft=0.35):
    """Painterly posterise: n tone steps with soft transitions."""
    t = np.clip(x, 0, 1) * n
    f = np.floor(t)
    return np.clip((f + smoothstep(0.5 - soft, 0.5 + soft, t - f)) / n, 0, 1)


def worley(cx, cy, seed, jitter=0.9, wx=0.0, wy=0.0, n=N):
    """Wrapped Voronoi on a cx*cy jittered grid. Returns F1, F2 (cell units), id, count."""
    r = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(cx), np.arange(cy))
    m = cx * cy
    pts = np.stack([gx.ravel() + 0.5 + (r.random(m) - 0.5) * jitter,
                    gy.ravel() + 0.5 + (r.random(m) - 0.5) * jitter], 1)
    pts[:, 0] %= cx
    pts[:, 1] %= cy
    tree = cKDTree(pts, boxsize=(cx, cy))
    X, Y = grid(n)
    q = np.stack([np.mod(X * cx + wx, cx).ravel(), np.mod(Y * cy + wy, cy).ravel()], 1)
    q = np.minimum(q, [np.nextafter(cx, 0), np.nextafter(cy, 0)])
    d, i = tree.query(q, k=2, workers=-1)
    return d[:, 0].reshape(n, n), d[:, 1].reshape(n, n), i[:, 0].reshape(n, n), m


def _nn_dist(cx, cy, seed, jitter):
    """Distance from each Voronoi site to its nearest neighbour (same sites as worley())."""
    r = np.random.default_rng(seed)
    gx, gy = np.meshgrid(np.arange(cx), np.arange(cy))
    m = cx * cy
    pts = np.stack([gx.ravel() + 0.5 + (r.random(m) - 0.5) * jitter,
                    gy.ravel() + 0.5 + (r.random(m) - 0.5) * jitter], 1)
    pts[:, 0] %= cx
    pts[:, 1] %= cy
    d, _ = cKDTree(pts, boxsize=(cx, cy)).query(pts, k=2)
    return d[:, 1]


def cells(c, seed, warp=0.18, jitter=1.0, n=N):
    """Packed rounded cells filling the plane: dome 0 at borders .. 1 at centres, id, count."""
    wx = (band(c * 1.2, c * 0.8, seed + 101, n=n) - 0.5) * 2 * warp
    wy = (band(c * 1.2, c * 0.8, seed + 102, n=n) - 0.5) * 2 * warp
    F1, F2, idx, m = worley(c, c, seed, jitter, wx, wy, n)
    return (F2 - F1) / (F2 + F1 + 1e-9), idx, m


def pebbles(c, seed, prob=0.5, rmin=0.2, rmax=0.45, warp=0.14, jitter=1.0, power=0.5, n=N):
    """Scattered rounded lumps (never overlapping). Returns dome (0..1 height), per-lump random
    value, soft mask."""
    wx = (band(c * 1.3, c * 0.8, seed + 101, n=n) - 0.5) * 2 * warp
    wy = (band(c * 1.3, c * 0.8, seed + 102, n=n) - 0.5) * 2 * warp
    F1, _, idx, m = worley(c, c, seed, jitter, wx, wy, n)
    r = np.random.default_rng(seed + 1)
    rad = np.minimum(r.uniform(rmin, rmax, m), _nn_dist(c, c, seed, jitter) * 0.47)
    on = r.random(m) < prob
    val = r.random(m)
    t = np.clip(1 - (F1 / rad[idx]) ** 2, 0, 1) * on[idx]
    return t ** power * (t > 0), val[idx], smoothstep(0.0, 0.18, t)


def strokes(count, seed, length=(30, 60), width=(3, 6), angle=None, curve=0.3, taper=True, grad=0.0, ss=2):
    """Paint `count` tapered strokes (later ones on top). Returns (val, z, cov):
    val = random tone of the top stroke (+grad from base to tip), z = paint order 0..1, cov = coverage.
    angle: None (random) or (mean_deg, spread_deg)."""
    S = N * ss
    r = np.random.default_rng(seed)
    val = Image.new('F', (S, S), 0.5)
    zim = Image.new('F', (S, S), 0.0)
    cov = Image.new('F', (S, S), 0.0)
    dv, dz, dc = ImageDraw.Draw(val), ImageDraw.Draw(zim), ImageDraw.Draw(cov)
    ts = [0.0, 0.34, 0.67, 1.0]
    for k in range(count):
        x, y = r.random() * S, r.random() * S
        a = r.random() * 2 * math.pi if angle is None else math.radians(angle[0] + r.uniform(-angle[1], angle[1]))
        L = r.uniform(*length) * ss
        W = r.uniform(*width) * ss
        c = r.uniform(-curve, curve)
        v = r.random()
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        pts = []
        for t in ts:
            cx_ = x + dx * L * (t - 0.5) + px * c * L * (t - 0.5) ** 2 * 2
            cy_ = y + dy * L * (t - 0.5) + py * c * L * (t - 0.5) ** 2 * 2
            w = W * (1 - t ** 1.6 * 0.92) / 2 if taper else W / 2
            pts.append((cx_, cy_, w))
        z = (k + 1) / count
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pad = W
        for ox in (-S, 0, S):
            if max(xs) + pad + ox < 0 or min(xs) - pad + ox > S:
                continue
            for oy in (-S, 0, S):
                if max(ys) + pad + oy < 0 or min(ys) - pad + oy > S:
                    continue
                for i in range(len(pts) - 1):
                    (x0, y0, w0), (x1, y1, w1) = pts[i], pts[i + 1]
                    poly = [(x0 + px * w0 + ox, y0 + py * w0 + oy), (x1 + px * w1 + ox, y1 + py * w1 + oy),
                            (x1 - px * w1 + ox, y1 - py * w1 + oy), (x0 - px * w0 + ox, y0 - py * w0 + oy)]
                    tv = v + grad * ((i + 0.5) / (len(pts) - 1) - 0.5) * 2
                    dv.polygon(poly, fill=float(tv))
                    dz.polygon(poly, fill=float(z))
                    dc.polygon(poly, fill=1.0)

    def down(im):
        a = np.asarray(im, dtype=np.float32).reshape(N, ss, N, ss).mean((1, 3))
        return a.astype(np.float64)

    return down(val), down(zim), down(cov)


def ramp(t, stops):
    """Scalar field -> sRGB colour (float HxWx3) through colour stops [(pos,(r,g,b)),...]."""
    pos = [s[0] for s in stops]
    cols = np.array([s[1] for s in stops], float)
    return np.stack([np.interp(t, pos, cols[:, i]) for i in range(3)], -1)


def mixc(a, b, m):
    return a * (1 - m[..., None]) + np.asarray(b, float) * m[..., None]


def mul(col, k):
    return col * k[..., None]


def normal_map(h, strength):
    """Height (0..1-ish) -> OpenGL tangent-space normal map (uint8)."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5  # d/d(row), row grows downward
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(h)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx * inv, ny * inv, nz * inv], -1)
    return np.clip(n * 127.5 + 127.5, 0, 255).astype(np.uint8)


def save(name, albedo=None, height=None, nstrength=40.0, rough=None, normal=None):
    os.makedirs(OUT, exist_ok=True)
    if albedo is not None:
        a = np.clip(albedo, 0, 255).astype(np.uint8)
        Image.fromarray(a).save(os.path.join(OUT, f'{name}_albedo.png'))
        if PREVIEW:
            Image.fromarray(np.tile(a, (2, 2, 1))).resize((N, N), Image.LANCZOS).save(os.path.join(PREVIEW, f'{name}_2x2.png'))
        m = a.reshape(-1, a.shape[-1]).mean(0)
        print(f'  {name}: mean albedo {m.round(0)}  min {a.min()} max {a.max()}')
    if normal is None and height is not None:
        normal = normal_map(height, nstrength)
    if normal is not None:
        Image.fromarray(normal).save(os.path.join(OUT, f'{name}_normal.png'))
        if PREVIEW:
            Image.fromarray(np.tile(normal, (2, 2, 1))).resize((N, N), Image.LANCZOS).save(os.path.join(PREVIEW, f'{name}_normal_2x2.png'))
    if rough is not None:
        Image.fromarray(np.clip(rough * 255, 0, 255).astype(np.uint8)).save(os.path.join(OUT, f'{name}_rough.png'))


def wrapd(a):
    """Wrapped difference in 0..1 space -> -0.5..0.5"""
    return (a + 0.5) % 1.0 - 0.5


def prof1d(seed, beta=1.4, n=4096, hi=None):
    """Periodic 1D noise profile in 0..1 (sample with phase in 0..1)."""
    r = np.random.default_rng(seed)
    F = np.fft.rfft(r.standard_normal(n))
    f = np.arange(F.size, dtype=float)
    f[0] = 1
    amp = f ** (-beta / 2)
    if hi:
        amp *= np.exp(-(f / hi) ** 4)
    amp[0] = 0
    return norm01(np.fft.irfft(F * amp, n))


def sample1d(p, phase):
    x = (phase % 1.0) * p.size
    i = np.floor(x).astype(int) % p.size
    f = x - np.floor(x)
    return p[i] * (1 - f) + p[(i + 1) % p.size] * f


# ----------------------------------------------------------------------------- ground
def tex_grass():
    # three painted passes: big soft clumps underneath, then blades on top
    v0, z0, _ = strokes(2600, 1, length=(70, 130), width=(18, 30), curve=0.4, grad=0.10)
    v1, z1, c1 = strokes(15000, 2, length=(34, 76), width=(5, 9), curve=0.5, grad=0.26)
    patch = spectral(beta=3.2, seed=3, hi=7)
    yell = band(2.5, 1.5, seed=4)
    t0 = 0.30 + (blur(v0, 3) - 0.5) * 0.35
    t1 = 0.52 + (v1 - 0.5) * 0.62
    t = np.where(c1 > 0.5, t1, t0)
    t = np.clip(t + (patch - 0.5) * 0.30, 0, 1)
    col = ramp(t, [(0, (54, 92, 36)), (0.3, (66, 108, 42)), (0.55, (80, 124, 48)), (0.8, (96, 140, 56)), (1, (112, 154, 64))])
    ym = smoothstep(0.50, 0.95, yell) * 0.36
    col = mixc(col, col * np.array([1.22, 1.07, 0.80]), ym)
    cool = smoothstep(0.62, 0.9, band(3, 2, seed=5)) * 0.35
    col = mixc(col, col * np.array([0.90, 0.98, 1.02]), cool)
    h = blur(z1 * c1 * 0.7 + v1 * 0.3, 0.8)
    rough = 0.93 - 0.07 * smoothstep(0.4, 0.9, t)
    save('grass', col, h, 26, rough)


def tex_dirt():
    m1 = spectral(beta=2.8, seed=10, hi=18)
    m2 = band(12, 7, seed=11)
    t = soft_steps(m1 * 0.7 + m2 * 0.3, 5, 0.42)
    col = ramp(t, [(0, (114, 82, 55)), (0.5, (134, 98, 66)), (1, (152, 115, 79))])
    cl, cv, cm = pebbles(13, 12, prob=0.6, rmin=0.28, rmax=0.5, warp=0.2, power=1.0)
    col = mul(col, 1 + 0.11 * cl * (cv - 0.25))
    col = mul(col, 1 - 0.10 * cm * (1 - smoothstep(0.0, 0.45, cl)))  # soft cavity ring round clods
    g, gv, gm = pebbles(64, 14, prob=0.3, rmin=0.14, rmax=0.32)
    col = mul(col, 1 + (gv - 0.5) * 0.26 * gm)
    pb, pv, pm = pebbles(20, 13, prob=0.2, rmin=0.12, rmax=0.3, warp=0.07, power=0.5)
    pcol = ramp(pv, [(0, (124, 104, 84)), (0.5, (150, 131, 108)), (1, (174, 156, 132))])
    col = mul(col, 1 - 0.16 * blur(pm, 2.5) * (1 - pm))  # seat stones into the ground
    col = mixc(col, mul(pcol, 0.84 + 0.18 * pb), pm)
    wx = (band(4, 3, seed=17) - 0.5) * 0.28
    wy = (band(4, 3, seed=18) - 0.5) * 0.28
    F1, F2, _, _ = worley(5, 5, 15, 0.95, wx, wy)
    crack = (1 - smoothstep(0.0, 0.03, F2 - F1)) * smoothstep(0.52, 0.72, band(3, 2, seed=16)) * (1 - pm)
    col = mul(col, 1 - 0.28 * crack)
    h = m1 * 0.25 + cl * 0.22 + pb * 0.5 + g * 0.05 - crack * 0.3
    rough = 0.9 - 0.16 * pm + 0.04 * crack
    save('dirt', col, h, 60, rough)


def tex_soil():
    r = np.random.default_rng(201)
    big, bi, bm_ = cells(7, 20, warp=0.2)
    bval = r.random(bm_)[bi]
    bigd = smoothstep(0.0, 0.5, big) ** 0.8 * (0.4 + 0.6 * r.random(bm_)[bi])
    med, mi, mm_ = cells(17, 21, warp=0.2)
    mval = r.random(mm_)[mi]
    medd = smoothstep(0.0, 0.55, med) ** 0.8 * (0.35 + 0.65 * r.random(mm_)[mi])
    sm, sv, _ = pebbles(44, 22, prob=0.6, rmin=0.2, rmax=0.45, warp=0.12, power=0.6)
    fine = spectral(beta=1.6, seed=23, lo=40)
    h = norm01(bigd * 0.5 + medd * 0.3 + sm * 0.14 + fine * 0.06, 0.1)
    t = np.clip(h * 0.8 + (bval - 0.5) * 0.16 + (mval - 0.5) * 0.10 + 0.1, 0, 1)
    t = soft_steps(t, 7, 0.45)
    col = ramp(t, [(0, (52, 35, 24)), (0.3, (72, 49, 34)), (0.55, (90, 62, 43)), (0.8, (108, 77, 54)), (1, (126, 93, 66))])
    damp = smoothstep(0.55, 0.85, band(3, 2, seed=24)) * 0.5
    col = mixc(col, col * np.array([0.92, 0.92, 0.94]), damp)
    sp, spv, spm = pebbles(40, 25, prob=0.035, rmin=0.1, rmax=0.22, power=0.5)
    scol = ramp(spv, [(0, (132, 114, 90)), (1, (164, 144, 112))])
    col = mixc(col, scol, spm * 0.85)
    rough = 0.95 - 0.07 * smoothstep(0.5, 1.0, h) - 0.15 * spm
    save('soil', col, h + sp * 0.08, 95, rough)


def tex_path():
    m = spectral(beta=3.0, seed=30, hi=14)
    m2 = band(10, 6, seed=31)
    t = soft_steps(m * 0.75 + m2 * 0.25, 4, 0.45)
    col = ramp(t, [(0, (160, 130, 91)), (0.5, (176, 146, 104)), (1, (190, 162, 120))])
    g, gv, gm = pebbles(58, 32, prob=0.55, rmin=0.15, rmax=0.4)
    col = mul(col, 1 + (gv - 0.5) * 0.17 * gm)
    st, sv, smk = pebbles(13, 33, prob=0.2, rmin=0.16, rmax=0.42, warp=0.08, power=0.4)
    st2, sv2, smk2 = pebbles(28, 34, prob=0.14, rmin=0.14, rmax=0.36, warp=0.08, power=0.4)
    scol = mul(ramp(sv, [(0, (150, 132, 108)), (0.5, (176, 158, 132)), (1, (198, 182, 158))]), 0.88 + 0.14 * st)
    scol2 = mul(ramp(sv2, [(0, (146, 126, 100)), (0.5, (170, 150, 124)), (1, (192, 176, 150))]), 0.88 + 0.14 * st2)
    col = mul(col, 1 - 0.13 * np.maximum(blur(smk, 3) * (1 - smk), blur(smk2, 2) * (1 - smk2)))
    ring = smk * (1 - smoothstep(0.0, 0.55, st))
    ring2 = smk2 * (1 - smoothstep(0.0, 0.55, st2))
    col = mixc(col, scol, smk)
    col = mixc(col, scol2, smk2 * (1 - smk))
    col = mul(col, 1 - 0.16 * np.maximum(ring, ring2))
    stone = np.maximum(np.minimum(st, 0.75) * smk, np.minimum(st2, 0.75) * smk2 * 0.7)
    h = m * 0.15 + stone * 0.5 + g * 0.07
    anym = np.maximum(smk, smk2)
    rough = 0.84 - 0.2 * anym + (m2 - 0.5) * 0.05
    save('path', col, h, 55, rough)


# ----------------------------------------------------------------------------- wood family
def _grain(seed, along='x', knots=3, rings=22, palette=None, ring_dark=0.2):
    X, Y = grid()
    if along == 'y':
        X, Y = Y, X  # build with grain along first coord, swap back by construction
    an = (7, 1) if along == 'x' else (1, 7)
    warpn = (spectral(beta=3.0, seed=seed, aniso=an, hi=10) - 0.5) * 0.06
    phi = Y + warpn
    r = np.random.default_rng(seed + 5)
    km = np.zeros_like(phi)
    kring = np.zeros_like(phi)
    for ki in range(knots):
        xk, yk = (ki + r.uniform(0.15, 0.85)) / knots + 0.37 * ki, (ki + r.uniform(0.2, 0.8)) / knots
        rk = r.uniform(0.012, 0.024)
        dx, dy = wrapd(X - xk), wrapd(Y - yk)
        B = rk * 2.6
        phi = phi - B * np.tanh(dy / (rk * 0.8)) * np.exp(-(dx / (rk * 7)) ** 2) * np.exp(-np.abs(dy) / (rk * 6))
        rr = np.sqrt((dx / 1.5) ** 2 + dy ** 2)
        k = np.exp(-(rr / rk) ** 2.4)
        km = np.maximum(km, k)
        kring = np.maximum(kring, k * (0.5 + 0.5 * np.cos(rr / rk * 9)))
    p_broad = prof1d(seed + 1, beta=2.0, hi=14)
    p_mid = prof1d(seed + 2, beta=1.2, hi=70)
    p_ph = prof1d(seed + 3, beta=2.0, hi=10)
    broad = sample1d(p_broad, phi)
    mid = sample1d(p_mid, phi)
    saw = (phi * rings + sample1d(p_ph, phi) * 1.6) % 1.0
    ringline = np.exp(-(saw / 0.09) ** 2) + 0.35 * np.exp(-((1 - saw) / 0.3) ** 2)
    fib = spectral(beta=1.3, seed=seed + 4, aniso=(48, 1) if along == 'x' else (1, 48), lo=6)
    patchy = spectral(beta=3.0, seed=seed + 6, aniso=(3, 1) if along == 'x' else (1, 3), hi=6)
    t = np.clip(0.5 + (broad - 0.5) * 0.36 + (mid - 0.5) * 0.30 + (fib - 0.5) * 0.22 + (patchy - 0.5) * 0.22, 0, 1)
    col = ramp(t, palette)
    col = mul(col, 1 - ring_dark * ringline * (0.6 + 0.4 * mid))
    col = mixc(col, np.array(palette[0][1]) * 0.72, km * 0.85)
    col = mul(col, 1 - 0.15 * kring)
    h = t * 0.3 - ringline * 0.35 + (fib - 0.5) * 0.3 - km * 0.25 + kring * 0.08
    rough = np.clip(0.68 + ringline * 0.09 - (t - 0.5) * 0.14 + (fib - 0.5) * 0.06 + km * 0.05, 0, 1)
    return col, h, rough, fib, t


def tex_wood():
    col, h, rough, _, _ = _grain(40, 'x', knots=2, rings=22,
                                 palette=[(0, (116, 77, 45)), (0.5, (150, 106, 66)), (1, (178, 134, 90))])
    save('wood', col, h, 34, rough)


def tex_roof():
    col, h, rough, fib, t = _grain(70, 'y', knots=0, rings=30, ring_dark=0.16,
                                   palette=[(0, (138, 129, 120)), (0.5, (170, 160, 150)), (1, (194, 185, 174))])
    _, _, sc = strokes(46, 71, length=(140, 460), width=(2.2, 4.5), angle=(90, 2.5), curve=0.03, taper=True)
    _, _, sc2 = strokes(160, 72, length=(40, 140), width=(1.2, 2.2), angle=(90, 3), curve=0.03, taper=True)
    split = np.clip(blur(sc, 0.6) + 0.5 * blur(sc2, 0.5), 0, 1)
    col = mul(col, 1 - 0.42 * split)
    stain = smoothstep(0.5, 0.85, spectral(beta=3, seed=73, aniso=(1, 2.5), hi=8))
    col = mixc(col, col * np.array([0.90, 0.94, 0.95]), stain * 0.6)
    silver = smoothstep(0.55, 0.9, band(5, 3, seed=74, aniso=(1, 2)))
    col = mixc(col, col * np.array([1.06, 1.06, 1.07]), silver * 0.5)
    h = h - split * 0.55
    save('roof', col, h, 38, np.clip(rough + 0.14 + split * 0.06, 0, 1))


def tex_bark():
    wx = (band(2.5, 1.5, seed=51) - 0.5) * 0.9 + (band(10, 5, seed=53) - 0.5) * 0.28
    wy = (band(3, 2, seed=52) - 0.5) * 0.4
    F1, F2, idx, m = worley(9, 3, 50, 1.0, wx, wy)
    r = np.random.default_rng(54)
    pv = r.random(m)[idx]
    e = F2 - F1
    plate = smoothstep(0.012, 0.15, e)          # crisp plates, narrow furrows
    dome = smoothstep(0.0, 0.55, e)
    G1, G2, gidx, gm = worley(11, 7, 56, 1.0, wx * 1.2, wy * 2 + (band(8, 5, seed=55) - 0.5) * 0.5)
    sub = smoothstep(0.0, 0.07, G2 - G1)        # shallow cross-breaks -> scales
    gv = r.random(gm)[gidx]
    stri = spectral(beta=1.5, seed=57, aniso=(1, 18), lo=5)
    h = plate * (0.50 + 0.20 * dome + 0.18 * pv + 0.12 * gv) * (0.80 + 0.20 * sub) + (stri - 0.5) * 0.10 * plate
    h = norm01(h, 0.1)
    t = np.clip(h * 0.88 + (pv - 0.5) * 0.10 + (stri - 0.5) * 0.10 + 0.04, 0, 1)
    col = ramp(t, [(0, (50, 38, 30)), (0.3, (76, 61, 48)), (0.6, (100, 82, 65)), (0.85, (122, 103, 84)), (1, (140, 120, 99))])
    moss = smoothstep(0.62, 0.9, band(4, 2.5, seed=59)) * (1 - plate * 0.4) * 0.3
    col = mixc(col, col * np.array([0.90, 1.04, 0.82]), moss)
    save('bark', col, h, 70, np.clip(0.94 - 0.08 * h, 0, 1))


# ----------------------------------------------------------------------------- mineral
def tex_stone():
    m = spectral(beta=2.5, seed=60, hi=16)
    m2 = band(9, 5, seed=66)
    t = soft_steps(m * 0.7 + m2 * 0.3, 5, 0.42)
    col = ramp(t, [(0, (126, 121, 112)), (0.5, (150, 146, 138)), (1, (170, 166, 156))])
    wx = (band(5, 3, seed=67) - 0.5) * 0.22
    wy = (band(5, 3, seed=68) - 0.5) * 0.22
    F1, F2, idx, mc = worley(5, 5, 61, 1.0, wx, wy)
    r = np.random.default_rng(69)
    fv = r.random(mc)[idx]
    facet = blur(fv, 2.5)
    edge = (1 - smoothstep(0.0, 0.03, F2 - F1)) * smoothstep(0.5, 0.68, band(3, 2, seed=64))
    col = mul(col, 1 + (facet - 0.5) * 0.10)
    col = mul(col, 1 - 0.26 * edge)
    # chips: small crisp flakes knocked out, lighter fresh rock inside
    C1, C2, cidx, cm_ = worley(17, 17, 63, 1.0, wx * 2, wy * 2)
    chm = (np.random.default_rng(631).random(cm_) < 0.07)[cidx] * smoothstep(0.0, 0.05, C2 - C1)
    col = mixc(col, col * 1.09, chm * 0.9)
    sp, sv, spm = pebbles(76, 62, prob=0.32, rmin=0.12, rmax=0.3)
    col = mul(col, 1 + (sv - 0.55) * 0.30 * spm)
    pit, _, pitm = pebbles(24, 65, prob=0.12, rmin=0.07, rmax=0.17, power=0.6)
    col = mul(col, 1 - 0.30 * pitm)
    lich = smoothstep(0.60, 0.80, band(4, 2.5, seed=601)) * (0.55 + 0.45 * smoothstep(0.35, 0.6, band(22, 10, seed=602)))
    col = mixc(col, (170, 172, 126), lich * 0.34)
    och = smoothstep(0.66, 0.86, band(5, 3, seed=603)) * 0.28
    col = mixc(col, (176, 150, 112), och)
    h = m * 0.22 + facet * 0.3 - edge * 0.28 - chm * 0.16 - pit * 0.25 + sp * 0.02
    rough = 0.82 + (m2 - 0.5) * 0.08 + lich * 0.08 - chm * 0.06
    save('stone', col, h, 62, np.clip(rough, 0, 1))


def tex_plaster():
    stain = spectral(beta=3.2, seed=80, hi=7)
    v, z, c = strokes(520, 81, length=(150, 300), width=(46, 100), curve=0.6, taper=False)
    trow = blur(v, 7)
    fine = spectral(beta=1.8, seed=82, lo=24, hi=160)
    t = np.clip(0.5 + (stain - 0.5) * 0.7 + (trow - 0.5) * 0.35, 0, 1)
    col = ramp(t, [(0, (212, 197, 172)), (0.5, (226, 214, 192)), (1, (236, 227, 208))])
    warm = smoothstep(0.62, 0.9, band(3, 2, seed=83)) * 0.4
    col = mixc(col, col * np.array([1.0, 0.965, 0.90]), warm)
    wx = (band(6, 4, seed=84) - 0.5) * 0.16
    wy = (band(6, 4, seed=85) - 0.5) * 0.16
    F1, F2, _, _ = worley(3, 3, 86, 1.0, wx, wy)
    crack = (1 - smoothstep(0.0, 0.008, F2 - F1)) * smoothstep(0.55, 0.7, band(2.5, 1.5, seed=87))
    col = mul(col, 1 - 0.20 * crack)
    h = trow * 0.6 + (fine - 0.5) * 0.14 - crack * 0.5
    rough = 0.90 - (trow - 0.5) * 0.08 + (fine - 0.5) * 0.04
    save('plaster', col, h, 26, np.clip(rough, 0, 1))


def tex_metal():
    wx = (band(14, 8, seed=91) - 0.5) * 0.5
    wy = (band(14, 8, seed=92) - 0.5) * 0.5
    F1, F2, idx, m = worley(24, 24, 90, 1.0, wx, wy)
    r = np.random.default_rng(93)
    sv = r.random(m)[idx]
    ang = (r.random(m) * 2 * math.pi)[idx]
    X, Y = grid()
    facet = sv + 0.35 * (np.cos(ang) * X + np.sin(ang) * Y) * 13 % 1.0 * 0.0  # keep flat per-crystal tone
    spangle = blur(sv, 0.7)
    low = spectral(beta=3, seed=94, hi=8)
    _, _, sc = strokes(420, 95, length=(50, 320), width=(1.0, 2.0), curve=0.05, taper=False)
    sc = blur(sc, 0.5)
    k = 1 + (spangle - 0.5) * 0.06 + (low - 0.5) * 0.05 + sc * 0.035
    col = np.stack([190 * k, 192 * k, 195 * k], -1)
    tint = (r.random(m)[idx] - 0.5)
    col = col * (1 + tint[..., None] * np.array([0.02, 0.0, -0.025]))
    seam = 1 - smoothstep(0.0, 0.03, F2 - F1)
    h = spangle * 0.10 - sc * 0.25 - seam * 0.03
    rough = 0.42 + (spangle - 0.5) * 0.16 + sc * 0.09 + (low - 0.5) * 0.08
    save('metal', col, h, 14, np.clip(rough, 0.3, 0.55))
    _ = facet


# ----------------------------------------------------------------------------- woven / organic
def _weave(p, flat, seed):
    """Plain weave with thread pitch p px. Returns height 0..1, top-is-vertical mask, cell ids."""
    X, Y = grid()
    wob = (band(6, 4, seed=seed) - 0.5) * 0.10
    u = X * N / p + wob
    v = Y * N / p + (band(6, 4, seed=seed + 1) - 0.5) * 0.10
    iu, iv = np.floor(u), np.floor(v)
    cu = np.cos(np.pi * (u - iu - 0.5)).clip(0, 1) ** flat
    cv = np.cos(np.pi * (v - iv - 0.5)).clip(0, 1) ** flat
    hv = cu * (0.56 + 0.44 * np.sin(np.pi * v + np.pi * iu))
    hh = cv * (0.56 - 0.44 * np.sin(np.pi * u + np.pi * iv))
    return np.maximum(hv, hh), hv >= hh, iu.astype(int), iv.astype(int)


def tex_fabric():
    h, vert, iu, iv = _weave(16, 0.7, 100)
    slub = spectral(beta=1.4, seed=101, aniso=(1, 10), lo=4)
    slub2 = spectral(beta=1.4, seed=102, aniso=(10, 1), lo=4)
    fibre = np.where(vert, slub, slub2)
    h = norm01(h + (fibre - 0.5) * 0.15, 0.1)
    low = spectral(beta=3, seed=103, hi=6)
    a = 237 + (h - 0.55) * 30 + (fibre - 0.5) * 8 + (low - 0.5) * 6
    a = np.clip(a, 215, 255)
    col = np.stack([a, a, a], -1)
    rough = 0.90 - (h - 0.5) * 0.08
    save('fabric', col, h, 55, np.clip(rough, 0.8, 0.95))


def tex_straw():
    p = 64
    h, vert, iu, iv = _weave(p, 0.22, 110)
    r = np.random.default_rng(111)
    nu = N // p
    tone_v = r.random((nu, nu))  # per vertical-strip segment
    tone_h = r.random((nu, nu))
    tv = tone_v[iv % nu, iu % nu]
    th = tone_h[iv % nu, iu % nu]
    # a strip keeps one tone along its run, with small per-crossing variation
    run_v = r.random(nu)[iu % nu]
    run_h = r.random(nu)[iv % nu]
    tone = np.where(vert, run_v * 0.65 + tv * 0.35, run_h * 0.65 + th * 0.35)
    fv = spectral(beta=1.2, seed=112, aniso=(1, 40), lo=8)
    fh = spectral(beta=1.2, seed=113, aniso=(40, 1), lo=8)
    fib = np.where(vert, fv, fh)
    t = np.clip(0.5 + (tone - 0.5) * 0.7 + (fib - 0.5) * 0.4, 0, 1)
    col = ramp(t, [(0, (182, 142, 78)), (0.5, (214, 178, 104)), (1, (236, 206, 136))])
    gap = smoothstep(0.18, 0.62, h)
    col = mul(col, 0.66 + 0.34 * gap)
    hh = norm01(h * 0.85 + (fib - 0.5) * 0.14, 0.1)
    rough = 0.62 + (1 - gap) * 0.25 + (fib - 0.5) * 0.1
    save('straw', col, hh, 70, np.clip(rough, 0, 1))


def tex_plant():
    fib = spectral(beta=1.5, seed=120, aniso=(1, 22), lo=3)
    veins = band(26, 10, seed=121, aniso=(1, 9))
    wx = (band(30, 16, seed=123) - 0.5) * 0.4
    F1, F2, _, _ = worley(36, 36, 122, 0.9, wx, wx)
    cell = smoothstep(0.0, 0.18, F2 - F1)
    low = spectral(beta=3, seed=124, hi=6)
    vein_line = smoothstep(0.66, 0.9, veins)
    a = 238 + (fib - 0.5) * 16 + vein_line * 10 - (1 - cell) * 7 + (low - 0.5) * 8
    a = np.clip(a, 215, 255)
    col = np.stack([a * 0.995, a, a * 0.985], -1)
    h = fib * 0.45 + vein_line * 0.35 + cell * 0.2
    rough = 0.66 - (fib - 0.5) * 0.10 - vein_line * 0.05 + (low - 0.5) * 0.06
    save('plant', col, h, 16, np.clip(rough, 0.55, 0.75))


def tex_water_normal():
    h = band(5, 2.5, seed=130) + 0.55 * band(11, 5, seed=131) + 0.28 * band(23, 9, seed=132) + 0.12 * band(47, 16, seed=133)
    h = norm01(h, 0.05)
    save('water', height=blur(h, 1.0), nstrength=85)
    os.replace(os.path.join(OUT, 'water_normal.png'), os.path.join(OUT, 'water_normal.png'))


def tex_noise():
    n = 512
    r = spectral(beta=3.0, seed=140, hi=9, n=n)
    g = spectral(beta=2.2, seed=141, lo=7, hi=40, n=n)
    b = spectral(beta=1.8, seed=142, lo=28, hi=150, n=n)
    F1, _, _, _ = worley(12, 12, 143, 1.0, n=n)
    a = norm01(F1, 0.05)
    out = np.stack([norm01(r, 0.05), norm01(g, 0.05), norm01(b, 0.05), a], -1)
    Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(OUT, 'noise.png'))
    if PREVIEW:
        for i, c in enumerate('rgba'):
            Image.fromarray(np.clip(out[..., i] * 255, 0, 255).astype(np.uint8)).save(os.path.join(PREVIEW, f'noise_{c}.png'))


# ----------------------------------------------------------------------------- leaf card
def tex_leafcard():
    ss = 2
    S = N * ss
    a = (np.arange(S) + 0.5)
    Xp, Yp = np.meshgrid(a, a)
    rgb = np.zeros((S, S, 3))
    alpha = np.zeros((S, S))
    nrm = np.zeros((S, S, 3))
    nrm[..., 2] = 1
    r = np.random.default_rng(150)
    leaves = []
    n1 = 8
    for i in range(n1):
        ang = i / n1 * 2 * math.pi + r.uniform(-0.16, 0.16) + 0.2
        ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
        reach = min(0.468 / max(ca, sa), 0.60)
        leaves.append(dict(ang=ang, L=reach * S * r.uniform(0.95, 1.0), wr=r.uniform(0.46, 0.56), off=0.02 * S,
                           curv=r.uniform(-0.22, 0.22), hue=r.uniform(-1, 1), val=r.uniform(-1, 1)))
    r.shuffle(leaves)
    for i in range(4):
        ang = i / 4 * 2 * math.pi + r.uniform(-0.3, 0.3) + 0.9
        leaves.append(dict(ang=ang, L=S * r.uniform(0.26, 0.33), wr=r.uniform(0.52, 0.62), off=0.0,
                           curv=r.uniform(-0.25, 0.25), hue=r.uniform(-1, 1), val=r.uniform(0.2, 1)))
    cx = cy = S / 2
    for lf in leaves:
        ca, sa = math.cos(lf['ang']), math.sin(lf['ang'])
        bx, by = cx + ca * lf['off'], cy + sa * lf['off']
        L = lf['L']
        W = L * lf['wr']
        dx, dy = Xp - bx, Yp - by
        u = (dx * ca + dy * sa) / L
        vraw = (-dx * sa + dy * ca) / (W / 2)
        uc = np.clip(u, 0, 1)
        v = vraw - lf['curv'] * np.sin(np.pi * uc)
        w = np.sin(np.pi * uc ** 0.8) ** 0.75 * (1 - uc ** 3) ** 0.5
        w = np.maximum(w, 1e-4)
        q = np.abs(v) / w
        inside = (u > 0.0) & (u < 1.0) & (q < 1.0)
        # occlusion on what is underneath, hugging this leaf's outline
        near = (u > -0.05) & (u < 1.05) & (q < 1.45) & ~inside
        occ = np.where(near, (1 - smoothstep(1.0, 1.45, q)) * 0.26, 0.0)
        rgb *= (1 - occ)[..., None]
        # colour
        hue, val = lf['hue'], lf['val']
        base = np.array([70 + hue * 8, 128 + val * 8, 50 - hue * 6], float)
        tipc = np.array([126 + hue * 12, 178 + val * 8, 76 - hue * 8], float)
        g = smoothstep(0.0, 1.0, uc) ** 0.9
        col = base[None, None, :] * (1 - g[..., None]) + tipc[None, None, :] * g[..., None]
        col *= (1.0 + 0.07 * (1 - q) - 0.05 * smoothstep(0.75, 1.0, q))[..., None]  # body lighter, rim a touch deeper
        vpx = v * (W / 2)
        mid = np.exp(-(vpx / (0.010 * L + 2)) ** 2) * smoothstep(0.0, 0.08, uc) * (1 - smoothstep(0.86, 0.99, uc))
        sline = (uc * 7.0 - np.abs(v) * 4.2 * lf['wr']) % 1.0
        side = np.exp(-((sline - 0.5) / 0.06) ** 2) * smoothstep(0.03, 0.12, np.abs(v)) * (1 - smoothstep(0.7, 0.95, q))
        vein = np.clip(mid + side * 0.55, 0, 1)
        col = col * (1 - vein[..., None] * 0.0) + vein[..., None] * np.array([34, 30, 16])
        rgb[inside] = col[inside]
        alpha[inside] = 1.0
        # normal (leaf frame: u along, v across) -> image frame
        s = np.sign(v)
        nv = 0.62 * q ** 2 * s - 0.34 * s * np.exp(-np.abs(v) / 0.16) + side * 0.0
        nu = 0.30 * (2 * uc - 1)
        nx = nu * ca - nv * sa
        ny_down = nu * sa + nv * ca
        nn = np.stack([nx, -ny_down, np.ones_like(nx)], -1)
        nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
        nrm[inside] = nn[inside]

    def down(x):
        return x.reshape(N, ss, N, ss, -1).mean((1, 3))

    al = down(alpha[..., None])[..., 0]
    pm = down(rgb * alpha[..., None])
    col = pm / np.maximum(al[..., None], 1e-6)
    nd = down(nrm * alpha[..., None]) + (1 - al[..., None]) * np.array([0, 0, 1.0])
    nd /= np.linalg.norm(nd, axis=-1, keepdims=True)
    # bleed colour outwards so mip-maps / bilinear never pick up dark fringes
    solid = al > 0.5
    idx = ndi.distance_transform_edt(~solid, return_distances=False, return_indices=True)
    fill = col[idx[0], idx[1]]
    col = np.where((al > 0.999)[..., None], col, fill)
    out = np.dstack([np.clip(col, 0, 255), al * 255]).astype(np.uint8)
    Image.fromarray(out, 'RGBA').save(os.path.join(OUT, 'leafcard_albedo.png'))
    Image.fromarray(np.clip(nd * 127.5 + 127.5, 0, 255).astype(np.uint8)).save(os.path.join(OUT, 'leafcard_normal.png'))
    if PREVIEW:
        bg = np.array([150, 190, 235.0])
        comp = col * al[..., None] + bg * (1 - al[..., None])
        Image.fromarray(comp.astype(np.uint8)).save(os.path.join(PREVIEW, 'leafcard_preview.png'))
        Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(os.path.join(PREVIEW, 'leafcard_bleed.png'))
    print(f'  leafcard: coverage {al.mean():.2f}, edge alpha max top/bottom/left/right '
          f'{al[0].max():.2f} {al[-1].max():.2f} {al[:, 0].max():.2f} {al[:, -1].max():.2f}')


ALL = {
    'grass': tex_grass, 'dirt': tex_dirt, 'soil': tex_soil, 'path': tex_path, 'wood': tex_wood, 'bark': tex_bark,
    'stone': tex_stone, 'roof': tex_roof, 'plaster': tex_plaster, 'metal': tex_metal, 'fabric': tex_fabric,
    'straw': tex_straw, 'plant': tex_plant, 'leafcard': tex_leafcard, 'water': tex_water_normal, 'noise': tex_noise,
}

if __name__ == '__main__':
    args = sys.argv[1:]
    only = None
    if '--only' in args:
        only = args[args.index('--only') + 1].split(',')
    if '--preview' in args:
        PREVIEW = args[args.index('--preview') + 1]
        os.makedirs(PREVIEW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    for name, fn in ALL.items():
        if only and name not in only:
            continue
        print(f'[tex] {name}')
        fn()
    print('[tex] done ->', OUT)
