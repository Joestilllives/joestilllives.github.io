# Pilot report: Mechanica episode 1, "How a key actually opens a lock"

Length 32.1 s, 11.27 MB, 1080x1920, 30 fps.

## Quality gates (all checked on the final file)

| Result | Gate | Measured |
|---|---|---|
| PASS | sources and quotes verified | PASS  sources gate: 4 claims, 0 problems |
| PASS | captions <= 20 characters/second | worst 19.5 |
| PASS | captions <= 42 chars, <= 2 lines | longest line 42, max 2 lines |
| PASS | text covers < 50% of frame | max 14.4% |
| PASS | narration pace 2.2-3.8 words/s | 2.72-3.75 |
| PASS | music >= 20 dB under voice (WCAG) | 22.0 dB |
| PASS | silence drop before the twist | 0.52 s at -240 dBFS |
| PASS | video 1080x1920 H.264 30fps 4:2:0 | 1080x1920 h264 30fps yuv420p bt709 |
| PASS | audio AAC-LC 48 kHz | aac LC 48000 Hz |
| PASS | faststart (moov first) | moov before mdat |
| PASS | keyframe every <= 0.5 s (closed GOP) | max interval 0.50 s |
| PASS | file size <= 100 MB | 11.3 MB, video 2.6 Mbps |
| PASS | loudness -15..-13 LUFS | -14.1 LUFS |
| PASS | true peak <= -1 dBFS | -1.0 dBFS |
| PASS | Whisper accuracy on final mix | WER 0.011 |
| PASS | SSIM final vs lossless master | 0.9975 |
| PASS | no still stretch over 3 s | longest 2.47 s |
| PASS | something new every <= 3.5 s | longest gap 3.17 s (frame-to-frame metric: 3.53 s) |
| PASS | nothing under Instagram UI (safe zones) | 0 ink samples in the red zones |

## Machine time per video (4-core CPU, no GPU)

| Step | Time |
|---|---|
| Kokoro voice, 7 lines | about 15 s |
| Blender hero shot, 60 frames at 760x760 | 268 s (4.5 s per frame) |
| 2D composition, 963 frames | 65 s (0.07 s per frame) |
| Music and effects (Tone.js offline) | about 10 s |
| Encode | 28 s |
| All gates incl. speech check | about 1.5 min |
| **Total** | **about 7 to 8 min, of which the Blender shot is about 4.5 min** |

## Voice A/B (listen to both in voice-ab/)

- Kokoro: zero word errors on both lines, 2.9 to 3.3 words/s, about 1 s to generate.
- Chatterbox: zero word errors on both lines, 3.5 to 3.8 words/s, 8.8x and 4.1x real time on this CPU (about 2 to 4 min per video). Weights MIT (checked on its model page). Adds an inaudible AI watermark (Resemble Perth).
- The pilot uses Kokoro. Pick by ear.

## Before posting

1. Turn on the AI label (realistic AI voice; Meta requires it).
2. Paste caption.txt. Its last lines name the sources; source-sheet.md is the full statement-by-statement sheet (hosting still to decide).
3. Use cover-4x5.png as the grid cover.
