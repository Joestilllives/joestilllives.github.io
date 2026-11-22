/* Carryover: read Microsoft To Do lists in the browser and download them for other apps.
   Sign-in uses the Microsoft identity platform (authorization code flow with PKCE) and asks
   only for Tasks.Read. The access token stays in this tab's memory; nothing is sent anywhere
   except Microsoft's own sign-in and Graph API. */
(function () {
  var CONFIG = {
    /* Paste the Application (client) ID from the Microsoft app registration here.
       While it is empty, the page runs in demo mode with sample lists. */
    clientId: '770b0406-86f9-4340-937b-1736f01ee838',
    authority: 'https://login.microsoftonline.com/common',
    scope: 'Tasks.Read'
  };
  /* Lets a test page supply a client ID without editing this file. */
  if (window.CARRYOVER_CLIENT_ID) CONFIG.clientId = String(window.CARRYOVER_CLIENT_ID);
  var GRAPH = 'https://graph.microsoft.com/v1.0';
  var REDIRECT = location.origin + location.pathname.replace(/index\.html$/, '');
  var KEY = 'carryover-auth';

  var $ = function (id) { return document.getElementById(id); };
  var state = { raw: null, lists: null, demo: false, format: 'todoist', includeCompleted: false, chosen: {} };

  /* ---------- helpers ---------- */
  function b64url(bytes) {
    var s = ''; bytes = new Uint8Array(bytes);
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function randomString(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return b64url(a); }
  function show(view) {
    ['viewStart', 'viewLoading', 'viewReady', 'viewError'].forEach(function (v) { $(v).hidden = v !== view; });
  }
  function fail(msg) { $('errorText').textContent = msg; show('viewError'); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  /* ---------- sign-in ---------- */
  function signIn() {
    if (!CONFIG.clientId) { loadDemo(); return; }
    var verifier = randomString(48), st = randomString(16);
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)).then(function (hash) {
      try { sessionStorage.setItem(KEY, JSON.stringify({ verifier: verifier, state: st })); } catch (e) {}
      var q = new URLSearchParams({
        client_id: CONFIG.clientId, response_type: 'code', redirect_uri: REDIRECT, response_mode: 'query',
        scope: CONFIG.scope, state: st, code_challenge: b64url(hash), code_challenge_method: 'S256', prompt: 'select_account'
      });
      location.assign(CONFIG.authority + '/oauth2/v2.0/authorize?' + q.toString());
    });
  }

  function handleRedirect() {
    var p = new URLSearchParams(location.search);
    if (!p.has('code') && !p.has('error')) return false;
    history.replaceState(null, '', REDIRECT + location.hash);
    if (p.has('error')) {
      fail(p.get('error') === 'access_denied' ? 'Sign-in was cancelled, so nothing was read. You can try again whenever you like.' : 'Microsoft sign-in did not finish: ' + (p.get('error_description') || p.get('error')));
      return true;
    }
    var saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(KEY)); sessionStorage.removeItem(KEY); } catch (e) {}
    if (!saved || saved.state !== p.get('state')) { fail('That sign-in link expired or came from another tab. Please sign in again.'); return true; }
    show('viewLoading');
    $('progress').textContent = 'Finishing sign-in…';
    fetch(CONFIG.authority + '/oauth2/v2.0/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ client_id: CONFIG.clientId, grant_type: 'authorization_code', code: p.get('code'),
        redirect_uri: REDIRECT, code_verifier: saved.verifier, scope: CONFIG.scope }).toString()
    }).then(function (r) { return r.json(); }).then(function (tok) {
      if (!tok.access_token) throw new Error(tok.error_description || 'Microsoft did not return access.');
      return readAll(tok.access_token);
    }).then(function (lists) { ready(lists, false); })
      .catch(function (e) { fail('Could not read your lists: ' + e.message); });
    return true;
  }

  /* ---------- reading from Microsoft Graph ---------- */
  function graph(url, token, tries) {
    tries = tries || 0;
    return fetch(url, { headers: { Authorization: 'Bearer ' + token } }).then(function (r) {
      if (r.status === 429 || r.status === 503 || r.status === 504) {
        if (tries >= 5) throw new Error('Microsoft is busy right now. Please try again in a few minutes.');
        var wait = (Number(r.headers.get('Retry-After')) || Math.pow(2, tries)) * 1000;
        return sleep(Math.min(wait, 30000)).then(function () { return graph(url, token, tries + 1); });
      }
      if (r.status === 401 || r.status === 403) throw new Error('Microsoft did not allow access to your tasks. Sign in again and approve read access.');
      if (!r.ok) throw new Error('Microsoft returned an error (' + r.status + ').');
      return r.json();
    });
  }
  function all(url, token, onPage) {
    var items = [];
    function next(u) {
      return graph(u, token).then(function (page) {
        items = items.concat(page.value || []);
        if (onPage) onPage(items.length);
        return page['@odata.nextLink'] ? next(page['@odata.nextLink']) : items;
      });
    }
    return next(url);
  }
  function readAll(token) {
    $('progress').textContent = 'Finding your lists…';
    return all(GRAPH + '/me/todo/lists', token).then(function (lists) {
      var total = 0, i = 0;
      return lists.reduce(function (chain, l) {
        return chain.then(function () {
          i++;
          return all(GRAPH + '/me/todo/lists/' + encodeURIComponent(l.id) + '/tasks?$expand=checklistItems', token, function (n) {
            $('progress').textContent = 'Reading list ' + i + ' of ' + lists.length + ' (' + (total + n) + ' tasks so far)…';
          }).then(function (tasks) { l.tasks = tasks; total += tasks.length; });
        });
      }, Promise.resolve()).then(function () { return lists; });
    });
  }

  /* ---------- demo ---------- */
  function loadDemo() {
    show('viewLoading');
    $('progress').textContent = 'Loading sample lists…';
    setTimeout(function () { ready(DEMO, true); }, 400);
  }
  var DEMO = [
    { id: 'd1', displayName: 'Tasks', wellknownListName: 'defaultList', tasks: [
      { id: 't1', title: 'Renew passport', importance: 'high', status: 'notStarted', dueDateTime: { dateTime: '2027-01-15T00:00:00.0000000', timeZone: 'UTC' },
        body: { contentType: 'html', content: '<p>Book appointment online.</p><p>Bring <b>2 photos</b> &amp; old passport.</p>' },
        checklistItems: [{ displayName: 'Fill the form', isChecked: true }, { displayName: 'Pay fee', isChecked: false }] },
      { id: 't2', title: 'Pay electricity bill', importance: 'normal', status: 'notStarted', dueDateTime: { dateTime: '2026-12-05T00:00:00.0000000', timeZone: 'UTC' },
        recurrence: { pattern: { type: 'absoluteMonthly', interval: 1, dayOfMonth: 5 }, range: { type: 'noEnd' } }, body: { contentType: 'text', content: '' } },
      { id: 't3', title: 'Call the bank about the card', importance: 'normal', status: 'completed', completedDateTime: { dateTime: '2026-11-10T09:00:00.0000000', timeZone: 'UTC' }, body: { contentType: 'text', content: '' } }
    ] },
    { id: 'd2', displayName: 'Groceries', wellknownListName: 'none', tasks: [
      { id: 't4', title: 'Milk', importance: 'normal', status: 'notStarted', body: { contentType: 'text', content: '' } },
      { id: 't5', title: 'Atta, 5 kg', importance: 'normal', status: 'notStarted', body: { contentType: 'text', content: '' } },
      { id: 't6', title: 'Coffee beans', importance: 'low', status: 'completed', body: { contentType: 'text', content: '' } }
    ] },
    { id: 'd3', displayName: 'Goa trip', wellknownListName: 'none', tasks: [
      { id: 't7', title: 'Book train tickets', importance: 'high', status: 'notStarted', dueDateTime: { dateTime: '2026-12-01T00:00:00.0000000', timeZone: 'UTC' },
        isReminderOn: true, reminderDateTime: { dateTime: '2026-11-30T03:30:00.0000000', timeZone: 'UTC' },
        body: { contentType: 'text', content: 'Window seats if possible, "sleeper" class is fine.' },
        checklistItems: [{ displayName: 'Check dates with Riya', isChecked: false }] },
      { id: 't8', title: 'Water the plants before leaving', importance: 'normal', status: 'notStarted',
        recurrence: { pattern: { type: 'weekly', interval: 1, daysOfWeek: ['monday', 'thursday'] }, range: { type: 'noEnd' } }, body: { contentType: 'text', content: '' } }
    ] }
  ];

  /* ---------- ready view ---------- */
  function ready(raw, demo) {
    state.raw = raw; state.demo = demo; state.lists = Formats.normalise(raw); state.chosen = {};
    state.lists.forEach(function (l, i) { state.chosen[i] = true; });
    $('demoNote').hidden = !demo;
    var open = 0, done = 0;
    state.lists.forEach(function (l) { l.tasks.forEach(function (t) { if (t.done) done++; else open++; }); });
    $('summary').textContent = state.lists.length + (state.lists.length === 1 ? ' list' : ' lists') + ' · ' + open + ' open tasks · ' + done + ' completed';
    var box = $('lists'); box.innerHTML = '';
    state.lists.forEach(function (l, i) {
      var o = l.tasks.filter(function (t) { return !t.done; }).length;
      var row = document.createElement('label');
      row.className = 'listrow';
      row.innerHTML = '<input type="checkbox" checked><span class="lname"></span><span class="lcount"></span>';
      row.querySelector('input').id = 'list-' + i;
      row.querySelector('.lname').textContent = l.name;
      row.querySelector('.lcount').textContent = o + ' open · ' + (l.tasks.length - o) + ' done';
      row.querySelector('input').addEventListener('change', function (e) { state.chosen[i] = e.target.checked; preview(); });
      box.appendChild(row);
    });
    show('viewReady');
    preview();
  }

  function selected() { return state.lists.filter(function (l, i) { return state.chosen[i]; }); }
  function build() {
    var f = Formats.ALL[state.format];
    return f.make(selected(), { includeCompleted: state.includeCompleted });
  }
  function preview() {
    if (!state.lists) return;
    var files = build(), first = files[0];
    var text = files.length ? first.text.replace(/^﻿/, '') : '';
    var lines = text.split(/\r?\n/);
    $('previewName').textContent = files.length > 1 ? files.length + ' files, one per list (showing ' + first.name.replace(/^todoist\//, '') + ')' : (first ? first.name : 'Nothing selected');
    $('previewBody').textContent = lines.slice(0, 40).join('\n') + (lines.length > 40 ? '\n…' : '');
    $('download').disabled = !selected().length;
    $('guideHint').textContent = HINTS[state.format];
  }
  var HINTS = {
    todoist: 'One file per list. In Todoist, create a project for each list, then use the project menu’s Import from CSV option.',
    csv: 'Opens in Excel or Google Sheets. Notion and Airtable can import it as a table.',
    markdown: 'Drop the file into an Obsidian vault, or import it into Notion, Logseq or any notes app.',
    ics: 'For apps that import iCalendar tasks, such as Thunderbird and Nextcloud Tasks.',
    json: 'Everything Carryover read, in full. Keep it as a backup.'
  };

  function download() {
    var files = build();
    if (!files.length) return;
    var blob, name;
    if (files.length === 1) {
      blob = new Blob([files[0].text], { type: 'text/plain;charset=utf-8' });
      name = files[0].name;
    } else {
      blob = new Blob([Zip.make(files)], { type: 'application/zip' });
      name = 'carryover-' + state.format + '.zip';
    }
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
    $('saved').hidden = false;
  }

  /* ---------- wiring ---------- */
  document.querySelectorAll('input[name="format"]').forEach(function (r) {
    r.addEventListener('change', function () { state.format = r.value; preview(); });
  });
  $('includeCompleted').addEventListener('change', function (e) { state.includeCompleted = e.target.checked; preview(); });
  $('signIn').addEventListener('click', signIn);
  $('tryDemo').addEventListener('click', loadDemo);
  $('download').addEventListener('click', download);
  [$('startOver'), $('retry')].forEach(function (b) { b.addEventListener('click', function () { state = { raw: null, lists: null, demo: false, format: state.format, includeCompleted: state.includeCompleted, chosen: {} }; $('saved').hidden = true; show('viewStart'); }); });

  if (!CONFIG.clientId) {
    $('signIn').textContent = 'Sign in with Microsoft (coming soon)';
    $('signIn').disabled = true;
    $('signInNote').hidden = false;
  }
  if (!handleRedirect()) show('viewStart');
})();
