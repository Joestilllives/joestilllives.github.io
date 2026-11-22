# Voice each beat with Kokoro am_fenrir at one speed, 250 ms lead-in, report words per second.
import json, sys, os, subprocess, soundfile as sf
from kokoro_onnx import Kokoro
spec = json.load(open('spec.json')); speed = float(sys.argv[1]); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
M = os.path.expanduser('~/.cache/faceless-reel'); k = Kokoro(f'{M}/kokoro.onnx', f'{M}/voices.bin')
for b in spec['beats']:
    a, sr = k.create(b.get('tts', b['say']), voice='am_fenrir', speed=b.get('speed', speed), lang='en-us')
    raw = f'{out}/{b["id"]}.raw.wav'; sf.write(raw, a, sr)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af', 'adelay=250', '-ar', '48000', '-ac', '1', f'{out}/{b["id"]}.wav'], check=True); os.remove(raw)
    n = len(b.get('tts', b['say']).replace('-', ' ').split()); print(f"{b['id']:8} {n:2} words {len(a)/sr:5.2f}s {n/(len(a)/sr):.2f} wps")
