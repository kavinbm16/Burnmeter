.PHONY: install dev start build test check clean

# One-time setup: Python venv + deps, frontend deps.
install:
	uv venv
	uv pip install -e '.[dev]'
	cd frontend && npm install

# Development: backend (:8400) + frontend hot-reload (:5173) together.
# Open http://localhost:5173 — Ctrl-C stops both.
dev:
	@echo "→ backend  http://127.0.0.1:8400"
	@echo "→ frontend http://localhost:5173  (open this)"
	@trap 'kill 0' EXIT; \
		.venv/bin/python -m backend.main & \
		( cd frontend && npm run dev ) & \
		wait

# Single server: build the frontend, then serve everything from the backend.
# Open http://127.0.0.1:8400 — one process, one port.
start: build
	@echo "→ http://127.0.0.1:8400"
	.venv/bin/python -m backend.main

build:
	cd frontend && npm run build

test:
	.venv/bin/python -m pytest

check:
	cd frontend && npm run check

clean:
	rm -rf frontend/dist
