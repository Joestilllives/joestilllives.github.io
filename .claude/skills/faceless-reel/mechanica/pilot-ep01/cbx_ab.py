import time, json, torch, torchaudio, os
from chatterbox.tts import ChatterboxTTS
t0 = time.time(); m = ChatterboxTTS.from_pretrained(device='cpu'); load = time.time() - t0
spec = json.load(open('spec.json')); os.makedirs('vo_chatterbox', exist_ok=True); res = {'load_s': round(load, 1), 'lines': {}}
for b in spec['beats']:
    if b['id'] not in ('hook', 'turn'): continue
    t = time.time(); wav = m.generate(b.get('tts', b['say']), exaggeration=0.45, cfg_weight=0.5); el = time.time() - t
    torchaudio.save(f"vo_chatterbox/{b['id']}.wav", wav, m.sr); dur = wav.shape[-1] / m.sr
    res['lines'][b['id']] = {'audio_s': round(dur, 2), 'gen_s': round(el, 1), 'x_realtime': round(el / dur, 1)}
    print(b['id'], res['lines'][b['id']], flush=True)
json.dump(res, open('vo_chatterbox/ab.json', 'w'), indent=1)
