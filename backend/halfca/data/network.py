"""The upstream B2B network an aggregator would see (Follow the Credit).

Tiers sell strictly downwards (tier 3 → 2 → 1 → direct suppliers → the user), so the
graph is a DAG and the only cycles are the rings planted on purpose. Taint signals are
sprinkled sparsely and capped at two per firm (≤ 0.6 own risk), so nothing but a ring
or its customers can reach the 0.7 at-risk line.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from halfca import config

from .factory import Factory
from .model import Firm, InvoicePlan, UpstreamInvoice

BENFORD = [math.log10(1 + 1 / d) for d in range(1, 10)]
UPSTREAM_START = date(2026, 7, 1)
UPSTREAM_END = date(2026, 9, 30)
UPSTREAM_CITIES = (
    "Ludhiana",
    "Ambala",
    "Karnal",
    "Sonipat",
    "Jaipur",
    "Moradabad",
    "Kanpur",
    "Agra",
    "Lucknow",
    "Ghaziabad",
    "Faridabad",
    "Delhi",
)
UPSTREAM_HSN = (
    "7208",
    "7213",
    "7214",
    "7216",
    "7217",
    "7304",
    "7306",
    "7403",
    "7604",
    "3917",
    "3208",
    "2523",
    "7318",
    "7307",
)


@dataclass
class RingSpec:
    names: list[str]
    cities: list[str]
    feeder: int  # index of the ring member that sells into `target`
    target: Firm  # the direct supplier the ring feeds
    feeder_invoices: int = 8


def digit_counts_benford(n: int) -> list[int]:
    """Counts per first digit 1..9 that follow Benford as closely as integers allow."""
    raw = [n * p for p in BENFORD]
    counts = [int(r) for r in raw]
    order = sorted(range(9), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: n - sum(counts)]:
        counts[i] += 1
    return counts


def mad(counts: list[int]) -> float:
    n = sum(counts)
    return sum(abs(c / n - p) for c, p in zip(counts, BENFORD, strict=True)) / 9


def first_digit(value: float) -> int:
    s = f"{abs(value):.6e}"
    return int(s[0])


class NetworkBuilder:
    def __init__(self, f: Factory, as_of: datetime) -> None:
        self.f = f
        self.rng = f.rng
        self.as_of = as_of
        self.firms: list[Firm] = []
        self.invoices: list[UpstreamInvoice] = []
        self._series: dict[str, int] = {}

    # ── firms ──
    def firm(self, name: str | None, tier: int, city: str | None = None, **kw: object) -> Firm:
        name = name or self.f.upstream_name()
        city = city or self.rng.choice(UPSTREAM_CITIES)
        firm = self.f.firm(
            name,
            city,
            "upstream",
            registered_on=self.as_of.date() - timedelta(days=self.rng.randint(800, 5200)),
            prefix=self.f.prefix_for(name),
            **kw,  # type: ignore[arg-type]
        )
        firm.tier = tier
        self.firms.append(firm)
        return firm

    # ── invoices ──
    def _number(self, seller: Firm) -> str:
        if seller.gstin not in self._series:
            self._series[seller.gstin] = self.rng.randint(80, 1800)
        self._series[seller.gstin] += self.rng.randint(1, 9)
        return f"{seller.invoice_prefix}{self._series[seller.gstin]}"

    def _date(self) -> date:
        return self.f.business_day(UPSTREAM_START, UPSTREAM_END)

    def trade(
        self,
        seller: Firm,
        buyer: Firm,
        n: int,
        median: float,
        *,
        values: list[float] | None = None,
        round_to: int = 0,
    ) -> None:
        for i in range(n):
            if values is not None:
                value = values[i]
            else:
                value = self.f.lognormal(median, 0.7, 8_000, 40_00_000)
                if round_to:
                    value = max(round_to, round(value / round_to) * round_to)
            self.invoices.append(
                UpstreamInvoice(
                    seller=seller.gstin,
                    buyer=buyer.gstin,
                    invoice_no=self._number(seller),
                    invoice_date=self._date(),
                    hsn=self.rng.choice(UPSTREAM_HSN),
                    value=round(value, 2),
                )
            )

    def values_with_digits(self, counts: list[int], lo_exp: int = 5) -> list[float]:
        """Invoice values whose first digits follow `counts` (shuffled)."""
        values: list[float] = []
        for d, c in enumerate(counts, start=1):
            for _ in range(c):
                exp = lo_exp + (1 if self.rng.random() < 0.15 and d < 4 else 0)
                values.append(round((d + self.rng.random() * 0.999) * 10**exp, 2))
        self.rng.shuffle(values)
        return values

    # ── network shapes ──
    def tiers(self, direct_suppliers: list[Firm], n1: int, n2: int, n3: int) -> None:
        t1 = [self.firm(None, 1) for _ in range(n1)]
        t2 = [self.firm(None, 2) for _ in range(n2)]
        t3 = [self.firm(None, 3) for _ in range(n3)]
        for buyer in direct_suppliers:
            for seller in self.rng.sample(t1, self.rng.randint(2, 3)):
                self.trade(seller, buyer, self.rng.randint(3, 8), 1_60_000)
        for buyer in t1:
            for seller in self.rng.sample(t2, self.rng.randint(1, 2)):
                self.trade(seller, buyer, self.rng.randint(2, 5), 2_40_000)
        for buyer in t2:
            for seller in self.rng.sample(t3, self.rng.randint(1, 2)):
                self.trade(seller, buyer, self.rng.randint(1, 4), 3_20_000)

    def ring(self, spec: RingSpec) -> list[Firm]:
        members = [
            self.firm(name, 4, city, tags=["ring"])
            for name, city in zip(spec.names, spec.cities, strict=True)
        ]
        k = len(members)
        for i, seller in enumerate(members):
            buyer = members[(i + 1) % k]
            # Circular traders bill big, round amounts to each other.
            self.trade(seller, buyer, self.rng.randint(18, 26), 6_50_000, round_to=5_000)
        self.trade(
            members[spec.feeder], spec.target, spec.feeder_invoices, 5_80_000, round_to=5_000
        )
        return members

    def outside_buyers(self, n: int) -> list[Firm]:
        """Firms that buy from our suppliers but sell nothing we can see (graph leaves)."""
        return [self.firm(None, 0, tags=["peer"]) for _ in range(n)]

    def sales_with_benford(self, seller: Firm, buyers: list[Firm], counts: list[int]) -> None:
        values = self.values_with_digits(counts)
        for v in values:
            self.trade(seller, self.rng.choice(buyers), 1, 0, values=[v])

    # ── aggregator signals ──
    def aggregator_fields(self, firms: list[Firm], invoices_by_seller: Counter[str]) -> None:
        for firm in firms:
            sold = invoices_by_seller.get(firm.gstin, 0)
            firm.ewb_count_90d = max(1, int(sold * self.rng.uniform(0.5, 0.9))) + self.rng.randint(
                2, 30
            )
            firm.turnover_3m_avg = round(
                self.f.lognormal(28_00_000, 0.8, 3_00_000, 4_00_00_000), -3
            )
            firm.turnover_month = round(firm.turnover_3m_avg * self.rng.uniform(0.8, 1.3), -3)

    def sprinkle_signals(self, firms: list[Firm], protected: set[str]) -> None:
        """At most two signals per firm, so own risk never reaches the 0.7 line."""
        candidates = [x for x in firms if x.gstin not in protected]
        counts: Counter[str] = Counter()

        def take(p: float) -> list[Firm]:
            picked = [x for x in candidates if counts[x.gstin] < 2 and self.rng.random() < p]
            for x in picked:
                counts[x.gstin] += 1
            return picked

        for x in take(0.03):
            x.registered_on = self.as_of.date() - timedelta(days=self.rng.randint(20, 85))
        for x in take(0.06):
            x.returns_missed_6m = self.rng.randint(1, 2)
        for x in take(0.03):
            x.turnover_month = round(x.turnover_3m_avg * self.rng.uniform(3.3, 5.0), -3)
        pool = [x for x in candidates if counts[x.gstin] < 2]
        self.rng.shuffle(pool)
        for a, b in zip(pool[0:8:2], pool[1:8:2], strict=False):
            b.address = a.address
            counts[a.gstin] += 1
            counts[b.gstin] += 1


def own_risk_upper_bound(firm: Firm, as_of: date, shared: bool) -> float:
    """Same signals the taint engine scores, for the generator's self-checks."""
    risk = 0.0
    if (as_of - firm.registered_on).days < config.NEW_REG_DAYS:
        risk += config.RISK_NEW_REGISTRATION
    if firm.ewb_count_90d == 0:
        risk += config.RISK_ZERO_EWB
    if firm.turnover_3m_avg and firm.turnover_month > config.TURNOVER_SPIKE * firm.turnover_3m_avg:
        risk += config.RISK_TURNOVER_SPIKE
    if shared:
        risk += config.RISK_SHARED_IDENTITY
    if firm.returns_missed_6m > 0:
        risk += config.RISK_FILING_GAPS
    return min(1.0, risk)


def arora_digits(plans: list[InvoicePlan], gstin: str) -> list[int]:
    counts = [0] * 9
    for p in plans:
        if p.direction == "inward" and p.party.gstin == gstin and p.dup_of is None:
            counts[first_digit(p.total) - 1] += 1
    return counts
