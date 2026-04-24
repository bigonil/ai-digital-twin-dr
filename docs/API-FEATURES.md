# API Reference — Feature Endpoints

This document describes the REST API endpoints for the 4 new platform features.

## Base URL
```
http://localhost:8001
```

## Authentication
Currently, no authentication is required. Production deployments should add API key or OAuth2.

---

## Compliance API

### POST /api/compliance/run
Run a full compliance audit on all infrastructure nodes.

**Request:**
```bash
curl -X POST http://localhost:8001/api/compliance/run
```

**Response (200 OK):**
```json
{
  "generated_at": "2026-04-21T15:30:00Z",
  "rto_threshold_minutes": 60,
  "rpo_threshold_minutes": 15,
  "total_nodes": 14,
  "pass_count": 10,
  "fail_count": 2,
  "warning_count": 2,
  "skipped_count": 0,
  "results": [
    {
      "node_id": "db-primary",
      "node_name": "Primary Database",
      "node_type": "database",
      "rto_minutes": 30,
      "rpo_minutes": 5,
      "rto_threshold": 60,
      "rpo_threshold": 15,
      "rto_status": "pass",
      "rpo_status": "pass",
      "blast_radius_size": 8,
      "worst_case_rto": 35,
      "worst_case_rpo": 10
    }
  ]
}
```

**Status Codes:**
- `200` — Audit completed successfully; results cached
- `500` — Audit failed (database error)

---

### GET /api/compliance/report
Retrieve the most recently cached compliance report.

**Request:**
```bash
curl http://localhost:8001/api/compliance/report
```

**Response (200 OK):**
Returns the same structure as `POST /api/compliance/run`.

**Status Codes:**
- `200` — Report found
- `404` — No report cached yet (run audit first)

---

### GET /api/compliance/export
Download the compliance report as a JSON file attachment.

**Request:**
```bash
curl http://localhost:8001/api/compliance/export \
  -H "Content-Disposition: attachment; filename=compliance-report.json"
```

**Response (200 OK):**
```
Content-Type: application/json
Content-Disposition: attachment; filename=compliance-report-<timestamp>.json
```

File contents: Same as compliance report.

**Status Codes:**
- `200` — Export successful
- `404` — No report cached yet

---

## What-If API

### POST /api/whatif/simulate
Simulate the impact of adding virtual infrastructure nodes/edges.

**Request:**
```bash
curl -X POST http://localhost:8001/api/whatif/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "origin_node_id": "db-primary",
    "depth": 3,
    "virtual_nodes": [
      {
        "id": "virtual-replica-db",
        "name": "Replica Database",
        "type": "database",
        "rto_minutes": 30,
        "rpo_minutes": 5,
        "is_redundant": true
      }
    ],
    "virtual_edges": [
      {
        "source": "virtual-replica-db",
        "target": "app-server",
        "type": "DEPENDS_ON"
      }
    ]
  }'
```

**Request Schema:**
```json
{
  "origin_node_id": "string (required, must exist in topology)",
  "depth": "integer (required, 1-10)",
  "virtual_nodes": [
    {
      "id": "string (required, must start with 'virtual-')",
      "name": "string (required)",
      "type": "string (required)",
      "rto_minutes": "integer (optional, default 60)",
      "rpo_minutes": "integer (optional, default 15)",
      "is_redundant": "boolean (optional, default false)"
    }
  ],
  "virtual_edges": [
    {
      "source": "string (required, node ID)",
      "target": "string (required, node ID)",
      "type": "string (required, must match _ALLOWED_REL_TYPES)"
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "origin_node_id": "db-primary",
  "baseline": {
    "blast_radius": [
      {
        "id": "db-primary",
        "name": "Primary Database",
        "type": "database",
        "distance": 0,
        "estimated_rto_minutes": 30,
        "estimated_rpo_minutes": 5
      }
    ],
    "total_affected": 8,
    "worst_case_rto_minutes": 35,
    "worst_case_rpo_minutes": 10
  },
  "proposed": {
    "blast_radius": [
      {
        "id": "db-primary",
        "name": "Primary Database",
        "type": "database",
        "distance": 0,
        "estimated_rto_minutes": 30,
        "estimated_rpo_minutes": 5
      }
    ],
    "total_affected": 6,
    "worst_case_rto_minutes": 30,
    "worst_case_rpo_minutes": 5
  },
  "blast_radius_delta": -2,
  "rto_delta_minutes": -5,
  "rpo_delta_minutes": -5,
  "virtual_nodes_added": 1,
  "virtual_edges_added": 1
}
```

**Status Codes:**
- `200` — Simulation completed successfully
- `404` — Origin node not found
- `422` — Validation error (invalid depth, virtual node ID format, etc.)
- `500` — Simulation failed

---

## Chaos API

### POST /api/chaos/experiments
Create a new chaos engineering experiment.

**Request:**
```bash
curl -X POST http://localhost:8001/api/chaos/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "db-primary",
    "scenario": "cpu_hog",
    "depth": 3,
    "notes": "Testing CPU exhaustion impact"
  }'
```

**Request Schema:**
```json
{
  "node_id": "string (required, must exist in topology)",
  "scenario": "string (required, one of: terminate, network_loss, cpu_hog, disk_full, memory_pressure)",
  "depth": "integer (required, 1-10)",
  "notes": "string (optional)"
}
```

**Response (200 OK):**
```json
{
  "experiment_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_id": "db-primary",
  "node_name": "Primary Database",
  "scenario": "cpu_hog",
  "created_at": "2026-04-21T15:30:00Z",
  "simulation": {
    "blast_radius": [
      {
        "id": "db-primary",
        "name": "Primary Database",
        "type": "database",
        "distance": 0
      }
    ],
    "total_affected": 8,
    "worst_case_rto_minutes": 35,
    "affected_nodes": [
      {
        "id": "db-primary",
        "name": "Primary Database",
        "distance": 0
      }
    ]
  },
  "actual_rto_minutes": null,
  "actual_blast_radius": [],
  "resilience_score": null,
  "notes": "Testing CPU exhaustion impact"
}
```

**Status Codes:**
- `200` — Experiment created successfully
- `404` — Node not found
- `422` — Validation error

---

### GET /api/chaos/experiments
List all chaos experiments.

**Request:**
```bash
curl http://localhost:8001/api/chaos/experiments
```

**Query Parameters:**
- None (future: pagination, filtering)

**Response (200 OK):**
```json
[
  {
    "experiment_id": "550e8400-e29b-41d4-a716-446655440000",
    "node_id": "db-primary",
    "node_name": "Primary Database",
    "scenario": "cpu_hog",
    "created_at": "2026-04-21T15:30:00Z",
    "resilience_score": 0.85,
    "simulation": { ... },
    "actual_rto_minutes": 25,
    "actual_blast_radius": ["db-primary"],
    "notes": "..."
  }
]
```

**Status Codes:**
- `200` — List retrieved

---

### GET /api/chaos/experiments/{id}
Get a specific chaos experiment.

**Request:**
```bash
curl http://localhost:8001/api/chaos/experiments/550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK):**
Same as individual experiment object.

**Status Codes:**
- `200` — Experiment found
- `404` — Experiment not found

---

### POST /api/chaos/experiments/{id}/actuals
Record actual results from running the chaos experiment in a lab/staging environment.

**Request:**
```bash
curl -X POST http://localhost:8001/api/chaos/experiments/550e8400-e29b-41d4-a716-446655440000/actuals \
  -H "Content-Type: application/json" \
  -d '{
    "actual_rto_minutes": 25,
    "actual_blast_radius": ["db-primary", "app-001"],
    "notes": "Failover triggered at 30s, DNS update took 25min total"
  }'
```

**Request Schema:**
```json
{
  "actual_rto_minutes": "integer (required)",
  "actual_blast_radius": ["string (array of node IDs)"],
  "notes": "string (optional)"
}
```

**Response (200 OK):**
```json
{
  "experiment_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_id": "db-primary",
  "node_name": "Primary Database",
  "scenario": "cpu_hog",
  "created_at": "2026-04-21T15:30:00Z",
  "simulation": { ... },
  "actual_rto_minutes": 25,
  "actual_blast_radius": ["db-primary", "app-001"],
  "resilience_score": 0.85,
  "notes": "Failover triggered at 30s, DNS update took 25min total"
}
```

**Resilience Score Calculation:**
```
rto_accuracy = 1.0 if actual_rto <= predicted_rto else predicted_rto / actual_rto
node_accuracy = intersection(predicted, actual) / union(predicted, actual)
resilience_score = (rto_accuracy + node_accuracy) / 2
```

**Status Codes:**
- `200` — Actuals recorded and resilience score calculated
- `404` — Experiment not found
- `422` — Validation error

---

### DELETE /api/chaos/experiments/{id}
Delete a chaos experiment.

**Request:**
```bash
curl -X DELETE http://localhost:8001/api/chaos/experiments/550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK):**
```json
{
  "status": "deleted",
  "experiment_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Status Codes:**
- `200` — Experiment deleted
- `404` — Experiment not found

---

## Postmortem API

### POST /api/postmortem/reports
Create a postmortem report analyzing a real incident against predictions.

**Request:**
```bash
curl -X POST http://localhost:8001/api/postmortem/reports \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Primary Failover",
    "occurred_at": "2026-04-21T15:30:00Z",
    "actual_origin_node_id": "db-primary",
    "actually_failed_node_ids": ["db-primary", "cache-001"],
    "actual_rto_minutes": 30,
    "actual_rpo_minutes": 5,
    "reference_simulation_node_id": "db-primary",
    "reference_simulation_depth": 3
  }'
```

**Request Schema:**
```json
{
  "title": "string (required)",
  "occurred_at": "string (required, ISO 8601 timestamp)",
  "actual_origin_node_id": "string (required)",
  "actually_failed_node_ids": ["string (required, array of node IDs)"],
  "actual_rto_minutes": "integer (required)",
  "actual_rpo_minutes": "integer (optional)",
  "reference_simulation_node_id": "string (optional, if omitted, compares to empty set)",
  "reference_simulation_depth": "integer (optional, default 3)"
}
```

**Response (200 OK):**
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440001",
  "title": "Database Primary Failover",
  "occurred_at": "2026-04-21T15:30:00Z",
  "origin_node_id": "db-primary",
  "prediction_accuracy": {
    "predicted_node_ids": ["db-primary", "cache-001", "app-001"],
    "actual_node_ids": ["db-primary", "cache-001"],
    "true_positives": ["db-primary", "cache-001"],
    "false_positives": ["app-001"],
    "false_negatives": [],
    "precision": 0.67,
    "recall": 1.0,
    "accuracy_score": 0.8,
    "rto_delta_minutes": 0
  },
  "simulation_used": {
    "origin_node_id": "db-primary",
    "depth": 3,
    "worst_case_rto_minutes": 30,
    "worst_case_rpo_minutes": 5
  },
  "recommendations": [
    "False positive on app-001 suggests blast radius tracing is conservative; consider tightening propagation rules",
    "RTO prediction was perfect (0m delta) — confidence in recovery planning is high"
  ],
  "created_at": "2026-04-21T16:00:00Z"
}
```

**Accuracy Metrics:**
```
precision = TP / (TP + FP)  — of predicted failures, how many were correct?
recall = TP / (TP + FN)      — of actual failures, how many did we predict?
f1_score = 2 * (precision * recall) / (precision + recall)  — balanced accuracy
```

**Status Codes:**
- `200` — Report created successfully
- `404` — Reference simulation not found (if specified)
- `422` — Validation error

---

### GET /api/postmortem/reports
List all postmortem reports.

**Request:**
```bash
curl http://localhost:8001/api/postmortem/reports
```

**Response (200 OK):**
```json
[
  {
    "report_id": "550e8400-e29b-41d4-a716-446655440001",
    "title": "Database Primary Failover",
    "occurred_at": "2026-04-21T15:30:00Z",
    "origin_node_id": "db-primary",
    "prediction_accuracy": {
      "accuracy_score": 0.8,
      "precision": 0.67,
      "recall": 1.0,
      "rto_delta_minutes": 0
    },
    "created_at": "2026-04-21T16:00:00Z"
  }
]
```

**Status Codes:**
- `200` — List retrieved

---

### GET /api/postmortem/reports/{id}
Get a specific postmortem report.

**Request:**
```bash
curl http://localhost:8001/api/postmortem/reports/550e8400-e29b-41d4-a716-446655440001
```

**Response (200 OK):**
Same as individual report object.

**Status Codes:**
- `200` — Report found
- `404` — Report not found

---

## Error Responses

All endpoints return standard error responses:

### 400 Bad Request
```json
{
  "detail": "Request validation failed",
  "status_code": 400
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found",
  "status_code": 404
}
```

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "origin_node_id"],
      "msg": "value_error.missing",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error",
  "status_code": 500
}
```

---

## Rate Limiting

Currently no rate limiting is configured. Production deployments should add rate limiting middleware.

---

## Caching

- **Compliance Report**: Cached in-memory on `app.state.last_compliance_report`. Cache is invalidated when a new audit runs.
- **Chaos Experiments**: Stored in-memory on `app.state.chaos_experiments`. Persists for the lifetime of the backend process.
- **Postmortem Reports**: Stored in-memory on `app.state.postmortem_reports`. Persists for the lifetime of the backend process.

For production, migrate to persistent storage (PostgreSQL, Redis, etc.).

---

## Examples

See [FEATURES.md](./FEATURES.md) for detailed workflow examples for each feature.
