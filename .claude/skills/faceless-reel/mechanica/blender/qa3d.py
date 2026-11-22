"""Quality gates for a rendered Blender sequence (transparent PNGs + timings.json from mstudio.render).

    python3 qa3d.py FRAMES_DIR [--expect N]

Gates (PASS/FAIL with the number behind each; exit 1 on any FAIL):
  frames present      every expected frame exists
  no empty frame      the subject covers >= 0.5% of every frame
  not cropped         no solid subject pixels on the frame border (shadow-catcher shadows are semi-transparent, ignored)
  render-time spikes  no frame takes more than 3x the median (Blender Studio found motion-blurred frames up to 100x)
  fireflies           <= 20 isolated hot pixels per frame (bright specks the denoiser missed)
  flicker             low frame-to-frame noise on parts that are not moving (per-frame denoising can shimmer)
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

def main(d, expect=None):
    files = sorted(f for f in os.listdir(d) if f.startswith('f_') and f.endswith('.png'))
    T = json.load(open(os.path.join(d, 'timings.json'))) if os.path.exists(os.path.join(d, 'timings.json')) else None
    n = expect or (len(T['frames']) if T else len(files))
    gate(len(files) == n, 'frames present', f'{len(files)} of {n}')
    cover, crop, flies, rgbs, alphas = [], [], [], [], []
    for f in files:
        rgb, a = load(os.path.join(d, f)); rgbs.append(rgb); alphas.append(a)
        cover.append(float((a > 0.5).mean()))
        b = np.concatenate([a[:3].ravel(), a[-3:].ravel(), a[:, :3].ravel(), a[:, -3:].ravel()])
        crop.append(float((b > 0.9).mean()))
        lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) * a
        med = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))).astype(np.float32) / 255
        flies.append(int(((lum > 0.9) & (lum > med * 2.0 + 0.15)).sum()))
    gate(min(cover) >= 0.005, 'no empty frame', f'smallest subject coverage {min(cover) * 100:.2f}%')
    worst = int(np.argmax(crop))
    gate(max(crop) <= 0.001, 'not cropped', f'worst {files[worst]}: {max(crop) * 100:.2f}% of border is solid subject')
    if T:
        secs = [x['seconds'] for x in T['frames']]; med = statistics.median(secs)
        gate(max(secs) <= 3 * med, 'render-time spikes', f'median {med:.2f}s, max {max(secs):.2f}s, total {sum(secs):.0f}s')
    gate(max(flies) <= 20, 'fireflies', f'max {max(flies)} hot pixels in a frame (frame {files[int(np.argmax(flies))]})')
    if len(rgbs) >= 3:
        res = []
        for i in range(1, len(rgbs) - 1):
            p, c, nx = rgbs[i - 1], rgbs[i], rgbs[i + 1]
            solid = (alphas[i - 1] > 0.95) & (alphas[i] > 0.95) & (alphas[i + 1] > 0.95)
            still = (np.abs(nx - p).max(axis=2) < 0.02) & solid           # pixels on parts that are not moving
            if still.sum() > 500:
                res.append(float(np.abs(c - (p + nx) / 2).max(axis=2)[still].mean()))
        if res:
            gate(max(res) <= 0.012, 'flicker', f'mean residual on still parts {statistics.mean(res):.4f}, worst {max(res):.4f} (limit 0.012)')
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
    sys.exit(main(sys.argv[1], e))
