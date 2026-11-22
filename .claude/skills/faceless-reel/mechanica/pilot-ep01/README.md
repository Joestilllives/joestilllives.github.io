# Mechanica pilot, episode 1: "How a key actually opens a lock"

The first studio-grade Mechanica video, built end to end and timed. Run from this folder, in order:

```bash
python3 gate_sources.py spec.json        # every claim has a source and a quote found in the saved source text
python3 voice.py 1.0 vo_kokoro           # Kokoro am_fenrir; per-line speed and spoken-form text live in spec.json
python3 words.py vo_kokoro               # word timings (faster-whisper) for labels and captions
~/.cache/faceless-reel/blender-venv/bin/python hero.py hero_full 60 24   # Blender cutaway hero shot, transparent PNGs
node comp.js --mode look                 # stills at key moments + text coverage; LOOK at them
npm i tone@15.1.22 && node music.js      # original music bed + sound effects (Tone.js, offline)
python3 mix.py vo_kokoro                 # voice chain, bed 22 dB under voice, silence drop, -14 LUFS master
node comp.js --mode render               # lossless master, 30 fps, deterministic
python3 gates.py                         # encode + 19 gates; look at final.frames.png before calling it done
node cover.js                            # 4:5 grid cover
```

Needs pedalboard and pyloudnorm (pip), plus the skill's setup. `cbx_ab.py` is the Chatterbox voice A/B (own venv with CPU torch).
This is pilot code: paths and the lock drawing are specific to this episode. The next step is to generalize it into the skill.
