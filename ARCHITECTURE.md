# 🏗️ AI Digital Twin — Disaster Recovery Platform

## Documento Architetturale

**Versione:** 1.0  
**Data:** Aprile 2026  
**Autore:** Digital Twin DR Team

---

## 📋 Indice

1. [Visione d'Insieme](#visione-dinsieme)
2. [Cos'è Questo Sistema](#cosè-questo-sistema)
3. [Come Funziona](#come-funziona)
4. [Architettura Tecnica](#architettura-tecnica)
5. [Componenti Principali](#componenti-principali)
6. [Flussi Dati](#flussi-dati)
7. [Guida all'Utilizzo](#guida-allutilizzo)
8. [Casi d'Uso Reali](#casi-duso-reali)
9. [Scalabilità e Performance](#scalabilità-e-performance)

---

## Visione d'Insieme

L'**AI Digital Twin — Disaster Recovery Platform** è una soluzione integrata che permette ai team di infrastruttura di:

✅ **Mappare** l'intera infrastruttura cloud (AWS, Azure, etc.) in tempo reale da Terraform  
✅ **Simulare** guasti cascanti in millisecondi con precisione temporale  
✅ **Visualizzare** il propagarsi dei disastri con animazioni immersive in 2D  
✅ **Analizzare** l'impatto su RTO/RPO per ogni componente  
✅ **Generare** playbook di recovery automatici con raccomandazioni architetturali  
✅ **Testare** strategie DR senza toccare la produzione

**Target Users:**
- DevOps/SRE engineers
- Disaster Recovery planners
- Infrastructure architects
- Compliance & governance teams

---

## Cos'è Questo Sistema

### Definizione Estesa

Un **Digital Twin** è una replica virtuale dell'infrastruttura reale. Questo sistema crea un twin dinamico basato su:

1. **Terraform State** — la sorgente di verità dell'infrastruttura (risorse, dipendenze)
2. **Neo4j Graph Database** — storage delle relazioni topologiche
3. **Code AST Analysis** — link tra funzioni applicative e risorse infra
4. **Architecture Documentation** — conoscenza semantica tramite embeddings vettoriali
5. **Live Metrics** — salute in real-time da VictoriaMetrics

### Problema che Risolve

**Scenario Tipico:**

> Una database primaria si guasta. Cosa succede?
> - Quali applicazioni ne soffrono?
> - Quando diventeranno non disponibili?
> - Quali componenti cascheranno?
> - Quanto ci metterà a recuperarsi?
> - Come lo ricuperamo?

**Risposta Tradizionale:** Manuale, lenta, incompleta.  
**Risposta di questo sistema:** Automatica, in millisecondi, con visualizzazione animata e playbook generato.

---

## Come Funziona

### Fase 1: Ingestion (Mappatura)

```
┌─────────────────────┐
│  Terraform Files    │
│  (HCL → JSON)       │
└──────────┬──────────┘
           │ Phase 1 Parser
           ▼
┌─────────────────────────────────┐
│  Neo4j Graph Database           │
│  (:Node {type, region, az, ...})│
│  -[:DEPENDS_ON]->               │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Code AST Analysis              │
│  Python/JS → function links      │
│  :Function -[:CALLS]-> :Node    │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Documentation Embeddings        │
│  Markdown → Qdrant vectors       │
│  Semantic search for recovery    │
└─────────────────────────────────┘
```

**Risultato:** Una rappresentazione completa della tua infrastruttura come grafo orientato.

### Fase 2: Simulazione Disastri

Quando l'utente clicca **"Simulate"** su un nodo:

```
1. API riceve: node_id = "db-001", depth = 5
   │
2. Backend esegue BFS (breadth-first search)
   │   • db-001 fallisce al tempo T+0ms
   │   • Tutti i nodi dipendenti si attivano
   │   • Per ogni edge: calcola delay (tipo di edge, distanza)
   │
3. Timeline Building
   │   • Node A fallisce → T+0ms
   │   • Node B (distanza 1) fallisce → T+2500ms
   │   • Node C (distanza 2) fallisce → T+4200ms
   │   • (delays = 600ms * distanza + jitter)
   │
4. RTO/RPO Calculation
   │   • Per ogni nodo: stima recovery time (tipo + config)
   │   • Max RTO = worst case across all nodes
   │   │
▼ Response inviato al Frontend
{
  "blast_radius": [...],
  "timeline_steps": [
    {"node_id": "db-001", "step_time_ms": 0, "distance": 0},
    {"node_id": "app-001", "step_time_ms": 2500, "distance": 1},
    {"node_id": "cache-001", "step_time_ms": 4200, "distance": 2}
  ],
  "total_duration_ms": 5000,
  "worst_case_rto_minutes": 15
}
```

### Fase 3: Visualizzazione e Timeline

Il frontend riceve la simulazione e:

1. **Posiziona i nodi** con algoritmo tiered layout (O(n)):
   - Tier 0: Load balancers
   - Tier 1: Compute (EC2, Lambda, ECS)
   - Tier 2: Data (Database, Cache)
   - Tier 3: Storage (S3)

2. **Inizia il playback** della timeline con animazioni sincronizzate:
   ```
   T+0ms:     db-001 si colora di rosso (failure)
   T+600ms:   app-001 inizia a brillare (activating state)
   T+2500ms:  app-001 diventa rosso (failed)
   T+4200ms:  cache-001 diventa rosso
   T+5000ms:  Fine simulazione, report generato
   ```

3. **Genera il Report** con 5 sezioni:
   - Executive Summary
   - Impact Table (tutti i nodi affetti)
   - Timeline of Events
   - Root Cause Analysis
   - Mitigation & Architecture Recommendations

### Fase 4: Recovery Planning

Basato su:
- **Recovery Steps** generati dalla simulazione (backend)
- **Architecture Recommendations** dal frontend (type-specific, type: aws_rds_cluster → "Enable Global Database")
- **Best Practices** hardcoded (circuit breakers, health checks, etc.)

---

## Architettura Tecnica

### Diagramma a Blocchi Completo

```
┌────────────────────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE LAYER (Docker Compose)                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐ │
│  │   FRONTEND (Node.js)     │    │      BACKEND (Python/FastAPI)        │ │
│  │   :3001                  │    │      :8001 (REST), :9001 (MCP)       │ │
│  ├──────────────────────────┤    ├──────────────────────────────────────┤ │
│  │ • React + Vite           │    │ • FastAPI framework                  │ │
│  │ • Tailwind CSS           │    │ • Neo4j driver                       │ │
│  │ • SVG animations         │    │ • VictoriaMetrics client             │ │
│  │ • Timeline playback      │    │ • Qdrant client                      │ │
│  └──────────────────────────┘    │ • MCP Server (stdio)                 │ │
│                                  │ • Parsers (4 phases)                 │ │
│                                  └──────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐ │
│  │  NEO4J GRAPH DATABASE    │    │  VICTORIAMETRICS (Time-Series)       │ │
│  │  :7474, :7687            │    │  :8428                               │ │
│  ├──────────────────────────┤    ├──────────────────────────────────────┤ │
│  │ • Nodes: Infrastructure  │    │ • Live metrics scraping              │ │
│  │ • Edges: Dependencies    │    │ • Health status per node             │ │
│  │ • Properties: type,      │    │ • Storage: 30 giorni                 │ │
│  │   region, AZ, RTO/RPO    │    │ • Query engine (MetricsQL)           │ │
│  └──────────────────────────┘    └──────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐ │
│  │  QDRANT VECTOR DATABASE  │    │  OLLAMA (Embeddings)                 │ │
│  │  :6333, :6334            │    │  :11434 (Host Process)               │ │
│  ├──────────────────────────┤    ├──────────────────────────────────────┤ │
│  │ • Markdown docs parsed   │    │ • nomic-embed-text model             │ │
│  │ • Semantic search        │    │ • 768-dimensional embeddings         │ │
│  │ • RAG for recovery steps │    │ • Generates recovery context         │ │
│  └──────────────────────────┘    └──────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
            │  Your AWS    │ │  Your Azure  │ │  Your GCP    │
            │ Infrastructure│ │ Infrastructure│ │ Infrastructure│
            │ (via Terraform)│ │ (via Terraform)│ │ (via Terraform)│
            └──────────────┘ └──────────────┘ └──────────────┘
```

### Stack Tecnologico

| Layer | Tecnologia | Ruolo |
|-------|-----------|-------|
| **Frontend** | React 18 + Vite + Tailwind CSS | UI/UX per simulazione e visualizzazione |
| **Backend** | FastAPI + Python 3.12 | REST API, logica di simulazione, MCP server |
| **Graph DB** | Neo4j 5.18 | Topologia infrastruttura e relazioni |
| **Time-Series DB** | VictoriaMetrics 1.101 | Metriche live e storiche |
| **Vector DB** | Qdrant 1.9.2 | Embeddings semantici per recovery docs |
| **Embedding Model** | Ollama + nomic-embed-text | Generazione embeddings 768-dim |
| **Orchestration** | Docker Compose v2 | Gestione lifecycle 6 container |

---

## Componenti Principali

### 1. Frontend — React Dashboard

**Struttura:**

```
src/
├── App.jsx                    # Layout principale 3-colonne
│   ├── Colonna A: TopologyViewer
│   ├── Colonna B: InfrastructureMap (SVG 2D)
│   └── Colonna C: MetricsDashboard
│   ├── Riga 3: DisasterPanel (controls)
│   ├── Riga 4: SimulationTimeline (conditional)
│   └── Riga 5: SimulationReport (conditional)
│
├── components/
│   ├── TopologyViewer.jsx       # Left sidebar: node browser
│   ├── InfrastructureMap.jsx    # Center: 2D visualization + animations
│   ├── MetricsDashboard.jsx     # Right sidebar: per-node metrics
│   ├── DisasterPanel.jsx        # Simulation controls
│   ├── SimulationTimeline.jsx   # Timeline playback UI
│   └── SimulationReport.jsx     # 5-section report accordion
│
├── hooks/
│   ├── useSimulationPlayback.js # rAF-based animation loop
│   └── useNodeMetrics.js        # Seeded deterministic mock metrics
│
├── utils/
│   └── mapLayout.js             # Tiered layout algorithm
│
└── api/
    └── client.js                # fetch wrapper for /api/* endpoints
```

**Responsabilità:**
- Riceve topology da `/api/topology`
- Invia simulazione a `/api/dr/simulate`
- Riceve timeline completa con step_time_ms
- Sincronizza simulationTime con animazioni CSS
- Genera report automaticamente quando playback finisce

### 2. Backend — FastAPI

**Endpoints Principali:**

```python
GET /api/topology
  → Restituisce InfraGraph (nodes + edges da Neo4j)

POST /api/dr/simulate
  {
    "node_id": "db-001",
    "depth": 5
  }
  → Restituisce SimulationWithTimeline

GET /api/metrics/health/:node_id
  → Status e health metrics da VictoriaMetrics

GET /api/recovery/:simulation_id
  → Recovery steps da RAG (Qdrant + LLM)
```

**Logica di Simulazione (Pseudo-codice):**

```python
def simulate_disaster(node_id, depth, graph_db):
    # 1. BFS per trovare tutti i nodi nel blast radius
    queue = deque([(node_id, 0)])
    visited = set([node_id])
    blast_radius = []
    timeline_steps = []
    
    while queue:
        current_id, distance = queue.popleft()
        
        if distance > depth:
            continue
        
        current_node = graph_db.get_node(current_id)
        step_time_ms = calculate_step_time(distance, current_node)
        
        blast_radius.append({
            "id": current_id,
            "distance": distance,
            "step_time_ms": step_time_ms,
            "estimated_rto_minutes": estimate_rto(current_node),
            "estimated_rpo_minutes": estimate_rpo(current_node)
        })
        
        timeline_steps.append({
            "node_id": current_id,
            "distance": distance,
            "step_time_ms": step_time_ms
        })
        
        # 2. Aggiungi dipendenti alla queue
        for dependent in graph_db.get_dependents(current_id):
            if dependent not in visited:
                visited.add(dependent)
                queue.append((dependent, distance + 1))
    
    # 3. Calcola metriche aggregate
    worst_rto = max(node["estimated_rto_minutes"] for node in blast_radius)
    max_distance = max(node["distance"] for node in blast_radius)
    total_duration_ms = calculate_total_duration(timeline_steps)
    
    return {
        "origin_node_id": node_id,
        "blast_radius": blast_radius,
        "timeline_steps": timeline_steps,
        "max_distance": max_distance,
        "total_duration_ms": total_duration_ms,
        "worst_case_rto_minutes": worst_rto,
        "recovery_steps": generate_recovery_steps(blast_radius)
    }
```

### 3. Neo4j Graph Database

**Schema:**

```cypher
// Nodo
CREATE (n:Node {
  id: "db-001",
  name: "Primary Database",
  type: "aws_rds_cluster",
  region: "us-east-1",
  az: "us-east-1a",
  status: "healthy",
  rto_minutes: 15,
  rpo_minutes: 1,
  is_redundant: true
})

// Relazione di dipendenza
(appServer)-[:DEPENDS_ON]->(database)

// Esempio di grafo:
//
//     lb-001 (LB)
//        │
//        ├─> app-001 (EC2)
//        │      │
//        │      └─> db-001 (RDS) ◄─────────┐
//        │                                  │
//        └─> app-002 (EC2)                  │
//               │                           │
//               └─> cache-001 (ElastiCache)─┘
```

**Indici:**
- `n:Node(id)` — lookup veloce per nodo
- `(n)-[:DEPENDS_ON]->(m)` — traversal efficiente

### 4. VictoriaMetrics

**Ruolo:**
- Scrape Prometheus metrics (se presenti)
- Storage metriche storiche
- Endpoint query per health status
- Visualizzazione metriche nel MetricsDashboard

**Metriche Simulabili:**
```
node_cpu_seconds_total
node_memory_MemAvailable_bytes
http_requests_total
http_request_duration_seconds
application_errors_total
replication_lag_seconds
```

### 5. Qdrant Vector Database

**Uso:**
1. **Ingest:** Docs Markdown → embeddings 768-dim
2. **Search:** Query similari per step di recovery
3. **RAG:** Context retrieval per recovery playbook generation

**Esempio:**
```
Docs: "For RDS failover, first trigger automated backup..."
    ↓
Embedding: [0.234, -0.512, 0.089, ..., 0.156]
    ↓
Stored in Qdrant
    ↓
Query: "How to recover from database failure?"
    ↓
Top-3 similar docs retrieved
    ↓
Passed to LLM for recovery step generation
```

---

## Flussi Dati

### Flusso 1: Mappatura Infrastruttura (Una tantum)

```
┌─────────────────────┐
│  terraform.tfstate  │  Sorgente di verità: AWS/Azure resources
└──────────┬──────────┘
           │ HTTP POST /api/parse/terraform
           ▼
┌─────────────────────────────────────┐
│  Backend: TerraformParser (Phase 1) │  Legge HCL/JSON, estrae risorse
└──────────┬────────────────────────┬─┘
           │                        │
           ▼                        ▼
    ┌─────────────┐         ┌──────────────┐
    │   Neo4j     │         │ VictoriaM.   │  Store metriche
    │ CREATE Node │         │ Scrape config│
    │ CREATE Edge │         └──────────────┘
    └─────────────┘
```

### Flusso 2: Simulazione Disastri (On-Demand)

```
┌──────────────────────────┐
│ User clicks "Simulate"   │  Frontend: selected node
│ node_id="db-001"         │
└──────────┬───────────────┘
           │ POST /api/dr/simulate
           ▼
┌──────────────────────────────────┐
│  Backend: Disaster Simulator    │
│  • BFS traverse Neo4j graph      │
│  • Calculate step_time_ms        │
│  • Estimate RTO/RPO              │
└──────────┬───────────────────────┘
           │ Return SimulationWithTimeline
           ▼
┌──────────────────────────────┐
│  Frontend: Store in State    │
│  simulationResult = {        │
│    blast_radius: [...],      │
│    timeline_steps: [...],    │
│    total_duration_ms: 5000   │
│  }                           │
└──────────┬───────────────────┘
           │
           ▼
┌───────────────────────────────────┐
│  Frontend: Initialize Playback    │
│  • simulationTime = 0             │
│  • Start rAF loop                 │
│  • Sync CSS animations            │
│  • Update node classes:           │
│    - node-activating (600ms)      │
│    - node-failed (600ms+)         │
│    - node-healthy (entire cast)   │
└───────────────────────────────────┘
```

### Flusso 3: Visualizzazione Animata

```
┌─────────────────────────────────┐
│  simulationTime updates (rAF)   │  Every ~16.67ms (60fps)
│  0ms → 5000ms                   │
└────────┬──────────────────────┬─┘
         │                      │
         ▼                      ▼
    ┌─────────────────┐   ┌──────────────────┐
    │  Update State   │   │  Re-render SVG   │
    │  setSimTime(ms) │   │  Derived classes │
    └────────┬────────┘   └────────┬─────────┘
             │                     │
             ▼                     ▼
    ┌──────────────────────────────────────┐
    │  Derived State (useMemo)             │
    │  • activatingIds ← nodes in          │
    │    [step_time_ms, step_time_ms+600)  │
    │  • failedIds ← nodes where           │
    │    simulationTime >= step_time_ms+600│
    │  • blastIds ← all in blast_radius    │
    └────────┬─────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────┐
    │  CSS Classes Applied                 │
    │  node-activating → pulse-glow 0.8s   │
    │  node-failed → pulse-failed 1.5s     │
    │  node-healthy → pulse-healthy 2s     │
    │  edge-flow → flow-animation 1.5s     │
    │  hop-ring → hop-ring 2s              │
    └──────────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────┐
    │  SVG Renders with Animations         │
    │  Nodes glow, edges flow, rings ripple│
    │  All synchronized with simulationTime│
    └──────────────────────────────────────┘
```

### Flusso 4: Report Generation

```
┌─────────────────────────────────────┐
│  Playback Complete                  │
│  simulationTime >= total_duration_ms│
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  isSimulationDone = true            │
│  (computed in App.jsx)              │
└────────┬────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Render <SimulationReport />         │
│  5 sections:                         │
│  1. Executive Summary                │
│  2. Impact Table                     │
│  3. Timeline of Events               │
│  4. Root Cause Analysis              │
│  5. Mitigation + Recommendations     │
└──────────────────────────────────────┘
```

---

## Guida all'Utilizzo

### Setup Iniziale (5 minuti)

#### Prerequisiti

- Docker Desktop ≥ 4.25 con WSL2 (Windows)
- Ollama scaricato e avviato
- Git clonato il repo

#### 1. Scarica il Modello Ollama

```bash
ollama pull nomic-embed-text
```

#### 2. Avvia l'Infrastruttura

**Windows (PowerShell):**
```powershell
cd ai-digital-twin-dr
.\scripts\start.ps1
```

**Linux/macOS:**
```bash
cd ai-digital-twin-dr
bash scripts/start.sh
```

**Attendi:** Tutti i container diventano `healthy` (1-2 minuti)

#### 3. Ingestione Dati

```powershell
# Windows
.\scripts\ingest.ps1

# Linux/macOS
bash scripts/ingest.sh
```

Questo popola Neo4j con la topologia Terraform di sample.

#### 4. Accedi al Dashboard

```
http://localhost:3001
```

### Workflow Tipico di Simulazione (3 minuti)

#### Passo 1: Seleziona un Nodo

1. Guarda il **Topology Viewer** (pannello sinistro)
2. Clicca su qualsiasi nodo infrastrutturale (es. "Primary Database")
3. Il nodo si evidenzia con un bordo celeste
4. Il **Metrics Dashboard** (destra) si popola con i dati del nodo

#### Passo 2: Configura la Simulazione

1. Nel **Disaster Panel** (in basso), modifica il campo **Depth** (default: 5)
   - 1-3: Simulazione breve (focalizzata)
   - 5-7: Simulazione standard
   - 8-10: Simulazione completa (tutti i dipendenti)

2. Clicca il pulsante rosso **"Simulate"**

#### Passo 3: Guarda la Cascata

1. Il **SimulationTimeline** appare con:
   - Progress bar (0% → 100%)
   - Play/Pause/Rewind buttons
   - Speed slider

2. L'**Infrastructure Map** (centro) si anima:
   - Nodo origine diventa rosso
   - I nodi dipendenti "brillano" in sequenza
   - Gli edge si illuminano con flusso animato
   - Anelli concentrici pulsano dal nodo origine

3. **Flusso temporale:**
   ```
   T+0ms:     Nodo origine fallisce → rosso intenso
   T+600ms:   Primo dipendente inizia a brillare
   T+2500ms:  Primo dipendente diventa rosso
   T+4200ms:  Secondo dipendente diventa rosso
   T+5000ms:  Fine simulazione
   ```

#### Passo 4: Analizza il Report

1. Quando la timeline termina, **SimulationReport** appare in basso:

   **📊 Executive Summary**
   - Nodo origine e tipo di failure
   - Numero nodi affetti
   - Max propagation depth
   - Worst RTO/RPO

   **📋 Impact Table**
   - Ogni nodo affetto con distanza, tipo, RTO, RPO

   **⏱️ Timeline of Events**
   - T+0ms: db-001 fallisce
   - T+2500ms: app-001 fallisce
   - T+4200ms: cache-001 fallisce

   **🔍 Root Cause Analysis**
   - Descrizione tipo di failure (es. "RDS cluster lost quorum...")

   **🛡️ Mitigation Actions**
   - Recovery steps dal backend
   - Arch recommendations (Multi-AZ, Global Database, etc.)
   - Best practices (health checks, circuit breakers, etc.)

#### Passo 5: Reset o Nuova Simulazione

1. Clicca **"Reset"** per azzerare
2. Oppure seleziona un altro nodo e clicca **"Simulate"** di nuovo

### Scenario Reale: Recovery Planning

#### Caso: Database Failure

```
Seleziono: Primary Database (aws_rds_cluster)
Depth: 5
Simulo...

RISULTATO:
- Blast Radius: 12 nodi affetti
- Max Distance: 3 hops
- Timeline: 5000ms cascata
- Worst RTO: 15 minuti
- Worst RPO: 2 minuti

RACCOMANDAZIONI:
✓ Abilita Global Database per cross-region recovery (RPO < 1s)
✓ Configura Aurora Auto Scaling per failover readers
✓ Implementa connection pooling (PgBouncer)
✓ Set RTO target in DR runbook

RECOVERY STEPS:
1. Trigger automated failover to read replica
2. Update DNS to point to standby database
3. Restart application servers
4. Verify health checks pass
5. Run smoke tests
```

#### Caso: Load Balancer Failure

```
Seleziono: Primary LB (aws_lb)
Depth: 3
Simulo...

RISULTATO:
- Blast Radius: 8 nodi affetti
- Max Distance: 2 hops
- Timeline: 3000ms cascata
- Worst RTO: 5 minuti
- Worst RPO: 0 minuti (stateless)

RACCOMANDAZIONI:
✓ Abilita cross-zone load balancing
✓ Configura AWS WAF + Shield Standard
✓ Health check interval: 10s, unhealthy threshold: 2
✓ Connection draining timeout: 60s

RECOVERY STEPS:
1. Alert on LB unhealthy status
2. Auto-provision replacement LB
3. Attach remaining backends
4. Update Route53 DNS records
5. Verify traffic distribution
```

---

## Casi d'Uso Reali

### 1. **Compliance & Testing (Trimestrale)**

**Scenario:** Audit annuale richiede DR test senza produzione.

```
Azioni:
1. Apri dashboard DR
2. Seleziona ogni nodo critico (database, LB, API server)
3. Simula cascata per depth=5
4. Documenta RTO/RPO per ogni componente
5. Esporta report dettagliato

Output:
- Recovery plan per ogni failure mode
- SLA gaps identificati
- Architecture recommendations
- Evidence di compliance testing
```

### 2. **Architecture Planning (Pre-deployment)**

**Scenario:** Team vuole aggiungere nuova app, ma quale infra è necessaria?

```
Azioni:
1. Aggiungi nuova app a Terraform
2. Ingestione automatica nel Digital Twin
3. Simula failure scenarios
4. Rivedi RTO/RPO vs. requirements
5. Itera architettura

Esempio:
- Nuova payment API connessa a master database
- Simulazione mostra: RTO 30 min (requirement: 5 min)
- Raccomandata: Add read replica + caching
- Re-simula: RTO scende a 5 min ✓
- Deployment approved
```

### 3. **Incident Postmortem (Post-outage)**

**Scenario:** Production issue occurred. Team vuole capire cosa sarebbe accaduto se...

```
Azioni:
1. Identifica nodo che fallisce (es. "cache-prod-001")
2. Simula cascata con depth=5
3. Confronta con incident reale:
   - Simulation timeline vs. actual events
   - Affected systems match?
   - RTO/RPO prediction accuracy?

Output:
- Validation: Did simulation predict actual outage?
- If yes: Simulation is trustworthy for future planning
- If no: Investigate graph assumptions
- Document lessons learned
```

### 4. **Chaos Engineering Integration**

**Scenario:** Team esegue chaos test. DR platform fornisce prediction vs. reality.

```
Scenario di Test:
1. Injectare fault: Terminate RDS instance
2. Apri DR dashboard
3. Simula same node failure
4. Confronta:
   - Predicted timeline vs. actual metrics
   - Predicted RTO vs. actual recovery time
   - Accuracy score

Benefit:
- Validate assumptions in graph
- Identify if actual system is more resilient
- Or LESS resilient (yikes!)
- Iterate and improve
```

---

## Scalabilità e Performance

### Limiti Attuali (Test Environment)

| Metrica | Valore | Bottleneck |
|---------|--------|-----------|
| Nodi Graph | 10,000+ | Neo4j memory |
| Simulazione (depth=5) | <500ms | BFS traverse |
| Rendering nodi (SVG) | <1000 nodes | Browser rendering |
| Timeline playback | 5000ms | rAF loop |

### Optimizzazioni Implementate

1. **useMemo Hooks** — Derived state (activatingIds, failedIds) non ricalcola se simulationTime non cambia
2. **SVG Optimization** — viewBox preserveAspectRatio xMidYMid meet, no viewport rescale
3. **CSS Keyframes** — Inline nella `<defs>`, non JavaScript animation
4. **Tiered Layout** — O(n) algorithm, no force-directed complexity
5. **Neo4j Indexing** — Index su node.id per lookup O(1)

### Scaling Recommendations

**Se topology > 10,000 nodes:**
1. Implementa node clustering visualization (aggregate nodes per AZ)
2. Lazy-load edges (mostra solo path da origin a blast radius)
3. Pagination per report (impact table > 100 rows)
4. Cache simulazioni su backend (LRU cache)

**Se timeline > 10,000 events:**
1. Temporal binning (aggregate events per 100ms)
2. Virtual scrolling per timeline list
3. Downsample metrics sparklines

---

## Supporto e Troubleshooting

### Container non parte

```bash
# Diagnosi
docker compose logs backend
docker compose logs neo4j

# Fix: Pulisci volumi e riavvia
docker compose down -v
docker compose up -d
```

### Simulazione restituisce 0 nodi blast_radius

```
Causa: Nodo non ha dipendenti nel grafo
Soluzione:
1. Verifica Neo4j: http://localhost:7474
2. Esegui: MATCH (n:Node)-[r]->(m) RETURN count(r)
3. Se = 0: Esegui ingestione di nuovo
   .\scripts\ingest.ps1
```

### Frontend non si connette a backend

```bash
# Verifica API è up
curl http://localhost:8001/health

# Controlla VITE_API_URL in .env
cat .env | grep VITE_API_URL

# Reinizializza frontend
docker compose down frontend
docker compose up frontend -d
```

---

## Conclusione

Questa piattaforma trasforma il Disaster Recovery da **preventivo e carta** a **simulato e visuale**.

Con il Digital Twin puoi:
- ✅ Testare senza toccare produzione
- ✅ Identificare SLA gaps prima dell'incident
- ✅ Educate team su cascate di failure
- ✅ Generare automated recovery playbooks
- ✅ Dimostrare compliance con regolatori

**Prossimi step:**
1. Popola il tuo Terraform nel Digital Twin
2. Esegui simulazioni sugli scenari critici
3. Itera architettura basato su RTO/RPO
4. Integra con incident management tool
5. Automatizza DR testing mensile
