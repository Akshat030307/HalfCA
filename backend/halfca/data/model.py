"""Generator data model.

A scenario builds a World: firms, one InvoicePlan per invoice and the upstream B2B
network. derive.py turns the World into the source files (invoices, bank, Tally day
book, IMS feed, e-way bills + toll crossings) and the reference data.

An InvoicePlan says what the invoice is *and* how every other thread should look:
whether the books record it (and how), whether it was paid, whether the supplier filed
it on IMS, and what the road saw. Truth labels record what was injected on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Direction = Literal["inward", "outward"]
Head = Literal["igst", "cgst_sgst"]
# How the books (Tally) record the invoice.
LedgerMode = Literal[
    "exact",  # same reference, party GSTIN present: pairs at stage 1
    "no_gstin",  # same reference, party ledger has no GSTIN: pairs at stage 2
    "id_variant",  # reference typed differently but normalises equal: stage 2, ID flag
    "garbled",  # reference missing, party name close: stage 3 (fuzzy)
    "alias",  # reference missing, party name far: stage 4 (AI) or unmatched without AI
    "missing",  # never booked: unmatched
]
PaymentMode = Literal["normal", "short", "none", "double"]
# What the road saw (inter-state inward goods at or above the e-way bill threshold).
RoadMode = Literal["auto", "missing_ewb", "paper_only", "impossible", "recycled"]


def money(value: float | Decimal) -> float:
    """Round to paise, half-up, as an invoice would (floats alone round 0.745 down)."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass
class Firm:
    gstin: str
    pan: str
    name: str
    city: str
    state_code: str
    role: Literal["self", "supplier", "customer", "upstream"]
    registered_on: date
    address: str
    phone: str
    bank_account: str
    invoice_prefix: str = ""
    status: str = "Active"
    ewb_count_90d: int = 0
    turnover_3m_avg: float = 0.0
    turnover_month: float = 0.0
    returns_missed_6m: int = 0
    tier: int = 0  # upstream tier (1 = sells to a direct supplier)
    tags: list[str] = field(default_factory=list)


@dataclass
class Trip:
    """An explicit truck movement (heroes). Otherwise derive.py invents a normal trip."""

    vehicle_no: str
    generated_at: datetime
    departure: datetime
    speed_kmh: float
    ewb_no: str | None = None
    crossings: bool = True  # False = paper-only (no crossings in the window)


@dataclass
class InvoicePlan:
    uid: str
    direction: Direction
    party: Firm  # supplier for inward, customer for outward
    invoice_no: str
    invoice_date: date
    hsn: str
    taxable: float
    rate: float  # rate actually charged on the invoice
    head: Head  # tax head actually charged
    labels: list[str] = field(default_factory=list)  # truth labels (D01..D16, hero:...)
    tax_override: float | None = None  # D06: recorded tax differs from taxable x rate

    # Books
    ledger: LedgerMode = "exact"
    ledger_ref: str | None = None  # reference text when it differs from invoice_no
    ledger_party: str | None = None  # party ledger name when it differs from party.name
    ledger_amount_delta: float = 0.0
    ledger_date_delta: int = 0  # days from invoice date to booking date

    # Bank
    payment: PaymentMode = "normal"
    payment_delta: float = 0.0  # short payment amount
    payment_lag: int | None = None  # days after invoice date; None = drawn at random

    # IMS (inward only)
    ims: bool = False

    # Road (inward only)
    road: RoadMode = "auto"
    trip: Trip | None = None
    ewb_no: str | None = None  # e-way bill quoted on the invoice
    recycled_from: str | None = None  # uid whose e-way bill this invoice quotes

    dup_of: str | None = None  # uid of the original, for duplicate copies

    # ── derived money ──
    @property
    def tax(self) -> float:
        if self.tax_override is not None:
            return self.tax_override
        return money(Decimal(str(self.taxable)) * Decimal(str(self.rate)) / 100)

    @property
    def igst(self) -> float:
        return self.tax if self.head == "igst" else 0.0

    @property
    def cgst(self) -> float:
        return 0.0 if self.head == "igst" else money(Decimal(str(self.tax)) / 2)

    @property
    def sgst(self) -> float:
        return 0.0 if self.head == "igst" else money(self.tax - self.cgst)

    @property
    def total(self) -> float:
        return money(Decimal(str(self.taxable)) + Decimal(str(self.tax)))

    @property
    def supplier_state(self) -> str:
        return self.party.state_code if self.direction == "inward" else "07"

    @property
    def buyer_state(self) -> str:
        return "07" if self.direction == "inward" else self.party.state_code

    @property
    def inter_state(self) -> bool:
        return self.supplier_state != self.buyer_state


@dataclass
class UpstreamInvoice:
    seller: str  # GSTIN
    buyer: str  # GSTIN
    invoice_no: str
    invoice_date: date
    hsn: str
    value: float  # invoice total


@dataclass
class OrphanPayment:
    """A bank line with no invoice behind it (D09, payment without invoice)."""

    uid: str
    party: Firm
    paid_on: date
    amount: float
    direction: Direction


@dataclass
class World:
    scenario: str
    seed: int
    period: str
    as_of: datetime
    me: Firm
    firms: list[Firm]
    plans: list[InvoicePlan]
    upstream: list[UpstreamInvoice]
    targets: dict[str, float] = field(default_factory=dict)  # demo totals the build checks
    orphan_payments: list[OrphanPayment] = field(default_factory=list)
