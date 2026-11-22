/* Clear Air Check: page logic. Uses hourly collected data when fresh, else checks live. */
(function () {
  'use strict';
  var A = window.AQI, S = window.AQSources;
  var SOURCES = S.SOURCES, CITIES = S.CITIES;
  var STALE_HOURS = 3;     // older collected data than this triggers a live check
  var HISTORY_DAYS = 7;

  // ---------- helpers ----------
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

  function ago(date) {
    if (!date || isNaN(date)) return 'time unknown';
    var mins = Math.round((Date.now() - date.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    var h = Math.round(mins / 60);
    if (h < 48) return h + ' h ago';
    return Math.round(h / 24) + ' days ago';
  }

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

  function srcById(id) { return SOURCES.filter(function (s) { return s.id === id; })[0]; }

  // ---------- rendering: current readings ----------

  function renderLegend() {
    var prev = -1;
    $('legend').innerHTML = A.CATEGORIES.map(function (c) {
      var li = '<li><span class="sw ' + c.key + '"></span>' + c.name + ' <span class="muted">' + (prev + 1) + '–' + c.max + '</span></li>';
      prev = c.max;
      return li;
    }).join('');
  }

  function renderVerdict(loc, results) {
    var ok = results.filter(function (r) { return r.status === 'ok'; });
    var pending = results.some(function (r) { return r.status === 'loading'; });
    var off = results.filter(function (r) { return r.src.official && r.status === 'ok'; })[0];
    var ind = ok.filter(function (r) { return r.src.independent; });
    var indAqi = ind.length ? Math.round(A.median(ind.map(function (r) { return r.aqi; }))) : null;
    var agInd = A.agreement(ind.map(function (r) { return { aqi: r.aqi }; }));

    // Headline = the independent (non-government) estimate. Government figure sits beside it.
    var html = '<div class="verdict-head"><div><p class="eyebrow">' + esc(loc.name) + ' · Independent estimate</p>';
    if (indAqi != null) {
      var c = catOf(indAqi);
      html += '<div class="big"><span class="big-num ' + c.key + '">' + indAqi + '</span>' +
        '<span class="big-cat">' + c.name + '<small>From ' + ind.length + ' non-government source' + (ind.length > 1 ? 's' : '') +
        (agInd ? ' · ' + agInd.level.toLowerCase() + ' agreement' : '') + '</small></span></div>';
    } else {
      html += '<div class="big"><span class="big-num none">' + (pending ? '…' : '-') + '</span></div>';
    }
    html += '</div>';
    if (off) {
      var oc = catOf(off.aqi);
      html += '<div class="agree"><span class="agree-label">Government says</span><strong><span class="chip ' + oc.key + '">' + off.aqi + '</span> ' + oc.name + '</strong>' +
        '<span class="muted small">CPCB official AQI</span></div>';
    }
    html += '</div>';

    var msg;
    if (off && indAqi != null && off.aqi > 0) {
      var p = Math.round((indAqi - off.aqi) / off.aqi * 100);
      if (p >= 25) msg = 'The government figure is <strong>' + Math.round((1 - off.aqi / indAqi) * 100) + '% lower</strong> than what independent sources measure (' + off.aqi + ' vs ' + indAqi + ').';
      else if (p <= -25) msg = 'The government figure is <strong>higher</strong> than independent sources (' + off.aqi + ' vs ' + indAqi + ').';
      else msg = 'The government figure broadly <strong>matches</strong> independent sources (within ' + Math.abs(p) + '%).';
      if (catOf(off.aqi).key !== catOf(indAqi).key) msg += ' That puts it in a different health category: <strong>' + catOf(off.aqi).name + '</strong> instead of <strong>' + catOf(indAqi).name + '</strong>.';
    } else if (indAqi != null && !off && !pending) {
      msg = 'The government (CPCB) reading isn’t available right now, so there’s nothing to compare against yet.';
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

  function sourceBody(r, mode) {
    if (r.status === 'loading') return '<p class="muted">Loading…</p>';
    if (r.status === 'serveronly') return '<p class="muted">Collected hourly by the site’s server. OpenAQ doesn’t allow live checks from a browser.</p>';
    if (r.status === 'nokey') {
      return mode === 'snapshot' ?
        '<p class="muted">Not set up on the hourly collector yet.</p>' :
        '<p class="muted">Needs a free API key for live checks.</p><button class="ghost small-btn" data-open-settings>Add key</button>';
    }
    if (r.status === 'error') return '<p class="err">Couldn’t load: ' + esc(r.error) + '</p>';
    var c = catOf(r.aqi);
    return (r.status === 'ok' ?
      '<div class="src-aqi"><span class="chip lg ' + c.key + '">' + r.aqi + '</span><span>' + c.name +
      '<small class="muted">' + esc(r.summary || '') + (r.dominant ? ' · led by ' + pollLabel(r.dominant) : '') + '</small></span></div>' :
      '<p class="muted">No comparable reading.</p>') +
      (r.detail && r.detail.length ? '<ul class="detail">' + r.detail.map(function (d) {
        return '<li><span>' + esc(d.text) + '</span><span class="muted">' + esc(d.meta) + '</span></li>';
      }).join('') + '</ul>' : '') +
      (r.note ? '<p class="note">' + esc(r.note) + '</p>' : '') +
      (r.time ? '<p class="time">Reading from ' + ago(r.time) + '</p>' : '');
  }

  function renderSources(results, mode) {
    $('sources').innerHTML = results.map(function (r) {
      var s = r.src;
      return '<article class="card src' + (s.official ? ' is-official' : '') + '"><header><h3><span class="dot s-' + s.id + '"></span>' + esc(s.name) + '</h3>' +
        '<span class="pill">' + esc(s.kind) + '</span></header>' + sourceBody(r, mode) + '</article>';
    }).join('');
  }

  function renderTable(results) {
    var ok = results.filter(function (r) { return r.status === 'ok'; });
    if (!ok.length) { $('pollutants').innerHTML = '<tr><td class="muted">Waiting for data…</td></tr>'; return; }
    var rows = A.POLLUTANTS.filter(function (p) {
      return ok.some(function (r) { return r.subs && r.subs[p.id] != null; });
    });
    var head = '<thead><tr><th>Pollutant</th>' + ok.map(function (r) { return '<th>' + esc(r.src.short) + '</th>'; }).join('') + '</tr></thead>';
    var body = '<tbody>' + rows.map(function (p) {
      return '<tr><th scope="row">' + p.label + ' <span class="muted small">' + p.avg + '</span></th>' +
        ok.map(function (r) { return '<td>' + chip(r.subs[p.id]) + '</td>'; }).join('') + '</tr>';
    }).join('') + '</tbody>';
    $('pollutants').innerHTML = head + body;
  }

  function renderAll(loc, results, mode) {
    renderVerdict(loc, results);
    renderScale(results);
    renderSources(results, mode);
    renderTable(results);
  }

  // ---------- history (collected hourly) ----------

  var monthCache = {};

  function loadMonth(ym) {
    if (!monthCache[ym]) {
      monthCache[ym] = fetch('data/history/' + ym + '.csv?h=' + Math.floor(Date.now() / 3600000))
        .then(function (r) { return r.ok ? r.text() : ''; })
        .catch(function () { return ''; })
        .then(function (txt) {
          var lines = txt.trim().split('\n');
          var cols = (lines.shift() || '').split(',');
          return lines.filter(Boolean).map(function (l) {
            var v = l.split(','), row = { time: new Date(v[0].replace('Z', ':00Z')), city: v[1] };
            for (var i = 2; i < cols.length; i++) row[cols[i]] = v[i] === '' || v[i] == null ? null : +v[i];
            return row;
          });
        });
    }
    return monthCache[ym];
  }

  function loadHistory(cityName) {
    var now = new Date(), from = new Date(now.getTime() - HISTORY_DAYS * 86400000);
    var months = [from.toISOString().slice(0, 7)];
    if (now.toISOString().slice(0, 7) !== months[0]) months.push(now.toISOString().slice(0, 7));
    return Promise.all(months.map(loadMonth)).then(function (parts) {
      return [].concat.apply([], parts).filter(function (r) {
        return r.city === cityName && r.time >= from;
      }).sort(function (a, b) { return a.time - b.time; });
    });
  }

  function gapSummary(rows, cityName) {
    var gaps = [];
    rows.forEach(function (r) {
      if (r.cpcb == null || r.cpcb <= 0) return;
      var ind = A.median(SOURCES.filter(function (s) { return s.independent; }).map(function (s) { return r[s.id]; }));
      if (ind != null) gaps.push((ind - r.cpcb) / r.cpcb * 100);
    });
    if (!rows.length) return 'History builds up hour by hour once the collector is running.';
    if (gaps.length < 6) return 'The official vs. independent comparison appears here once CPCB data has been collected for a few hours.';
    var avg = Math.round(A.mean(gaps));
    var higherShare = Math.round(gaps.filter(function (g) { return g > 0; }).length / gaps.length * 100);
    var dir = avg >= 0 ? '<strong>' + avg + '% higher</strong>' : '<strong>' + Math.abs(avg) + '% lower</strong>';
    return 'Over the last ' + gaps.length + ' hours in ' + esc(cityName) + ', non-government sources read on average ' + dir +
      ' than the government (CPCB) figure, and higher in ' + higherShare + '% of hours.';
  }

  function renderHistory(rows, cityName) {
    $('gapStat').innerHTML = gapSummary(rows, cityName);
    var el = $('history');
    var series = SOURCES.filter(function (s) { return rows.some(function (r) { return r[s.id] != null; }); });
    if (rows.length < 2 || !series.length) { el.innerHTML = ''; $('historyLegend').innerHTML = ''; return; }

    // Draw at the container's real width so labels stay readable on phones.
    var W = Math.max(320, Math.min(760, el.clientWidth || 720)), H = W < 500 ? 220 : 240, L = 34, R = 8, T = 8, B = 24;
    var t1 = Date.now(), t0 = t1 - HISTORY_DAYS * 86400000;
    var maxV = 0;
    rows.forEach(function (r) { series.forEach(function (s) { if (r[s.id] > maxV) maxV = r[s.id]; }); });
    var yMax = Math.min(500, Math.max(200, Math.ceil((maxV + 30) / 100) * 100));
    var x = function (t) { return L + (t - t0) / (t1 - t0) * (W - L - R); };
    var y = function (v) { return T + (1 - v / yMax) * (H - T - B); };

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="AQI by source over the last ' + HISTORY_DAYS + ' days">';
    // category bands
    var lo = 0;
    A.CATEGORIES.forEach(function (c) {
      if (lo >= yMax) return;
      var hi = Math.min(c.max, yMax);
      svg += '<rect class="band ' + c.key + '" x="' + L + '" width="' + (W - L - R) + '" y="' + y(hi) + '" height="' + (y(lo) - y(hi)) + '"/>';
      lo = c.max;
    });
    // y grid + labels
    for (var v = 0; v <= yMax; v += 100) {
      svg += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/>' +
        '<text class="axis-t" x="' + (L - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + '</text>';
    }
    // day ticks
    for (var d = 0; d <= HISTORY_DAYS; d++) {
      var day = new Date(t0 + d * 86400000); day.setHours(0, 0, 0, 0);
      if (day.getTime() < t0) continue;
      svg += '<text class="axis-t" x="' + x(day.getTime()) + '" y="' + (H - 6) + '" text-anchor="middle">' +
        day.toLocaleDateString(undefined, { weekday: 'short' }) + '</text>';
    }
    // lines (break where more than 2h of data is missing)
    series.forEach(function (s) {
      var dPath = '', prev = null;
      rows.forEach(function (r) {
        if (r[s.id] == null) return;
        var t = r.time.getTime();
        dPath += (prev == null || t - prev > 2.5 * 3600000 ? 'M' : 'L') + x(t).toFixed(1) + ' ' + y(r[s.id]).toFixed(1);
        prev = t;
      });
      svg += '<path class="line s-' + s.id + (s.official ? ' official' : '') + '" d="' + dPath + '"/>';
    });
    svg += '<line id="hoverLine" class="hover-line" y1="' + T + '" y2="' + (H - B) + '" x1="-10" x2="-10"/>';
    svg += '<rect id="hoverZone" x="' + L + '" y="' + T + '" width="' + (W - L - R) + '" height="' + (H - T - B) + '" fill="transparent"/>';
    svg += '</svg><div id="hoverTip" class="hover-tip" hidden></div>';
    el.innerHTML = svg;

    $('historyLegend').innerHTML = series.map(function (s) {
      return '<li><span class="key s-' + s.id + (s.official ? ' official' : '') + '"></span>' + esc(s.name) + '</li>';
    }).join('');

    // hover / touch readout
    var svgEl = el.querySelector('svg'), tip = $('hoverTip'), line = $('hoverLine');
    function show(evt) {
      var pt = evt.touches ? evt.touches[0] : evt;
      var box = svgEl.getBoundingClientRect();
      var vx = (pt.clientX - box.left) / box.width * W;
      var t = t0 + (vx - L) / (W - L - R) * (t1 - t0);
      var best = null;
      rows.forEach(function (r) { if (!best || Math.abs(r.time - t) < Math.abs(best.time - t)) best = r; });
      if (!best) return;
      var px = x(best.time.getTime());
      line.setAttribute('x1', px); line.setAttribute('x2', px);
      tip.hidden = false;
      tip.innerHTML = '<strong>' + best.time.toLocaleString(undefined, { weekday: 'short', hour: 'numeric' }) + '</strong>' +
        series.map(function (s) { return '<span><i class="key s-' + s.id + '"></i>' + esc(s.short) + ' ' + (best[s.id] == null ? '-' : best[s.id]) + '</span>'; }).join('');
      var left = px / W * box.width;
      tip.style.left = Math.max(0, Math.min(box.width - tip.offsetWidth, left - tip.offsetWidth / 2)) + 'px';
    }
    function hide() { tip.hidden = true; line.setAttribute('x1', -10); line.setAttribute('x2', -10); }
    var zone = $('hoverZone');
    zone.addEventListener('mousemove', show);
    zone.addEventListener('touchstart', show, { passive: true });
    zone.addEventListener('touchmove', show, { passive: true });
    zone.addEventListener('mouseleave', hide);
  }

  // ---------- data flow ----------

  var snapshot = null, snapshotPromise = null;

  function loadSnapshot(force) {
    if (!snapshotPromise || force) {
      snapshotPromise = fetch('data/latest.json?h=' + (force ? Date.now() : Math.floor(Date.now() / 600000)))
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (j) { snapshot = j && j.cities ? j : null; return snapshot; });
    }
    return snapshotPromise;
  }

  function snapshotAge() {
    return snapshot ? (Date.now() - Date.parse(snapshot.generated)) / 3600000 : Infinity;
  }

  function keys() {
    return { cpcb: store('aqi.key.cpcb') || '', waqi: store('aqi.key.waqi') || '' };
  }

  var current = null, runId = 0;

  function setStatus(html) { $('dataStatus').innerHTML = html; }

  function showSnapshot(loc) {
    var c = snapshot.cities[loc.name];
    var results = SOURCES.map(function (src) {
      var r = Object.assign({ src: src }, c.sources[src.id] || { status: 'empty' });
      if (r.time) r.time = new Date(r.time);
      return r;
    });
    renderAll(loc, results, 'snapshot');
    setStatus('<span class="live-dot"></span>Collected hourly · updated ' + ago(new Date(snapshot.generated)) +
      ' · <button class="link" id="liveBtn" type="button">Check live now</button>');
  }

  function runLive(loc) {
    var my = ++runId;
    var k = keys();
    var results = SOURCES.map(function (src) {
      if (src.serverOnly) return { src: src, status: 'serveronly' };
      return { src: src, status: src.keyName && !k[src.keyName] ? 'nokey' : 'loading' };
    });
    renderAll(loc, results, 'live');
    setStatus('Live check from your browser' +
      (snapshot && snapshot.cities[loc.name] ? ' · hourly data is ' + ago(new Date(snapshot.generated)).replace(' ago', ' old') : ''));

    results.forEach(function (r, i) {
      if (r.status !== 'loading') return;
      Promise.resolve()
        .then(function () { return S.fetchers[r.src.id](loc, k[r.src.keyName]); })
        .then(function (data) { results[i] = Object.assign({ src: r.src }, data); })
        .catch(function (e) { results[i] = { src: r.src, status: 'error', error: e.message || String(e) }; })
        .then(function () { if (my === runId) renderAll(loc, results, 'live'); });
    });
  }

  function load(loc, opts) {
    current = loc;
    var my = ++runId;
    var isCity = CITIES.some(function (c) { return c.name === loc.name; });
    $('historyCard').hidden = !isCity;

    loadSnapshot(opts && opts.force).then(function () {
      if (my !== runId) return;
      var useSnap = !(opts && opts.live) && isCity && snapshot && snapshot.cities[loc.name] && snapshotAge() < STALE_HOURS;
      if (useSnap) showSnapshot(loc); else runLive(loc);
    });

    if (isCity) {
      loadHistory(loc.name).then(function (rows) { if (current === loc) renderHistory(rows, loc.name); });
    }
  }

  // ---------- controls ----------

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
      try { history.replaceState(null, '', '?city=' + encodeURIComponent(c.name)); } catch (e) { /* file:// */ }
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
        var r = function (v) { return Math.round(v * 1e4) / 1e4; };
        load({ name: 'Your location', lat: r(pos.coords.latitude), lon: r(pos.coords.longitude) }, { live: true });
      }, function (err) {
        btn.disabled = false; btn.textContent = 'Use my location';
        setStatus('Couldn’t get your location: ' + esc(err.message));
      }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    });
  }

  function initSettings() {
    var dlg = $('settings');
    function open() {
      var k = keys();
      $('key-cpcb').value = k.cpcb; $('key-waqi').value = k.waqi;
      dlg.showModal();
    }
    $('settingsBtn').addEventListener('click', open);
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-open-settings]')) open();
      if (e.target.id === 'liveBtn' && current) { S.clearCache(); load(current, { live: true }); }
    });
    dlg.addEventListener('close', function () {
      if (dlg.returnValue !== 'save') return;
      store('aqi.key.cpcb', $('key-cpcb').value.trim());
      store('aqi.key.waqi', $('key-waqi').value.trim());
      S.clearCache();
      if (current) load(current, { live: true });
    });
  }

  $('refreshBtn').addEventListener('click', function () { S.clearCache(); monthCache = {}; if (current) load(current, { force: true }); });
  renderLegend();
  initSettings();
  initLocate();
  initCities();
})();
