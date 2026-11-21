// Faceless prompt-Reel renderer. Each Reel is one HTML page driven by a paused GSAP timeline,
// seeked frame by frame at 30 fps, so every frame is deterministic and nothing is ever still.
//
//   node render.js --data posts.json --out OUT [--handle @name] [--badge badge.png]
//                  [--voice-cache DIR] [--mode dump|look|render] [--only DAY]
//
// --mode dump    write OUT/speech.json (every spoken line) and stop; voice it with tts.py
// --mode look    one still at the end of every beat into OUT/look/, for qa.py look
// --mode render  (default) MP4s, carousels, grid covers, captions and a script.txt per Reel
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync, spawn } = require('child_process');
const { chromium } = require('playwright');

const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const SKILL = path.resolve(__dirname, '..');
const DATA = path.resolve(arg('data'));
const OUT = path.resolve(arg('out'));
const HANDLE = arg('handle', '@handle');
const MODE = arg('mode', 'render');
const ONLY = arg('only');
const CACHE = path.resolve(arg('voice-cache', path.join(OUT, '..', 'voice-cache')));
const MODELS = process.env.FACELESS_REEL_MODELS || path.join(require('os').homedir(), '.cache', 'faceless-reel');
const GSAP = fs.readFileSync(path.join(MODELS, 'node_modules', 'gsap', 'dist', 'gsap.min.js'), 'utf8');
const WORLDS = JSON.parse(fs.readFileSync(path.join(SKILL, 'palette.json'), 'utf8')).worlds;
const badgeFile = arg('badge');
const BADGE = badgeFile && fs.existsSync(badgeFile)
  ? `<img src="data:image/png;base64,${fs.readFileSync(badgeFile).toString('base64')}">` : '';
const posts = JSON.parse(fs.readFileSync(DATA, 'utf8')).filter(p => !ONLY || String(p.day) === ONLY);

const FPS = 30, WPS = 9;
const hold = s => s.replace(/\s/g, '').length / 15 + 1.5;     // reading time for a finished prompt
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const words = s => s.split(/\s+/).filter(Boolean);
const ord = ['one', 'two', 'three', 'four', 'five', 'six'];
const spoken = t => t.replace(/\b\d\.\s/g, '').replace(/\[|\]/g, '');
const vars = w => Object.entries(WORLDS[w]).map(([k, v]) => `--${k}:${v}`).join(';');
// Variety defaults rotate by day, so consecutive Reels differ even when the JSON does not say how.
const defaults = p => ({
  world: p.world || (p.day % 2 ? 'navy' : 'paper'),
  layout: p.layout || (Math.floor((p.day - 1) / 2) % 2 ? 'center' : 'left'),
  ending: p.ending || (p.day % 2 ? 'send' : 'save'),
});

// ---------- page ----------
const CSS = `*{margin:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;font-family:'Inter',sans-serif;background:var(--bg);color:var(--ink)}
.wrap{position:absolute;inset:0;padding:300px 230px 480px 88px;display:flex;flex-direction:column}
.top{display:flex;flex-direction:column;gap:18px}
.label{font:700 26px 'Inter';letter-spacing:4px;color:var(--muted);text-transform:uppercase}
.prog{height:6px;border-radius:3px;background:var(--line);overflow:hidden}
.prog i{display:block;height:100%;width:100%;background:var(--accent);transform-origin:0 50%;transform:scaleX(0.001)}
.stage{position:relative;flex:1}
.scene{position:absolute;inset:0;display:flex;visibility:hidden;flex-direction:column;justify-content:center;gap:32px;visibility:hidden}
.center .scene{align-items:center;text-align:center}
.hook{font:800 96px/1.04 'Inter Display','Inter';letter-spacing:-2px;text-wrap:balance}
.hook span,.rv{display:inline-block}
.sub{font:500 44px/1.3 'Inter';color:var(--muted);text-wrap:balance}
.num{font:800 96px/1 'Inter Display','Inter';color:var(--accent);font-variant-numeric:tabular-nums}
.title{font:700 58px/1.1 'Inter Display','Inter';letter-spacing:-1px;text-wrap:balance}
.box{background:var(--panel);border:2px solid var(--line);border-radius:28px;padding:40px 44px;width:100%;text-align:left}
.copy{font:700 22px 'Inter';letter-spacing:3px;color:var(--muted);margin-bottom:18px}
.prompt{font:500 33px/1.45 'JetBrains Mono',monospace}
.prompt span{opacity:0}
.wow{font:900 300px/0.9 'Inter Display','Inter';letter-spacing:-8px;color:var(--accent);font-variant-numeric:tabular-nums}
.unit{font:700 56px/1.1 'Inter Display','Inter'}
.bars{display:flex;flex-direction:column;gap:7px;width:100%}
.bars b{display:block;height:12px;border-radius:6px;background:var(--ink);opacity:.85;transform-origin:0 50%}
.sheets{position:relative;width:360px;height:420px}
.center .sheets{margin:0 auto}
.sheets b{position:absolute;inset:0;border-radius:14px;background:var(--panel);border:3px solid var(--ink)}
.sheets b:after{content:'';position:absolute;left:40px;right:40px;top:60px;height:200px;
  background:repeating-linear-gradient(var(--line) 0 10px,transparent 10px 34px)}
.cta1{font:800 76px/1.08 'Inter Display','Inter';letter-spacing:-1.5px;text-wrap:balance}
.cta2{font:500 44px/1.35 'Inter';color:var(--muted)}
.hl{color:var(--accent)}
.foot{display:flex;align-items:center;gap:20px;font:600 30px 'Inter';color:var(--muted)}
.foot img{width:84px;height:84px}`;

function sceneHtml(b, i) {
  const rv = (cls, html) => `<div class="${cls} rv">${html}</div>`;
  if (b.type === 'hook') {
    return `<section class="scene" id="s${i}"><div class="hook">${words(b.text).map(w => `<span>${esc(w)}</span>`).join(' ')}</div>${b.sub ? rv('sub', esc(b.sub)) : ''}</section>`;
  }
  if (b.type === 'wow') {
    const n = Math.min(Math.max(b.from, b.to), 24);
    const vis = b.kind === 'sheets'
      ? `<div class="sheets">${Array.from({ length: Math.min(n, 8) }, () => '<b></b>').join('')}</div>`
      : `<div class="bars">${Array.from({ length: n }, (_, k) => `<b style="width:${55 + ((k * 37) % 45)}%"></b>`).join('')}</div>`;
    return `<section class="scene" id="s${i}"><div class="wow" id="w${i}">${b.from}</div>${rv('unit', esc(b.unit))}${vis}</section>`;
  }
  if (b.type === 'card') {
    return `<section class="scene" id="s${i}">${b.num ? rv('num', b.num) : ''}${rv('title', esc(b.title))}
      <div class="box"><div class="copy">COPY THIS</div><div class="prompt">${words(b.prompt).map(w => `<span>${esc(w)}</span>`).join(' ')}</div></div></section>`;
  }
  return `<section class="scene" id="s${i}">${rv('cta1', b.a)}${rv('cta2', b.b)}</section>`;
}

// The timeline. Motion personality: power3/expo out, 0.35 s base unit, max 3% overshoot,
// entrances overlap 30-50%, blur-to-sharp reveals, 0 ms hard colour flips on the turn.
const TIMELINE = `
const tl = gsap.timeline({paused:true}); const proxies = [];
const R = (t, at, st) => tl.fromTo(t,{opacity:0,y:28,filter:'blur(14px)'},{opacity:1,y:0,filter:'blur(0px)',duration:.35,ease:'power3.out',stagger:st||.2},at);
const world = (name, at) => tl.set(document.documentElement, {...WORLDS[name]}, at);
BEATS.forEach((b, i) => {
  const s = document.getElementById('s'+i), t = b.start;
  tl.set(s,{visibility:'visible'},t); if (i < BEATS.length-1) tl.set(s,{visibility:'hidden'},t+b.dur);
  world(b.world, t);                                   // every beat starts in its own world: a hard cut
  if (b.type==='hook') { R(s.querySelectorAll('.hook span'), t+.05, .06); R(s.querySelectorAll('.rv'), t+.45); }
  if (b.type==='card') {
    R(s.querySelectorAll('.rv'), t+.05);
    tl.fromTo(s.querySelector('.box'),{clipPath:'inset(0 0 100% 0)'},{clipPath:'inset(0 0 0% 0)',duration:.35,ease:'expo.out'},t+.25);
    s.querySelectorAll('.prompt span').forEach((w,k)=>tl.set(w,{opacity:1},t+.5+k/${WPS}));
  }
  if (b.type==='wow') {
    const p = {v:b.from}; proxies.push([p, document.getElementById('w'+i)]);
    const land = t + 1.6;
    R(s.querySelectorAll('.rv'), t+.05);
    tl.to(p,{v:b.to,duration:1.2,ease:'expo.out'},t+.4);
    if (b.kind==='sheets') {
      const sh = [...s.querySelectorAll('.sheets b')];
      sh.forEach((e,k)=>tl.set(e,{x:k*14,y:-k*14,rotation:(k%2?1:-1)*k*.8},t));
      if (b.to < b.from) tl.to(sh.slice(1),{x:0,y:0,rotation:0,opacity:0,duration:.6,ease:'expo.out',stagger:{each:.05,from:'end'}},t+.5);
      else tl.from(sh.slice(1),{x:0,y:0,rotation:0,opacity:0,duration:.6,ease:'expo.out',stagger:.05},t+.5);
    } else {
      const bars = [...s.querySelectorAll('.bars b')], keep = Math.max(1, Math.round(bars.length*Math.min(b.from,b.to)/Math.max(b.from,b.to)));
      if (b.to < b.from) tl.to(bars.slice(keep),{scaleX:.001,duration:.5,ease:'expo.out',stagger:{each:.03,from:'end'}},t+.45);
      else tl.from(bars.slice(keep),{scaleX:.001,duration:.5,ease:'expo.out',stagger:.03},t+.45);
    }
    world(b.flip, land);                                // the twist: 0 ms colour-world flip
    tl.fromTo('#w'+i,{scale:1.03},{scale:1,duration:.2,ease:'power3.out'},land);
  }
  if (b.type==='cta') R(s.querySelectorAll('.rv'), t+.05);
});
tl.to('.prog i',{scaleX:1,ease:'none',duration:TOTAL},0);   // continuous motion to the last frame
window.seekTo = t => { tl.seek(t,false); proxies.forEach(([p,e])=>e.textContent=Math.round(p.v)); };`;

function pageHtml(beats, label, layout, total) {
  const worlds = Object.fromEntries(Object.entries(WORLDS).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).map(([a, c]) => [`--${a}`, c]))]));
  return `<!doctype html><html style="${vars(beats[0].world)}"><head><meta charset="utf-8"><style>${CSS}</style></head><body>
<div class="wrap ${layout}"><div class="top"><div class="label">${label}</div><div class="prog"><i></i></div></div>
<div class="stage">${beats.map(sceneHtml).join('')}</div><div class="foot">${BADGE}${HANDLE}</div></div>
<script>${GSAP}</script><script>(() => { const BEATS=${JSON.stringify(beats)},TOTAL=${total},WORLDS=${JSON.stringify(worlds)};${TIMELINE} })();</script></body></html>`;
}

// ---------- voice + timing ----------
function voiced(text) {
  const src = path.join(CACHE, crypto.createHash('sha1').update(text).digest('hex') + '.wav');
  if (!fs.existsSync(src)) throw new Error(`no voice for "${text}": run --mode dump, then tts.py`);
  return src;
}
const dur = f => parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
function timeBeats(beats) {
  let t = 0;
  for (const b of beats) {
    const need = b.type === 'card' ? 0.5 + words(b.prompt).length / WPS + hold(b.prompt) : b.type === 'wow' ? 2.6 : b.type === 'hook' ? 2.2 : 2.4;
    b.dur = Math.max(need, MODE === 'render' ? dur(voiced(b.speech)) + 0.4 : 0);
    b.start = t; t += b.dur;
  }
  return t;
}

// ---------- build ----------
const SPEECH = [];
async function buildReel(pg, beats, label, layout, file) {
  if (MODE === 'dump') { beats.forEach(b => SPEECH.push(b.speech)); return; }
  const total = timeBeats(beats);
  const errs = []; const onErr = e => errs.push(String(e)); pg.on('pageerror', onErr);
  await pg.goto('about:blank');
  await pg.setContent(pageHtml(beats, label, layout, total), { waitUntil: 'load' });
  pg.off('pageerror', onErr);
  if (errs.length) throw new Error(`timeline error in ${file}: ${errs.join('; ')}`);
  const base = path.join(OUT, file);
  if (MODE === 'look') {
    fs.mkdirSync(path.join(OUT, 'look'), { recursive: true });
    for (const [i, b] of beats.entries()) {
      await pg.evaluate(t => window.seekTo(t), b.start + b.dur - 0.05);
      await pg.screenshot({ path: path.join(OUT, 'look', `${file.replace(/\//g, '_')}_${i}.png`) });
    }
    return;
  }
  const tmp = base + '.tmp';
  fs.mkdirSync(tmp, { recursive: true });
  // Voice track: each line padded to its beat, then concatenated.
  const parts = beats.map((b, i) => {
    const w = path.join(tmp, `a${i}.wav`);
    execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', voiced(b.speech), '-af', 'apad', '-t', b.dur.toFixed(3), '-ar', '48000', '-ac', '2', w]);
    return w;
  });
  fs.writeFileSync(path.join(tmp, 'a.txt'), parts.map(p => `file '${p}'`).join('\n'));
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(tmp, 'a.txt'), '-c', 'copy', path.join(tmp, 'voice.wav')]);
  // Frames: seek the timeline, screenshot, pipe straight into the encoder.
  const enc = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-', '-i', path.join(tmp, 'voice.wav'),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(FPS),
    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
    '-shortest', '-movflags', '+faststart', base + '.mp4'], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, bad) => enc.on('close', c => (c ? bad(new Error('ffmpeg ' + c)) : ok())));
  const frames = Math.ceil(total * FPS);
  for (let f = 0; f < frames; f++) {
    await pg.evaluate(t => window.seekTo(t), f / FPS);
    const jpg = await pg.screenshot({ type: 'jpeg', quality: 92 });
    if (!enc.stdin.write(jpg)) await new Promise(r => enc.stdin.once('drain', r));
    if (f === Math.round(beats[0].dur * FPS) - 2) fs.writeFileSync(path.join(tmp, 'cover.jpg'), jpg);
  }
  enc.stdin.end();
  await done;
  // Grid cover: the finished hook frame, cropped to the 4:5 profile-grid window.
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', path.join(tmp, 'cover.jpg'), '-vf', 'crop=1080:1350:0:285', base + '.cover.png']);
  fs.writeFileSync(base + '.script.txt', beats.map(b => b.speech).join(' ') + '\n');
  fs.writeFileSync(base + '.axes.json', JSON.stringify(beats.axes));
  fs.rmSync(tmp, { recursive: true, force: true });
}

// ---------- static carousel (same worlds, no motion) ----------
async function carousel(pg, p, d, dir) {
  const slide = (inner) => `<!doctype html><html style="${vars(d.world)}"><head><meta charset="utf-8"><style>${CSS}
    html,body{height:1350px}.wrap{padding:96px 88px}.scene{visibility:visible}.prompt span{opacity:1}.prog{display:none}</style></head>
    <body><div class="wrap ${d.layout}"><div class="top"><div class="label">${esc(p.series || 'Get an Hour Back')} &middot; Day ${p.day}/${p.of || 30}</div></div>
    <div class="stage"><section class="scene">${inner}</section></div><div class="foot">${BADGE}${HANDLE}</div></div></body></html>`;
  const send = p.send || 'a coworker who needs it';
  const pages = [`<div class="hook">${esc(p.hook)}</div><div class="sub">${esc(p.sub)} &rarr;</div>`,
    ...p.cards.map((c, i) => `<div class="num">0${i + 1}</div><div class="title">${esc(c.title)}</div><div class="box"><div class="copy">COPY THIS</div><div class="prompt">${words(c.prompt).map(w => `<span>${esc(w)}</span>`).join(' ')}</div></div>`),
    `<div class="cta1">Save this for <span class="hl">${esc(p.save)}</span>.</div><div class="cta2">Send it to ${esc(send)}.<br><br>Follow ${HANDLE} for Day ${p.day + 1}.</div>`];
  for (const [i, html] of pages.entries()) {
    await pg.setContent(slide(html), { waitUntil: 'load' });
    await pg.screenshot({ path: path.join(dir, `slide-${i + 1}.png`) });
  }
  fs.writeFileSync(path.join(dir, 'caption.txt'), p.caption.trim() + '\n');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const vert = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  const sq = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  for (const p of posts) {
    const d = defaults(p), day = `day-${String(p.day).padStart(2, '0')}`;
    const label = `${esc(p.series || 'Get an Hour Back')} &middot; Day ${p.day}/${p.of || 30}`;
    const send = p.send || 'a coworker who needs it';
    fs.mkdirSync(path.join(OUT, day, 'carousel'), { recursive: true });
    if (MODE === 'render') await carousel(sq, p, d, path.join(OUT, day, 'carousel'));
    const flip = d.world === 'navy' ? 'paper' : 'navy';
    const end = d.ending === 'send'
      ? { a: `Send this to <span class="hl">${esc(send)}</span>.`, b: `Save it for ${esc(p.save)}.<br>Follow ${HANDLE} for Day ${p.day + 1}.`,
          speech: `Send this to ${send}, and save it for ${p.save}. Day ${p.day + 1} is tomorrow.` }
      : { a: `Save this for <span class="hl">${esc(p.save)}</span>.`, b: `Send it to ${esc(send)}.<br>Follow ${HANDLE} for Day ${p.day + 1}.`,
          speech: `Save this for ${p.save}, and send it to ${send}. Day ${p.day + 1} is tomorrow.` };

    // Main Reel: hook, the one wow moment, one typed card per prompt, then the ask in the amber world.
    const main = [{ type: 'hook', text: p.hook, sub: p.sub, speech: p.say, world: d.world }];
    if (p.wow) main.push({ type: 'wow', kind: p.wow.kind || 'bars', from: p.wow.from, to: p.wow.to, unit: p.wow.unit, speech: p.wow.say, world: d.world, flip });
    p.cards.forEach((c, i) => main.push({ type: 'card', num: `0${i + 1}`, title: c.title, prompt: c.prompt, world: d.world,
      speech: c.say || `Prompt ${ord.at(i)}. ${spoken(c.title).toLowerCase()}.` }));
    main.push({ type: 'cta', a: end.a, b: end.b, speech: end.speech, world: 'amber' });
    main.axes = { world: d.world, layout: d.layout, ending: d.ending, wow: p.wow ? `${p.wow.kind || 'bars'}-${p.wow.to < p.wow.from ? 'down' : 'up'}` : 'none',
      opener: (p.say.match(/^\W*(\w+)/) || [, ''])[1].toLowerCase(), cards: String(p.cards.length) };
    await buildReel(vert, main, label, d.layout, `${day}/1-main-reel-1230`);
    if (MODE === 'render') fs.writeFileSync(path.join(OUT, day, '1-main-reel-1230.txt'), p.caption.trim() + '\n');

    // Short single-prompt Reels, each in the opposite world and layout from the main one.
    for (const [si, s] of (p.singles || []).entries()) {
      const c = p.cards[s.card], w = si % 2 ? d.world : flip, lay = si % 2 ? d.layout : (d.layout === 'left' ? 'center' : 'left');
      const beats = [
        { type: 'hook', text: s.hook, speech: s.say, world: w },
        { type: 'card', title: c.title, prompt: c.prompt, speech: 'Copy this, and paste it into Claude or ChatGPT.', world: w },
        { type: 'cta', a: `Send this to <span class="hl">${esc(send)}</span>.`, b: `New prompt every day.<br>Follow ${HANDLE}`,
          speech: `Send this to ${send}. There's a new one every day.`, world: 'amber' },
      ];
      beats.axes = { world: w, layout: lay, ending: 'send', wow: 'none', opener: (s.say.match(/^\W*(\w+)/) || [, ''])[1].toLowerCase(), cards: '1' };
      const slot = ['0-early-reel-0800', '2-evening-reel-1900', '3-extra-reel'][si];
      await buildReel(vert, beats, 'Steal this prompt', lay, `${day}/${slot}`);
      if (MODE === 'render') fs.writeFileSync(path.join(OUT, day, `${slot}.txt`), s.caption.trim() + '\n');
    }
    console.log(`${MODE} ${day}`);
  }
  await browser.close();
  if (MODE === 'dump') fs.writeFileSync(path.join(OUT, 'speech.json'), JSON.stringify([...new Set(SPEECH)], null, 1));
})();
