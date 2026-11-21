"""Quality gates for faceless prompt Reels. Every gate prints PASS or FAIL with the number behind it.

    python3 qa.py script posts.json      # before rendering: hooks, asks, hashtags, colour contrast
    python3 qa.py look OUT               # after `render.js --mode look`: safe zones + grayscale sheet
    python3 qa.py final OUT              # after rendering: spec, loudness, Whisper, variety, frames

Exit code 1 if any gate fails.
"""
import glob
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

W, H = 1080, 1920
BOTTOM, RIGHT = 1440, 850          # Instagram caption/audio strip below y=1440, action rail right of x=850
GRID_TOP, GRID_BOTTOM = 285, 1635  # 4:5 profile-grid crop of a 9:16 Reel
failed = []


def gate(ok, name, detail):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<26} {detail}")
    if not ok:
        failed.append(name)


def words(s):
    return len(s.split())


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def script(data):
    pal = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'palette.json')))['worlds']
    print('palette')
    for name, w in pal.items():
        for fg, need in (('ink', 4.5), ('muted', 4.5), ('accent', 3.0)):
            r = contrast(w[fg], w['bg'])
            gate(r >= need, f'{name} {fg} contrast', f'{r:.1f}:1 (need {need}:1)')
        r = contrast(w['ink'], w['panel'])
        gate(r >= 4.5, f'{name} ink on panel', f'{r:.1f}:1')
    posts = json.load(open(data))
    for p in posts:
        print(f"day {p['day']}")
        hooks = [('main', p['say'])] + [(f"single {i + 1}", s['say']) for i, s in enumerate(p.get('singles', []))]
        for name, h in hooks:
            n = words(h)
            gate(5 <= n <= 18, f'hook {name} 5-18 words', f'{n} words: "{h}"')
        cap = p['caption'].lower()
        gate(bool(re.search(r'\b(save|send)\b', cap)), 'caption save/send ask', 'found' if re.search(r'\b(save|send)\b', cap) else 'missing')
        tags = re.findall(r'#\w+', p['caption'])
        gate(len(tags) <= 5, 'caption hashtags <= 5', f'{len(tags)}')


def look(out):
    shots = sorted(glob.glob(os.path.join(out, 'look', '*.png')))
    if not shots:
        sys.exit('no stills: run render.js --mode look first')
    for f in shots:
        im = Image.open(f).convert('RGB')
        px = im.load()
        BG = px[4, 4]  # the corner is always background, whatever the colour world
        def ink(x0, y0, x1, y1):
            return sum(1 for y in range(y0, y1, 4) for x in range(x0, x1, 4)
                       if sum(abs(a - b) for a, b in zip(px[x, y], BG)) > 60)
        bad = ink(0, BOTTOM, W, H) + ink(RIGHT, 0, W, BOTTOM)
        top = ink(0, 0, W, GRID_TOP)
        gate(bad == 0, f'safe zone {os.path.basename(f)[:20]}', f'{bad} ink samples under the IG interface')
        gate(top < 400, f'grid crop {os.path.basename(f)[:20]}', f'{top} ink samples above the 4:5 crop line')
    # Contact sheet: colour with zones on top, luminance-only "squint test" underneath.
    t = 216
    sheet = Image.new('RGB', (t * len(shots), 2 * 384), 'white')
    for i, f in enumerate(shots):
        im = Image.open(f).convert('RGB')
        d = ImageDraw.Draw(im)
        d.rectangle((0, BOTTOM, W, H), outline=(255, 0, 0), width=8)
        d.rectangle((RIGHT, 0, W, BOTTOM), outline=(255, 0, 0), width=8)
        d.line((0, GRID_TOP, W, GRID_TOP), fill=(255, 194, 75), width=6)
        d.line((0, GRID_BOTTOM, W, GRID_BOTTOM), fill=(255, 194, 75), width=6)
        sheet.paste(im.resize((t, 384)), (i * t, 0))
        sheet.paste(ImageOps.grayscale(Image.open(f)).convert('RGB').resize((t, 384)), (i * t, 384))
    path = os.path.join(out, 'look_sheet.png')
    sheet.save(path)
    print(f'  sheet: {path}  (look at it: red = covered by Instagram, gold = grid crop)')


def probe(f):
    j = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', f],
                                  capture_output=True, text=True).stdout)
    v = next(s for s in j['streams'] if s['codec_type'] == 'video')
    a = next((s for s in j['streams'] if s['codec_type'] == 'audio'), {})
    return v, a, j['format']


def loudness(f):
    err = subprocess.run(['ffmpeg', '-nostats', '-i', f, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    lufs = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1])
    peak = float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', err)[-1])
    return lufs, peak


NUM = {'0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five', '6': 'six', '7': 'seven',
       '8': 'eight', '9': 'nine', '10': 'ten', '20': 'twenty', '30': 'thirty', '40': 'forty'}
SAME = {'roll': 'role', 'for': 'four', 'to': 'two', 'too': 'two'}  # sound identical to a listener


def norm(s):
    s = s.lower().replace('-', ' ').replace('chat gpt', 'chatgpt')
    return [SAME.get(w, w) for w in (NUM.get(w, w) for w in re.sub(r"[^a-z0-9' ]", ' ', s).split())]


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return d[-1] / max(1, len(r))


def final(out):
    from faster_whisper import WhisperModel
    import soundfile as sf
    asr = WhisperModel('base.en', device='cpu', compute_type='int8')
    reels = sorted(glob.glob(os.path.join(out, '**', '*.mp4'), recursive=True))
    for f in reels:
        print(os.path.relpath(f, out))
        v, a, fmt = probe(f)
        fps = eval(v['r_frame_rate'])
        size = int(fmt['size']) / 1e6
        gate(v['width'] == W and v['height'] == H and v['codec_name'] == 'h264' and abs(fps - 30) < 0.01
             and v['pix_fmt'] == 'yuv420p', 'video spec', f"{v['width']}x{v['height']} {v['codec_name']} {fps:.0f}fps {v['pix_fmt']}")
        gate(a.get('codec_name') == 'aac' and a.get('sample_rate') == '48000', 'audio spec', f"{a.get('codec_name')} {a.get('sample_rate')} Hz")
        gate(size <= 100, 'file size <= 100 MB', f'{size:.1f} MB')
        lufs, peak = loudness(f)
        gate(-15 <= lufs <= -13, 'loudness -15..-13 LUFS', f'{lufs:.1f} LUFS')
        gate(peak <= -1.0, 'true peak <= -1 dBFS', f'{peak:.1f} dBFS')
        wav = f + '.16k.wav'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', f, '-ar', '16000', '-ac', '1', wav], check=True)
        heard = ' '.join(s.text for s in asr.transcribe(sf.read(wav, dtype='float32')[0])[0])
        os.remove(wav)
        said = open(f.replace('.mp4', '.script.txt')).read()
        e = wer(said, heard)
        gate(e <= 0.18, 'Whisper accuracy WER<=0.18', f'{e:.3f}' + ('' if e <= 0.18 else f'  heard: {heard.strip()}'))
        # Frames from the final encoded file, for a human look at the exact pixels people will see.
        dur = float(fmt['duration'])
        sheet = Image.new('RGB', (5 * 216, 384), 'white')
        for i in range(5):
            png = f'{f}.f{i}.png'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{dur * (i + 0.5) / 5:.2f}', '-i', f,
                            '-frames:v', '1', png], check=True)
            sheet.paste(Image.open(png).resize((216, 384)), (i * 216, 0))
            os.remove(png)
        sheet.save(f.replace('.mp4', '.frames.png'))
    # Anti-sameness: each main Reel must differ from the previous one on at least 4 of 6 axes.
    mains = sorted(glob.glob(os.path.join(out, 'day-*', '1-main-reel-*.axes.json')))
    for prev, cur in zip(mains, mains[1:]):
        a, b = json.load(open(prev)), json.load(open(cur))
        diff = [k for k in a if a[k] != b.get(k)]
        gate(len(diff) >= 4, f'variety {os.path.basename(os.path.dirname(cur))}', f'{len(diff)}/6 axes differ: {", ".join(diff) or "none"}')
    print(f'\n{len(reels)} reels checked, {len(failed)} gate failures')


if __name__ == '__main__':
    {'script': script, 'look': look, 'final': final}[sys.argv[1]](sys.argv[2])
    sys.exit(1 if failed else 0)
