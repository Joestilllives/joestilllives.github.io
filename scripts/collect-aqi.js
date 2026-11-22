#!/usr/bin/env node
/*
 * Hourly collector for Clear Air Check (run by .github/workflows/collect-aqi.yml).
 * Fetches every source for every city server-side, then writes:
 *   aqi/data/latest.json             full snapshot the page loads instantly
 *   aqi/data/history/YYYY-MM.csv     one row per city per hour (for the history chart)
 * Keys come from env: DATA_GOV_IN_KEY, WAQI_TOKEN, OPENAQ_KEY, PURPLEAIR_KEY (all optional).
 */
'use strict';
const fs = require('fs');
const path = require('path');

const AQI_DIR = path.join(__dirname, '..', 'aqi');
require(path.join(AQI_DIR, 'aqi.js'));
require(path.join(AQI_DIR, 'sources.js'));
const S = globalThis.AQSources;

const KEYS = {
  cpcb: process.env.DATA_GOV_IN_KEY || '',
  waqi: process.env.WAQI_TOKEN || '',
  openaq: process.env.OPENAQ_KEY || '',
  purpleair: process.env.PURPLEAIR_KEY || ''
};
const OUT = path.join(AQI_DIR, 'data');
const COLS = S.SOURCES.map((s) => s.id);

async function collectCity(city) {
  const sources = {};
  for (const src of S.SOURCES) {
    const key = src.keyName ? KEYS[src.keyName] : null;
    if (src.keyName && !key) { sources[src.id] = { status: 'nokey' }; continue; }
    try {
      const r = await S.fetchers[src.id](city, key, { pause: 1100 });
      sources[src.id] = {
        status: r.status, aqi: r.aqi ?? null, dominant: r.dominant ?? null, subs: r.subs || {},
        summary: r.summary || null, detail: r.detail || [], note: r.note || null,
        time: r.time ? new Date(r.time).toISOString() : null
      };
    } catch (e) {
      sources[src.id] = { status: 'error', error: String(e.message || e) };
    }
  }
  return sources;
}

function writeHistory(hourIso, cities) {
  const dir = path.join(OUT, 'history');
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, hourIso.slice(0, 7) + '.csv');
  const header = ['time', 'city', ...COLS].join(',');
  let lines = [];
  if (fs.existsSync(file)) {
    // Re-map old rows to the current columns, so adding a source never breaks history.
    const old = fs.readFileSync(file, 'utf8').trim().split('\n');
    const oldCols = old.shift().split(',');
    lines = old.filter(Boolean).map((l) => {
      const v = l.split(','), row = {};
      oldCols.forEach((c, i) => { row[c] = v[i] ?? ''; });
      return [row.time, row.city, ...COLS.map((c) => row[c] ?? '')].join(',');
    });
  }
  lines = lines.filter((l) => !l.startsWith(hourIso + ',')); // re-run in the same hour replaces it
  for (const [name, c] of Object.entries(cities)) {
    const vals = COLS.map((id) => (c.sources[id].status === 'ok' ? c.sources[id].aqi : ''));
    if (vals.some((v) => v !== '')) lines.push([hourIso, name, ...vals].join(','));
  }
  fs.writeFileSync(file, header + '\n' + lines.join('\n') + '\n');
}

(async () => {
  const started = new Date();
  const cities = {};
  for (const city of S.CITIES) {
    cities[city.name] = { lat: city.lat, lon: city.lon, sources: await collectCity(city) };
    const summary = COLS.map((id) => {
      const s = cities[city.name].sources[id];
      return id + '=' + (s.status === 'ok' ? s.aqi : s.status);
    }).join(' ');
    console.log(city.name.padEnd(10), summary);
  }

  fs.mkdirSync(OUT, { recursive: true });
  const snapshot = { generated: started.toISOString(), cities };
  fs.writeFileSync(path.join(OUT, 'latest.json'), JSON.stringify(snapshot));

  const hour = new Date(started);
  hour.setUTCMinutes(0, 0, 0);
  writeHistory(hour.toISOString().slice(0, 13) + ':00Z', cities);

  const anyOk = Object.values(cities).some((c) => Object.values(c.sources).some((s) => s.status === 'ok'));
  if (!anyOk) { console.error('No source returned data.'); process.exit(1); }
})();
