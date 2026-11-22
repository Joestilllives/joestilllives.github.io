"""Mechanica studio: the tested Blender practices as functions (Blender 5.3, bpy, headless Cycles on CPU).

Every default here was measured on the pilot (see the Blender playbook tab). Typical use:

    import mstudio as ms
    S = ms.scene(size=760, frames=60, preset='final')
    plug = ms.part(ms.cylinder(0.9, 4.6, axis='X'), 'brass')
    ms.studio(S, hdri=ms.HDRI, rim_only=[plug])          # HDRI + reflection cards + key + rim (light-linked)
    ms.camera(S, target=(0, 0, 0.75), lens=58, orbit=(-32, -22), distance=10.5, height=3.6)
    ms.explode([...], start=1, dur=27, stagger=5)          # exploded view assembling, expo ease-out
    ms.render(S, 'out/')                                   # per-frame PNG16 + timings.json
"""
import bpy, bmesh, math, time, json, os
from mathutils import Vector
from bpy_extras import anim_utils

HERE = os.path.dirname(os.path.abspath(__file__))
HDRI = os.environ.get('MSTUDIO_HDRI', os.path.expanduser('~/.cache/faceless-reel/hdri/studio_small_09.hdr'))

# ---------- scene and render presets ----------
PRESETS = {   # samples, motion blur, shadow catcher. 12 samples matched 24 once denoised with albedo+normal (tested).
    'draft': dict(samples=6, mblur=False, catcher=False, scale=50),
    'final': dict(samples=16, mblur=True, catcher=False, scale=100),
    'hero':  dict(samples=16, mblur=True, catcher=True, scale=100),
}

def scene(size=760, frames=60, fps=30, preset='final', view='Khronos PBR Neutral'):
    """Fresh scene with the tested Cycles settings."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    S = bpy.context.scene; p = PRESETS[preset]; S['preset'] = preset
    S.render.engine = 'CYCLES'; S.cycles.device = 'CPU'
    S.cycles.samples = p['samples']; S.cycles.use_adaptive_sampling = True; S.cycles.adaptive_threshold = 0.05
    S.cycles.use_denoising = True; S.cycles.denoiser = 'OPENIMAGEDENOISE'
    S.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'; S.cycles.denoising_prefilter = 'ACCURATE'
    c = S.cycles  # trimmed light paths: metal needs glossy bounces, little else (tested: no visible loss)
    c.max_bounces = 6; c.diffuse_bounces = 2; c.glossy_bounces = 4; c.transmission_bounces = 4; c.volume_bounces = 0
    c.transparent_max_bounces = 4; c.caustics_reflective = False; c.caustics_refractive = False
    c.sample_clamp_indirect = 10; c.blur_glossy = 0.5           # Filter Glossy: fewer fireflies from sharp reflections
    S.render.use_persistent_data = True
    S.render.resolution_x = S.render.resolution_y = size; S.render.resolution_percentage = p['scale']
    S.render.film_transparent = True; S.render.fps = fps; S.frame_start, S.frame_end = 1, frames
    S.render.image_settings.file_format = 'PNG'; S.render.image_settings.color_mode = 'RGBA'; S.render.image_settings.color_depth = '16'
    S.view_settings.view_transform = view                      # Khronos: brass stays true to the brand amber (tested)
    S.render.use_motion_blur = p['mblur']; S.render.motion_blur_shutter = 0.5
    if p['catcher']: shadow_catcher(S)
    return S

# ---------- materials ----------
# Base colours are linear and capped at 0.8 (manual: near-1.0 colours add noise). (rgb, metallic, roughness, extras)
MATERIALS = {
    'brass':      ((0.80, 0.58, 0.21), 1.0, 0.28, {}),
    'steel':      ((0.70, 0.73, 0.78), 1.0, 0.22, {}),
    'aluminium':  ((0.80, 0.80, 0.80), 1.0, 0.32, {}),
    'copper':     ((0.80, 0.45, 0.30), 1.0, 0.25, {}),
    'iron':       ((0.33, 0.34, 0.36), 1.0, 0.45, {}),
    'heat_steel': ((0.70, 0.73, 0.78), 1.0, 0.25, {'Thin Film IOR': 2.0, 'heat_range': (120.0, 210.0)}),  # thin film 120-210 nm: straw, bronze, purple, blue (swept)
    'rubber':     ((0.03, 0.03, 0.035), 0.0, 0.85, {}),
    'plastic':    ((0.05, 0.09, 0.22), 0.0, 0.40, {}),        # brand navy
    'plastic_white': ((0.75, 0.75, 0.75), 0.0, 0.35, {}),
    'accent':     ((0.80, 0.52, 0.12), 0.0, 0.35, {}),        # brand amber as a painted part
    'glass':      ((0.80, 0.80, 0.80), 0.0, 0.02, {'Transmission Weight': 1.0, 'IOR': 1.5}),
    'prism_glass': ((0.80, 0.80, 0.80), 0.0, 0.0, {'Transmission Weight': 1.0, 'IOR': 1.52, 'Dispersion': 0.6}),  # 5.3 dispersion
}

def material(name, variation=True, edges=True):
    """Library material with surface variation (noise in roughness and a 3% colour shift) and an edge/recess mask
    from Pointiness (cheap; the AO node is expensive per the manual). Cached by name."""
    key = f'ms_{name}_{int(variation)}{int(edges)}'
    if key in bpy.data.materials: return bpy.data.materials[key]
    rgb, metal, rough, extras = MATERIALS[name]
    m = bpy.data.materials.new(key); m.use_nodes = True; nt = m.node_tree; P = nt.nodes['Principled BSDF']
    P.inputs['Metallic'].default_value = metal; P.inputs['Roughness'].default_value = rough
    for k, v in extras.items():
        if k in P.inputs: P.inputs[k].default_value = v
    if 'heat_range' in extras:   # heat tint varies across the part: noise drives the oxide film thickness
        hn = nt.nodes.new('ShaderNodeTexNoise'); hn.inputs['Scale'].default_value = 2.5; hn.inputs['Detail'].default_value = 3
        hr = nt.nodes.new('ShaderNodeMapRange'); hr.inputs['To Min'].default_value, hr.inputs['To Max'].default_value = extras['heat_range']
        nt.links.new(hn.outputs['Fac'], hr.inputs['Value']); nt.links.new(hr.outputs['Result'], P.inputs['Thin Film Thickness'])
    colour = nt.nodes.new('ShaderNodeRGB'); colour.outputs[0].default_value = (*rgb, 1); out = colour.outputs[0]
    if variation and extras.get('Transmission Weight', 0) == 0:
        n = nt.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = 18 if metal else 9; n.inputs['Detail'].default_value = 6
        r = nt.nodes.new('ShaderNodeMapRange'); r.inputs['To Min'].default_value = rough - 0.035; r.inputs['To Max'].default_value = rough + 0.035
        nt.links.new(n.outputs['Fac'], r.inputs['Value']); nt.links.new(r.outputs['Result'], P.inputs['Roughness'])
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
        mix.inputs['A'].default_value = tuple(v * 0.97 for v in rgb) + (1,); mix.inputs['B'].default_value = tuple(min(0.8, v * 1.03) for v in rgb) + (1,)
        nt.links.new(n.outputs['Fac'], mix.inputs['Factor']); out = mix.outputs['Result']
    if edges and extras.get('Transmission Weight', 0) == 0:
        g = nt.nodes.new('ShaderNodeNewGeometry'); ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.42; ramp.color_ramp.elements[0].color = (0.82, 0.82, 0.82, 1)  # recesses slightly darker
        ramp.color_ramp.elements[1].position = 0.58; ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
        e = ramp.color_ramp.elements.new(0.5); e.color = (0.94, 0.94, 0.94, 1)
        nt.links.new(g.outputs['Pointiness'], ramp.inputs['Fac'])
        mul = nt.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs['Factor'].default_value = 1.0
        nt.links.new(out, mul.inputs['A']); nt.links.new(ramp.outputs['Color'], mul.inputs['B']); out = mul.outputs['Result']
    nt.links.new(out, P.inputs['Base Color'])
    return m

# ---------- geometry ----------
def cylinder(radius, depth, axis='Z', location=(0, 0, 0), verts=96):
    rot = {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=location, rotation=rot)
    return bpy.context.object

def box(size, location=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, scale=size); return bpy.context.object

def cut(obj, cutter):
    """Boolean difference, applied; the cutter is deleted."""
    m = obj.modifiers.new('cut', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = cutter
    bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier='cut'); bpy.data.objects.remove(cutter)
    return obj

def bevel(obj, width=0.025, segments=3):
    """Real parts never have razor edges: highlights catch the rounded edge (tested, no render cost).
    Never add Weighted Normal on round parts: it flattened the pins' shading (tested)."""
    b = obj.modifiers.new('bevel', 'BEVEL'); b.width = width; b.segments = segments; b.limit_method = 'ANGLE'
    return obj

def part(obj, mat, smooth=True, bevel_width=0.025, name=None):
    """A finished part: material, smooth shading by angle, bevel."""
    if name: obj.name = name
    obj.data.materials.clear(); obj.data.materials.append(material(mat) if isinstance(mat, str) else mat)
    if smooth:
        bpy.context.view_layer.objects.active = obj; obj.select_set(True)
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    if bevel_width: bevel(obj, bevel_width)
    return obj

def spring(radius=0.14, wire=0.03, pitch=0.11, turns=6, location=(0, 0, 0), mat='steel', name=None):
    """Coil spring along Z: a small circle swept by the Screw modifier (no booleans, very light)."""
    bpy.ops.mesh.primitive_circle_add(vertices=12, radius=wire, location=(0, 0, 0), rotation=(math.pi / 2, 0, 0))
    sp = bpy.context.object; bpy.ops.object.transform_apply(rotation=True)
    for v in sp.data.vertices: v.co.x += radius
    sc = sp.modifiers.new('screw', 'SCREW'); sc.axis = 'Z'; sc.screw_offset = pitch; sc.iterations = turns; sc.steps = 32
    sp.location = location; sp.data.materials.append(material(mat))
    if name: sp.name = name
    return sp

def import_cad(path, mat, scale=0.1, name=None):
    """STL from build123d / CadQuery (mm) into Blender units."""
    bpy.ops.wm.stl_import(filepath=path); o = bpy.context.object; o.scale = (scale,) * 3
    bpy.context.view_layer.objects.active = o; bpy.ops.object.transform_apply(scale=True)
    return part(o, mat, bevel_width=0, name=name)          # CAD meshes carry their own fillets

def pivot(name, location=(0, 0, 0), children=()):
    """Empty used as a controller: animate it, children follow (plan pivots in blockout)."""
    bpy.ops.object.empty_add(location=location); e = bpy.context.object; e.name = name
    for c in children:
        c.parent = e; c.matrix_parent_inverse = e.matrix_world.inverted()
    return e

# ---------- animation: real keyframes with easing ----------
def key(obj, path, frames_values, index=-1, ease=('EXPO', 'EASE_OUT')):
    """Keyframes with interpolation/easing on the keys themselves (Blender 5 channelbag API)."""
    for f, v in frames_values:
        setattr(obj, path, v) if index < 0 else getattr(obj, path).__setitem__(index, v)
        obj.keyframe_insert(path, index=index, frame=f)
    ad = obj.animation_data; cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    for fc in cb.fcurves:
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            for k in fc.keyframe_points:
                k.interpolation, k.easing = ease

def explode(objs, offsets, start=1, dur=24, stagger=4, spins=None, assemble=True):
    """Exploded view. Each object travels between home and home+offset (and an optional tilt, degrees),
    staggered so consecutive parts overlap, with an expo ease-out. assemble=True flies in; False flies out."""
    for i, (o, off) in enumerate(zip(objs, offsets)):
        home = o.location.copy(); away = home + Vector(off); a, b = start + i * stagger, start + i * stagger + dur
        p0, p1 = (away, home) if assemble else (home, away)
        key(o, 'location', [(a, p0.copy()), (b, p1.copy())])
        if spins:
            s = math.radians(spins[i]); r0, r1 = ((0, s, 0), (0, 0, 0)) if assemble else ((0, 0, 0), (0, s, 0))
            key(o, 'rotation_euler', [(a, r0), (b, r1)])

# ---------- light ----------
NAVY_LINEAR = (0.0048, 0.0103, 0.0466)   # brand navy #0E1B3D in linear light

def studio(S, hdri=HDRI, hdri_strength=0.5, cards=True, key_energy=900, rim_energy=500, rim_only=None, backdrop=None):
    """Tested rig: CC0 studio HDRI (fills dark sides, real reflections), two reflection cards (softbox shine,
    no render cost), a neutral key, and a rim light. rim_only=[objects] light-links the rim to those parts so one
    hero part pops without relighting everything (manual: Light Linking)."""
    w = bpy.data.worlds.new('studio'); S.world = w; w.use_nodes = True; nt = w.node_tree; bg = nt.nodes['Background']
    if hdri and os.path.exists(hdri):
        env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(hdri)
        nt.links.new(env.outputs['Color'], bg.inputs['Color']); bg.inputs[1].default_value = hdri_strength
    else:
        bg.inputs[0].default_value = (0.05, 0.08, 0.18, 1); bg.inputs[1].default_value = 0.6
    if backdrop:   # opaque brand backdrop for the camera only; reflections and lighting still see the HDRI
        S.render.film_transparent = False      # Rays that passed through glass see the backdrop too: otherwise glass shows
        lp = nt.nodes.new('ShaderNodeLightPath'); flat = nt.nodes.new('ShaderNodeBackground'); flat.inputs[0].default_value = (*backdrop, 1)
        mix = nt.nodes.new('ShaderNodeMixShader'); out = nt.nodes['World Output']   # the grey studio and reads as metal (tested)
        mx = nt.nodes.new('ShaderNodeMath'); mx.operation = 'MAXIMUM'
        nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs[0]); nt.links.new(lp.outputs['Is Transmission Ray'], mx.inputs[1])
        nt.links.new(mx.outputs[0], mix.inputs['Fac']); nt.links.new(bg.outputs[0], mix.inputs[1]); nt.links.new(flat.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])
    if cards:
        for loc, rot in (((0, -6, 4), (math.radians(60), 0, 0)), ((-6, 2, 3), (math.radians(70), 0, math.radians(-110)))):
            bpy.ops.mesh.primitive_plane_add(size=6, location=loc, rotation=rot); cd = bpy.context.object; cd.name = 'reflection_card'
            em = bpy.data.materials.new('card'); em.use_nodes = True; t = em.node_tree; t.nodes.remove(t.nodes['Principled BSDF'])
            e = t.nodes.new('ShaderNodeEmission'); e.inputs['Strength'].default_value = 4; t.links.new(e.outputs[0], t.nodes['Material Output'].inputs[0])
            cd.data.materials.append(em); cd.visible_camera = cd.visible_diffuse = cd.visible_shadow = False
    lights = {}
    for name, loc, energy, size, col in (('key', (4, -5, 7), key_energy, 5, (1, 0.97, 0.92)), ('rim', (-6, 4, 5), rim_energy, 3, (0.75, 0.82, 1.0))):
        bpy.ops.object.light_add(type='AREA', location=loc); L = bpy.context.object; L.name = name
        L.data.energy, L.data.size, L.data.color = energy, size, col
        L.rotation_euler = (math.atan2(math.hypot(loc[0], loc[1]), loc[2]), 0, math.atan2(loc[0], -loc[1])); lights[name] = L
    if rim_only:
        coll = bpy.data.collections.new('rim_receivers')
        for o in rim_only: coll.objects.link(o)
        lights['rim'].light_linking.receiver_collection = coll
    return lights

def bloom(S, strength=0.6, threshold=1.0, kind='Bloom'):
    """Compositor glare on bright pixels (emission, hot highlights). Needs an opaque backdrop (studio(backdrop=...))."""
    ng = bpy.data.node_groups.new('mstudio_comp', 'CompositorNodeTree'); S.compositing_node_group = ng
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers'); gl = ng.nodes.new('CompositorNodeGlare'); out = ng.nodes.new('NodeGroupOutput')
    gl.inputs['Type'].default_value = kind; gl.inputs['Threshold'].default_value = threshold; gl.inputs['Strength'].default_value = strength
    ng.links.new(rl.outputs['Image'], gl.inputs['Image']); ng.links.new(gl.outputs['Image'], out.inputs[0])
    return gl

def shadow_catcher(S, z=-0.95):
    """Invisible floor that only receives shadows, with its own bounce light off so it doesn't wash out colour (tested)."""
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, z)); f = bpy.context.object; f.name = 'shadow_catcher'
    f.is_shadow_catcher = True; f.visible_diffuse = False; f.visible_glossy = False
    return f

# ---------- camera ----------
def camera(S, target=(0, 0, 0), lens=58, distance=10.5, height=3.6, orbit=(-32, -22), dof=None, focus=None):
    """Tracked camera with a slow orbit (degrees, first frame to last) so the shot is never still.
    Longer lenses (50-85 mm) keep mechanical parts free of wide-angle distortion. dof=f-stop for close-ups only."""
    bpy.ops.object.empty_add(location=target); aim = bpy.context.object; aim.name = 'cam_target'
    bpy.ops.object.camera_add(); cam = bpy.context.object; S.camera = cam; cam.data.lens = lens
    tr = cam.constraints.new('TRACK_TO'); tr.target = aim; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
    pos = lambda deg: (target[0] + distance * math.sin(math.radians(deg)), target[1] - distance * math.cos(math.radians(deg)), target[2] + height)
    key(cam, 'location', [(S.frame_start, pos(orbit[0])), (S.frame_end, pos(orbit[1]))], ease=('SINE', 'EASE_IN_OUT'))
    if dof:
        cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = dof; cam.data.dof.focus_object = focus or aim
    return cam

def overflow(S, objs, margin=0.05, step=2, max_pts=600, edges='lrtb'):
    """How far any part leaves the frame (minus a safety margin) across the animation. Projects the evaluated
    mesh's own vertices (not bounding boxes, which overshoot round parts by ~40%) into the camera on every
    `step`-th frame. No rendering needed. edges: which borders count ('lrb' lets things fall in from the top)."""
    from bpy_extras.object_utils import world_to_camera_view
    worst, at = -1.0, None
    for f in range(S.frame_start, S.frame_end + 1, step):
        S.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
        for o in objs:
            oe = o.evaluated_get(dg); me = oe.to_mesh(); vs = me.vertices; n = len(vs)
            for i in range(0, n, max(1, n // max_pts)):
                v = world_to_camera_view(S, S.camera, oe.matrix_world @ vs[i].co)
                over = max(d for e, d in (('l', margin - v.x), ('r', v.x - (1 - margin)), ('b', margin - v.y), ('t', v.y - (1 - margin))) if e in edges)
                if over > worst: worst, at = over, f
            oe.to_mesh_clear()
    return worst, at        # > 0: something leaves the frame; < 0: spare room (the tightest gap to the margin)

def fit(S, objs, margin=0.05, lo=0.5, hi=3.0, iters=9, **kw):
    """Tightest camera distance (scaled along its orbit around the target) that keeps every part inside the
    margin on every frame: subjects fill the frame and nothing gets cropped. Binary search, framing only.
    Physics scenes: call simulate(S) first so every frame holds the simulated positions. kw goes to overflow."""
    cam = S.camera; ad = cam.animation_data; tgt = cam.constraints['Track To'].target.location
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    fcs = [fc for fc in cb.fcurves if fc.data_path == 'location']
    base = {(fc.array_index, i): kp.co[1] for fc in fcs for i, kp in enumerate(fc.keyframe_points)}
    def apply(k):
        for fc in fcs:
            for i, kp in enumerate(fc.keyframe_points):
                t = tgt[fc.array_index]; kp.co[1] = t + (base[(fc.array_index, i)] - t) * k; kp.handle_left[1] = kp.handle_right[1] = kp.co[1]
    for _ in range(iters):
        mid = (lo + hi) / 2; apply(mid)
        if overflow(S, objs, margin, **kw)[0] > 0: lo = mid
        else: hi = mid
    apply(hi); o, f = overflow(S, objs, margin, **kw)
    print(f'MSTUDIO framing: camera distance x{hi:.2f}, ' + (f'overflow {o:.3f} at frame {f}' if o > 0 else f'all parts in frame (tightest margin {-o + margin:.3f})'))
    return o

def simulate(S):
    """Rigid bodies only simulate frame after frame. Step the whole range once to fill the cache; afterwards any frame
    (a still, the framing fit) holds the right positions. Cheap: 100 frames of 150 coins took 3-4 s."""
    if not (S.rigidbody_world and S.rigidbody_world.enabled) or S.get('simulated'): return
    t = time.time()
    for f in range(S.frame_start, S.frame_end + 1): S.frame_set(f)
    S['simulated'] = 1; print(f'MSTUDIO simulated {S.frame_end - S.frame_start + 1} physics frames in {time.time() - t:.0f}s')

# ---------- render, with time logged per frame ----------
def render(S, out, frames=None):
    """Render frame by frame so every frame's time is logged (motion-blurred frames can cost far more)."""
    os.makedirs(out, exist_ok=True); log = []
    env = os.environ.get('MSTUDIO_FRAMES')                   # e.g. "1,45,90": check a look on stills before a full render
    if env and not frames: frames = [int(x) for x in env.split(',')]
    simulate(S)
    for f in (frames or range(S.frame_start, S.frame_end + 1)):
        S.frame_set(f); S.render.filepath = os.path.join(out, f'f_{f:04d}.png'); t = time.time()
        bpy.ops.render.render(write_still=True); log.append({'frame': f, 'seconds': round(time.time() - t, 2)})
    json.dump({'preset': S.get('preset'), 'samples': S.cycles.samples, 'size': S.render.resolution_x, 'frames': log},
              open(os.path.join(out, 'timings.json'), 'w'), indent=1)
    total = sum(x['seconds'] for x in log); print(f'MSTUDIO rendered {len(log)} frames in {total:.0f}s ({total / len(log):.2f} s/frame)')
    return log

# ---------- linked asset library (Blender Studio practice: rely on linking) ----------
def build_library(path):
    """Save every library material into one .blend that episodes link instead of copy."""
    for name in MATERIALS: material(name).use_fake_user = True
    bpy.data.libraries.write(path, set(m for m in bpy.data.materials if m.name.startswith('ms_')), fake_user=True)
    return path

def link_materials(path, names):
    """Link (not append) library materials: one source of truth for every episode."""
    with bpy.data.libraries.load(path, link=True) as (src, dst):
        dst.materials = [n for n in src.materials if any(n == f'ms_{x}_11' for x in names)]
    return {m.name: m for m in dst.materials}
