"""Write derived tables to disk in each source system's own format.

<out>/sources/    what the user uploads: invoice register (CSV), HDFC statement (CSV),
                  Tally day book (XML), IMS feed (JSON), e-way bills + toll crossings (JSON)
<out>/reference/  aggregator/officer-side data: counterparties, upstream invoices, HSN rates,
                  road geography
<out>/truth/      what was injected on purpose (for tests and make eval only)
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

from halfca import config

from .derive import Row, Tables
from .model import World

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def source_names(period: str) -> dict[str, str]:
    y, m = period.split("-")
    tag = f"{MONTHS[int(m) - 1]}{y[2:]}"
    return {
        "invoices": f"invoices_{tag}.csv",
        "bank": f"hdfc_current_{tag}.csv",
        "ledger": f"tally_daybook_{tag}.xml",
        "ims": f"ims_feed_{period}.json",
        "eway": f"eway_bills_{tag}.json",
    }


def _csv(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: "" if v is None else v for k, v in r.items()})


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


def _tally_xml(path: Path, w: World, rows: list[Row]) -> None:
    """A Tally-flavoured day book export. Tally signs debits negative."""
    env = ET.Element("ENVELOPE")
    ET.SubElement(ET.SubElement(env, "HEADER"), "TALLYREQUEST").text = "Import Data"
    imp = ET.SubElement(ET.SubElement(env, "BODY"), "IMPORTDATA")
    desc = ET.SubElement(imp, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "Day Book"
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = w.me.name
    ET.SubElement(sv, "SVFROMDATE").text = f"{w.period.replace('-', '')}01"
    ET.SubElement(sv, "SVTODATE").text = w.as_of.strftime("%Y%m%d")
    data = ET.SubElement(imp, "REQUESTDATA")
    for r in rows:
        msg = ET.SubElement(data, "TALLYMESSAGE")
        v = ET.SubElement(msg, "VOUCHER", VCHTYPE=str(r["voucher_type"]), ACTION="Create")
        ET.SubElement(v, "DATE").text = str(r["voucher_date"]).replace("-", "")
        ET.SubElement(v, "VOUCHERTYPENAME").text = str(r["voucher_type"])
        ET.SubElement(v, "VOUCHERNUMBER").text = str(r["voucher_no"])
        if r["reference"]:
            ET.SubElement(v, "REFERENCE").text = str(r["reference"])
        ET.SubElement(v, "PARTYLEDGERNAME").text = str(r["party_name"])
        if r["party_gstin"]:
            ET.SubElement(v, "PARTYGSTIN").text = str(r["party_gstin"])
        ET.SubElement(v, "NARRATION").text = str(r["narration"])
        entry = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(entry, "LEDGERNAME").text = str(r["party_name"])
        debit = float(r["debit"]) > 0  # type: ignore[arg-type]
        ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
        amount = float(r["amount"])  # type: ignore[arg-type]
        ET.SubElement(entry, "AMOUNT").text = f"{-amount if debit else amount:.2f}"
    ET.indent(env, space=" ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(env).write(path, encoding="utf-8", xml_declaration=True)


def write(w: World, t: Tables, out: Path) -> dict[str, Path]:
    for sub in ("sources", "reference", "truth"):
        shutil.rmtree(out / sub, ignore_errors=True)
    names = source_names(w.period)
    src = out / "sources"
    paths = {k: src / v for k, v in names.items()}

    _csv(paths["invoices"], t.invoices)
    _csv(paths["bank"], t.bank)
    _tally_xml(paths["ledger"], w, t.ledger)
    _json(
        paths["ims"],
        {
            "gstin": w.me.gstin,
            "return_period": w.period,
            "fetched_at": w.as_of.isoformat(),
            "records": t.ims,
        },
    )
    _json(
        paths["eway"],
        {
            "recipient_gstin": w.me.gstin,
            "fetched_at": w.as_of.isoformat(),
            "eway_bills": t.eway_bills,
            "toll_crossings": t.toll_crossings,
        },
    )

    ref = out / "reference"
    _csv(ref / "counterparties.csv", t.counterparties)
    _csv(ref / "upstream_invoices.csv", t.upstream_invoices)
    _csv(ref / "hsn_rates.csv", t.hsn_rates)
    shutil.copyfile(config.ROUTES_PATH, ref / "routes.json")

    truth = out / "truth"
    _csv(truth / "truth_labels.csv", t.truth_labels)
    _json(
        truth / "manifest.json",
        {
            "scenario": w.scenario,
            "seed": w.seed,
            "period": w.period,
            "as_of": w.as_of.isoformat(),
            "user_gstin": w.me.gstin,
            "targets": w.targets,
            "counts": {
                "invoices": len(t.invoices),
                "bank": len(t.bank),
                "ledger": len(t.ledger),
                "ims": len(t.ims),
                "eway_bills": len(t.eway_bills),
                "toll_crossings": len(t.toll_crossings),
                "counterparties": len(t.counterparties),
                "upstream_invoices": len(t.upstream_invoices),
            },
        },
    )
    return paths
