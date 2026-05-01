# Design: Accurate Cascading Failure Model (MVP)

**Date:** 2026-04-24  
**Status:** Ready for Implementation  
**Approach:** Phase 1 (MVP) → Phase 2 (Probabilistic) → Phase 3 (Event-Driven)

---

## Problem Statement

Current simulation model uses **linear timing** (distance × total_duration / max_distance) and **static RTO/RPO**, which don't reflect reality:

1. **Timing of Propagation** — Failures propagate at different speeds depending on edge type (DB replication = 500-1000ms/hop, API calls = 50-100ms/hop), not linearly
2. **RTO/RPO Estimation** — RTO/RPO are static per-node, but should be **dynamic** based on recovery strategy and whether dependencies are healthy
3. **Dependency Completeness** — Graph lacks implicit dependencies (timeouts between services, resource contention, monitoring state drift, data consistency windows, cross-region latency)

This design introduces a **realistic propagation model (MVP)** with roadmap for probabilistic and event-driven extensions.

---

## Goals (MVP)

✅ **Realistic timing** — Edge-type-specific latency (REPLICATES_TO, CALLS, ROUTES_TO, USES, SHARES_RESOURCE, TIMEOUT_CALLS)  
✅ **Dynamic RTO/RPO** — Recovery strategy + dependency health context  
✅ **Monitoring integration** — Incorporate Dynatrace/Prometheus degradation state  
✅ **Dependency inference** — Parser extracts recovery_strategy + edge types from Terraform  
✅ **Scalable** — Design supports Phase 2 (probabilistic jitter) and Phase 3 (event-driven)

---

## 1. Neo4j Schema Extension

### InfraNode Properties

```
{
  // Existing
  id: string (unique)
  name: string
  type: string (aws_rds_cluster, aws_instance, etc.)
  region: string
  rto_minutes: number (static estimate)
  rpo_minutes: number (static estimate)
  status: "healthy" | "degraded" | "failed" | "simulated_failure"
  is_redundant: boolean
  
  // NEW: Recovery Strategy
  recovery_strategy: "replica_fallback" | "backup_fallback" | "multi_az" | "stateless" | "generic"
  recovery_rules: {
    "replica_edge": string (edge type to follow for replica, e.g., "REPLICATES_TO")
    "backup_edge": string (fallback edge type, e.g., "BACKED_UP_BY")
    "fallback_rto_multiplier": number (RTO multiplier if fallback, e.g., 2.0)
    "circuit_breaker_threshold_seconds": number (optional, for future)
  }
  
  // NEW: Monitoring State
  monitoring_state: "healthy" | "degraded" | "unknown"
  last_monitoring_update: timestamp
  observed_latency_ms: number (from real metrics, can override model defaults)
}
```

### Edge Properties

All edge types (DEPENDS_ON, REPLICATES_TO, CALLS, ROUTES_TO, USES, SHARES_RESOURCE, TIMEOUT_CALLS) support:

```
{
  // Existing
  type: string
  
  // NEW: Latency Modeling
  latency_ms: number (default per edge type, can be overridden per edge)
  latency_type: "static" | "variable"
  jitter_ms: number (range: [latency_ms - jitter, latency_ms + jitter], for Phase 2)
  
  // NEW: Contention Modeling
  shares_resource: boolean (true if this edge represents resource contention)
  contention_factor: number (latency multiplier when resource is contended, e.g., 1.2)
  
  // NEW: Circuit Breaker (for Phase 2)
  has_circuit_breaker: boolean
  breaker_threshold_seconds: number
  
  // NEW: Data Consistency (for Phase 1 RTO/RPO impact)
  replication_lag_seconds: number (for REPLICATES_TO edges, impacts RPO)
}
```

### Default Latency per Edge Type

| Edge Type | Default Latency (ms) | Description |
|-----------|---------------------|-------------|
| REPLICATES_TO | 1000 | DB cross-region replication |
| CALLS | 100 | Service-to-service API calls |
| ROUTES_TO | 50 | Load balancer routing |
| USES | 500 | Shared resource usage |
| SHARES_RESOURCE | 200 | Resource contention penalty |
| TIMEOUT_CALLS | 1000 | Service calls with timeout (worst case) |
| DEPENDS_ON | 100 | Generic dependency (default) |

---

## 2. Simulation Algorithm (Enhanced BFS)

### Phase 1: BFS with Latency Accumulation

**Input:**
- `origin_node_id`: Node that fails
- `depth`: Max hops
- `include_monitoring`: Boolean to incorporate Dynatrace state

**Algorithm:**

```
queue = [(origin_node, distance=0, accumulated_latency_ms=0)]
affected_nodes = {}
visited = set()

while queue not empty:
  current_node, distance, acc_latency = queue.pop(0)
  
  if distance > depth or current_node.id in visited:
    continue
  
  visited.add(current_node.id)
  
  // Step 1: Record affected node with accumulated latency
  current_node.step_time_ms = acc_latency
  affected_nodes[current_node.id] = current_node
  
  // Step 2: Process outgoing edges
  for edge in current_node.outgoing_edges:
    next_node = edge.target
    
    // Calculate latency for this hop
    base_latency = edge.latency_ms
    
    // Apply contention factor if resource already affected
    if edge.shares_resource and next_node.id in affected_nodes:
      base_latency *= edge.contention_factor
    
    // Accumulate for next hop
    next_latency = acc_latency + base_latency
    
    queue.append((next_node, distance + 1, next_latency))

return affected_nodes
```

**Key Differences from Current:**
- Latency accumulates per hop (not linear interpolation)
- Edge-specific latency_ms (not uniform)
- Contention modeling (shared resources)
- Distance-based ordering preserved for timeline animation

---

### Phase 2: Dynamic RTO/RPO Calculation

For each affected node, calculate `effective_rto_minutes` and `effective_rpo_minutes` based on recovery strategy.

**Strategy: replica_fallback**
```
// Look for REPLICATES_TO edges pointing to replicas
replicas = [dep for dep in node.dependencies 
            if edge_type == "REPLICATES_TO" and dep.id not in affected_nodes]

if replicas exist and all healthy:
  effective_rto = min(replica.rto_minutes for replica in replicas)
else if replicas exist but some degraded:
  effective_rto = node.rto_minutes * 1.5  // degraded fallback
else:
  // No healthy replica, look for backup
  backups = [dep for dep in node.dependencies 
             if edge_type == "BACKED_UP_BY"]
  if backups:
    effective_rto = node.rto_minutes * node.recovery_rules["fallback_rto_multiplier"]
  else:
    // No backup, worst case
    effective_rto = node.rto_minutes * 3.0

// RPO: affected by replication_lag_seconds on REPLICATES_TO edges
replication_edges = [e for e in node.outgoing_edges if e.type == "REPLICATES_TO"]
if replication_edges:
  max_lag_seconds = max(e.replication_lag_seconds for e in replication_edges)
  effective_rpo = node.rpo_minutes + (max_lag_seconds / 60)
else:
  effective_rpo = node.rpo_minutes
```

**Strategy: multi_az**
```
// Multi-AZ failover is fast (~30 seconds per hop)
effective_rto = node.rto_minutes * 0.5  // Fast failover
effective_rpo = node.rpo_minutes  // No data loss
```

**Strategy: stateless**
```
// Stateless nodes can be spun up quickly
effective_rto = node.rto_minutes * 0.5  // Scaling up is faster than DB recovery
effective_rpo = 0  // No data loss
```

**Strategy: generic (default)**
```
// Conservative estimate: use static RTO/RPO
effective_rto = node.rto_minutes
effective_rpo = node.rpo_minutes
```

---

### Phase 3: Incorporate Monitoring State (Optional)

If `include_monitoring=true`:

```
for node in affected_nodes:
  if node.monitoring_state == "degraded":
    // Already compromised, recovery will be slower
    node.effective_rto_minutes *= 1.5
    node.at_risk = true
  elif node.monitoring_state == "unknown":
    // No observability data, use static RTO
    pass
  else:
    node.at_risk = false
```

---

## 3. Terraform Parser Refactoring

Current parser extracts resources and DEPENDS_ON relationships. Enhanced version adds:

### New Phases

**Phase 1: Extract resources** (existing)
- Parse HCL, extract resource attributes

**Phase 2: Infer recovery_strategy** (NEW)
```python
TYPE_TO_STRATEGY = {
    "aws_rds_cluster": "replica_fallback",
    "aws_rds_instance": "replica_fallback",
    "aws_elb": "multi_az",
    "aws_alb": "multi_az",
    "aws_lambda_function": "stateless",
    "aws_ecs_service": "stateless",
    "aws_ec2_instance": "generic",
    "aws_s3_bucket": "stateless",
    # ... more mappings
}

for resource in resources:
    resource.recovery_strategy = TYPE_TO_STRATEGY.get(resource.type, "generic")
```

**Phase 3: Infer edge types** (NEW)
```python
def infer_edge_type(source, target):
    """Infer edge type from resource types and relationship"""
    if source.type == "aws_rds_cluster" and target.type == "aws_rds_cluster":
        return "REPLICATES_TO"
    elif source.type in ["aws_lambda_function", "aws_instance", "aws_ecs_service"] \
         and target.type in ["aws_lambda_function", "aws_instance", "aws_ecs_service", "aws_rds_cluster"]:
        return "CALLS"
    elif source.type in ["aws_elb", "aws_alb"] \
         and target.type in ["aws_instance", "aws_ecs_service"]:
        return "ROUTES_TO"
    elif "security_group" in source.type or "security_group" in target.type:
        return "DEPENDS_ON"
    else:
        return "DEPENDS_ON"  # Default fallback

for resource in resources:
    for reference in resource.references:
        edge_type = infer_edge_type(resource, reference.target)
        edges.append({
            "source": resource.id,
            "target": reference.target.id,
            "type": edge_type,
        })
```

**Phase 4: Set default latency** (NEW)
```python
LATENCY_DEFAULTS = {
    "REPLICATES_TO": 1000,
    "CALLS": 100,
    "ROUTES_TO": 50,
    "USES": 500,
    "DEPENDS_ON": 100,
}

for edge in edges:
    edge.latency_ms = LATENCY_DEFAULTS.get(edge.type, 100)
```

**Phase 5: Infer recovery_rules** (NEW)
```python
for resource in resources:
    if resource.recovery_strategy == "replica_fallback":
        # Check if has REPLICATES_TO edges
        replica_edges = [e for e in edges 
                        if e.source == resource.id and e.type == "REPLICATES_TO"]
        resource.recovery_rules = {
            "replica_edge": "REPLICATES_TO",
            "backup_edge": "BACKED_UP_BY",
            "fallback_rto_multiplier": 2.0 if replica_edges else 3.0,
        }
    elif resource.recovery_strategy == "multi_az":
        resource.recovery_rules = {
            "fallback_rto_multiplier": 0.5,
        }
    else:
        resource.recovery_rules = {}
```

**Phase 6: Create Neo4j nodes + edges** (existing, enhanced)
- Create InfraNode with recovery_strategy + recovery_rules
- Create edges with latency_ms + type

---

## 4. API Changes

### Request (Extended)

```json
POST /api/dr/simulate
{
  "node_id": "aws_rds_cluster.postgres",
  "depth": 5,
  "include_monitoring": true
}
```

### Response (Extended)

```json
{
  "origin_node_id": "aws_rds_cluster.postgres",
  "blast_radius": [
    {
      "id": "aws_rds_cluster.postgres",
      "name": "Primary Database",
      "type": "aws_rds_cluster",
      "distance": 0,
      "step_time_ms": 0,
      "estimated_rto_minutes": 15,
      "estimated_rpo_minutes": 1,
      "effective_rto_minutes": 15,
      "recovery_strategy": "replica_fallback",
      "monitoring_state": "healthy",
      "at_risk": false
    },
    {
      "id": "aws_instance.app_001",
      "name": "API Server",
      "type": "aws_instance",
      "distance": 1,
      "step_time_ms": 100,
      "estimated_rto_minutes": 10,
      "estimated_rpo_minutes": 2,
      "effective_rto_minutes": 15,
      "recovery_strategy": "stateless",
      "monitoring_state": "degraded",
      "at_risk": true
    }
  ],
  "timeline_steps": [
    {
      "node_id": "aws_rds_cluster.postgres",
      "node_name": "Primary Database",
      "distance": 0,
      "step_time_ms": 0,
      "rto_minutes": 15,
      "rpo_minutes": 1
    },
    {
      "node_id": "aws_instance.app_001",
      "node_name": "API Server",
      "distance": 1,
      "step_time_ms": 100,
      "rto_minutes": 15,
      "rpo_minutes": 2
    }
  ],
  "max_distance": 2,
  "total_duration_ms": 5000,
  "worst_case_rto_minutes": 15,
  "worst_case_rpo_minutes": 2,
  "model_version": "1.0-accurate",
  "validation_score": null
}
```

---

## 5. Dependency Types Roadmap

| Dependency Type | MVP | Phase 2 | Phase 3 |
|-----------------|-----|---------|---------|
| **1. Timeout between services** | ✅ TIMEOUT_CALLS edge | Jitter + variability | Circuit breaker recovery |
| **2. Resource contention** | ✅ shares_resource + contention_factor | Multi-edge contention | Resource pool modeling |
| **3. Circuit breaker** | ✅ has_circuit_breaker flag | Event-driven logic | Auto recovery rules |
| **4. Monitoring state** | ✅ monitoring_state + degradation | Dynatrace ingestion | Real-time drift |
| **5. Data consistency** | ✅ replication_lag_seconds | Multi-region windows | Consistency guarantees |
| **6. Cross-region** | Placeholder | ✅ Geo-failover model | Regional latency matrix |

**MVP covers 1-5 at base level; 6 is documented but not implemented.**

---

## 6. Testing Strategy

| Test Type | Scenario | Assertion |
|-----------|----------|-----------|
| **Unit: Latency accumulation** | BFS with REPLICATES_TO (1000ms) and CALLS (100ms) | step_time_ms for 2nd hop = 1100ms |
| **Unit: RTO dynamic (replica healthy)** | recovery_strategy="replica_fallback", replica in graph | effective_rto = replica.rto |
| **Unit: RTO dynamic (replica down)** | recovery_strategy="replica_fallback", replica affected | effective_rto = node.rto × 2.0 |
| **Unit: RTO dynamic (multi-AZ)** | recovery_strategy="multi_az" | effective_rto = node.rto × 0.5 |
| **Unit: Monitoring degradation** | monitoring_state="degraded" | effective_rto multiplied by 1.5 |
| **Unit: Parser inference** | Parse sample Terraform with RDS + EC2 | Infer REPLICATES_TO, CALLS, recovery_strategy |
| **Integration: Full simulation** | Run simulate_disaster on sample graph | Timeline step_time_ms matches expected latencies |
| **Integration: Backward compat** | Old API call without monitoring_state | Works without errors, monitoring_state=null |

---

## 7. Implementation Roadmap

### Fase 1 (MVP) — This Design
- [ ] Neo4j schema extension (recovery_strategy, latency_ms, monitoring_state)
- [ ] Parser refactoring (Phases 2-6 above)
- [ ] BFS algorithm enhancement (latency accumulation)
- [ ] RTO/RPO dynamic calculation (3 strategies)
- [ ] Monitoring state incorporation
- [ ] API response extension
- [ ] Unit + integration tests
- [ ] Design doc + code review

**Effort:** ~2-3 weeks (backend dev + testing)

### Fase 2 (Post-MVP)
- Advanced contention modeling (multi-edge competition)
- Probabilistic simulation (Approach 2 from brainstorm)
- Circuit breaker logic + event triggering
- Real-time Dynatrace/Prometheus ingestion
- Jitter + variability support

**Effort:** ~2 weeks

### Fase 3
- Event-driven simulation (Approach 3 from brainstorm)
- Time-dependent propagation
- Cross-region failover modeling
- Data consistency windows
- Validation framework (real incident comparison)

**Effort:** ~3 weeks

---

## 8. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Parser inference is incorrect | Simulation accuracy degraded | Heavy testing of inference logic; manual review of inferred edges |
| Latency defaults don't match reality | Results still inaccurate | Phase 2: ingest real Dynatrace latency to override defaults |
| Monitoring state data unavailable | Can't incorporate degradation | include_monitoring=false by default; graceful fallback |
| Schema change breaks existing queries | Regression in other features | Backward compat testing; all existing queries still work |

---

## 9. Success Criteria (MVP)

✅ Simulation produces **timing within ±20% of real cascading failures** (validated in Phase 3)  
✅ RTO/RPO **context-aware** (varies by recovery_strategy and dependency health)  
✅ Parser **correctly infers** recovery_strategy + edge types for 95%+ of resources  
✅ API **backward compatible** (old requests still work)  
✅ **All tests green** (unit + integration)  
✅ **Scalable to Phases 2-3** (no architectural rework needed)

---

## Appendix: Example Walkthrough

### Scenario: Primary RDS fails (replica in same region, app servers depend)

**Terraform:**
```hcl
resource "aws_rds_cluster" "primary" {
  engine = "aurora-postgresql"
}

resource "aws_rds_cluster" "replica" {
  engine = "aurora-postgresql"
}

resource "aws_instance" "app_1" {
  tags = { depends_on = "aws_rds_cluster.primary" }
}
```

**Parser inference:**
```
primary: type=aws_rds_cluster → recovery_strategy="replica_fallback"
replica: type=aws_rds_cluster → recovery_strategy="replica_fallback"
app_1: type=aws_instance → recovery_strategy="stateless"

Edge primary → replica: type=REPLICATES_TO, latency_ms=1000
Edge app_1 → primary: type=CALLS, latency_ms=100

recovery_rules for primary:
  replica_edge: "REPLICATES_TO"
  fallback_rto_multiplier: 2.0
```

**Simulation (simulate_disaster on primary):**

```
Phase 1 (BFS):
  T=0: primary fails (origin)
  T=1000: replica fails (REPLICATES_TO latency)
  T=100: app_1 fails (CALLS latency)

Phase 2 (RTO/RPO dynamic):
  primary.effective_rto:
    recovery_strategy="replica_fallback"
    replica is affected → effective_rto = primary.rto × 2.0 = 30 min
  
  replica.effective_rto:
    recovery_strategy="replica_fallback"
    no other replica → effective_rto = replica.rto × 3.0 = 15 min
  
  app_1.effective_rto:
    recovery_strategy="stateless"
    effective_rto = app_1.rto × 0.5 = 5 min
    (can spin up new instance quickly)

Timeline:
  [0ms] primary fails, step_time_ms=0, effective_rto=30min
  [100ms] app_1 fails, step_time_ms=100, effective_rto=5min
  [1000ms] replica fails, step_time_ms=1000, effective_rto=15min
```

**Output to frontend:**
- Animation shows primary → app_1 at 100ms, then replica at 1000ms
- Report shows "Worst-case RTO: 30 minutes" (primary's degraded recovery)
- User understands: primary without replica is expensive to recover

---

## Sign-Off

**Design ready for:**
- [ ] User review + approval
- [ ] Implementation (writing-plans skill → detailed tasks)

