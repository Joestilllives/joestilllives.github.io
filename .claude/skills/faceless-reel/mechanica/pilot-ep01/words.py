# Word timestamps for every voiced line (faster-whisper), mapped onto the script's own words.
import json, sys, soundfile as sf, difflib, re, subprocess
from faster_whisper import WhisperModel
spec = json.load(open('spec.json')); vo = sys.argv[1]
m = WhisperModel('base.en', device='cpu', compute_type='int8'); out = {}
norm = lambda w: re.sub(r"[^a-z0-9']", '', w.lower())
for b in spec['beats']:
    wav = f"{vo}/{b['id']}.wav"; dur = sf.info(wav).duration
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', wav, '-ar', '16000', '-ac', '1', '/tmp/claude-0/-home-user-joestilllives-github-io/c8b4840a-941c-578d-bf3e-22bc86ddeadc/scratchpad/pilot/_16k.wav'], check=True)
    segs, _ = m.transcribe(sf.read('/tmp/claude-0/-home-user-joestilllives-github-io/c8b4840a-941c-578d-bf3e-22bc86ddeadc/scratchpad/pilot/_16k.wav', dtype='float32')[0], word_timestamps=True)
    heard = [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]
    script = b['say'].split()
    # align script words to heard words; script words keep their own spelling
    sm = difflib.SequenceMatcher(None, [norm(w) for w in script], [norm(h[0]) for h in heard])
    times = [None] * len(script)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('equal', 'replace'):
            for k in range(i2 - i1):
                j = j1 + min(k, j2 - j1 - 1)
                if j1 < j2: times[i1 + k] = (heard[j][1], heard[j][2])
    for i, t in enumerate(times):  # fill gaps by interpolation
        if t is None:
            prev = next((times[k] for k in range(i - 1, -1, -1) if times[k]), (0.25, 0.25))
            times[i] = (prev[1], prev[1] + 0.2)
    out[b['id']] = {'dur': dur, 'words': [[w, round(a, 3), round(e, 3)] for w, (a, e) in zip(script, times)]}
    print(b['id'], f'{dur:.2f}s', ' '.join(f'{w}@{a:.2f}' for w, (a, e) in list(zip(script, times))[:6]), '...')
json.dump(out, open(f'{vo}/words.json', 'w'), indent=1)
