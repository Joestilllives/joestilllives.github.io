/* Indian National AQI maths (CPCB). Pure functions, no DOM. */
(function (root) {
  'use strict';

  // Index values at each breakpoint: Good, Satisfactory, Moderate, Poor, Very Poor, Severe.
  var IDX = [0, 50, 100, 200, 300, 400, 500];

  // CPCB concentration breakpoints. µg/m³ except CO (mg/m³).
  // The last value is the top of "Severe" used to scale up to 500.
  var IN_BP = {
    pm25: [0, 30, 60, 90, 120, 250, 380],
    pm10: [0, 50, 100, 250, 350, 430, 510],
    no2:  [0, 40, 80, 180, 280, 400, 800],
    o3:   [0, 50, 100, 168, 208, 748, 1000],
    co:   [0, 1, 2, 10, 17, 34, 50],
    so2:  [0, 40, 80, 380, 800, 1600, 2400],
    nh3:  [0, 200, 400, 800, 1200, 1800, 2400]
  };

  var POLLUTANTS = [
    { id: 'pm25', label: 'PM2.5', avg: '24h' },
    { id: 'pm10', label: 'PM10', avg: '24h' },
    { id: 'no2', label: 'NO₂', avg: '24h' },
    { id: 'o3', label: 'O₃', avg: '8h' },
    { id: 'co', label: 'CO', avg: '8h' },
    { id: 'so2', label: 'SO₂', avg: '24h' },
    { id: 'nh3', label: 'NH₃', avg: '24h' }
  ];

  var CATEGORIES = [
    { max: 50, name: 'Good', key: 'good' },
    { max: 100, name: 'Satisfactory', key: 'sat' },
    { max: 200, name: 'Moderate', key: 'mod' },
    { max: 300, name: 'Poor', key: 'poor' },
    { max: 400, name: 'Very Poor', key: 'vpoor' },
    { max: 500, name: 'Severe', key: 'severe' }
  ];

  function interp(x, xs, ys) {
    for (var i = 1; i < xs.length; i++) {
      if (x <= xs[i]) {
        return ys[i - 1] + (x - xs[i - 1]) * (ys[i] - ys[i - 1]) / (xs[i] - xs[i - 1]);
      }
    }
    return ys[ys.length - 1];
  }

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  /** Indian AQI sub-index for one pollutant concentration. */
  function subIndex(pollutant, conc) {
    var bp = IN_BP[pollutant];
    if (!bp || !isNum(conc) || conc < 0) return null;
    return Math.round(interp(conc, bp, IDX));
  }

  /**
   * Overall AQI from sub-indices {pm25: 120, no2: 40, ...}.
   * CPCB requires a PM reading; overall = max sub-index.
   */
  function overall(subs) {
    if (!subs || (!isNum(subs.pm25) && !isNum(subs.pm10))) return null;
    var best = null;
    Object.keys(subs).forEach(function (k) {
      var v = subs[k];
      if (isNum(v) && (!best || v > best.aqi)) best = { aqi: v, dominant: k };
    });
    return best;
  }

  function category(aqi) {
    if (!isNum(aqi)) return null;
    for (var i = 0; i < CATEGORIES.length; i++) if (aqi <= CATEGORIES[i].max) return CATEGORIES[i];
    return CATEGORIES[CATEGORIES.length - 1];
  }

  // US EPA (pre-2024) breakpoints, used by WAQI. Used only to back-convert to concentration.
  var US_IDX = [0, 50, 100, 150, 200, 300, 400, 500];
  var US_BP = {
    pm25: [0, 12, 35.4, 55.4, 150.4, 250.4, 350.4, 500.4],
    pm10: [0, 54, 154, 254, 354, 424, 504, 604]
  };

  /** Concentration from a US AQI sub-index (approximate inverse). */
  function usAqiToConc(pollutant, aqi) {
    var bp = US_BP[pollutant];
    if (!bp || !isNum(aqi) || aqi < 0) return null;
    return interp(aqi, US_IDX, bp);
  }

  function mean(arr) {
    var v = arr.filter(isNum);
    if (!v.length) return null;
    return v.reduce(function (a, b) { return a + b; }, 0) / v.length;
  }

  function median(arr) {
    var v = arr.filter(isNum).slice().sort(function (a, b) { return a - b; });
    if (!v.length) return null;
    var m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }

  /** Great-circle distance in km. */
  function distanceKm(lat1, lon1, lat2, lon2) {
    var R = 6371, toRad = Math.PI / 180;
    var dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  /**
   * How well do the sources agree?
   * values: [{aqi, official: bool}]
   */
  function agreement(values) {
    var all = values.filter(function (v) { return isNum(v.aqi); });
    if (all.length < 2) return null;
    var nums = all.map(function (v) { return v.aqi; });
    var lo = Math.min.apply(null, nums), hi = Math.max.apply(null, nums);
    var avg = mean(nums);
    var rel = avg > 0 ? (hi - lo) / avg : 0;
    var level = (rel <= 0.2 || hi - lo <= 15) ? 'High' : rel <= 0.4 ? 'Medium' : 'Low';

    var off = all.filter(function (v) { return v.official; }).map(function (v) { return v.aqi; });
    var ind = all.filter(function (v) { return !v.official; }).map(function (v) { return v.aqi; });
    var gap = null;
    if (off.length && ind.length) {
      var o = median(off), i = median(ind);
      gap = { official: o, independent: i, pct: o > 0 ? Math.round((i - o) / o * 100) : null };
    }
    return { level: level, spread: hi - lo, rel: rel, lo: lo, hi: hi, count: all.length, gap: gap };
  }

  root.AQI = {
    IN_BP: IN_BP, POLLUTANTS: POLLUTANTS, CATEGORIES: CATEGORIES,
    subIndex: subIndex, overall: overall, category: category,
    usAqiToConc: usAqiToConc, mean: mean, median: median,
    distanceKm: distanceKm, agreement: agreement
  };
})(typeof window !== 'undefined' ? window : globalThis);
