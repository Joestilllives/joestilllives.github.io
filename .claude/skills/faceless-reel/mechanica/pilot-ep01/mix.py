# Voice chain (pedalboard), placement on the timeline, bed >= 20 dB under voice, silence drop, -14 LUFS master.
import json, sys, numpy as np, soundfile as sf, pyloudnorm as pyln
from pedalboard import Pedalboard, HighpassFilter, Compressor, PeakFilter, LowShelfFilter, Limiter, Gain
vo = sys.argv[1] if len(sys.argv) > 1 else 'vo_kokoro'
T = json.load(open('timeline.json')); SR = 48000; N = int((T['total'] + 0.2) * SR)
meter = pyln.Meter(SR)
chain = Pedalboard([HighpassFilter(80), LowShelfFilter(cutoff_frequency_hz=200, gain_db=-1.5), PeakFilter(3000, 2.0, 0.9),
                    Compressor(threshold_db=-20, ratio=3, attack_ms=5, release_ms=80), Limiter(threshold_db=-3), Gain(-3)])  # JUCE limiter adds make-up gain = -threshold; undo it
voice = np.zeros(N)
for b in T['beats']:
    a, sr = sf.read(f"{vo}/{b['id']}.wav", dtype='float32'); assert sr == SR
    a = chain(a.reshape(1, -1), SR)[0]; i = int((b['start'] + b['pre']) * SR); voice[i:i + len(a)] += a[:N - i]
def load(f):
    x, sr = sf.read(f, dtype='float32'); x = x.mean(axis=1) if x.ndim > 1 else x; x = np.pad(x, (0, max(0, N - len(x))))[:N]; return x
bed, sfx = load('bed.wav'), load('sfx.wav')
Lv = meter.integrated_loudness(voice)
gap = 22.0                                                     # WCAG 1.4.7 asks for >= 20 dB; aim 22 for margin
bed *= 10 ** ((Lv - gap - meter.integrated_loudness(bed)) / 20)
sfx *= 10 ** ((Lv - 12 - meter.integrated_loudness(sfx)) / 20)
# Silence drop: bed and effects fade out over 30 ms into the gap before the twist and come back on the line.
tw = next(b for b in T['beats'] if b['id'] == 'turn'); a, z = int(tw['start'] * SR), int(T['at']['line'] * SR)
env = np.ones(N); f = int(0.03 * SR); env[a:a + f] = np.linspace(1, 0, f); env[a + f:z] = 0
bed *= env; sfx[a + f:int((tw['start'] + tw['pre']) * SR)] = 0
mix = voice + bed + sfx
mix = mix * 10 ** ((-18.0 - meter.integrated_loudness(mix)) / 20)   # leave headroom; ffmpeg two-pass loudnorm masters the stereo file
sf.write('premaster.wav', np.stack([mix, mix], 1), SR, subtype='PCM_24')
import subprocess, re as _re
err = subprocess.run(['ffmpeg', '-nostats', '-i', 'premaster.wav', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
m = json.loads(err[err.rindex('{'):err.rindex('}') + 1])
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', 'premaster.wav', '-af', f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true", '-ar', '48000', '-c:a', 'pcm_s24le', 'mix.wav'], check=True); sf.write('stem_voice.wav', voice, SR); sf.write('stem_bed.wav', bed, SR)
drop = mix[a + f:int((tw['start'] + tw['pre']) * SR)]
rms = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)
report = {'voice_lufs': Lv, 'bed_lufs': meter.integrated_loudness(bed), 'bed_under_voice_db': Lv - meter.integrated_loudness(bed),
          'mix_lufs': meter.integrated_loudness(mix), 'silence_drop_s': len(drop) / SR, 'silence_drop_dbfs': rms(drop), 'speech_dbfs': rms(voice[voice != 0])}
report = {k: round(float(v), 2) for k, v in report.items()}; json.dump(report, open('mix_report.json', 'w'), indent=1); print(json.dumps(report, indent=1))
