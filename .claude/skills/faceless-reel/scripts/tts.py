"""Voice every spoken line with Kokoro (voice am_fenrir; speed 1.12, or 0.95 for lines under 10 spoken words) into a cache.

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
made, pace = 0, []


def spoken_words(text):
    """Words as said aloud: '600-word' is three words, '150' is three."""
    n = 0
    for tok in text.replace('-', ' ').split():
        digits = ''.join(c for c in tok if c.isdigit())
        if not digits:
            n += 1
            continue
        v = int(digits)
        hundreds, rest = divmod(v % 1000, 100)
        n += (2 if hundreds else 0) + (0 if rest == 0 else 1 if rest <= 20 or rest % 10 == 0 else 2) + (2 if v >= 1000 else 0)
        n = max(n, 1)
    return n


def speed(text):
    # Lines under 10 words spoken at 1.12 land above 3.8 words per second; give them normal speed.
    return 0.95 if spoken_words(text) < 10 else 1.12


for text in dict.fromkeys(lines):
    out = os.path.join(cache, hashlib.sha1(text.encode()).hexdigest() + '.wav')
    if os.path.exists(out):
        sec = sf.info(out).duration - 0.25  # minus the lead-in silence
        if spoken_words(text) >= 5:
            pace.append((spoken_words(text) / sec, text))
        continue
    audio, sr = k.create(text, voice='am_fenrir', speed=speed(text), lang='en-us')
    raw = out + '.raw.wav'
    sf.write(raw, audio, sr)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af', 'adelay=250',
                    '-ar', '48000', '-ac', '1', out], check=True)
    n = spoken_words(text)
    if n >= 5:  # narration pace on real sentences: 2.2-3.8 words per second
        pace.append((n / (len(audio) / sr), text))
    os.remove(raw)
    made += 1
print(f'voiced {made} new lines, {len(set(lines)) - made} already cached')
bad = [(w, t) for w, t in pace if not 2.2 <= w <= 3.8]
if pace:
    print(f"  {'PASS' if not bad else 'FAIL'}  narration pace 2.2-3.8 wps  "
          f"{min(w for w, _ in pace):.2f}-{max(w for w, _ in pace):.2f} across {len(pace)} lines")
for w, t in bad:
    print(f'        {w:.2f} wps: {t}')
sys.exit(1 if bad else 0)
