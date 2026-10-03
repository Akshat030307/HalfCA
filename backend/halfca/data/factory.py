"""Deterministic building blocks for synthetic firms, numbers, dates and amounts.

Every company, GSTIN, phone and bank account here is fictional. Phones use the +91 55
range (not a mobile series) and bank accounts carry a SYN prefix so nothing can be
mistaken for a real one.
"""

from __future__ import annotations

import math
import random
import string
from datetime import date, timedelta

from halfca.ingest.gstin import make_gstin

from .model import Firm

SURNAMES = [
    "Agarwal",
    "Bansal",
    "Goyal",
    "Mittal",
    "Garg",
    "Gupta",
    "Jain",
    "Khanna",
    "Kapoor",
    "Malhotra",
    "Sethi",
    "Bhatia",
    "Chawla",
    "Dhingra",
    "Grover",
    "Kohli",
    "Luthra",
    "Narang",
    "Ahuja",
    "Batra",
    "Chopra",
    "Dua",
    "Gulati",
    "Juneja",
    "Kalra",
    "Madan",
    "Nagpal",
    "Puri",
    "Sachdeva",
    "Talwar",
    "Verma",
    "Yadav",
    "Saini",
    "Rana",
    "Chauhan",
    "Rathore",
    "Tyagi",
    "Rastogi",
    "Tiwari",
    "Pandey",
    "Mishra",
    "Saxena",
    "Maheshwari",
    "Khandelwal",
    "Somani",
    "Singhal",
    "Bhalla",
    "Anand",
    "Sood",
    "Vohra",
    "Wadhwa",
    "Bedi",
    "Sahni",
    "Marwah",
    "Oberoi",
    "Thapar",
    "Kakkar",
    "Bhasin",
    "Taneja",
    "Arneja",
    "Dhawan",
    "Chadha",
    "Gill",
    "Sandhu",
    "Dhillon",
    "Grewal",
    "Bajwa",
    "Sidhu",
    "Tandon",
    "Rawat",
    "Negi",
    "Bisht",
    "Joshi",
    "Bhardwaj",
    "Kaushik",
    "Vashisht",
]

AUSPICIOUS = [
    "Shree Balaji",
    "Shiv Shakti",
    "Om Sai",
    "Jai Durga",
    "Maa Bhagwati",
    "Shree Ram",
    "Ganpati",
    "Laxmi",
    "Saraswati",
    "Radhe Krishna",
    "Gurukripa",
    "Navkar",
    "Mahavir",
    "Vishwakarma",
    "Sanjivani",
    "Pragati",
    "Unnati",
    "Samrat",
    "Royal",
    "National",
    "Modern",
    "New India",
    "Indus",
    "Sunrise",
    "Star",
    "Diamond",
    "Golden",
    "Vardhman",
    "Shubh Laxmi",
    "Kamdhenu",
    "Shivam",
    "Aadinath",
    "Tirupati",
    "Siddhi Vinayak",
    "Neelkanth",
    "Trimurti",
    "Ekta",
    "Sangam",
    "Anmol",
    "Kohinoor",
]

SUPPLIER_GOODS = [
    "Steel",
    "Pipes",
    "Tubes",
    "Fittings",
    "Fasteners",
    "Wires",
    "Alloys",
    "Metals",
    "Hardware",
    "Tools",
    "Valves",
    "Sanitary",
    "Paints",
    "Cables",
    "Castings",
    "Forgings",
    "Plast",
    "Polymers",
    "Locks",
    "Electricals",
]
SUPPLIER_SUFFIX = [
    "Industries",
    "Udyog",
    "Enterprises",
    "Traders",
    "Pvt Ltd",
    "& Co",
    "Works",
    "Manufacturing Co",
    "Corporation",
    "& Sons",
    "Impex",
    "Products",
]
UPSTREAM_GOODS = [
    "Ispat",
    "Steel Rolling Mills",
    "Wire Drawing",
    "Metal Craft",
    "Strips",
    "Billets",
    "Ingots",
    "Polymers",
    "Chemicals",
    "Pigments",
    "Refractories",
    "Castings",
    "Galvanisers",
    "Alloys",
    "Extrusions",
    "Profiles",
    "Coaters",
    "Resins",
    "Forge",
    "Foundry",
]
CUSTOMER_PATTERNS = [
    "{s} Hardware & Paints",
    "{a} Sanitary Store",
    "{s} Builders",
    "{a} Hardware Mart",
    "{s} Construction Co",
    "{a} Electricals & Hardware",
    "{s} Interiors",
    "{a} Tiles & Sanitation",
    "{s} Hardware Stores",
    "{a} Building Material",
    "{s} Contractors",
    "{a} Paint House",
    "{s} Trading Co",
    "{a} Plumbing Solutions",
    "{s} Infra Projects",
]

AREAS: dict[str, tuple[str, ...]] = {
    "Delhi": (
        "Naraina Industrial Area",
        "Okhla Phase 2",
        "Mundka Industrial Area",
        "Chawri Bazar",
        "Kirti Nagar",
        "Wazirpur Industrial Area",
        "Bawana Sector 3",
        "Lajpat Rai Market",
        "Mayapuri Phase 1",
        "Patparganj Industrial Area",
    ),
    "Ludhiana": ("Focal Point Phase 5", "Industrial Area A", "Gill Road", "GT Road, Dhandari"),
    "Ambala": ("Industrial Area, Ambala Cantt", "GT Road, Ambala City"),
    "Karnal": ("Sector 3 HSIIDC", "GT Road, Karnal", "Industrial Area, Kunjpura Road"),
    "Moradabad": ("Delhi Road", "Industrial Estate, Lakri Fazalpur", "Kanth Road"),
    "Jaipur": ("VKI Area Road 14", "Sitapura Industrial Area", "Jhotwara Industrial Area"),
    "Kanpur": ("Panki Industrial Area", "Dada Nagar", "Fazalganj"),
    "Agra": ("Sikandra Industrial Area", "Nunhai Industrial Estate"),
    "Lucknow": ("Talkatora Industrial Area", "Aishbagh", "Chinhat Industrial Area"),
    "Sonipat": ("Kundli Industrial Area", "HSIIDC Rai"),
    "Ghaziabad": ("Loha Mandi", "Sahibabad Industrial Area"),
    "Noida": ("Sector 63", "Phase 2"),
    "Faridabad": ("Sector 24", "NIT Industrial Area"),
    "Gurugram": ("Udyog Vihar Phase 4", "Sector 37"),
}

RTO: dict[str, tuple[str, ...]] = {
    "Delhi": ("DL1L", "DL1M", "DL1G"),
    "Ludhiana": ("PB10",),
    "Ambala": ("HR01",),
    "Karnal": ("HR05",),
    "Moradabad": ("UP21",),
    "Jaipur": ("RJ14",),
    "Kanpur": ("UP78",),
    "Agra": ("UP80",),
    "Lucknow": ("UP32",),
}

CITY_STATE: dict[str, str] = {
    "Delhi": "07",
    "Ludhiana": "03",
    "Ambala": "06",
    "Karnal": "06",
    "Sonipat": "06",
    "Gurugram": "06",
    "Faridabad": "06",
    "Jaipur": "08",
    "Moradabad": "09",
    "Kanpur": "09",
    "Agra": "09",
    "Lucknow": "09",
    "Ghaziabad": "09",
    "Noida": "09",
}


class Factory:
    """Unique, seeded generators for one World."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self._names: set[str] = set()
        self._pans: set[str] = set()
        self._ewbs: set[str] = set()
        self._vehicles: set[str] = set()
        self._addresses: set[str] = set()

    # ── names ──
    def reserve(self, *names: str) -> None:
        self._names.update(n.lower() for n in names)

    def _unique(self, make) -> str:  # type: ignore[no-untyped-def]
        for _ in range(500):
            name = make()
            if name.lower() not in self._names:
                self._names.add(name.lower())
                return name
        raise RuntimeError("ran out of unique names")

    def supplier_name(self) -> str:
        r = self.rng
        return self._unique(
            lambda: (
                f"{r.choice(SURNAMES + AUSPICIOUS)} {r.choice(SUPPLIER_GOODS)} "
                f"{r.choice(SUPPLIER_SUFFIX)}"
            )
        )

    def upstream_name(self) -> str:
        r = self.rng
        return self._unique(
            lambda: (
                f"{r.choice(SURNAMES + AUSPICIOUS)} {r.choice(UPSTREAM_GOODS)}"
                + r.choice(["", " Pvt Ltd", " Ltd", " Industries", " & Co", " LLP"])
            )
        )

    def customer_name(self) -> str:
        r = self.rng
        return self._unique(
            lambda: r.choice(CUSTOMER_PATTERNS).format(s=r.choice(SURNAMES), a=r.choice(AUSPICIOUS))
        )

    # ── identity ──
    def pan(self, name: str, fixed: str | None = None) -> str:
        if fixed:
            self._pans.add(fixed)
            return fixed
        kind = "C" if ("Pvt Ltd" in name or name.endswith(" Ltd") or "LLP" in name) else "F"
        initial = name.strip()[0].upper()
        if not initial.isalpha():
            initial = "X"
        for _ in range(500):
            pan = (
                "AA"
                + self.rng.choice(string.ascii_uppercase)
                + kind
                + initial
                + f"{self.rng.randint(1000, 9999)}"
                + self.rng.choice(string.ascii_uppercase)
            )
            if pan not in self._pans:
                self._pans.add(pan)
                return pan
        raise RuntimeError("ran out of PANs")

    def address(self, city: str) -> str:
        """Unique per firm: a shared address is a taint signal, so it only happens on purpose."""
        for _ in range(500):
            area = self.rng.choice(AREAS.get(city, ("Main Road",)))
            kind = self.rng.choice(["Plot", "Shop", "Unit", "Khasra"])
            addr = f"{kind} {self.rng.randint(2, 480)}, {area}, {city}"
            if addr not in self._addresses:
                self._addresses.add(addr)
                return addr
        raise RuntimeError("ran out of addresses")

    def phone(self) -> str:
        return f"+91 55{self.rng.randint(100, 999)} {self.rng.randint(10000, 99999)}"

    def bank_account(self) -> str:
        return f"SYN{self.rng.randint(10**11, 10**12 - 1)}"

    def firm(
        self,
        name: str,
        city: str,
        role: str,
        *,
        registered_on: date,
        prefix: str = "",
        pan: str | None = None,
        gstin: str | None = None,
        tags: list[str] | None = None,
    ) -> Firm:
        state = CITY_STATE[city]
        pan_ = pan or self.pan(name)
        gstin_ = gstin or make_gstin(state, pan_)
        return Firm(
            gstin=gstin_,
            pan=pan_,
            name=name,
            city=city,
            state_code=state,
            role=role,  # type: ignore[arg-type]
            registered_on=registered_on,
            address=self.address(city),
            phone=self.phone(),
            bank_account=self.bank_account(),
            invoice_prefix=prefix,
            tags=list(tags or []),
        )

    def prefix_for(self, name: str) -> str:
        """Invoice series like 'BS/' or 'GTI/26/' from a firm name."""
        words = [w for w in name.replace("&", " ").split() if w[0].isalpha()]
        letters = "".join(w[0] for w in words[:3]).upper()
        style = self.rng.random()
        if style < 0.4:
            return f"{letters}/"
        if style < 0.7:
            return f"{letters}/26/"
        if style < 0.85:
            return f"{letters}-"
        return f"{letters}/{self.rng.choice(['T', 'GST', 'S'])}/"

    # ── road ──
    def reserve_vehicle(self, plate: str) -> None:
        self._vehicles.add(plate)

    def vehicle(self, city: str) -> str:
        for _ in range(500):
            rto = self.rng.choice(RTO.get(city, ("DL1L",)))
            series = "".join(
                self.rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ")
                for _ in range(self.rng.choice([1, 2, 2]))
            )
            v = f"{rto} {series} {self.rng.randint(1000, 9999)}"
            if v not in self._vehicles:
                self._vehicles.add(v)
                return v
        raise RuntimeError("ran out of vehicles")

    def ewb_no(self, fixed: str | None = None) -> str:
        if fixed:
            self._ewbs.add(fixed)
            return fixed
        for _ in range(500):
            e = f"38{self.rng.randint(10**9, 10**10 - 1)}"
            if e not in self._ewbs:
                self._ewbs.add(e)
                return e
        raise RuntimeError("ran out of e-way bill numbers")

    # ── time and money ──
    def business_day(self, start: date, end: date) -> date:
        """A date in [start, end], weekdays favoured over Sundays."""
        days = [start + timedelta(d) for d in range((end - start).days + 1)]
        weights = [0.25 if d.weekday() == 6 else (0.8 if d.weekday() == 5 else 1.0) for d in days]
        return self.rng.choices(days, weights)[0]

    def lognormal(self, median: float, sigma: float, lo: float, hi: float) -> float:
        for _ in range(100):
            v = math.exp(math.log(median) + sigma * self.rng.gauss(0, 1))
            if lo <= v <= hi:
                return v
        return min(max(median, lo), hi)

    def taxable_amount(self, median: float, sigma: float = 0.85) -> float:
        """A realistic taxable value: qty x unit price, so it rarely lands on round numbers."""
        v = self.lognormal(median, sigma, 3_000, 9_00_000)
        return round(v + self.rng.random(), 2)
