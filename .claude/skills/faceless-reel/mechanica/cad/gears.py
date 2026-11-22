# Two meshing spur gears with true involute teeth (bd_warehouse), exported as STL for Blender.
import inspect
from build123d import export_stl, Pos
from bd_warehouse.gear import SpurGear
print(inspect.signature(SpurGear.__init__))
m = 2.0                                             # module (mm): tooth size; meshing gears must share it
g1 = SpurGear(module=m, tooth_count=20, pressure_angle=20, root_fillet=0.5, thickness=6)
g2 = SpurGear(module=m, tooth_count=12, pressure_angle=20, root_fillet=0.5, thickness=6)
c = m * (20 + 12) / 2                                 # centre distance = module x (z1 + z2) / 2
export_stl(g1, 'cadtest/gear20.stl'); export_stl(Pos(c, 0, 0) * g2, 'cadtest/gear12.stl')
print('centre distance mm', c)
