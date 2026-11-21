// Faceless prompt-Reel renderer: voiced Reels with prompts typed on screen, plus a carousel per post.
//
//   node render.js --data posts.json --out OUT [--handle @name] [--badge badge.png]
//                  [--voice-cache DIR] [--mode dump|look|render] [--only DAY]
//
// --mode dump    write OUT/speech.json (every spoken line) and stop; voice it with tts.py
// --mode look    write one still per beat to OUT/look/ for the pre-render visual check (qa.py look)
// --mode render  (default) build MP4s, carousels, covers, captions and a script.txt per Reel
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const DATA = path.resolve(arg('data'));
const OUT = path.resolve(arg('out'));
const HANDLE = arg('handle', '@handle');
const MODE = arg('mode', 'render');
const ONLY = arg('only');
const CACHE = path.resolve(arg('voice-cache', path.join(OUT, '..', 'voice-cache')));
const badgeFile = arg('badge');
const BADGE = badgeFile && fs.existsSync(badgeFile)
  ? `<img src="data:image/png;base64,${fs.readFileSync(badgeFile).toString('base64')}">` : '';
const posts = JSON.parse(fs.readFileSync(DATA, 'utf8')).filter(p => !ONLY || String(p.day) === ONLY);

const WPS = 9;                                   // prompt words revealed per second
const hold = s => s.replace(/\s/g, '').length / 15 + 1.5; // reading time once fully shown (letters/15 + 1.5 s)

// Brand atoms stay fixed; see SKILL.md for the safe zones these paddings enforce.
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const css = h => {
  const v = h > 1500;
  return `*{margin:0;box-sizing:border-box}
html,body{width:1080px;height:${h}px;background:#0E1B3D;color:#F5F7FF;font-family:'Inter',sans-serif;overflow:hidden}
.wrap{position:absolute;inset:0;padding:${v ? '300px 230px 480px 88px' : '96px 88px'};display:flex;flex-direction:column}
.label{font:700 26px 'Inter';letter-spacing:4px;color:#FFC24B;text-transform:uppercase}
.main{flex:1;display:flex;flex-direction:column;justify-content:center;gap:${v ? 32 : 44}px}
.hook{font:800 ${v ? 96 : 112}px/1.02 'Inter Display','Inter';letter-spacing:-2px}
.sub{font:500 44px/1.3 'Inter';color:#B9C3E6}
.num{font:800 ${v ? 96 : 120}px/1 'Inter Display','Inter';color:#FFC24B;font-variant-numeric:tabular-nums}
.title{font:700 ${v ? 58 : 66}px/1.1 'Inter Display','Inter';letter-spacing:-1px}
.box{background:#1A2B57;border:2px solid #2E4682;border-radius:28px;padding:44px 48px}
.copy{font:700 22px 'Inter';letter-spacing:3px;color:#FFC24B;margin-bottom:20px}
.prompt{font:500 ${v ? 33 : 38}px/1.45 'JetBrains Mono',monospace;white-space:pre-wrap}
.h{visibility:hidden}.cur{color:#FFC24B}
.cta1{font:800 ${v ? 76 : 84}px/1.08 'Inter Display','Inter';letter-spacing:-1.5px}
.cta2{font:500 44px/1.35 'Inter';color:#B9C3E6}
.hl{color:#FFC24B}
.foot{display:flex;justify-content:space-between;align-items:center;font:600 30px 'Inter';color:#B9C3E6}
.who{display:flex;align-items:center;gap:20px}.who img{width:84px;height:84px}
.arrow{color:#FFC24B;font-weight:800}`;
};
const page = (h, label, inner, arrow) => `<!doctype html><html><head><meta charset="utf-8"><style>${css(h)}</style></head>
<body><div class="wrap"><div class="label">${label}</div><div class="main">${inner}</div>
<div class="foot"><span class="who">${BADGE}${HANDLE}</span><span class="arrow">${arrow ? 'Swipe &rarr;' : ''}</span></div></div></body></html>`;
const words = s => s.split(/\s+/).filter(Boolean).length;
const hookHtml = (hook, sub) => `<div class="hook">${esc(hook)}</div>${sub ? `<div class="sub">${sub}</div>` : ''}`;
// k = prompt words shown; the rest keep their space but are hidden, so nothing reflows while typing.
function cardHtml(num, title, prompt, k) {
  let seen = 0, out = '';
  for (const t of prompt.split(/(\s+)/)) {
    if (/^\s+$/.test(t)) { out += seen <= k ? t : `<span class="h">${t}</span>`; continue; }
    seen++;
    out += seen <= k ? esc(t) : `<span class="h">${esc(t)}</span>`;
    if (seen === k && k < words(prompt)) out += '<span class="cur">&#9612;</span>';
  }
  return `${num ? `<div class="num">${num}</div>` : ''}<div class="title">${esc(title)}</div>
    <div class="box"><div class="copy">COPY THIS</div><div class="prompt">${out}</div></div>`;
}
const ctaHtml = (a, b) => `<div class="cta1">${a}</div><div class="cta2">${b}</div>`;
const typed = (num, title, prompt, label) => {
  const frames = [];
  for (let k = 0; k <= words(prompt); k++) frames.push({ html: page(1920, label, cardHtml(num, title, prompt, k)), dur: 1 / WPS });
  frames.at(-1).dur = hold(prompt);
  return { frames, minDur: words(prompt) / WPS + hold(prompt) };
};
const spoken = t => t.replace(/\b\d\.\s/g, '').replace(/\[|\]/g, '');
const ord = ['one', 'two', 'three', 'four', 'five', 'six'];

function voice(text, wav) {
  const src = path.join(CACHE, crypto.createHash('sha1').update(text).digest('hex') + '.wav');
  if (!fs.existsSync(src)) throw new Error(`no voice for "${text}": run --mode dump, then tts.py`);
  fs.copyFileSync(src, wav);
  return parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav]).toString());
}

// Each reel = list of beats {frames:[{html,dur}], speech, minDur}. Returns nothing in dump/look modes.
const SPEECH = [];
async function buildReel(pg, beats, file) {
  if (MODE === 'dump') { beats.forEach(b => SPEECH.push(b.speech)); return; }
  const base = path.join(OUT, file);
  if (MODE === 'look') {
    fs.mkdirSync(path.join(OUT, 'look'), { recursive: true });
    for (const [i, b] of beats.entries()) {
      await pg.setContent(b.frames.at(-1).html, { waitUntil: 'load' });
      await pg.screenshot({ path: path.join(OUT, 'look', `${file.replace(/\//g, '_')}_${i}.png`) });
    }
    return;
  }
  const tmp = base + '.tmp';
  fs.mkdirSync(tmp, { recursive: true });
  const clips = [];
  for (const [bi, b] of beats.entries()) {
    const wav = path.join(tmp, `b${bi}.wav`);
    const alen = voice(b.speech, wav);
    const shots = [];
    for (const [fi, f] of b.frames.entries()) {
      const png = path.join(tmp, `b${bi}f${fi}.png`);
      await pg.setContent(f.html, { waitUntil: 'load' });
      await pg.screenshot({ path: png });
      shots.push({ png, dur: f.dur });
    }
    const fixed = shots.slice(0, -1).reduce((a, s) => a + s.dur, 0);
    const total = Math.max(alen + 0.4, b.minDur || 0, fixed + 0.8);
    shots.at(-1).dur = total - fixed;
    const list = path.join(tmp, `b${bi}.txt`);
    fs.writeFileSync(list, shots.map(s => `file '${s.png}'\nduration ${s.dur.toFixed(3)}`).join('\n') + `\nfile '${shots.at(-1).png}'\n`);
    const clip = path.join(tmp, `b${bi}.mov`);
    execFileSync('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', list, '-i', wav, '-af', 'apad', '-t', total.toFixed(3),
      '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '18', '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', clip], { stdio: 'ignore' });
    clips.push(clip);
  }
  const cl = path.join(tmp, 'clips.txt');
  fs.writeFileSync(cl, clips.map(c => `file '${c}'`).join('\n'));
  // Instagram master: H.264 30 fps yuv420p, AAC 48 kHz 192 kbps, -14 LUFS, true peak under -1 dBFS, faststart.
  execFileSync('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', cl, '-c:v', 'copy',
    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
    '-movflags', '+faststart', base + '.mp4'], { stdio: 'ignore' });
  // Grid cover: the hook frame, cropped to the 4:5 profile-grid window.
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', path.join(tmp, 'b0f0.png'), '-vf', 'crop=1080:1350:0:285', base + '.cover.png']);
  fs.writeFileSync(base + '.script.txt', beats.map(b => b.speech).join(' ') + '\n');
  fs.rmSync(tmp, { recursive: true, force: true });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const vert = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  const sq = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  for (const p of posts) {
    const day = `day-${String(p.day).padStart(2, '0')}`;
    fs.mkdirSync(path.join(OUT, day, 'carousel'), { recursive: true });
    const label = `${esc(p.series || 'Get an Hour Back')} &middot; Day ${p.day}/${p.of || 30}`;
    const send = p.send || 'a coworker who needs it';

    if (MODE === 'render') {
      const cs = [page(1350, label, hookHtml(p.hook, esc(p.sub) + ' &rarr;'), true),
        ...p.cards.map((c, i) => page(1350, label, cardHtml(`0${i + 1}`, c.title, c.prompt, 1e9), true)),
        page(1350, label, ctaHtml(`Save this for <span class="hl">${esc(p.save)}</span>.`, `Send it to ${esc(send)}.<br><br>Follow ${HANDLE} for Day ${p.day + 1}.`), false)];
      for (const [i, html] of cs.entries()) {
        await sq.setContent(html, { waitUntil: 'load' });
        await sq.screenshot({ path: path.join(OUT, day, 'carousel', `slide-${i + 1}.png`) });
      }
      fs.writeFileSync(path.join(OUT, day, 'carousel', 'caption.txt'), p.caption.trim() + '\n');
    }

    // Main Reel: hook, one typed card per prompt, save + send ask.
    const main = [{ frames: [{ html: page(1920, label, hookHtml(p.hook, esc(p.sub))), dur: 1 }], speech: p.say, minDur: 2 }];
    p.cards.forEach((c, i) => main.push({ ...typed(`0${i + 1}`, c.title, c.prompt, label), speech: c.say || `Prompt ${ord.at(i)}. ${spoken(c.title).toLowerCase()}.` }));
    main.push({ frames: [{ html: page(1920, label, ctaHtml(`Save this for <span class="hl">${esc(p.save)}</span>.`, `Send it to ${esc(send)}.<br>Follow ${HANDLE} for Day ${p.day + 1}.`)), dur: 1 }],
      speech: `Save this for ${p.save}, and send it to ${send}. Day ${p.day + 1} is tomorrow.` });
    await buildReel(vert, main, `${day}/1-main-reel-1230`);
    if (MODE === 'render') fs.writeFileSync(path.join(OUT, day, '1-main-reel-1230.txt'), p.caption.trim() + '\n');

    // Short single-prompt Reels.
    for (const [si, s] of (p.singles || []).entries()) {
      const c = p.cards[s.card], lab = 'Steal this prompt';
      const beats = [
        { frames: [{ html: page(1920, lab, hookHtml(s.hook, '')), dur: 1 }], speech: s.say, minDur: 2.5 },
        { ...typed('', c.title, c.prompt, lab), speech: 'Copy this, and paste it into Claude or ChatGPT.' },
        { frames: [{ html: page(1920, lab, ctaHtml('Send this to <span class="hl">a coworker</span>.', `New prompt every day.<br>Follow ${HANDLE}`)), dur: 1 }],
          speech: `Send this to ${send}. There's a new one every day.` },
      ];
      const slot = ['0-early-reel-0800', '2-evening-reel-1900', '3-extra-reel'][si];
      await buildReel(vert, beats, `${day}/${slot}`);
      if (MODE === 'render') fs.writeFileSync(path.join(OUT, day, `${slot}.txt`), s.caption.trim() + '\n');
    }
    console.log(`${MODE} ${day}`);
  }
  await browser.close();
  if (MODE === 'dump') fs.writeFileSync(path.join(OUT, 'speech.json'), JSON.stringify([...new Set(SPEECH)], null, 1));
})();
