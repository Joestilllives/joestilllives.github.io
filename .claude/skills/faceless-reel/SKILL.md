---
name: faceless-reel
description: >-
  Make finished, upload-ready faceless Instagram Reels and carousels from a posts JSON: copy-paste
  prompt cards typed out on screen, a Kokoro voiceover, Instagram-spec audio and video, and automated
  quality gates (hook length, safe zones, loudness, Whisper accuracy). Use when asked to make, render,
  batch or re-render Reels, carousels or a week of posts for a faceless or text-led account, or to
  check Reels before they go out.
---

# faceless-reel

Turns a JSON file of posts into a folder the account owner only has to upload. Each post gives one
main Reel, up to three short single-prompt Reels, a carousel, captions and grid covers. Nothing here
posts to Instagram.

## Setup (once per machine)

```bash
bash scripts/setup.sh          # pip packages + Kokoro voice model (~350 MB) into ~/.cache/faceless-reel
```

Needs ffmpeg, Node and Playwright with Chromium. Set `FACELESS_REEL_MODELS` to keep the model elsewhere.

## The pipeline (run in this order, never skip a gate)

```bash
D=posts.json; O=out; M=~/.cache/faceless-reel; S=scripts
python3 $S/qa.py script $D                                    # 1. words: hooks, asks, hashtags
node $S/render.js --data $D --out $O --mode look --handle @h  # 2. one still per beat
python3 $S/qa.py look $O                                      #    safe zones + grayscale sheet; LOOK at it
node $S/render.js --data $D --out $O --mode dump              # 3. list every spoken line
python3 $S/tts.py $O/speech.json voice-cache $M               #    voice them (cached, re-runs are cheap)
node $S/render.js --data $D --out $O --handle @h --badge badge.png   # 4. full render
python3 $S/qa.py final $O                                     # 5. spec, loudness, Whisper accuracy
```

Then open each `*.frames.png` (five frames pulled from the final encoded MP4) and look at them.
A Reel is done only when every gate prints PASS **and** you have looked at both sheets. Fix the cause
of a FAIL in the JSON or the template, never by loosening a threshold.

`--only 3` renders one day. Steps 2 and 4 take about a minute per day on CPU.

## The posts JSON

See `examples/day1.json`. Per post:

| field | what it is |
| --- | --- |
| `day`, `series`, `of` | "Get an Hour Back · Day 1/30" label |
| `say` | spoken hook, 5 to 18 words, payload first |
| `hook` | on-screen hook, 6 words or fewer, read before it is heard |
| `sub` | one line under the hook |
| `cards[]` | `{title, prompt, say?}`; `say` overrides the spoken line for that card |
| `save`, `send` | finishes "Save this for ___" and "send it to ___" |
| `caption` | main Reel and carousel caption |
| `singles[]` | `{card, say, hook, caption}`: short Reels built from one card |

Write hooks with `/ig-reel` (its `hookscore.py` and 26 formulas) and captions through `/ig-human` when
those skills are available. Hooks that score under 50 are not hooks yet.

## Rules this skill enforces, and why

Adapted from a faceless-Reel production playbook; only the parts that apply to text-led prompt Reels.

- **Safe zones.** Nothing below y=1440 or right of x=850 on a 1080×1920 frame: Instagram's caption,
  audio strip and action rail sit there. First headline below y=300 so the 4:5 profile-grid crop
  (y=285 to 1635) never slices it. `qa.py look` checks the pixels, not the template.
- **Mute-proof.** Every spoken line is also on screen; most people watch muted first.
- **Reading time.** A fully typed prompt stays up for letters/15 + 1.5 s before the cut.
- **An explicit save or send ask** on every Reel and caption ("send it to a coworker who needs it").
  Sends to friends are one of the strongest reach signals for non-followers.
- **Voice:** Kokoro `am_fenrir` at speed 1.12, with 250 ms of lead-in silence. Without the lead-in the
  first consonant is clipped and "Prompt" is heard as "From".
- **Accuracy:** Whisper re-transcribes every finished Reel; word error rate must be 0.18 or less across
  the Reel. It is measured per Reel because a short line with one misheard word scores 33%.
  Same-sounding words (role/roll, four/for) are not counted as errors.
- **Master:** H.264, 1080×1920, 30 fps, yuv420p, AAC 48 kHz 192 kbps, -14 LUFS (gate -15 to -13),
  true peak at or under -1 dBFS, faststart. Static text Reels encode at well under 2 MB; that is fine.
- **Never invent numbers.** No made-up statistics, results or time savings stated as fact. Use "if"
  framing ("If your inbox eats your first hour...") or a number the user gave you.
- **Nothing gets posted.** The owner uploads the files.

## Not adopted (and why), so nobody re-adds them by reflex

- 3D, physics and map engines (Three.js, Matter.js, D3): built for finance explainers; a prompt
  Reel's payoff is the text itself.
- Music bed and vocal-pocket EQ: cannot be judged without listening, and a bad bed hurts more than
  silence. Revisit only with a human ear in the loop.
- Phoneme-level forced alignment and word-by-word captions: on-screen text here is the card, not a
  transcript.
- Source-citation gates: only needed when a Reel states figures. If one does, cite the source in the
  caption and in the JSON.

## After posting: the feedback loop

Every 10 Reels, record per Reel: 3-second hold rate, average watch time, sends, saves and follows
(Instagram Insights). Rewrite the next batch's hooks toward the top third, and vary at least two of
these against the previous week: opening hook formula, card count, ending ask, topic area.
