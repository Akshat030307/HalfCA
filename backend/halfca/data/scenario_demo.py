"""The demo month (seed 2609, Sep 2026). Builds the World behind the demo table in CLAUDE.md.

Every count in the table is placed here on purpose; balancers then land the ₹ totals:

  inward 228 = 212 on IMS (197 accept · 11 reject · 4 pending) + 3 not on IMS
               + 7 duplicate copies + 6 never booked
  outward 324 = 7 tax errors + 12 other discrepancies + 15 no-GSTIN ledgers
                + 3 fuzzy + 2 AI-only + 12 never booked + 273 clean
  funnel: stage 1 491 · stage 2 38 (30 no-GSTIN + 8 ID variants) · stage 3 3 · stage 4 2
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from halfca import config
from halfca.ingest.normalise import name_similarity

from .factory import Factory
from .model import Firm, InvoicePlan, Trip, World
from .network import (
    NetworkBuilder,
    RingSpec,
    arora_digits,
    digit_counts_benford,
)
from .plans import PlanMaker, balance_tax, itc

IST = timezone(timedelta(hours=5, minutes=30))
START, END = date(2026, 9, 1), date(2026, 9, 30)
AS_OF = datetime(2026, 10, 10, 18, 0, tzinfo=IST)

# ₹ targets, centred inside their 0.1-lakh display buckets.
TARGET_ITC_CLAIMED = 18_60_050.0
TARGET_OUTPUT_TAX = 25_40_050.0

# Kaveri Metals' 64 invoices: first-digit counts with MAD 0.0514 (displays 0.051).
KAVERI_DIGITS = [11, 7, 6, 7, 9, 9, 9, 3, 3]
SHARMA_INVOICES = 72  # a conforming supplier, for contrast

RING = ["Zenith Traders", "Arka Impex", "Nexo Metals", "Vrindam Trading", "Kairo Enterprises"]
RING_CITIES = ["Sonipat", "Delhi", "Sonipat", "Ghaziabad", "Faridabad"]

HERO_SUPPLIERS = {
    # key: (name, city, invoice prefix)
    "patel": ("Patel Pipes", "Jaipur", "PP/26/"),
    "sharma": ("Sharma Steel", "Ludhiana", "LD/"),
    "rohilkhand": ("Rohilkhand Alloys", "Moradabad", "MB/"),
    "ganga": ("Ganga Wires", "Kanpur", "KN/"),
    "pinkcity": ("Pink City Fasteners", "Jaipur", "JP/"),
    "doaba": ("Doaba Fittings", "Ludhiana", "DF/"),
    "kaveri": ("Kaveri Metals", "Karnal", "KM/26/"),
    "mehta": ("Mehta Tubes", "Ambala", "MT/"),
    "singh": ("Singh Fittings", "Delhi", "SF/"),
}
OTHER_SUPPLIER_CITIES = (
    ["Delhi"] * 10
    + ["Ludhiana"] * 6
    + ["Ambala"] * 2
    + ["Karnal"] * 2
    + ["Jaipur"] * 5
    + ["Moradabad"] * 4
    + ["Kanpur"] * 3
    + ["Agra"] * 2
    + ["Lucknow"] * 2
)
OTHER_CUSTOMER_CITIES = (
    ["Delhi"] * 59
    + ["Gurugram"] * 4
    + ["Faridabad"] * 4
    + ["Noida"] * 3
    + ["Ghaziabad"] * 2
    + ["Sonipat"] * 2
)
NAMED_UPSTREAM = ["Bharat Tubes", "Ostwal Steel", "Northline Alloys"]


def _d(day: int) -> date:
    return date(2026, 9, day)


def _t(day: int, hh: int, mm: int) -> datetime:
    return datetime(2026, 9, day, hh, mm, tzinfo=IST)


class DemoBuilder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.f = Factory(self.rng)
        self.f.reserve(
            *(n for n, _, _ in HERO_SUPPLIERS.values()),
            *RING,
            *NAMED_UPSTREAM,
            "Capital Hardware",
            config.USER_NAME,
        )
        long_ago = lambda: AS_OF.date() - timedelta(days=self.rng.randint(1500, 6000))  # noqa: E731
        self.long_ago = long_ago

        self.me = self.f.firm(
            config.USER_NAME,
            "Delhi",
            "self",
            registered_on=date(2017, 7, 1),
            prefix="AR/S/",
            pan="AAKFA4821M",
            gstin=config.USER_GSTIN,
        )
        self.me.address = "Shop 14, Chawri Bazar, Delhi"
        self.pm = PlanMaker(self.f, self.me)

        self.s: dict[str, Firm] = {}
        for key, (name, city, prefix) in HERO_SUPPLIERS.items():
            kw = {"pan": "AAHCK3367Q", "gstin": "06AAHCK3367Q1ZW"} if key == "kaveri" else {}
            tags = ["hero", "showcase"] if key in ("patel", "mehta", "singh") else ["hero"]
            self.s[key] = self.f.firm(
                name, city, "supplier", registered_on=long_ago(), prefix=prefix, tags=tags, **kw
            )
        self.others_s = [self._supplier(city) for city in self._shuffled(OTHER_SUPPLIER_CITIES)]
        self.capital = self.f.firm(
            "Capital Hardware", "Delhi", "customer", registered_on=long_ago(), tags=["hero"]
        )
        self.others_c = [
            self.f.firm(self.f.customer_name(), city, "customer", registered_on=long_ago())
            for city in self._shuffled(OTHER_CUSTOMER_CITIES)
        ]
        self.plans: list[InvoicePlan] = []

    def _shuffled(self, items: list[str]) -> list[str]:
        out = list(items)
        self.rng.shuffle(out)
        return out

    def _supplier(self, city: str) -> Firm:
        name = self.f.supplier_name()
        return self.f.firm(
            name, city, "supplier", registered_on=self.long_ago(), prefix=self.f.prefix_for(name)
        )

    def _supplier_in(self, city: str, exclude: set[str]) -> Firm:
        pool = [x for x in self.others_s if x.city == city and x.gstin not in exclude]
        return self.rng.choice(pool)

    def _day(self) -> date:
        return self.f.business_day(START, END)

    def _add(self, plan: InvoicePlan) -> InvoicePlan:
        self.plans.append(plan)
        return plan

    # ── inward ───────────────────────────────────────────────────────────────
    def inward(self) -> None:
        pm, s = self.pm, self.s

        # Heroes that pass everything (IMS accept).
        self.pp0912 = self._add(
            pm.make(
                "inward",
                s["patel"],
                "PP/26/0912",
                _d(11),
                1_47_500,
                "7306",
                labels=["hero:PP/26/0912"],
                payment_lag=9,
            )
        )
        self._add(
            pm.make(
                "inward",
                s["sharma"],
                "LD/2291",
                _d(14),
                4_11_864.41,
                "7214",
                labels=["hero:LD/2291"],
                payment_lag=12,
                trip=Trip(
                    "PB10 GK 7731",
                    _t(14, 5, 10),
                    _t(14, 6, 0),
                    310 / (340 / 60),
                    ewb_no="381244710093",
                ),
            )
        )
        inv0418 = self._add(
            pm.make(
                "inward",
                s["patel"],
                "INV-0418",
                _d(4),
                94_915.25,
                "7306",
                labels=["hero:INV-0418"],
                payment_lag=14,
            )
        )

        # Kaveri Metals: clean on paper, 2 hops below a ring → IMS pending.
        for no, day, taxable in [
            ("KM/26/3341", 5, 6_40_000),
            ("KM/26/3352", 12, 5_60_000),
            ("KM/26/3367", 19, 6_20_000),
            ("KM/26/3378", 26, 5_13_300),
        ]:
            self._add(
                pm.make(
                    "inward",
                    s["kaveri"],
                    no,
                    _d(day),
                    taxable,
                    "7208",
                    labels=["D15", f"hero:{no}"],
                )
            )

        # Physical-trail failures: perfect paperwork, the road disagrees.
        self._add(
            pm.make(
                "inward",
                s["rohilkhand"],
                "MB/0877",
                _d(17),
                1_00_000,
                "7604",
                labels=["D12", "hero:MB/0877"],
                payment_lag=6,
                road="paper_only",
                trip=Trip(
                    "UP21 T 4410",
                    _t(17, 10, 20),
                    _t(17, 11, 0),
                    45,
                    ewb_no="381299021166",
                    crossings=False,
                ),
            )
        )
        self._add(
            pm.make(
                "inward",
                s["ganga"],
                "KN/1502",
                _d(19),
                1_20_000,
                "8544",
                labels=["D13", "hero:KN/1502"],
                payment_lag=8,
                road="impossible",
                trip=Trip(
                    "UP78 HT 2291",
                    _t(19, 21, 5),
                    _t(19, 22, 10),
                    480 / (182 / 60),
                    ewb_no="381300457720",
                ),
            )
        )
        jp1187 = self._add(
            pm.make(
                "inward",
                s["pinkcity"],
                "JP/1187",
                _d(8),
                50_000,
                "7318",
                labels=["D14", "hero:JP/1187"],
                payment_lag=10,
                trip=Trip("RJ14 GD 6620", _t(8, 9, 15), _t(8, 10, 5), 52, ewb_no="381266305518"),
            )
        )
        for no, day in [("JP/1188", 15), ("JP/1192", 23)]:
            self._add(
                pm.make(
                    "inward",
                    s["pinkcity"],
                    no,
                    _d(day),
                    50_000,
                    "7318",
                    labels=["D14", f"hero:{no}"],
                    road="recycled",
                    recycled_from=jp1187.uid,
                    payment_lag=9,
                )
            )

        # Inward tax errors (IMS reject). 6 x ITC = ₹43,396.
        used: set[str] = set()
        self._add(
            pm.make(
                "inward",
                s["doaba"],
                "DF/0450",
                _d(12),
                58_500,
                "7307",
                rate=12,
                labels=["D04", "hero:DF/0450"],
            )
        )
        for city, hsn, taxable, rate, head, label in [
            ("Agra", "6907", 40_000, 28, None, "D04"),  # abolished 28% slab
            ("Ludhiana", "7318", 60_000, 5, None, "D04"),  # 5% on an 18% item
            ("Jaipur", "8481", 45_000, 12, None, "D04"),  # abolished 12% slab
            ("Delhi", "3917", 50_000, None, "igst", "D05"),  # IGST on an intra-state supply
            ("Ambala", "8302", 43_200, None, "cgst_sgst", "D05"),  # CGST+SGST inter-state
        ]:
            sup = self._supplier_in(city, used)
            used.add(sup.gstin)
            self._add(
                pm.make(
                    "inward",
                    sup,
                    pm.next_number(sup),
                    self._day(),
                    taxable,
                    hsn,
                    rate=rate,
                    head=head,
                    labels=[label],
                )
            )  # type: ignore[arg-type]

        # Books-side discrepancies on accepted invoices.
        deck = self._inward_deck()
        disc: list[InvoicePlan] = []
        for kind in [
            "amt_gst",
            "amt_swap",
            "amt_round",
            "amt_plus",
            "pay_short",
            "pay_short",
            "date",
            "date",
            "date",
            "id",
            "id",
            "id",
            "id",
        ]:
            p = self._inward_random(deck)
            self._discrepancy(p, kind)
            disc.append(self._add(p))

        # Party ledger without GSTIN: pairs at stage 2.
        for _ in range(15):
            self._add(self._inward_random(deck, ledger="no_gstin", labels=["S2"]))

        # The clean bulk, balanced so ITC on IMS lands on target.
        pool = [self._add(self._inward_random(deck)) for _ in range(166)]

        # Booked but the supplier never filed (not on IMS).
        for _ in range(3):
            self._add(self._inward_random(deck, ims=False, labels=["D10"]))
        # Received, never booked, never filed.
        for _ in range(6):
            self._add(
                self._inward_random(
                    deck, ims=False, ledger="missing", payment="none", labels=["D09"]
                )
            )

        ims_plans = [p for p in self.plans if p.direction == "inward" and p.ims]
        fixed = [p for p in ims_plans if p not in pool]
        balance_tax(pool, TARGET_ITC_CLAIMED - itc(fixed))

        self._duplicates(inv0418, pool)

    def _inward_deck(self) -> list[Firm]:
        """Who the random inward invoices come from (hero suppliers get a few clean ones)."""
        s = self.s
        deck = (
            [s["patel"]] * 6
            + [s["sharma"]] * 5
            + [s["rohilkhand"]] * 2
            + [s["ganga"]] * 2
            + [s["doaba"]] * 2
            + [s["mehta"]] * 6
            + [s["singh"]] * 6
        )
        while len(deck) < 203:
            deck.extend(self.others_s)
        deck = deck[:203]
        self.rng.shuffle(deck)
        return deck

    def _inward_random(self, deck: list[Firm], **kw: object) -> InvoicePlan:
        sup = deck.pop()
        return self.pm.make(
            "inward",
            sup,
            self.pm.next_number(sup),
            self._day(),
            self.f.taxable_amount(24_000, sigma=1.0),
            **kw,
        )  # type: ignore[arg-type]

    def _discrepancy(self, p: InvoicePlan, kind: str) -> None:
        if kind.startswith("amt"):
            p.labels.append("D01")
            if kind == "amt_gst":
                p.ledger_amount_delta = -p.tax  # booked the taxable value only
            elif kind == "amt_swap":
                p.ledger_amount_delta = -900.0  # 52,840 typed as 51,940
            elif kind == "amt_round":
                p.ledger_amount_delta = -(p.total % 1000) - 1000
            else:
                p.ledger_amount_delta = 1_800.0
        elif kind == "pay_short":
            p.labels.append("D01")
            p.payment = "short"
            p.payment_delta = self.rng.choice([1_180.0, 2_360.0, 1_770.0])
            p.payment_lag = self.rng.randint(4, 12)
        elif kind == "date":
            p.labels.append("D02")
            p.ledger_date_delta = self.rng.randint(5, 11)
        elif kind == "id":
            p.labels.append("D03")
            p.ledger = "id_variant"
            p.ledger_ref = self._id_variant(p.invoice_no)

    def _id_variant(self, no: str) -> str:
        """How an accountant might retype the same invoice number."""
        options = [
            no.replace("/", "-") if "/" in no else no.replace("-", "/"),
            no.lower(),
            no + "/26-27",
            no.replace("/", " ") if "/" in no else no.replace("-", ""),
        ]
        variant = self.rng.choice(options)
        return variant if variant != no else no + "/26-27"

    def _duplicates(self, inv0418: InvoicePlan, pool: list[InvoicePlan]) -> None:
        pm = self.pm
        # The hero near-duplicate: same bill, renumbered, two days later, paid twice.
        self._add(
            pm.make(
                "inward",
                inv0418.party,
                "INV/418",
                _d(6),
                inv0418.taxable,
                inv0418.hsn,
                labels=["D08", "hero:INV/418"],
                ims=False,
                dup_of=inv0418.uid,
                payment_lag=11,
            )
        )
        candidates = [p for p in pool if p.invoice_date <= _d(25) and p.party.tags != ["hero"]]
        originals = self.rng.sample(candidates, 6)
        for i, orig in enumerate(originals):
            if i < 3:  # near duplicates: retyped number, shifted date
                no = self._near_dup_number(orig.invoice_no, i)
                day = orig.invoice_date + timedelta(days=self.rng.randint(2, 4))
                label = "D08"
            else:  # exact duplicates: the same bill keyed in twice
                no, day, label = orig.invoice_no, orig.invoice_date, "D07"
            self._add(
                pm.make(
                    "inward",
                    orig.party,
                    no,
                    day,
                    orig.taxable,
                    orig.hsn,
                    rate=orig.rate,
                    head=orig.head,
                    labels=[label],
                    ims=False,
                    dup_of=orig.uid,
                    payment="none",
                )
            )

    def _near_dup_number(self, no: str, style: int) -> str:
        head, tail = no[: len(no) - 2], no[-2:]
        if style == 0 and tail[0] != tail[1]:
            return head + tail[::-1]  # last two digits swapped
        if style == 1:
            return no.replace("/", "-", 1) if "/" in no else no.replace("-", "/", 1)
        return no[:-1] + str((int(no[-1]) + 1) % 10)  # last digit off by one

    # ── outward ──────────────────────────────────────────────────────────────
    def outward(self) -> None:
        pm = self.pm
        n = 324
        days = sorted(self.f.business_day(START, END) for _ in range(n))
        slots = list(range(n))
        hero_slot = 218  # → AR/S/2219
        slots.remove(hero_slot)
        self.rng.shuffle(slots)

        weights = [self.rng.uniform(0.4, 3.0) for _ in self.others_c]

        def customer() -> Firm:
            return self.rng.choices(self.others_c, weights)[0]

        def number(i: int) -> str:
            return f"AR/S/{2001 + i}"

        def take(k: int) -> list[int]:
            return [slots.pop() for _ in range(k)]

        made: dict[int, InvoicePlan] = {}
        made[hero_slot] = pm.make(
            "outward",
            self.capital,
            number(hero_slot),
            days[hero_slot],
            1_20_000,
            "7306",
            head="igst",
            labels=["D05", "hero:AR/S/2219"],
            payment_lag=7,
        )
        outside = [c for c in self.others_c if c.state_code != "07"]
        (i,) = take(1)
        made[i] = pm.make(
            "outward",
            self.rng.choice(outside),
            number(i),
            days[i],
            self.f.taxable_amount(30_000),
            head="cgst_sgst",
            labels=["D05"],
        )
        # Over-charges only, so output tax is never under-reported.
        for (hsn, rate), i in zip(
            [("2523", 28), ("8201", 12), ("7323", 18), ("8424", 12), ("5607", 12)],
            take(5),
            strict=True,
        ):
            made[i] = pm.make(
                "outward",
                customer(),
                number(i),
                days[i],
                self.f.taxable_amount(30_000),
                hsn,
                rate=rate,
                labels=["D04"],
            )

        for kind, i in zip(
            [
                "amt_gst",
                "amt_swap",
                "amt_plus",
                "pay_short",
                "pay_short",
                "date",
                "date",
                "date",
                "id",
                "id",
                "id",
                "id",
            ],
            take(12),
            strict=True,
        ):
            p = pm.make("outward", customer(), number(i), days[i], self.f.taxable_amount(30_000))
            self._discrepancy(p, kind)
            made[i] = p
        for i in take(15):
            made[i] = pm.make(
                "outward",
                customer(),
                number(i),
                days[i],
                self.f.taxable_amount(30_000),
                ledger="no_gstin",
                labels=["S2"],
            )
        for i in take(3):
            c = customer()
            made[i] = pm.make(
                "outward",
                c,
                number(i),
                days[i],
                self.f.taxable_amount(30_000),
                ledger="garbled",
                ledger_ref="",
                ledger_party=self._close_name(c.name),
                labels=["S3"],
            )
        for i in take(2):
            c = customer()
            made[i] = pm.make(
                "outward",
                c,
                number(i),
                days[i],
                self.f.taxable_amount(30_000),
                ledger="alias",
                ledger_ref="",
                ledger_party=self._alias(c.name),
                labels=["S4"],
            )
        for k, i in enumerate(take(12)):
            made[i] = pm.make(
                "outward",
                customer(),
                number(i),
                days[i],
                self.f.taxable_amount(30_000),
                ledger="missing",
                payment="normal" if k < 6 else "none",
                labels=["D09"],
            )
        pool: list[InvoicePlan] = []
        for i in list(slots):
            made[i] = pm.make(
                "outward", customer(), number(i), days[i], self.f.taxable_amount(30_000)
            )
            pool.append(made[i])

        outward = [made[i] for i in range(n)]
        fixed = [p for p in outward if p not in pool]
        balance_tax(pool, TARGET_OUTPUT_TAX - itc(fixed))
        self.plans.extend(outward)

    def _close_name(self, name: str) -> str:
        for variant in [name + " (Regd)", name.replace("&", "and"), name + " Delhi", name + "."]:
            if variant != name and name_similarity(variant, name) >= 90:
                return variant
        return name

    def _alias(self, name: str) -> str:
        """A Tally ledger alias made of initials, e.g. M.I.P. for Mittal Infra Projects."""
        words = [w for w in name.replace("&", " ").split() if w[0].isalpha()]
        alias = ".".join(w[0].upper() for w in words) + "."
        assert name_similarity(alias, name) < config.STAGE3_NAME_MIN - 10, (alias, name)
        return alias

    # ── network ──────────────────────────────────────────────────────────────
    def network(self) -> tuple[list[Firm], list]:
        nb = NetworkBuilder(self.f, AS_OF)
        s = self.s
        named = [
            nb.firm(n, 1, c, tags=["showcase"])
            for n, c in zip(NAMED_UPSTREAM, ["Jaipur", "Jaipur", "Ludhiana"], strict=True)
        ]
        nb.trade(named[0], s["patel"], 5, 1_80_000)
        nb.trade(named[1], s["patel"], 4, 2_10_000)
        nb.trade(named[2], s["mehta"], 5, 1_50_000)

        suppliers = list(s.values()) + self.others_s
        nb.tiers(suppliers, n1=110, n2=90, n3=60)

        ring = nb.ring(RingSpec(RING, RING_CITIES, feeder=2, target=s["kaveri"]))
        tier3 = [x for x in nb.firms if x.tier == 3]
        for seller in self.rng.sample(tier3, 2):  # the ring buys a little real stock too
            nb.trade(seller, ring[0], 2, 2_00_000)

        peers = nb.outside_buyers(30)
        kaveri_counts = [
            t - a
            for t, a in zip(KAVERI_DIGITS, arora_digits(self.plans, s["kaveri"].gstin), strict=True)
        ]
        nb.sales_with_benford(s["kaveri"], peers[:22], kaveri_counts)
        sharma_target = digit_counts_benford(SHARMA_INVOICES)
        sharma_counts = [
            max(0, t - a)
            for t, a in zip(sharma_target, arora_digits(self.plans, s["sharma"].gstin), strict=True)
        ]
        nb.sales_with_benford(s["sharma"], peers[8:], sharma_counts)

        firms = [self.me, *suppliers, self.capital, *self.others_c, *nb.firms]
        sold: dict[str, int] = {}
        for u in nb.invoices:
            sold[u.seller] = sold.get(u.seller, 0) + 1
        nb.aggregator_fields([x for x in firms if x.role != "customer"], Counter(sold))

        # The ring's tells (what the Credit screen's red badges point at).
        zenith, arka, nexo, vrindam, kairo = ring
        zenith.registered_on = AS_OF.date() - timedelta(days=41)
        nexo.ewb_count_90d = 0
        kairo.turnover_3m_avg = 9_50_000.0
        kairo.turnover_month = 95_00_000.0
        vrindam.address, vrindam.phone = arka.address, arka.phone
        vrindam.returns_missed_6m = 2

        protected = {x.gstin for x in ring} | {x.gstin for x in s.values()} | {self.me.gstin}
        nb.sprinkle_signals([x for x in firms if x.role in ("supplier", "upstream")], protected)
        return firms, nb.invoices


def build(seed: int = config.DEMO_SEED) -> World:
    b = DemoBuilder(seed)
    b.inward()
    b.outward()
    firms, upstream = b.network()
    rejected = itc(
        [p for p in b.plans if p.ims and ({"D04", "D05", "D12", "D13", "D14"} & set(p.labels))]
    )
    at_risk = itc([p for p in b.plans if "D15" in p.labels])
    return World(
        scenario="demo",
        seed=seed,
        period=config.DEMO_PERIOD,
        as_of=AS_OF,
        me=b.me,
        firms=firms,
        plans=b.plans,
        upstream=upstream,
        targets={
            "itc_claimed": itc([p for p in b.plans if p.ims]),
            "itc_rejected": rejected,
            "itc_at_risk": at_risk,
            "output_tax": itc([p for p in b.plans if p.direction == "outward"]),
        },
    )
