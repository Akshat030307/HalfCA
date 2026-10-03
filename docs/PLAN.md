# Half CA — implementation plan

The spec is `CLAUDE.md`. This file covers **build order** and **how it ships**.

## Shape of the system

```
 your laptop                                    VPS (coursefactory-vps, 1 vCPU / ~2 GB free)
 ───────────                                    ───────────────────────────────────────────
 make deploy                                    mesh-caddy (already owns :80/:443, HTTPS)
   ├─ pnpm build  → frontend/out (static)          │  halfca.akshatchowdhary.online
   ├─ rsync repo + out/ → /root/halfca             ▼
   └─ ssh: docker compose up -d --build         172.18.0.1:8040  (bridge only, not public)
                                                   │
                                                 web  (caddy:2-alpine)
                                                   ├─ /        → static export
                                                   └─ /api/*   → api:8000
                                                 api  (python:3.12-slim, FastAPI, DuckDB)
                                                   └─ volume halfca_data (demo data, generated on first boot)
```

Why this shape:
- **Static frontend, built locally.** `next build` on a shared 1-vCPU box is slow and memory-hungry. The VPS only serves files.
- **Only `api` builds on the VPS.** Its dependency layer is cached, so a redeploy rebuilds just the code layer.
- **One port, one Caddy block.** The VPS already has a Caddy on 80/443 serving the other sites. Half CA follows the same pattern as the other sites there: bind `172.18.0.1:8040` and add one site block to `/root/mesh/Caddyfile`.

## Milestones

Each milestone ends green (`make test`), running locally, committed, and deployed.

**Status (2026-10-03):** M0 ✅ live at https://halfca.akshatchowdhary.online · M1 ✅ demo + random generators, 38 tests.

| # | Milestone | Delivers | Done when |
|---|---|---|---|
| **M0** | Foundations + deploy pipeline | Repo skeleton, FastAPI `/api/health`, Next.js shell with both themes and 9 placeholder screens, Dockerfile, compose, `make deploy` | Shell is live on the VPS and `/api/health` answers through the web container |
| **M1** | Synthetic data generator | `routes.json`, counterparties + GSTINs, demo scenario (seed 2609) with exact numbers, random mode with truth labels, DuckDB loader | `make data` reproduces the demo table at the data level |
| **M2** | Engines | ingest/normalise/GSTIN, matching cascade, diffs/dupes/gaps, tax verifier, physical trail, taint graph, anomaly + Benford, IMS autopilot, liability | `test_demo_numbers` passes every row of the demo table, plus one test file per engine |
| **M3** | API | `POST /reconcile` pipeline + every GET endpoint, Pydantic models mirrored in `lib/api.ts` | All endpoints return demo data with `evidence` |
| **M4** | Screens | Upload, Matching, Overview, Discrepancies, **Goods ★**, **Credit ★**, IMS, Liability (Copilot UI shell) | All 9 screens render API data in both themes at 1280–1920 px |
| **M5** | AI layer | `ai/llm.py` adapter (provider TBD) + template fallbacks, IMS reasons, copilot SSE tool loop, MCP server (7 tools), stage-4 adjudication, PDF extraction | Copilot answers "Why did my liability go up?" with tool trace and evidence, with and without an LLM |
| **M6** | Ship it | WeasyPrint audit PDF, `make eval`, `docs/RUNBOOK.md`, final deploy | Definition of done in `CLAUDE.md` |

Order inside M4: shell → Overview → **Goods** → **Credit** → the rest (the ★ screens get polish first).

## How the demo numbers are hit (M1)

The generator builds the month as a **script, not a dice roll**:
1. Create counterparties (direct suppliers/customers + a layered upstream DAG, so the only cycle is the planted ring).
2. Place every hero record and every injected case with its `truth_label`.
3. Fill the rest with clean, realistic invoices (log-normal amounts, weekday bias).
4. Run small **balancers** so ITC claimed, rejected, at-risk and output tax land inside ±₹500 of the lakh targets (well clear of rounding edges).
5. Derive ledger vouchers, payments, IMS records, e-way bills and toll crossings from the invoices.

Definitions the engines and generator share:
- The **funnel** pairs each invoice with its books entry (purchase/sales voucher). Payments and IMS link to the pair afterwards.
- **ITC claimed (as filed)** = ITC on every IMS record, because unactioned IMS records are deemed accepted.
- All 7 duplicates are inward double-bookings, so they never inflate output tax.
- Outward tax errors are over-charges or wrong heads, so under-reported output tax is ₹0 and exposure = rejected + at risk.

## Deploying

One-time setup (needs you):
1. DNS: add an **A record** `halfca` → the VPS's public IP at your DNS provider.
2. Approve one block appended to `/root/mesh/Caddyfile` (then `caddy reload` in `mesh-caddy-1`):
   ```
   halfca.akshatchowdhary.online {
   	reverse_proxy 172.18.0.1:8040
   }
   ```

Every redeploy: `make deploy`. Reset demo data on the server: `make deploy-reset`. Logs: `make deploy-logs`.

## Open items

- **LLM provider** for M5 (Anthropic or an OpenAI-compatible one: Gemini, Groq, OpenRouter, Ollama). Everything before M5 is LLM-free.
- **Site protection** (basic auth at the web container) once a paid LLM key lives on the server.
