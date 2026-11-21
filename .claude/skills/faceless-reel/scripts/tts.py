"""Voice every spoken line with Kokoro (voice am_fenrir, speed 1.12) into a cache.

    python3 tts.py OUT/speech.json VOICE_CACHE MODEL_DIR

speech.json is written by `render.js --mode dump`. Each line becomes VOICE_CACHE/<sha1>.wav,
48 kHz mono with 250 ms of lead-in silence (without it the first consonant gets clipped,
and both phones and Whisper lose the first word). Lines already cached are skipped.
Accuracy is checked per Reel afterwards by qa.py, not here: one misheard word in a
three-word line is a 33% error rate, which says nothing about the Reel.
"""
import hashlib
import json
import os
import subprocess
import sys

import soundfile as sf
from kokoro_onnx import Kokoro

lines, cache, models = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
os.makedirs(cache, exist_ok=True)
k = Kokoro(os.path.join(models, 'kokoro.onnx'), os.path.join(models, 'voices.bin'))
made = 0
for text in dict.fromkeys(lines):
    out = os.path.join(cache, hashlib.sha1(text.encode()).hexdigest() + '.wav')
    if os.path.exists(out):
        continue
    audio, sr = k.create(text, voice='am_fenrir', speed=1.12, lang='en-us')
    raw = out + '.raw.wav'
    sf.write(raw, audio, sr)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af', 'adelay=250',
                    '-ar', '48000', '-ac', '1', out], check=True)
    os.remove(raw)
    made += 1
print(f'voiced {made} new lines, {len(set(lines)) - made} already cached')
