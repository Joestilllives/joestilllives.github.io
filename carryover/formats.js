/* Carryover export formats. Pure functions: they take the lists read from Microsoft To Do
   (normalised by normalise()) and return files as { name, text }. No network, no DOM. */
var Formats = (function () {
  /* ---------- normalising Graph data ---------- */

  function htmlToText(html) {
    if (!html) return '';
    var s = String(html)
      .replace(/<\s*br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|h[1-6])>/gi, '\n')
      .replace(/<li[^>]*>/gi, '- ')
      .replace(/<[^>]+>/g, '');
    s = s.replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
    return s.replace(/\r/g, '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  }

  /* Graph dateTimeTimeZone -> "YYYY-MM-DD" (To Do due dates are whole days). */
  function day(dt) {
    if (!dt || !dt.dateTime) return '';
    return String(dt.dateTime).slice(0, 10);
  }
  /* Graph dateTimeTimeZone or ISO string -> ISO string in UTC ("Z"), or '' */
  function iso(dt) {
    var v = dt && typeof dt === 'object' ? dt.dateTime : dt;
    if (!v) return '';
    v = String(v);
    var tz = dt && dt.timeZone;
    if (!/[zZ]|[+-]\d\d:?\d\d$/.test(v) && (!tz || /^utc$/i.test(tz))) v += 'Z';
    var d = new Date(v);
    return isNaN(d) ? '' : d.toISOString().replace(/\.\d{3}Z$/, 'Z');
  }

  var DAYS = { sunday: 'sun', monday: 'mon', tuesday: 'tue', wednesday: 'wed', thursday: 'thu', friday: 'fri', saturday: 'sat' };

  /* Recurrence -> plain English ("every 2 weeks on mon, thu"). Used for notes and Todoist. */
  function recurrenceText(r) {
    if (!r || !r.pattern) return '';
    var p = r.pattern, n = p.interval > 1 ? p.interval + ' ' : '';
    var unit = { daily: 'day', weekly: 'week', absoluteMonthly: 'month', relativeMonthly: 'month', absoluteYearly: 'year', relativeYearly: 'year' }[p.type];
    if (!unit) return '';
    var txt = 'every ' + n + unit + (p.interval > 1 ? 's' : '');
    if (p.type === 'weekly' && p.daysOfWeek && p.daysOfWeek.length) {
      txt = (p.interval > 1 ? 'every ' + p.interval + ' weeks on ' : 'every ') + p.daysOfWeek.map(function (d) { return DAYS[String(d).toLowerCase()] || d; }).join(', ');
    }
    return txt;
  }

  /* RFC 5545 RRULE for .ics */
  function rrule(r) {
    if (!r || !r.pattern) return '';
    var p = r.pattern;
    var freq = { daily: 'DAILY', weekly: 'WEEKLY', absoluteMonthly: 'MONTHLY', relativeMonthly: 'MONTHLY', absoluteYearly: 'YEARLY', relativeYearly: 'YEARLY' }[p.type];
    if (!freq) return '';
    var out = 'FREQ=' + freq;
    if (p.interval > 1) out += ';INTERVAL=' + p.interval;
    if (p.type === 'weekly' && p.daysOfWeek && p.daysOfWeek.length) {
      out += ';BYDAY=' + p.daysOfWeek.map(function (d) { return String(d).slice(0, 2).toUpperCase(); }).join(',');
    }
    if (r.range && r.range.type === 'endDate' && r.range.endDate) out += ';UNTIL=' + r.range.endDate.replace(/-/g, '');
    if (r.range && r.range.type === 'numbered' && r.range.numberOfOccurrences) out += ';COUNT=' + r.range.numberOfOccurrences;
    return out;
  }

  /* lists: [{ displayName, wellknownListName, tasks: [graph todoTask with checklistItems] }] */
  function normalise(lists) {
    return lists.map(function (l) {
      return {
        name: l.displayName || 'Untitled list',
        special: l.wellknownListName && l.wellknownListName !== 'none' ? l.wellknownListName : '',
        tasks: (l.tasks || []).map(function (t) {
          return {
            id: t.id || '',
            title: (t.title || '').trim() || '(untitled task)',
            notes: t.body && t.body.contentType === 'html' ? htmlToText(t.body.content) : ((t.body && t.body.content) || '').trim(),
            done: t.status === 'completed',
            importance: t.importance || 'normal',
            due: day(t.dueDateTime),
            reminder: t.isReminderOn ? iso(t.reminderDateTime) : '',
            created: iso(t.createdDateTime),
            completed: iso(t.completedDateTime),
            repeat: recurrenceText(t.recurrence),
            rrule: rrule(t.recurrence),
            categories: t.categories || [],
            steps: (t.checklistItems || []).map(function (c) { return { title: (c.displayName || '').trim(), done: !!c.isChecked }; }).filter(function (c) { return c.title; }),
            links: (t.linkedResources || []).map(function (r) { return r.webUrl; }).filter(Boolean)
          };
        })
      };
    });
  }

  function keep(lists, opts) {
    return lists.map(function (l) {
      return { name: l.name, special: l.special, tasks: opts && opts.includeCompleted ? l.tasks : l.tasks.filter(function (t) { return !t.done; }) };
    });
  }

  function safeName(s) {
    return String(s).replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80) || 'list';
  }
  function uniqueNames(lists, ext) {
    var used = {};
    return lists.map(function (l) {
      var base = safeName(l.name), name = base, i = 2;
      while (used[name.toLowerCase()]) name = base + ' (' + (i++) + ')';
      used[name.toLowerCase()] = 1;
      return name + ext;
    });
  }

  /* ---------- CSV ---------- */
  function csvCell(v, sheet) {
    v = v == null ? '' : String(v);
    /* In spreadsheets, stop text that looks like a formula ("=SUM(...)", "+1", "@x") from running.
       Ordinary titles such as "- buy milk" are left alone. Todoist files skip this. */
    if (sheet && /^(=|@|[+\-](?=[^\s])|\t|\r)/.test(v)) v = "'" + v;
    return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }
  function csvRow(cells, sheet) { return cells.map(function (c) { return csvCell(c, sheet); }).join(',') + '\r\n'; }

  /* One spreadsheet for everything: opens in Excel and Google Sheets, imports into Notion and Airtable. */
  function genericCsv(lists, opts) {
    var out = csvRow(['List', 'Task', 'Notes', 'Done', 'Importance', 'Due date', 'Reminder', 'Repeats', 'Steps', 'Categories', 'Links', 'Created', 'Completed'], true);
    keep(lists, opts).forEach(function (l) {
      l.tasks.forEach(function (t) {
        out += csvRow([l.name, t.title, t.notes, t.done ? 'yes' : 'no', t.importance, t.due, t.reminder, t.repeat,
          t.steps.map(function (s) { return (s.done ? '[x] ' : '[ ] ') + s.title; }).join('\n'),
          t.categories.join(', '), t.links.join(' '), t.created, t.completed], true);
      });
    });
    return [{ name: 'carryover-all-tasks.csv', text: '\ufeff' + out }];
  }

  /* Todoist imports one CSV per project. Steps become sub-tasks (INDENT 2).
     Todoist CSV priority uses 1 = highest (p1) and 4 = normal (p4). */
  function todoistCsv(lists, opts) {
    var kept = keep(lists, opts), names = uniqueNames(kept, '.csv');
    return kept.map(function (l, i) {
      var out = csvRow(['TYPE', 'CONTENT', 'DESCRIPTION', 'PRIORITY', 'INDENT', 'AUTHOR', 'RESPONSIBLE', 'DATE', 'DATE_LANG', 'TIMEZONE']);
      l.tasks.forEach(function (t) {
        var desc = t.notes;
        if (t.links.length) desc += (desc ? '\n\n' : '') + t.links.join('\n');
        var date = t.repeat ? t.repeat + (t.due ? ' starting ' + t.due : '') : t.due;
        out += csvRow(['task', t.title, desc, t.importance === 'high' ? 1 : 4, 1, '', '', date, date ? 'en' : '', '']);
        t.steps.forEach(function (s) {
          if (!s.done || (opts && opts.includeCompleted)) out += csvRow(['task', s.title, '', 4, 2, '', '', '', '', '']);
        });
      });
      return { name: 'todoist/' + names[i], text: out };
    });
  }

  /* ---------- Markdown (Obsidian, Notion, Logseq, any notes app) ---------- */
  function markdown(lists, opts) {
    var out = '# My Microsoft To Do lists\n\nExported with Carryover.\n';
    keep(lists, opts).forEach(function (l) {
      out += '\n## ' + l.name.replace(/\n/g, ' ') + '\n\n';
      if (!l.tasks.length) out += '_No tasks_\n';
      l.tasks.forEach(function (t) {
        var meta = [];
        if (t.due) meta.push('due ' + t.due);
        if (t.repeat) meta.push('repeats ' + t.repeat);
        if (t.importance === 'high') meta.push('important');
        out += '- [' + (t.done ? 'x' : ' ') + '] ' + t.title.replace(/\n/g, ' ') + (meta.length ? ' (' + meta.join(', ') + ')' : '') + '\n';
        t.steps.forEach(function (s) { out += '    - [' + (s.done ? 'x' : ' ') + '] ' + s.title.replace(/\n/g, ' ') + '\n'; });
        if (t.notes) out += t.notes.split('\n').map(function (line) { return '    > ' + line; }).join('\n') + '\n';
        t.links.forEach(function (u) { out += '    - ' + u + '\n'; });
      });
    });
    return [{ name: 'carryover-tasks.md', text: out }];
  }

  /* ---------- iCalendar VTODO (Thunderbird, Nextcloud Tasks, many CalDAV apps) ---------- */
  function icsText(s) { return String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n'); }
  function fold(line) {
    /* Fold at 75 octets, never splitting a multi-byte character. */
    var bytes = new TextEncoder().encode(line);
    if (bytes.length <= 75) return line;
    var out = [], cur = '', curLen = 0, limit = 75;
    for (var ch of line) {
      var n = new TextEncoder().encode(ch).length;
      if (curLen + n > limit) { out.push(cur); cur = ''; curLen = 0; limit = 74; }
      cur += ch; curLen += n;
    }
    out.push(cur);
    return out.join('\r\n ');
  }
  function icsStamp(isoStr) { return isoStr.replace(/[-:]/g, '').replace(/\.\d+/, ''); }
  function ics(lists, opts) {
    var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Carryover//To Do export//EN', 'CALSCALE:GREGORIAN'];
    var stamp = icsStamp(new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')), n = 0;
    keep(lists, opts).forEach(function (l) {
      l.tasks.forEach(function (t) {
        var uid = 'carryover-' + (t.id || ++n) + '@joestilllives.github.io';
        lines.push('BEGIN:VTODO', 'UID:' + uid, 'DTSTAMP:' + stamp, 'SUMMARY:' + icsText(t.title));
        if (t.notes) lines.push('DESCRIPTION:' + icsText(t.notes + (t.links.length ? '\n\n' + t.links.join('\n') : '')));
        lines.push('CATEGORIES:' + icsText(l.name));
        lines.push('STATUS:' + (t.done ? 'COMPLETED' : 'NEEDS-ACTION'));
        lines.push('PRIORITY:' + ({ high: 1, normal: 5, low: 9 }[t.importance] || 5));
        if (t.due) lines.push('DUE;VALUE=DATE:' + t.due.replace(/-/g, ''));
        if (t.created) lines.push('CREATED:' + icsStamp(t.created));
        if (t.completed) lines.push('COMPLETED:' + icsStamp(t.completed));
        if (t.rrule && t.due) lines.push('RRULE:' + t.rrule);
        if (t.reminder) lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + icsText(t.title), 'TRIGGER;VALUE=DATE-TIME:' + icsStamp(t.reminder), 'END:VALARM');
        lines.push('END:VTODO');
        t.steps.forEach(function (s, i) {
          if (s.done && !(opts && opts.includeCompleted)) return;
          lines.push('BEGIN:VTODO', 'UID:' + uid.replace('@', '-step' + i + '@'), 'DTSTAMP:' + stamp, 'SUMMARY:' + icsText(s.title),
            'RELATED-TO:' + uid, 'CATEGORIES:' + icsText(l.name), 'STATUS:' + (s.done ? 'COMPLETED' : 'NEEDS-ACTION'), 'END:VTODO');
        });
      });
    });
    lines.push('END:VCALENDAR');
    return [{ name: 'carryover-tasks.ics', text: lines.map(fold).join('\r\n') + '\r\n' }];
  }

  /* ---------- Full backup ---------- */
  function json(lists) {
    return [{ name: 'carryover-backup.json', text: JSON.stringify({ exportedWith: 'Carryover', exportedAt: new Date().toISOString(), lists: lists }, null, 2) }];
  }

  var ALL = {
    csv: { label: 'Spreadsheet (CSV)', make: genericCsv },
    todoist: { label: 'Todoist', make: todoistCsv },
    markdown: { label: 'Markdown', make: markdown },
    ics: { label: 'Calendar tasks (.ics)', make: ics },
    json: { label: 'Full backup (JSON)', make: json }
  };

  return { normalise: normalise, htmlToText: htmlToText, recurrenceText: recurrenceText, rrule: rrule, ALL: ALL,
           genericCsv: genericCsv, todoistCsv: todoistCsv, markdown: markdown, ics: ics, json: json, fold: fold };
})();
if (typeof module !== 'undefined') module.exports = Formats;
