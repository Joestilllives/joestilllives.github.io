# Mechanica Blender toolkit

Headless Blender 5.3 (bpy) on CPU. Everything here was tested on this machine; findings are in the planning doc's
Blender playbook tab.

| File | What |
| --- | --- |
| `mstudio.py` | The studio: scene presets (draft/final/hero), 12-material library with surface variation and edge masks, modelling helpers, eased keyframes, exploded views, studio light rig (HDRI, reflection cards, light-linked rim), brand backdrop, bloom, camera with pre-render framing fit, per-frame-timed render, linked material library |
| `qa3d.py` | Gates for a rendered sequence: frames present, no empty frame, not cropped, render-time spikes, fireflies, flicker; writes a contact sheet to look at |
| `lock_demo.py` | The pilot's lock hero shot rebuilt with mstudio |
| `gears_demo.py` | CAD-accurate gears (build123d) assembling and meshing at the true ratio |
| `showcase/hexfield.py` | Procedural motion graphics: Geometry Nodes built in Python, 3,136 pillars rippling, glowing crests, bloom |
| `showcase/coins.py` | Rigid-body physics: 150 coins pouring onto an invisible shadow-catching floor |
| `showcase/prism_beams.py` | Light physics: real glass prism, spectrum computed from Snell's law + SCHOTT Sellmeier data |
| `showcase/prism.py` | The failed path-traced caustic attempt, kept as evidence (plain and MNEE gave no spectrum) |

Quick start:
```bash
B=~/.cache/faceless-reel/blender-venv/bin/python
MSTUDIO_FRAMES=1,30,60 $B lock_demo.py out/ 60 draft   # look at stills first
$B lock_demo.py out/ 60 hero && python3 qa3d.py out/    # then the real thing, then the gates
```
Needs the studio HDRI at `~/.cache/faceless-reel/hdri/studio_small_09.hdr` (Poly Haven, CC0).
