#!/usr/bin/env python3
"""Headline sentiment -> stock returns, using FinBERT (ONNX, int8) on Moneycontrol headlines.

Each headline gets tone = P(positive) - P(negative). Headlines naming a company (from the
Wikipedia-matched list) are linked to it. News after the 15:30 close counts for the next
trading day (day D). We measure the stock's move on D (already priced?), then D+1 and D+5
after D's close (tradable), against the average liquid company.

Usage: python3 news_sentiment.py MODEL_DIR NEWS.parquet ARTICLES.csv PANEL.pkl FUNDS.txt OUTDIR
"""
import csv, json, os, re, sys, urllib.parse
import numpy as np
import pandas as pd
import onnxruntime as ort
from tokenizers import Tokenizer
from backtest import prepare


def score(model_dir, texts, batch=64):
    tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
    tok.enable_truncation(64)
    tok.enable_padding(length=64)
    sess = ort.InferenceSession(os.path.join(model_dir, "model_quantized.onnx"), providers=["CPUExecutionProvider"])
    labels = json.load(open(os.path.join(model_dir, "config.json")))["id2label"]
    names = [i.name for i in sess.get_inputs()]
    out = []
    for i in range(0, len(texts), batch):
        enc = tok.encode_batch(texts[i:i + batch])
        feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
        logits = sess.run(None, feed)[0]
        prob = np.exp(logits - logits.max(1, keepdims=True)); prob /= prob.sum(1, keepdims=True)
        out.append(prob)
    prob = np.vstack(out)
    lab = {int(k): v.lower() for k, v in labels.items()}
    pos = [k for k, v in lab.items() if v.startswith("pos")][0]
    neg = [k for k, v in lab.items() if v.startswith("neg")][0]
    return prob[:, pos] - prob[:, neg]


def company_patterns(articles_csv):
    pats = {}
    for r in csv.DictReader(open(articles_csv)):
        n = urllib.parse.unquote(r["article"]).replace("_", " ")
        n = re.sub(r"\s*\(.*?\)", "", n)
        n = re.sub(r"\b(Limited|Ltd\.?|Company|Corporation of India|Industries)\b", "", n).strip(" ,.")
        if len(n) < 4:
            continue
        pats[r["symbol"]] = re.compile(r"\b" + re.escape(n) + r"\b", re.I)
    return pats


def main(model_dir, news_pq, articles_csv, panel, funds_txt, outdir):
    os.makedirs(outdir, exist_ok=True)
    news = pd.read_parquet(news_pq)
    news["t"] = pd.to_datetime(news["article datetime"], errors="coerce")
    news = news.dropna(subset=["t", "title"]).drop_duplicates("title")
    cache = os.path.join(outdir, "scored.pkl")
    if os.path.exists(cache):
        news = pd.read_pickle(cache)
    else:
        news["tone"] = score(model_dir, news["title"].astype(str).tolist())
        news.to_pickle(cache)
    print(f"{len(news)} headlines scored, {news.t.min():%d %b %Y}..{news.t.max():%d %b %Y}; "
          f"positive {np.mean(news.tone > 0.5)*100:.0f}%, negative {np.mean(news.tone < -0.5)*100:.0f}%")
    pats = company_patterns(articles_csv)
    links = [(s, i) for i, title in zip(news.index, news["title"]) for s, pat in pats.items() if pat.search(title)]
    L = pd.DataFrame(links, columns=["symbol", "idx"]).join(news[["t", "tone", "title"]], on="idx")
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    mkt = np.log1p(p[p["liquid"]].groupby("date")["ret"].mean()).cumsum().reindex(lp.index).ffill()
    dates = lp.index
    # trading day D: same day if before 15:30, else the next trading day
    after_close = (L["t"].dt.hour * 60 + L["t"].dt.minute) >= 15 * 60 + 30
    day = L["t"].dt.normalize() + pd.to_timedelta(after_close.astype(int), unit="D")
    L["k"] = dates.searchsorted(day)
    g = L.groupby(["symbol", "k"]).agg(tone=("tone", "mean"), n=("tone", "size"), title=("title", "first")).reset_index()
    rows = []
    for r in g.itertuples():
        if r.symbol not in lp or r.k < 1 or r.k + 5 >= len(dates):
            continue
        s, k = lp[r.symbol], r.k
        ex = lambda a, b: np.expm1(s.iloc[b] - s.iloc[a]) - np.expm1(mkt.iloc[b] - mkt.iloc[a])
        rows.append({"symbol": r.symbol, "date": dates[k].date(), "tone": r.tone, "headlines": r.n, "title": r.title,
                     "news_day": ex(k - 1, k), "next_day": ex(k, k + 1), "next_week": ex(k, k + 5)})
    ev = pd.DataFrame(rows)
    ev.to_csv(os.path.join(outdir, "company_news_events.csv"), index=False)
    ev["mood"] = pd.cut(ev["tone"], [-1.01, -0.5, -0.1, 0.1, 0.5, 1.01],
                        labels=["very negative", "negative", "neutral", "positive", "very positive"])
    print(f"{len(ev)} company-days with news ({ev.symbol.nunique()} companies). Excess return vs market:")
    print(f"{'tone':14} {'n':>5} {'news day':>9} {'next day':>9} {'next week':>10} {'next week right':>16}")
    for m, gg in ev.groupby("mood", observed=True):
        right = (np.sign(gg.next_week) == (1 if "positive" in m else -1)).mean() if m != "neutral" else np.nan
        print(f"{m:14} {len(gg):5} {gg.news_day.mean()*100:+8.2f}% {gg.next_day.mean()*100:+8.2f}% {gg.next_week.mean()*100:+9.2f}% {right*100:15.0f}%")
    for c in ["news_day", "next_day", "next_week"]:
        print(f"rank corr tone vs {c}: {ev.tone.corr(ev[c], method='spearman'):+.3f}")
    # whole-market tone -> next-day market
    news["k"] = dates.searchsorted(news["t"].dt.normalize() + pd.to_timedelta(((news["t"].dt.hour*60+news["t"].dt.minute) >= 930).astype(int), unit="D"))
    daily = news.groupby("k")["tone"].mean()
    m1 = mkt.diff().shift(-1)
    md = pd.DataFrame({"tone": daily, "next": [m1.iloc[k] if k < len(m1) else np.nan for k in daily.index]}).dropna()
    print(f"whole-market: {len(md)} days, corr(day's average headline tone, next day's market) {md.tone.corr(md.next):+.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
