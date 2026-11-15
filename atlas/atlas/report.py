"""Self-contained HTML tearsheet (inline SVG, no plotting libraries)."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd

from .metrics import drawdown


def _svg_line(series: pd.Series, w=860, h=220, color="#2563eb", log=False, fill=False) -> str:
    s = series.dropna()
    if len(s) < 2:
        return ""
    step = max(1, len(s) // 800)
    s = s.iloc[::step]
    y = np.log(s.to_numpy()) if log else s.to_numpy()
    lo, hi = float(y.min()), float(y.max())
    hi = hi if hi > lo else lo + 1e-9
    xs = np.linspace(8, w - 8, len(y))
    ys = h - 8 - (y - lo) / (hi - lo) * (h - 16)
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys))
    area = f'<polygon points="8,{h-8} {pts} {w-8},{h-8}" fill="{color}" opacity="0.15"/>' if fill else ""
    first, last = s.index[0].date(), s.index[-1].date()
    return (f'<svg viewBox="0 0 {w} {h+18}" role="img" style="width:100%;height:auto">{area}'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'<text x="8" y="{h+14}" class="ax">{first}</text>'
            f'<text x="{w-8}" y="{h+14}" text-anchor="end" class="ax">{last}</text></svg>')


def _table(df: pd.DataFrame) -> str:
    return df.to_html(float_format=lambda v: f"{v:,.3f}", border=0, classes="t")


def tearsheet(result, title: str = "Atlas backtest", extra: dict[str, pd.DataFrame] | None = None) -> str:
    st = result.stats
    pct = {"cagr", "vol", "max_drawdown", "hit_rate_daily", "hit_rate_monthly", "worst_day",
           "worst_month", "var_95_daily", "cvar_95_daily", "cost_drag_ann", "psr"}
    tiles = "".join(
        f'<div class="tile"><div class="k">{k.replace("_", " ")}</div><div class="v">'
        f'{(f"{v:.2%}" if k in pct else f"{v:.2f}") if isinstance(v, float) else v}</div></div>'
        for k, v in st.items())
    r = result.returns
    monthly = (1 + r).resample("ME").prod() - 1
    yearly = (1 + r).resample("YE").prod() - 1
    yr = pd.DataFrame({"return": yearly.values}, index=yearly.index.year)
    worst = monthly.nsmallest(5).to_frame("worst months")
    sections = [
        ("Equity (log scale)", _svg_line(result.equity, log=True)),
        ("Drawdown", _svg_line(drawdown(r), color="#dc2626", fill=True)),
        ("Gross leverage", _svg_line(result.weights.abs().sum(axis=1), color="#7c3aed")),
        ("Risk scale (drawdown control x regime)",
         _svg_line(result.exposure_scale * result.regime, color="#059669")),
        ("Calendar-year returns", _table(yr)),
        ("Worst months", _table(worst)),
    ]
    for name, df in (extra or {}).items():
        sections.append((name, _table(df)))
    body = "".join(f"<section><h2>{html.escape(t)}</h2>{c}</section>" for t, c in sections)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#fff;--fg:#111827;--mut:#6b7280;--card:#f3f4f6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b0f17;--fg:#e5e7eb;--mut:#9ca3af;--card:#151b26}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px}}
h1{{font-size:22px}} h2{{font-size:15px;margin:28px 0 8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}}
.tile{{background:var(--card);border-radius:8px;padding:8px 10px}}
.k{{color:var(--mut);font-size:11px;text-transform:uppercase}} .v{{font-size:17px;font-variant-numeric:tabular-nums}}
.ax{{fill:var(--mut);font-size:11px}} table.t{{border-collapse:collapse;font-variant-numeric:tabular-nums}}
table.t td,table.t th{{padding:3px 10px;text-align:right;border-bottom:1px solid var(--card)}}
</style></head><body><h1>{html.escape(title)}</h1><div class="grid">{tiles}</div>{body}</body></html>"""
