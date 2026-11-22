"""Encode the final MP4 and run every gate. Exit 1 if any gate fails.
    python3 gates.py            (expects master_video.mkv, mix.wav, timeline.json, render_stats.json, mix_report.json, look/*.png)"""
import json, os, re, subprocess, sys, time
import numpy as np, soundfile as sf
sys.path.insert(0, '/home/user/joestilllives.github.io/.claude/skills/faceless-reel/scripts')
from qa import wer
from PIL import Image
failed, rows = [], []
def gate(ok, name, detail):
    rows.append(('PASS' if ok else 'FAIL', name, detail)); print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} {detail}")
    if not ok: failed.append(name)
run = lambda *a: subprocess.run(a, capture_output=True, text=True)

# ---------- encode ----------
t0 = time.time()
enc = run('ffmpeg', '-y', '-v', 'error', '-i', 'master_video.mkv', '-i', 'mix.wav',
          '-vf', 'scale=out_color_matrix=bt709:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high',
          '-b:v', '8M', '-maxrate', '10M', '-bufsize', '16M', '-g', '15', '-keyint_min', '15', '-sc_threshold', '0', '-flags', '+cgop',
          '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
          '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', '-shortest', 'final.mp4')
if enc.returncode: sys.exit(enc.stderr)
enc_s = time.time() - t0

# ---------- sources ----------
print('content'); r = run('python3', 'gate_sources.py', 'spec.json'); gate(r.returncode == 0, 'sources and quotes verified', r.stdout.strip().splitlines()[-1].strip())
# ---------- captions (Netflix rules) ----------
T = json.load(open('timeline.json')); worst_cps = max(len(c['text']) / (c['e'] - c['a']) for c in T['caps'])
longest = max(len(l) for c in T['caps'] for l in c['lines']); nlines = max(len(c['lines']) for c in T['caps'])
gate(worst_cps <= 20, 'captions <= 20 characters/second', f'worst {worst_cps:.1f}')
gate(longest <= 42 and nlines <= 2, 'captions <= 42 chars, <= 2 lines', f'longest line {longest}, max {nlines} lines')
# ---------- text coverage ----------
st = json.load(open('render_stats.json')); gate(st['max_text_coverage'] < 0.5, 'text covers < 50% of frame', f"max {st['max_text_coverage'] * 100:.1f}%")
# ---------- voice pace ----------
spec = json.load(open('spec.json')); paces = []
for b in spec['beats']:
    d = sf.info(f"vo_kokoro/{b['id']}.wav").duration - 0.25; paces.append(len(b.get('tts', b['say']).replace('-', ' ').split()) / d)
gate(all(2.2 <= p <= 3.8 for p in paces), 'narration pace 2.2-3.8 words/s', f'{min(paces):.2f}-{max(paces):.2f}')
# ---------- mix ----------
mr = json.load(open('mix_report.json'))
gate(mr['bed_under_voice_db'] >= 20, 'music >= 20 dB under voice (WCAG)', f"{mr['bed_under_voice_db']:.1f} dB")
gate(mr['silence_drop_s'] >= 0.45 and mr['silence_drop_dbfs'] <= -60, 'silence drop before the twist', f"{mr['silence_drop_s']:.2f} s at {mr['silence_drop_dbfs']:.0f} dBFS")

print('file')
j = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', 'final.mp4').stdout)
v = next(s for s in j['streams'] if s['codec_type'] == 'video'); a = next(s for s in j['streams'] if s['codec_type'] == 'audio')
fps = eval(v['r_frame_rate']); mb = int(j['format']['size']) / 1e6; dur = float(j['format']['duration']); vbr = int(v.get('bit_rate', 0)) / 1e6
gate(v['width'] == 1080 and v['height'] == 1920 and v['codec_name'] == 'h264' and abs(fps - 30) < .01 and v['pix_fmt'] == 'yuv420p',
     'video 1080x1920 H.264 30fps 4:2:0', f"{v['width']}x{v['height']} {v['codec_name']} {fps:.0f}fps {v['pix_fmt']} {v.get('color_space','?')}")
gate(a['codec_name'] == 'aac' and a['sample_rate'] == '48000', 'audio AAC-LC 48 kHz', f"{a['codec_name']} {a.get('profile','')} {a['sample_rate']} Hz")
with open('final.mp4', 'rb') as f: head = f.read(4096)
gate(head.find(b'moov') != -1 and (head.find(b'mdat') == -1 or head.find(b'moov') < head.find(b'mdat')), 'faststart (moov first)', 'moov before mdat')
kf = [float(x.strip(',')) for x in run('ffprobe', '-v', 'error', '-select_streams', 'v', '-skip_frame', 'nokey', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0', 'final.mp4').stdout.split() if x.strip(',')]
gi = max(np.diff(kf)) if len(kf) > 1 else 99
gate(gi <= 0.51, 'keyframe every <= 0.5 s (closed GOP)', f'max interval {gi:.2f} s')
gate(mb <= 100, 'file size <= 100 MB', f'{mb:.1f} MB, video {vbr:.1f} Mbps')
err = run('ffmpeg', '-nostats', '-i', 'final.mp4', '-af', 'ebur128=peak=true', '-f', 'null', '-').stderr
lufs = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1]); tp = float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', err)[-1])
gate(-15 <= lufs <= -13, 'loudness -15..-13 LUFS', f'{lufs:.1f} LUFS'); gate(tp <= -1.0, 'true peak <= -1 dBFS', f'{tp:.1f} dBFS')

print('accuracy')
from faster_whisper import WhisperModel
run('ffmpeg', '-y', '-v', 'error', '-i', 'final.mp4', '-ar', '16000', '-ac', '1', '_final16k.wav')
heard = ' '.join(s.text for s in WhisperModel('base.en', device='cpu', compute_type='int8').transcribe(sf.read('_final16k.wav', dtype='float32')[0])[0])
said = ' '.join(b['say'] for b in spec['beats']); e = wer(said.replace('1865', 'eighteen sixty-five'), heard.replace('1865', 'eighteen sixty-five'))
gate(e <= 0.18, 'Whisper accuracy on final mix', f'WER {e:.3f}' + ('' if e <= .05 else f' | heard: {heard.strip()}'))

print('picture')
ss = run('ffmpeg', '-i', 'final.mp4', '-i', 'master_video.mkv', '-lavfi', '[0:v]format=yuv444p[a];[1:v]format=yuv444p[b];[a][b]ssim', '-f', 'null', '-').stderr
ssim = float(re.findall(r'All:([\d.]+)', ss)[-1]); gate(ssim >= 0.97, 'SSIM final vs lossless master', f'{ssim:.4f}')
# stillness and rate of revelation: frame-to-frame change, ignoring the progress bar row
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'master_video.mkv', '-vf', 'fps=30,crop=1080:1500:0:380,scale=270:375,format=gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 375, 270).astype(np.int16)
diff = np.array([np.mean(np.abs(fr[i] - fr[i - 1]) > 8) for i in range(1, len(fr))])   # share of pixels that changed visibly
moving = diff > 0.0005; still, worst = 0, 0
for m in moving: still = 0 if m else still + 1; worst = max(worst, still)
gate(worst / 30 <= 3.0, 'no still stretch over 3 s', f'longest {worst / 30:.2f} s')
# A visual event = more than 1% of the picture changes within 0.2 s (6 frames). Comparing frames 0.2 s apart counts
# fades and reveals that are spread over several frames; frame-to-frame alone misses them (per-frame gap reported too).
d6 = np.array([np.mean(np.abs(fr[i] - fr[i - 6]) > 8) for i in range(6, len(fr))])
def longest_gap(ev, n): return np.diff(np.concatenate([[0], ev, [n / 30]])).max()
g6, g1 = longest_gap(np.where(d6 > 0.01)[0] / 30 + 0.2, len(fr)), longest_gap(np.where(diff > 0.01)[0] / 30, len(fr))
gate(g6 <= 3.5, 'something new every <= 3.5 s', f'longest gap {g6:.2f} s (frame-to-frame metric: {g1:.2f} s)')
# safe zones on the look stills
bad = 0
for f in sorted(os.listdir('look')):
    if not f.endswith('.png') or f == 'sheet.png': continue
    im = Image.open(f'look/{f}').convert('RGB'); px = im.load(); bg = px[4, 4]
    ink = lambda x0, y0, x1, y1: sum(1 for y in range(y0, y1, 4) for x in range(x0, x1, 4) if sum(abs(p - q) for p, q in zip(px[x, y], bg)) > 60)
    bad += ink(0, 1440, 1080, 1920) + ink(850, 0, 1080, 1440)
gate(bad == 0, 'nothing under Instagram UI (safe zones)', f'{bad} ink samples in the red zones')

# contact sheet from the FINAL encoded file
sheet = Image.new('RGB', (8 * 216, 384), 'white')
for i in range(8):
    run('ffmpeg', '-y', '-v', 'error', '-ss', f'{dur * (i + .5) / 8:.2f}', '-i', 'final.mp4', '-frames:v', '1', f'_f{i}.png')
    sheet.paste(Image.open(f'_f{i}.png').resize((216, 384)), (i * 216, 0)); os.remove(f'_f{i}.png')
sheet.save('final.frames.png')
json.dump({'rows': rows, 'encode_s': round(enc_s, 1), 'duration_s': round(dur, 2), 'size_mb': round(mb, 2)}, open('gates_report.json', 'w'), indent=1)
print(f'\n{len(rows)} gates, {len(failed)} failed. encode {enc_s:.0f}s, {dur:.1f}s video, {mb:.1f} MB')
sys.exit(1 if failed else 0)
