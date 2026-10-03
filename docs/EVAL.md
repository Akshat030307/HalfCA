# Half CA: detection accuracy on synthetic data

Measured 2026-10-03 with `make eval`: 10 random-mode months
(seeds 1, 2, 3, 4, 5, 6, 7, 8, 9, 10), each about 550 invoices with discrepancies planted at
the catalogue rates in `CLAUDE.md`. Stage-4 matching: skipped (no model).

**These numbers are measured on synthetic data.** They say how well the engines find what
the generator planted, not how they would do on real books. The generator and the engines
were written from the same spec, so planted cases are clear-cut; real books are messier
(errors overlap, names and references are dirtier), so expect lower numbers there.

| Code | Discrepancy | Planted | Flagged | Correct | Precision | Recall |
|---|---|---:|---:|---:|---:|---:|
| D01 | Amount mismatch | 104 | 104 | 104 | 100% | 100% |
| D02 | Date mismatch | 62 | 62 | 62 | 100% | 100% |
| D03 | Invoice ID typo / reformat | 105 | 105 | 105 | 100% | 100% |
| D04 | Wrong tax rate | 89 | 89 | 89 | 100% | 100% |
| D05 | Wrong tax head | 52 | 52 | 52 | 100% | 100% |
| D06 | Tax arithmetic error | 22 | 22 | 22 | 100% | 100% |
| D07 | Exact duplicate | 5 | 5 | 5 | 100% | 100% |
| D08 | Near-duplicate | 19 | 19 | 19 | 100% | 100% |
| D09 | Invoice without payment / payment without invoice | 117 | 208 | 116 | 55.8% | 99.1% |
| D10 | In books, not on IMS | 25 | 25 | 25 | 100% | 100% |
| D11 | Missing e-way bill | 33 | 33 | 33 | 100% | 100% |
| D12 | Paper-only supply | 21 | 21 | 21 | 100% | 100% |
| D13 | Impossible journey | 9 | 9 | 9 | 100% | 100% |
| D14 | Recycled e-way bill | 14 | 14 | 14 | 100% | 100% |
| D15 | Supplier fed by a circular-trading ring | 107 | 107 | 107 | 100% | 100% |
| D16 | Threshold hugging | 103 | 109 | 103 | 94.5% | 100% |
| **ALL** | All types | 887 | 984 | 886 | 90.0% | 99.9% |

Where the extra flags come from:

- **D09** extra flags: 91 × unpaid past terms (clean invoices still unpaid more than 30 days after their date on the as-of day. The generator pays clean invoices 0–45 days late, so these are real gaps under the 30-day rule that it simply did not label); 1 × payment without invoice (bank lines with no invoice that were not planted as D09).
- **D16** extra flags: 6 × hugger's other ₹45–50k invoice.

How it is scored (per invoice, `backend/halfca/eval.py`):

- *Planted*: invoices the generator labelled with that code. *Flagged*: invoices the engines
  flagged for it. *Correct*: both. Precision = correct ÷ flagged; recall = correct ÷ planted.
- D09 counts unbooked and unpaid invoices by invoice, and matches a payment with no
  invoice to a payment-only finding by party name.
- D15 counts invoices from suppliers whose credit taint reaches 0.7;
  D16 counts the ₹45,000–₹49,999 invoices of a supplier flagged for threshold hugging.
- Every month is written in its native formats and read back through the upload loaders,
  so the run covers ingestion as well as the engines.
