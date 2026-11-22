// Mechanica pilot composition: "How a key actually opens a lock".
// Builds one HTML page driven by a paused GSAP timeline and captures it frame by frame (deterministic, 30 fps).
//   node comp.js --mode look|render [--fps 30] [--scale 1]
// look: stills at key moments + text-coverage report; render: lossless master + timeline.json.
const fs = require('fs'), path = require('path'), { spawn, execFileSync } = require('child_process');
const { chromium } = require('playwright');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const MODE = arg('mode', 'look'), FPS = +arg('fps', 30), SCALE = +arg('scale', 1);
const DIR = __dirname, SKILL = '/home/user/joestilllives.github.io/.claude/skills/faceless-reel';
const spec = JSON.parse(fs.readFileSync(path.join(DIR, 'spec.json')));
const words = JSON.parse(fs.readFileSync(path.join(DIR, arg('vo', 'vo_kokoro'), 'words.json')));
const PAL = JSON.parse(fs.readFileSync(path.join(SKILL, 'palette.json'))).worlds;
const GSAP = fs.readFileSync(path.join(process.env.HOME, '.cache/faceless-reel/node_modules/gsap/dist/gsap.min.js'), 'utf8');
const BADGE = 'data:image/png;base64,' + fs.readFileSync(path.join(SKILL, 'assets/badge.png')).toString('base64');

// ---------- timing: each beat = its voice line + air; the twist gets a silence drop first ----------
const PRE = { turn: 0.55 }, AIR = 0.32;
let t = 0; const beats = spec.beats.map(b => {
  const w = words[b.id], pre = PRE[b.id] || 0, d = { id: b.id, start: t, pre, vo: w.dur, dur: pre + w.dur + AIR };
  d.words = w.words.map(([s, a, e]) => [s, +(t + pre + Math.max(a, 0.25)).toFixed(3), +(t + pre + e).toFixed(3)]);
  t += d.dur; return d; });
const TOTAL = +t.toFixed(3); const B = Object.fromEntries(beats.map(b => [b.id, b]));
const at = (id, word) => { const w = B[id].words.find(x => x[0].toLowerCase().replace(/[^a-z0-9]/g, '').startsWith(word)); return w ? w[1] : B[id].start; };

// ---------- captions: Netflix rules (<=42 chars/line, <=20 chars/s, bottom-heavy, gaps closed to 2 frames) ----------
const caps = [];
const toCap = ws => ({ text: ws.map(w => w[0]).join(' '), a: ws[0][1], e: ws[ws.length - 1][2] });
for (const b of beats) {                                   // a caption per sentence; over 84 characters, split at a comma
  let sent = [];
  const out = s => { const txt = s.map(w => w[0]).join(' ');
    if (txt.length <= 84) return caps.push(toCap(s));
    const k = s.findIndex((w, i) => /,$/.test(w[0]) && i > 1 && i < s.length - 2);
    const cut = k > 0 ? k + 1 : Math.ceil(s.length / 2); caps.push(toCap(s.slice(0, cut))); caps.push(toCap(s.slice(cut))); };
  for (const w of b.words) { sent.push(w); if (/[.?!]$/.test(w[0])) { out(sent); sent = []; } }
  if (sent.length) out(sent);
}
for (let i = 0; i < caps.length; i++) {                    // hold until the next caption (minus 2 frames) when the gap is under 1 s
  const n = caps[i + 1]; const want = caps[i].a + caps[i].text.length / 20 + 0.1;
  caps[i].e = n && n.a - caps[i].e < 1.0 ? n.a - 2 / FPS : Math.max(caps[i].e + 0.4, want);
}
const lines = txt => {                                      // bottom-heavy pyramid, both lines <= 42 characters
  if (txt.length <= 42) return [txt];
  const w = txt.split(' '); let best = null;
  for (let k = 1; k < w.length; k++) { const t1 = w.slice(0, k).join(' '), t2 = w.slice(k).join(' ');
    if (t1.length > 42 || t2.length > 42 || t1.length > t2.length) continue;
    const sc = Math.abs(t2.length - t1.length - 6) + (/[,.]$/.test(w[k - 1]) ? -8 : 0) + (/^(and|the|a|an|to|of|is|in|by|with|that|this|his|her|their|your)$/i.test(w[k - 1]) ? 30 : 0); if (!best || sc < best[0]) best = [sc, [t1, t2]]; }
  return best ? best[1] : [txt];
};
caps.forEach(c => { c.lines = lines(c.text); });

// ---------- the lock (side cutaway, SVG units inside a 760 x 720 box) ----------
const XS = [250, 340, 430, 520, 610], KEYPIN = [90, 120, 70, 135, 105], DRV = 120, SHEAR = 400, REST = 540, TOP = 150;
const RIGHT = KEYPIN.map(L => REST - L - SHEAR);           // how far the right key lifts each stack: [50,20,70,5,35]
const WRONG = [30, 62, 20, 40, 10];
const code = RIGHT.map(v => Math.round(v / 10));          // the "password" shown on the hook: 5 2 7 1 4 (cut depths)
const keyPath = lifts => {                                // key blade with a cut under every pin
  let d = `M -260 ${REST + 60} L -260 ${REST + 12} `;
  XS.forEach((x, i) => { const y = REST - lifts[i]; d += `L ${x - 34} ${REST + 12} L ${x - 6} ${y} L ${x + 6} ${y} L ${x + 34} ${REST + 12} `; });
  return d + `L 700 ${REST + 12} L 720 ${REST + 36} L 700 ${REST + 60} Z`;
};
const spring = (x, y0, y1) => { let d = `M ${x} ${y0}`; const n = 7, h = (y1 - y0) / n; for (let k = 0; k < n; k++) d += ` L ${x + (k % 2 ? -14 : 14)} ${y0 + h * (k + 0.5)}`; return d + ` L ${x} ${y1}`; };
const stacks = XS.map((x, i) => `
  <g class="stack" id="st${i}">
    <path class="spring" id="sp${i}" d="${spring(x, TOP, REST - KEYPIN[i] - DRV)}"/>
    <rect class="driver" id="dr${i}" x="${x - 19}" y="${REST - KEYPIN[i] - DRV}" width="38" height="${DRV}" rx="6"/>
    <rect class="keypin" id="kp${i}" x="${x - 19}" y="${REST - KEYPIN[i]}" width="38" height="${KEYPIN[i]}" rx="6"/>
    <rect class="tick" id="tk${i}" x="${x - 30}" y="${REST - KEYPIN[i] - 2}" width="60" height="4" rx="2"/>
    <line class="guide" x1="${x + 30}" x2="700" y1="${REST - KEYPIN[i]}" y2="${REST - KEYPIN[i]}"/>
  </g>`).join('');
const LOCK = `<svg class="lock" viewBox="150 110 620 560" width="760" height="686">
  <g id="lockbody">
    <rect class="housing" x="170" y="${TOP - 20}" width="520" height="${SHEAR - TOP + 20}" rx="18"/>
    <rect class="plug" id="plug" x="170" y="${SHEAR}" width="520" height="190" rx="18"/>
    ${XS.map(x => `<rect class="shaft" x="${x - 23}" y="${TOP}" width="46" height="${REST - TOP + 6}" rx="8"/>`).join('')}
    <rect class="keyway" x="170" y="${REST + 8}" width="520" height="56"/>
    ${stacks}
    <line class="shear" id="shear" x1="150" x2="710" y1="${SHEAR}" y2="${SHEAR}"/>
  </g>
  <g id="keyR" class="key"><path d="${keyPath(RIGHT)}"/><circle cx="-300" cy="${REST + 36}" r="64"/><circle class="hole" cx="-318" cy="${REST + 36}" r="18"/></g>
  <g id="keyW" class="key wrong"><path d="${keyPath(WRONG)}"/><circle cx="-300" cy="${REST + 36}" r="64"/><circle class="hole" cx="-318" cy="${REST + 36}" r="18"/></g>
</svg>`;
// Front view of the plug turning (shown after the splits line up).
const FRONT = `<svg class="front" viewBox="0 0 760 720" width="760" height="720">
  <circle class="housing" cx="380" cy="380" r="250"/><circle class="plugF" id="plugF" cx="380" cy="380" r="170"/>
  <g id="plugRot"><circle class="plugF2" cx="380" cy="380" r="170"/><rect class="keyway" x="368" y="300" width="24" height="170" rx="6"/>
  <rect class="keyF" x="372" y="290" width="16" height="190" rx="5"/></g>
  <circle class="shearF" id="shearF" cx="380" cy="380" r="170"/>
  <rect class="driver" x="361" y="100" width="38" height="70" rx="6"/></svg>`;
const KEYBIG = `<svg class="keybig" viewBox="-380 360 1120 300" width="760" height="204" style="top:250px;transform:scale(1.0)">
  <path class="keyshape" d="${keyPath(RIGHT)}"/><circle class="keyshape" cx="-300" cy="${REST + 36}" r="64"/><circle class="hole" cx="-318" cy="${REST + 36}" r="18"/>
  ${XS.map((x, i) => `<g class="cut" id="cut${i}"><rect x="${x - 26}" y="${REST - RIGHT[i] - 92}" width="52" height="62" rx="12"/><text x="${x}" y="${REST - RIGHT[i] - 46}">${code[i]}</text></g>`).join('')}</svg>`;
const PATENT = `<div class="patent"><div class="pmeta">US PATENT 48,475 &middot; L. YALE JR. &middot; 1865</div>
  <div class="pq"><span class="pl">&ldquo;&hellip;must all be arranged by the key,</span><span class="pl">so that the various lines of division</span><span class="pl">&hellip; are <b class="ul">all in the same line</b></span><span class="pl">before the cylinder &hellip; can be turned.&rdquo;</span></div>
  <div class="pnote">Transcribed from the scanned patent</div><div class="stamp" id="stamp">US 48,475</div></div>`;
const HERO = fs.existsSync(path.join(DIR, 'hero_full', 'f_0060.png'));

const W = c => Object.entries(PAL[c]).map(([k, v]) => `--${k}:${v}`).join(';');
const CSS = `*{margin:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden;background:var(--bg);color:var(--ink);font-family:Inter,'Inter Display',sans-serif}
.head{position:absolute;left:88px;top:296px;width:762px;display:flex;align-items:center;gap:16px;font:700 24px Inter;letter-spacing:4px;color:var(--muted);text-transform:uppercase}
.head img{width:56px;height:56px}.head .h{margin-left:auto;letter-spacing:1px;text-transform:none;font-weight:600}
.prog{position:absolute;left:88px;top:368px;width:762px;height:6px;border-radius:3px;background:var(--line);overflow:hidden}.prog i{display:block;height:100%;background:var(--accent);transform-origin:0 50%;transform:scaleX(.001)}
.hl{position:absolute;left:88px;top:420px;width:762px;font:800 70px/1.06 'Inter Display',Inter;letter-spacing:-1.5px;text-wrap:balance}
.stage{position:absolute;left:88px;top:560px;width:762px;height:720px}
.stage>*{position:absolute;left:0;top:0}
.housing{fill:var(--panel);stroke:var(--line);stroke-width:4}.plug{fill:#24396f;stroke:var(--line);stroke-width:4}
.shaft{fill:#0a1430}.keyway{fill:#0a1430}.keypin{fill:#E0B04F}.driver{fill:#C9D2EC}.spring{fill:none;stroke:#8C99BF;stroke-width:5;stroke-linejoin:round}
.tick{fill:var(--accent);opacity:0}.guide{stroke:var(--accent);stroke-width:3;stroke-dasharray:8 8;opacity:.75;transform:scaleX(0)}.shear{stroke:var(--muted);stroke-width:5;stroke-dasharray:14 10}
.key path,.key circle{fill:#D9DEEB}.key .hole{fill:var(--bg)}.wrong path,.wrong circle{fill:#AEB6CC}
.keyshape{fill:#D9DEEB}.hole{fill:var(--bg)}.cut rect{fill:var(--accent)}.cut text{font:800 46px Inter;fill:var(--bg);text-anchor:middle}
.plugF,.plugF2{fill:#24396f;stroke:var(--line);stroke-width:4}.keyF{fill:#D9DEEB}.shearF{fill:none;stroke:var(--gain);stroke-width:8;opacity:0}
.lbl{position:absolute;font:700 34px Inter;color:var(--ink);background:var(--bg);border:3px solid var(--accent);border-radius:14px;padding:6px 16px;white-space:nowrap}
.cap{position:absolute;left:88px;top:1300px;width:762px;text-align:center}.cap span{display:inline-block;font:600 36px/1.22 Inter;color:#fff;background:rgba(6,12,30,.82);padding:8px 18px;border-radius:12px;max-width:762px}
.patent{position:absolute;left:8px;top:30px;width:720px;background:#FBF7EE;color:#1a1a1a;border-radius:18px;padding:44px 46px;box-shadow:0 12px 22px rgba(0,0,0,.22)}
.pq span{display:block}.stamp{position:absolute;right:30px;bottom:-46px;font:800 30px Inter;letter-spacing:2px;color:#9a3412;border:5px solid #9a3412;border-radius:12px;padding:8px 16px;transform:rotate(-6deg);background:#FBF7EE}
.pmeta{font:700 24px Inter;letter-spacing:2px;color:#5a5345;margin-bottom:26px}.pq{font:500 40px/1.34 Georgia,serif}.pnote{margin-top:26px;font:500 24px Inter;color:#6b6456}
.ul{font-weight:inherit;background:linear-gradient(var(--accent),var(--accent)) no-repeat 0 92%/0% 8px}
.cta{position:absolute;left:88px;top:470px;width:762px;font:800 72px/1.08 'Inter Display',Inter;letter-spacing:-1.5px;text-wrap:balance}.cta2{position:absolute;left:88px;top:1120px;width:762px;font:600 40px/1.3 Inter;color:var(--muted)}
.ring{position:absolute;left:339px;top:780px;width:260px;height:260px;border-radius:50%}
.hero{width:760px;height:760px;top:-20px}
`;
const html = `<!doctype html><html style="${W('navy')}"><head><meta charset="utf-8"><style>${CSS}</style></head><body>
<div class="head"><img src="${BADGE}">Mechanica<span class="h">@mechanica.explained</span></div><div class="prog"><i></i></div>
<div class="hl" id="hl"></div>
<div class="stage" id="stage">
  <div id="sHook">${KEYBIG}</div>
  ${HERO ? `<img class="hero" id="hero" src="hero_full/f_0001.png">` : ''}
  <div id="sLock">${LOCK}</div>
  <div id="sFront">${FRONT}</div>
  <div id="sPatent">${PATENT}</div>
  <div class="lbl" id="lPlug" style="left:40px;top:470px">plug</div><div class="lbl" id="lPins" style="left:590px;top:300px">pins</div>
  <div class="lbl" id="lSpr" style="left:270px;top:-10px">springs</div><div class="lbl" id="lSplit" style="left:610px;top:330px">split</div>
  <div class="lbl" id="lJam" style="left:560px;top:268px;border-color:var(--cost)">jammed</div><div class="lbl" id="lLine" style="left:560px;top:268px;border-color:var(--gain)">one line</div>
  <div class="lbl" id="lTurn" style="left:300px;top:670px;border-color:var(--gain)">it turns</div>
</div>
<div class="cta" id="cta">Send this to the friend who&rsquo;s always losing their keys.</div><div class="cta2" id="cta2">Follow @mechanica.explained for how things work.</div><img class="ring" id="ring" src="data:image/png;base64,${fs.readFileSync(path.join(SKILL, 'assets/profile-picture.png')).toString('base64')}">
<div class="cap" id="cap"><span id="capt"></span></div>
<script>${GSAP}</script><script>
const B=${JSON.stringify(B)},CAPS=${JSON.stringify(caps)},TOTAL=${TOTAL},PAL=${JSON.stringify(PAL)},RIGHT=${JSON.stringify(RIGHT)},WRONG=${JSON.stringify(WRONG)};
const AT=${JSON.stringify({ plug: at('parts', 'plug'), pins: at('parts', 'pins'), springs: at('parts', 'springs'), split: at('split', 'split'), different: at('split', 'different'), jammed: at('jam', 'jammed'), line: at('turn', 'line'), turns: at('turn', 'turns'), patent: at('receipt', 'patent') })};
const tl=gsap.timeline({paused:true}), E='power3.out', X='expo.out';
const world=(w,t)=>tl.set(document.documentElement,{...Object.fromEntries(Object.entries(PAL[w]).map(([k,v])=>['--'+k,v]))},t);
const show=(sel,t,on=true)=>tl.set(sel,{autoAlpha:on?1:0},t);
const pop=(sel,t)=>tl.fromTo(sel,{autoAlpha:0,y:24,filter:'blur(12px)'},{autoAlpha:1,y:0,filter:'blur(0px)',duration:.35,ease:E},t);
const hl=(txt,t)=>{tl.call(()=>{},null,t);tl.set('#hl',{textContent:txt},t);tl.fromTo('#hl',{autoAlpha:0,y:20,filter:'blur(10px)'},{autoAlpha:1,y:0,filter:'blur(0px)',duration:.35,ease:E},t)};
gsap.set(['#sLock','#sFront','#sPatent','.lbl','#cta','#cta2','#ring','#hl','#keyW','#hero'],{autoAlpha:0});
const lift=(i,dy,t,d=.45)=>{tl.to(['#kp'+i,'#dr'+i,'#tk'+i],{y:-dy,duration:d,ease:X},t);tl.to('#sp'+i,{scaleY:1-dy/(${REST}-${TOP}-260),transformOrigin:'50% 0%',duration:d,ease:X},t)};
// HOOK: the key slides in; its cuts light up as a five-digit "password".
let b=B.hook; world('navy',b.start); hl('Your key is a password',b.start+.05);
tl.fromTo('#sHook',{x:-420},{x:0,duration:.8,ease:X},b.start); show('#sHook',b.start);
tl.set('.cut',{autoAlpha:0},0); document.querySelectorAll('.cut').forEach((c,i)=>tl.fromTo(c,{autoAlpha:0,scale:.6,transformOrigin:'50% 100%'},{autoAlpha:1,scale:1,duration:.3,ease:X},b.start+.9+i*.28));
// PARTS: Blender exploded view assembles, then the 2D cutaway; labels land as each part is named.
b=B.parts; show('#sHook',b.start,false); tl.set('#hl',{autoAlpha:0},b.start);
const heroEnd=b.start+2.0; if(document.getElementById('hero')){show('#hero',b.start);show('#hero',heroEnd,false);}
show('#sLock',document.getElementById('hero')?heroEnd:b.start);
tl.fromTo('.stack',{y:-160,autoAlpha:0},{y:0,autoAlpha:1,duration:.5,ease:X,stagger:.06},heroEnd);
pop('#lPlug',Math.max(AT.plug,heroEnd+.05)); pop('#lPins',Math.max(AT.pins,heroEnd+.1)); pop('#lSpr',Math.max(AT.springs,heroEnd+.15));
// SPLIT: each stack separates at its split; ticks mark five different heights.
b=B.split; tl.to(['#lPlug','#lPins','#lSpr'],{autoAlpha:0,duration:.2},b.start); hl('Every stack is split in two',b.start+.05);
for(let i=0;i<5;i++){tl.to('#dr'+i,{y:-14,duration:.3,ease:X,yoyo:true,repeat:1},AT.split+i*.08);tl.to('#tk'+i,{opacity:1,duration:.2},AT.split+i*.08);}
pop('#lSplit',AT.split);
tl.fromTo('.guide',{scaleX:0,transformOrigin:'0% 50%'},{scaleX:1,duration:.4,ease:X,stagger:.12},AT.different);
tl.fromTo('#sLock',{scale:1},{scale:1.14,transformOrigin:'45% 52%',duration:.45,ease:X},AT.different-.15);
// JAM: wrong key; splits scattered; shear line coral; the plug shakes but cannot turn.
b=B.jam; tl.to(['#lSplit','#hl','.guide'],{autoAlpha:0,duration:.2},b.start); tl.set('#sLock',{scale:1},b.start); show('#keyW',b.start);
tl.fromTo('#keyW',{x:-700},{x:0,duration:.9,ease:X},b.start+.05); WRONG.forEach((v,i)=>lift(i,v,b.start+.35+i*.1));
tl.set('#shear',{stroke:'var(--cost)'},AT.jammed-.2); hl('Wrong key: jammed',AT.jammed-.2); pop('#lJam',AT.jammed);
tl.to('#plug',{x:6,duration:.06,yoyo:true,repeat:7,ease:'none'},AT.jammed+.05);
// TURN: silence drop, then the right key lifts every split to one line (teal flash), then the plug turns (front view).
b=B.turn; tl.to(['#lJam','#hl'],{autoAlpha:0,duration:.15},b.start); tl.to('#keyW',{x:-700,duration:.35,ease:'power2.in'},b.start); WRONG.forEach((v,i)=>lift(i,0,b.start+.05,.3));
tl.set('#shear',{stroke:'var(--muted)'},b.start); show('#keyR',b.start+.3);
tl.fromTo('#keyR',{x:-700},{x:0,duration:.9,ease:X},b.start+.35); RIGHT.forEach((v,i)=>lift(i,v,b.start+b.pre+.6+i*.12,.5));
const L=AT.line; tl.set('#shear',{stroke:'var(--gain)',strokeDasharray:'none',strokeWidth:9},L); tl.set('.tick',{fill:'var(--gain)'},L);
tl.fromTo('#lockbody',{scale:1.03,transformOrigin:'50% 55%'},{scale:1,duration:.25,ease:E},L); hl('One line. Now it turns.',L); pop('#lLine',L+.05);
show('#sLock',AT.turns-.15,false); tl.set('#lLine',{autoAlpha:0},AT.turns-.15); show('#sFront',AT.turns-.15); tl.set('#shearF',{opacity:1},AT.turns-.15);
tl.fromTo('#plugRot',{rotation:0,svgOrigin:'380 380'},{rotation:90,svgOrigin:'380 380',duration:.9,ease:X},AT.turns); pop('#lTurn',AT.turns+.3);
// RECEIPT: the patent itself, underline drawn under the key phrase.
b=B.receipt; world('paper',b.start); tl.set(['#sFront','#lTurn','#hl'],{autoAlpha:0},b.start); hl('Written down in 1865',b.start+.05);
pop('#sPatent',b.start+.15); tl.set('.pl',{autoAlpha:0},0);
document.querySelectorAll('.pl').forEach((l,i)=>tl.fromTo(l,{autoAlpha:0,y:16,filter:'blur(8px)'},{autoAlpha:1,y:0,filter:'blur(0px)',duration:.35,ease:E},b.start+.35+i*.75));
tl.to('.ul',{backgroundSize:'100% 8px',duration:.7,ease:'power2.inOut'},b.start+2.9);
tl.fromTo('#stamp',{autoAlpha:0,scale:1.6},{autoAlpha:1,scale:1,duration:.25,ease:'power3.in'},b.start+3.7);
tl.fromTo('#sPatent',{rotation:0},{rotation:-1.2,duration:.12,ease:'power2.out',yoyo:true,repeat:1},b.start+3.95);
// SEND: amber world, the ask.
b=B.send; world('amber',b.start); tl.set(['#sPatent','#hl','#stage'],{autoAlpha:0},b.start); pop('#cta',b.start+.05); pop('#cta2',b.start+.5);
tl.fromTo('#ring',{autoAlpha:0,rotation:-40,scale:.7},{autoAlpha:1,rotation:0,scale:1,duration:.6,ease:X},b.start+.3);
tl.to('.prog i',{scaleX:1,ease:'none',duration:TOTAL},0);
const HF=${HERO ? 60 : 0},HS=B.parts.start;
window.seekTo=t=>{tl.seek(t,false);const c=CAPS.find(c=>t>=c.a&&t<c.e);const el=document.getElementById('capt');el.innerHTML=c?c.lines.map(l=>l.replace(/&/g,'&amp;').replace(/</g,'&lt;')).join('<br>'):'';el.style.visibility=c?'visible':'hidden';
 if(HF){const f=Math.min(HF,Math.max(1,Math.floor((t-HS)*30)+1));const im=document.getElementById('hero');const s='hero_full/f_'+String(f).padStart(4,'0')+'.png';if(!im.src.endsWith(s))im.src=s;}};
window.coverage=()=>{const g=new Uint8Array(108*192);let n=0;const walk=e=>{for(const c of e.childNodes){if(c.nodeType===3&&c.textContent.trim()){const p=c.parentElement;if(!p.checkVisibility({opacityProperty:true,visibilityProperty:true}))continue;const r=document.createRange();r.selectNodeContents(c);for(const q of r.getClientRects())for(let y=Math.max(0,Math.floor(q.top/10));y<Math.min(192,Math.ceil(q.bottom/10));y++)for(let x=Math.max(0,Math.floor(q.left/10));x<Math.min(108,Math.ceil(q.right/10));x++)g[y*108+x]=1;}else if(c.nodeType===1)walk(c);}};walk(document.body);for(const v of g)n+=v;return n/g.length;};
</script></body></html>`;
fs.writeFileSync(path.join(DIR, 'comp.html'), html);
fs.writeFileSync(path.join(DIR, 'timeline.json'), JSON.stringify({ total: TOTAL, beats, caps, at: { line: at('turn', 'line'), turns: at('turn', 'turns'), jammed: at('jam', 'jammed') } }, null, 1));

(async () => {
  const br = await chromium.launch(); const pg = await br.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: SCALE });
  const errs = []; pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto('file://' + path.join(DIR, 'comp.html')); await pg.waitForTimeout(600);
  if (errs.length) throw new Error(errs.join('; '));
  const seek = async s => { await pg.evaluate(s => window.seekTo(s), s); await pg.evaluate(() => new Promise(r => requestAnimationFrame(() => r()))); };
  if (MODE === 'look') {
    fs.mkdirSync(path.join(DIR, 'look'), { recursive: true }); const cov = {};
    const moments = { hook: B.hook.start + 2.6, hero: B.parts.start + 1.0, parts: B.parts.start + B.parts.dur - .1, split: B.split.start + B.split.dur - .1,
      jam: B.jam.start + B.jam.dur - .2, line: (B.turn.start + B.turn.dur) - 1.6, turn: B.turn.start + B.turn.dur - .1, receipt: B.receipt.start + B.receipt.dur - .1, send: TOTAL - .05 };
    for (const [k, s] of Object.entries(moments)) { await seek(s); if (k === 'hero') await pg.waitForTimeout(300); await pg.screenshot({ path: path.join(DIR, 'look', `${k}.png`) }); cov[k] = await pg.evaluate(() => window.coverage()); }
    fs.writeFileSync(path.join(DIR, 'look', 'coverage.json'), JSON.stringify(cov, null, 1)); console.log('look done', TOTAL.toFixed(2) + 's', JSON.stringify(cov));
  } else {
    const t0 = Date.now(), frames = Math.ceil(TOTAL * FPS); let maxCov = 0;
    const enc = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-qp', '0', '-pix_fmt', 'yuv444p', path.join(DIR, 'master_video.mkv')], { stdio: ['pipe', 'inherit', 'inherit'] });
    const done = new Promise((ok, bad) => enc.on('close', c => c ? bad(new Error('ffmpeg ' + c)) : ok()));
    for (let f = 0; f < frames; f++) {
      await seek(f / FPS); if (f % 15 === 0) maxCov = Math.max(maxCov, await pg.evaluate(() => window.coverage()));
      const png = await pg.screenshot({ type: 'png' }); if (!enc.stdin.write(png)) await new Promise(r => enc.stdin.once('drain', r));
    }
    enc.stdin.end(); await done;
    const el = (Date.now() - t0) / 1000; fs.writeFileSync(path.join(DIR, 'render_stats.json'), JSON.stringify({ frames, seconds: el, per_frame: el / frames, max_text_coverage: maxCov }));
    console.log(`render ${frames} frames in ${el.toFixed(0)}s (${(el / frames).toFixed(2)} s/frame), max text coverage ${(maxCov * 100).toFixed(1)}%`);
  }
  await br.close();
})();
