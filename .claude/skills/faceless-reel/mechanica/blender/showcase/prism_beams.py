"""Showcase 3, light physics done honestly: a real glass prism, with the light beams drawn as glowing geometry whose
paths are COMPUTED: Snell's law at each face, with the refractive index per wavelength from the Sellmeier equation for
SCHOTT N-SF11 dense flint glass (B1-3, C1-3 from SCHOTT's published data; about 3x the dispersion of BK7, which is
why demonstration prisms use flint). Cycles cannot path-trace this dispersed caustic
on CPU (tested: plain and MNEE both gave no spectrum), so the physics is computed in Python and drawn.
    blender-venv/bin/python prism_beams.py OUT [FRAMES] [PRESET]"""
import sys, os, math; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 60; preset = sys.argv[3] if len(sys.argv) > 3 else 'final'
S = ms.scene(size=1080, frames=frames, preset=preset)

B, C = (1.73759695, 0.313747346, 1.89878101), (0.013188707, 0.0623068142, 155.23629)   # N-SF11 Sellmeier (C in um^2)
def n_bk7(nm):
    l2 = (nm / 1000.0) ** 2; return math.sqrt(1 + sum(b * l2 / (l2 - c) for b, c in zip(B, C)))

def refract(d, nrm, n1, n2):        # 2D Snell's law; nrm points against d
    cos_i = -(d[0] * nrm[0] + d[1] * nrm[1]); r = n1 / n2; k = 1 - r * r * (1 - cos_i * cos_i)
    if k < 0: return None           # total internal reflection
    t = r * cos_i - math.sqrt(k); return (r * d[0] + t * nrm[0], r * d[1] + t * nrm[1])

def hit(p, d, a, b):                # ray p+t*d against segment a-b; returns (t, point, outward normal)
    ex, ey = b[0] - a[0], b[1] - a[1]; den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-9: return None
    t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den; u = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
    if t <= 1e-6 or not 0 <= u <= 1: return None
    nx, ny = ey, -ex; ln = math.hypot(nx, ny); return t, (p[0] + t * d[0], p[1] + t * d[1]), (nx / ln, ny / ln)

R = 1.1; Z = 1.0
tri = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in (90, 210, 330)]
faces = [(tri[i], tri[(i + 1) % 3]) for i in range(3)]
def first_hit(p, d, inside):
    best = None
    for a, b in faces:
        h = hit(p, d, a, b)
        if h and (best is None or h[0] < best[0]): best = h
    t, q, nrm = best; c = (q[0] - sum(x for x, _ in tri) / 3, q[1] - sum(y for _, y in tri) / 3)
    if nrm[0] * c[0] + nrm[1] * c[1] < 0: nrm = (-nrm[0], -nrm[1])        # make the normal point outward
    return q, nrm

def wl_rgb(nm):                     # approximate visible-spectrum colour (linear)
    stops = [(400, (0.35, 0.0, 0.8)), (450, (0.0, 0.15, 1.0)), (490, (0.0, 0.8, 0.9)), (530, (0.1, 1.0, 0.1)),
             (575, (1.0, 0.95, 0.0)), (610, (1.0, 0.45, 0.0)), (660, (1.0, 0.0, 0.0)), (700, (0.6, 0.0, 0.0))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if a <= nm <= b: f = (nm - a) / (b - a); return tuple(x + (y - x) * f for x, y in zip(ca, cb))
    return stops[-1][1]

def beam(p0, p1, rgb, strength, radius, name):
    """A glowing beam: thin emissive cylinder between two points (visible to camera only; it does not light the scene)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]; L = math.hypot(dx, dy)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=L, location=((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, Z),
                                        rotation=(0, math.pi / 2, math.atan2(dy, dx)))
    o = bpy.context.object; o.name = name
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree; t.nodes.remove(t.nodes['Principled BSDF'])
    e = t.nodes.new('ShaderNodeEmission'); e.inputs['Color'].default_value = (*rgb, 1); e.inputs['Strength'].default_value = strength
    t.links.new(e.outputs[0], t.nodes['Material Output'].inputs[0]); o.data.materials.append(m)
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = o.visible_shadow = False
    return o

# Aim at the minimum-deviation angle for a 60-degree prism (textbook setup; avoids total internal reflection):
# incidence theta1 = asin(n * sin(30 deg)) at the middle of the spectrum (550 nm), measured from the entry face normal.
fa, fb = faces[0]; mid = ((fa[0] + fb[0]) / 2, (fa[1] + fb[1]) / 2); fn = (fb[1] - fa[1], -(fb[0] - fa[0]))
if fn[0] * mid[0] + fn[1] * mid[1] < 0: fn = (-fn[0], -fn[1])
fn_ang = math.atan2(fn[1], fn[0]); th1 = math.asin(n_bk7(550) * math.sin(math.radians(30)))
d_ang = fn_ang + math.pi - th1; d0 = (math.cos(d_ang), math.sin(d_ang)); src = (mid[0] - 9 * d0[0], mid[1] - 9 * d0[1])
print('incidence %.1f deg' % math.degrees(th1))
entry, n_in = first_hit(src, d0, False)
beams = [beam(src, entry, (1, 1, 1), 6, 0.035, 'white_in')]
rays = []
for nm in range(400, 701, 5):
    n = n_bk7(nm); d1 = refract(d0, n_in, 1.0, n)
    p_in = (entry[0] + d1[0] * 1e-4, entry[1] + d1[1] * 1e-4); exit_p, n_out = first_hit(p_in, d1, True)
    d2 = refract(d1, (-n_out[0], -n_out[1]), n, 1.0)
    if d2 is None: continue
    rays.append((nm, exit_p, (exit_p[0] + d2[0] * 9.0, exit_p[1] + d2[1] * 9.0)))
beams.append(beam(entry, rays[len(rays) // 2][1], (0.9, 0.9, 0.9), 3, 0.02, 'inside'))
import bmesh
me = bpy.data.meshes.new('spectrum'); bm = bmesh.new(); col = bm.loops.layers.color.new('spec')
for (n1, a1, e1), (n2, a2, e2) in zip(rays, rays[1:]):          # one quad per wavelength step: a continuous fan
    vs = [bm.verts.new((x, y, Z)) for x, y in (a1, a2, e2, e1)]; f = bm.faces.new(vs)
    for lp, nm in zip(f.loops, (n1, n2, n2, n1)): lp[col] = (*wl_rgb(nm), 1)
bm.to_mesh(me); bm.free(); fan = bpy.data.objects.new('spectrum', me); S.collection.objects.link(fan)
m = bpy.data.materials.new('spectrum'); m.use_nodes = True; t = m.node_tree; t.nodes.remove(t.nodes['Principled BSDF'])
ca = t.nodes.new('ShaderNodeVertexColor'); ca.layer_name = 'spec'; e = t.nodes.new('ShaderNodeEmission'); e.inputs['Strength'].default_value = 2.2   # bright enough to glow, not so bright it clips to white
t.links.new(ca.outputs['Color'], e.inputs['Color']); t.links.new(e.outputs[0], t.nodes['Material Output'].inputs[0]); fan.data.materials.append(m)
fan.visible_diffuse = fan.visible_glossy = fan.visible_transmission = fan.visible_shadow = False
print('spread at 9 units: %.2f units' % math.dist(rays[0][2], rays[-1][2]))
print('N-SF11 n(400nm)=%.4f n(700nm)=%.4f' % (n_bk7(400), n_bk7(700)))

# The prism itself: real dispersive glass, bevelled, on an invisible shadow-catching floor.
bpy.ops.mesh.primitive_cylinder_add(vertices=3, radius=R, depth=2.2, location=(0, 0, Z))
prism = ms.part(bpy.context.object, 'prism_glass', smooth=False, bevel_width=0.02, name='prism')
ms.studio(S, hdri_strength=0.35, backdrop=ms.NAVY_LINEAR, key_energy=250, rim_energy=600)
ms.bloom(S, strength=0.6, threshold=1.6)
# Light should travel left to right across the frame: point screen-right along the bisector of the in and out beams.
mo = rays[len(rays) // 2]; dout = (mo[2][0] - mo[1][0], mo[2][1] - mo[1][1]); lo = math.hypot(*dout); dout = (dout[0] / lo, dout[1] / lo)
rx, ry = d0[0] + dout[0], d0[1] + dout[1]; a = math.degrees(math.atan2(ry, rx))
ms.camera(S, target=(0.8 * dout[0], 0.8 * dout[1], Z), lens=24, distance=10.0, height=4.5, orbit=(a - 5, a + 5))
ms.fit(S, beams + [fan, prism], margin=0.06)
ms.render(S, out)
