"""Turn a World (plans) into the records each source system would hold.

Invoices, Tally vouchers, bank lines, IMS records, e-way bills and FASTag toll
crossings all come from the same InvoicePlans, so the threads agree exactly where the
plan says they should and disagree exactly where it injected something.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from halfca import config

from . import hsn as hsn_table
from . import routes as geo_mod
from .factory import Factory
from .model import InvoicePlan, OrphanPayment, Trip, World, money

Row = dict[str, object]

TOLL_GRACE = timedelta(hours=48)  # crossings count until validity end + this
NOISE_START = date(2026, 8, 20)


@dataclass
class Tables:
    invoices: list[Row] = field(default_factory=list)
    ledger: list[Row] = field(default_factory=list)
    bank: list[Row] = field(default_factory=list)
    ims: list[Row] = field(default_factory=list)
    eway_bills: list[Row] = field(default_factory=list)
    toll_crossings: list[Row] = field(default_factory=list)
    counterparties: list[Row] = field(default_factory=list)
    upstream_invoices: list[Row] = field(default_factory=list)
    hsn_rates: list[Row] = field(default_factory=list)
    truth_labels: list[Row] = field(default_factory=list)


def ewb_validity_days(distance_km: float) -> int:
    """Regular cargo: one day per 200 km (part thereof)."""
    return max(1, math.ceil(distance_km / 200))


class Deriver:
    def __init__(self, w: World) -> None:
        self.w = w
        # A separate stream so derivation never shifts the plan's random draws.
        self.rng = random.Random(w.seed * 7919 + 17)
        self.f = Factory(self.rng)
        self.geo = geo_mod.load()
        self.t = Tables()
        self.as_of_day = w.as_of.date()
        self.tz = w.as_of.tzinfo
        self.by_uid = {p.uid: p for p in w.plans}
        self.ewb_of: dict[str, str] = {}  # plan uid -> e-way bill no
        self.busy: dict[str, list[tuple[datetime, datetime]]] = {}  # vehicle -> windows
        self.fleet: dict[str, list[str]] = {}  # supplier gstin -> vehicles
        self.vehicle_leg: dict[str, geo_mod.Leg] = {}
        self._seq: dict[str, int] = {}
        # Hero plates and e-way bill numbers are fixed; keep random ones from colliding.
        for p in w.plans:
            if p.trip is not None:
                self.f.reserve_vehicle(p.trip.vehicle_no)
                if p.trip.ewb_no:
                    self.f.ewb_no(p.trip.ewb_no)

    def seq(self, key: str) -> int:
        self._seq[key] = self._seq.get(key, 0) + 1
        return self._seq[key]

    def at(self, d: date, hour: float) -> datetime:
        return datetime.combine(d, time(0, 0), self.tz) + timedelta(hours=hour)

    # ── invoices ──
    def invoices(self) -> None:
        for p in self.w.plans:
            h = hsn_table.BY_CODE[p.hsn]
            qty = max(1, round(p.taxable / h.unit_price))
            supplier = p.party if p.direction == "inward" else self.w.me
            buyer = self.w.me if p.direction == "inward" else p.party
            self.t.invoices.append(
                {
                    "invoice_id": p.uid,
                    "invoice_no": p.invoice_no,
                    "invoice_date": p.invoice_date.isoformat(),
                    "direction": p.direction,
                    "supplier_gstin": supplier.gstin,
                    "supplier_name": supplier.name,
                    "supplier_state": supplier.state_code,
                    "buyer_gstin": buyer.gstin,
                    "buyer_name": buyer.name,
                    "place_of_supply": buyer.state_code,
                    "hsn": p.hsn,
                    "description": h.description,
                    "qty": qty,
                    "unit": h.unit,
                    "unit_price": money(p.taxable / qty),
                    "taxable_value": p.taxable,
                    "rate": p.rate,
                    "cgst": p.cgst,
                    "sgst": p.sgst,
                    "igst": p.igst,
                    "total": p.total,
                    "ewb_no": self.ewb_of.get(p.uid),
                }
            )
            for code in p.labels:
                self.t.truth_labels.append(
                    {
                        "invoice_id": p.uid,
                        "invoice_no": p.invoice_no,
                        "direction": p.direction,
                        "party_gstin": p.party.gstin,
                        "code": code,
                    }
                )

    # ── road ──
    def _vehicle_for(self, p: InvoicePlan, leg: geo_mod.Leg, start: datetime, end: datetime) -> str:
        gstin = p.party.gstin
        fleet = self.fleet.setdefault(gstin, [])
        for v in fleet:
            if all(
                e < start - timedelta(hours=36) or s > end + timedelta(hours=36)
                for s, e in self.busy.get(v, [])
            ):
                return v
        v = self.f.vehicle(p.party.city)
        fleet.append(v)
        self.vehicle_leg[v] = leg
        return v

    def _crossings(
        self,
        vehicle: str,
        leg: geo_mod.Leg,
        departure: datetime,
        speed: float,
        jitter: bool,
        reverse: bool = False,
    ) -> list[datetime]:
        plazas = list(leg.plazas)
        dist = leg.distance_km
        times = []
        last: datetime | None = None
        order = reversed(plazas) if reverse else plazas
        for pz in order:
            km = (dist - (pz.km - leg.origin_km)) if reverse else (pz.km - leg.origin_km)
            t = departure + timedelta(hours=km / speed)
            if jitter:
                t += timedelta(minutes=self.rng.uniform(-4, 7))
            if last and t <= last:
                t = last + timedelta(minutes=5)
            last = t
            times.append(t)
            self.t.toll_crossings.append(
                {
                    "crossing_id": f"TC{len(self.t.toll_crossings) + 1:05d}",
                    "vehicle_no": vehicle,
                    "plaza_id": pz.id,
                    "plaza_name": pz.name,
                    "crossed_at": t.isoformat(timespec="seconds"),
                }
            )
        return times

    def road(self) -> None:
        inward = sorted(
            (p for p in self.w.plans if p.direction == "inward" and p.dup_of is None),
            key=lambda p: (p.invoice_date, p.uid),
        )
        for p in inward:
            if p.road == "recycled":
                continue  # quotes another invoice's e-way bill (below)
            needs = p.inter_state and p.total >= config.EWB_THRESHOLD
            if not needs or p.road == "missing_ewb":
                continue
            leg = self.geo.leg_from(p.party.city)
            if leg is None:
                continue
            trip = p.trip or self._auto_trip(p, leg)
            valid_until = trip.generated_at + timedelta(days=ewb_validity_days(leg.distance_km))
            vehicle = trip.vehicle_no
            if p.trip is not None and vehicle not in self.fleet.get(p.party.gstin, []):
                self.fleet.setdefault(p.party.gstin, []).append(vehicle)
                self.vehicle_leg[vehicle] = leg
            ewb = trip.ewb_no or self.f.ewb_no()
            self.ewb_of[p.uid] = ewb
            self.busy.setdefault(vehicle, []).append((trip.generated_at, valid_until + TOLL_GRACE))
            self.t.eway_bills.append(
                {
                    "ewb_no": ewb,
                    "doc_type": "INV",
                    "doc_no": p.invoice_no,
                    "doc_date": p.invoice_date.isoformat(),
                    "supplier_gstin": p.party.gstin,
                    "supplier_name": p.party.name,
                    "recipient_gstin": self.w.me.gstin,
                    "from_city": p.party.city,
                    "from_state": p.party.state_code,
                    "to_city": "Delhi",
                    "to_state": "07",
                    "hsn": p.hsn,
                    "value": p.total,
                    "transport_mode": "Road",
                    "vehicle_no": vehicle,
                    "route_id": leg.route.id,
                    "distance_km": leg.distance_km,
                    "generated_at": trip.generated_at.isoformat(timespec="seconds"),
                    "valid_until": valid_until.isoformat(timespec="seconds"),
                }
            )
            if trip.crossings:
                self._crossings(vehicle, leg, trip.departure, trip.speed_kmh, jitter=p.trip is None)
        # Recycled: later invoices quote the first invoice's e-way bill.
        for p in self.w.plans:
            if p.road == "recycled" and p.recycled_from:
                self.ewb_of[p.uid] = self.ewb_of[p.recycled_from]
            if p.dup_of and p.dup_of in self.ewb_of:
                self.ewb_of[p.uid] = self.ewb_of[p.dup_of]

    def _auto_trip(self, p: InvoicePlan, leg: geo_mod.Leg) -> Trip:
        generated = self.at(p.invoice_date, self.rng.uniform(8, 19.5))
        departure = generated + timedelta(hours=self.rng.uniform(0.4, 3.0))
        end = generated + timedelta(days=ewb_validity_days(leg.distance_km)) + TOLL_GRACE
        vehicle = self._vehicle_for(p, leg, generated, end)
        return Trip(vehicle, generated, departure, self.rng.uniform(38, 56))

    def noise(self) -> None:
        """Other trips by the same trucks (outside their e-way bill windows) and background
        traffic, so a plaza log looks like a plaza log."""
        days = (self.as_of_day - NOISE_START).days
        for vehicle, leg in sorted(self.vehicle_leg.items()):
            for _ in range(self.rng.randint(3, 6)):
                for _attempt in range(20):
                    start = self.at(
                        NOISE_START + timedelta(self.rng.randint(0, days)), self.rng.uniform(0, 23)
                    )
                    end = start + timedelta(hours=leg.distance_km / 40 + 30)
                    if all(
                        end < s - timedelta(hours=12) or start > e + timedelta(hours=12)
                        for s, e in self.busy.get(vehicle, [])
                    ):
                        self.busy.setdefault(vehicle, []).append((start, end))
                        speed = self.rng.uniform(36, 55)
                        self._crossings(vehicle, leg, start, speed, jitter=True)
                        back = start + timedelta(
                            hours=leg.distance_km / speed + self.rng.uniform(8, 20)
                        )
                        self._crossings(vehicle, leg, back, speed, jitter=True, reverse=True)
                        break
        legs = [
            self.geo.leg_from(c)
            for c in (
                "Ludhiana",
                "Ambala",
                "Karnal",
                "Moradabad",
                "Jaipur",
                "Kanpur",
                "Agra",
                "Lucknow",
            )
        ]
        for _ in range(110):
            leg = self.rng.choice([leg for leg in legs if leg])
            vehicle = self.f.vehicle(leg.origin_city)
            for _trip in range(self.rng.randint(1, 3)):
                start = self.at(
                    NOISE_START + timedelta(self.rng.randint(0, days)), self.rng.uniform(0, 23)
                )
                self._crossings(
                    vehicle,
                    leg,
                    start,
                    self.rng.uniform(36, 58),
                    jitter=True,
                    reverse=self.rng.random() < 0.5,
                )
        self.t.toll_crossings.sort(key=lambda r: (str(r["crossed_at"]), str(r["vehicle_no"])))
        for i, r in enumerate(self.t.toll_crossings, start=1):
            r["crossing_id"] = f"TC{i:05d}"

    # ── bank + books ──
    def _bank_name(self, name: str) -> str:
        return name.upper().replace("&", "AND").replace(".", "")[:22].strip()

    def _cheque_no(self) -> int:
        return self.rng.randint(100000, 999999)

    def _utr(self, mode: str, d: date) -> str:
        bank = self.rng.choice(["HDFC", "SBIN", "ICIC", "PUNB", "UTIB", "KKBK"])
        tail = "".join(self.rng.choice("0123456789") for _ in range(9))
        return f"{bank}{mode[0]}{d:%y%m%d}{tail}"

    def payments(self) -> list[tuple[InvoicePlan, date, float]]:
        out: list[tuple[InvoicePlan, date, float]] = []
        for p in self.w.plans:
            if p.payment == "none":
                continue
            if p.dup_of and p.payment == "normal" and "hero:INV/418" not in p.labels:
                continue
            lag = p.payment_lag
            if lag is None:
                # Most pay inside 30-day terms; a few are slow (these become aged gaps).
                slow = self.rng.random() < 0.06
                if p.direction == "inward":
                    lag = self.rng.randint(40, 75) if slow else self.rng.randint(5, 32)
                else:
                    lag = self.rng.randint(40, 75) if slow else self.rng.randint(0, 30)
            paid = p.invoice_date + timedelta(days=lag)
            if paid > self.as_of_day:
                continue
            amount = p.total - (p.payment_delta if p.payment == "short" else 0.0)
            out.append((p, paid, money(amount)))
        out.sort(key=lambda x: (x[1], x[0].uid))
        return out

    def bank_and_books(self) -> None:
        paid: list[tuple[InvoicePlan | OrphanPayment, date, float]] = list(self.payments())
        paid += [(o, o.paid_on, o.amount) for o in self.w.orphan_payments]
        paid.sort(key=lambda x: (x[1], x[0].uid))
        for p, d, amount in paid:
            orphan = isinstance(p, OrphanPayment)
            mode = (
                "RTGS"
                if amount >= 2_00_000
                else self.rng.choices(
                    ["NEFT", "IMPS", "UPI", "CHQ"], [70, 15, 5 if amount < 1_00_000 else 0, 10]
                )[0]
            )
            name = self._bank_name(p.party.name)
            if orphan:
                ref = "-ADVANCE"
            else:
                with_ref = self.rng.random() < 0.85 or p.payment == "short" or p.labels
                ref = f"-{p.invoice_no}" if with_ref else ""
            out = p.direction == "inward"
            narration = (
                f"{mode} {'DR' if out else 'CR'}-{name}{ref}"
                if mode != "CHQ"
                else f"CHQ {'PAID' if out else 'DEP'} {self._cheque_no()}-{name}{ref}"
            )
            n = self.seq("bank")
            self.t.bank.append(
                {
                    "txn_id": f"HDFC{n:05d}",
                    "txn_date": d.isoformat(),
                    "direction": "debit" if out else "credit",
                    "amount": amount,
                    "counterparty": name,
                    "narration": narration,
                    "utr": self._utr(mode, d) if mode != "CHQ" else None,
                    "mode": mode,
                }
            )
            kind = "Payment" if out else "Receipt"
            against = "advance, no bill" if orphan else p.invoice_no
            self._voucher(
                kind,
                d,
                p.party.name,
                p.party.gstin,
                None if orphan else p.invoice_no,
                amount,
                f"Being {'payment made' if out else 'amount received'} against {against}",
                debit=out,
            )
            if orphan:
                self.t.truth_labels.append(
                    {
                        "invoice_id": p.uid,
                        "invoice_no": None,
                        "direction": p.direction,
                        "party_gstin": p.party.gstin,
                        "code": "D09",
                    }
                )

        booked = sorted(
            (p for p in self.w.plans if p.ledger != "missing"),
            key=lambda p: (p.invoice_date, p.uid),
        )
        for p in booked:
            normal_lag = self.rng.randint(0, 2) if p.direction == "inward" else 0
            d = p.invoice_date + timedelta(days=p.ledger_date_delta or normal_lag)
            gstin = None if p.ledger in ("no_gstin", "garbled", "alias") else p.party.gstin
            ref = p.invoice_no if p.ledger_ref is None else p.ledger_ref
            kind = "Purchase" if p.direction == "inward" else "Sales"
            verb = "purchased vide bill" if kind == "Purchase" else "sold vide invoice"
            narration = f"Being goods {verb} {ref}" if ref else "Being goods sold, bill to follow"
            self._voucher(
                kind,
                d,
                p.ledger_party or p.party.name,
                gstin,
                ref,
                money(p.total + p.ledger_amount_delta),
                narration,
                debit=kind == "Sales",
            )

        for _ in range(70):
            d = self.f.business_day(date(2026, 9, 1), date(2026, 9, 30))
            head, lo, hi = self.rng.choice(
                [
                    ("Rent", 85_000, 85_000),
                    ("Salaries", 3_20_000, 3_60_000),
                    ("Electricity", 9_000, 21_000),
                    ("Freight Inward", 2_500, 18_000),
                    ("Bank Charges", 120, 900),
                    ("Office Expenses", 800, 7_500),
                    ("Depreciation", 14_000, 14_000),
                    ("Staff Welfare", 1_200, 6_000),
                ]
            )
            self._voucher(
                "Journal",
                d,
                head,
                None,
                None,
                money(self.rng.uniform(lo, hi)),
                f"Being {head.lower()} for the month",
                debit=True,
            )
        self.t.ledger.sort(key=lambda r: (str(r["voucher_date"]), str(r["voucher_no"])))

    def _voucher(
        self,
        kind: str,
        d: date,
        party: str,
        gstin: str | None,
        ref: str | None,
        amount: float,
        narration: str,
        *,
        debit: bool,
    ) -> None:
        prefix = {
            "Purchase": "PUR",
            "Sales": "SAL",
            "Payment": "PAY",
            "Receipt": "RCT",
            "Journal": "JRN",
        }[kind]
        self.t.ledger.append(
            {
                "voucher_no": f"{prefix}/{self.seq(prefix):04d}",
                "voucher_type": kind,
                "voucher_date": d.isoformat(),
                "party_name": party,
                "party_gstin": gstin,
                "reference": ref or None,
                "amount": amount,
                "debit": amount if debit else 0.0,
                "credit": 0.0 if debit else amount,
                "narration": narration,
            }
        )

    # ── IMS ──
    def ims(self) -> None:
        for p in sorted((p for p in self.w.plans if p.ims), key=lambda p: (p.invoice_date, p.uid)):
            filed = min(p.invoice_date + timedelta(days=self.rng.randint(2, 26)), self.as_of_day)
            self.t.ims.append(
                {
                    "ims_id": f"IMS{self.seq('ims'):05d}",
                    "supplier_gstin": p.party.gstin,
                    "supplier_name": p.party.name,
                    "invoice_no": p.invoice_no,
                    "invoice_date": p.invoice_date.isoformat(),
                    "invoice_type": "R",
                    "place_of_supply": "07",
                    "taxable_value": p.taxable,
                    "rate": p.rate,
                    "igst": p.igst,
                    "cgst": p.cgst,
                    "sgst": p.sgst,
                    "total": p.total,
                    "return_period": self.w.period.replace("-", "")[4:] + self.w.period[:4],
                    "filed_on": filed.isoformat(),
                    "status": "No action",
                }
            )

    # ── reference data ──
    def reference(self) -> None:
        for x in self.w.firms:
            self.t.counterparties.append(
                {
                    "gstin": x.gstin,
                    "pan": x.pan,
                    "name": x.name,
                    "city": x.city,
                    "state_code": x.state_code,
                    "role": x.role,
                    "registered_on": x.registered_on.isoformat(),
                    "address": x.address,
                    "phone": x.phone,
                    "bank_account": x.bank_account,
                    "status": x.status,
                    "ewb_count_90d": x.ewb_count_90d,
                    "turnover_3m_avg": x.turnover_3m_avg,
                    "turnover_month": x.turnover_month,
                    "returns_missed_6m": x.returns_missed_6m,
                    "tier": x.tier,
                    "tags": ",".join(x.tags),
                }
            )
        for u in sorted(self.w.upstream, key=lambda u: (u.invoice_date, u.seller, u.invoice_no)):
            self.t.upstream_invoices.append(
                {
                    "seller_gstin": u.seller,
                    "buyer_gstin": u.buyer,
                    "invoice_no": u.invoice_no,
                    "invoice_date": u.invoice_date.isoformat(),
                    "month": u.invoice_date.strftime("%Y-%m"),
                    "hsn": u.hsn,
                    "value": u.value,
                }
            )
        self.t.hsn_rates = hsn_table.table_rows()

    def run(self) -> Tables:
        self.road()
        self.noise()
        self.invoices()
        self.bank_and_books()
        self.ims()
        self.reference()
        return self.t


def derive(w: World) -> Tables:
    return Deriver(w).run()
