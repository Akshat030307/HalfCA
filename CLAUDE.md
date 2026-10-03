# CLAUDE.md — Half CA

> **Half CA** — AI GST reconciliation that follows the goods. Half a chartered accountant, all of the paperwork.
> *"The paper says the goods moved. The road says whether they did."*

Half CA is a 24-hour hackathon build for **Problem Statement 2: Intelligent Tax Reconciliation**. It reconciles invoices, payments, ledger and the GST IMS feed (the standard 3-way match), then adds two checks nobody else does:

1. **Follow the Goods:** invoice → e-way bill → the truck's toll crossings. Did the goods physically move?
2. **Follow the Credit:** the upstream supplier graph. Is this ITC built on a circular-trading ring?

This file is the **complete spec**. The build order and deploy flow live in `docs/PLAN.md`.

**Resuming work?** The handoff file below (imported automatically) has the current status, VPS access, workflow and gotchas. Keep it updated at the end of each milestone.

@docs/CONTEXT.md

Server access and the VPS layout are kept out of git, in `docs/CONTEXT.local.md` (only on the maintainer's machine):

@docs/CONTEXT.local.md

### Decisions that override the original brief (2026-10-03)

- **Name:** the project is **Half CA** (it was "Chungi"). Python package `halfca`, domain `halfca.akshatchowdhary.online`.
- **Look:** friendly and a bit playful, not a forensic control room. Dark mode is **pure black**; light mode is **pale orange and peach**. Orange is the brand accent (it replaces road-yellow). See the Frontend and UI spec sections.
- **Hero amounts shrunk** so the demo table holds: `MB/0877` ₹1,18,000 · `KN/1502` ₹1,41,600 · `JP/1187/1188/1192` ₹59,000 each (all invoice totals incl. 18% IGST). The demo table itself is unchanged.
- **Recycled e-way bill:** flag **every** invoice that shares the trip (all 3 JP invoices), not only the ones after the first.
- **Ring detection:** a cycle (length ≤ 6) counts when at least one of its nodes is within 3 hops upstream of the user. The cycle itself may extend further.
- **Stage 4 without an LLM:** skipped, so a no-LLM run shows 20 unmatched instead of 18. `test_demo_numbers` runs with a deterministic stub adjudicator.
- **LLM provider: Groq** (OpenAI-compatible), model `openai/gpt-oss-120b`, set via `HALFCA_LLM_PROVIDER=groq` and `HALFCA_LLM_API_KEY` in `backend/.env` (local) and `/root/halfca/.env` (VPS). Calls run at temperature 0 and are cached on disk (`data/llm_cache.json`) by request hash, so re-runs are stable and free. Tests never call a model: `tests/conftest.py` blanks the provider and uses a deterministic stub adjudicator. Other providers (`openai`, `openrouter`, `ollama`) are one env change away.
- **Deploy:** Docker Compose on the VPS, behind the VPS's shared Caddy. Docker is a deploy tool only; local dev never needs it.
- **Invoice PDFs (M5):** the Groq key has no vision model, so a PDF's **text layer** (pypdf) is what `openai/gpt-oss-120b` reads, into a fixed schema. Python then checks every value against the document's own text (amounts written on it, invoice number and e-way bill verbatim, GSTINs present and checksum-valid, the date in some format); anything unbacked is dropped. Rates and totals are worked out in Python. Scans and images are marked `needs_review`. A PDF that disagrees with the register is a `document` discrepancy ("Invoice PDF"); a PDF missing from the register is added to it. Per upload: at most 25 documents, 180 s.
- **IMS reasons stay templated** even with a key: they are the spec's exact one-liners and can never drift. The model explains them in the copilot instead.
- **Copilot number guard (M5):** every number in a model-written answer must appear in a tool result, the question or the prompt's background facts. One rewrite is allowed, then the templated answer is used. The UI shows "✓ N numbers traced to tool output".
- **MCP SDK v2:** `FastMCP` is now `mcp.server.mcpserver.MCPServer`; `halfca/mcp_server.py` uses it.
- **M6 scope (user, 2026-10-03):** the audit report and the accuracy scores only; no demo-day RUNBOOK.
- **Audit report:** WeasyPrint with the brand fonts bundled in `backend/halfca/report/fonts/` (OFL; the server image only has DejaVu). Cached per dataset, IMS approval state and template version in `data/reports/`.
- **Random mode road codes (M6 fix):** D11–D14 are drawn from the eligible pool (inter-state purchases ≥ ₹50,000) at the catalogue's share of *all* invoices. Drawing per invoice dropped ~85% of them (D13 appeared once in 40 months). The demo month is unaffected.

---

## Problem statement (as given by the hackathon)

> **INTELLIGENT TAX RECONCILIATION.** Build an AI-driven tax reconciliation system that analyzes invoices, transactions, accounting records, and tax data to identify discrepancies, errors, and potential compliance issues. The system should go beyond basic matching and provide:
> - Transaction reconciliation to match invoices, payments, and accounting records.
> - Mismatch & duplicate detection for differences in amounts, dates, invoice IDs, tax values, and repeated records.
> - Tax verification by comparing recorded tax amounts with expected tax based on applicable rates.
> - Missing & unmatched transaction detection to identify incomplete or unaccounted financial records.
> - Anomaly detection to flag unusual transaction and tax patterns.
> - Tax liability analysis to estimate tax obligations from reconciled financial records.
> - Reconciliation dashboard to visualize matched, unmatched, duplicate, and discrepant transactions.
>
> **Dataset:** Teams must generate a synthetic financial dataset containing invoices, transactions, tax rates, tax amounts, accounting records, and intentionally introduced discrepancies.

**Why Half CA is different:** a fake invoice that has been paid and booked passes a 3-way match. The fraud only shows up in two places other tools don't look:
- **The physical world.** India's e-way bill system is integrated with FASTag/RFID toll data.
- **The supplier network.** Fake ITC flows through rings of shell firms trading in circles.

**Context the UI and copilot may reference (all real):**
- GST 2.0 slabs (0 / 5 / 18 / 40%) took effect on 22 Sep 2025, abolishing 12% and 28%.
- IMS (Invoice Management System) action has been mandatory since 1 Apr 2026. Supplier invoices a business doesn't act on are **deemed accepted** into its ITC, correct or not. GSTR-2B generates on the 14th.
- E-way bills are mandatory for inter-state goods consignments above ₹50,000.

**Honest limit:** toll-crossing and upstream supplier data are officer-side or aggregator-side in reality. Half CA positions these modules for auditors and tax authorities, and the demo uses synthetic data.

---

## Golden rules

1. **The LLM never produces a number.** Every tax amount, match decision, score and total comes from deterministic Python. The LLM only:
   - extracts fields from invoice PDFs/images
   - adjudicates stage-4 match candidates (choosing among candidates the rules found)
   - writes plain-language reasons and copilot answers from tool outputs
2. **Synthetic data only.** Every company, GSTIN and person is fictional. Show "Synthetic data" in the UI header.
3. **The demo seed is sacred.** `make data` must regenerate *exactly* the demo numbers below. A test enforces this. Never "fix" a failing demo-number test by editing the expected values; fix the generator or the engine.
4. **The demo must work offline and without an API key.** If no LLM is configured (`HALFCA_LLM_PROVIDER` unset or its key missing):
   - ingestion uses the CSV/JSON path
   - stage-4 matching is skipped (those records go to the unmatched queue)
   - IMS reasons use templates
   - the copilot returns templated answers built from the same tool outputs

   With a key, the LLM layers switch on. The UI must never break either way.
5. **Explainability everywhere.** Every flag carries an `evidence` object (what was recorded, what was expected, and the chain of records behind it). The UI shows it, the copilot cites it, and the PDF report prints it.
6. **No external map tiles or CDNs at runtime.** The map and graph render from bundled data (see Frontend). A hackathon venue's Wi-Fi will fail you.
7. **Small, verified steps.** After each milestone: run the tests, run the app, commit. Don't build features ahead of the engine that feeds them.

---

## Demo dataset: exact targets (seed `2609`, period `2026-09`)

The user is **Arora Hardware Distributors**, GSTIN `07AAKFA4821M1ZA` (Delhi).

| Metric | Value |
|---|---|
| Invoices reconciled | **552** |
| Matching funnel (unmatched left after each stage) | 552 → **61** → **23** → **20** → **18**; paired per stage **491 / 38 / 3 / 2** |
| Matched (clean on paper) | **489**. The 5 physical-trail failures sit *inside* these 489: they pass every paper check |
| Discrepancies | **38**: amount 11 · tax rate 9 · invoice ID 8 · date 6 · tax head 4. Of the 13 tax errors, 6 are inward (become IMS rejects) and 7 are outward sales (affect output tax) |
| Duplicates | **7** |
| Unmatched | **18** |
| Physical-trail failures | **5 invoices**: 1 paper-only (`MB/0877`), 1 impossible journey (`KN/1502`, 480 km in 3h 02m ≈ 158 km/h), 1 truck trip recycled across 3 invoices (`JP/1187`, `JP/1188`, `JP/1192`) |
| Ring | 5 firms (Zenith Traders, Arka Impex, Nexo Metals, Vrindam Trading, Kairo Enterprises). Nexo Metals sells to **Kaveri Metals** (`06AAHCK3367Q1ZW`), which sells to Arora |
| Kaveri taint score | **0.82** |
| IMS supplier records | **212** → Accept **197** · Reject **11** · Pending **4** |
| Rejects (11) | the 5 physical-trail failures + 6 inward tax-rate/tax-head errors |
| Pending (4) | the 4 Kaveri Metals invoices (ring taint) |
| ITC claimed (as filed) | ₹18.6 L |
| ITC rejected | ₹1.1 L (the 11 rejects) |
| ITC at risk | ₹4.2 L (the 4 Kaveri invoices) |
| Eligible ITC | ₹13.3 L |
| Output tax | ₹25.4 L |
| Net payable | as filed **₹6.8 L** → reconciled **₹12.1 L** |
| Exposure caught | **₹5.3 L** (1.1 + 4.2) |
| Benford, Kaveri Metals | 64 invoices, first-digit MAD **0.051** → nonconforming |

**Hero records** must exist with these IDs and stories, because the UI and script reference them:
- `PP/26/0912` Patel Pipes: clean 4/4 threads
- `LD/2291` Sharma Steel: Ludhiana → Delhi on NH-44, 3/3 tolls (Shambhu, Bastara, Panipat) in 5h 40m
- `MB/0877` Rohilkhand Alloys: e-way bill present, 0 toll crossings in 72 h
- `KN/1502` Ganga Wires: Kanpur → Delhi, impossible journey
- `JP/1187/1188/1192` Pink City Fasteners: one trip on NH-48, three invoices
- `DF/0450` Doaba Fittings: 12 Sep 2026, HSN 7307, charged the abolished 12% slab, expected 18%
- `AR/S/2219`: outward sale to Capital Hardware, Delhi → Delhi, IGST charged, expected CGST + SGST
- `INV-0418` / `INV/418` Patel Pipes: same ₹1,12,000, 4 Sep and 6 Sep, a duplicate
- 4 Kaveri Metals invoices including `KM/26/3341` and `KM/26/3367`, totalling ₹4.2 L ITC

The generator also has a **random mode** (`--scenario random --seed N`) that injects discrepancies at the rates below. Use it to compute precision and recall per discrepancy type.

### Synthetic dataset spec

**Entities** (one SME, one month, plus the upstream network):

| Entity | Volume (approx.) | Key fields |
|---|---|---|
| Counterparties | 120 suppliers/customers + 300 upstream firms | GSTIN, PAN, name, state, registered_on, address, phone, bank_account, status |
| Invoices (sales + purchase) | ~550 | invoice_no, date, supplier/buyer GSTIN, HSN, qty, taxable_value, rate, cgst, sgst, igst, place_of_supply, direction |
| Payments (bank) | ~500 | date, amount, counterparty, narration, UTR |
| Ledger entries | ~1,100 | voucher_no, date, account, debit, credit, reference |
| IMS records | ~210 | supplier-filed copy of each inward invoice + status |
| E-way bills | ~180 | ewb_no, invoice ref, vehicle_no, from/to city, route_id, distance_km, generated_at, valid_until |
| Toll crossings | ~1,500 | vehicle_no, plaza_id, crossed_at |
| Upstream B2B edges | ~2,000 | seller_gstin, buyer_gstin, value, month |
| HSN rate table | ~60 HSNs | hsn, rate, effective_from, effective_to (pre/post 22 Sep 2025) |

**Clean records** use realistic distributions: log-normal amounts, a weekday bias, and payment lags of 0–45 days. Every injected record carries a `truth_label`.

**Data contract (settled in M1; the engines must follow it):**
- **Snapshot:** data is as of **10 Oct 2026, 18:00 IST**. Payments after that date are not in the bank file, so roughly 380 of the month's invoices are paid and ~1,000 vouchers are in the day book. The demo has ~60 e-way bills; the ₹18.6 L ITC total caps how many inward invoices cross ₹50,000.
- **Layout:** `data/sources/` holds the five uploads in their native formats (invoice register CSV, HDFC statement CSV, Tally day book XML, IMS feed JSON, e-way bills + toll crossings JSON). `data/reference/` holds aggregator/officer-side data (counterparties, upstream invoices, HSN rates, routes). `data/truth/` holds truth labels and a manifest; **engines never read `truth/`** and it is not loaded into DuckDB. Raw tables are `raw_*` in DuckDB.
- **Funnel:** each invoice pairs with its books entry (a Purchase/Sales voucher). Payments and IMS records link to the pair afterwards.
- **ITC claimed (as filed)** = ITC on every IMS record, because unactioned records are deemed accepted.
- **Duplicates** are inward double-bookings, not on IMS. They are excluded from the physical-trail checks (the original is checked once).
- **Physical trail** applies to **inter-state** inward goods at or above ₹50,000. Crossings count from `generated_at` to `valid_until` + 48 h (MB/0877's window is 24 h validity + 48 h = 72 h). With a single crossing, speed is a lower bound measured from `generated_at`. Only crossings that move forward along the route count (return trips are ignored).
- **Recycled e-way bill:** invoices that quote the same `ewb_no` (or the same vehicle in overlapping windows) are all flagged.
- **Outward tax errors are over-charges or wrong heads**, so under-reported output tax is ₹0 in the demo and exposure = rejected + at risk.
- **Benford:** Kaveri Metals' 64 invoices (60 to other buyers + 4 to Arora) have MAD 0.0514. Sharma Steel (72) conforms. Nobody else reaches 50 invoices.
- **Name similarity** for stage 3 is `ingest.normalise.name_similarity` (RapidFuzz `token_sort_ratio` after lowercasing and stripping punctuation). The generator uses the same function.

**Discrepancy catalogue** (random-mode injection rates):

| Code | Discrepancy | Rate |
|---|---|---|
| D01 | Amount mismatch (invoice vs payment/ledger) | 2% |
| D02 | Date mismatch beyond tolerance | 1% |
| D03 | Invoice ID typo/reformat (`INV-0418` vs `INV/418`) | 2% |
| D04 | Wrong tax rate (incl. abolished 12% / 28% after 22 Sep 2025) | 1.5% |
| D05 | Wrong tax head (IGST on intra-state or vice versa) | 1% |
| D06 | Tax arithmetic error | 0.5% |
| D07 | Exact duplicate | 0.5% |
| D08 | Near-duplicate (renumbered, shifted date) | 0.8% |
| D09 | Invoice without payment / payment without invoice | 2% |
| D10 | In books, not in IMS (supplier didn't file) | 1.5% |
| D11 | Missing e-way bill on an eligible consignment | 0.5% |
| D12 | Paper-only supply (e-way bill, no toll crossings) | 0.3% |
| D13 | Impossible journey | 0.2% |
| D14 | Recycled e-way bill | 0.3% |
| D15 | Supplier in a circular-trading ring / shell firm | 2 rings of 4–6 firms |
| D16 | Threshold hugging (cluster just under ₹50,000) | 1 supplier |

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, managed with **uv** |
| Storage | **DuckDB** file at `data/halfca.duckdb`, written atomically (temp file + rename). Generated sources stay in their native formats under `data/sources/`. No Postgres needed |
| Data / ML | pandas, RapidFuzz, NetworkX, scikit-learn (Isolation Forest), SciPy |
| LLM | Provider-agnostic adapter in `ai/llm.py` (Anthropic SDK or OpenAI-compatible). Provider/model from env `HALFCA_LLM_PROVIDER` / `HALFCA_LLM_MODEL`. Provider not chosen yet |
| MCP | Official MCP Python SDK (`FastMCP`), stdio transport |
| PDF report | WeasyPrint (HTML → PDF) |
| Frontend | Next.js (App Router) + TypeScript (strict), Tailwind, shadcn/ui, Framer Motion, Recharts; **pnpm**. Built as a **static export** (`output: 'export'`); screens fetch from `/api` on the client |
| Deploy | Docker Compose on the VPS: `api` (FastAPI) + `web` (Caddy serving the static export and proxying `/api`). See `deploy/` and `docs/PLAN.md` |
| Map / graph | Custom SVG components (a stylised projected map and a deterministic ring layout; see the UI spec). MapLibre/deck.gl only as an optional stretch, with bundled data |

---

## Repo layout

```
HalfCA/
├── CLAUDE.md
├── Makefile
├── docs/            PLAN.md (build order + deploy), CONTEXT.md (handoff), EVAL.md (make eval)
├── deploy/          compose.yml, Caddyfile (web container), rsync excludes
├── data/            generated files + halfca.duckdb (gitignored)
├── backend/
│   ├── pyproject.toml
│   ├── halfca/
│   │   ├── config.py            env, paths, thresholds (single source of constants)
│   │   ├── store.py             DuckDB access
│   │   ├── models.py            Pydantic domain models + Evidence
│   │   ├── data/                generator: entities, routes, scenario_demo, scenario_random, inject
│   │   ├── ingest/              csv_loader, llm_extract, normalise, gstin
│   │   ├── engines/             common (Flag + evidence), matching, tax, dupes_gaps, physical, taint, anomaly, liability
│   │   ├── ai/                  llm (client + cache), adjudicate (stage 4), ims_autopilot, copilot, prompts/
│   │   ├── pipeline.py          runs every engine over raw_* tables → res_* tables + summary
│   │   ├── fmt.py               ₹ / lakh / duration text for evidence and reasons
│   │   ├── tools.py             the 7 tool functions (shared by copilot + MCP)
│   │   ├── mcp_server.py
│   │   ├── report/              pdf.py + templates/
│   │   └── api/                 main.py, routers/
│   └── tests/
└── frontend/
    ├── app/(app)/{upload,matching,overview,discrepancies,goods,credit,ims,liability,copilot}/page.tsx
    ├── components/          shell, kpi, donut, funnel, flip-card, route-map, ring-graph, waterfall, benford, chat
    └── lib/                 api.ts (typed client), tokens.ts, format.ts (₹ lakh / Indian grouping)
```

---

## Commands

Prerequisites (EndeavourOS / Arch):
```bash
sudo pacman -S --needed python uv nodejs npm pnpm pango   # pango is needed by WeasyPrint
```

| Command | Does |
|---|---|
| `make setup` | `uv sync` in backend + `pnpm install` in frontend |
| `make data` | Generate the demo scenario (seed 2609) into `data/` and load DuckDB |
| `make data-random SEED=7` | Generate a random-mode dataset for evaluation |
| `make api` | `uv run uvicorn halfca.api.main:app --reload --port 8000` |
| `make web` | `pnpm dev` (port 3000, proxies `/api` → 8000) |
| `make dev` | api + web together |
| `make mcp` | Run the MCP server on stdio |
| `make test` | `uv run pytest -q` (backend) + `pnpm typecheck && pnpm lint` (frontend) |
| `make eval` | Precision/recall per discrepancy type on random mode |
| `make report` | Write `data/audit-report-2026-09.pdf` |
| `make build` | Static frontend export into `frontend/out` |
| `make deploy` | `make build`, rsync to the VPS, `docker compose up -d --build` there, then a health check |
| `make deploy-domain` | One-time: route `halfca.akshatchowdhary.online` through the VPS's shared Caddy (needs the DNS A record first) |
| `make deploy-logs` | Tail the VPS containers' logs |
| `make deploy-reset` | Regenerate the demo data on the VPS |

Env (`backend/.env`, never committed): `HALFCA_LLM_PROVIDER`, `HALFCA_LLM_MODEL`, `HALFCA_LLM_API_KEY` (all optional; no LLM means templated fallbacks). On the VPS the same keys go in `/root/halfca/.env`.

---

## Engine specs

All thresholds live in `config.py`.

**Shared output (built in M2):** every engine emits `Flag`s (`engines/common.py`): `kind`, `category` (discrepancy · duplicate · unmatched · gap · physical · credit · anomaly · review), the record, counterparty, `recorded`, `expected`, ₹ `impact` and an `evidence` object `{summary, recorded, expected, chain: [{source, id, label, fields}], notes}`. `pipeline.reconcile()` runs the engines in order (duplicates → matching → payment/IMS links → diffs → tax → gaps → physical → taint → anomalies → IMS → liability) and returns the `res_*` tables. Invoice status precedence: unmatched → duplicate → discrepant → matched (physical failures stay inside matched). `make data` stores raw + results atomically; the container rebuilds the demo when the code fingerprint in `meta.code` changes.

### Ingestion
- **CSV/JSON loader:** the primary path, and what the demo uses.
- **LLM extraction:** for PDFs/images. Send the file as a document/image content block and ask for a JSON schema of invoice fields. Validate with Pydantic. Retry once on schema failure. On failure, mark the record `needs_review`. Never invent values.
- **GSTIN validation:** 15 characters. `[0:2]` is the state code, `[2:12]` the PAN, `[12]` the entity number, `[13]` is `Z`, `[14]` the checksum. Checksum: base-36 values; alternate weights 1/2; sum `p//36 + p%36`; check = `(36 - sum%36) % 36`.
- **Invoice-number normalisation:** uppercase; strip separators `-/_ .`; strip leading zeros of the numeric tail; strip FY suffixes like `/26-27`.

### Matching cascade (invoices are the anchor; link payment, ledger, IMS)
1. **Exact:** (GSTIN, invoice_no) equal.
2. **Normalised:** normalised invoice_no equal, and amount within ±₹1.
3. **Fuzzy:** amount within ±2%, date within ±7 days, counterparty name similarity ≥ 85 (RapidFuzz `token_sort_ratio`). Pick the best unique candidate.
4. **AI adjudication:** for each remaining record, give the LLM the top-3 rule-ranked candidates. It may only pick one of them or "none". Without an LLM, skip this stage (the funnel shows it as skipped; tests inject a deterministic stub).

Output: match groups with `stage` and `confidence`. Unmatched records go to the queue, sorted by ₹ impact.

### Field diffs, duplicates, gaps
- **Diffs on matched groups:**
  - amount (> ₹1 off)
  - date (> 3 days apart)
  - invoice ID (normalised equal but raw string differs)
  - tax rate
  - tax head
- **Exact duplicate:** same GSTIN + invoice_no + amount (no date window: the same bill keyed twice).
- **Near-duplicate:** same supplier, same amount, invoice_no edit distance ≤ 2, dates ≤ 5 days apart.
- **Gaps:**
  - invoice without payment (aged)
  - payment without invoice
  - in books but not in IMS (supplier didn't file)
  - in IMS but not in books

### Tax verifier
- **Rate:** rate = `hsn_rates` lookup by HSN **and supply date** (effective_from / effective_to; GST 2.0 slabs 0/5/18/40 from 22 Sep 2025, so 12% and 28% are invalid after that date).
- **Tax head:** supplier state == recipient state → CGST + SGST split equally, otherwise IGST.
- **Arithmetic:** recompute the tax and compare, with ±₹1 tolerance.
- Flag invoices within 30 days of 22 Sep 2025 as `transition_review`. Flag them for review; never auto-decide.

### Physical trail (inter-state inward goods invoices ≥ ₹50,000; see the data contract)
1. E-way bill exists? If not → `missing_ewb`.
2. Vehicle has toll crossings on the declared route within the e-way bill validity? If none → `paper_only`.
3. Average speed (route km ÷ elapsed time between first and last crossing, extrapolated to origin/destination) ≤ 80 km/h? If not → `impossible_journey`.
4. Same vehicle + same trip window attached to more than one invoice / e-way bill → `recycled_ewb` (flag **every** invoice sharing the trip).

Routes and toll plazas live in `data/routes.json`: city coordinates, plaza names, km markers. Shared by the generator, the engine and the map.

### ITC taint graph (NetworkX DiGraph of GSTINs, edge = seller → buyer)
- **Cycles:** `simple_cycles` bounded to length ≤ 6; keep a cycle when at least one of its nodes is within 3 hops upstream of the user.
- **Own risk:** ring membership 0.91. Otherwise sum and cap at 1.0:
  - registration < 90 days: +0.3
  - goods trade with zero e-way bills: +0.3
  - turnover > 3× trailing average: +0.2
  - shared PAN / bank / phone / address with another GSTIN: +0.2
  - return-filing gaps: +0.2
- **Propagation:** `r(v) = max(own(v), 0.9 × max over sellers u of r(u))`, iterated to a fixed point. This gives Kaveri = 0.91 × 0.9 = **0.82**.
- Supplier with r ≥ 0.7 → its invoices are **at risk** → IMS **Pending**.

### Anomaly
- Isolation Forest per invoice. Features: amount z-score per supplier, weekday, invoice-number gap, roundness, days-to-payment, rate mix.
- **Benford:** first-digit MAD per supplier with ≥ 50 invoices; threshold 0.015.
- **Threshold hugging:** a supplier with ≥ 30% of invoices between ₹45,000 and ₹49,999.

### IMS Autopilot (deterministic decision, LLM only writes the reason)
- not matched → **Pending**
- tax/amount wrong → **Reject**
- physical trail failed → **Reject**
- supplier taint ≥ 0.7 → **Pending**
- otherwise → **Accept**

### Liability
- `net = output_tax − eligible_itc`, by IGST/CGST/SGST, shown as as-filed vs reconciled.
- `eligible_itc = claimed − rejected − at_risk`.
- `exposure = rejected + at_risk + under-reported output tax`.

---

## API (FastAPI, prefix `/api`, all JSON unless noted)

| Method | Path | Returns |
|---|---|---|
| GET | `/dataset` | current dataset: scenario, period, source files and record counts |
| POST | `/upload` | multipart files (a dropped folder, loose files or a zip) → a **job** to poll; sources not sent are kept from the current dataset |
| POST | `/upload/demo` | the "Use demo dataset" button: the demo's own files through the real ingestion path → job |
| POST | `/reset` | regenerate the demo month (seed 2609) → job |
| POST | `/reconcile?period=2026-09` | re-runs all engines on the stored dataset → job |
| GET | `/jobs/{id}` | job progress: five steps (extract · gstin · normalise · road · match) with real details, files found, KPIs when done |
| GET | `/invoices/{key}` | one invoice's four threads (books, bank, IMS, road) + flags; `key` = invoice_id or invoice number (slashes allowed) |
| GET | `/demo-pack.zip` | the demo month as a folder: 5 sources + invoice PDFs + README |
| GET | `/summary` | KPI counts, donut data, discrepancy-type counts |
| GET | `/funnel` | per-stage in / paired / left |
| GET | `/discrepancies?type=` | list with `evidence` |
| GET | `/goods` | routes + per-invoice verdicts (for the map) |
| GET | `/goods/{key}` | e-way bill, crossings, verdict, evidence |
| GET | `/credit/graph?scope=focus\|full` | nodes, edges, cycles, taint scores (focus = you, at-risk suppliers + chain, showcase suppliers, rings) |
| GET | `/credit/supplier/{gstin}` | taint score, signals, invoices, ITC at risk |
| GET | `/ims` | records + recommendation + reason |
| POST | `/ims/approve` | bulk-approve accepts |
| GET | `/liability` | waterfall + net payable + by tax head |
| GET | `/benford/{gstin}` | observed vs expected + MAD |
| POST | `/copilot` | **SSE stream**: tool-call events, then answer tokens, then evidence links |
| GET | `/copilot` | the copilot's tools, model (or none) and suggested questions |
| GET | `/report.pdf` | audit report |

Keep the Pydantic response models in `models.py` and mirror them in `frontend/lib/api.ts`.

## MCP tools (`tools.py`, also used by the in-app copilot)

`reconcile_period(gstin, month)` · `list_discrepancies(type?, min_amount?)` · `trace_goods(invoice_id)` · `supplier_risk(gstin)` · `ims_recommendations(month)` · `estimate_liability(month, scenario)` · `explain(flag_id)`

Every tool returns JSON with an `evidence` array. The copilot is a tool-use loop over these same functions, capped at 4 tool calls per answer.

---

## Frontend

- **The UI spec below is the design.** Build the 9 screens exactly as described, fed by API data.
- **Two themes**, toggled from the top bar, defaulting to the OS preference. Tokens are CSS variables in `app/globals.css`, mirrored in `lib/tokens.ts`:

  | Token | Light (peach) | Dark (pure black) |
  |---|---|---|
  | bg | `#FFF0E1` | `#000000` |
  | panel | `#FFF8F0` | `#0D0D0D` |
  | peach (soft fill) | `#FFDCC2` | `#1A1411` |
  | line | `#EBCFB8` | `#2A2420` |
  | ink (text, outlines) | `#1C130C` | `#FFF4EA` |
  | muted | `#7B6352` | `#A8978A` |
  | orange (brand) | `#F26B1D` | `#FF8A3D` |
  | pale orange | `#FFC59A` | `#3A2212` |
  | green | `#16A34A` | `#22C55E` |
  | amber (status, golden so it never reads as brand orange) | `#C98A00` | `#FBBF24` |
  | violet | `#7C3AED` | `#A78BFA` |
  | slate | `#64748B` | `#94A3B8` |
  | red | `#DC2626` | `#F87171` |

- **Fonts:**
  - Anton for the big display moments: page H1s, KPI numbers, hero callouts (uppercase, tight)
  - Space Grotesk for card titles and section headings
  - Inter for body text
  - JetBrains Mono for GSTINs, invoice numbers and amounts

  Self-host the fonts with `next/font`.
- **Money:** format in Indian grouping (`₹2,12,400`) and lakh (`₹4.2 L`). Use `lib/format.ts` only; never hand-format.
- The ★ screens (Goods, Credit) are the differentiators. Polish them first.
- Every screen needs loading, empty and error states. Animations must not block reading: hold key numbers ≥ 1.5 s.

---

## UI spec (the design: build this)

**Look and feel:**
- Friendly and a little playful, inspired by comic-book landing pages: big condensed headlines, chunky outlined "sticker" cards, pill buttons, halftone-dot textures. Serious numbers, light-hearted wrapping. Not a generic admin template.
- Cards: `panel` fill, 18px radius. In light mode a 2px `ink` outline with a 4px offset `ink` shadow; in dark mode a 1.5px `line` outline with a soft offset shadow. Buttons press down (shadow shrinks) on click.
- Orange is the one brand accent. Use it for the active nav, primary buttons, and the ★ features. Every "orange" in the screen specs below means the brand orange token.
- Status colours: green = matched / accept / verified, amber = discrepancy / pending / at risk, violet = duplicate, slate = unmatched, red = fraud / reject / ring.
- Microcopy can wink ("Nothing fishy here. Yet.") but numbers, evidence and table text stay plain.
- Numbers count up when they appear.
- Cards fade or slide in with a stagger (300–500 ms each), with a slight spring.
- Use mono font for every GSTIN, invoice number and amount column.

**Logo:** a "half" badge.
- A circle split across the middle: top half orange, bottom half ink. "CA" in Anton sits across the split, so each letter is half inverted (ink on the orange half, orange on the ink half). Badge colours are fixed in both themes; only the outline follows `ink`.
- Wordmark "HALF CA" in Anton next to it, with "follows the goods" in small muted text underneath.
- Build it as an inline SVG component; the badge can do a half-turn wiggle on hover.
- The toll barrier survives as the icon for the **Road** thread.

**Shell (every screen):**
- **Left sidebar (248px):**
  - logo at the top
  - nav group "Reconcile · Sep 2026" with items A–I, each with a small letter badge (the badge turns orange when active).
  - a theme toggle (sun / moon) at the bottom Upload, Matching, Overview, Discrepancies, **Follow the Goods ★**, **Follow the Credit ★**, IMS Autopilot, Liability, Copilot.
- **Top bar (64px):**
  - avatar tile "AH", **Arora Hardware Distributors**, and the GSTIN in mono with "New Delhi"
  - chip "Period · Sep 2026"
  - right side: an amber chip "GSTR-2B in 3d 04h" with a live countdown, and a chip "Synthetic data"
- **Page header:** H1 (Anton, uppercase, 40px) plus a muted one-line subtitle. Right-side chips where noted.

**A · Upload**
- Dashed drop zone with two columns.
- **Left column:** five file rows slide in one by one. Each row has an icon tile, a filename, a muted detail line and a type chip:

  | File | Detail | Chip |
  |---|---|---|
  | `invoices_sep26.zip` | 552 invoices · PDF + CSV | Invoices |
  | `hdfc_current_sep26.csv` | 498 bank transactions | Payments |
  | `tally_daybook_sep26.xml` | 1,104 ledger vouchers | Ledger |
  | `ims_feed_2026-09.json` | 212 supplier records | IMS |
  | `eway_bills_sep26.json` | 181 e-way bills + toll crossings | Road (orange) |

- Record counts in the file rows come from `GET /api/dataset`; the numbers in the table above are illustrative.
- **Right column:** a step list. Each step shows a spinner while running, then a green tick:
  1. Extracting 552 invoices with vision AI
  2. Validating 120 GSTINs (state · PAN · check digit)
  3. Normalising invoice numbers
  4. Linking e-way bills to toll crossings
  5. Matching across four threads
- Then a orange "View results →" button.
- Drives the real `/upload` + `/reconcile` calls. Preload the demo files with one click ("Use demo dataset").

**B · Matching**
- Subtitle: "Cheapest rules first. AI only sees the hardest cases."
- Four funnel rows. Each row has: label + method on the left, a horizontal bar whose width is proportional to records in (bar text "552 in"), and "**491** paired · 61 left" on the right.
- Bars animate in sequence. The AI stage bar is dark gold with a twinkling ✦.
- Below: "Unmatched queue **18** records with no partner, sorted by ₹ impact".

**C · Overview**
- **Row of 6 KPI tiles:** Reconciled 552, Matched 489 (green), Discrepancies 38 (amber), Duplicates 7 (violet), Unmatched 18, and **Exposure caught ₹5.3 L** (orange gradient tile).
- **Then three cards:**
  1. A donut (matched / discrepant / duplicate / unmatched) with "88.6% clean match" in the centre, plus a legend.
  2. "Discrepancies by type": horizontal bars for Amount 11, Tax rate 9, Invoice ID 8, Date 6, Tax head 4, Duplicates 7.
  3. **"Four threads · two invoices"**: two stacked thread cards.
     - `PP/26/0912 · Patel Pipes`, chip **4/4** green. Rows Invoice ✓, Payment ✓, Ledger ✓, **Road** ✓ (the Road label is orange), each with a right-aligned detail.
     - `MB/0877 · Rohilkhand Alloys`, chip **3/4** red. Road ✕ "0 toll crossings in 72 h".
     - Rows light up one by one. This card visually explains the 4th thread.

**D · Discrepancies**
- Header chips show counts per type.
- **Three hero flip-cards** (they start on a striped back with the logo and flip to the front in sequence):
  1. **Tax rate**, "Abolished slab still charged": `DF/0450`, Doaba Fittings, 12 Sep 2026, HSN 7307. Diff box: Recorded "12% · ₹7,020" (red row) vs Expected "18% · ₹10,530" (green row). Note: "The 12% slab was abolished by GST 2.0 on 22 Sep 2025. Rate checked against the date of supply."
  2. **Tax head**, "IGST on an intra-state sale": `AR/S/2219`, sale to Capital Hardware, Delhi → Delhi. Recorded "IGST 18% · ₹21,600" vs Expected "CGST + SGST 9% + 9%".
  3. **Duplicate**, "Same invoice, renumbered": Patel Pipes, `INV-0418` (04 Sep) and `INV/418` (06 Sep), both ₹1,12,000. Note: "Same supplier, same amount, invoice number edit distance 2 (identical once normalised), two days apart."
- **Below:** an "All flags" table (Record · Counterparty · Type chip · Recorded (red mono) · Expected (green mono) · ₹ impact) with a type filter. Rows animate in.

**E · Follow the Goods ★** (the money shot)
- Header chip: "★ Only on Half CA".
- Two columns: a large map card and a 360px column of invoice cards.
- **Map:** an SVG with viewBox `0 0 860 600`.
  - Theme-aware "road atlas" look: a dotted grid background with a softly lit landmass blob (peach paper in light mode, near-black in dark mode), faint dashed state lines and spaced-out uppercase state labels (PUNJAB, HARYANA, RAJASTHAN, UTTAR PRADESH).
  - Roads are wide dark strokes with a dashed centre line.
  - Cities are dots with labels; Ludhiana, Delhi, Moradabad, Jaipur and Kanpur get orange dots.
- **Routes** (store them in `routes.json`; these projected coordinates work well):

  | Route | SVG path | Toll plazas (fraction along path) |
  |---|---|---|
  | r1 Ludhiana → Delhi, NH-44 | `M180 95 C228 118 255 140 275 160 S310 205 318 222 S330 245 338 258 S362 302 370 320` | Shambhu .32, Bastara .62, Panipat .84 |
  | r2 Moradabad → Delhi | `M540 250 C480 262 430 298 370 320` | TP-UP-118 .35, TP-UP-121 .72 |
  | r3 Kanpur → Delhi | `M720 510 C630 505 545 478 470 450 S398 362 370 320` | TP-UP-204 .28, TP-UP-188 .55, TP-UP-160 .82 |
  | r4 Jaipur → Delhi, NH-48 | `M215 470 C255 420 295 385 320 362 S352 333 370 320` | Shahjahanpur .35, Kherki Daula .68 |

  City coordinates: Ludhiana (180,95), Delhi (370,320), Moradabad (540,250), Jaipur (215,470), Kanpur (720,510), Lucknow (770,420).
- **Four beats** play automatically on entering (about 6 s apart). Clicking an invoice card replays its beat. The active card gets a orange outline, and a verdict chip appears on the card when its beat ends.
  1. **`LD/2291`** Sharma Steel, ₹4,86,000, EWB `3812 4471 0093`, vehicle `PB10 GK 7731`.
     - A orange truck (inline SVG, rotates along the path) drives r1.
     - A glowing orange trail draws behind it.
     - Each toll pin turns **green** with a glow as the truck passes.
     - Badge "✓ Goods verified · 3/3 tolls".
  2. **`MB/0877`** Rohilkhand Alloys, ₹1,18,000, EWB `3812 9902 1166`, vehicle `UP21 T 4410`.
     - The r2 trail is a faint red dashed line.
     - Grey "ghost" trucks flicker at both ends.
     - No pins light up.
     - Badge "✕ Paper-only supply · 0 tolls".
  3. **`KN/1502`** Ganga Wires, ₹1,41,600, EWB `3813 0045 7720`, vehicle `UP78 HT 2291`.
     - The truck races r3 in about 1.5 s with a red trail; pins turn **red**.
     - A stopwatch panel in the top-right counts up: "3h 02m · 480 km · 158 km/h (limit 80)".
     - Badge "✕ Impossible journey".
  4. **`JP/1187` +2** Pink City Fasteners, ₹59,000 ×3, EWB `3812 6630 5518`, vehicle `RJ14 GD 6620`.
     - One truck drives r4.
     - Three invoice tags (`JP/1187`, `JP/1188`, `JP/1192`) stack on top of it one by one.
     - Badge "✕ Recycled e-way bill · 1 trip, 3 invoices".
- Verdict badges show in a fixed top-left slot of the map card.
- **End:** a red summary card under the invoice list reads "5 invoices passed every paper check. They failed the road."
- A small legend sits bottom-left: truck trail / toll crossed / no crossing.

**F · Follow the Credit ★**
- Two columns: a graph card and a 340px supplier risk card.
- **Graph:** an SVG with viewBox `0 0 860 600`, grid background, deterministic layout.

  | Node | Position | Size | Style |
  |---|---|---|---|
  | Arora Hardware ("YOU") | (720,300) | r 38 | ink fill, orange stroke, pulsing ring |
  | Kaveri Metals | (520,220) | r 26 | amber |
  | Patel Pipes | (540,390) | | green |
  | Singh Fittings | (620,480) | | green |
  | Mehta Tubes | (590,110) | | green |
  | Bharat Tubes → Patel Pipes | (390,470) | | upstream green |
  | Ostwal Steel → Patel Pipes | (430,555) | | upstream green |
  | Northline Alloys → Mehta Tubes | (440,60) | | upstream green |
  | Ring | circle centred (240,200), radius 110, angles −90° + i·72° | | red |

  Ring order: Zenith Traders → Arka Impex → Nexo Metals → Vrindam Trading → Kairo Enterprises → back to Zenith.
- **Sequence on enter:**
  1. Only "you" and the direct suppliers, with grey edges.
  2. An animated click on Kaveri; the risk card slides in.
  3. Upstream nodes fade in. Ring nodes appear scattered, then **snap into a circle**.
  4. Curved, dashed red ring edges with arrowheads "march" (animated dash offset). A red edge runs Nexo Metals → Kaveri.
  5. Red badges pop: "Registered 41 days ago" (Zenith), "Zero e-way bills" (Nexo), "Turnover +900%" (Kairo).
  6. Red particles flow continuously Nexo → Kaveri → you.
  7. A callout bottom-left counts up: "YOUR ITC AT RISK **₹4.2 lakh** · 4 invoices from Kaveri Metals · kept **Pending**".
- **Risk card:**
  - Kaveri Metals, GSTIN mono, "Haryana"
  - taint score meter filling to **0.82** (amber → red gradient)
  - "2 hops downstream of a 5-firm ring"
  - "Ring signals" list with red "!" bullets
  - "Action": keep the 4 invoices **Pending** and request transport proof

**G · IMS Autopilot**
- Header right: an amber chip "GSTR-2B generates in 3 days · 14 Oct" and a orange button "Approve 197 accepts".
- KPI row: Supplier records 212, Accept 197 (green), Reject 11 (red), Pending 4 (amber).
- Table columns: Supplier · Invoice · Date · Taxable · ITC · Autopilot (pill: Accept green / Reject red / Pending amber) · Reason (muted, one line).
- Show the hero rows first, e.g.:
  - Rohilkhand Alloys `MB/0877`: Reject, "Goods not evidenced: 0 toll crossings"
  - Kaveri Metals `KM/26/3341`: Pending, "Supplier fed by a circular-trading ring (taint 0.82)"
  - Ganga Wires `KN/1502`: Reject, "Impossible journey: 480 km in 3h 02m"
  - Doaba Fittings `DF/0450`: Reject, "Charged abolished 12% slab · expected 18%"
  - Pink City Fasteners `JP/1188`: Reject, "Recycled e-way bill (trip used by JP/1187)"
- **Approve:** turns Accept pills solid green "✓ Approved" in a ripple and shows the toast "197 accepted on IMS · 11 rejected · 4 kept pending".

**H · Liability**
- Two cards.
- **Left card:**
  - "Input tax credit · ₹ lakh" waterfall: Claimed 18.6 (slate) → Rejected −1.1 (red, floating) → At risk −4.2 (amber, floating) → Eligible 13.3 (green). Bars grow up in sequence, with value labels on top.
  - Below: "Benford screen · Kaveri Metals · 64 invoices". Amber bars for observed first digits 1–9, a dashed white line with dots for the Benford expected curve, and the caption "First-digit MAD **0.051** · nonconforming (threshold 0.015)".
- **Right card:**
  - "Net payable · ₹ lakh": two horizontal bars, As filed 6.8 (slate) and Reconciled 12.1 (orange).
  - Formula in mono: "Output tax ₹25.4 L − eligible ITC ₹13.3 L = ₹12.1 L".
  - A orange-gradient callout "EXPOSURE CAUGHT BEFORE FILING **₹5.3 lakh**".
  - A "By tax head" table (IGST / CGST / SGST / Total: output, ITC, net).
  - A "Download audit report (PDF)" button.

**I · Copilot**
- Header chip "📡 MCP server · 7 tools".
- **Left 260px card:** "Try asking" suggestion buttons:
  - Why did my liability go up?
  - Which invoices failed the road check?
  - Is Kaveri Metals safe to buy from?

  Under them, a mono list of the 7 MCP tool names.
- **Chat card:**
  - User bubbles: orange, right-aligned.
  - Each answer shows a **tool-trace block** first: mono lines like `→ estimate_liability(month='2026-09')` with a left border in light blue, appearing one by one as the SSE events arrive.
  - Then the answer streams word by word in a panel bubble.
  - Then evidence chips ("5 road failures →", "Kaveri ring →", "IMS actions →", "Liability →") that navigate to the relevant screen.
  - Composer input + orange Send button.

**Responsive:** designed for 1920×1080 and 1440×900 screen recording. It must not break at 1280px wide (KPI grids wrap to 3 columns).

---

## Testing

- `tests/test_demo_numbers.py`: generate seed 2609, run the pipeline, assert **every** number in the demo table above.
- One test file per engine, built from small hand-made fixtures (one per discrepancy type, including the hero records).
- `tests/test_gstin.py`:
  - checksum validates `07AAKFA4821M1ZA` and `06AAHCK3367Q1ZW`
  - checksum rejects a corrupted one
- `tests/test_no_key.py`: the full pipeline and copilot fallback work with `ANTHROPIC_API_KEY` unset.
- **Evaluation:** `make eval` prints precision/recall per D01–D16 on random mode. Report these numbers as measured on synthetic data, never as real-world claims.

## Conventions

- **Python:**
  - ruff + ruff format
  - type hints everywhere
  - pure functions in `engines/` (DataFrames in, results out, no I/O)
  - constants only in `config.py`
- **TypeScript:**
  - strict mode
  - no `any`
  - server components by default
  - client components only for animation and interaction
- **Commits:** one per milestone or meaningful step, imperative mood.
- **Don't:**
  - add auth
  - add Postgres, or make Docker a requirement for local dev (it is for deploy only)
  - call external APIs other than the configured LLM provider
  - fetch map tiles
  - let the LLM touch arithmetic
  - edit the expected demo numbers

## Definition of done

- `make setup && make data && make dev` works on a clean machine with no API key.
- `make test` is green, including `test_demo_numbers`.
- All 9 screens render real API data and match the UI spec.
- The copilot answers "Why did my liability go up?" with tool calls and evidence links, both with and without a key.
- The MCP server lists 7 tools, and `supplier_risk` works from an MCP client.
- `make report` produces the audit PDF.
- ~~`docs/RUNBOOK.md` demo-day checklist~~: dropped by the user (2026-10-03).
