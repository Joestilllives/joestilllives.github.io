# Voice: Pocket TTS (Kyutai)

Chosen by the owner over Kokoro and Chatterbox (Nov 23, 2026). Install in its own venv:
`pip install pocket-tts` (CPU; 1.75x faster than real time on this 4-core machine, about 15 s per 30 s script).

## Licences (checked Nov 23, 2026)
- Code: MIT. Weights (`kyutai/pocket-tts`): CC BY 4.0. Commercial use is allowed; credit "Voice: Kyutai Pocket TTS".
  The model's gate terms ban impersonation, cloning without consent and presenting audio as real recordings.
- Preset voices, from huggingface.co/kyutai/tts-voices:
  - CC0, commercial, no credit needed: marius, javert, bill_boerst, caro_davy, peter_yearsley, stuart_bell.
  - CC BY 4.0, commercial with credit: alba and the VCTK voices (anna, george, paul, ...).
  - NON-COMMERCIAL, never use: cosette (Expresso), jean (EARS).

## Audition of the pilot script (pocket_audition.py)
Every voice passed Whisper intelligibility (WER 0.043 to 0.065, base.en). Pace gate 2.2 to 3.8 words/s:
- pass: bill_boerst, caro_davy, peter_yearsley, george, paul, anna
- fail: marius (one beat 4.04), javert (1.81), stuart_bell (2.05), alba (3.82, borderline)
