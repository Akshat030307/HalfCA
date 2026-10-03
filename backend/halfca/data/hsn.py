"""Synthetic HSN rate table for a hardware distributor, before and after GST 2.0.

Rates are modelled on the GST 2.0 rationalisation (22 Sep 2025: 12% and 28% slabs
abolished, items moved mostly to 5% or 18%). It is demo data, not a legal reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from halfca import config


@dataclass(frozen=True)
class Hsn:
    code: str
    description: str
    rate_pre: float  # until 21 Sep 2025
    rate_post: float  # from 22 Sep 2025
    unit: str
    unit_price: float  # typical wholesale price per unit, ₹


HSN_TABLE: tuple[Hsn, ...] = (
    Hsn("7304", "Seamless steel tubes and pipes", 18, 18, "kg", 92),
    Hsn("7305", "Large-diameter welded steel pipes", 18, 18, "kg", 84),
    Hsn("7306", "Welded steel tubes, GI pipes", 18, 18, "kg", 78),
    Hsn("7307", "Tube or pipe fittings (elbows, tees, sockets)", 18, 18, "pcs", 145),
    Hsn("7308", "Steel structures and parts", 18, 18, "kg", 88),
    Hsn("7310", "Steel tanks, drums and containers", 18, 18, "pcs", 2400),
    Hsn("7312", "Stranded wire and wire ropes", 18, 18, "kg", 120),
    Hsn("7313", "Barbed wire", 18, 18, "kg", 82),
    Hsn("7314", "Wire mesh and fencing", 18, 18, "kg", 96),
    Hsn("7315", "Chains of iron or steel", 18, 18, "kg", 140),
    Hsn("7317", "Nails, tacks and staples", 18, 18, "kg", 86),
    Hsn("7318", "Screws, bolts, nuts and washers", 18, 18, "kg", 165),
    Hsn("7320", "Springs of iron or steel", 18, 18, "pcs", 38),
    Hsn("7323", "Steel kitchen and household articles", 12, 5, "pcs", 260),
    Hsn("7324", "Steel sinks and sanitary ware", 18, 18, "pcs", 2100),
    Hsn("7326", "Other articles of iron or steel", 18, 18, "pcs", 75),
    Hsn("7213", "Steel bars and rods, hot-rolled", 18, 18, "kg", 64),
    Hsn("7214", "TMT bars", 18, 18, "kg", 62),
    Hsn("7216", "Steel angles, shapes and sections", 18, 18, "kg", 66),
    Hsn("7217", "Steel wire", 18, 18, "kg", 74),
    Hsn("7208", "Flat-rolled steel sheets", 18, 18, "kg", 68),
    Hsn("7403", "Refined copper", 18, 18, "kg", 840),
    Hsn("7408", "Copper wire", 18, 18, "kg", 880),
    Hsn("7411", "Copper tubes and pipes", 18, 18, "kg", 910),
    Hsn("7412", "Copper tube fittings", 18, 18, "pcs", 190),
    Hsn("7604", "Aluminium bars and profiles", 18, 18, "kg", 285),
    Hsn("7608", "Aluminium tubes and pipes", 18, 18, "kg", 310),
    Hsn("7610", "Aluminium doors, windows and structures", 18, 18, "pcs", 5200),
    Hsn("7615", "Aluminium kitchen and sanitary articles", 12, 5, "pcs", 340),
    Hsn("8201", "Spades, shovels and agricultural hand tools", 12, 5, "pcs", 420),
    Hsn("8202", "Hand saws and blades", 18, 18, "pcs", 310),
    Hsn("8203", "Files, pliers and pincers", 18, 18, "pcs", 220),
    Hsn("8204", "Spanners and wrenches", 18, 18, "pcs", 280),
    Hsn("8205", "Hand tools, hammers, vices", 18, 18, "pcs", 350),
    Hsn("8207", "Drill bits and interchangeable tools", 18, 18, "pcs", 160),
    Hsn("8301", "Padlocks and locks", 18, 18, "pcs", 240),
    Hsn("8302", "Hinges, handles and door fittings", 18, 18, "pcs", 95),
    Hsn("8307", "Flexible metal tubing", 18, 18, "m", 140),
    Hsn("8311", "Welding electrodes and rods", 18, 18, "kg", 210),
    Hsn("8413", "Water pumps", 18, 18, "pcs", 6400),
    Hsn("8424", "Agricultural sprayers", 12, 5, "pcs", 1850),
    Hsn("8467", "Hand-held power tools", 18, 18, "pcs", 3900),
    Hsn("8481", "Taps, cocks and valves", 18, 18, "pcs", 380),
    Hsn("8482", "Ball and roller bearings", 18, 18, "pcs", 210),
    Hsn("8536", "Switches, sockets and connectors", 18, 18, "pcs", 85),
    Hsn("8544", "Insulated wire and cables", 18, 18, "m", 46),
    Hsn("3917", "PVC and HDPE pipes", 18, 18, "m", 120),
    Hsn("3922", "Plastic sinks, baths and cisterns", 18, 18, "pcs", 1450),
    Hsn("3925", "Plastic builders' ware, water tanks", 18, 18, "pcs", 3800),
    Hsn("3926", "Other plastic articles", 18, 18, "pcs", 60),
    Hsn("3208", "Enamel paints and varnishes", 18, 18, "ltr", 290),
    Hsn("3209", "Emulsion paints", 18, 18, "ltr", 240),
    Hsn("3214", "Wall putty and sealants", 18, 18, "kg", 28),
    Hsn("3506", "Adhesives", 18, 18, "kg", 260),
    Hsn("2523", "Portland cement", 28, 18, "bag", 365),
    Hsn("6810", "Cement blocks and pavers", 18, 18, "pcs", 42),
    Hsn("6907", "Ceramic floor and wall tiles", 18, 18, "box", 520),
    Hsn("6910", "Ceramic sinks and WC pans", 18, 18, "pcs", 2600),
    Hsn("7003", "Glass sheets", 18, 18, "sqm", 640),
    Hsn("4009", "Rubber hoses", 18, 18, "m", 95),
    Hsn("4016", "Rubber gaskets and washers", 18, 18, "pcs", 14),
    Hsn("5607", "Ropes and twine", 12, 5, "kg", 180),
    Hsn("9603", "Brooms and brushes", 12, 5, "pcs", 70),
)

BY_CODE: dict[str, Hsn] = {h.code: h for h in HSN_TABLE}


def rate_on(code: str, on: date) -> float:
    h = BY_CODE[code]
    return h.rate_post if on >= config.GST2_EFFECTIVE else h.rate_pre


def table_rows() -> list[dict[str, object]]:
    """hsn_rates rows: one per HSN per regime, with effective_from / effective_to."""
    start = date(2017, 7, 1)
    pre_end = date.fromordinal(config.GST2_EFFECTIVE.toordinal() - 1)
    rows: list[dict[str, object]] = []
    for h in HSN_TABLE:
        rows.append(
            {
                "hsn": h.code,
                "description": h.description,
                "rate": h.rate_pre,
                "effective_from": start.isoformat(),
                "effective_to": pre_end.isoformat(),
            }
        )
        rows.append(
            {
                "hsn": h.code,
                "description": h.description,
                "rate": h.rate_post,
                "effective_from": config.GST2_EFFECTIVE.isoformat(),
                "effective_to": None,
            }
        )
    return rows
