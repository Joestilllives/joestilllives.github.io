/*
 * Data sources for Clear Air Check. Shared by the web page (live checks)
 * and scripts/collect-aqi.js (the hourly GitHub Actions collector).
 * Needs AQI (aqi.js) and fetch on the global object.
 */
(function (root) {
  'use strict';
  var A = root.AQI;

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

  var SOURCES = [
    { id: 'cpcb', name: 'CPCB (government)', short: 'Govt', kind: 'What the government reports', official: true, keyName: 'cpcb' },
    { id: 'cams', name: 'Open-Meteo · CAMS', short: 'Satellite', kind: 'Independent · satellite model (EU Copernicus)', official: false, independent: true },
    { id: 'waqi', name: 'WAQI (aqicn.org)', short: 'WAQI', kind: 'Relays government stations · not counted', official: false, relay: true, keyName: 'waqi' },
    { id: 'openaq', name: 'Citizen sensors · OpenAQ', short: 'Citizens', kind: 'Independent · citizen sensors', official: false, independent: true, keyName: 'openaq', serverOnly: true }
  ];

  // ---------- helpers ----------

  function num(v) {
    var n = typeof v === 'number' ? v : parseFloat(v);
    return isFinite(n) ? n : null;
  }

  function round(v, d) {
    if (v == null) return null;
    var f = Math.pow(10, d || 0);
    return Math.round(v * f) / f;
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function getJSON(url, headers) {
    var ctl = new AbortController();
    var t = setTimeout(function () { ctl.abort(); }, 25000);
    return fetch(url, { headers: headers || {}, signal: ctl.signal })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .catch(function (e) {
        if (e.name === 'AbortError') throw new Error('request timed out');
        if (e instanceof TypeError) throw new Error('blocked or unreachable (network or CORS)');
        throw e;
      })
      .finally(function () { clearTimeout(t); });
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

  function latestOf(items) {
    return items.reduce(function (t, s) { return s.time && (!t || s.time > t) ? s.time : t; }, null);
  }

  // ---------- CPCB (official, via data.gov.in) ----------
  // The feed's min/max/avg values are CPCB pollutant sub-indices, not concentrations.

  var CPCB_RESOURCE = '3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69';
  var CPCB_POLL = { 'PM2.5': 'pm25', 'PM10': 'pm10', 'NO2': 'no2', 'SO2': 'so2', 'CO': 'co', 'OZONE': 'o3', 'NH3': 'nh3' };
  var cpcbCache = null;

  function parseCpcbTime(s) {
    var m = /^(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})/.exec(s || '');
    if (!m) return null;
    return new Date(m[3] + '-' + m[2] + '-' + m[1] + 'T' + m[4] + ':' + m[5] + ':00+05:30');
  }

  function cpcbRecords(key) {
    if (cpcbCache && Date.now() - cpcbCache.t < 10 * 60000) return Promise.resolve(cpcbCache.records);
    return getJSON('https://api.data.gov.in/resource/' + CPCB_RESOURCE +
      '?api-key=' + encodeURIComponent(key) + '&format=json&limit=5000')
      .then(function (j) {
        if (!j || !Array.isArray(j.records)) throw new Error((j && j.message) || 'unexpected response');
        cpcbCache = { t: Date.now(), records: j.records };
        return j.records;
      });
  }

  function fetchCpcb(loc, key) {
    return cpcbRecords(key).then(function (records) {
      var byStation = {};
      records.forEach(function (r) {
        var lat = num(r.latitude), lon = num(r.longitude);
        var pid = CPCB_POLL[String(r.pollutant_id || '').toUpperCase()];
        var val = num(r.avg_value != null ? r.avg_value : r.pollutant_avg);
        if (lat == null || lon == null || !pid) return;
        var st = byStation[r.station] || (byStation[r.station] = {
          name: r.station, subs: {}, time: parseCpcbTime(r.last_update),
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
      if (!near.length) return { status: 'empty', detail: [], note: 'No official station within ' + FALLBACK_KM + ' km.' };

      var base = {
        time: latestOf(near),
        summary: near.length === 1 ? '1 station' : 'Median of ' + near.length + ' stations',
        detail: near.slice(0, 8).map(function (s) {
          return { text: s.name, meta: round(s.dist, 1) + ' km · AQI ' + s.aqi };
        })
      };
      if (near.length > 8) base.detail.push({ text: '+ ' + (near.length - 8) + ' more stations', meta: '' });
      var res = finish(base, medianSubs(near.map(function (s) { return s.subs; })));
      res.aqi = Math.round(A.median(near.map(function (s) { return s.aqi; })));
      return res;
    });
  }

  // ---------- Open-Meteo (Copernicus CAMS model) ----------

  function fetchCams(loc) {
    var url = 'https://air-quality-api.open-meteo.com/v1/air-quality?latitude=' + loc.lat + '&longitude=' + loc.lon +
      '&hourly=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone' +
      '&past_days=2&forecast_days=1&timeformat=unixtime';
    return getJSON(url).then(function (j) {
      var h = j && j.hourly;
      if (!h || !h.time) throw new Error('unexpected response');
      var now = Date.now() / 1000;
      var idx = [];
      h.time.forEach(function (t, i) { if (t <= now) idx.push(i); });
      function avg(field, hours, skip) {
        var arr = h[field] || [];
        var end = idx.length - (skip || 0);
        return A.mean(idx.slice(Math.max(0, end - hours), end).map(function (i) { return arr[i]; }));
      }
      var co = avg('carbon_monoxide', 8);
      var conc = {
        pm25: avg('pm2_5', 24), pm10: avg('pm10', 24),
        no2: avg('nitrogen_dioxide', 24), so2: avg('sulphur_dioxide', 24),
        o3: avg('ozone', 8), co: co == null ? null : co / 1000 // µg/m³ → mg/m³
      };
      // Latest hour vs. the 3 before it: is the air improving or worsening right now?
      var pmNow = avg('pm2_5', 1), pmPrev = avg('pm2_5', 3, 1);
      var nowAqi = A.subIndex('pm25', pmNow);
      var trend = pmNow == null || pmPrev == null ? '' :
        pmNow < pmPrev * 0.9 ? ' · improving ↓' : pmNow > pmPrev * 1.1 ? ' · worsening ↑' : ' · steady';
      var base = {
        time: idx.length ? new Date(h.time[idx[idx.length - 1]] * 1000) : null,
        summary: '24h model average',
        detail: [
          { text: 'Right now (PM2.5, latest hour)', meta: (nowAqi == null ? '-' : 'AQI ' + nowAqi + ' · ' + A.category(nowAqi).name) + trend },
          { text: 'PM2.5 (24h avg)', meta: round(conc.pm25, 1) + ' µg/m³' },
          { text: 'PM10 (24h avg)', meta: round(conc.pm10, 1) + ' µg/m³' },
          { text: 'Model grid point', meta: round(j.latitude, 2) + ', ' + round(j.longitude, 2) }
        ],
        note: 'Regional estimate (~40 km grid); may smooth over local hotspots.'
      };
      return finish(base, subsFromConc(conc));
    });
  }

  // ---------- WAQI (aqicn.org) ----------
  // Sub-indices are on the US scale; PM values are back-converted to concentrations.

  function parseWaqiFeed(d, loc) {
    var iaqi = d.iaqi || {};
    var geo = (d.city && d.city.geo) || [];
    var conc = {
      pm25: iaqi.pm25 ? A.usAqiToConc('pm25', num(iaqi.pm25.v)) : null,
      pm10: iaqi.pm10 ? A.usAqiToConc('pm10', num(iaqi.pm10.v)) : null
    };
    var subs = subsFromConc(conc), ov = A.overall(subs);
    return {
      name: (d.city && d.city.name) || 'Station',
      dist: geo.length === 2 ? A.distanceKm(loc.lat, loc.lon, num(geo[0]), num(geo[1])) : null,
      subs: subs, aqi: ov ? ov.aqi : null,
      time: d.time && d.time.iso ? new Date(d.time.iso) : null,
      attrib: (d.attributions || []).map(function (a) { return a.name; }).filter(Boolean)
    };
  }

  function fetchWaqi(loc, key) {
    var tok = '?token=' + encodeURIComponent(key);
    var d = 0.25; // ~25 km box
    var box = (loc.lat - d) + ',' + (loc.lon - d) + ',' + (loc.lat + d) + ',' + (loc.lon + d);
    return getJSON('https://api.waqi.info/v2/map/bounds' + tok + '&latlng=' + box + '&networks=all')
      .then(function (j) {
        if (!j || j.status !== 'ok') throw new Error((j && j.data) || 'WAQI error');
        var uids = (j.data || [])
          .filter(function (s) { return num(s.aqi) != null; })
          .map(function (s) { return { uid: s.uid, dist: A.distanceKm(loc.lat, loc.lon, s.lat, s.lon) }; })
          .filter(function (s) { return s.dist <= NEAR_KM; })
          .sort(function (a, b) { return a.dist - b.dist; })
          .slice(0, 5)
          .map(function (s) { return '@' + s.uid; });
        if (!uids.length) uids = ['geo:' + loc.lat + ';' + loc.lon]; // nearest station anywhere
        return Promise.allSettled(uids.map(function (u) {
          return getJSON('https://api.waqi.info/feed/' + u + '/' + tok).then(function (f) {
            if (!f || f.status !== 'ok') throw new Error('feed error');
            return parseWaqiFeed(f.data, loc);
          });
        }));
      })
      .then(function (settled) {
        var st = settled.filter(function (s) { return s.status === 'fulfilled'; }).map(function (s) { return s.value; });
        var ok = st.filter(function (s) { return s.aqi != null && s.dist != null && s.dist <= FALLBACK_KM; });
        if (!ok.length) {
          var far = st.filter(function (s) { return s.dist != null; })[0];
          return { status: 'empty', detail: [], note: far ? 'Nearest WAQI station is ' + round(far.dist) + ' km away, too far to compare.' : 'No WAQI station data nearby.' };
        }
        ok.sort(function (a, b) { return a.dist - b.dist; });
        var attrib = [];
        ok.forEach(function (s) { s.attrib.forEach(function (a) { if (attrib.indexOf(a) < 0) attrib.push(a); }); });
        var govLinked = attrib.some(function (n) { return /CPCB|Central Pollution|Pollution Control|PCB/i.test(n); });
        var base = {
          time: latestOf(ok),
          summary: ok.length === 1 ? '1 station' : 'Median of ' + ok.length + ' stations',
          detail: ok.map(function (s) { return { text: s.name, meta: round(s.dist, 1) + ' km · AQI ' + s.aqi }; }),
          note: (govLinked ?
            'Mostly republishes government station data: a pipeline cross-check, not an independent measurement. ' : '') +
            'Values back-converted from the US scale (approximate).'
        };
        var res = finish(base, medianSubs(ok.map(function (s) { return s.subs; })));
        res.aqi = Math.round(A.median(ok.map(function (s) { return s.aqi; })));
        return res;
      });
  }

  // ---------- OpenAQ (citizen low-cost sensors) ----------
  // OpenAQ does not allow browser (CORS) requests, so this runs in the collector only.

  function fetchOpenAq(loc, key, opts) {
    var pause = (opts && opts.pause) || 0;
    var H = { 'X-API-Key': key };
    var api = 'https://api.openaq.org/v3';
    var url = api + '/locations?coordinates=' + loc.lat + ',' + loc.lon + '&radius=' + (NEAR_KM * 1000) + '&limit=100';
    return getJSON(url, H).then(function (j) {
      var cutoff = Date.now() - 6 * 3600 * 1000;
      var locs = (j.results || []).filter(function (l) {
        var hasPm = (l.sensors || []).some(function (s) { return s.parameter && s.parameter.name === 'pm25'; });
        var last = l.datetimeLast && l.datetimeLast.utc ? Date.parse(l.datetimeLast.utc) : 0;
        return l.isMonitor === false && hasPm && last > cutoff && l.coordinates;
      }).map(function (l) {
        l._dist = A.distanceKm(loc.lat, loc.lon, l.coordinates.latitude, l.coordinates.longitude);
        return l;
      }).sort(function (a, b) { return a._dist - b._dist; }).slice(0, 6);

      if (!locs.length) return { status: 'empty', detail: [], note: 'No active citizen sensors within ' + NEAR_KM + ' km on OpenAQ.' };

      // Sequential with a pause, to stay inside OpenAQ's rate limit.
      var out = [];
      return locs.reduce(function (p, l) {
        return p.then(function () { return sleep(pause); })
          .then(function () { return getJSON(api + '/locations/' + l.id + '/latest', H); })
          .then(function (lj) {
            var params = {};
            (l.sensors || []).forEach(function (s) { if (s.parameter) params[s.id] = s.parameter.name; });
            var conc = {}, latest = null;
            (lj.results || []).forEach(function (r) {
              var pn = params[r.sensorsId];
              var t = r.datetime && r.datetime.utc ? new Date(r.datetime.utc) : null;
              if ((pn === 'pm25' || pn === 'pm10') && t && Date.now() - t < 3 * 3600 * 1000) {
                conc[pn] = num(r.value);
                if (!latest || t > latest) latest = t;
              }
            });
            var subs = subsFromConc(conc), ov = A.overall(subs);
            if (ov) out.push({ loc: l, subs: subs, aqi: ov.aqi, time: latest });
          }, function () { /* skip one failing sensor */ });
      }, Promise.resolve()).then(function () {
        if (!out.length) return { status: 'empty', detail: [], note: 'Nearby sensors have no recent PM readings.' };
        var base = {
          time: latestOf(out),
          summary: out.length === 1 ? '1 sensor' : 'Median of ' + out.length + ' sensors',
          detail: out.map(function (s) {
            var who = (s.loc.provider && s.loc.provider.name) || '';
            return { text: s.loc.name || ('Sensor ' + s.loc.id), meta: round(s.loc._dist, 1) + ' km · AQI ' + s.aqi + (who ? ' · ' + who : '') };
          }),
          note: 'Latest readings, not 24h averages. Low-cost sensors can read high in humid air.'
        };
        var res = finish(base, medianSubs(out.map(function (s) { return s.subs; })));
        res.aqi = Math.round(A.median(out.map(function (s) { return s.aqi; })));
        return res;
      });
    });
  }

  root.AQSources = {
    CITIES: CITIES, SOURCES: SOURCES, NEAR_KM: NEAR_KM,
    fetchers: { cpcb: fetchCpcb, cams: fetchCams, waqi: fetchWaqi, openaq: fetchOpenAq },
    clearCache: function () { cpcbCache = null; }
  };
})(typeof window !== 'undefined' ? window : globalThis);
