"""Second proof, a different mechanism: two CAD-accurate spur gears (build123d involute teeth) assemble, then mesh
at the true 20:12 ratio. Small gear in heat-tinted steel with a light-linked rim light.
    blender-venv/bin/python gears_demo.py OUT CAD_DIR [FRAMES] [PRESET]   (CAD_DIR holds gear20.stl, gear12.stl)"""
import sys, os, math; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mstudio as ms, bpy
out, cad = sys.argv[1], sys.argv[2]; frames = int(sys.argv[3]) if len(sys.argv) > 3 else 60; preset = sys.argv[4] if len(sys.argv) > 4 else 'final'
S = ms.scene(size=760, frames=frames, preset=preset)
big = ms.import_cad(os.path.join(cad, 'gear20.stl'), 'brass', name='gear20')
small = ms.import_cad(os.path.join(cad, 'gear12.stl'), 'heat_steel', name='gear12')
for g in (big, small):                                   # pivot at the gear's own centre so it spins on its axis
    bpy.context.view_layer.objects.active = g; g.select_set(True); bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS'); g.select_set(False)
shafts = [ms.part(ms.cylinder(0.25, 1.6, location=(g.location.x, g.location.y, 0)), 'steel', name='shaft') for g in (big, small)]
small.rotation_euler.z = math.radians(180 / 12)          # half a tooth: teeth interleave instead of colliding
# Assemble: the small gear and its shaft slide in from the right, expo ease-out.
a_end = int(frames * 0.4)
ms.explode([small, shafts[1]], [(3.0, 0, 0.6), (3.0, 0, 0.6)], start=1, dur=a_end - 1, stagger=2)
# Mesh: constant speed (linear keys). The 12-tooth gear turns 20/12 times as fast, the other way: gear ratio = teeth ratio.
turn = math.radians(90)
ms.key(big, 'rotation_euler', [(a_end, (0, 0, 0)), (frames, (0, 0, turn))], ease=('LINEAR', 'AUTO'))
s0 = small.rotation_euler.z
ms.key(small, 'rotation_euler', [(a_end, (0, 0, s0)), (frames, (0, 0, s0 - turn * 20 / 12))], ease=('LINEAR', 'AUTO'))
ms.studio(S, rim_only=[small])
ms.camera(S, target=(1.6, 0, 0), lens=60, distance=8.5, height=6.0, orbit=(-18, -8))
ms.fit(S, [big, small] + shafts)
ms.render(S, out)
