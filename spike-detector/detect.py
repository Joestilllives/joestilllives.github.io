#!/usr/bin/env python3
"""Wikipedia spike detector: find what the world suddenly started reading about.

Compares the latest RECENT hours of Wikipedia pageviews (all languages, desktop +
mobile) with the BASELINE hours before them, corrects for time-of-day traffic
swings per language, and ranks pages by how abnormally fast they are growing.
English results are grouped with their other-language versions so you can tell a
global surge from a purely local one.

Usage: python3 detect.py [--recent 3] [--baseline 24] [--out results.json]
"""
import argparse, gzip, json, math, os, re, subprocess, sys, time, urllib.parse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

DUMPS = "https://dumps.wikimedia.org/other/pageviews"
CACHE = os.environ.get("SPIKE_CACHE", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache"))
UA = "wiki-spike-detector/0.1 (personal research script)"
PROJECT_RE = re.compile(r"^([a-z][a-z0-9-]*)(\.m)?$")  # plain language code = Wikipedia
NAMESPACES = {s.lower() for s in """
Special Spezial Spécial Especial Speciale Speciaal Specjalna Служебная Özel Spesial Istimewa
特別 特殊 특수 Wikipedia Википедия Wikipédia Vikipedi ويكيبيديا विकिपीडिया 维基百科 위키백과
File Datei Fichier Archivo Ficheiro Bestand Plik Файл Dosya ファイル 文件 파일 Image Media
Category Kategorie Catégorie Categoría Categoria Categorie Kategoria Категория Kategori カテゴリ 分类 분류
Template Vorlage Modèle Plantilla Predefinição Sjabloon Szablon Шаблон Şablon テンプレート 模板 틀
User Benutzer Utilisateur Usuario Usuário Utente Gebruiker Użytkownik Участник Kullanıcı 利用者 用户 사용자
Talk Diskussion Discussion Discusión Discussão Discussione Overleg Dyskusja Обсуждение Tartışma
Help Hilfe Aide Ayuda Ajuda Aiuto Pomoc Справка Yardım Portal Portail Портал Module Modul Draft MediaWiki
""".split()}
SKIP_TITLES = {"-", "Main_Page", "Hauptseite", "Wikipédia:Accueil_principal", "Pagina_principale"}


def available_hours(n):
    """Return the n most recent hourly dump file URLs."""
    import datetime as dt
    urls, day = [], dt.datetime.now(dt.timezone.utc).date()
    while len(urls) < n:
        listing = run_curl(f"{DUMPS}/{day:%Y}/{day:%Y-%m}/").decode()
        names = sorted(set(re.findall(rf"pageviews-{day:%Y%m%d}-\d{{6}}\.gz", listing)), reverse=True)
        urls += [f"{DUMPS}/{day:%Y}/{day:%Y-%m}/{x}" for x in names]
        day -= dt.timedelta(days=1)
    return list(reversed(urls[:n]))  # oldest first


def run_curl(url, out=None):
    cmd = ["curl", "-sSfL", "-m", "300", "-A", UA, url] + (["-o", out] if out else [])
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"download failed: {url}: {r.stderr.decode().strip()}")
    return r.stdout


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, url.rsplit("/", 1)[1])
    if not os.path.exists(path):
        run_curl(url, path + ".part")
        os.rename(path + ".part", path)
    return path


def wanted(title):
    if title in SKIP_TITLES:
        return False
    if ":" in title and title.split(":", 1)[0].lower() in NAMESPACES:
        return False
    return True


def read_hour(path, keep=None, min_views=0):
    """Return (per-page views, per-language total views) for one hourly file.
    Desktop and mobile rows are merged. If keep is given, only those pages."""
    pages, totals = {}, {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split(" ")
            if len(parts) < 3:
                continue
            m = PROJECT_RE.match(parts[0])
            if not m:
                continue
            lang, views = m.group(1), int(parts[2])
            totals[lang] = totals.get(lang, 0) + views
            key = (lang, parts[1])
            if keep is not None:
                if key in keep:
                    pages[key] = pages.get(key, 0) + views
            elif views >= min_views or key in pages:
                pages[key] = pages.get(key, 0) + views
    return pages, totals


def _read_recent(path):
    return read_hour(path, min_views=8)


def _read_base(args):
    return read_hour(args[0], keep=args[1])


def enwiki_info(titles):
    """Short descriptions + other-language titles for English pages."""
    info = {t: {"desc": "", "langs": {}} for t in titles}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                  "prop": "description|langlinks", "lllimit": "max",
                  "titles": "|".join(t.replace("_", " ") for t in batch)}
        cont = {}
        while True:
            q = urllib.parse.urlencode({**params, **cont})
            data = None
            for attempt in range(5):  # the API rate-limits bursts (HTTP 429)
                time.sleep(1.0 + 2 ** attempt - 1)
                try:
                    data = json.loads(run_curl(f"https://en.wikipedia.org/w/api.php?{q}&maxlag=5"))
                    break
                except Exception as e:
                    err = e
            if data is None:  # descriptions are optional extras
                print("  (wiki API gave up:", str(err)[-60:], ")", file=sys.stderr)
                break
            back = {}
            for r in data.get("query", {}).get("redirects", []) + data.get("query", {}).get("normalized", []):
                back[r["to"]] = back.get(r["from"], r["from"])
            for p in data.get("query", {}).get("pages", []):
                orig = back.get(p["title"], p["title"]).replace(" ", "_")
                orig = back.get(orig.replace("_", " "), orig).replace(" ", "_")
                if orig not in info:
                    continue
                if p.get("description"):
                    info[orig]["desc"] = p["description"]
                for ll in p.get("langlinks", []):
                    info[orig]["langs"][ll["lang"]] = ll["title"].replace(" ", "_")
            if "continue" not in data:
                break
            cont = data["continue"]
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=3)
    ap.add_argument("--baseline", type=int, default=24)
    ap.add_argument("--min-rate", type=float, default=40, help="min views/hour in recent window")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--out", default="results.json")
    a = ap.parse_args()

    urls = available_hours(a.recent + a.baseline)
    hours = [re.search(r"(\d{8}-\d{2})", u).group(1) for u in urls]
    print(f"Window: {hours[0]} .. {hours[-1]} UTC ({len(urls)} hours)", file=sys.stderr)
    with ThreadPoolExecutor(6) as ex:
        paths = list(ex.map(fetch, urls))
    print("Downloaded.", file=sys.stderr)
    base_paths, recent_paths = paths[:a.baseline], paths[a.baseline:]

    with ProcessPoolExecutor() as ex:
        recent = list(ex.map(_read_recent, recent_paths))
    rsum = {}
    for pages, _ in recent:
        for k, v in pages.items():
            rsum[k] = rsum.get(k, 0) + v
    cand = {k for k, v in rsum.items() if v / a.recent >= a.min_rate and wanted(k[1])}
    print(f"{len(cand)} candidate pages", file=sys.stderr)
    with ProcessPoolExecutor() as ex:
        base = list(ex.map(_read_base, [(p, cand) for p in base_paths]))
    # Re-read recent with the same filter so the hourly series is complete.
    with ProcessPoolExecutor() as ex:
        recent = list(ex.map(_read_base, [(p, cand) for p in recent_paths]))
    hourly = base + recent

    def lang_total(i, lang):
        return hourly[i][1].get(lang, 0)

    results = []
    for key in cand:
        lang, title = key
        series = [h[0].get(key, 0) for h in hourly]
        b, r = series[:a.baseline], series[a.baseline:]
        b_avg, r_avg = sum(b) / len(b), sum(r) / len(r)
        lt_b = sum(lang_total(i, lang) for i in range(a.baseline)) / a.baseline
        lt_r = sum(lang_total(i, lang) for i in range(a.baseline, len(hourly))) / a.recent
        diurnal = (lt_r / lt_b) if lt_b else 1.0          # whole-language traffic swing
        ratio = (r_avg / max(diurnal, 0.2)) / (b_avg + 3)
        if ratio < 4:
            continue
        # Where did it take off? first hour exceeding 3x the baseline rate
        onset = next((hours[i] for i, v in enumerate(series) if v > 3 * (b_avg + 3) and i >= a.baseline - 6), hours[-1])
        last = r[-3:]
        if len(last) == 3 and last[0] < last[1] < last[2] and last[2] > 1.3 * last[0]:
            shape = "climbing"   # still accelerating: the early-warning case
        elif last[-1] < 0.6 * max(last):
            shape = "fading"     # brief burst (TV, quiz answer, viral post)
        else:
            shape = "holding"    # jumped and stayed up (news, a death, an announcement)
        results.append({"shape": shape, "new": b_avg < 0.5, "lang": lang, "title": title, "series": series, "recent_rate": round(r_avg),
                        "base_rate": round(b_avg, 1), "surge": round(ratio, 1), "onset": onset,
                        "score": math.log(ratio) * math.log10(r_avg + 10)})
    results.sort(key=lambda x: -x["score"])

    # Group: English page + its other-language versions that also surged.
    en_titles = [x["title"] for x in results if x["lang"] == "en"][:100]
    info = enwiki_info(en_titles)
    alias = {}
    for t, d in info.items():
        for lg, lt in d["langs"].items():
            alias[(lg, lt)] = t
    groups, by_en = [], {}
    for x in results:
        en = x["title"] if x["lang"] == "en" else alias.get((x["lang"], x["title"]))
        if en and en in by_en:
            g = by_en[en]
            g["also"].append({k: x[k] for k in ("lang", "title", "surge", "recent_rate")})
            g["score"] += 0.35 * x["score"]
            continue
        g = {**x, "also": [], "en_title": en, "desc": info.get(en, {}).get("desc", "") if en else "",
             "languages_total": len(info.get(en, {}).get("langs", {})) + 1 if en else None}
        groups.append(g)
        if en:
            by_en[en] = g
    for g in groups:
        g["died_recently"] = bool(re.search(r"–20\d\d\)", g.get("desc") or "")) and hours[-1][:4] in g["desc"]
        g["reach"] = "global" if len(g["also"]) >= 2 else "local"
    groups.sort(key=lambda g: -g["score"])
    import datetime as dt
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "hours": hours, "recent": a.recent, "baseline": a.baseline, "results": groups[:a.top]}
    with open(a.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for g in groups[:a.top]:
        name = g["title"].replace("_", " ")
        extra = f" +{len(g['also'])} langs" if g["also"] else ""
        print(f"{g['shape']:>8} {g['surge']:>7}x  {g['recent_rate']:>6}/h  {g['lang']:>4}  {name}{extra}  — {g['desc']}")


if __name__ == "__main__":
    main()
