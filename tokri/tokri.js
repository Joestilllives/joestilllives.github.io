/* Tokri: the whole shop lives inside the link, so there is no server and nothing to store.
   Shop data (short keys keep links short):
   { n: name, t: tagline, p: whatsapp number (digits, with country code), e: emoji,
     c: theme colour, d: delivery fee (0 = free, -1 = pickup only), o: note to customers,
     i: [[item name, price, category, description], ...] }
   Encoded as "z" + base64url(deflate-raw(JSON)), or "j" + base64url(JSON) where
   CompressionStream is missing. */
var Tokri = (function () {
  function b64url(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function unb64url(str) {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) str += '=';
    var s = atob(str), out = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  }
  function pipe(bytes, stream) {
    return new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer().then(function (b) { return new Uint8Array(b); });
  }
  function encode(shop) {
    var raw = new TextEncoder().encode(JSON.stringify(shop));
    if (typeof CompressionStream === 'undefined') return Promise.resolve('j' + b64url(raw));
    return pipe(raw, new CompressionStream('deflate-raw')).then(function (z) { return 'z' + b64url(z); });
  }
  function decode(code) {
    try {
      var kind = code.charAt(0), bytes = unb64url(code.slice(1));
      var p = kind === 'z' ? pipe(bytes, new DecompressionStream('deflate-raw')) : Promise.resolve(bytes);
      return p.then(function (b) { return clean(JSON.parse(new TextDecoder().decode(b))); }).catch(function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }
  function str(v, max) { return typeof v === 'string' ? v.slice(0, max) : ''; }
  /* Never trust what comes in a link: keep only the fields and types we expect. */
  function clean(s) {
    if (!s || typeof s !== 'object') return null;
    var items = Array.isArray(s.i) ? s.i.slice(0, 200).map(function (it) {
      if (!Array.isArray(it)) return null;
      var price = Math.round(Number(it[1]) * 100) / 100;
      return [str(it[0], 80), isFinite(price) && price >= 0 ? price : 0, str(it[2], 30), str(it[3], 140)];
    }).filter(function (it) { return it && it[0]; }) : [];
    var color = /^#[0-9a-f]{6}$/i.test(s.c) ? s.c : '#e8577e';
    var d = Number(s.d);
    return {
      n: str(s.n, 60), t: str(s.t, 120), p: String(s.p || '').replace(/\D/g, '').slice(0, 15),
      e: str(s.e, 8), c: color, d: isFinite(d) ? Math.max(-1, Math.min(d, 100000)) : 0,
      o: str(s.o, 300), i: items
    };
  }
  function phone(input) {
    var d = String(input || '').replace(/\D/g, '');
    if (d.length === 11 && d.charAt(0) === '0') d = d.slice(1);
    if (d.length === 10) d = '91' + d;
    return d;
  }
  function money(n) {
    return '\u20b9' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
  /* "Chocolate cake - 650", "Brownies (box of 6) ₹360", "Samosa 20" -> [name, price] */
  function parseLine(line) {
    var m = String(line).trim().match(/^(.*?)[\s:\-–—=|,]*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)\s*(?:\/-|rs\.?|₹)?\s*$/i);
    if (!m || !m[1].trim()) return null;
    return [m[1].replace(/[\s:\-–—=|,₹]+$/, '').trim(), Number(m[2])];
  }
  return { encode: encode, decode: decode, clean: clean, phone: phone, money: money, parseLine: parseLine };
})();
