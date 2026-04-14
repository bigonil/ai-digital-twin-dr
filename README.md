# 🧬 AI Digital Twin — Disaster Recovery Platform

> **A Living Digital Twin of your infrastructure for real-time Disaster Recovery simulation.**  
> Map Terraform resources, source code, and documentation into a unified graph — then simulate failure scenarios and generate recovery playbooks in seconds.

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI Digital Twin Platform                            │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     React Frontend  (:3000)                          │   │
│  │   ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │   │
│  │   │  3D Force Graph  │  │ Disaster Panel  │  │  Metrics Sidebar │   │   │
│  │   │  (Neo4j topology)│  │ (Blast Radius)  │  │  (VictoriaMetrics│   │   │
│  │   └────────┬─────────┘  └────────┬────────┘  └────────┬─────────┘   │   │
│  └────────────┼────────────────────┼────────────────────┼─────────────┘   │
│               │        REST API / WebSocket               │                 │
│  ┌────────────▼──────────────────────────────────────────▼─────────────┐   │
│  │                FastAPI Backend  (:8000) + MCP Server (:9000)         │   │
│  │   ┌─────────────────────────────────────────────────────────────┐   │   │
│  │   │                     Parsers (4 Phases)                      │   │   │
│  │   │  Phase 1: Terraform HCL → Neo4j graph                       │   │   │
│  │   │  Phase 2: Python/JS AST → Function↔Resource links           │   │   │
│  │   │  Phase 3: Markdown Docs → Qdrant vector embeddings          │   │   │
│  │   │  Phase 4: VictoriaMetrics → Live health on graph nodes       │   │   │
│  │   └─────────────────────────────────────────────────────────────┘   │   │
│  │   ┌─────────────────────────────────────────────────────────────┐   │   │
│  │   │                     MCP Tools                               │   │   │
│  │   │  simulate_disaster(node_id) → cascading failure analysis    │   │   │
│  │   │  get_recovery_plan(target)  → step-by-step DR playbook      │   │   │
│  │   │  check_drift()             → Terraform state vs. graph      │   │   │
│  │   └─────────────────────────────────────────────────────────────┘   │   │
│  └────┬──────────────────────────┬──────────────────────────┬──────────┘   │
│       │                          │                          │               │
│  ┌────▼─────────┐   ┌────────────▼──────────┐   ┌──────────▼────────────┐  │
│  │    Neo4j     │   │   VictoriaMetrics     │   │        Qdrant         │  │
│  │  (:7474/7687)│   │      (:8428)          │   │       (:6333)         │  │
│  │  Graph DB    │   │  Time-Series DB       │   │     Vector DB         │  │
│  │  Topology    │   │  Live Metrics/Health  │   │  Semantic Search (RAG)│  │
│  └──────────────┘   └───────────────────────┘   └───────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Ollama  (runs on HOST machine, outside Docker) — :11434            │   │
│  │  Model: nomic-embed-text (768-dim embeddings for Qdrant)            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service Summary

| Service          | Image                                      | Port(s)        | Purpose                          |
|------------------|--------------------------------------------|----------------|----------------------------------|
| `frontend`       | node:20-alpine (Vite → Nginx)              | **3000**       | React 3D dashboard               |
| `backend`        | python:3.12-slim (FastAPI + MCP)           | **8000**, 9000 | REST API + MCP server            |
| `neo4j`          | neo4j:5.18-community                       | **7474**, 7687 | Graph DB — infra topology        |
| `victoriametrics`| victoriametrics/victoria-metrics:v1.101.0 | **8428**       | Time-series metrics              |
| `qdrant`         | qdrant/qdrant:v1.9.2                       | **6333**, 6334 | Vector DB — semantic search      |
| `vmagent`        | victoriametrics/vmagent:v1.101.0           | 8429           | Prometheus scrape agent          |
| Ollama           | _Host process_ (not Docker)                | **11434**      | LLM embedding model              |

### Memory Allocation (16 GB target)

| Service          | Limit   |
|------------------|---------|
| neo4j            | 3 GB    |
| victoriametrics  | 768 MB  |
| qdrant           | 1.5 GB  |
| backend          | 1 GB    |
| frontend         | 512 MB  |
| vmagent          | 256 MB  |
| **Total**        | **~7 GB** |

---

## ✅ Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop | ≥ 4.25 | Enable WSL2 backend on Windows |
| Docker Compose | v2 (plugin) | Bundled with Docker Desktop |
| Ollama | any | Download at [ollama.ai](https://ollama.ai) |
| `nomic-embed-text` | — | `ollama pull nomic-embed-text` |
| Node.js | ≥ 20 | Only needed for local frontend dev |
| Python | ≥ 3.12 | Only needed for local backend dev |

---

## 🚀 Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/bigonil/ai-digital-twin-dr.git
cd ai-digital-twin-dr
cp .env.example .env
# Edit .env if you need custom passwords
```

### 2. Pull the Ollama embedding model (on your host)

```bash
ollama pull nomic-embed-text
```

### 3. Launch — choose your platform

#### Windows (PowerShell)

```powershell
.\scripts\start.ps1
```

The script will:
- Check Docker Desktop is running
- Copy `.env.example` → `.env` if needed
- Set `COMPOSE_CONVERT_WINDOWS_PATHS=1`
- Start all 6 containers (`docker compose up -d`)
- Tail logs until all health checks pass

#### WSL2 / Linux / macOS (Bash)

```bash
bash scripts/start.sh
```

The script will:
- Detect `docker compose` (v2) vs `docker-compose` (v1)
- Auto-detect Ollama URL (localhost → Windows host fallback)
- Warn if running from `/mnt/c/` (bind-mount perf note)
- Start all containers and watch health

#### Manual

```bash
cp .env.example .env
docker compose up -d
docker compose ps        # verify all containers are healthy
```

---

## 📥 Ingest Sample Data

Once all containers show **healthy**, ingest the included sample Terraform + docs:

**Windows:**
```powershell
.\scripts\ingest.ps1
```

**WSL2 / Linux:**
```bash
bash scripts/ingest.sh
```

**Manual (curl):**
```bash
# Ingest Terraform files → Neo4j graph
curl -X POST http://localhost:8000/api/parse/terraform \
  -H "Content-Type: application/json" \
  -d '{"path": "/data/terraform/sample"}'

# Ingest architecture docs → Qdrant vectors
curl -X POST http://localhost:8000/api/parse/docs \
  -H "Content-Type: application/json" \
  -d '{"path": "/data/docs"}'
```

---

## 🌐 Service Access

| Service              | URL                                            | Credentials            |
|----------------------|------------------------------------------------|------------------------|
| **Dashboard**        | http://localhost:3000                          | —                      |
| **FastAPI docs**     | http://localhost:8000/docs                     | —                      |
| **FastAPI health**   | http://localhost:8000/health                   | —                      |
| **Neo4j Browser**    | http://localhost:7474                          | neo4j / changeme_neo4j |
| **VictoriaMetrics**  | http://localhost:8428                          | —                      |
| **Qdrant UI**        | http://localhost:6333/dashboard                | —                      |
| **MCP Server**       | stdio on port 9000                             | —                      |

---

## 🤖 MCP Server Integration

The platform exposes a [Model Context Protocol](https://modelcontextprotocol.io) server so AI agents (Claude Code, GitHub Copilot) can query and manipulate the graph directly.

### Available Tools

| Tool | Description |
|------|-------------|
| `simulate_disaster(node_id, depth)` | Recursive impact analysis — finds all cascading failures from a node |
| `get_recovery_plan(target)` | Queries Neo4j + Qdrant to produce a step-by-step DR playbook |
| `check_drift()` | Compares Terraform state files vs. current Neo4j graph |

### Connect Claude Code

Add to your Claude Code MCP config (`~/.claude/mcp_settings.json`):

```json
{
  "mcpServers": {
    "digital-twin-dr": {
      "command": "docker",
      "args": ["exec", "-i", "dt-backend", "python", "-m", "mcp.server"]
    }
  }
}
```

### Connect GitHub Copilot (MCP extension)

```json
{
  "servers": {
    "digital-twin-dr": {
      "type": "stdio",
      "command": "docker",
      "args": ["exec", "-i", "dt-backend", "python", "-m", "mcp.server"]
    }
  }
}
```

---

## 📂 Project Structure

```
ai-digital-twin-dr/
├── docker-compose.yml          # 6-service orchestration
├── .env.example                # Environment variable template
├── .gitattributes              # LF line-ending enforcement
├── config/
│   └── scrape.yml              # vmagent Prometheus scrape config
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI entry point
│   ├── settings.py             # Pydantic settings
│   ├── api/                    # REST endpoints
│   │   ├── graph.py            # Graph CRUD
│   │   ├── metrics.py          # VictoriaMetrics proxy
│   │   └── dr.py               # DR simulation endpoints
│   ├── db/                     # Database clients
│   │   ├── neo4j_client.py
│   │   ├── victoriametrics_client.py
│   │   └── qdrant_client.py
│   ├── parsers/                # 4-phase ingestion
│   │   ├── infra.py            # Phase 1: Terraform → Neo4j
│   │   ├── code.py             # Phase 2: AST → function links
│   │   └── docs.py             # Phase 3: Markdown → Qdrant
│   └── mcp/
│       └── server.py           # MCP tool server
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── nginx.conf
│   └── src/
│       ├── App.jsx
│       ├── api/client.js
│       └── components/
│           ├── Graph3D.jsx         # ForceGraph3D visualization
│           ├── DisasterPanel.jsx   # Blast radius simulation UI
│           └── MetricsSidebar.jsx  # Live metrics from VictoriaMetrics
├── data/
│   ├── terraform/sample/       # Sample Terraform files for ingestion
│   └── docs/                   # Sample architecture docs
└── scripts/
    ├── start.ps1               # Windows PowerShell launcher
    ├── start.sh                # WSL2/Linux/macOS launcher
    ├── ingest.ps1              # Data ingestion (Windows)
    └── ingest.sh               # Data ingestion (Linux)
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt URI (inside Docker network) |
| `NEO4J_PASSWORD` | `changeme_neo4j` | Neo4j admin password |
| `VICTORIAMETRICS_URL` | `http://victoriametrics:8428` | VM query endpoint |
| `QDRANT_HOST` | `qdrant` | Qdrant service hostname |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama on host machine |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `VITE_API_URL` | `http://localhost:8000` | API URL for browser → backend calls |
| `DR_RTO_SECONDS` | `300` | Recovery Time Objective threshold |
| `DR_RPO_SECONDS` | `60` | Recovery Point Objective threshold |

---

## 🩺 Health Checks

```bash
# All containers healthy?
docker compose ps

# Backend API
curl http://localhost:8000/health

# Neo4j
curl http://localhost:7474

# VictoriaMetrics
curl http://localhost:8428/health

# Qdrant
curl http://localhost:6333/healthz
```

---

## 🛑 Stop & Clean Up

```bash
# Stop all containers (keep data volumes)
docker compose down

# Stop and remove all volumes (destructive — wipes graph + metrics + vectors)
docker compose down -v
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-improvement`
3. Commit with descriptive messages
4. Open a Pull Request

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
