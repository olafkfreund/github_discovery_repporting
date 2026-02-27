# DevOps Discovery & Reporting Platform

default:
    @just --list

# --- Backend ---

# Run the backend dev server
dev:
    uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test *args:
    uv run pytest {{args}}

# Run tests with coverage
test-cov:
    uv run pytest --cov=backend --cov-report=term-missing

# Lint
lint:
    uv run ruff check backend/ tests/

# Format
fmt:
    uv run ruff format backend/ tests/

# Type check
typecheck:
    uv run mypy backend/

# Run lint + typecheck
check: lint typecheck

# --- Database ---

# Start PostgreSQL via docker compose
db-up:
    docker compose up -d postgres

# Stop PostgreSQL
db-down:
    docker compose down

# Create a new migration
migrate-create name:
    uv run alembic revision --autogenerate -m "{{name}}"

# Run migrations
migrate:
    uv run alembic upgrade head

# Rollback last migration
migrate-down:
    uv run alembic downgrade -1

# --- Frontend ---

# Install frontend deps
fe-install:
    cd frontend && npm install

# Run frontend dev server
fe-dev:
    cd frontend && npm run dev

# Build frontend
fe-build:
    cd frontend && npm run build

# --- Setup ---

# Initial project setup
setup: db-up
    uv sync --all-extras
    sleep 2
    just migrate
    mkdir -p reports
    @echo "Setup complete. Run 'just dev' to start the backend."

# Generate a Fernet encryption key
gen-key:
    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
