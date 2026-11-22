"""Morning trade signal for the next Indian session, from last night's US close.

Rule (from backtest.py, judged on unseen data):
  Accenture's daily move MINUS the S&P 500's move ("beyond the market").
  >= +1.5%  -> LONG the Indian IT basket at the 09:15 open, exit at the close
  <= -1.5%  -> SHORT (intraday) the basket at the open, exit at the close
  otherwise -> no trade
Runs around 02:45 UTC (08:15 IST), after the US close and before India opens.

    python signal_today.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from prices import fetch_history

HERE = Path(__file__).parent
OUT = HERE / "output"
THRESHOLD = 0.015
BASKET = ["TCS", "Infosys", "Wipro", "HCLTech", "Tech Mahindra"]
STRONG = 0.03  # raw Accenture move that also qualified in the trade test


def compute(acn, spx):
    """acn, spx: {date: close}. Returns the signal for the latest common US session."""
    days = sorted(set(acn) & set(spx))
    if len(days) < 2:
        raise ValueError("not enough price history")
    prev, last = days[-2], days[-1]
    a = acn[last] / acn[prev] - 1
    s = spx[last] / spx[prev] - 1
    excess = a - s
    action = "LONG" if excess >= THRESHOLD else "SHORT" if excess <= -THRESHOLD else "NONE"
    if action == "NONE":
        why = f"Accenture moved {excess*100:+.2f}% beyond the S&P 500 — inside the ±{THRESHOLD*100:.1f}% band, so no trade."
    else:
        verb = "buy" if action == "LONG" else "short (intraday)"
        why = (f"Accenture moved {excess*100:+.2f}% beyond the S&P 500 (Accenture {a*100:+.2f}%, S&P {s*100:+.2f}%). "
               f"Rule: {verb} the Indian IT basket at the 9:15 open, exit by the close.")
    return {
        "us_session": last, "accenture_pct": round(a * 100, 2), "sp500_pct": round(s * 100, 2),
        "excess_pct": round(excess * 100, 2), "threshold_pct": THRESHOLD * 100, "action": action,
        "strong": abs(a) >= STRONG and action != "NONE" and (a > 0) == (action == "LONG"),
        "basket": BASKET, "explanation": why,
    }


def main():
    acn, spx = fetch_history("ACN", "1mo"), fetch_history("^GSPC", "1mo")
    sig = compute(acn, spx)
    sig["generated"] = datetime.now(timezone.utc).isoformat()
    sig["disclaimer"] = "Based on past prices; edges fade. Paper-trade first. Not investment advice."
    OUT.mkdir(exist_ok=True)
    path = OUT / "signal.json"
    hist_path = OUT / "signal_history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    if not history or history[-1]["us_session"] != sig["us_session"]:
        history.append({k: sig[k] for k in ("us_session", "accenture_pct", "sp500_pct", "excess_pct", "action")})
    hist_path.write_text(json.dumps(history[-500:], indent=0), encoding="utf-8")
    path.write_text(json.dumps(sig, indent=1), encoding="utf-8")
    print(sig["action"], "-", sig["explanation"])


if __name__ == "__main__":
    main()
