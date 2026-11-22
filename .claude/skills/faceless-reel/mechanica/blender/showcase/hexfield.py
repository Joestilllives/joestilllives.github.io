"""Showcase 1, procedural motion graphics: a field of hexagonal metal pillars rippling like a liquid surface.
Built as a Geometry Nodes tree from Python (no hand work), animated by Scene Time, crests glow brand amber.
    blender-venv/bin/python hexfield.py OUT [FRAMES] [PRESET]"""
import sys, os, math; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 90; preset = sys.argv[3] if len(sys.argv) > 3 else 'final'
S = ms.scene(size=1080, frames=frames, preset=preset); S.render.resolution_y = 1080

# ---- Geometry Nodes, built in code ----
ng = bpy.data.node_groups.new('hexfield', 'GeometryNodeTree')
ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
N, L = ng.nodes.new, ng.links.new
COLS, SIZE = 56, 24.0; DX = SIZE / (COLS - 1); DY = DX * math.sqrt(3) / 2
grid = N('GeometryNodeMeshGrid'); grid.inputs['Size X'].default_value = SIZE; grid.inputs['Size Y'].default_value = DY * (COLS - 1)
grid.inputs['Vertices X'].default_value = grid.inputs['Vertices Y'].default_value = COLS                # 3,136 pillars
gp = N('GeometryNodeInputPosition'); sep = N('ShaderNodeSeparateXYZ'); row = N('ShaderNodeMath'); row.operation = 'DIVIDE'; row.inputs[1].default_value = DY
rnd = N('ShaderNodeMath'); rnd.operation = 'ROUND'; odd = N('ShaderNodeMath'); odd.operation = 'FLOORED_MODULO'; odd.inputs[1].default_value = 2
half = N('ShaderNodeMath'); half.operation = 'MULTIPLY'; half.inputs[1].default_value = DX / 2; shift = N('ShaderNodeCombineXYZ')
setp = N('GeometryNodeSetPosition')
L(gp.outputs['Position'], sep.inputs[0]); L(sep.outputs['Y'], row.inputs[0]); L(row.outputs[0], rnd.inputs[0]); L(rnd.outputs[0], odd.inputs[0])
L(odd.outputs[0], half.inputs[0]); L(half.outputs[0], shift.inputs['X']); L(grid.outputs['Mesh'], setp.inputs['Geometry']); L(shift.outputs['Vector'], setp.inputs['Offset'])
pts = N('GeometryNodeMeshToPoints')
hexa = N('GeometryNodeMeshCylinder'); hexa.inputs['Vertices'].default_value = 6; hexa.inputs['Radius'].default_value = (DX - 0.035) / math.sqrt(3); hexa.inputs['Depth'].default_value = 2.0
rot = N('GeometryNodeTransform'); rot.inputs['Rotation'].default_value = (0, 0, math.radians(30))
hexa.fill_type = 'NGON'
setmat = N('GeometryNodeSetMaterial')
inst = N('GeometryNodeInstanceOnPoints')
pos = N('GeometryNodeInputPosition'); t = N('GeometryNodeInputSceneTime')
length = N('ShaderNodeVectorMath'); length.operation = 'LENGTH'
# height = 0.55*sin(1.1*r - 2.2*t) + 0.35*noise(p*0.18 + t*0.15)  : a ripple from the centre plus slow organic drift
mr = N('ShaderNodeMath'); mr.operation = 'MULTIPLY'; mr.inputs[1].default_value = 1.1
mt = N('ShaderNodeMath'); mt.operation = 'MULTIPLY'; mt.inputs[1].default_value = 2.2
sub = N('ShaderNodeMath'); sub.operation = 'SUBTRACT'
sn = N('ShaderNodeMath'); sn.operation = 'SINE'
amp = N('ShaderNodeMath'); amp.operation = 'MULTIPLY'; amp.inputs[1].default_value = 0.55
noise = N('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 0.18; noise.inputs['Detail'].default_value = 2
nt4 = N('ShaderNodeMath'); nt4.operation = 'MULTIPLY'; nt4.inputs[1].default_value = 0.15
addv = N('ShaderNodeVectorMath'); addv.operation = 'ADD'
namp = N('ShaderNodeMath'); namp.operation = 'MULTIPLY_ADD'; namp.inputs[1].default_value = 0.7; namp.inputs[2].default_value = -0.35
h = N('ShaderNodeMath'); h.operation = 'ADD'
store = N('GeometryNodeStoreNamedAttribute'); store.data_type = 'FLOAT'; store.domain = 'INSTANCE'; store.inputs['Name'].default_value = 'crest'
trans = N('GeometryNodeTranslateInstances'); comb = N('ShaderNodeCombineXYZ')
outn = N('NodeGroupOutput')
L(setp.outputs['Geometry'], pts.inputs['Mesh']); L(pts.outputs['Points'], inst.inputs['Points'])
L(hexa.outputs['Mesh'], rot.inputs['Geometry']); L(rot.outputs['Geometry'], setmat.inputs['Geometry']); L(setmat.outputs['Geometry'], inst.inputs['Instance'])
L(pos.outputs['Position'], length.inputs[0]); L(length.outputs['Value'], mr.inputs[0]); L(t.outputs['Seconds'], mt.inputs[0])
L(mr.outputs[0], sub.inputs[0]); L(mt.outputs[0], sub.inputs[1]); L(sub.outputs[0], sn.inputs[0]); L(sn.outputs[0], amp.inputs[0])
L(t.outputs['Seconds'], nt4.inputs[0]); L(pos.outputs['Position'], addv.inputs[0]); L(nt4.outputs[0], addv.inputs[1])
L(addv.outputs['Vector'], noise.inputs['Vector']); L(noise.outputs['Fac'], namp.inputs[0])
L(amp.outputs[0], h.inputs[0]); L(namp.outputs[0], h.inputs[1])
L(h.outputs[0], comb.inputs['Z']); L(inst.outputs['Instances'], store.inputs['Geometry']); L(h.outputs[0], store.inputs['Value'])
L(store.outputs['Geometry'], trans.inputs['Instances']); L(comb.outputs['Vector'], trans.inputs['Translation'])
L(trans.outputs['Instances'], outn.inputs[0])

# ---- material: dark brushed metal; the crests (high pillars) glow amber through the instance attribute ----
ms.MATERIALS['anodised'] = ((0.06, 0.07, 0.09), 1.0, 0.24, {})
m = ms.material('anodised').copy(); m.name = 'hex_metal'; tree = m.node_tree; P = tree.nodes['Principled BSDF']
att = tree.nodes.new('ShaderNodeAttribute'); att.attribute_type = 'INSTANCER'; att.attribute_name = 'crest'
ramp = tree.nodes.new('ShaderNodeValToRGB'); ramp.color_ramp.elements[0].position = 0.52; ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
ramp.color_ramp.elements[1].position = 0.82; ramp.color_ramp.elements[1].color = (1.0, 0.55, 0.12, 1)
geo = tree.nodes.new('ShaderNodeNewGeometry'); nz = tree.nodes.new('ShaderNodeSeparateXYZ'); top = tree.nodes.new('ShaderNodeMath'); top.operation = 'GREATER_THAN'; top.inputs[1].default_value = 0.9
cap = tree.nodes.new('ShaderNodeMix'); cap.data_type = 'RGBA'; cap.inputs['A'].default_value = (0, 0, 0, 1)
tree.links.new(geo.outputs['Normal'], nz.inputs[0]); tree.links.new(nz.outputs['Z'], top.inputs[0]); tree.links.new(top.outputs[0], cap.inputs['Factor'])
tree.links.new(att.outputs['Fac'], ramp.inputs['Fac']); tree.links.new(ramp.outputs['Color'], cap.inputs['B']); tree.links.new(cap.outputs['Result'], P.inputs['Emission Color'])
P.inputs['Emission Strength'].default_value = 9.0
setmat.inputs['Material'].default_value = m

bpy.ops.mesh.primitive_plane_add(size=1); host = bpy.context.object; host.name = 'hexfield'
mod = host.modifiers.new('hexfield', 'NODES'); mod.node_group = ng

ms.studio(S, hdri_strength=0.35, key_energy=300, rim_energy=1200, backdrop=ms.NAVY_LINEAR)
if os.environ.get('NOBLOOM') != '1': ms.bloom(S, strength=0.7, threshold=1.2)
bpy.ops.object.empty_add(location=(0, 0, 0.3)); focus = bpy.context.object
cam = ms.camera(S, target=(0, 0, 0.2), lens=50, distance=9.0, height=3.2, orbit=(-25, -5), dof=2.0, focus=focus)
ms.render(S, out)
