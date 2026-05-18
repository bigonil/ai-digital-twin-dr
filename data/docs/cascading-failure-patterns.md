# Cascading Failure Patterns — ATHENA DR Platform

## Overview

Cascading failures occur when a single component failure triggers secondary and tertiary failures across the dependency graph. ATHENA's BFS simulation traverses `DEPENDS_ON` edges in Neo4j to compute the blast radius. Understanding common cascade patterns helps operators anticipate failures and prevent propagation.

---

## Pattern 1: Database → Application → Load Balancer

**Trigger:** Aurora primary (`aws_rds_cluster`) fails or becomes unavailable.

**Cascade sequence:**
1. **T+0s** — Aurora writer fails; cluster endpoint returns connection errors
2. **T+5s** — Application servers (`aws_instance`) begin receiving `ECONNRESET` on DB connections
3. **T+15s** — Connection pool exhausted; application returns 500 errors to all requests
4. **T+30s** — ALB (`aws_lb`) health check fails on application instances
5. **T+60s** — ALB routes remaining traffic to surviving instances; overloads them
6. **T+90s** — Surviving instances become unhealthy from overload → full service outage

**Blast radius:** 3 hops from origin (Aurora → App servers → ALB)
**Eisenhower classification:** Q1 (RTO breach: 2+ min > target; critical blast radius ≤ 2 hops; affects production)

**Mitigation:**
- Circuit breaker at application layer (fail fast, don't hold connections)
- Connection pool `max_wait = 500ms` with immediate fail on timeout
- ALB health check grace period: allow 2 consecutive failures before removing target

---

## Pattern 2: Cache → Database Stampede

**Trigger:** Redis (`aws_elasticache_cluster`) primary fails; cache unavailable for 30–120 seconds.

**Cascade sequence:**
1. **T+0s** — Redis primary fails; replica promotion begins
2. **T+5s** — Cache miss rate → 100%; all requests miss cache
3. **T+10s** — All missed cache requests fall through to Aurora for reads
4. **T+20s** — Aurora connection count spikes 5–10x; `DatabaseConnections` alarm fires
5. **T+30s** — Aurora CPU spikes; queries slow down (lock contention, buffer pool pressure)
6. **T+45s** — Slow Aurora responses cause application timeouts; error rate increases
7. **T+60s** — Redis replica promoted; but Aurora now overloaded, app still slow

**Blast radius:** 2 hops (Redis → Aurora → App servers)
**Eisenhower classification:** Q2 during Redis promotion (not urgent if auto-failover working; important because affects production)

**Mitigation:**
- Request coalescing: deduplicate simultaneous cache-miss requests for same key
- Stale-while-revalidate pattern: serve expired cache data during miss
- Aurora connection pooling: PgBouncer or RDS Proxy to limit max connections

---

## Pattern 3: Queue Consumer Death → DLQ Overflow

**Trigger:** Application servers (`aws_instance`) fail while processing SQS messages.

**Cascade sequence:**
1. **T+0s** — App instances fail; in-flight SQS messages reach `VisibilityTimeout`
2. **T+VisibilityTimeout** — Messages become visible again; retried up to `maxReceiveCount`
3. **T+N×VisibilityTimeout** — Messages exceed `maxReceiveCount`; moved to DLQ
4. **T+ongoing** — New messages queue in main queue; `ApproximateAgeOfOldestMessage` grows
5. **T+4h** — If SQS retention period reached before consumers recover, messages lost

**Blast radius:** 1 hop from App servers (consumers → SQS queue)
**Eisenhower classification:** Q3 (urgent: queue growing; not important if jobs are background tasks)

**Mitigation:**
- Set `VisibilityTimeout` to `max_processing_time × 1.5` (avoids premature re-queuing)
- DLQ `maxReceiveCount = 3` (fail fast to DLQ rather than consuming retry capacity)
- Separate consumer processes from API servers (failure isolation)

---

## Pattern 4: AZ Failure — Partial Multi-AZ Cascade

**Trigger:** Availability Zone us-east-1a becomes unavailable.

**Cascade sequence:**
1. **T+0s** — All resources in us-east-1a become unavailable simultaneously
2. **T+0s** — Aurora promotes replica in us-east-1b (if Multi-AZ enabled): 30–120 seconds
3. **T+0s** — ElastiCache promotes replica in us-east-1b: 20–60 seconds
4. **T+0s** — ASG terminates us-east-1a instances; launches replacements in us-east-1b, us-east-1c
5. **T+30s** — New instances in us-east-1b/1c come online; connection storm to Aurora/Redis
6. **T+60s** — Aurora/Redis handling connection storm; temporary performance degradation
7. **T+90s** — Normal operation resumes in remaining AZs

**Blast radius:** ALL nodes in us-east-1a simultaneously; secondary effects in us-east-1b/1c from connection surge
**Eisenhower classification:** Q1 (AZ failure = RTO breach likely; critical blast radius; cascade in progress)

**Mitigation:**
- Pre-warm connection pools on surviving AZ instances before traffic shifts
- RDS Proxy absorbs connection storms (decouples app connections from DB connections)
- Spread ASG min capacity: `desired_capacity / num_AZs` per AZ minimum

---

## Pattern 5: Memory Pressure → OOM Cascade

**Trigger:** Aurora or ElastiCache node runs out of memory; evictions or OOM kill occurs.

**Cascade sequence:**
1. **T+0s** — Memory usage approaches 100%; OS starts swapping (database)
2. **T+30s** — Query latency increases 5–10x due to swap I/O
3. **T+60s** — Application timeouts; requests begin failing
4. **T+90s** — If OOM killer triggers: database process killed; instance restarts
5. **T+2min** — Instance restart (60–120 seconds); equivalent to node failure
6. **T+3min** — Cascades as per Pattern 1 (database failure)

**Blast radius:** Starts as 1 node; if OOM kill → cascades as full DB failure
**Eisenhower classification:** Q2 initially (warning, not yet breach); escalates to Q1 if OOM kill occurs

**Mitigation:**
- CloudWatch alarm on `FreeableMemory < 500 MB` (15-minute warning before crisis)
- Aurora parameter: `max_connections` tuned to `LEAST(DBInstanceClassMemory/9531392, 5000)`
- ElastiCache: enable `maxmemory-policy allkeys-lru` to evict old keys before OOM

---

## Blast Radius Calculation

ATHENA uses BFS (Breadth-First Search) to traverse the dependency graph from the origin node:

```
blast_radius[distance=0] = origin node
blast_radius[distance=1] = nodes with DEPENDS_ON edge to origin
blast_radius[distance=2] = nodes depending on distance=1 nodes
...
blast_radius[distance=N] = nodes at N hops from origin
```

**Eisenhower urgency based on blast radius:**
- Distance ≤ 2: `critical_blast = True` → contributes to **Important** classification
- Distance > 2: not critical by default (but may still affect Eisenhower if affects_production)

**RTO impact accumulation:**
- Effective RTO at each node = max(own RTO, upstream node RTO × latency_factor)
- `replica_fallback` nodes: effective RTO = base RTO × 0.5 (fast recovery)
- `backup_fallback` nodes: effective RTO = base RTO × 2.0 (slow recovery)

---

## Recovery Priority During Cascading Failure

When multiple nodes are failing simultaneously:

1. **Restore in reverse blast-radius order** (furthest first is wrong — restore origin first)
2. **Priority order:** Database > Cache > Application > Queue > Load Balancer
3. **Reason:** Restoring downstream nodes before origin leads to immediate re-failure when origin comes back

Correct sequence for Pattern 1 cascade:
1. Restore Aurora (origin) → wait for full health
2. Flush application connection pools → reconnect to Aurora
3. Verify Redis is healthy or promote replica
4. Validate ALB health checks pass
5. Restore SQS consumers last (low risk, queue retains messages)

---

## Common False Positives

Not all "cascading" alerts are real failures:
- **Deploy-time health check dips:** Normal during rolling deployments; `HealthyHostCount` temporarily drops
- **Replication lag spikes:** Heavy write load temporarily increases lag; watch for sustained lag > 60 seconds before escalating
- **Connection count spikes:** Burst traffic causes connection surge; not a failure if DB handles it within 30 seconds
- **SQS depth spikes:** Batch job submission; depth grows then drains normally
