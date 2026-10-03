"""Random mode: a fresh month with discrepancies injected at the catalogue rates.

Every injected record carries a truth label (D01..D16), so `make eval` can score the
engines' precision and recall per type. Each invoice gets at most one invoice-level
injection, which keeps the labels unambiguous.
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta

from halfca import config

from . import hsn as hsn_table
from . import routes as geo
from .factory import Factory
from .model import Firm, InvoicePlan, OrphanPayment, Trip, World
from .network import NetworkBuilder, RingSpec
from .plans import PlanMaker
from .scenario_demo import AS_OF, END, IST, START

# Per-invoice injection rates (CLAUDE.md discrepancy catalogue).
RATES: dict[str, float] = {
    "D01": 0.020,
    "D02": 0.010,
    "D03": 0.020,
    "D04": 0.015,
    "D05": 0.010,
    "D06": 0.005,
    "D07": 0.005,
    "D08": 0.008,
    "D09": 0.020,
    "D10": 0.015,
    "D11": 0.005,
    "D12": 0.003,
    "D13": 0.002,
    "D14": 0.003,
}
INWARD_ONLY = {"D07", "D08", "D10", "D11", "D12", "D13", "D14"}
ROAD = {"D11", "D12", "D13", "D14"}

SUPPLIER_CITIES = [
    "Delhi",
    "Ludhiana",
    "Ambala",
    "Karnal",
    "Jaipur",
    "Moradabad",
    "Kanpur",
    "Agra",
    "Lucknow",
]
CUSTOMER_CITIES = ["Delhi"] * 8 + ["Gurugram", "Faridabad", "Noida", "Ghaziabad", "Sonipat"]
RING_NAMES = [
    ["Orbit Tradelinks", "Sarthak Impex", "Velocity Metals", "Ishan Commerce", "Quark Ventures"],
    ["Pinnacle Overseas", "Rudraksh Traders", "Vistar Alloys", "Neev Enterprises"],
]


class RandomBuilder:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.f = Factory(self.rng)
        self.f.reserve(config.USER_NAME, *(n for ring in RING_NAMES for n in ring))
        self.me = self.f.firm(
            config.USER_NAME,
            "Delhi",
            "self",
            registered_on=date(2017, 7, 1),
            prefix="AR/S/",
            pan="AAKFA4821M",
            gstin=config.USER_GSTIN,
        )
        self.pm = PlanMaker(self.f, self.me)
        old = lambda: AS_OF.date() - timedelta(days=self.rng.randint(1500, 6000))  # noqa: E731
        self.suppliers = []
        for _ in range(45):
            name = self.f.supplier_name()
            self.suppliers.append(
                self.f.firm(
                    name,
                    self.rng.choice(SUPPLIER_CITIES),
                    "supplier",
                    registered_on=old(),
                    prefix=self.f.prefix_for(name),
                )
            )
        self.customers = [
            self.f.firm(
                self.f.customer_name(),
                self.rng.choice(CUSTOMER_CITIES),
                "customer",
                registered_on=old(),
            )
            for _ in range(75)
        ]
        self.plans: list[InvoicePlan] = []
        self.orphans: list[OrphanPayment] = []
        self.hugger = self.rng.choice([s for s in self.suppliers if s.city != "Delhi"])
        self.ring_fed = self.rng.sample([s for s in self.suppliers if s is not self.hugger], 2)

    def day(self) -> date:
        return self.f.business_day(START, END)

    def eligible(self, p: InvoicePlan) -> bool:
        return p.direction == "inward" and p.inter_state and p.total >= config.EWB_THRESHOLD

    # ── base invoices ──
    def base(self) -> None:
        for _ in range(225):
            sup = self.rng.choice(self.suppliers)
            taxable = self.f.taxable_amount(30_000, sigma=0.95)
            if sup is self.hugger and self.rng.random() < 0.45:
                taxable = self.rng.uniform(45_000, 49_990) / (1 + 0.18)  # just under ₹50,000
                p = self.pm.make(
                    "inward",
                    sup,
                    self.pm.next_number(sup),
                    self.day(),
                    taxable,
                    self.rng.choice(["7318", "7307", "8481"]),
                    labels=["D16"],
                )
            else:
                p = self.pm.make("inward", sup, self.pm.next_number(sup), self.day(), taxable)
            if sup in self.ring_fed:
                p.labels.append("D15")
            self.plans.append(p)
        # D16: one supplier keeps billing just under the e-way bill threshold.
        for _ in range(8):
            taxable = self.rng.uniform(45_000, 49_990) / 1.18
            self.plans.append(
                self.pm.make(
                    "inward",
                    self.hugger,
                    self.pm.next_number(self.hugger),
                    self.day(),
                    taxable,
                    self.rng.choice(["7318", "7307", "8481"]),
                    labels=["D16"],
                )
            )
        outward_days = sorted(self.day() for _ in range(330))
        for i, d in enumerate(outward_days):
            self.plans.append(
                self.pm.make(
                    "outward",
                    self.rng.choice(self.customers),
                    f"AR/S/{2001 + i}",
                    d,
                    self.f.taxable_amount(32_000),
                )
            )

    # ── injections ──
    def inject(self) -> None:
        codes = list(RATES)
        weights = [RATES[c] for c in codes]
        clean = 1 - sum(weights)
        for p in list(self.plans):
            if p.labels:  # D15/D16 invoices stay otherwise clean
                continue
            code = self.rng.choices(codes + ["clean"], weights + [clean])[0]
            if code == "clean":
                continue
            if code in INWARD_ONLY and p.direction != "inward":
                continue
            if code in ROAD and not self.eligible(p):
                continue
            if code == "D13" and len(geo.load().leg_from(p.party.city).plazas) < 2:
                continue  # one crossing cannot time a journey
            self.apply(p, code)

    def apply(self, p: InvoicePlan, code: str) -> None:
        r = self.rng
        if code == "D01":
            if r.random() < 0.5:
                p.ledger_amount_delta = r.choice(
                    [-p.tax, -900.0, 1_800.0, -(p.total % 1000) - 1000]
                )
            else:
                p.payment, p.payment_delta, p.payment_lag = "short", r.choice([1_180.0, 2_360.0]), 5
        elif code == "D02":
            p.ledger_date_delta = r.randint(5, 12)
        elif code == "D03":
            p.ledger = "id_variant"
            p.ledger_ref = r.choice(
                [p.invoice_no.replace("/", "-"), p.invoice_no.lower(), p.invoice_no + "/26-27"]
            )
            if p.ledger_ref == p.invoice_no:
                p.ledger_ref = p.invoice_no + "/26-27"
        elif code == "D04":
            right = p.rate
            p.rate = r.choice([x for x in (5.0, 12.0, 18.0, 28.0, 40.0) if x != right])
        elif code == "D05":
            p.head = "igst" if p.head == "cgst_sgst" else "cgst_sgst"
        elif code == "D06":
            p.tax_override = round(p.tax * r.choice([0.9, 1.1, 0.5]) + r.choice([0.0, 99.0]), 2)
        elif code in ("D07", "D08"):
            near = code == "D08"
            no = (
                p.invoice_no.replace("/", "-", 1)
                if near and "/" in p.invoice_no
                else (
                    p.invoice_no[:-1] + str((int(p.invoice_no[-1]) + 1) % 10)
                    if near
                    else p.invoice_no
                )
            )
            day = p.invoice_date + timedelta(days=r.randint(1, 4) if near else 0)
            self.plans.append(
                self.pm.make(
                    "inward",
                    p.party,
                    no,
                    day,
                    p.taxable,
                    p.hsn,
                    rate=p.rate,
                    head=p.head,
                    labels=[code],
                    ims=False,
                    dup_of=p.uid,
                    payment="none",
                )
            )
            return
        elif code == "D09":
            kind = r.choice(["unbooked", "aged", "orphan"])
            if kind == "unbooked":
                p.ledger, p.payment = "missing", "none"
                p.ims = False
            elif kind == "aged":
                p.invoice_date = date(2026, 9, r.randint(1, 6))
                p.payment = "none"
            else:
                self.orphans.append(
                    OrphanPayment(
                        f"o{len(self.orphans) + 1:04d}",
                        p.party,
                        p.invoice_date + timedelta(days=r.randint(2, 15)),
                        round(r.uniform(20_000, 2_00_000), -2),
                        p.direction,
                    )
                )
                return  # the label lives on the bank line, not this invoice
        elif code == "D10":
            p.ims = False
        elif code == "D11":
            p.road = "missing_ewb"
        elif code == "D12":
            p.road = "paper_only"
            p.trip = Trip(
                self.f.vehicle(p.party.city),
                _at(p.invoice_date, 10),
                _at(p.invoice_date, 11),
                45,
                crossings=False,
            )
        elif code == "D13":
            p.road = "impossible"
            p.trip = Trip(
                self.f.vehicle(p.party.city),
                _at(p.invoice_date, 20),
                _at(p.invoice_date, 21),
                r.uniform(120, 175),
            )
        elif code == "D14":
            earlier = [
                q
                for q in self.plans
                if q.party is p.party
                and q is not p
                and self.eligible(q)
                and q.road == "auto"
                and q.invoice_date < p.invoice_date
                and not q.labels
            ]
            if not earlier:
                return
            src = r.choice(earlier)
            p.road, p.recycled_from = "recycled", src.uid
            src.labels.append("D14")  # every invoice sharing the trip is flagged
        p.labels.append(code)

    # ── network ──
    def network(self) -> tuple[list[Firm], list]:
        nb = NetworkBuilder(self.f, AS_OF)
        nb.tiers(self.suppliers, n1=110, n2=90, n3=60)
        for names, target in zip(RING_NAMES, self.ring_fed, strict=True):
            cities = [
                self.rng.choice(["Sonipat", "Delhi", "Ghaziabad", "Faridabad"]) for _ in names
            ]
            ring = nb.ring(
                RingSpec(names, cities, feeder=self.rng.randrange(len(names)), target=target)
            )
            ring[0].registered_on = AS_OF.date() - timedelta(days=self.rng.randint(25, 80))
            ring[1].ewb_count_90d = 0
        firms = [self.me, *self.suppliers, *self.customers, *nb.firms]
        sold: dict[str, int] = {}
        for u in nb.invoices:
            sold[u.seller] = sold.get(u.seller, 0) + 1
        nb.aggregator_fields([x for x in firms if x.role != "customer"], Counter(sold))
        for ring_firm in [x for x in nb.firms if "ring" in x.tags]:
            if ring_firm.name in (RING_NAMES[0][1], RING_NAMES[1][1]):
                ring_firm.ewb_count_90d = 0
        protected = {x.gstin for x in nb.firms if "ring" in x.tags} | {self.me.gstin}
        nb.sprinkle_signals([x for x in firms if x.role in ("supplier", "upstream")], protected)
        return firms, nb.invoices


def _at(d: date, hour: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=IST)


def build(seed: int = 7) -> World:
    b = RandomBuilder(seed)
    b.base()
    b.inject()
    firms, upstream = b.network()
    for p in b.plans:  # keep every rate lookup honest after injections
        assert p.hsn in hsn_table.BY_CODE
    return World(
        scenario="random",
        seed=seed,
        period=config.DEMO_PERIOD,
        as_of=AS_OF,
        me=b.me,
        firms=firms,
        plans=b.plans,
        upstream=upstream,
        orphan_payments=b.orphans,
    )
