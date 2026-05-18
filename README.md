# 🔮 ATHENA — Predictive Resilience Engine

> **A living predictive engine for your cloud infrastructure.**  
> Map Terraform resources, source code, and documentation into a unified graph — then simulate failure scenarios and generate recovery playbooks in seconds.

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ATHENA — Predictive Resilience Engine                  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     React Frontend  (:3001)                          │   │
│  │   ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │   │
│  │   │  3D Force Graph  │  │ Disaster Panel  │  │  Metrics Sidebar │   │   │
│  │   │  (Neo4j topology)│  │ (Blast Radius)  │  │  (VictoriaMetrics│   │   │
│  │   └────────┬─────────┘  └────────┬────────┘  └────────┬─────────┘   │   │
│  └────────────┼────────────────────┼────────────────────┼─────────────┘   │
│               │        REST API / WebSocket               │                 │
│  ┌────────────▼──────────────────────────────────────────▼─────────────┐   │
│  │                FastAPI Backend  (:8001) + MCP Server (:9001)         │   │
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
| `frontend`       | node:20-alpine (Vite → Nginx)              | **3001**       | React 3D dashboard               |
| `backend`        | python:3.12-slim (FastAPI + MCP)           | **8001**, 9001 | REST API + MCP server            |
| `neo4j`          | neo4j:5.18-community                       | **7474**, 7687 | Graph DB — infra topology        |
| `redis`          | redis:7-alpine                             | **6379**       | Simulation result cache          |
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
| redis            | 256 MB  |
| vmagent          | 256 MB  |
| **Total**        | **~7.3 GB** |

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
curl -X POST http://localhost:8001/api/parse/terraform \
  -H "Content-Type: application/json" \
  -d '{"path": "/data/terraform/sample"}'

# Ingest architecture docs → Qdrant vectors
curl -X POST http://localhost:8001/api/parse/docs \
  -H "Content-Type: application/json" \
  -d '{"path": "/data/docs"}'
```

---

## 🌐 Service Access

| Service              | URL                                            | Credentials            |
|----------------------|------------------------------------------------|------------------------|
| **Dashboard**        | http://localhost:3001                          | —                      |
| **FastAPI docs**     | http://localhost:8001/docs                     | —                      |
| **FastAPI health**   | http://localhost:8001/health                   | —                      |
| **Neo4j Browser**    | http://localhost:7474                          | neo4j / changeme_neo4j |
| **VictoriaMetrics**  | http://localhost:8428                          | —                      |
| **Qdrant UI**        | http://localhost:6333/dashboard                | —                      |
| **MCP Server**       | stdio on port 9001                             | —                      |

---

## 🎬 Dynamic Disaster Simulation — Unified Dashboard with 2D Propagation, Metrics & Report

The platform visualizes cascading failures in **real-time** with an integrated 3-column dashboard, interactive timeline, and comprehensive post-simulation report:

### Dashboard Layout

```
┌──────────────────────────────────────────────────────────┐
│               Header (Node Count)                        │
├──────────┬──────────────────────┬──────────────────────┤
│Topology  │  2D Infrastructure    │  Metrics Dashboard   │
│Viewer    │  Map                  │  (per-node)          │
│(list)    │  • All topo nodes     │  • CPU/Memory bars   │
│  w-56    │  • Connections        │  • Sparklines        │
│  border-r│  • Blast propagation  │  • 8+ metrics        │
│          │  • WoW animations     │  • RTO/RPO           │
├──────────┴──────────────────────┴──────────────────────┤
│ Simulation Controls (depth input + Simulate/Reset) h-14 │
├─────────────────────────────────────────────────────────┤
│ SimulationTimeline (play/pause/speed/progress)   h-20   │
├─────────────────────────────────────────────────────────┤
│ SimulationReport (5 sections, scrollable)       max-h-64│
└─────────────────────────────────────────────────────────┘
```

### Features

**Topology Viewer (Left Panel)**
- Browse all infrastructure nodes from Neo4j
- Click to select a node for simulation
- Node type icons and status badges

**Infrastructure Map (Center Panel)**
- **Tiered Layout**: Nodes grouped by architectural tier (LB → Compute → Data → Storage)
- **Real-Time Propagation**: Watch nodes turn RED as the cascade spreads (0ms → total_duration_ms)
- **All Topology Edges**: Base layer shows complete infrastructure dependency graph
- **Blast Radius Highlighting**: Selected nodes and edges animate with gradient flows
- **WoW Animations**:
  - `pulse-glow` (0.8s): Nodes actively failing — bright red pulse
  - `pulse-healthy` (2s): Nodes in blast radius — steady green glow
  - `edge-flow` (1.5s): Propagation paths — animated gradient flows
  - `hop-ring` (2s): Origin node — concentric ripple effect
- **Node Status**: Colored circles (🟢 Healthy, 🟡 Degraded, 🔴 Failed) with icons

**Metrics Dashboard (Right Panel)**
- **Per-Node Metrics**: 
  - CPU/Memory bars with historical sparklines
  - Request rate, error rate, latency percentiles (p50/p95/p99)
  - Throughput, disk I/O, replication lag (database nodes only)
  - RTO/RPO and redundancy status
- **Deterministic Mock Data**: Same node always shows identical values; seeded variation across nodes
- **Type-Aware Baselines**: Databases show high memory/replication lag; load balancers show high request rates
- **Idle State**: "Select a node to view observability metrics"

**Simulation Controls**
- **Depth Input**: Set propagation depth (1-10 hops, default 5)
- **Simulate Button**: Triggers disaster simulation on selected node
- **Reset Button**: Clears simulation state and returns to idle topology view

**Interactive Timeline** (appears after simulation)
- **Play/Pause**: Control animation playback
- **Rewind**: Reset to start of simulation
- **Speed Slider**: 0.25x to 2.0x animation speed
- **Progress Bar**: Visual timeline of failure cascade (0ms → total_duration_ms)
- **Auto-pause**: Playback automatically pauses at simulation end

**Post-Simulation Report** (appears when playback completes)
- **Executive Summary**: Origin node, failure mode, affected count, max hops, worst RTO/RPO, cost
- **Eisenhower Matrix**: Interactive 2×2 quadrant view + SVG bubble chart (one bubble per affected node)
- **Impact Table**: Sortable table showing all affected nodes with distance, type, effective RTO/RPO, recovery cost
- **Timeline of Events**: Chronological list of node failures with millisecond precision
- **Root Cause Analysis**: Auto-generated failure description based on node type
- **Mitigation Actions**: Recovery steps + architecture-specific recommendations + best practices
- **LLM Playbook**: Claude-powered step-by-step recovery runbook (falls back to static template if API unavailable)
- **Collapsible Sections**: Each report section can be expanded/collapsed for focused analysis

### Usage Workflow

1. **Select a Node**: Click any node in the Topology Viewer (left panel)
2. **Configure Simulation**: Set propagation depth in the control bar (default: 5)
3. **Simulate**: Click the red "Simulate" button
4. **Review Blast Radius**: 
   - Infrastructure Map highlights all affected nodes
   - Metrics Dashboard shows selected node's observability metrics
5. **Playback**:
   - Click **Play** to animate the disaster propagation
   - Watch nodes pulse in sequence as failures cascade
   - Adjust **Speed** slider for faster/slower animation
6. **Analyze Results**:
   - SimulationTimeline shows cascade progression with timeline bar
   - SimulationReport appears at playback end with detailed analysis
   - Review RTO/RPO impact, recovery steps, and recommendations

### Simulation Response Data

The `/api/dr/simulate` endpoint returns:

```json
{
  "origin_node_id": "db-001",
  "blast_radius": [
    {
      "id": "db-001",
      "name": "Primary Database",
      "type": "aws_rds_cluster",
      "distance": 0,
      "step_time_ms": 0,
      "estimated_rto_minutes": 15,
      "estimated_rpo_minutes": 1
    },
    {
      "id": "app-001",
      "name": "API Server",
      "type": "aws_instance",
      "distance": 1,
      "step_time_ms": 2500,
      "estimated_rto_minutes": 10,
      "estimated_rpo_minutes": 2
    }
  ],
  "timeline_steps": [
    {"node_id": "db-001", "node_name": "Primary Database", "distance": 0, "step_time_ms": 0},
    {"node_id": "app-001", "node_name": "API Server", "distance": 1, "step_time_ms": 2500}
  ],
  "recovery_steps": [
    "Trigger automated failover to read replica",
    "Update DNS to point to standby database",
    "Restart application servers"
  ],
  "max_distance": 3,
  "total_duration_ms": 5000,
  "worst_case_rto_minutes": 15,
  "worst_case_rpo_minutes": 2,
  "eisenhower_quadrant": "Q1",
  "total_recovery_cost_usd": 4320.50,
  "model_version": "1.0-accurate"
}
```

---

## 🛠️ Advanced Features

Beyond the core DR Simulator, the platform includes 4 dedicated features for compliance, planning, incident analysis, and resilience testing:

### **Compliance** — Audit Against SLAs
- Run continuous audits against RTO/RPO thresholds (default: 60 min RTO, 15 min RPO)
- Identify nodes in warning/failure state based on worst-case cascading impact
- Export audit reports as JSON for stakeholders
- **Use case**: Infrastructure team verifies compliance before/after changes

### **What-If Analysis** — Test Architecture Changes
- Model virtual infrastructure additions (replicas, caches, secondary regions)
- Simulate baseline vs. proposed topology without modifying production
- Compare blast radius and RTO/RPO deltas
- **Use case**: Evaluate impact of planned redundancy or failover strategy before deployment

### **Chaos Engineering** — Validate Resilience
- Run chaos experiments with 5 failure modes (terminate, network loss, CPU hog, disk full, memory pressure)
- Record actual results from lab tests and compare against predictions
- Calculate resilience score based on RTO accuracy and node prediction accuracy
- **Use case**: Proactively test systems; measure confidence in recovery predictions

### **Postmortem Analysis** — Learn from Real Incidents
- Analyze real production incidents against simulation predictions
- Calculate prediction accuracy (precision, recall, F1-score)
- Auto-generate recommendations based on false positives/negatives
- **Use case**: Improve model over time; share incident data with stakeholders

**📖 Full Guide**: See [FEATURES.md](./docs/FEATURES.md) for detailed workflows and examples.

---

## 🎯 Eisenhower DR Classifier

Every simulation result is automatically classified into one of four **Eisenhower quadrants** to drive the correct response urgency:

```
                    IMPORTANT
                        │
          Q2            │            Q1
     Plan & schedule    │      Act immediately
     (not urgent,       │      (urgent + important)
      important)        │
  ──────────────────────┼────────────────────────── URGENT
     Q4                 │            Q3
     Defer / ignore     │      Delegate / monitor
     (not urgent,       │      (urgent, not important)
      not important)    │
                        │
                   NOT IMPORTANT
```

### Classification Logic (`algorithms/eisenhower_classifier.py`)

| Signal | Threshold | Contribution |
|--------|-----------|--------------|
| `worst_case_rto_minutes > rto_target` | configurable (default 60 min) | **Urgent** |
| `replication_lag_min > rpo_target` | configurable (default 15 min) | **Urgent** |
| `cascade_in_progress` | `len(blast_radius) > 1` | **Urgent** |
| `affects_production` | always `True` in API | **Important** |
| `critical_blast` | any node at distance ≤ 2 | **Important** |
| RTO breach (above) | same as urgency | **Important** |

### Escalation Timer

Q3 events (urgent but not important) auto-escalate to Q1 after **15 minutes** (`ESCALATION_WINDOW_MIN`) without resolution, via `apply_escalation(quadrant, elapsed_minutes)`.

### Q1 Auto-Routing in MCP

When `simulate_disaster` classifies an event as **Q1**, the MCP server immediately appends a full recovery plan (`get_recovery_plan`) to the response — no second tool call needed by the agent.

### Frontend Visualization

The **Simulation Report** includes two Eisenhower visualizations:
- **2×2 Matrix**: The four quadrants with the active quadrant highlighted, showing live blast radius count, worst-case RTO, and contextual action bullets.
- **Bubble Chart**: Each affected node plotted on Urgency (x-axis, based on distance) × Importance (y-axis, based on effective RTO). Bubble radius scales with importance; color follows the node's individual quadrant.

### API Response Field

```json
{
  "eisenhower_quadrant": "Q1",
  "worst_case_rto_minutes": 120,
  "worst_case_rpo_minutes": 5,
  ...
}
```

---

## 🤖 MCP Server Integration

The platform exposes a [Model Context Protocol](https://modelcontextprotocol.io) server so AI agents (Claude Code, GitHub Copilot) can query and manipulate the graph directly.

### Available Tools

| Tool | Description |
|------|-------------|
| `simulate_disaster(node_id, depth)` | Recursive impact analysis — returns timeline with step_time_ms, Eisenhower quadrant; auto-routes Q1 to recovery plan |
| `get_recovery_plan(target)` | Queries Neo4j + Qdrant to produce a step-by-step DR playbook |
| `check_drift()` | Compares Terraform state files vs. current Neo4j graph |
| `get_simulation_timeline(simulation_id, query_at_time_ms)` | Query Redis-cached simulation — returns nodes active at time T (milliseconds) |
| `analyze_cascading_failure(simulation_id, time_ms)` | RTO/RPO metrics and affected node count at a specific point in the cascade |

### Timeline-Aware Simulation

The `simulate_disaster` tool now returns cascading failure timelines with millisecond-precision step times. External agents can then query the cached simulation at any point in time:

**Example: Agent-Driven Analysis**

1. **Run simulation** → get `simulation_id`
   ```bash
   # MCP Tool: simulate_disaster(node_id="db-001", depth=5)
   # Returns: simulation_id="sim_0", timeline_steps with step_time_ms
   ```

2. **Query state at 2500ms** → see which nodes have failed
   ```bash
   # MCP Tool: get_simulation_timeline(simulation_id="sim_0", query_at_time_ms=2500)
   # Returns: 2 nodes active (origin + distance-1)
   ```

3. **Analyze impact at 5000ms** → RTO/RPO for full cascade
   ```bash
   # MCP Tool: analyze_cascading_failure(simulation_id="sim_0", time_ms=5000)
   # Returns: max_distance, worst_case_rto, worst_case_rpo, affected_node_ids
   ```

This enables agents to step through failures at granular time points, extract SLA impact metrics, and generate recovery runbooks.

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
│   ├── main.py                 # FastAPI entry point + global error handler
│   ├── settings.py             # Pydantic settings (Redis, rate limits, Claude API)
│   ├── observability.py        # Prometheus metrics (simulation_latency, affected_nodes_histogram)
│   ├── api/                    # REST endpoints
│   │   ├── dependencies.py     # Rate limiting, optional API key auth
│   │   ├── graph.py            # Graph CRUD
│   │   ├── metrics.py          # VictoriaMetrics proxy
│   │   ├── dr.py               # DR simulate / reset / drift / playbook
│   │   ├── compliance.py       # SLA compliance audit
│   │   ├── whatif.py           # What-if analysis
│   │   └── chaos.py            # Chaos engineering experiments
│   ├── algorithms/             # Core DR intelligence
│   │   ├── eisenhower_classifier.py  # Urgency×Importance quadrant + escalation timer
│   │   ├── cascading_failure.py      # BFS with latency accumulation
│   │   ├── rto_rpo_calculator.py     # Effective RTO/RPO + monitoring state impact
│   │   ├── cost_estimator.py         # Hourly + recovery cost by node type/region
│   │   ├── playbook_generator.py     # Claude API LLM playbook (fallback: static)
│   │   └── region_latency.py         # Cross-region latency matrix
│   ├── db/                     # Database clients
│   │   ├── neo4j_client.py     # Neo4j Bolt client + indices (type, region, status, recovery_strategy, monitoring_state)
│   │   ├── simulation_cache.py # Redis/memory simulation cache (TTL-based)
│   │   ├── victoriametrics_client.py
│   │   └── qdrant_client.py
│   ├── models/                 # Pydantic schemas
│   │   ├── graph.py            # AffectedNode, DisasterSimulationResult
│   │   ├── enhanced_graph.py   # EnhancedAffectedNode, EnhancedSimulationWithTimeline (with eisenhower_quadrant)
│   │   ├── features.py         # RecoveryPlaybook, compliance, chaos, postmortem
│   │   └── errors.py           # Unified ErrorResponse schema
│   ├── parsers/                # 4-phase ingestion
│   │   ├── infra.py            # Phase 1: Terraform → Neo4j
│   │   ├── code.py             # Phase 2: AST → function links
│   │   └── docs.py             # Phase 3: Markdown → Qdrant (with embedding cache)
│   ├── tests/                  # pytest test suite (~90 tests)
│   │   ├── test_eisenhower.py
│   │   ├── test_enhanced_simulation.py
│   │   ├── test_timeline_simulation.py
│   │   └── ...
│   └── mcp_server/
│       └── app.py              # MCP tool server (simulate_disaster, get_recovery_plan, check_drift, timeline tools)
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── nginx.conf
│   ├── README.md                        # Frontend documentation
│   └── src/
│       ├── App.jsx                      # Main layout: 3-column + timeline + report
│       ├── api/client.js
│       ├── hooks/
│       │   ├── useSimulationPlayback.js # Timeline animation loop
│       │   └── useNodeMetrics.js        # Seeded deterministic mock metrics per node
│       ├── utils/
│       │   └── mapLayout.js             # Tiered layout algorithm for node positioning
│       └── components/
│           ├── TopologyViewer.jsx       # Left panel: Infrastructure node browser (React.memo)
│           ├── InfrastructureMap.jsx    # Center panel: 2D tiered visualization + animations (React.memo)
│           ├── MetricsDashboard.jsx     # Right panel: Per-node observability metrics + sparklines (React.memo)
│           ├── DisasterPanel.jsx        # Controls: Depth input + Simulate/Reset buttons
│           ├── SimulationTimeline.jsx   # Timeline playback: play/pause/speed/progress
│           ├── SimulationReport.jsx     # 7-section report: summary, Eisenhower matrix+chart, impact table, timeline, RCA, mitigation, playbook
│           ├── ComplianceDashboard.jsx  # SLA compliance audit UI
│           ├── ArchitecturePlanner.jsx  # What-if analysis UI
│           ├── ChaosDashboard.jsx       # Chaos engineering UI
│           ├── PostmortemView.jsx       # Postmortem analysis UI
│           ├── PlaybookPanel.jsx        # LLM recovery playbook viewer
│           └── SimulationComparison.jsx # Baseline vs. proposed topology comparison
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
| `REDIS_URL` | `redis://redis:6379` | Redis URL for simulation cache |
| `SIMULATION_CACHE_TTL_SECONDS` | `3600` | Simulation cache TTL (1 hour) |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama on host machine |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `VITE_API_URL` | `http://localhost:8001` | API URL for browser → backend calls |
| `DR_RTO_SECONDS` | `300` | Recovery Time Objective threshold |
| `DR_RPO_SECONDS` | `60` | Recovery Point Objective threshold |
| `API_SECRET_KEY` | _(unset)_ | Optional API key for endpoint auth — if unset, auth is disabled |
| `ANTHROPIC_API_KEY` | _(unset)_ | Claude API key for LLM-powered playbook generation |
| `RATE_LIMIT_PER_MINUTE` | `60` | Global request rate limit per IP |

---

## 🩺 Health Checks

```bash
# All containers healthy?
docker compose ps

# Backend API
curl http://localhost:8001/health

# Neo4j
curl http://localhost:7474

# VictoriaMetrics
curl http://localhost:8428/health

# Qdrant
curl http://localhost:6333/healthz
```

---

## ⚠️ Known Issues — Port Conflicts (Windows)

On Windows with **Docker Desktop** and **Zscaler ZSATunnel**, the default ports clash:

| Default Port | Conflict                          | Remapped Host Port |
|--------------|-----------------------------------|--------------------|
| 3000         | `com.docker.backend` / `wslrelay` | **3001**           |
| 8000         | `com.docker.backend`              | **8001**           |
| 9000         | Zscaler ZSATunnel                 | **9001**           |

The `docker-compose.yml` already uses the remapped ports above.  
All internal container-to-container communication is unaffected (uses original ports inside the Docker network).

---

## 🛑 Stop & Clean Up

```bash
# Stop all containers (keep data volumes)
docker compose down

# Stop and remove all volumes (destructive — wipes graph + metrics + vectors)
docker compose down -v
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [FEATURES.md](./docs/FEATURES.md) | Detailed workflows for Compliance, What-If, Chaos, Postmortem |
| [changelog-session-2026-05-17-18.html](./docs/changelog-session-2026-05-17-18.html) | Full session changelog (17–18 May 2026) with Eisenhower algorithm explanation |
| [eisenhower-dr-simulation.html](./docs/eisenhower-dr-simulation.html) | Eisenhower DR classifier design specification |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-improvement`
3. Commit with descriptive messages
4. Open a Pull Request

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
