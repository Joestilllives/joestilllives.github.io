"""Daily closing prices from Yahoo Finance's public chart endpoint (standard library only)."""
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; RippleBot/1.0)"
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"

# Approximate market close in UTC hours, used to decide which close an alert came after.
CLOSE_UTC = {"IN": 10.0, "TW": 5.5, "US": 21.0}


def yahoo_symbol(entity):
    """Map a graph entity to a Yahoo symbol, or None if it has no price."""
    if entity.get("price"):
        return entity["price"]
    t = entity.get("ticker")
    if not t:
        return None
    if t.startswith("NSE:"):
        return t[4:] + ".NS"
    return t


def market_of(symbol):
    if symbol.endswith(".NS") or symbol == "^NSEI":
        return "IN"
    if symbol.endswith(".TW") or symbol == "^TWII":
        return "TW"
    return "US"


def benchmark_of(symbol, benchmarks):
    """Index to subtract for 'excess' returns. Commodities, FX and yields get none."""
    if any(c in symbol for c in "=^"):
        return None
    return benchmarks.get(market_of(symbol))


def fetch_history(symbol, rng="2y", tries=3):
    """Return {'YYYY-MM-DD': close} for a symbol."""
    url = CHART.format(sym=urllib.parse.quote(symbol, safe=""), rng=rng)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            res = data["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            out = {}
            for ts, c in zip(res["timestamp"], closes):
                if c is not None and not math.isnan(c):
                    out[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")] = float(c)
            return out
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{symbol}: {last}")


def fetch_many(symbols, rng="2y"):
    prices, errors = {}, []
    for s in sorted(set(symbols)):
        try:
            prices[s] = fetch_history(s, rng)
        except Exception as e:
            errors.append(str(e))
        time.sleep(0.3)  # be polite
    return prices, errors


def returns(series, invert=False):
    """Daily log returns keyed by date: {date: r} (date = day of the later close)."""
    dates = sorted(series)
    out = {}
    for a, b in zip(dates, dates[1:]):
        pa, pb = series[a], series[b]
        if pa > 0 and pb > 0:
            r = math.log(pb / pa)
            out[b] = -r if invert else r
    return out
