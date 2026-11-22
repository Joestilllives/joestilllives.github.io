# Blender hero shot: exploded pin stacks assemble into a lock plug. Transparent PNG frames.
# Run: blender-venv/bin/python hero.py OUTDIR FRAMES [SAMPLES]
import bpy, math, sys, time, os
# Defaults = the settings that won the Blender tests (Production standards tab, section 7). Override with HERO_OPTS="key=value,...".
OPT = {'view': 'Khronos PBR Neutral', 'bevel': '1', 'paths': 'fast', 'denoise': 'full', 'cards': '1', 'mblur': '1', 'catcher': '0'}
OPT.update(dict(kv.split('=') for kv in os.environ.get('HERO_OPTS', '').split(',') if '=' in kv))
out, frames = sys.argv[1], int(sys.argv[2]); samples = int(sys.argv[3]) if len(sys.argv) > 3 else 16
bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene
S.render.engine = 'CYCLES'; S.cycles.device = 'CPU'
S.cycles.samples = samples; S.cycles.use_adaptive_sampling = True; S.cycles.adaptive_threshold = 0.05
S.cycles.use_denoising = True; S.render.use_persistent_data = True
S.render.resolution_x = S.render.resolution_y = 760; S.render.film_transparent = True
S.render.image_settings.file_format = 'PNG'; S.render.image_settings.color_mode = 'RGBA'; S.render.image_settings.color_depth = '16'  # no banding in dark gradients
S.frame_start, S.frame_end = 1, frames
S.view_settings.view_transform = OPT.get('view', 'Standard')
if OPT.get('look'): S.view_settings.look = OPT['look']
if OPT.get('engine') == 'eevee': S.render.engine = 'BLENDER_EEVEE'
if OPT.get('paths') == 'fast':          # trimmed light paths: metal needs glossy bounces, little else
    c = S.cycles; c.max_bounces = 6; c.diffuse_bounces = 2; c.glossy_bounces = 4; c.transmission_bounces = 0; c.volume_bounces = 0
    c.transparent_max_bounces = 4; c.caustics_reflective = False; c.caustics_refractive = False; c.sample_clamp_indirect = 10
if OPT.get('mblur') == '1': S.render.use_motion_blur = True; S.render.motion_blur_shutter = 0.5
if OPT.get('denoise') == 'full':
    S.cycles.denoiser = 'OPENIMAGEDENOISE'; S.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'; S.cycles.denoising_prefilter = 'ACCURATE'

def mat(name, rgb, metal, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*rgb, 1); p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    return m
BRASS = mat('brass', (0.83, 0.60, 0.22), 1.0, 0.28)      # close to the brand amber, as metal
STEEL = mat('steel', (0.72, 0.75, 0.80), 1.0, 0.22)
SPRING = mat('spring', (0.55, 0.58, 0.64), 1.0, 0.35)
NAVY = mat('navy', (0.05, 0.09, 0.22), 0.2, 0.5)

def ease(t):  # expo-out, matching the 2D motion personality
    return 1 - pow(2, -10 * t) if t < 1 else 1

# Plug: a brass cylinder lying along X, with the keyway hinted by a dark slot.
bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=0.9, depth=4.6, rotation=(0, math.pi / 2, 0))
plug = bpy.context.object; plug.data.materials.append(BRASS); bpy.ops.object.shade_smooth()
def cut(obj, cutter):
    m = obj.modifiers.new('cut', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = cutter
    bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier='cut')
    bpy.data.objects.remove(cutter)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.62, 0), scale=(5, 1.24, 2.2)); cut(plug, bpy.context.object)  # open the front: cutaway
for x in (-1.6, -0.8, 0.0, 0.8, 1.6):                                                                                       # drilled pin holes
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.19, depth=1.4, location=(x, 0, 0.55)); cut(plug, bpy.context.object)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.42), scale=(4.7, 0.16, 0.5)); cut(plug, bpy.context.object)       # keyway

key_len = [0.75, 1.05, 0.60, 1.15, 0.85]   # different key-pin lengths: the whole point of the lock
xs = [-1.6, -0.8, 0.0, 0.8, 1.6]
parts = []
for i, (x, kl) in enumerate(zip(xs, key_len)):
    seat = -0.17                              # key pins rest on the keyway, inside the drilled holes
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.17, depth=kl, location=(x, 0, seat + kl / 2))
    kp = bpy.context.object; kp.data.materials.append(BRASS); bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.17, depth=0.6, location=(x, 0, seat + kl + 0.3))
    dp = bpy.context.object; dp.data.materials.append(STEEL); bpy.ops.object.shade_smooth()
    # Spring: a helix made with the screw modifier on a small circle.
    bpy.ops.object.empty_add(location=(x, 0, seat + kl + 0.6)); piv = bpy.context.object
    bpy.ops.mesh.primitive_circle_add(vertices=12, radius=0.03, location=(0, 0, 0), rotation=(math.pi / 2, 0, 0))
    sp = bpy.context.object; bpy.ops.object.transform_apply(rotation=True)
    for v in sp.data.vertices: v.co.x += 0.14            # profile sits on the coil radius
    sc = sp.modifiers.new('screw', 'SCREW'); sc.axis = 'Z'; sc.screw_offset = 0.11; sc.iterations = 6; sc.steps = 32
    sp.data.materials.append(SPRING); sp.parent = piv; sp.location = (0, 0, 0)
    parts.append((kp, dp, piv, i))

if OPT.get('bevel') == '1':
    for o in [plug] + [p for st in parts for p in st[:2]]:
        bv = o.modifiers.new('bevel', 'BEVEL'); bv.width = 0.025; bv.segments = 3; bv.limit_method = 'ANGLE'

# Animation: everything starts exploded (spread up and outward, slightly rotated), then lands in place.
# Each stack lands a little after the previous one (staggered 30-50% overlap).
for kp, dp, piv, i in parts:
    for obj, lift, spin in ((kp, 0.85, 18), (dp, 1.35, -24), (piv, 1.8, 28)):
        home = obj.location.copy(); start = frames * (0.06 + 0.09 * i); dur = frames * 0.45
        for f in range(1, frames + 1):
            t = max(0.0, min(1.0, (f - start) / dur)); e = ease(t)
            obj.location = (home.x + (1 - e) * (home.x * 0.35), home.y, home.z + (1 - e) * lift)
            obj.rotation_euler = (0, math.radians((1 - e) * spin), 0)
            obj.keyframe_insert('location', frame=f); obj.keyframe_insert('rotation_euler', frame=f)

# Camera: a slow 3/4 orbit so the shot is never still.
bpy.ops.object.empty_add(location=(0, 0, 0.75)); aim = bpy.context.object
bpy.ops.object.camera_add(); cam = bpy.context.object; S.camera = cam; cam.data.lens = 58
tr = cam.constraints.new('TRACK_TO'); tr.target = aim; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
for f in (1, frames):
    a = math.radians(-32 + 10 * (f - 1) / max(1, frames - 1))
    cam.location = (10.5 * math.sin(a), -10.5 * math.cos(a), 3.6)
    cam.keyframe_insert('location', frame=f)

# Light: big soft key, cool rim, warm fill. World stays dark so reflections read as metal.
for loc, energy, size, col in (((4, -5, 7), 900, 5, (1, 0.97, 0.92)), ((-6, 4, 5), 500, 3, (0.7, 0.8, 1.0)), ((0, -8, -1), 120, 6, (1, 0.85, 0.6))):
    bpy.ops.object.light_add(type='AREA', location=loc); L = bpy.context.object
    L.data.energy, L.data.size, L.data.color = energy, size, col
    L.rotation_euler = (math.atan2(math.hypot(loc[0], loc[1]), loc[2]), 0, math.atan2(loc[0], -loc[1]))
if OPT.get('catcher') == '1':      # invisible floor that only receives shadows: the part sits on the page instead of floating
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -0.95)); fl = bpy.context.object; fl.is_shadow_catcher = True; fl.visible_diffuse = False; fl.visible_glossy = False  # shadows only, no bounce light
if OPT.get('cards') == '1':        # reflection cards: big soft emitters seen only in reflections, shape the metal like a studio softbox
    for loc, rot in (((0, -6, 4), (math.radians(60), 0, 0)), ((-6, 2, 3), (math.radians(70), 0, math.radians(-110)))):
        bpy.ops.mesh.primitive_plane_add(size=6, location=loc, rotation=rot); cd = bpy.context.object
        em = bpy.data.materials.new('card'); em.use_nodes = True; nt = em.node_tree; nt.nodes.remove(nt.nodes['Principled BSDF'])
        e = nt.nodes.new('ShaderNodeEmission'); e.inputs['Strength'].default_value = 4; nt.links.new(e.outputs[0], nt.nodes['Material Output'].inputs[0])
        cd.data.materials.append(em); cd.visible_camera = False; cd.visible_diffuse = False; cd.visible_shadow = False
w = bpy.data.worlds.new('w'); S.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.05, 0.08, 0.18, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.6

S.render.filepath = out.rstrip('/') + '/f_'
t = time.time()
if len(sys.argv) > 4:   # test mode: render only these frames as stills
    for f in map(int, sys.argv[4].split(',')):
        S.frame_set(f); S.render.filepath = f"{out.rstrip('/')}/test_{f:03d}.png"; bpy.ops.render.render(write_still=True)
    frames = len(sys.argv[4].split(','))
else:
    bpy.ops.render.render(animation=True)
el = time.time() - t
print(f'HERO frames={frames} samples={samples} total={el:.1f}s per_frame={el / frames:.2f}s')
