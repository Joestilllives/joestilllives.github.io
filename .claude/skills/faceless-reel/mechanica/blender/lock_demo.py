"""The pilot's lock hero shot, rebuilt entirely with mstudio (proof that the toolkit covers a real shot).
    blender-venv/bin/python lock_demo.py OUT [FRAMES] [PRESET]"""
import sys, os, math; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mstudio as ms, bpy
out = sys.argv[1]; frames = int(sys.argv[2]) if len(sys.argv) > 2 else 60; preset = sys.argv[3] if len(sys.argv) > 3 else 'hero'
S = ms.scene(size=760, frames=frames, preset=preset)

# Plug: brass cylinder, cut open (cutaway), drilled pin holes, keyway.
plug = ms.cylinder(0.9, 4.6, axis='X', verts=128)
ms.cut(plug, ms.box((5, 1.24, 2.2), (0, -0.62, 0)))
XS = [-1.6, -0.8, 0.0, 0.8, 1.6]
for x in XS: ms.cut(plug, ms.cylinder(0.19, 1.4, location=(x, 0, 0.55), verts=48))
ms.cut(plug, ms.box((4.7, 0.16, 0.5), (0, 0, -0.42)))
ms.part(plug, 'brass', name='plug')

# Pin stacks: key pin (brass) of different lengths, driver pin (steel), spring.
KEY = [0.75, 1.05, 0.60, 1.15, 0.85]; seat = -0.17; movers, offsets, spins, pins = [], [], [], []
for i, (x, kl) in enumerate(zip(XS, KEY)):
    kp = ms.part(ms.cylinder(0.17, kl, location=(x, 0, seat + kl / 2), verts=48), 'brass', name=f'key_pin_{i}')
    dp = ms.part(ms.cylinder(0.17, 0.6, location=(x, 0, seat + kl + 0.3), verts=48), 'steel', name=f'driver_{i}')
    sp = ms.spring(location=(x, 0, seat + kl + 0.6), name=f'spring_{i}')
    for o, lift, spin in ((kp, 0.85, 18), (dp, 1.35, -24), (sp, 1.8, 28)):
        movers.append(o); offsets.append((x * 0.35, 0, lift)); spins.append(spin)
    pins += [kp, dp]

# Exploded view assembling: each stack lands a little after the previous one, expo ease-out (real keyframes).
order = sorted(range(len(movers)), key=lambda k: (k // 3, k % 3))
ms.explode([movers[k] for k in order], [offsets[k] for k in order], start=int(frames * 0.06), dur=int(frames * 0.45),
           stagger=max(1, int(frames * 0.03)), spins=[spins[k] for k in order])

ms.studio(S, rim_only=pins)                       # rim light hits only the pins: they pop against the plug
ms.camera(S, target=(0, 0, 0.75), lens=58, distance=10.5, height=3.6, orbit=(-32, -22))
ms.fit(S, movers + [plug])                        # framing checked before rendering: no part leaves the frame
ms.render(S, out)
