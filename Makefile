# Half CA. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

VPS      ?= coursefactory-vps
VPS_DIR  ?= /root/halfca
DOMAIN   ?= halfca.akshatchowdhary.online
SEED     ?= 7
BACKEND  := cd backend &&
FRONTEND := cd frontend &&
COMPOSE  := cd $(VPS_DIR)/deploy && docker compose
# Pick up Caddyfile edits without a restart; retried because a just-created
# container needs a moment before its admin endpoint listens.
RELOAD_WEB := for i in $$(seq 1 15); do $(COMPOSE) exec -T web caddy reload --address 127.0.0.1:2019 --config /etc/caddy/Caddyfile 2>/dev/null && exit 0; sleep 1; done; echo "caddy reload failed" >&2; exit 1

.PHONY: help setup data data-random demo-pack api web dev mcp test eval report build \
        deploy deploy-check deploy-domain deploy-logs deploy-reset deploy-status

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies
	$(BACKEND) uv sync
	$(FRONTEND) pnpm install

data: ## Generate the demo scenario (seed 2609) and load DuckDB
	$(BACKEND) uv run python -m halfca.data.build --scenario demo

data-random: ## Generate a random-mode dataset (SEED=7)
	$(BACKEND) uv run python -m halfca.data.build --scenario random --seed $(SEED)

demo-pack: ## Ready-to-drag demo folder (5 sources + invoice PDFs) in ./demo-pack
	$(BACKEND) uv run python -m halfca.data.demo_pack --out ../demo-pack

api: ## FastAPI on :8000 with reload
	$(BACKEND) uv run uvicorn halfca.api.main:app --reload --port 8000

web: ## Next.js dev server on :3000 (proxies /api to :8000)
	$(FRONTEND) pnpm dev --port 3000

dev: ## api + web together
	$(MAKE) -j2 api web

mcp: ## MCP server on stdio
	$(BACKEND) uv run python -m halfca.mcp_server

test: ## Backend tests + frontend typecheck and lint
	$(BACKEND) uv run pytest -q
	$(BACKEND) uv run ruff check .
	$(FRONTEND) pnpm typecheck && pnpm lint

eval: ## Precision/recall per discrepancy type on random mode
	$(BACKEND) uv run python -m halfca.eval --seed $(SEED)

report: ## Write data/audit-report-2026-09.pdf
	$(BACKEND) uv run python -m halfca.report.pdf

build: ## Static frontend export into frontend/out
	$(FRONTEND) pnpm build

deploy: build ## Build, ship to the VPS, (re)start containers, health-check
	rsync -az --delete --exclude-from=deploy/rsync-exclude ./ $(VPS):$(VPS_DIR)/
	ssh $(VPS) '$(COMPOSE) up -d --build --remove-orphans && $(RELOAD_WEB)'
	@$(MAKE) --no-print-directory deploy-check

deploy-check: ## Wait for the deployed API to answer through the web container
	@ssh $(VPS) 'for i in $$(seq 1 60); do curl -fsS http://172.18.0.1:8040/api/health && echo && exit 0; sleep 2; done; echo "health check failed" >&2; exit 1'

deploy-domain: ## One-time: route DOMAIN to Half CA via the VPS's shared Caddy
	@ssh $(VPS) getent hosts $(DOMAIN) >/dev/null || { echo "$(DOMAIN) has no DNS record yet (add A -> 200.141.7.5)"; exit 1; }
	ssh $(VPS) bash -s -- $(DOMAIN) < deploy/route-domain.sh

deploy-logs: ## Tail the VPS containers' logs
	ssh -t $(VPS) '$(COMPOSE) logs -f --tail=100'

deploy-status: ## Container status on the VPS
	ssh $(VPS) '$(COMPOSE) ps'

deploy-reset: ## Regenerate the demo data on the VPS
	ssh $(VPS) '$(COMPOSE) exec -T api python -m halfca.data.build --scenario demo && $(COMPOSE) restart api'
