"""Voice every pilot beat in each commercially usable Pocket TTS voice; write per-beat wavs and one audition file each."""
import json, os, sys, time, numpy as np, scipy.io.wavfile as wv
from pocket_tts import TTSModel
SP = sys.argv[1]; spec = json.load(open(f'{SP}/pilot/spec.json'))
VOICES = {'marius': 'CC0', 'javert': 'CC0', 'bill_boerst': 'CC0', 'caro_davy': 'CC0', 'peter_yearsley': 'CC0',
          'stuart_bell': 'CC0', 'alba': 'CC BY 4.0', 'george': 'CC BY 4.0', 'paul': 'CC BY 4.0', 'anna': 'CC BY 4.0'}
m = TTSModel.load_model(); sr = m.sample_rate; rep = {}
for v, lic in VOICES.items():
    st = m.get_state_for_audio_prompt(v); d = f'{SP}/vo_pocket/{v}'; os.makedirs(d, exist_ok=True); parts = []; t0 = time.time(); paces = []
    for b in spec['beats']:
        text = b.get('tts', b['say']); a = m.generate_audio(st, text).numpy().astype(np.float32)
        wv.write(f'{d}/{b["id"]}.wav', sr, a); parts += [a, np.zeros(int(sr * 0.35), np.float32)]
        paces.append(len(text.replace('-', ' ').split()) / (len(a) / sr))
    full = np.concatenate(parts); full = full / (np.abs(full).max() + 1e-9) * 0.89
    wv.write(f'{SP}/vo_pocket/audition_{v}.wav', sr, full)
    rep[v] = {'licence': lic, 'seconds': round(len(full) / sr, 1), 'gen_s': round(time.time() - t0, 1), 'pace_min': round(min(paces), 2), 'pace_max': round(max(paces), 2)}
    print(v, rep[v], flush=True)
json.dump(rep, open(f'{SP}/vo_pocket/report.json', 'w'), indent=1)
