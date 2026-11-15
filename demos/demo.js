/* Shared helpers for the sample business sites.
   - Adds a "this is a sample" banner linking to /services/.
   - WhatsApp and call buttons show a preview instead of contacting anyone,
     because every business here is made up.
   - Demo.openStatus() shows "Open now / Closed" from a weekly schedule (India time). */
(function () {
  var css = '' +
    '.demo-bar{position:sticky;top:0;z-index:9999;display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;' +
    'padding:8px 16px;background:#020C24;color:#fff;font:600 14px/1.3 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;text-align:center}' +
    '.demo-bar a{color:#ffb43c;text-decoration:underline}' +
    '.demo-modal{position:fixed;inset:0;z-index:10000;display:none;align-items:center;justify-content:center;padding:16px;background:rgba(0,0,0,.55)}' +
    '.demo-modal.show{display:flex}' +
    '.demo-card{max-width:420px;width:100%;background:#fff;color:#1b1b1b;border-radius:16px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);' +
    'font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '.demo-card h3{margin:0 0 6px;font-size:18px}' +
    '.demo-card p{margin:0 0 12px;color:#555}' +
    '.demo-bubble{white-space:pre-wrap;background:#dcf8c6;border-radius:12px 12px 2px 12px;padding:12px 14px;margin:0 0 14px;color:#111;max-height:45vh;overflow:auto}' +
    '.demo-card button{width:100%;padding:12px;border:0;border-radius:10px;background:#020C24;color:#fff;font:600 15px system-ui,sans-serif;cursor:pointer}';
  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var bar = document.createElement('div');
  bar.className = 'demo-bar';
  bar.innerHTML = '<span>Sample website. This business is made up.</span><a href="/services/">Get one like this for your business &rarr;</a>';
  document.body.insertBefore(bar, document.body.firstChild);

  var modal = document.createElement('div');
  modal.className = 'demo-modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.innerHTML = '<div class="demo-card"><h3></h3><p></p><div class="demo-bubble"></div><button type="button">Got it</button></div>';
  document.body.appendChild(modal);
  var mTitle = modal.querySelector('h3'), mText = modal.querySelector('p'), mBubble = modal.querySelector('.demo-bubble');
  function close() { modal.classList.remove('show'); }
  modal.querySelector('button').addEventListener('click', close);
  modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

  function show(title, text, bubble) {
    mTitle.textContent = title;
    mText.textContent = text;
    mBubble.textContent = bubble || '';
    mBubble.style.display = bubble ? '' : 'none';
    modal.classList.add('show');
    modal.querySelector('button').focus();
  }

  var Demo = {
    /* On the real site this opens wa.me/<number>?text=<message>. */
    whatsapp: function (message) {
      show('This opens WhatsApp', 'On the real site, the customer’s WhatsApp opens a chat with the business with this message already typed. They just press send.', message);
    },
    call: function () {
      show('This calls the business', 'On the real site, tapping this on a phone starts a call straight away. No copying numbers.', '');
    },
    /* schedule: {0:[[540,780]], 1:[...], ...} with minutes since midnight; Sunday = 0 */
    openStatus: function (el, schedule) {
      var parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date());
      var get = function (t) { return (parts.find(function (p) { return p.type === t; }) || {}).value; };
      var day = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(get('weekday'));
      var now = (parseInt(get('hour'), 10) % 24) * 60 + parseInt(get('minute'), 10);
      var fmt = function (m) { var h = Math.floor(m / 60), mm = m % 60, ap = h >= 12 ? 'pm' : 'am'; h = h % 12 || 12; return h + (mm ? ':' + String(mm).padStart(2, '0') : '') + ' ' + ap; };
      var today = schedule[day] || [];
      for (var i = 0; i < today.length; i++) {
        if (now >= today[i][0] && now < today[i][1]) {
          el.textContent = 'Open now · until ' + fmt(today[i][1]);
          el.dataset.state = 'open';
          return;
        }
      }
      for (var d = 0; d < 7; d++) {
        var slots = schedule[(day + d) % 7] || [];
        for (var j = 0; j < slots.length; j++) {
          if (d > 0 || slots[j][0] > now) {
            el.textContent = 'Closed · opens ' + (d === 0 ? 'today' : d === 1 ? 'tomorrow' : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][(day + d) % 7]) + ' at ' + fmt(slots[j][0]);
            el.dataset.state = 'closed';
            return;
          }
        }
      }
      el.textContent = 'Closed';
      el.dataset.state = 'closed';
    }
  };

  document.addEventListener('click', function (e) {
    var c = e.target.closest('[data-call]');
    if (c) { e.preventDefault(); Demo.call(); return; }
    var w = e.target.closest('[data-wa]');
    if (w) { e.preventDefault(); Demo.whatsapp(w.getAttribute('data-wa')); }
  });

  window.Demo = Demo;
})();
