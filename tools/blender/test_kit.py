"""Smoke test for kit.py:  blender --background --factory-startup --python tools/blender/test_kit.py -- <out_dir>"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit
from kit import Builder, srgb

out = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else os.path.dirname(os.path.abspath(__file__))
kit.reset()

b = Builder('test_crate', seed=1)
for i in range(5):
    b.box((0.9, 0.16, 0.03), loc=(0, -0.45, 0.1 + i * 0.18), mat='wood_light', jitter=0.12)
    b.box((0.9, 0.16, 0.03), loc=(0, 0.45, 0.1 + i * 0.18), rot=(0, 0, 0), mat='wood_light', jitter=0.12)
    b.box((0.03, 0.9, 0.16), loc=(-0.45, 0, 0.1 + i * 0.18), mat='wood_light', jitter=0.12)
    b.box((0.03, 0.9, 0.16), loc=(0.45, 0, 0.1 + i * 0.18), mat='wood_light', jitter=0.12)
for sx in (-1, 1):
    for sy in (-1, 1):
        b.box((0.07, 0.07, 0.95), loc=(sx * 0.44, sy * 0.44, 0.475), mat='wood_dark', bevel=0.015)
with b.at(loc=(1.4, 0, 0)):
    prof = [(0, 0), (0.30, 0), (0.32, 0.02), (0.38, 0.4), (0.32, 0.78), (0.30, 0.8), (0.27, 0.8), (0.27, 0.74), (0, 0.74)]
    b.lathe(prof, mat='wood_plank', segs=28)
    for z in (0.12, 0.68):
        b.lathe([(0.335, z - 0.03), (0.345, z - 0.025), (0.352, z + 0.025), (0.342, z + 0.03)], mat='metal', segs=28)
with b.at(loc=(-1.5, 0.2, 0)):
    b.blob((0.6, 0.45, 0.4), loc=(0, 0, 0.2), mat='stone', noise_amp=0.25, flatten_bottom=-0.5, jitter=0.1)
    b.tube([(0.5, 0, 0), (0.55, 0, 0.5), (0.7, 0.1, 0.9)], lambda t: 0.04 * (1 - 0.6 * t), mat='plant',
           color=srgb(60, 110, 40), color_top=srgb(120, 170, 60))
    for k in range(6):
        b.leaf(0.45, 0.12, loc=(0.6, 0.05, 0.5 + k * 0.05), rot=(0, 35 + k * 5, k * 60), color=srgb(50, 120, 40),
               color_top=srgb(140, 190, 70), bend=60)
with b.at(loc=(0, 2.0, 0)):
    b.tube([(0, 0, 0), (0.05, 0, 1.0), (0, 0.05, 1.8)], lambda t: 0.16 * (1 - 0.5 * t), mat='bark', segs=12)
    b.blob(0.8, loc=(0, 0, 2.3), mat='plant', color=srgb(40, 80, 30), subdiv=2)
    b.foliage((0, 0, 2.3), (1.0, 1.0, 0.85), count=90, size=0.7, color=srgb(50, 105, 35), color_top=srgb(120, 175, 60))
b.prism([(-0.5, 0), (0.5, 0), (0.5, 0.6), (0, 1.0), (-0.5, 0.6)], 0.1, loc=(3, 0, 0), mat='plaster')
obj = b.build()
kit.marker('test_marker', (0, 0, 1.0), parent=obj)
print('TRIS', kit.tri_count([obj]), 'MATS', [m.name for m in obj.data.materials])
kit.export_glb(os.path.join(out, 'test_kit.glb'), [obj])
kit.render_preview(os.path.join(out, 'test_kit.png'), [obj], az=30, el=25)
