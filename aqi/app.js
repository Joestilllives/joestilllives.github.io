/* Clear Air Check: fetches each source, normalises to Indian AQI, renders. */
(function () {
  'use strict';
  var A = window.AQI;

  var CITIES = [
    { name: 'Delhi', lat: 28.6139, lon: 77.2090 },
    { name: 'Mumbai', lat: 19.0760, lon: 72.8777 },
    { name: 'Bengaluru', lat: 12.9716, lon: 77.5946 },
    { name: 'Kolkata', lat: 22.5726, lon: 88.3639 },
    { name: 'Chennai', lat: 13.0827, lon: 80.2707 },
    { name: 'Hyderabad', lat: 17.3850, lon: 78.4867 },
    { name: 'Pune', lat: 18.5204, lon: 73.8567 },
    { name: 'Ahmedabad', lat: 23.0225, lon: 72.5714 },
    { name: 'Jaipur', lat: 26.9124, lon: 75.7873 },
    { name: 'Lucknow', lat: 26.8467, lon: 80.9462 },
    { name: 'Kanpur', lat: 26.4499, lon: 80.3319 },
    { name: 'Patna', lat: 25.5941, lon: 85.1376 }
  ];

  var NEAR_KM = 25;      // "nearby" radius for stations and sensors
  var FALLBACK_KM = 75;  // widen if nothing is nearby

  // ---------- small helpers ----------
  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function store(k, v) {
    try {
      if (v === undefined) return localStorage.getItem(k);
      if (v === null || v === '') localStorage.removeItem(k); else localStorage.setItem(k, v);
    } catch (e) { /* storage unavailable: run without it */ }
    return null;
  }

  function num(v) {
    var n = typeof v === 'number' ? v : parseFloat(v);
    return isFinite(n) ? n : null;
  }

  function getJSON(url, headers) {
    var ctl = new AbortController();
    var t = setTimeout(function () { ctl.abort(); }, 20000);
    return fetch(url, { headers: headers || {}, signal: ctl.signal })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .catch(function (e) {
        if (e.name === 'AbortError') throw new Error('Request timed out');
        if (e instanceof TypeError) throw new Error('Network or CORS error');
        throw e;
      })
      .finally(function () { clearTimeout(t); });
  }

  function ago(date) {
    if (!date || isNaN(date)) return 'time unknown';
    var mins = Math.round((Date.now() - date.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    var h = Math.round(mins / 60);
    if (h < 48) return h + ' h ago';
    return Math.round(h / 24) + ' days ago';
  }

  function round(v, d) {
    if (v == null) return null;
    var f = Math.pow(10, d || 0);
    return Math.round(v * f) / f;
  }

  function subsFromConc(conc) {
    var s = {};
    Object.keys(conc).forEach(function (k) {
      var v = A.subIndex(k, conc[k]);
      if (v != null) s[k] = v;
    });
    return s;
  }

  function medianSubs(list) {
    var out = {};
    A.POLLUTANTS.forEach(function (p) {
      var m = A.median(list.map(function (s) { return s[p.id]; }));
      if (m != null) out[p.id] = Math.round(m);
    });
    return out;
  }

  function finish(base, subs) {
    var ov = A.overall(subs);
    base.subs = subs;
    base.aqi = ov ? ov.aqi : null;
    base.dominant = ov ? ov.dominant : null;
    base.status = ov ? 'ok' : 'empty';
    return base;
  }

  // ---------- sources ----------

  var SOURCES = [
    {
      id: 'cpcb', name: 'CPCB (official)', kind: 'Government stations', official: true, keyName: 'cpcb',
      fetch: fetchCpcb
    },
    {
      id: 'cams', name: 'Open-Meteo · CAMS', kind: 'Satellite-assisted model', official: false,
      fetch: fetchOpenMeteo
    },
    {
      id: 'waqi', name: 'WAQI (aqicn.org)', kind: 'Global aggregator', official: false, keyName: 'waqi',
      fetch: fetchWaqi
    },
    {
      id: 'openaq', name: 'Citizen sensors · OpenAQ', kind: 'Low-cost sensors', official: false, keyName: 'openaq',
      fetch: fetchOpenAq
    }
  ];

  // Official CPCB real-time feed published on data.gov.in.
  // Its min/max/avg values are CPCB pollutant sub-indices (not concentrations).
  var CPCB_RESOURCE = '3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69';
  var CPCB_POLL = { 'PM2.5': 'pm25', 'PM10': 'pm10', 'NO2': 'no2', 'SO2': 'so2', 'CO': 'co', 'OZONE': 'o3', 'NH3': 'nh3' };
  var cpcbCache = null;

  function parseCpcbTime(s) {
    var m = /^(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})/.exec(s || '');
    if (!m) return null;
    return new Date(m[3] + '-' + m[2] + '-' + m[1] + 'T' + m[4] + ':' + m[5] + ':00+05:30');
  }

  function fetchCpcb(loc, key) {
    var fresh = cpcbCache && Date.now() - cpcbCache.t < 10 * 60000;
    var p = fresh ? Promise.resolve(cpcbCache.records) :
      getJSON('https://api.data.gov.in/resource/' + CPCB_RESOURCE +
        '?api-key=' + encodeURIComponent(key) + '&format=json&limit=5000')
        .then(function (j) {
          if (!j || !Array.isArray(j.records)) throw new Error((j && j.message) || 'Unexpected response');
          cpcbCache = { t: Date.now(), records: j.records };
          return j.records;
        });

    return p.then(function (records) {
      var byStation = {};
      records.forEach(function (r) {
        var lat = num(r.latitude), lon = num(r.longitude);
        var pid = CPCB_POLL[String(r.pollutant_id || '').toUpperCase()];
        var val = num(r.avg_value != null ? r.avg_value : r.pollutant_avg);
        if (lat == null || lon == null || !pid) return;
        var st = byStation[r.station] || (byStation[r.station] = {
          name: r.station, lat: lat, lon: lon, subs: {}, time: parseCpcbTime(r.last_update),
          dist: A.distanceKm(loc.lat, loc.lon, lat, lon)
        });
        if (val != null) st.subs[pid] = Math.round(val);
      });

      var stations = Object.keys(byStation).map(function (k) { return byStation[k]; })
        .map(function (s) { var o = A.overall(s.subs); s.aqi = o ? o.aqi : null; return s; })
        .filter(function (s) { return s.aqi != null; })
        .sort(function (a, b) { return a.dist - b.dist; });

      var near = stations.filter(function (s) { return s.dist <= NEAR_KM; });
      if (!near.length) near = stations.filter(function (s) { return s.dist <= FALLBACK_KM; }).slice(0, 3);

      var base = { detail: [], note: null };
      if (!near.length) { base.status = 'empty'; base.note = 'No official station within ' + FALLBACK_KM + ' km.'; return base; }

      base.time = near.reduce(function (t, s) { return s.time && (!t || s.time > t) ? s.time : t; }, null);
      base.summary = near.length === 1 ? '1 station' : 'Median of ' + near.length + ' stations';
      base.detail = near.slice(0, 8).map(function (s) {
        return { text: s.name, meta: round(s.dist, 1) + ' km · AQI ' + s.aqi };
      });
      if (near.length > 8) base.detail.push({ text: '+ ' + (near.length - 8) + ' more stations', meta: '' });

      var res = finish(base, medianSubs(near.map(function (s) { return s.subs; })));
      res.aqi = Math.round(A.median(near.map(function (s) { return s.aqi; })));
      return res;
    });
  }

  function fetchOpenMeteo(loc) {
    var url = 'https://air-quality-api.open-meteo.com/v1/air-quality?latitude=' + loc.lat + '&longitude=' + loc.lon +
      '&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone' +
      '&past_days=2&forecast_days=1&timeformat=unixtime';
    return getJSON(url).then(function (j) {
      var h = j && j.hourly;
      if (!h || !h.time) throw new Error('Unexpected response');
      var now = Date.now() / 1000;
      var idx = [];
      h.time.forEach(function (t, i) { if (t <= now) idx.push(i); });
      function avg(field, hours) {
        var arr = h[field] || [];
        return A.mean(idx.slice(-hours).map(function (i) { return arr[i]; }));
      }
      var co = avg('carbon_monoxide', 8);
      var conc = {
        pm25: avg('pm2_5', 24), pm10: avg('pm10', 24),
        no2: avg('nitrogen_dioxide', 24), so2: avg('sulphur_dioxide', 24),
        o3: avg('ozone', 8), co: co == null ? null : co / 1000 // µg/m³ → mg/m³
      };
      var base = {
        time: idx.length ? new Date(h.time[idx[idx.length - 1]] * 1000) : null,
        summary: '24h model average',
        conc: conc,
        detail: [
          { text: 'Model grid point', meta: round(j.latitude, 2) + ', ' + round(j.longitude, 2) },
          { text: 'PM2.5 (24h avg)', meta: round(conc.pm25, 1) + ' µg/m³' },
          { text: 'PM10 (24h avg)', meta: round(conc.pm10, 1) + ' µg/m³' }
        ],
        note: 'Regional estimate (~40 km grid); may smooth over local hotspots.'
      };
      return finish(base, subsFromConc(conc));
    });
  }

  function fetchWaqi(loc, key) {
    var url = 'https://api.waqi.info/feed/geo:' + loc.lat + ';' + loc.lon + '/?token=' + encodeURIComponent(key);
    return getJSON(url).then(function (j) {
      if (!j || j.status !== 'ok') throw new Error((j && j.data) || 'WAQI error');
      var d = j.data, iaqi = d.iaqi || {};
      var geo = (d.city && d.city.geo) || [];
      var dist = geo.length === 2 ? A.distanceKm(loc.lat, loc.lon, num(geo[0]), num(geo[1])) : null;
      var conc = {
        pm25: iaqi.pm25 ? A.usAqiToConc('pm25', num(iaqi.pm25.v)) : null,
        pm10: iaqi.pm10 ? A.usAqiToConc('pm10', num(iaqi.pm10.v)) : null
      };
      var attrib = (d.attributions || []).map(function (a) { return a.name; }).filter(Boolean);
      var govLinked = attrib.some(function (n) { return /CPCB|Central Pollution|Pollution Control|PCB/i.test(n); });
      var base = {
        time: d.time && d.time.iso ? new Date(d.time.iso) : null,
        summary: 'Nearest station',
        detail: [
          { text: (d.city && d.city.name) || 'Station', meta: dist != null ? round(dist, 1) + ' km' : '' },
          { text: 'WAQI headline (US scale)', meta: String(d.aqi) }
        ],
        note: govLinked ?
          'Republishes government station data, so it is a pipeline cross-check, not an independent measurement.' :
          'Values back-converted from the US scale (approximate).',
        far: dist != null && dist > FALLBACK_KM
      };
      if (attrib.length) base.detail.push({ text: 'Data from', meta: attrib.slice(0, 2).join(', ') });
      var subs = subsFromConc(conc);
      if (base.far) {
        base.status = 'empty';
        base.note = 'Nearest WAQI station is ' + round(dist) + ' km away, too far to compare.';
        return base;
      }
      return finish(base, subs);
    });
  }

  function fetchOpenAq(loc, key) {
    var H = { 'X-API-Key': key };
    var api = 'https://api.openaq.org/v3';
    var url = api + '/locations?coordinates=' + loc.lat + ',' + loc.lon + '&radius=' + (NEAR_KM * 1000) + '&limit=100';
    return getJSON(url, H).then(function (j) {
      var cutoff = Date.now() - 6 * 3600 * 1000;
      var locs = (j.results || []).filter(function (l) {
        var hasPm = (l.sensors || []).some(function (s) { return s.parameter && s.parameter.name === 'pm25'; });
        var last = l.datetimeLast && l.datetimeLast.utc ? Date.parse(l.datetimeLast.utc) : 0;
        return l.isMonitor === false && hasPm && last > cutoff;
      }).map(function (l) {
        l._dist = A.distanceKm(loc.lat, loc.lon, l.coordinates.latitude, l.coordinates.longitude);
        return l;
      }).sort(function (a, b) { return a._dist - b._dist; }).slice(0, 6);

      if (!locs.length) {
        return { status: 'empty', detail: [], note: 'No active citizen sensors within ' + NEAR_KM + ' km on OpenAQ.' };
      }

      return Promise.allSettled(locs.map(function (l) {
        return getJSON(api + '/locations/' + l.id + '/latest', H).then(function (lj) {
          var params = {};
          (l.sensors || []).forEach(function (s) { if (s.parameter) params[s.id] = s.parameter.name; });
          var conc = {}, latest = null;
          (lj.results || []).forEach(function (r) {
            var p = params[r.sensorsId];
            var t = r.datetime && r.datetime.utc ? new Date(r.datetime.utc) : null;
            if ((p === 'pm25' || p === 'pm10') && t && Date.now() - t < 3 * 3600 * 1000) {
              conc[p] = num(r.value);
              if (!latest || t > latest) latest = t;
            }
          });
          var subs = subsFromConc(conc), ov = A.overall(subs);
          return ov ? { loc: l, subs: subs, aqi: ov.aqi, time: latest } : null;
        });
      })).then(function (settled) {
        var ok = settled.map(function (s) { return s.status === 'fulfilled' ? s.value : null; }).filter(Boolean);
        if (!ok.length) return { status: 'empty', detail: [], note: 'Nearby sensors have no recent PM readings.' };
        var base = {
          time: ok.reduce(function (t, s) { return !t || s.time > t ? s.time : t; }, null),
          summary: ok.length === 1 ? '1 sensor' : 'Median of ' + ok.length + ' sensors',
          detail: ok.map(function (s) {
            var who = (s.loc.provider && s.loc.provider.name) || '';
            return { text: s.loc.name || ('Sensor ' + s.loc.id), meta: round(s.loc._dist, 1) + ' km · AQI ' + s.aqi + (who ? ' · ' + who : '') };
          }),
          note: 'Latest readings, not 24h averages. Low-cost sensors can read high in humid air.'
        };
        var res = finish(base, medianSubs(ok.map(function (s) { return s.subs; })));
        res.aqi = Math.round(A.median(ok.map(function (s) { return s.aqi; })));
        return res;
      });
    });
  }

  // ---------- rendering ----------

  function catOf(aqi) { return A.category(aqi) || { name: '-', key: 'none' }; }

  function chip(aqi) {
    if (aqi == null) return '<span class="chip none">-</span>';
    var c = catOf(aqi);
    return '<span class="chip ' + c.key + '" title="' + c.name + '">' + aqi + '</span>';
  }

  function pollLabel(id) {
    var p = A.POLLUTANTS.filter(function (x) { return x.id === id; })[0];
    return p ? p.label : id;
  }

  function renderLegend() {
    var prev = 0;
    $('legend').innerHTML = A.CATEGORIES.map(function (c) {
      var li = '<li><span class="sw ' + c.key + '"></span>' + c.name + ' <span class="muted">' + (prev === 0 ? 0 : prev + 1) + '–' + c.max + '</span></li>';
      prev = c.max;
      return li;
    }).join('');
  }

  function renderVerdict(loc, results) {
    var ok = results.filter(function (r) { return r.status === 'ok'; });
    var pending = results.some(function (r) { return r.status === 'loading'; });
    var off = results.filter(function (r) { return r.src.official; })[0];
    var ag = A.agreement(ok.map(function (r) { return { aqi: r.aqi, official: r.src.official }; }));

    var html = '<div class="verdict-head"><div><p class="eyebrow">' + esc(loc.name) + '</p>';
    var headline = off && off.status === 'ok' ? off : ok[0];
    if (headline) {
      var c = catOf(headline.aqi);
      html += '<div class="big"><span class="big-num ' + c.key + '">' + headline.aqi + '</span>' +
        '<span class="big-cat">' + c.name + '<small>' + esc(headline.src.official ? 'Official CPCB AQI' : headline.src.name) + '</small></span></div>';
    } else {
      html += '<div class="big"><span class="big-num none">' + (pending ? '…' : '-') + '</span></div>';
    }
    html += '</div>';

    if (ag) {
      html += '<div class="agree ' + ag.level.toLowerCase() + '"><span class="agree-label">Agreement</span><strong>' + ag.level + '</strong>' +
        '<span class="muted small">' + ag.count + ' sources · range ' + ag.lo + '–' + ag.hi + '</span></div>';
    }
    html += '</div>';

    var msg;
    if (ag && ag.gap && ag.gap.pct != null) {
      var p = ag.gap.pct;
      if (p >= 25) msg = 'Independent sources read <strong>' + p + '% higher</strong> than the official figure (' + Math.round(ag.gap.independent) + ' vs ' + Math.round(ag.gap.official) + ').';
      else if (p <= -25) msg = 'Independent sources read <strong>' + Math.abs(p) + '% lower</strong> than the official figure (' + Math.round(ag.gap.independent) + ' vs ' + Math.round(ag.gap.official) + ').';
      else msg = 'Independent sources broadly <strong>match</strong> the official figure (within ' + Math.abs(p) + '%).';
    } else if (off && off.status === 'nokey') {
      msg = 'Add a free data.gov.in key under <button class="link" data-open-settings>API keys</button> to compare against the official CPCB reading.';
    } else if (pending) {
      msg = 'Checking sources…';
    } else if (!ok.length) {
      msg = 'No source returned data for this location right now.';
    }
    if (msg) html += '<p class="verdict-msg">' + msg + '</p>';
    $('verdict').innerHTML = html;
  }

  function renderScale(results) {
    var ok = results.filter(function (r) { return r.status === 'ok'; });
    if (!ok.length) { $('scale').innerHTML = '<p class="muted">Waiting for data…</p>'; return; }
    $('scale').innerHTML = ok.map(function (r) {
      var pct = Math.min(100, r.aqi / 500 * 100);
      var c = catOf(r.aqi);
      return '<div class="scale-row"><span class="scale-label">' + esc(r.src.name) + '</span>' +
        '<div class="track"><span class="marker ' + c.key + (r.src.official ? ' official' : '') + '" style="left:' + pct + '%">' + r.aqi + '</span></div></div>';
    }).join('') + '<div class="scale-row axis"><span class="scale-label"></span><div class="ticks"><span>0</span><span>100</span><span>200</span><span>300</span><span>400</span><span>500</span></div></div>';
  }

  function renderSources(results) {
    $('sources').innerHTML = results.map(function (r) {
      var s = r.src;
      var body;
      if (r.status === 'loading') body = '<p class="muted">Loading…</p>';
      else if (r.status === 'nokey') body = '<p class="muted">Needs a free API key.</p><button class="ghost small-btn" data-open-settings>Add key</button>';
      else if (r.status === 'error') body = '<p class="err">Couldn’t load: ' + esc(r.error) + '</p>';
      else {
        var c = catOf(r.aqi);
        body = (r.status === 'ok' ?
          '<div class="src-aqi"><span class="chip lg ' + c.key + '">' + r.aqi + '</span><span>' + c.name +
          '<small class="muted">' + esc(r.summary || '') + (r.dominant ? ' · led by ' + pollLabel(r.dominant) : '') + '</small></span></div>' :
          '<p class="muted">No comparable reading.</p>') +
          (r.detail && r.detail.length ? '<ul class="detail">' + r.detail.map(function (d) {
            return '<li><span>' + esc(d.text) + '</span><span class="muted">' + esc(d.meta) + '</span></li>';
          }).join('') + '</ul>' : '') +
          (r.note ? '<p class="note">' + esc(r.note) + '</p>' : '') +
          (r.time ? '<p class="time">Updated ' + ago(r.time) + '</p>' : '');
      }
      return '<article class="card src' + (s.official ? ' is-official' : '') + '"><header><h3>' + esc(s.name) + '</h3>' +
        '<span class="pill">' + esc(s.kind) + '</span></header>' + body + '</article>';
    }).join('');
  }

  function renderTable(results) {
    var ok = results.filter(function (r) { return r.status === 'ok'; });
    if (!ok.length) { $('pollutants').innerHTML = '<tr><td class="muted">Waiting for data…</td></tr>'; return; }
    var rows = A.POLLUTANTS.filter(function (p) {
      return ok.some(function (r) { return r.subs && r.subs[p.id] != null; });
    });
    var head = '<thead><tr><th>Pollutant</th>' + ok.map(function (r) { return '<th>' + esc(r.src.name) + '</th>'; }).join('') + '</tr></thead>';
    var body = '<tbody>' + rows.map(function (p) {
      return '<tr><th scope="row">' + p.label + ' <span class="muted small">' + p.avg + '</span></th>' +
        ok.map(function (r) { return '<td>' + chip(r.subs[p.id]) + '</td>'; }).join('') + '</tr>';
    }).join('') + '</tbody>';
    $('pollutants').innerHTML = head + body;
  }

  function renderAll(loc, results) {
    renderVerdict(loc, results);
    renderScale(results);
    renderSources(results);
    renderTable(results);
  }

  // ---------- control flow ----------

  var current = null;
  var runId = 0;

  function keys() {
    return { cpcb: store('aqi.key.cpcb') || '', waqi: store('aqi.key.waqi') || '', openaq: store('aqi.key.openaq') || '' };
  }

  function load(loc) {
    current = loc;
    var my = ++runId;
    var k = keys();
    var results = SOURCES.map(function (src) {
      return { src: src, status: src.keyName && !k[src.keyName] ? 'nokey' : 'loading' };
    });
    renderAll(loc, results);

    results.forEach(function (r, i) {
      if (r.status !== 'loading') return;
      Promise.resolve()
        .then(function () { return r.src.fetch(loc, k[r.src.keyName]); })
        .then(function (data) { results[i] = Object.assign({ src: r.src }, data); })
        .catch(function (e) { results[i] = { src: r.src, status: 'error', error: e.message || String(e) }; })
        .then(function () { if (my === runId) renderAll(loc, results); });
    });
  }

  function initCities() {
    var sel = $('citySelect');
    sel.innerHTML = CITIES.map(function (c, i) { return '<option value="' + i + '">' + c.name + '</option>'; }).join('') +
      '<option value="me" hidden>My location</option>';
    var want = new URLSearchParams(location.search).get('city') || store('aqi.city') || 'Delhi';
    var idx = CITIES.findIndex(function (c) { return c.name.toLowerCase() === want.toLowerCase(); });
    sel.value = String(idx < 0 ? 0 : idx);
    sel.addEventListener('change', function () {
      if (sel.value === 'me') return;
      var c = CITIES[+sel.value];
      store('aqi.city', c.name);
      load(c);
    });
    load(CITIES[+sel.value]);
  }

  function initLocate() {
    var btn = $('locateBtn');
    if (!navigator.geolocation) { btn.hidden = true; return; }
    btn.addEventListener('click', function () {
      btn.disabled = true; btn.textContent = 'Locating…';
      navigator.geolocation.getCurrentPosition(function (pos) {
        btn.disabled = false; btn.textContent = 'Use my location';
        $('citySelect').value = 'me';
        load({ name: 'Your location', lat: round(pos.coords.latitude, 4), lon: round(pos.coords.longitude, 4) });
      }, function (err) {
        btn.disabled = false; btn.textContent = 'Use my location';
        alert('Couldn’t get your location: ' + err.message);
      }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    });
  }

  function initSettings() {
    var dlg = $('settings');
    function open() {
      var k = keys();
      $('key-cpcb').value = k.cpcb; $('key-waqi').value = k.waqi; $('key-openaq').value = k.openaq;
      dlg.showModal();
    }
    $('settingsBtn').addEventListener('click', open);
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-open-settings]')) open();
    });
    dlg.addEventListener('close', function () {
      if (dlg.returnValue !== 'save') return;
      store('aqi.key.cpcb', $('key-cpcb').value.trim());
      store('aqi.key.waqi', $('key-waqi').value.trim());
      store('aqi.key.openaq', $('key-openaq').value.trim());
      cpcbCache = null;
      if (current) load(current);
    });
  }

  $('refreshBtn').addEventListener('click', function () { cpcbCache = null; if (current) load(current); });
  renderLegend();
  initSettings();
  initLocate();
  initCities();
})();
