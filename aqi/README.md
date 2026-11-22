# Clear Air Check

Compares India's official AQI (CPCB) with independent sources: the Copernicus CAMS model via Open-Meteo, WAQI and OpenAQ citizen sensors. Every source is recalculated on the Indian AQI scale.

## How data flows

- `.github/workflows/collect-aqi.yml` runs `scripts/collect-aqi.js` every hour.
- It writes `aqi/data/latest.json` (what the page shows) and `aqi/data/history/YYYY-MM.csv` (the 7-day chart).
- If that data is more than 3 hours old, or for "Use my location", the page checks live from the browser instead (Open-Meteo, plus CPCB and WAQI if the visitor added their own keys).

## Setup (one time)

1. Get free keys:
   - **data.gov.in**: sign up at https://data.gov.in, then My Account → API key
   - **WAQI**: https://aqicn.org/data-platform/token/
   - **OpenAQ**: https://explore.openaq.org/register
   - **PurpleAir**: https://develop.purpleair.com/ (a "read" key; new accounts get free credits)
2. In the GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**, add
   `DATA_GOV_IN_KEY`, `WAQI_TOKEN`, `OPENAQ_KEY`, `PURPLEAIR_KEY`.
3. Merge to `master`. Scheduled workflows only run on the default branch.
4. **Actions → Collect AQI data → Run workflow** for a first run instead of waiting up to an hour.

Any missing key just leaves that source out. Open-Meteo needs no key.

## Run locally

```sh
DATA_GOV_IN_KEY=... WAQI_TOKEN=... OPENAQ_KEY=... PURPLEAIR_KEY=... node scripts/collect-aqi.js
python3 -m http.server   # then open http://localhost:8000/aqi/
```
