# Half CA: handoff context for an AI agent

Read this before doing anything. It is the working memory of the project: where things are,
how they run, what is decided, and what bites. `CLAUDE.md` is the product spec (what to
build); `docs/PLAN.md` is the build order. This file is how to operate.

Last updated: 2026-10-03, after M5.

---

## 1. Status in one screen

| Milestone | State | Notes |
|---|---|---|
| M0 foundations + deploy | ✅ | Live at https://halfca.akshatchowdhary.online |
| M1 synthetic data | ✅ | Demo (seed 2609) + random mode, truth labels, DuckDB loader |
| M2 engines | ✅ | Every demo-table number found by the engines; Groq stage-4 wired |
| M3 API + upload | ✅ | All endpoints, real folder upload with progress jobs, reset, demo pack with invoice PDFs |
| M4 screens | ✅ | All 9 screens on live API data, both themes, 1280–1920 px |
| M5 AI layer | ✅ | 7 tools, copilot SSE (Groq tool loop + number guard, templates without a key), MCP server, invoice PDFs read by AI and checked against the register |
| **M6 ship** | **next** | PDF audit report (`GET /api/report.pdf`, `make report`, enable the Liability button), `make eval`, RUNBOOK, final deploy |

Health right now: `make test` green (134 backend tests + frontend typecheck/lint).
All 9 screens render real data; the copilot answers with and without a key. The audit-report
button on Liability is disabled until M6.

## 2. Working with this user

- The user owns the project and the VPS. The repo has no git remote yet. Communicate in plain, simple words; they often ask for summaries "in simple words".
- **Ask with AskUserQuestion when something is genuinely ambiguous** (they asked for this). Decide obvious things yourself and say so.
- After each milestone: run `make test`, run the app, commit, **deploy**, and report. They expect deploys.
- Commits: one per milestone or meaningful step, imperative mood, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Git identity is set repo-locally (Akshat Chowdhary / akshatchowdhary03@gmail.com).
- **Never ask the user to paste secrets in chat.** They put keys in `backend/.env` themselves. Never print secret values (use `sed -E 's/=.*/=<set>/'` to show which keys exist).
- Never change the expected demo numbers to make a test pass (golden rule 3 in CLAUDE.md).

## 3. Local machine

- Arch-based Linux (EndeavourOS). Repo: `/home/gingersnaps/HalfCA`. Not on any remote.
- Toolchain: Python 3.12 via **uv**; Node 26; **pnpm** installed with `npm i -g` into `~/.npm-global` and symlinked into `~/.local/bin`; Docker (legacy builder locally, so no `COPY --chmod`); `google-chrome-stable` for headless screenshots.
- Dev: `make api` (FastAPI :8000, reload), `make web` (Next dev :3000, proxies `/api` → :8000), `make dev` (both).
- Screenshots (useful to check UI work):
  ```bash
  google-chrome-stable --headless=new --disable-gpu --hide-scrollbars --window-size=1440,900 \
    --virtual-time-budget=6000 --blink-settings=preferredColorScheme=1 \
    --screenshot=/path/out.png http://localhost:3000/overview/
  # preferredColorScheme=1 light, =0 dark. For the live site add:
  #   --host-resolver-rules="MAP halfca.akshatchowdhary.online <server-ip>"
  ```
- Screenshots of animated screens: Chrome's `--virtual-time-budget` does **not** run the motion animations (elements stay at opacity 0). Drive the real Chrome with `puppeteer-core` from a scratch dir (`npm i puppeteer-core`, `executablePath: "/usr/bin/google-chrome-stable"`, `page.emulateMediaFeatures([{name: "prefers-color-scheme", value: "dark"}])`), wait real time, and click buttons by text to test flows (e.g. "Use demo dataset", "Approve 197 accepts").
- Gotchas:
  - `pkill -f "<pattern>"` can match and kill **your own shell** if the command line contains the pattern. Free a port with `fuser -k 8000/tcp` instead.
  - The laptop's `curl` cannot do HTTPS (certificate store issue). Use Python (`uv run python -c "import httpx; ..."`) or run the check on the VPS over ssh.
  - The laptop's DNS resolver may cache old answers; check DNS from the VPS (`ssh $VPS getent hosts <name>` or `dig @1.1.1.1`).

## 4. Repo map (what lives where)

```
CLAUDE.md                spec + decisions (imports this file)
docs/PLAN.md             milestones, deploy design, open items
docs/CONTEXT.md          this file
Makefile                 every command (make help)
backend/
  halfca/config.py       ALL thresholds/constants + env (.env loader)
  halfca/data/           generator: scenario_demo, scenario_random, plans, network, derive, write, build (CLI), routes.json, hsn
  halfca/ingest/         gstin (checksum), normalise (invoice no + name_similarity), csv_loader (5 source formats)
  halfca/engines/        common (Flag/evidence), matching, dupes_gaps, tax, physical, taint, anomaly, liability
  halfca/ai/             llm (OpenAI-compatible client, tool calls, disk cache), adjudicate (stage 4),
                         ims_autopilot, copilot (tool loop + templates + number guard), warm (cache warm-up)
  halfca/tools.py        the 7 tools (copilot + MCP share them)
  halfca/mcp_server.py   MCP server on stdio (MCP SDK v2 `MCPServer`)
  halfca/ingest/         + llm_extract (PDF text → schema → verified fields), documents (read + add to register)
  halfca/engines/        + documents (invoice PDF vs register → `document` discrepancies)
  halfca/pipeline.py     runs all engines: raw_* frames → res_* tables + summary
  halfca/store.py        DuckDB: atomic save (temp file + rename), load_prefixed, meta
  halfca/api/            main.py (/api/health), routers/dataset.py (/api/dataset)
  halfca/models.py       Pydantic API models (mirror in frontend/lib/api.ts)
  tests/                 conftest (blanks LLM, stub adjudicator, demo fixtures), factories, one file per engine, test_demo_numbers
  Dockerfile, entrypoint.sh (rebuilds demo data if missing or built by older code)
frontend/                Next.js 16 static export; read node_modules/next/dist/docs before Next-specific code
  app/globals.css        theme tokens (light peach / dark pure black), utilities: card, halftone, btn-press
  app/(app)/*/page.tsx   the 9 screens (placeholders until M4)
  components/shell/      logo (half badge), sidebar, topbar (GSTR-2B countdown), theme-toggle, page-header
  lib/                   format.ts (₹/lakh, only place to format), tokens.ts, nav.ts, clock.ts, company.ts
deploy/                  compose.yml, caddy/Caddyfile (web container), rsync-exclude, route-domain.sh
data/                    generated (gitignored): sources/, reference/, truth/, halfca.duckdb, llm_cache.json
```

## 5. Data and engines, quick reference

- `make data` regenerates the demo (seed 2609, Sep 2026, as of 10 Oct 2026 18:00 IST), runs the pipeline, writes `data/halfca.duckdb` with `raw_*` (sources + reference) and `res_*` (results). ~4 s; Groq is called only for stage 4 and cached.
- `make data-random SEED=n` → `data/random-n/` for evaluation (truth labels D01–D16).
- Demo truth (must hold): 552 invoices; funnel 552→61→23→20→18 (491/38/3/2); 489 matched / 38 discrepancies (amount 11, rate 9, ID 8, date 6, head 4) / 7 duplicates / 18 unmatched; 5 road failures inside matched (MB/0877 paper-only, KN/1502 158 km/h, JP/1187-1188-1192 recycled); ring Zenith→Arka→Nexo→Vrindam→Kairo; Kaveri taint 0.82; IMS 197/11/4; ITC 18.6 → rejected 1.1, at risk 4.2, eligible 13.3; output 25.4; net 6.8 → 12.1; exposure 5.3; Benford Kaveri 64 invoices, MAD 0.051.
- Without an LLM, stage 4 is skipped → 20 unmatched (IMS and liability unchanged).
- The "data contract" section of CLAUDE.md lists the rules engines and generator share (toll window = generation → validity + 48 h, physical trail only for inter-state ≥ ₹50k, ITC claimed = all IMS records, etc.).
- Results tables: `res_invoices` (status per invoice), `res_matches`, `res_funnel`, `res_unmatched`, `res_flags` (all findings with evidence JSON), `res_payment_links`, `res_ims_links`, `res_physical`, `res_taint_nodes`, `res_taint_edges`, `res_cycles`, `res_benford`, `res_outliers`, `res_tax_expected`, `res_ims`, `res_liability_heads`, `res_liability_waterfall`, `res_summary` (key → JSON).
- Tests: `make test` (or `cd backend && uv run pytest -q`). Tests never call a model.

## 6. LLM (Groq)

- Provider `groq`, model `openai/gpt-oss-120b` (OpenAI-compatible API at `https://api.groq.com/openai/v1`). Env: `HALFCA_LLM_PROVIDER`, `HALFCA_LLM_API_KEY`, optional `HALFCA_LLM_MODEL`, `HALFCA_LLM_BASE_URL`.
- Keys live in `backend/.env` (local) and `/root/halfca/.env` (VPS, mode 600). Both are excluded from git and from rsync.
- Models on this free key (checked 2026-10-03): `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, whisper, guard models. **No vision model** (no Llama 4), so PDF/image extraction needs testing in M5 or falls back to CSV.
- Calls: temperature 0, JSON mode where structured, `reasoning_effort=low` for gpt-oss, retries on 429, cached in `data/llm_cache.json` by request hash.
- The LLM never produces numbers; stage 4 accepts only a shortlisted voucher or "none".
- **Free-tier limits (checked 2026-10-03): 8,000 tokens/minute and 1,000 requests/day per model.**
  A copilot answer is ~3–6k tokens, a PDF read ~1k. Everything is cached by request hash, so
  repeats are free and instant. Rate-limit waits: stage 4 and PDF reading wait up to 60 s,
  the live copilot only 8 s and then falls back to the templated answer (with a note).
- `ai/warm.py` runs in the background when the API starts with a key: it reads the 13 demo
  PDFs and asks the 3 suggested questions, so the demo's AI moments are cache hits
  (~4 min the first time on a fresh cache; then ~1 s). `HALFCA_WARM=0` turns it off; tests do.

## 7. The VPS

Server access, the shared server's layout and the HTTPS routing are in
`docs/CONTEXT.local.md` (gitignored; it stays on the maintainer's machine). In short: Docker
Compose (`api` + `web`) on a shared VPS, behind that server's existing HTTPS Caddy. From the
laptop: `make deploy`, `make deploy-logs`, `make deploy-status`, `make deploy-reset`,
`make deploy-check`. The container entrypoint runs
`python -m halfca.data.build --scenario demo --if-stale`, which rebuilds the demo when the
code fingerprint changes and re-reconciles an uploaded dataset instead of replacing it.

## 8. Design direction (frontend)

- Friendly, comic-book-inspired (user's reference: a Marvel landing page): big condensed **Anton** headlines, chunky outlined "sticker" cards with offset shadows, pill buttons, halftone dots, light-hearted microcopy; numbers and evidence stay plain.
- Light mode = pale orange + peach (`--bg #FFF0E1`), dark mode = **pure black** (`#000`). Orange is the brand accent; amber (status) is golden so it never reads as brand. Tokens in `app/globals.css` and CLAUDE.md.
- Logo: circle split top orange / bottom ink with "CA" half-inverted; wordmark "HALF CA".
- Frontend is a static export: no server data fetching at runtime; screens fetch `/api/*` on the client (SWR). Dev uses Next rewrites; prod uses the Caddy proxy.

## 8b. Screens (built in M4)

- One client component per screen in `frontend/components/screens/*.tsx`; `app/(app)/*/page.tsx` are thin server wrappers (PageHeader + screen). Data via `useApi(path)` (SWR, `lib/hooks.ts`); after a job finishes the Upload screen calls `useRefreshAll()`.
- Shared UI: `components/ui/` (card, button, chip, kpi, count-up, states, toast), charts in `components/charts/` (donut, hbars, waterfall, benford), the map in `components/goods/route-map.tsx` (arc-length path sampler in `lib/path.ts`), the graph in `components/credit/ring-graph.tsx`, the evidence drawer in `components/evidence/evidence-drawer.tsx` (`useEvidence()(flag)` from anywhere).
- Story records are picked by rule, never by hard-coded numbers: Overview threads come from `summary.examples`; Goods beats from `/goods.beats`; Discrepancy hero cards from `pickHeroes()` (abolished slab charged *below* the right rate, IGST on intra-state, biggest near-duplicate); the Credit focus graph from `showcase` tags. For the demo they land on PP/26/0912 + MB/0877, LD/2291 → MB/0877 → KN/1502 → JP×3, DF/0450 + AR/S/2219 + INV/418, Patel/Mehta/Singh + Bharat/Ostwal/Northline.
- Animations use `motion/react`; React's lint rules forbid setState synchronously in effects and reassigning render-time variables, so sequences key their state by a run counter and timers call setState from callbacks.
- IMS approvals hit the shared server state: approving on the live site shows as approved for every viewer until the dataset changes.

## 9. API and upload (built in M3)

- Routers in `backend/halfca/api/routers/`: `dataset`, `overview` (summary, funnel, discrepancies, invoice detail), `goods`, `credit` (graph, supplier, benford), `ims` (IMS, approve, liability), `jobs` (upload, demo, reset, reconcile, job polling, demo-pack.zip). Typed client: `frontend/lib/api.ts` (`api.*`, `fetcher` for SWR, `followJob`).
- `api/state.py` keeps the current dataset in memory and reloads when the DuckDB file's inode/mtime changes. IMS approvals live in `data/state.json`, keyed by `dataset_id` (a new dataset clears them).
- `api/jobs.py`: one job at a time (409 otherwise), steps `extract → gstin → normalise → road → match` with real details from `pipeline.reconcile(progress=…)`. Uploads are saved under `data/uploads/` (last 5 kept). Sources not uploaded are kept from the current dataset, so dropping one edited CSV works. Reference data always comes from the server.
- `ingest/uploads.py` sorts a dropped folder/zip: data files by name then content, PDFs/images as documents, everything else ignored with a note. Wrong columns give a readable error.
- Goods "beats" and the Credit focus graph are chosen from the data (biggest clean verified trip, biggest of each failure; `showcase`-tagged suppliers), and they land on the spec's heroes for the demo.
- `make demo-pack` → `./demo-pack/Arora Hardware – Sep 2026/` (5 sources, 13 invoice PDFs, README). The app serves the same as `/api/demo-pack.zip`. PDFs are WeasyPrint-rendered GST tax invoices with a text layer, each marked synthetic.

## 9b. AI layer (built in M5)

- **Tools** (`halfca/tools.py`): the 7 spec tools over the current dataset. Money comes
  pre-formatted (`₹4.2 L`, `₹1,18,000`) so the model never does arithmetic; every result has a
  `headline` and an `evidence` list (`label`, `screen`, `href`). `supplier_risk` takes a name
  ("Kaveri") or GSTIN; `trace_goods`/`explain` take invoice numbers. Errors come back as
  `{"error": ...}`.
- **Copilot** (`ai/copilot.py`, `POST /api/copilot` SSE, `GET /api/copilot` info): with a key,
  a Groq tool loop (max 4 calls) then the model's answer, checked by the number guard; without
  a key, intent rules pick the tools and templates write the answer. Events: `tool`,
  `tool_done`, `token`, `evidence`, `done` (mode, model, numbers checked, note). The answer is
  paced word by word (22 ms) from a cached completion, so the demo is stable.
- **SSE gotchas:** Next dev gzip buffered the stream (fixed with `compress: false` in dev);
  the web Caddy skips `encode` for `/api/copilot`.
- **MCP:** `make mcp` (stdio). Add to Claude Code with
  `claude mcp add halfca -- uv --directory /home/gingersnaps/HalfCA/backend run python -m halfca.mcp_server`.
  Tool errors are raised as the SDK's `ToolError` so the client sees the message.
- **Invoice PDFs:** a dropped folder/zip's PDFs (and the demo button's 13 demo-pack PDFs) are
  read in the upload job's step 1 with live progress. Each file row says what reading found
  ("agrees with the register", "differs: …", "added as a new invoice", "needs review: …").
  `raw_documents` holds the extracted fields; uploads without PDFs keep the previous ones, so
  editing an amount in the CSV and re-uploading makes the PDF disagree with the books.
- IMS reasons stay templated on purpose (see CLAUDE.md decisions).

## 10. Conventions that are easy to miss

- Constants only in `config.py`; engines are pure (DataFrames in, results out, no I/O).
- Money text on the backend via `halfca/fmt.py`; on the frontend only via `lib/format.ts`.
- Every flag needs evidence (`engines/common.py`).
- `ruff` line length 100; `ruff format` then `ruff check`. TypeScript strict, no `any`, prettier width 100.
- Keep `deploy/rsync-exclude` excluding `.env`, `data/`, `node_modules`, `.venv`.
- This file contains VPS layout details. If the repo is ever published, review this file first.
