.PHONY: help install dev test lint serve-backend serve-frontend clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Backend ─────────────────────────────────────────────────────────

install: ## Install backend + frontend deps
	cd backend && uv sync
	cd frontend && npm install

dev: ## Start both backend and frontend
	$(MAKE) serve-backend &
	$(MAKE) serve-frontend

serve-backend: ## Start FastAPI dev server (port 8000)
	cd backend && uv run uvicorn canongate.api.app:app --reload --host 0.0.0.0 --port 8000

serve-frontend: ## Start Vite dev server (port 5173)
	cd frontend && npm run dev

test: ## Run backend tests
	cd backend && uv run pytest -v

lint: ## Run ruff + pyright
	cd backend && uv run ruff check src/ tests/
	cd backend && uv run ruff format --check src/ tests/

format: ## Auto-format backend code
	cd backend && uv run ruff format src/ tests/
	cd backend && uv run ruff check --fix src/ tests/

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.venv backend/*.db
	rm -rf frontend/node_modules frontend/dist
