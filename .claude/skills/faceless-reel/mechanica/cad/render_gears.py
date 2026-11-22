import bpy, math, time
bpy.ops.wm.read_factory_settings(use_empty=True); S = bpy.context.scene
S.render.engine = 'CYCLES'; S.cycles.device = 'CPU'; S.cycles.samples = 16; S.cycles.use_adaptive_sampling = True
S.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'; S.cycles.denoising_prefilter = 'ACCURATE'
c = S.cycles; c.max_bounces = 6; c.diffuse_bounces = 2; c.glossy_bounces = 4; c.transmission_bounces = 0; c.caustics_reflective = c.caustics_refractive = False; c.sample_clamp_indirect = 10
S.render.resolution_x = S.render.resolution_y = 760; S.render.film_transparent = True; S.view_settings.view_transform = 'Khronos PBR Neutral'
def mat(n, rgb, r):
    m = bpy.data.materials.new(n); m.use_nodes = True; p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*rgb, 1); p.inputs['Metallic'].default_value = 1; p.inputs['Roughness'].default_value = r; return m
objs = []
for f, m, spin in (('gear20.stl', mat('brass', (0.78, 0.56, 0.21), 0.3), 0.0), ('gear12.stl', mat('steel', (0.70, 0.73, 0.78), 0.25), 180 / 12)):
    bpy.ops.wm.stl_import(filepath='cadtest/' + f); o = bpy.context.object; o.scale = (0.1, 0.1, 0.1); o.data.materials.append(m)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35)); objs.append(o)
objs[1].rotation_euler.z = math.radians(spin)          # half a tooth offset so the teeth interleave
w = bpy.data.worlds.new('w'); S.world = w; w.use_nodes = True; nt = w.node_tree
env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load('/tmp/claude-0/-home-user-joestilllives-github-io/c8b4840a-941c-578d-bf3e-22bc86ddeadc/scratchpad/hdri/studio_small_09.hdr')
nt.links.new(env.outputs['Color'], nt.nodes['Background'].inputs['Color']); nt.nodes['Background'].inputs[1].default_value = 0.5
bpy.ops.object.light_add(type='AREA', location=(2, -3, 5)); L = bpy.context.object; L.data.energy = 300; L.data.size = 4; L.rotation_euler = (math.radians(30), 0, math.radians(30))
bpy.ops.object.empty_add(location=(1.6, 0, 0)); aim = bpy.context.object
bpy.ops.object.camera_add(location=(1.6, -6.5, 6.0)); cam = bpy.context.object; S.camera = cam; cam.data.lens = 60
t = cam.constraints.new('TRACK_TO'); t.target = aim; t.track_axis = 'TRACK_NEGATIVE_Z'; t.up_axis = 'UP_Y'
S.render.filepath = 'cadtest/gears.png'; t0 = time.time(); bpy.ops.render.render(write_still=True); print(f'GEARS {time.time() - t0:.1f}s')
