# NovaMindd

> **A sovereign, local-first AI execution platform for confidential industrial workflows.**

NovaMindd is an AI workbench designed for environments where sensitive documents, internal knowledge, engineering workflows, and AI-generated actions must remain under organisational control.

> **The model provides intelligence. NovaMindd provides authority.**

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- [Ollama](https://ollama.ai) running locally (`ollama serve`)
- Docker (for sandbox execution)
- PostgreSQL with pgvector (or use Docker Compose)

### 1. Install backend dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, OLLAMA_BASE_URL
```

### 3. Pull models into Ollama

```bash
ollama pull llama3.2:3b
ollama pull llava:7b
ollama pull deepseek-coder:6.7b
```

### 4. Build the sandbox image

```bash
python scripts/build_sandbox.py
```

### 5. Start with Docker Compose

```bash
docker-compose up
```

Or start the backend and frontend separately in development mode:

**Backend**
```bash
python scripts/run_dev.py
```

**Frontend**
```bash
cd apps/web
npm install
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend (Vite + React) | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| API docs (Swagger) | `http://localhost:8000/api/v1/docs` |

> The Vite dev server proxies all `/api` and `/health` requests to the backend automatically — no CORS configuration needed during development.

---

## Architecture

```
User / Operator
      │
      ▼
NovaMindd API (FastAPI)
      │
      ▼
Control Plane — Policy · RBAC · Routing · Residency · Validation
      │
      ├── Local Intelligence (Ollama LLM / VLM / Coding)
      ├── Private Knowledge (BM25 + Vector + Reranking)
      ├── Document AI (PyMuPDF + OCR + VLM)
      ├── Tool Gateway → Docker Sandbox
      └── Artifact Renderers (DOCX / XLSX / PPTX)
            │
            ▼
      Provenance + Audit
```

---

## Core Principles

1. **Intelligence Is Not Authority** — The model proposes. The platform authorizes.
2. **Least Privilege by Default** — Tools, files, credentials, and network access are explicitly authorized.
3. **Fail Closed** — Insufficient evidence or failed validation stops the workflow.
4. **Evidence Before Confidence** — Traceable evidence is preferred over fluent unsupported output.
5. **Deterministic Where Possible** — LLMs handle reasoning; deterministic renderers handle artifacts.
6. **Everything Important Is Observable** — Routing, execution, validation, and provenance are auditable.

---

## Project Structure

```
NovaMindd/
├── apps/
│   ├── api/                FastAPI application + routes
│   └── web/                React + TypeScript frontend (Vite)
│       ├── src/            Application source
│       ├── vite.config.ts  Dev server + API proxy config
│       └── Dockerfile      Production nginx container
├── core/
│   ├── config.py           Platform configuration
│   ├── logging.py          Structured logging + audit
│   ├── inference/          Model registry, router, residency, Ollama provider
│   ├── retrieval/          BM25 + vector + hybrid retrieval engine
│   ├── document_ai/        OCR + VLM document processing
│   ├── control_plane/      Policy engine, RBAC, tool registry, validation
│   ├── agents/             Tool gateway, agent planner
│   ├── sandbox/            Docker sandbox executor
│   ├── artifacts/          Document IR, DOCX/XLSX/PPTX renderers
│   └── provenance/         Provenance and audit records
├── models/registry/        Model manifests
├── policies/               Tool, network, resource policies
├── sandbox/images/         Sandbox Dockerfile
├── scripts/                Dev utilities
├── tests/
│   ├── unit/               Unit tests (no external deps)
│   ├── integration/        API integration tests
│   ├── security/           Adversarial sandbox/policy tests
│   └── evaluation/         Retrieval quality + provenance evaluation
├── configs/config.yaml     Platform configuration
├── docker-compose.yml
└── pyproject.toml
```

---

## Running Tests

```bash
# All unit tests (no Docker or Ollama required)
pytest tests/unit/ -v

# Integration tests (requires running API)
pytest tests/integration/ -v

# Security tests (requires Docker)
pytest tests/security/ -v

# Evaluation suite
pytest tests/evaluation/ -v

# Full suite
pytest -v
```

---

## Development Roadmap

| Phase | Status |
|-------|--------|
| 1. Foundation | ✅ Complete |
| 2. Local Inference | ✅ Complete |
| 3. Knowledge Layer | ✅ Complete |
| 4. Control Plane | ✅ Complete |
| 5. Secure Execution | ✅ Complete |
| 6. Agentic Workflows | ✅ Complete |
| 7. Artifacts | ✅ Complete |
| 8. Evaluation | ✅ Complete |
| 9. Frontend (React + Vite) | 🚧 In Progress |

---

## Security Architecture

- **Policy Engine** — Rule-based allow/deny/escalate for every action
- **Tool Authorization** — Explicit role and permission checks per tool
- **Docker Sandbox** — `--network=none`, read-only root FS, non-root UID, CPU/RAM limits
- **Deny-by-Default Egress** — No outbound connections from generated code
- **Credential Isolation** — No host environment variables in sandbox
- **Audit Log** — Append-only JSONL audit trail for every policy decision and execution
- **Provenance** — Every output traceable to evidence, model, tool actions, and validation steps

---

## License

License to be defined.
