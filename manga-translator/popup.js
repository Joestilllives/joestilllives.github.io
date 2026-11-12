"use strict";

const $ = (id) => document.getElementById(id);
const DEFAULT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"];

async function load() {
  const { settings = {} } = await browser.storage.local.get("settings");
  return settings;
}
async function save(patch) {
  const settings = await load();
  Object.assign(settings, patch);
  await browser.storage.local.set({ settings });
  return settings;
}
function status(el, text, kind) {
  el.textContent = text;
  el.className = "status" + (kind ? " " + kind : "");
}

let currentHost = null;

async function renderSite() {
  const settings = await load();
  const on = (settings.enabledSites || []).includes(currentHost);
  const btn = $("site-toggle");
  btn.textContent = on ? "✓ Translating on this site — tap to turn off" : "Translate manga on this site";
  btn.classList.toggle("on", on);
  $("site-hint").textContent = on
    ? "A small あ→A button appears at the bottom-left of the page. Tap it to hide or show translations. Tap a bubble to peek at the Japanese."
    : "Only sites you switch on are translated, so the free limit isn't wasted on other pages.";
}

async function renderUsage() {
  const s = await browser.runtime.sendMessage({ type: "getStatus" });
  let text = `${s.stats.pages} page(s) translated in ${s.stats.requests} request(s) today.`;
  if (s.exhausted.length) text += ` Limit hit today on: ${s.exhausted.join(", ")}.`;
  if (s.live) text += ` Right now: ${s.live}`;
  status($("usage"), text, s.exhausted.length ? "err" : "");
  $("log").textContent = (s.log || []).length ? s.log.slice().reverse().join("\n") : "Nothing yet.";
}

async function init() {
  const settings = await load();
  $("api-key").value = settings.apiKey || "";
  $("models").value = (settings.models || DEFAULT_MODELS).join("\n");
  $("batch").value = String(settings.batchSize || 4);
  $("sfx").checked = settings.showSfx !== false;
  $("lang").value = settings.targetLanguage || "English";

  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    const url = tab && tab.url ? new URL(tab.url) : null;
    if (url && /^https?:$/.test(url.protocol)) {
      currentHost = url.hostname;
      $("site-host").textContent = currentHost;
      $("site-section").hidden = false;
      renderSite();
    }
  } catch (_) { /* opened as a settings tab — no site to toggle */ }

  renderUsage();
}

$("site-toggle").addEventListener("click", async () => {
  const settings = await load();
  const sites = new Set(settings.enabledSites || []);
  if (sites.has(currentHost)) sites.delete(currentHost);
  else sites.add(currentHost);
  await save({ enabledSites: [...sites] });
  renderSite();
});

$("show-key").addEventListener("click", () => {
  const input = $("api-key");
  input.type = input.type === "password" ? "text" : "password";
});

$("save-key").addEventListener("click", async () => {
  const key = $("api-key").value.trim();
  await save({ apiKey: key });
  status($("key-status"), key ? "Saved." : "Key removed.", "ok");
});

$("test-key").addEventListener("click", async () => {
  const key = $("api-key").value.trim();
  if (!key) return status($("key-status"), "Paste a key first.", "err");
  status($("key-status"), "Checking…");
  const r = await browser.runtime.sendMessage({ type: "testKey", apiKey: key });
  if (!r.ok) return status($("key-status"), "That key didn't work: " + r.error, "err");
  await save({ apiKey: key });
  status($("key-status"), `Key works and is saved. Models available: ${r.models.slice(0, 12).join(", ") || "(none listed)"}`, "ok");
});

$("save-adv").addEventListener("click", async () => {
  const models = $("models").value.split(/[\n,]+/).map((m) => m.trim()).filter(Boolean);
  await save({
    models: models.length ? models : DEFAULT_MODELS,
    batchSize: parseInt($("batch").value, 10) || 4,
    showSfx: $("sfx").checked,
    targetLanguage: $("lang").value.trim() || "English",
  });
  status($("adv-status"), "Saved.", "ok");
});

$("clear-cache").addEventListener("click", async () => {
  await browser.runtime.sendMessage({ type: "clearCache" });
  status($("adv-status"), "Saved translations cleared.", "ok");
});

$("refresh-log").addEventListener("click", renderUsage);

$("reset-quota").addEventListener("click", async () => {
  await browser.runtime.sendMessage({ type: "resetQuota" });
  status($("adv-status"), "Models will be tried again.", "ok");
  renderUsage();
});

init();
