"""Helpers shared by the demo and random scenarios for building invoice plans."""

from __future__ import annotations

from datetime import date

from halfca import config

from . import hsn as hsn_table
from .factory import Factory
from .model import Firm, Head, InvoicePlan

# HSNs a hardware distributor trades most, with relative weights.
COMMON_HSN: tuple[tuple[str, float], ...] = (
    ("7306", 8),
    ("7307", 7),
    ("7318", 6),
    ("3917", 6),
    ("8481", 5),
    ("7214", 5),
    ("8544", 5),
    ("7217", 4),
    ("8302", 4),
    ("3209", 4),
    ("3208", 3),
    ("6907", 3),
    ("6910", 2),
    ("7324", 2),
    ("8301", 3),
    ("8205", 3),
    ("8467", 2),
    ("8536", 3),
    ("3922", 2),
    ("3925", 2),
    ("7304", 2),
    ("7216", 2),
    ("7314", 2),
    ("7323", 2),
    ("8201", 1),
    ("2523", 2),
    ("3214", 2),
    ("7412", 1),
    ("7411", 1),
    ("7610", 1),
)


def correct_rate(hsn: str, on: date) -> float:
    return hsn_table.rate_on(hsn, on)


def correct_head(supplier_state: str, buyer_state: str) -> Head:
    return "cgst_sgst" if supplier_state == buyer_state else "igst"


class PlanMaker:
    """Creates InvoicePlans with correct tax by default; callers override to inject errors."""

    def __init__(self, f: Factory, me: Firm) -> None:
        self.f = f
        self.me = me
        self._n = 0
        self._series: dict[str, int] = {}

    def uid(self) -> str:
        self._n += 1
        return f"i{self._n:04d}"

    def next_number(self, firm: Firm) -> str:
        """Next invoice number from a supplier's series (they bill other buyers in between)."""
        if firm.gstin not in self._series:
            self._series[firm.gstin] = self.f.rng.randint(120, 2400)
        self._series[firm.gstin] += self.f.rng.randint(3, 41)
        n = self._series[firm.gstin]
        width = 4 if self.f.rng.random() < 0.5 else 0
        return f"{firm.invoice_prefix}{n:0{width}d}" if width else f"{firm.invoice_prefix}{n}"

    def random_hsn(self) -> str:
        codes, weights = zip(*COMMON_HSN, strict=True)
        return self.f.rng.choices(codes, weights)[0]

    def make(
        self,
        direction: str,
        party: Firm,
        invoice_no: str,
        invoice_date: date,
        taxable: float,
        hsn: str | None = None,
        *,
        rate: float | None = None,
        head: Head | None = None,
        labels: list[str] | None = None,
        **kw: object,
    ) -> InvoicePlan:
        code = hsn or self.random_hsn()
        ims = bool(kw.pop("ims", direction == "inward"))
        supplier_state = party.state_code if direction == "inward" else self.me.state_code
        buyer_state = self.me.state_code if direction == "inward" else party.state_code
        return InvoicePlan(
            uid=self.uid(),
            direction=direction,  # type: ignore[arg-type]
            party=party,
            invoice_no=invoice_no,
            invoice_date=invoice_date,
            hsn=code,
            taxable=round(taxable, 2),
            rate=correct_rate(code, invoice_date) if rate is None else rate,
            head=correct_head(supplier_state, buyer_state) if head is None else head,
            labels=list(labels or []),
            ims=ims,
            **kw,  # type: ignore[arg-type]
        )


def itc(plans: list[InvoicePlan]) -> float:
    return round(sum(p.tax for p in plans), 2)


def balance_tax(pool: list[InvoicePlan], target_tax: float) -> None:
    """Scale the pool's taxable values so its total tax lands on target (to the rupee).

    The pool keeps its shape (relative sizes); one invoice absorbs the last rupees.
    """
    current = itc(pool)
    if current <= 0:
        raise ValueError("empty balancing pool")
    scale = target_tax / current
    for p in pool:
        p.taxable = round(p.taxable * scale, 2)
    anchor = max(pool, key=lambda p: p.taxable)
    for _ in range(8):
        residual = round(target_tax - itc(pool), 2)
        if abs(residual) < 0.5:
            break
        anchor.taxable = round(anchor.taxable + residual * 100 / anchor.rate, 2)
    if abs(target_tax - itc(pool)) >= 1.0:
        raise AssertionError("tax balancing did not converge")


def within(value: float, lakh_target: float) -> bool:
    """True when value displays as lakh_target at one decimal."""
    return round(value / 1e5, 1) == lakh_target


GST2 = config.GST2_EFFECTIVE
