// Original music bed + sound effects, composed with Tone.js and rendered offline in Chromium. Writes bed.wav and sfx.wav.
const fs = require('fs'), path = require('path'), { chromium } = require('playwright');
const DIR = __dirname, T = JSON.parse(fs.readFileSync(path.join(DIR, 'timeline.json')));
const TONE = fs.readFileSync(path.join(DIR, 'node_modules/tone/build/Tone.js'), 'utf8');
(async () => {
  const br = await chromium.launch(); const pg = await br.newPage(); await pg.setContent('<html><body></body></html>');
  await pg.addScriptTag({ content: TONE });
  const render = async (kind) => pg.evaluate(async ({ T, kind }) => {
    const B = Object.fromEntries(T.beats.map(b => [b.id, b])), dur = T.total + 1.5;
    const buf = await Tone.Offline(({ transport }) => {
      if (kind === 'bed') {
        // Calm, sharp: a soft triangle pad and a quiet plucked pulse. D minor tension, resolving to D major when the splits line up.
        const verb = new Tone.Reverb({ decay: 3.5, wet: 0.35 }).toDestination();
        const pad = new Tone.PolySynth(Tone.Synth, { oscillator: { type: 'triangle' }, envelope: { attack: 0.9, decay: 0.5, sustain: 0.7, release: 1.6 }, volume: -16 }).connect(verb);
        const pluck = new Tone.PolySynth(Tone.Synth, { oscillator: { type: 'sine' }, envelope: { attack: 0.005, decay: 0.25, sustain: 0, release: 0.2 }, volume: -20 }).connect(verb);
        const chords = [['hook', ['D3', 'F3', 'A3']], ['parts', ['A#2', 'D3', 'F3']], ['split', ['G2', 'A#2', 'D3']], ['jam', ['A2', 'C#3', 'E3', 'G3']],
                        ['receipt', ['F2', 'A2', 'C3']], ['send', ['A#2', 'D3', 'F3', 'A3']]];
        for (const [id, notes] of chords) { const b = B[id]; pad.triggerAttackRelease(notes, b.dur - 0.05, b.start); }
        const tw = B.turn; pad.triggerAttackRelease(['D3', 'F#3', 'A3', 'D4'], tw.start + tw.dur - T.at.line, T.at.line);   // resolution lands on the line
        const silenceA = tw.start, silenceB = tw.start + tw.pre;                                                     // the drop before the twist
        for (let t = 0.2; t < T.total; t += 0.6) { if (t > silenceA - 0.6 && t < T.at.line) continue;
          const id = T.beats.find(b => t >= b.start && t < b.start + b.dur)?.id; const n = { hook: 'D4', parts: 'F4', split: 'D4', jam: 'E4', turn: 'A4', receipt: 'C4', send: 'F4' }[id] || 'D4';
          pluck.triggerAttackRelease(n, 0.12, t, 0.5); }
      } else {
        // Sound effects, synthesized: a whoosh as each key slides in, a bright click when the splits align, a low thunk when the plug turns, rattles on the jam.
        const whoosh = (t) => { const n = new Tone.Noise('pink'); const f = new Tone.Filter(400, 'bandpass'); const g = new Tone.Gain(0).toDestination(); n.connect(f); f.connect(g);
          n.start(t).stop(t + 0.7); f.frequency.setValueAtTime(300, t); f.frequency.exponentialRampToValueAtTime(3000, t + 0.5); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.35, t + 0.15); g.gain.linearRampToValueAtTime(0, t + 0.65); };
        const click = (t, v = 0.7) => { const s = new Tone.MetalSynth({ envelope: { attack: 0.001, decay: 0.12, release: 0.05 }, harmonicity: 5.1, modulationIndex: 16, resonance: 3500, octaves: 1.2, volume: -12 }).toDestination(); s.triggerAttackRelease('C6', 0.05, t, v); };
        const thunk = (t) => { const m = new Tone.MembraneSynth({ pitchDecay: 0.05, octaves: 4, envelope: { attack: 0.001, decay: 0.35, sustain: 0 }, volume: -6 }).toDestination(); m.triggerAttackRelease('G1', 0.3, t); };
        whoosh(B.hook.start + 0.02); whoosh(B.jam.start + 0.05); whoosh(B.turn.start + 0.35);
        for (let k = 0; k < 6; k++) click(T.at.jammed + 0.05 + k * 0.12, 0.25);
        click(T.at.line, 1.0); click(T.at.line + 0.06, 0.6); thunk(T.at.turns + 0.05);
      }
    }, dur, 2, 48000);
    const L = buf.getChannelData(0), R = buf.getChannelData(1), n = L.length, out = new DataView(new ArrayBuffer(44 + n * 4));
    const w = (o, s) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
    w(0, 'RIFF'); out.setUint32(4, 36 + n * 4, true); w(8, 'WAVE'); w(12, 'fmt '); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 2, true);
    out.setUint32(24, 48000, true); out.setUint32(28, 48000 * 4, true); out.setUint16(32, 4, true); out.setUint16(34, 16, true); w(36, 'data'); out.setUint32(40, n * 4, true);
    for (let i = 0; i < n; i++) { out.setInt16(44 + i * 4, Math.max(-1, Math.min(1, L[i])) * 32767, true); out.setInt16(46 + i * 4, Math.max(-1, Math.min(1, R[i])) * 32767, true); }
    let s = ''; const u = new Uint8Array(out.buffer); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s);
  }, { T, kind });
  for (const k of ['bed', 'sfx']) { fs.writeFileSync(path.join(DIR, k + '.wav'), Buffer.from(await render(k), 'base64')); console.log('wrote', k + '.wav'); }
  await br.close();
})();
