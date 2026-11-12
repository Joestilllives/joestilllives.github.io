# Manga Lens Translator

A Firefox extension (works on **Firefox for Android**) that translates Japanese manga
into English right on the page. English text appears over each speech bubble as you read.
It's free to use: it runs on your own Google Gemini API key's free tier.

- Pages below the screen are translated ahead of time, so they're usually ready when you scroll to them.
- Several pages go in each request, which stretches the free daily limit.
- Pages you've already read are saved on your phone and never re-sent.
- When one AI model's free limit runs out, it switches to the next one.
- It only runs on sites you switch it on for.

**On the page:**
- **あ→A button (bottom-left):** tap it to hide or show all translations. It also shows progress.
- **Tap a bubble** to see the original Japanese underneath. Tap again to bring back the English.

## Setup on Android (one time, about 15 minutes)

### 1. Install Firefox and the pop-up blocker
1. Install **Firefox** from the Play Store.
2. In Firefox, go to **⋮ menu → Extensions → Extensions manager**, find **uBlock Origin**, and tap **+** to add it.
   This handles the pop-ups and ads.

### 2. Get the translator signed by Mozilla (free)
Regular Firefox only installs extensions that Mozilla has signed. Signing is free and automatic.
You can do this on your phone or a computer.

1. Download `dist/manga-lens-translator.zip` from this repository. On GitHub, open the file and tap **Download raw file**.
2. Go to <https://addons.mozilla.org/developers/> and sign in or create a free Firefox account.
3. Tap **Submit a New Add-on**.
4. When asked how to distribute it, choose **On your own**. The add-on stays private and isn't listed in the store.
5. Upload `manga-lens-translator.zip`, tick **Firefox for Android** as a platform, and continue through the steps.
6. After a few minutes, the signed version is ready. Download the **.xpi** file it gives you.

### 3. Install it in Firefox for Android
1. Open Firefox → **Settings → About Firefox**, and tap the Firefox logo **5 times**. This turns on a hidden menu.
2. Go back to **Settings** and tap **Install add-on from file**, then pick the `.xpi` you downloaded.

   If you don't see **Install add-on from file**, install **Firefox Beta** or **Firefox Nightly**
   from the Play Store and do steps 1 and 2 there instead.

### 4. Add your free Gemini key
1. Open <https://aistudio.google.com/apikey>, sign in with a Google account, and tap **Create API key**.
   **Don't add billing.** With no billing set up, you can never be charged. The free limit just resets daily.
2. In Firefox: **⋮ menu → Extensions → Manga Lens Translator**, paste the key, and tap **Test key**.

### 5. Read
Open a chapter on your manga site, then go to **⋮ menu → Extensions → Manga Lens Translator**
and tap **Translate manga on this site**. Translations start appearing within a few seconds.

## Good to know
- **Free limits:** Google changes the free-tier limits from time to time. If you see **limit hit**,
  translations stop until midnight Pacific time. Under **Advanced**, a higher "Pages per request" value stretches the limit further.
- **Privacy:** page images are sent to Google's Gemini API to be translated. On the free tier,
  Google may use that data to improve its products.
- **Accuracy:** dialogue translations are usually good. Hand-drawn sound effects and tiny text are hit-or-miss.
  Tap a bubble to compare it with the original.
- **Reader sites where tapping turns the page:** tapping on a translated bubble peeks at the
  Japanese instead of turning the page. Tap outside the bubbles to turn pages.

## Updating
After changing the code, bump `"version"` in `manifest.json`, run `./build.sh`, and upload the
new zip as a new version on the same add-on page at addons.mozilla.org.

## Files
| File | What it does |
|---|---|
| `content.js` / `content.css` | Runs on the manga page: finds pages, draws the translated bubbles |
| `background.js` | Talks to Gemini, batches pages, caches results, switches models on quota limits |
| `popup.html` / `popup.js` / `popup.css` | Settings screen: per-site switch, API key, usage |
| `build.sh` | Builds `dist/manga-lens-translator.zip` |
