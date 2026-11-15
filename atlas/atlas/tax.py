"""Capital-gains tax ledger (Indian resident individual; rules as of FY2025-26).

Taxes are a cost like any other, and for a strategy that turns its book over
several times a year they are the largest one. The ledger keeps FIFO lots per
instrument, classifies each realised gain, and settles tax at each financial
year end (31 March), paid out of the account.

Classes (set per symbol in config):
  equity  listed equity ETFs: STCG 20% (<12 months), LTCG 12.5% above the
          annual exemption (Rs 1.25 lakh)
  other   gold/silver/international ETFs: short-term at slab rate,
          long-term (>=12 months) 12.5%, no exemption
  debt    debt ETFs bought after 1 Apr 2023: slab rate regardless of holding
Interest on idle cash (a liquid fund) is taxed at the slab rate.

Losses: short-term losses offset any gains (highest-taxed first); long-term
losses offset long-term gains only; unused losses carry forward. Today's rules
are applied to the whole history. That is the right estimate of what the
strategy would cost to run *from now on*.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd

LONG_TERM_DAYS = 365


@dataclass
class TaxConfig:
    stcg_equity: float = 0.20
    ltcg: float = 0.125
    slab: float = 0.312                 # 30% + 4% cess
    exemption: float = 125_000.0         # equity LTCG, per financial year
    classes: dict = field(default_factory=dict)   # symbol -> "equity" | "other" | "debt"
    default_class: str = "equity"

    @classmethod
    def from_cfg(cls, tcfg: dict) -> "TaxConfig":
        classes = {}
        for cls_name in ("equity", "other", "debt"):
            for s in tcfg.get(cls_name, []):
                classes[s] = cls_name
        return cls(tcfg.get("stcg_equity", 0.20), tcfg.get("ltcg", 0.125), tcfg.get("slab", 0.312),
                   tcfg.get("exemption", 125_000.0), classes, tcfg.get("default_class", "equity"))


def financial_year(d: pd.Timestamp) -> int:
    """FY label = calendar year in which the FY ends (FY Apr-2025..Mar-2026 -> 2026)."""
    return d.year + 1 if d.month >= 4 else d.year


class TaxLedger:
    def __init__(self, cfg: TaxConfig):
        self.cfg = cfg
        self.lots: dict[str, deque] = defaultdict(deque)   # symbol -> deque[[units, cost, date]]
        # realised this FY, by bucket
        self.gains = defaultdict(float)
        self.interest = 0.0
        self.st_loss_cf = 0.0
        self.lt_loss_cf = 0.0
        self.paid: dict[int, float] = {}

    def _bucket(self, sym: str, held_days: int) -> str:
        c = self.cfg.classes.get(sym, self.cfg.default_class)
        lt = held_days >= LONG_TERM_DAYS
        if c == "debt":
            return "slab"
        if c == "equity":
            return "eq_lt" if lt else "eq_st"
        return "oth_lt" if lt else "slab"

    def buy(self, sym: str, units: float, price: float, date: pd.Timestamp) -> None:
        if units > 0:
            self.lots[sym].append([units, price, date])

    def sell(self, sym: str, units: float, price: float, date: pd.Timestamp) -> None:
        q = self.lots[sym]
        while units > 1e-12 and q:
            lot = q[0]
            take = min(units, lot[0])
            gain = take * (price - lot[1])
            self.gains[self._bucket(sym, (date - lot[2]).days)] += gain
            lot[0] -= take
            units -= take
            if lot[0] <= 1e-12:
                q.popleft()

    def add_interest(self, amount: float) -> None:
        if amount > 0:
            self.interest += amount

    def unrealised_gain(self, prices: dict) -> float:
        return sum(u * (prices.get(s, c) - c) for s, q in self.lots.items() for u, c, _ in q)

    def settle(self, fy: int) -> float:
        """Compute and record tax for the year just ended; reset the year's buckets."""
        c = self.cfg
        rate = {"slab": c.slab, "eq_st": c.stcg_equity, "eq_lt": c.ltcg, "oth_lt": c.ltcg}
        st = {k: self.gains[k] for k in ("slab", "eq_st")}
        lt = {k: self.gains[k] for k in ("eq_lt", "oth_lt")}
        st_loss = -sum(v for v in st.values() if v < 0) + self.st_loss_cf
        lt_loss = -sum(v for v in lt.values() if v < 0) + self.lt_loss_cf
        st = {k: max(v, 0.0) for k, v in st.items()}
        lt = {k: max(v, 0.0) for k, v in lt.items()}
        # LT losses -> LT gains only (higher-taxed first: equal rates here)
        for k in ("oth_lt", "eq_lt"):
            use = min(lt_loss, lt[k]); lt[k] -= use; lt_loss -= use
        # ST losses -> any gains, highest rate first
        pools = sorted([("slab", st), ("eq_st", st), ("oth_lt", lt), ("eq_lt", lt)],
                       key=lambda kv: -rate[kv[0]])
        for k, d in pools:
            use = min(st_loss, d[k]); d[k] -= use; st_loss -= use
        lt["eq_lt"] = max(lt["eq_lt"] - c.exemption, 0.0)
        tax = sum(st[k] * rate[k] for k in st) + sum(lt[k] * rate[k] for k in lt) + self.interest * c.slab
        self.st_loss_cf, self.lt_loss_cf = st_loss, lt_loss
        self.gains.clear()
        self.interest = 0.0
        self.paid[fy] = tax
        return tax


def buy_and_hold_after_tax(returns: pd.Series, capital: float, cfg: TaxConfig, cls: str = "equity") -> float:
    """Annualised after-tax return of buying once and selling at the end."""
    growth = float((1 + returns).prod())
    gain = capital * (growth - 1)
    years = len(returns) / 252
    if gain > 0:
        rate = cfg.ltcg if years >= 1 else (cfg.stcg_equity if cls == "equity" else cfg.slab)
        taxable = max(gain - (cfg.exemption if cls == "equity" else 0.0), 0.0)
        gain -= taxable * rate
    return (1 + gain / capital) ** (1 / years) - 1
