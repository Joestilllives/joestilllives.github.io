"""Showcase 2, physics: brass coins (150) drop as a tumbling cloud onto an invisible floor and pile up (rigid-body simulation).
Deterministic (fixed seed, simulated in frame order). The floor is the shadow catcher, so the pile casts real shadows.
    blender-venv/bin/python coins.py OUT [FRAMES] [PRESET]"""
import sys, os, math, random; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 120; preset = sys.argv[3] if len(sys.argv) > 3 else 'final'
S = ms.scene(size=1080, frames=frames, preset=preset)
random.seed(7)
E = os.environ.get
N, SIG, REST = int(E('N', 150)), float(E('SIG', 1.2)), float(E('REST', 0.05)); ADAMP = float(E('ADAMP', 0.5))
bpy.ops.rigidbody.world_add(); rw = S.rigidbody_world; rw.substeps_per_frame = 20; rw.solver_iterations = 20
rw.point_cache.frame_start, rw.point_cache.frame_end = 1, frames
floor = ms.shadow_catcher(S, z=0.0); floor.select_set(True); bpy.context.view_layer.objects.active = floor
bpy.ops.rigidbody.object_add(); floor.rigid_body.type = 'PASSIVE'; floor.rigid_body.friction = 0.9; floor.rigid_body.restitution = 0.0
proto = ms.part(ms.cylinder(0.5, 0.08, verts=64), 'brass', name='coin', bevel_width=0.012)
coins, placed = [], []
for i in range(N):
    c = proto.copy(); c.data = proto.data; S.collection.objects.link(c)     # linked mesh data: 150 coins, one mesh
    # Spawn without overlap, or the solver blows overlapping bodies apart (tested: coins flew 280 units). A coin fits in a
    # sphere of radius 0.5, so centres >= 1.02 apart are safe at ANY rotation. Each coin takes the lowest free height at a
    # Gaussian position, which packs a mound in the air; dropped, it settles into a heap.
    x, y = random.gauss(0, SIG), random.gauss(0, SIG); z = 1.0
    while any((x - p[0]) ** 2 + (y - p[1]) ** 2 + (z - p[2]) ** 2 < 1.02 ** 2 for p in placed): z += 0.05
    placed.append((x, y, z)); c.location = (x, y, z)
    c.rotation_euler = (random.uniform(0, math.tau), random.uniform(0, math.tau), random.uniform(0, math.tau))
    bpy.context.view_layer.objects.active = c; c.select_set(True); bpy.ops.rigidbody.object_add(); c.select_set(False)
    c.rigid_body.collision_shape = 'CYLINDER'; c.rigid_body.mass = 0.01; c.rigid_body.friction = 0.8; c.rigid_body.restitution = REST
    c.rigid_body.linear_damping, c.rigid_body.angular_damping = 0.2, ADAMP   # drag: stops coins skating and rolling away
    coins.append(c)
bpy.data.objects.remove(proto)
ms.studio(S, hdri_strength=0.5, backdrop=ms.NAVY_LINEAR, rim_energy=800)
ms.camera(S, target=(0, 0, 0.5), lens=50, distance=float(E('DIST', 12.5)), height=float(E('HEIGHT', 4.5)), orbit=(-30, -15))
if E('SIMONLY'):                                    # physics check without rendering: where do the coins end up?
    import statistics as st
    for f in range(1, frames + 1):
        S.frame_set(f)
        if f % 15 == 0 or f == frames:
            r = sorted(math.hypot(*c.matrix_world.translation[:2]) for c in coins); z = [c.matrix_world.translation.z for c in coins]
            print(f'frame {f}: radius median {st.median(r):.2f} p90 {r[int(.9*len(r))]:.2f} max {r[-1]:.2f} | airborne {sum(h > 1.0 for h in z)} | top {max(z):.2f}')
    sys.exit(0)
ms.simulate(S)
ms.fit(S, coins, margin=0.04, max_pts=24, edges='lrb')   # the pile and any straggler stay in; coins may enter from the top
ms.render(S, out)
