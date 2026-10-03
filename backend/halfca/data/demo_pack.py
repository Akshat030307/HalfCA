"""The demo month as a folder a person would actually hand over.

  Arora Hardware – Sep 2026/
    invoices_sep26.csv · hdfc_current_sep26.csv · tally_daybook_sep26.xml
    ims_feed_2026-09.json · eway_bills_sep26.json
    invoices/   a few supplier invoice PDFs (the story's bills), rendered with WeasyPrint
    README.txt

  python -m halfca.data.demo_pack --out demo-pack        (make demo-pack)
  GET /api/demo-pack.zip                                  (download from the app)

Every document is marked as synthetic.
"""

from __future__ import annotations

import argparse
import html
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from halfca import config, fmt
from halfca.ingest.csv_loader import read_eway, read_invoices
from halfca.ingest.gstin import STATES

FOLDER = "Arora Hardware – Sep 2026"
ZIP_NAME = "Arora-Hardware-Sep-2026.zip"
STORY_BILLS = [
    "PP/26/0912",
    "LD/2291",
    "MB/0877",
    "KN/1502",
    "JP/1187",
    "JP/1188",
    "JP/1192",
    "DF/0450",
    "INV-0418",
    "INV/418",
    "KM/26/3341",
    "KM/26/3367",
    "AR/S/2219",
]

_ONES = [
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def _three(n: int) -> str:
    h, rest = divmod(n, 100)
    parts = [f"{_ONES[h]} Hundred"] if h else []
    if rest:
        parts.append(_two(rest))
    return " ".join(parts)


def rupees_in_words(amount: float) -> str:
    """Indian numbering: 1,18,000.50 → 'Rupees One Lakh Eighteen Thousand and Fifty Paise Only'."""
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    parts = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand")):
        if rupees >= size:
            parts.append(
                f"{_three(rupees // size) if size == 10**7 else _two(rupees // size)} {name}"
            )
            rupees %= size
    if rupees:
        parts.append(_three(rupees))
    words = " ".join(parts) or "Zero"
    tail = f" and {_two(paise)} Paise" if paise else ""
    return f"Rupees {words}{tail} Only"


CSS = """
@page { size: A4; margin: 14mm 14mm 16mm; }
body { font-family: 'DejaVu Sans', 'Inter', sans-serif; font-size: 9.5pt; color: #1c130c; }
h1 { font-size: 15pt; margin: 0; letter-spacing: 0.5px; }
.top { display: flex; justify-content: space-between; align-items: flex-start;
       border-bottom: 2px solid #1c130c; padding-bottom: 8px; }
.badge { border: 1.5px solid #1c130c; padding: 4px 10px; font-weight: bold; font-size: 11pt; }
.muted { color: #6b5a4c; }
.grid { display: flex; gap: 14px; margin-top: 10px; }
.box { flex: 1; border: 1px solid #bba68f; padding: 8px 10px; }
.box h3 { margin: 0 0 4px; font-size: 8pt; text-transform: uppercase; letter-spacing: 1px;
          color: #6b5a4c; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { border: 1px solid #bba68f; padding: 5px 6px; text-align: left; }
th { background: #f6e9dc; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.5px; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.total td { font-weight: bold; background: #fbf3ea; }
.words { margin-top: 8px; font-style: italic; }
.foot { display: flex; justify-content: space-between; margin-top: 22px; }
.sign { text-align: right; }
.synthetic { position: fixed; bottom: -8mm; left: 0; right: 0; text-align: center;
             font-size: 7.5pt; color: #9a8472; }
"""


def _esc(v: Any) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def invoice_html(
    inv: pd.Series, supplier: dict[str, Any], buyer: dict[str, Any], ewb: pd.Series | None
) -> str:
    igst = float(inv.igst)
    tax_rows = (
        f"<tr><td colspan='5' class='n'>IGST @ {inv.rate:g}%</td><td class='n'>{fmt.inr(igst)[1:]}"
        "</td></tr>"
        if igst > 0
        else f"<tr><td colspan='5' class='n'>CGST @ {inv.rate / 2:g}%</td><td class='n'>"
        f"{fmt.inr(inv.cgst)[1:]}</td></tr><tr><td colspan='5' class='n'>SGST @ {inv.rate / 2:g}%"
        f"</td><td class='n'>{fmt.inr(inv.sgst)[1:]}</td></tr>"
    )
    ewb_line = (
        f"<div>E-way bill: <b>{fmt.ewb(ewb.ewb_no)}</b></div>"
        f"<div>Vehicle: {_esc(ewb.vehicle_no)}</div>"
        if ewb is not None
        else ""
    )
    date = pd.Timestamp(inv.invoice_date)
    s_code = str(supplier["gstin"])[:2]
    s_state = _esc(STATES.get(s_code, ""))
    pos = _esc(STATES.get(str(inv.place_of_supply), ""))
    qty = f"{int(inv.qty):,} {_esc(inv.unit)}"
    money = {
        k: fmt.inr(float(getattr(inv, k)))[1:] for k in ("unit_price", "taxable_value", "total")
    }
    note = (
        "Synthetic invoice generated for the Half CA demo · fictional company · not a real document"
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="top">
  <div>
    <h1>{_esc(supplier["name"])}</h1>
    <div class="muted">{_esc(supplier["address"])}</div>
    <div>GSTIN <b>{_esc(supplier["gstin"])}</b> · State {s_state} ({s_code})</div>
  </div>
  <div class="badge">TAX INVOICE</div>
</div>
<div class="grid">
  <div class="box"><h3>Bill to</h3>
    <b>{_esc(buyer["name"])}</b><br>{_esc(buyer["address"])}<br>GSTIN {_esc(buyer["gstin"])}</div>
  <div class="box"><h3>Invoice</h3>
    <div>No. <b>{_esc(inv.invoice_no)}</b></div>
    <div>Date {date:%d %b %Y}</div>
    <div>Place of supply {pos} ({_esc(inv.place_of_supply)})</div>
    <div>Reverse charge: No</div>
    {ewb_line}</div>
</div>
<table>
  <tr><th>#</th><th>Description</th><th>HSN</th><th class="n">Qty</th><th class="n">Rate</th>
      <th class="n">Taxable value</th></tr>
  <tr><td>1</td><td>{_esc(inv.description)}</td><td>{_esc(inv.hsn)}</td>
      <td class="n">{qty}</td><td class="n">{money["unit_price"]}</td>
      <td class="n">{money["taxable_value"]}</td></tr>
  {tax_rows}
  <tr class="total"><td colspan="5" class="n">Invoice total (₹)</td>
      <td class="n">{money["total"]}</td></tr>
</table>
<div class="words">{_esc(rupees_in_words(float(inv.total)))}</div>
<div class="foot">
  <div class="muted">Payment: NEFT/RTGS within 30 days.<br>
    Bank a/c {_esc(supplier["bank_account"])}</div>
  <div class="sign">For <b>{_esc(supplier["name"])}</b><br><br><br>Authorised signatory</div>
</div>
<div class="synthetic">{note}</div>
</body></html>"""


def build_pack(out: Path) -> Path:
    from weasyprint import HTML  # heavy import; only when making PDFs

    src = config.DATA_DIR / "sources"
    ref = config.DATA_DIR / "reference"
    if not src.is_dir():
        raise SystemExit("No demo sources yet: run `make data` first")
    folder = out / FOLDER
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "invoices").mkdir(parents=True)
    for f in sorted(src.iterdir()):
        shutil.copyfile(f, folder / f.name)

    invoices = read_invoices(next(src.glob("invoices_*.csv")))
    ewbs, _ = read_eway(next(src.glob("eway_bills_*.json")))
    ewb_by_no = {e.ewb_no: e for _, e in ewbs.iterrows()}
    cp = pd.read_csv(ref / "counterparties.csv", dtype=str, keep_default_na=False)
    firms = {r["gstin"]: r for r in cp.to_dict("records")}
    wanted = [n for n in STORY_BILLS if (invoices.invoice_no == n).sum() == 1]
    for no in wanted:
        inv = invoices[invoices.invoice_no == no].iloc[0]
        supplier = firms[inv.supplier_gstin]
        buyer = firms.get(
            inv.buyer_gstin, {"name": inv.buyer_name, "address": "", "gstin": inv.buyer_gstin}
        )
        ewb = ewb_by_no.get(inv.ewb_no) if isinstance(inv.ewb_no, str) else None
        name = f"{supplier['name'].replace(' ', '-')}_{no.replace('/', '-')}.pdf"
        HTML(string=invoice_html(inv, supplier, buyer, ewb)).write_pdf(folder / "invoices" / name)
    (folder / "README.txt").write_text(
        "Arora Hardware Distributors · September 2026 (synthetic demo data)\n\n"
        "Drag this whole folder onto Half CA's Upload screen.\n\n"
        "  invoices_sep26.csv        invoice register (sales + purchases)\n"
        "  hdfc_current_sep26.csv    bank statement\n"
        "  tally_daybook_sep26.xml   Tally day book (books of account)\n"
        "  ims_feed_2026-09.json     supplier invoices on the GST IMS\n"
        "  eway_bills_sep26.json     e-way bills and the trucks' toll crossings\n"
        "  invoices/                 a few of the supplier bills as PDFs\n\n"
        "Try editing an amount in the invoice CSV before uploading: the change shows up as\n"
        "a new discrepancy. Every company, GSTIN and person here is fictional.\n"
    )
    return folder


def demo_pack_zip() -> Path:
    """Build (or reuse) the downloadable zip of the demo pack."""
    out = config.DATA_DIR / "demo-pack"
    zpath = out / ZIP_NAME
    src = config.DATA_DIR / "sources"
    newest = max((f.stat().st_mtime for f in src.iterdir()), default=0)
    if zpath.is_file() and zpath.stat().st_mtime >= newest:
        return zpath
    folder = build_pack(out)
    tmp = zpath.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(out).as_posix())
    tmp.replace(zpath)
    return zpath


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("demo-pack"))
    args = ap.parse_args()
    folder = build_pack(args.out.resolve())
    pdfs = len(list((folder / "invoices").glob("*.pdf")))
    print(f"→ {folder} ({pdfs} invoice PDFs)")


if __name__ == "__main__":
    main()
