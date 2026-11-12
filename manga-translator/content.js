/* Manga Lens Translator — content script.
 *
 * Finds manga page images on sites you've switched it on for, sends them to the
 * background script (which talks to Gemini), and draws the English text over
 * each speech bubble. Pages below the screen are translated ahead of time so
 * they're usually ready by the time you scroll to them.
 */
(() => {
  "use strict";
  if (window.__mangaLensLoaded) return;
  window.__mangaLensLoaded = true;

  const MIN_NATURAL = 300;     // px — smaller images are icons/thumbnails, not pages
  const MIN_DISPLAY = 150;     // px on screen
  const MAX_PREPARING = 3;     // images being downloaded/resized at once
  const LOOKAHEAD = "1500px 0px 5000px 0px"; // translate pages this far below the screen

  const host = location.hostname;
  let active = false;
  let overlaysOn = true;

  /** @type {Map<HTMLImageElement, {src:string,status:string,layer?:HTMLElement,bubbles?:any[],error?:string,code?:string,lastW?:number,lastH?:number}>} */
  const records = new Map();
  const waiting = new Set(); // images that are near the screen and ready to send
  let preparing = 0;
  let root = null;
  let pill = null;
  let io = null;
  let mo = null;
  let ro = null;
  let tick = null;

  // ------------------------------------------------------------- activation

  async function refreshActive() {
    let settings = {};
    try {
      ({ settings = {} } = await browser.storage.local.get("settings"));
    } catch (_) { return; }
    const want = (settings.enabledSites || []).includes(host);
    if (want && !active) start();
    else if (!want && active) stop();
  }

  browser.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.settings) refreshActive();
  });

  function start() {
    active = true;
    root = document.createElement("div");
    root.id = "mlt-root";
    document.documentElement.appendChild(root);

    pill = document.createElement("div");
    pill.className = "mlt-pill";
    pill.addEventListener("click", onPillClick);
    root.appendChild(pill);

    io = new IntersectionObserver(onIntersect, { rootMargin: LOOKAHEAD });
    ro = new ResizeObserver(scheduleLayout);
    mo = new MutationObserver(onMutations);
    mo.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src", "srcset"],
    });
    document.querySelectorAll("img").forEach(watchImage);

    window.addEventListener("scroll", scheduleLayout, { capture: true, passive: true });
    window.addEventListener("resize", scheduleLayout, { passive: true });
    tick = setInterval(layoutAll, 1000); // catches layout shifts nothing else tells us about
    updatePill();
  }

  function stop() {
    active = false;
    io && io.disconnect();
    ro && ro.disconnect();
    mo && mo.disconnect();
    clearInterval(tick);
    window.removeEventListener("scroll", scheduleLayout, { capture: true });
    window.removeEventListener("resize", scheduleLayout);
    root && root.remove();
    root = pill = io = ro = mo = null;
    records.clear();
    waiting.clear();
  }

  // --------------------------------------------------------- image tracking

  function watchImage(img) {
    if (!(img instanceof HTMLImageElement) || !io) return;
    if (root && root.contains(img)) return;
    io.observe(img);
  }

  function onMutations(muts) {
    for (const m of muts) {
      if (m.type === "attributes") {
        const img = m.target;
        const rec = records.get(img);
        // Lazy loaders and page readers swap src on the same <img>.
        if (rec && rec.src !== (img.currentSrc || img.src)) dropRecord(img);
        if (!records.has(img) && img instanceof HTMLImageElement) {
          io.unobserve(img);
          io.observe(img);
        }
        continue;
      }
      m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.tagName === "IMG") watchImage(n);
        else if (n.querySelectorAll) n.querySelectorAll("img").forEach(watchImage);
      });
      m.removedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        for (const img of [...records.keys()]) {
          if (n === img || (n.contains && n.contains(img))) dropRecord(img);
        }
      });
    }
  }

  function dropRecord(img) {
    const rec = records.get(img);
    if (rec && rec.layer) rec.layer.remove();
    records.delete(img);
    waiting.delete(img);
    ro && ro.unobserve(img);
    updatePill();
  }

  function isPage(img) {
    const src = img.currentSrc || img.src;
    if (!src || src.startsWith("data:image/svg") || /\.svg(\?|$)/i.test(src)) return false;
    if (img.naturalWidth < MIN_NATURAL || img.naturalHeight < MIN_NATURAL) return false;
    const r = img.getBoundingClientRect();
    return r.width >= MIN_DISPLAY && r.height >= MIN_DISPLAY;
  }

  function onIntersect(entries) {
    for (const e of entries) {
      const img = e.target;
      if (!e.isIntersecting) { waiting.delete(img); continue; }
      if (records.has(img)) continue;
      if (img.complete && img.naturalWidth && isPage(img)) consider(img);
      else img.addEventListener("load", () => consider(img), { once: true });
    }
  }

  function consider(img) {
    if (!active || records.has(img) || !isPage(img)) return;
    waiting.add(img);
    pump();
  }

  // Send the waiting image closest to the current screen position first.
  function pump() {
    while (preparing < MAX_PREPARING && waiting.size) {
      let best = null;
      let bestDist = Infinity;
      for (const img of waiting) {
        const r = img.getBoundingClientRect();
        const dist = r.bottom < 0 ? -r.bottom + 2000 : Math.max(0, r.top); // prefer on-screen and below
        if (dist < bestDist) { bestDist = dist; best = img; }
      }
      waiting.delete(best);
      if (!best.isConnected || records.has(best)) continue;
      translateImage(best);
    }
  }

  // --------------------------------------------------------- image capture

  async function blobToJpegBase64(blob) {
    const bmp = await createImageBitmap(blob);
    const { width: w, height: h } = bmp;
    // Keep text legible: shrink big pages, but never squash a tall webtoon strip too narrow.
    let scale = Math.min(1, 1600 / Math.max(w, h));
    scale = Math.max(scale, Math.min(1, 900 / w));
    scale = Math.min(scale, Math.sqrt(8e6 / (w * h)), 1);
    const cw = Math.max(1, Math.round(w * scale));
    const ch = Math.max(1, Math.round(h * scale));
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cw, ch);
    ctx.drawImage(bmp, 0, 0, cw, ch);
    bmp.close && bmp.close();
    return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
  }

  async function captureImage(img, src) {
    // 1. Fetch it ourselves (usually served straight from the browser cache).
    try {
      const res = await fetch(src, { credentials: "include" });
      if (res.ok) return await blobToJpegBase64(await res.blob());
    } catch (_) { /* fall through */ }
    // 2. Ask the background script (different network context, no CORS).
    try {
      const r = await browser.runtime.sendMessage({ type: "fetchImage", src, referrer: location.href });
      if (r && r.dataUrl) return await blobToJpegBase64(await (await fetch(r.dataUrl)).blob());
    } catch (_) { /* fall through */ }
    // 3. Copy the pixels already on screen (fails if the site blocks it).
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext("2d").drawImage(img, 0, 0);
    const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
    if (!blob) throw new Error("Couldn't read this image.");
    return await blobToJpegBase64(blob);
  }

  async function translateImage(img) {
    const src = img.currentSrc || img.src;
    const rec = { src, status: "working" };
    records.set(img, rec);
    ensureLayer(img, rec);
    updatePill();
    preparing++;
    let image;
    try {
      image = await captureImage(img, src);
    } catch (e) {
      preparing--;
      return finish(img, rec, { ok: false, code: "image", error: "Couldn't read this page image." });
    }
    preparing--;
    pump();
    let result;
    try {
      result = await browser.runtime.sendMessage({ type: "translate", src, image, mime: "image/jpeg" });
    } catch (e) {
      result = { ok: false, code: "other", error: String(e.message || e) };
    }
    finish(img, rec, result);
  }

  function finish(img, rec, result) {
    if (records.get(img) !== rec) return; // image was swapped while we worked
    if (result && result.ok) {
      rec.status = "done";
      rec.bubbles = result.bubbles;
    } else {
      rec.status = "error";
      rec.code = result && result.code;
      rec.error = (result && result.error) || "Translation failed.";
    }
    renderBubbles(img, rec);
    updatePill();
  }

  // --------------------------------------------------------------- overlay

  function ensureLayer(img, rec) {
    if (rec.layer) return;
    const layer = document.createElement("div");
    layer.className = "mlt-layer";
    const badge = document.createElement("div");
    badge.className = "mlt-badge";
    badge.textContent = "Translating…";
    layer.appendChild(badge);
    root.appendChild(layer);
    rec.layer = layer;
    ro.observe(img);
    positionLayer(img, rec);
  }

  function renderBubbles(img, rec) {
    const layer = rec.layer;
    if (!layer) return;
    layer.replaceChildren();
    if (rec.status === "error") {
      const badge = document.createElement("div");
      badge.className = "mlt-badge mlt-badge-error";
      badge.textContent = rec.code === "quota" || rec.code === "nokey" || rec.code === "badkey"
        ? rec.error
        : rec.error + " Tap to retry.";
      badge.addEventListener("click", (ev) => {
        ev.stopPropagation();
        ev.preventDefault();
        if (rec.code === "nokey" || rec.code === "badkey") {
          browser.runtime.sendMessage({ type: "openSettings" });
          return;
        }
        dropRecord(img);
        consider(img);
      });
      layer.appendChild(badge);
      return;
    }
    for (const b of rec.bubbles || []) {
      const [y0, x0, y1, x1] = b.box;
      const el = document.createElement("div");
      el.className = "mlt-bubble mlt-" + (b.kind || "speech");
      el.style.left = x0 / 10 + "%";
      el.style.top = y0 / 10 + "%";
      el.style.width = (x1 - x0) / 10 + "%";
      el.style.height = (y1 - y0) / 10 + "%";
      const span = document.createElement("span");
      span.className = "mlt-text";
      span.textContent = b.text;
      el.appendChild(span);
      el.title = b.ja || "";
      // Tap a bubble to peek at the original Japanese underneath.
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        ev.preventDefault();
        el.classList.toggle("mlt-peek");
      });
      layer.appendChild(el);
    }
    rec.lastW = rec.lastH = 0;
    positionLayer(img, rec);
  }

  function fitText(bubble) {
    const span = bubble.firstChild;
    if (!span) return;
    const W = bubble.offsetWidth;
    const H = bubble.offsetHeight;
    if (!W || !H) return;
    // Rounded bubbles lose their corners, so keep text inside the inner area.
    const rounded = /mlt-(speech|thought)/.test(bubble.className);
    const px = rounded ? W * 0.13 : 3;
    const py = rounded ? H * 0.11 : 2;
    bubble.style.padding = py + "px " + px + "px";
    const iw = W - 2 * px;
    const ih = H - 2 * py;
    const fits = () => span.scrollHeight <= ih + 0.5 && span.scrollWidth <= iw + 0.5;
    // First try without breaking words; only split words if nothing else fits.
    span.style.overflowWrap = "normal";
    let lo = 6;
    let hi = Math.max(7, Math.min(32, ih * 0.6, iw * 0.5));
    while (hi - lo > 0.5) {
      const mid = (lo + hi) / 2;
      span.style.fontSize = mid + "px";
      if (fits()) lo = mid;
      else hi = mid;
    }
    span.style.fontSize = lo + "px";
    if (!fits()) span.style.overflowWrap = "anywhere";
  }

  function positionLayer(img, rec) {
    const layer = rec.layer;
    if (!layer) return;
    if (!img.isConnected) { dropRecord(img); return; }
    const r = img.getBoundingClientRect();
    const visible = r.width > 0 && r.height > 0 && getComputedStyle(img).visibility !== "hidden";
    layer.style.display = visible && overlaysOn ? "block" : "none";
    if (!visible) return;
    layer.style.left = r.left + window.scrollX + "px";
    layer.style.top = r.top + window.scrollY + "px";
    layer.style.width = r.width + "px";
    layer.style.height = r.height + "px";
    if (Math.abs((rec.lastW || 0) - r.width) > 1 || Math.abs((rec.lastH || 0) - r.height) > 1) {
      rec.lastW = r.width;
      rec.lastH = r.height;
      layer.querySelectorAll(".mlt-bubble").forEach(fitText);
    }
  }

  let layoutQueued = false;
  function scheduleLayout() {
    if (layoutQueued) return;
    layoutQueued = true;
    requestAnimationFrame(() => {
      layoutQueued = false;
      layoutAll();
    });
  }

  function layoutAll() {
    if (!active) return;
    for (const [img, rec] of records) positionLayer(img, rec);
  }

  // ------------------------------------------------------------ status pill

  function updatePill() {
    if (!pill) return;
    let working = 0, done = 0, err = null;
    for (const rec of records.values()) {
      if (rec.status === "working") working++;
      else if (rec.status === "done") done++;
      else if (rec.status === "error") err = err || rec;
    }
    pill.classList.toggle("mlt-pill-off", !overlaysOn);
    pill.classList.toggle("mlt-pill-error", !!err && !working);
    if (!overlaysOn) pill.textContent = "あ→A off";
    else if (working) pill.textContent = `あ→A ${working}…`;
    else if (err && (err.code === "nokey" || err.code === "badkey")) pill.textContent = "あ→A set key";
    else if (err && err.code === "quota") pill.textContent = "あ→A limit hit";
    else pill.textContent = done ? `あ→A ✓${done}` : "あ→A";
  }

  function onPillClick(ev) {
    ev.stopPropagation();
    for (const rec of records.values()) {
      if (rec.status === "error" && (rec.code === "nokey" || rec.code === "badkey")) {
        browser.runtime.sendMessage({ type: "openSettings" });
        return;
      }
    }
    overlaysOn = !overlaysOn;
    layoutAll();
    updatePill();
  }

  // When the key gets added, retry pages that failed for that reason.
  browser.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.settings || !active) return;
    const before = (changes.settings.oldValue || {}).apiKey;
    const after = (changes.settings.newValue || {}).apiKey;
    if (before === after) return;
    for (const [img, rec] of [...records]) {
      if (rec.status === "error") { dropRecord(img); consider(img); }
    }
  });

  refreshActive();
})();
