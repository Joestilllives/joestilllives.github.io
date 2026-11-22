"""Showcase 3, light physics: a glass prism splits a white beam into a rainbow on a wall (Blender 5.3 dispersion).
    blender-venv/bin/python prism.py OUT SAMPLES SIZE [mnee]"""
import sys, os, math; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out, spp, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); mnee = len(sys.argv) > 4 and sys.argv[4] == 'mnee'
S = ms.scene(size=size, frames=1, preset='final'); S.cycles.samples = spp; S.render.use_motion_blur = False
c = S.cycles; c.caustics_refractive = True; c.caustics_reflective = True; c.blur_glossy = 0.0; c.max_bounces = 12; c.transmission_bounces = 12
c.sample_clamp_indirect = 0
# Prism: equilateral triangle extruded, dispersive glass (Abbe-number style dispersion in the Principled BSDF).
bpy.ops.mesh.primitive_cylinder_add(vertices=3, radius=0.9, depth=2.4, location=(0, 0, 0.9), rotation=(0, 0, math.radians(90)))
prism = bpy.context.object; prism.data.materials.append(ms.material('prism_glass', variation=False, edges=False))
# Wall (white, matte) to catch the spectrum, and a floor.
bpy.ops.mesh.primitive_plane_add(size=12, location=(4.5, 0, 2), rotation=(0, math.radians(-90), 0)); wall = bpy.context.object   # faces -X, toward the prism
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, -0.3)); floor = bpy.context.object
for o in (wall, floor): o.data.materials.append(ms.material('plastic_white', variation=False, edges=False))
# The beam: a small, bright sphere light inside a tube, aimed at the prism's face.
bpy.ops.object.light_add(type='SPOT', location=(-5, -1.0, 0.9)); L = bpy.context.object
L.data.energy = 6000; L.data.shadow_soft_size = 0.02; L.data.spot_size = math.radians(4); L.data.spot_blend = 0.1
L.rotation_euler = (0, math.radians(-90), math.atan2(1.0, 5.0))   # spot shines down -Z: -90 deg about Y aims it along +X, at the prism
if mnee:
    L.data.cycles.is_caustics_light = True; prism.cycles.is_caustics_caster = True; wall.cycles.is_caustics_receiver = True; floor.cycles.is_caustics_receiver = True
w = bpy.data.worlds.new('dark'); S.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs[1].default_value = 0.002
S.render.film_transparent = False
ms.camera(S, target=(1.8, 0.3, 0.9), lens=28, distance=7.0, height=2.0, orbit=(-12, -12))
ms.render(S, out)
