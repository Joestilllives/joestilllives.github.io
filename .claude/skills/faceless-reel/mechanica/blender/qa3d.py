"""Quality gates for a rendered Blender sequence (transparent PNGs + timings.json from mstudio.render).

    python3 qa3d.py FRAMES_DIR [--expect N] [--edges lrtb]

Gates (PASS/FAIL with the number behind each; exit 1 on any FAIL):
  frames present      every expected frame exists
  no empty frame      the subject covers >= 0.5% of every frame
  not cropped         no solid subject pixels on the checked borders (--edges, default all four; e.g. lrb when things
                      fall in from the top on purpose). Transparent film: alpha > 0.9. Opaque backdrop: differs from
                      the backdrop colour (read from the corners of the last frame) by more than 0.1
  render-time spikes  no frame takes more than 3x the median (Blender Studio found motion-blurred frames up to 100x).
                      Frame 1 is excluded: it pays one-off setup (BVH build, kernels) and ran 3x the median on the coins
  fireflies           <= 20 isolated hot pixels per frame (bright specks the denoiser missed; thin lines excluded)
  flicker             low frame-to-frame noise on parts that are not moving (per-frame denoising can shimmer). Uses the
                      median residual per frame, so a fast object crossing in one frame is not mistaken for flicker
Also writes sheet.png: 8 frames composited on brand navy, for a human look.
"""
import json, os, sys, statistics
import numpy as np
from PIL import Image, ImageFilter

NAVY = (14, 27, 61)
failed = []
def gate(ok, name, detail):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<22} {detail}")
    if not ok: failed.append(name)

def load(p):
    a = np.asarray(Image.open(p).convert('RGBA')).astype(np.float32) / 255.0
    return a[..., :3], a[..., 3]

def main(d, expect=None, edges='lrtb'):
    files = sorted(f for f in os.listdir(d) if f.startswith('f_') and f.endswith('.png'))
    T = json.load(open(os.path.join(d, 'timings.json'))) if os.path.exists(os.path.join(d, 'timings.json')) else None
    n = expect or (len(T['frames']) if T else len(files))
    gate(len(files) == n, 'frames present', f'{len(files)} of {n}')
    cover, crop, flies, rgbs, alphas = [], [], [], [], []
    rgb_last, a_last = load(os.path.join(d, files[-1])); opaque = a_last.min() > 0.99
    if opaque:                                     # backdrop rendered in: the subject is whatever differs from its colour
        bg = np.median(np.concatenate([rgb_last[:8, :8].reshape(-1, 3), rgb_last[:8, -8:].reshape(-1, 3)]), axis=0)
    for f in files:
        rgb, a = load(os.path.join(d, f)); rgbs.append(rgb)
        if opaque: a = (np.abs(rgb - bg).max(axis=2) > 0.1).astype(np.float32)
        alphas.append(a if not opaque else np.ones_like(a))
        cover.append(float((a > 0.5).mean()))
        side = {'t': a[:3].ravel(), 'b': a[-3:].ravel(), 'l': a[:, :3].ravel(), 'r': a[:, -3:].ravel()}
        b = np.concatenate([side[e] for e in edges])
        crop.append(float((b > 0.9).mean()))
        lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) * a
        med = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))).astype(np.float32) / 255
        hot = (lum > 0.9) & (lum > med * 2.0 + 0.15)
        # A firefly is isolated: at most 1 of its 8 neighbours is even half as bright. Pixels on thin bright lines
        # (a glowing beam, a bevel highlight) always have 2+, and the median test alone flagged 44 of them on the prism.
        pad = np.pad(lum, 1); nb = sum((pad[1 + dy:pad.shape[0] - 1 + dy, 1 + dx:pad.shape[1] - 1 + dx] > lum * 0.5).astype(np.int8)
                                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
        flies.append(int((hot & (nb <= 1)).sum()))
    gate(min(cover) >= 0.005, 'no empty frame', f'smallest subject coverage {min(cover) * 100:.2f}%')
    worst = int(np.argmax(crop))
    gate(max(crop) <= 0.001, 'not cropped', f'edges {edges}{" (opaque backdrop)" if opaque else ""}: worst {files[worst]} {max(crop) * 100:.2f}% of border is solid subject')
    if T:
        secs = [x['seconds'] for x in T['frames']]; body = secs[1:] or secs; med = statistics.median(body)
        gate(max(body) <= 3 * med, 'render-time spikes', f'median {med:.2f}s, max {max(body):.2f}s (frame 1: {secs[0]:.2f}s), total {sum(secs):.0f}s')
    gate(max(flies) <= 20, 'fireflies', f'max {max(flies)} hot pixels in a frame (frame {files[int(np.argmax(flies))]})')
    if len(rgbs) >= 3:
        res = []
        for i in range(1, len(rgbs) - 1):
            p, c, nx = rgbs[i - 1], rgbs[i], rgbs[i + 1]
            solid = (alphas[i - 1] > 0.95) & (alphas[i] > 0.95) & (alphas[i + 1] > 0.95)
            still = (np.abs(nx - p).max(axis=2) < 0.02) & solid           # pixels on parts that are not moving
            if still.sum() > 500:
                res.append(float(np.median(np.abs(c - (p + nx) / 2).max(axis=2)[still])))
        if res:
            gate(max(res) <= 0.012, 'flicker', f'median residual on still parts: typical {statistics.median(res):.4f}, worst frame {max(res):.4f} (limit 0.012)')
        else:
            gate(True, 'flicker', 'no still region to measure (everything moves)')
    pick = [files[int(i)] for i in np.linspace(0, len(files) - 1, min(8, len(files)))]
    t = 220; sheet = Image.new('RGB', (t * len(pick), t), NAVY)
    for i, f in enumerate(pick):
        im = Image.open(os.path.join(d, f)).convert('RGBA'); bg = Image.new('RGBA', im.size, NAVY + (255,)); bg.alpha_composite(im)
        sheet.paste(bg.convert('RGB').resize((t, t)), (i * t, 0))
    sheet.save(os.path.join(d, 'sheet.png')); print(f'  sheet: {os.path.join(d, "sheet.png")}  (look at it)')
    print(f'{len(failed)} gate failures'); return 1 if failed else 0

if __name__ == '__main__':
    e = int(sys.argv[sys.argv.index('--expect') + 1]) if '--expect' in sys.argv else None
    edges = sys.argv[sys.argv.index('--edges') + 1] if '--edges' in sys.argv else 'lrtb'
    sys.exit(main(sys.argv[1], e, edges))
