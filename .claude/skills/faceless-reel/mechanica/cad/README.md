# Accurate parts from CAD

`gears.py` builds two meshing spur gears with true involute teeth (build123d + bd_warehouse, Apache-2.0) and exports STL.
`render_gears.py` imports them into Blender with the Mechanica look (Khronos PBR Neutral, trimmed light paths, studio HDRI).

```bash
python3 -m venv cad && cad/bin/pip install build123d bd_warehouse
cad/bin/python gears.py                                                    # writes cadtest/gear20.stl, gear12.stl
~/.cache/faceless-reel/blender-venv/bin/python render_gears.py           # paths inside are from the test run
```
Studio HDRI: Poly Haven `studio_small_09` (CC0), fetched via api.polyhaven.com/files/studio_small_09.
