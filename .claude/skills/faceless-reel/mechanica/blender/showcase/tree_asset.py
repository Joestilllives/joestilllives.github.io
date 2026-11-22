"""Organic test 1: a downloaded CC0 tree (Poly Haven 'Jacaranda Tree', 1k textures) in the Mechanica studio.
Objects are APPENDED from the .blend as data (no scripts in the file run; the script lists any it finds).
    blender-venv/bin/python tree_asset.py OUT [FRAMES] [PRESET]      env TBOUNCE (transparent bounces, default 8)
The file holds the tree twice (plus lower-detail LOD1 copies, all visible): VARIANT=mesh is one 2.2M-polygon mesh with
the leaves baked in plus the trunk; VARIANT=gn is a 141k-polygon branch mesh whose Geometry Nodes scatter leaf objects."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 60; preset = sys.argv[3] if len(sys.argv) > 3 else 'final'
SRC = os.path.expanduser('~/.cache/faceless-reel/assets/jacaranda_tree/jacaranda_tree_1k.blend')
S = ms.scene(size=1080, frames=frames, preset=preset)
S.cycles.transparent_max_bounces = int(os.environ.get('TBOUNCE', 8))     # leaves are alpha-cut cards stacked deep
with bpy.data.libraries.load(SRC, link=False) as (src, dst):
    V = os.environ.get('VARIANT', 'gn')
    dst.objects = ['jacaranda_tree_LOD0', 'jacaranda_tree_trunk_LOD0'] if V == 'mesh' else ['jacaranda_tree_geometry_nodes']
    print('MSTUDIO asset texts (scripts) in file:', list(src.texts) or 'none')
tree = []
for o in dst.objects:
    if o is None or o.type not in ('MESH', 'EMPTY', 'CURVES'): continue
    S.collection.objects.link(o); tree.append(o)
    if o.name.startswith('jacaranda_tree_geometry_nodes'): o.location = (0, 0, 0)   # the file parks it 24.75 to the side
meshes = [o for o in tree if o.type == 'MESH']
print('MSTUDIO tree objects:', [(o.name, len(o.data.polygons)) for o in meshes])
# Stand it on the floor at the origin, whatever units the asset uses.
from mathutils import Vector
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
h = hi.z - lo.z; k = 4.0 / h                                   # scale to 4 units tall, like our other scenes
for o in tree:
    if o.parent is None: o.location = (o.location - Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))) * k; o.scale = o.scale * k
print(f'MSTUDIO tree height {h:.2f} asset units, scaled x{k:.3f}')
ms.shadow_catcher(S, z=0.0)
E = os.environ.get
ms.studio(S, hdri_strength=float(E('HDRI', 1.0)), key_energy=float(E('KEY', 2500)), rim_energy=float(E('RIM', 1500)), backdrop=ms.NAVY_LINEAR)
ms.camera(S, target=(0, 0, 2.0), lens=50, distance=11.0, height=2.6, orbit=(-25, 5))
ms.fit(S, meshes, margin=0.05, max_pts=300)
ms.render(S, out)
