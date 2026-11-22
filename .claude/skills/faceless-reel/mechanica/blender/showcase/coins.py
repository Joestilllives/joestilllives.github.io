"""Showcase 2, physics: ~150 brass coins pour onto an invisible floor and pile up (rigid-body simulation).
Deterministic (fixed seed, simulated in frame order). The floor is the shadow catcher, so the pile casts real shadows.
    blender-venv/bin/python coins.py OUT [FRAMES] [PRESET]"""
import sys, os, math, random; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 90; preset = sys.argv[3] if len(sys.argv) > 3 else 'final'
S = ms.scene(size=1080, frames=frames, preset=preset)
random.seed(7)
bpy.ops.rigidbody.world_add(); rw = S.rigidbody_world; rw.substeps_per_frame = 20; rw.solver_iterations = 20
rw.point_cache.frame_start, rw.point_cache.frame_end = 1, frames
floor = ms.shadow_catcher(S, z=0.0); floor.select_set(True); bpy.context.view_layer.objects.active = floor
bpy.ops.rigidbody.object_add(); floor.rigid_body.type = 'PASSIVE'; floor.rigid_body.friction = 0.6
proto = ms.part(ms.cylinder(0.5, 0.08, verts=64), 'brass', name='coin', bevel_width=0.012)
coins = []
for i in range(150):
    c = proto.copy(); c.data = proto.data; S.collection.objects.link(c)     # linked mesh data: 150 coins, one mesh
    c.location = (random.gauss(0, 0.12), random.gauss(0, 0.12), 2.2 + i * 0.16)   # a column: they arrive as a stream
    c.rotation_euler = (random.uniform(0, math.pi), random.uniform(0, math.pi), random.uniform(0, math.pi))
    bpy.context.view_layer.objects.active = c; c.select_set(True); bpy.ops.rigidbody.object_add(); c.select_set(False)
    c.rigid_body.collision_shape = 'CYLINDER'; c.rigid_body.mass = 0.01; c.rigid_body.friction = 0.5; c.rigid_body.restitution = 0.3
    coins.append(c)
bpy.data.objects.remove(proto)
ms.studio(S, hdri_strength=0.5, backdrop=ms.NAVY_LINEAR, rim_energy=800)
ms.camera(S, target=(0, 0, 0.9), lens=50, distance=9.0, height=2.6, orbit=(-30, -15))
ms.render(S, out)
