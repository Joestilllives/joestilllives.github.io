/* Manga Lens Translator — background script.
 *
 * Receives page images from the content script, batches several pages into a
 * single Gemini request (the free tier limits requests per day, not pages, so
 * batching stretches the allowance), caches results, and falls back to other
 * models when one model's free quota runs out.
 */
"use strict";

const API_BASE = "https://generativelanguage.googleapis.com/v1beta";

const DEFAULT_SETTINGS = {
  apiKey: "",
  // Tried in order. When one model's free daily quota runs out we move to the next.
  models: [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
  ],
  batchSize: 4,
  enabledSites: [],
  showSfx: true,
  targetLanguage: "English",
};

const CACHE_LIMIT = 800;
const BATCH_WAIT_MS = 700;

// ---------------------------------------------------------------- settings

async function getSettings() {
  const stored = await browser.storage.local.get("settings");
  return Object.assign({}, DEFAULT_SETTINGS, stored.settings || {});
}

// Free-tier quotas reset at midnight Pacific time.
function quotaDay() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/Los_Angeles" });
}

async function getModelState() {
  const { modelState } = await browser.storage.local.get("modelState");
  if (!modelState || modelState.day !== quotaDay()) {
    return { day: quotaDay(), exhausted: {} };
  }
  return modelState;
}

async function markExhausted(model) {
  const state = await getModelState();
  state.exhausted[model] = true;
  await browser.storage.local.set({ modelState: state });
}

async function bumpStats(requests, pages) {
  const { stats } = await browser.storage.local.get("stats");
  const s = stats && stats.day === quotaDay() ? stats : { day: quotaDay(), requests: 0, pages: 0 };
  s.requests += requests;
  s.pages += pages;
  await browser.storage.local.set({ stats: s });
}

// What we're doing right now (shown on the page while it waits) and a short
// activity log (shown in settings) so problems can be diagnosed.
let liveStatus = "";
const activityLog = [];
function setStatus(text) { liveStatus = text; }
function logEvent(text) {
  const time = new Date().toLocaleTimeString("en-GB");
  activityLog.push(`${time}  ${text}`);
  if (activityLog.length > 40) activityLog.shift();
  browser.storage.local.set({ activityLog }).catch(() => {});
}

const REQUEST_TIMEOUT_MS = 75000;

// Models that returned "not found" this session; skip them until restart.
const missingModels = new Set();
// Models that rejected the thinkingConfig field.
const noThinkingConfig = new Set();

// ------------------------------------------------------------------- cache

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function cacheGet(key) {
  const k = "c:" + key;
  const got = await browser.storage.local.get(k);
  return got[k] || null;
}

let cacheWriteChain = Promise.resolve();
function cacheSet(key, value) {
  // Serialize writes so the index doesn't get clobbered by concurrent updates.
  cacheWriteChain = cacheWriteChain.then(async () => {
    const k = "c:" + key;
    const { cacheIndex = [] } = await browser.storage.local.get("cacheIndex");
    const idx = cacheIndex.filter((x) => x !== k);
    idx.push(k);
    const evict = idx.length > CACHE_LIMIT ? idx.splice(0, idx.length - CACHE_LIMIT) : [];
    await browser.storage.local.set({ [k]: value, cacheIndex: idx });
    if (evict.length) await browser.storage.local.remove(evict);
  }).catch((e) => console.warn("[manga-lens] cache write failed", e));
  return cacheWriteChain;
}

async function cacheClear() {
  const all = await browser.storage.local.get(null);
  const keys = Object.keys(all).filter((k) => k.startsWith("c:"));
  keys.push("cacheIndex");
  await browser.storage.local.remove(keys);
}

// ------------------------------------------------------------------- queue

class TranslateError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const queue = [];          // pending items waiting to be sent
const inflight = new Map(); // key -> Promise of result
let batchTimer = null;
let working = false;

function enqueue(item) {
  return new Promise((resolve, reject) => {
    item.resolve = resolve;
    item.reject = reject;
    queue.push(item);
    scheduleBatch();
  });
}

async function scheduleBatch() {
  if (working) return;
  const { batchSize } = await getSettings();
  if (queue.length >= batchSize) {
    clearTimeout(batchTimer);
    batchTimer = null;
    runBatch();
  } else if (!batchTimer) {
    batchTimer = setTimeout(() => {
      batchTimer = null;
      runBatch();
    }, BATCH_WAIT_MS);
  }
}

async function runBatch() {
  if (working || queue.length === 0) return;
  working = true;
  try {
    const settings = await getSettings();
    const batch = queue.splice(0, Math.max(1, Math.min(8, settings.batchSize | 0)));
    try {
      const pages = await translateBatch(settings, batch);
      setStatus("");
      await bumpStats(1, batch.length);
      batch.forEach((item, i) => {
        const result = { bubbles: pages[i] || [], t: Date.now() };
        cacheSet(item.key, result);
        item.resolve(result);
      });
    } catch (err) {
      const e = err instanceof TranslateError ? err : new TranslateError("other", String(err && err.message || err));
      setStatus("");
      logEvent(`Failed: ${e.message}`);
      batch.forEach((item) => item.reject(e));
      // On a "stop everything" error, fail the rest of the queue too instead of
      // burning more requests.
      if (["quota", "nokey", "badkey"].includes(e.code)) {
        queue.splice(0).forEach((item) => item.reject(e));
      }
    }
  } finally {
    working = false;
    if (queue.length) scheduleBatch();
  }
}

// ------------------------------------------------------------- Gemini call

function buildPrompt(settings, count) {
  const lang = settings.targetLanguage || "English";
  return [
    `You are an expert manga translator and letterer. You will receive ${count} manga page image(s), in reading order.`,
    `For EACH page, find every piece of Japanese text: speech bubbles, thought bubbles, narration boxes, signs` +
      (settings.showSfx ? ", and sound effects." : ". Skip sound effects (SFX)."),
    `Translate each into natural, fluent ${lang} that keeps the character's tone, personality and register.`,
    `Use the surrounding pages as context so names, pronouns and running jokes stay consistent.`,
    `Japanese manga is read right-to-left, top-to-bottom; list bubbles in that reading order.`,
    `For each text region give box_2d as [ymin, xmin, ymax, xmax] normalized to 0-1000 relative to that page image.`,
    `The box must cover the whole inside of the speech bubble or text area (not just the characters), so the translation can be printed over it.`,
    `Keep translations concise enough to fit in the bubble. Do not add notes or explanations.`,
    `If a page has no Japanese text, return an empty bubbles list for it.`,
    `"page" is the 1-based index of the image in this request.`,
  ].join("\n");
}

const RESPONSE_SCHEMA = {
  type: "OBJECT",
  properties: {
    pages: {
      type: "ARRAY",
      items: {
        type: "OBJECT",
        properties: {
          page: { type: "INTEGER" },
          bubbles: {
            type: "ARRAY",
            items: {
              type: "OBJECT",
              properties: {
                box_2d: { type: "ARRAY", items: { type: "INTEGER" } },
                japanese: { type: "STRING" },
                translation: { type: "STRING" },
                kind: { type: "STRING", enum: ["speech", "thought", "narration", "sfx", "sign"] },
              },
              required: ["box_2d", "translation"],
            },
          },
        },
        required: ["page", "bubbles"],
      },
    },
  },
  required: ["pages"],
};

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function parseRetryDelay(body) {
  try {
    for (const d of body.error.details || []) {
      if (d.retryDelay) return Math.ceil(parseFloat(d.retryDelay) * 1000);
    }
  } catch (_) { /* ignore */ }
  return 15000;
}

function isDailyQuota(body) {
  const text = JSON.stringify(body || {});
  return /PerDay|per day|daily/i.test(text) || /limit:\s*0\b/.test(text);
}

async function callGemini(settings, model, items) {
  const parts = [{ text: buildPrompt(settings, items.length) }];
  items.forEach((item, i) => {
    parts.push({ text: `Page ${i + 1}:` });
    parts.push({ inline_data: { mime_type: item.mime, data: item.image } });
  });
  const generationConfig = {
    temperature: 0.4,
    responseMimeType: "application/json",
    responseSchema: RESPONSE_SCHEMA,
  };
  // Thinking adds latency and isn't needed here; some models reject the field.
  if (!noThinkingConfig.has(model)) generationConfig.thinkingConfig = { thinkingBudget: 0 };

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/models/${encodeURIComponent(model)}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": settings.apiKey },
      body: JSON.stringify({ contents: [{ role: "user", parts }], generationConfig }),
      signal: ctrl.signal,
    });
    let body = null;
    try { body = await res.json(); } catch (_) { /* non-JSON or timed out mid-body */ }
    return { status: res.status, body };
  } finally {
    clearTimeout(timer);
  }
}

function extractPages(body, count) {
  const cand = body && body.candidates && body.candidates[0];
  const text = cand && cand.content && (cand.content.parts || []).map((p) => p.text || "").join("");
  if (!text) {
    const reason = (cand && cand.finishReason) || (body && body.promptFeedback && body.promptFeedback.blockReason) || "empty";
    throw new TranslateError("blocked", "Gemini returned no translation (" + reason + ")");
  }
  let data;
  try {
    data = JSON.parse(text);
  } catch (_) {
    try {
      // Occasionally wrapped in a code fence.
      data = JSON.parse(text.replace(/^```(?:json)?\s*|\s*```$/g, ""));
    } catch (_e) {
      throw new TranslateError("other", "Gemini's answer was cut off or garbled.");
    }
  }
  const out = Array.from({ length: count }, () => []);
  (data.pages || []).forEach((p, i) => {
    const idx = Number.isInteger(p.page) && p.page >= 1 && p.page <= count ? p.page - 1 : i;
    if (idx >= count) return;
    out[idx] = (p.bubbles || [])
      .filter((b) => Array.isArray(b.box_2d) && b.box_2d.length === 4 && b.translation)
      .map((b) => ({
        box: b.box_2d.map((n) => Math.max(0, Math.min(1000, Number(n) || 0))),
        text: String(b.translation).trim(),
        ja: b.japanese ? String(b.japanese) : "",
        kind: b.kind || "speech",
      }))
      .filter((b) => b.box[2] > b.box[0] && b.box[3] > b.box[1]);
  });
  return out;
}

async function translateBatch(settings, items) {
  if (!settings.apiKey) throw new TranslateError("nokey", "Add your free Gemini API key in the extension settings.");
  const models = (settings.models || []).map((m) => m.trim()).filter(Boolean);
  let lastError = null;
  let timeouts = 0;

  for (const model of models) {
    if (missingModels.has(model)) continue;
    if (timeouts >= 2) break;          // two models timed out: stop rather than wait for minutes
    const state = await getModelState();
    if (state.exhausted[model]) continue;

    for (let attempt = 0; attempt < 3; attempt++) {
      let r;
      const started = Date.now();
      setStatus(`Waiting for ${model}…`);
      try {
        r = await callGemini(settings, model, items);
      } catch (e) {
        const timedOut = e && e.name === "AbortError";
        logEvent(`${model}: ${timedOut ? "no answer after " + REQUEST_TIMEOUT_MS / 1000 + "s" : "network error: " + (e && e.message)}`);
        lastError = timedOut
          ? new TranslateError("timeout", "Gemini took too long to answer.")
          : new TranslateError("network", "Network error talking to Gemini.");
        if (timedOut) { timeouts++; break; } // don't sit through another long wait on the same model
        await sleep(2000);
        continue;
      }
      const msg = (r.body && r.body.error && r.body.error.message) || "";
      const secs = ((Date.now() - started) / 1000).toFixed(1);
      logEvent(`${model}: ${items.length} page(s) → HTTP ${r.status} in ${secs}s${msg ? " — " + msg.slice(0, 160) : ""}`);

      if (r.status === 200) {
        if (!r.body) { lastError = new TranslateError("other", "Gemini sent an unreadable answer."); break; }
        return extractPages(r.body, items.length);
      }
      if (r.status === 400 && /thinking/i.test(msg) && !noThinkingConfig.has(model)) {
        noThinkingConfig.add(model);
        continue;
      }
      if ((r.status === 400 && /API key/i.test(msg)) || r.status === 401 || r.status === 403) {
        throw new TranslateError("badkey", "Your Gemini API key was rejected. Check it in the extension settings.");
      }
      if (r.status === 404 || (r.status === 400 && /not found|not supported/i.test(msg))) {
        missingModels.add(model);
        lastError = new TranslateError("other", `Model ${model} isn't available.`);
        break;
      }
      if (r.status === 429) {
        if (isDailyQuota(r.body)) {
          await markExhausted(model);
          lastError = new TranslateError("quota", "Today's free Gemini limit is used up. It resets at midnight Pacific time.");
          break;
        }
        // Per-minute limit: wait once (briefly), then move on to the next model.
        lastError = new TranslateError("rate", "Free per-minute limit reached. Wait a minute.");
        if (attempt >= 1) break;
        const wait = Math.min(30000, parseRetryDelay(r.body));
        setStatus(`Free per-minute limit reached, retrying in ${Math.round(wait / 1000)}s…`);
        await sleep(wait);
        continue;
      }
      if (r.status >= 500) {
        lastError = new TranslateError("other", `Gemini is overloaded (${r.status}).`);
        if (attempt >= 1) break;
        setStatus(`${model} is busy, retrying…`);
        await sleep(3000);
        continue;
      }
      lastError = new TranslateError("other", msg || `Gemini error ${r.status}`);
      break;
    }
  }
  throw lastError || new TranslateError("quota", "Today's free Gemini limit is used up. It resets at midnight Pacific time.");
}

// ---------------------------------------------------------------- handlers

async function handleTranslate(msg) {
  const key = await sha256(msg.src);
  const cached = await cacheGet(key);
  if (cached) return { ok: true, cached: true, bubbles: cached.bubbles };
  if (!inflight.has(key)) {
    const p = enqueue({ key, image: msg.image, mime: msg.mime || "image/jpeg" })
      .finally(() => inflight.delete(key));
    inflight.set(key, p);
  }
  try {
    const result = await inflight.get(key);
    return { ok: true, bubbles: result.bubbles };
  } catch (e) {
    return { ok: false, code: e.code || "other", error: e.message };
  }
}

async function handleFetchImage(msg) {
  const res = await fetch(msg.src, { credentials: "include", referrer: msg.referrer || "" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  const blob = await res.blob();
  const dataUrl = await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(blob);
  });
  return { dataUrl };
}

async function handleTestKey(msg) {
  const res = await fetch(`${API_BASE}/models?pageSize=200`, { headers: { "x-goog-api-key": msg.apiKey } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) return { ok: false, error: (body.error && body.error.message) || "HTTP " + res.status };
  const models = (body.models || [])
    .filter((m) => (m.supportedGenerationMethods || []).includes("generateContent"))
    .map((m) => m.name.replace(/^models\//, ""))
    .filter((n) => /flash/i.test(n) && !/image|tts|audio|live|embedding/i.test(n));
  return { ok: true, models };
}

browser.runtime.onMessage.addListener((msg, sender) => {
  switch (msg && msg.type) {
    case "translate":
      return handleTranslate(msg);
    case "fetchImage":
      return handleFetchImage(msg).catch((e) => ({ error: String(e.message || e) }));
    case "openSettings":
      return browser.runtime.openOptionsPage();
    case "testKey":
      return handleTestKey(msg).catch((e) => ({ ok: false, error: String(e.message || e) }));
    case "getStatus":
      return Promise.all([browser.storage.local.get("stats"), getModelState()]).then(([s, m]) => ({
        stats: s.stats && s.stats.day === quotaDay() ? s.stats : { requests: 0, pages: 0 },
        exhausted: Object.keys(m.exhausted),
        live: liveStatus,
        queued: queue.length,
        log: activityLog.slice(),
      }));
    case "resetQuota":
      return browser.storage.local.remove("modelState").then(() => missingModels.clear());
    case "clearCache":
      return cacheClear();
    default:
      return undefined;
  }
});
