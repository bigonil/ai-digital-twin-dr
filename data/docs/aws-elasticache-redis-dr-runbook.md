# AWS ElastiCache Redis — Disaster Recovery Runbook

## Resource Type: aws_elasticache_cluster | Strategy: replica_fallback, backup_fallback

### Overview

ElastiCache Redis replication groups (`aws_elasticache_cluster`) consist of a primary node and 1–5 replicas. With `automatic_failover_enabled = true`, a replica is promoted to primary in 20–60 seconds when the primary fails. The primary endpoint DNS updates automatically; read replicas use individual endpoints.

RTO targets: < 1 min (auto-failover) | 5–10 min (manual cluster recreation)
RPO: 0 (cache is ephemeral — data loss is acceptable for cache use cases)
RPO for persistent Redis (AOF/RDB): < 60 seconds

---

## Failure Scenario: Primary Node Failure (replica_fallback)

**Symptoms:**
- CloudWatch alarm: `ElastiCache/CacheHits` drops sharply
- Application logs: `ECONNREFUSED` or `READONLY` error from Redis client
- CloudWatch metric: `ElastiCache/ReplicationLag` on a specific replica spikes then drops to 0 (promotion)

**Detection Commands:**
```bash
aws elasticache describe-replication-groups \
  --replication-group-id app-redis \
  --query 'ReplicationGroups[0].{Status:Status,PrimaryEndpoint:NodeGroups[0].PrimaryEndpoint}'

aws elasticache describe-events \
  --source-identifier app-redis \
  --source-type replication-group \
  --duration 30
```

**Recovery Steps — replica_fallback (auto):**
1. ElastiCache detects primary failure via internal health checks (10-second intervals)
2. Automatic failover promotes replica — takes 20–60 seconds
3. DNS propagation to new primary completes within 60 seconds (TTL = 5s for endpoint)
4. Verify new primary is accepting writes:
   ```bash
   redis-cli -h <primary-endpoint> -p 6379 SET health_check ok
   redis-cli -h <primary-endpoint> -p 6379 GET health_check
   ```
5. Check application Redis connection pool reconnects (most clients retry with backoff)
6. Monitor `CacheHitRatio` returns to baseline (typically > 80%)

**Recovery Steps — replica_fallback (manual trigger):**
```bash
aws elasticache test-failover \
  --replication-group-id app-redis \
  --node-group-id 0001
```

**Verification:** `aws elasticache describe-replication-groups` shows new primary node ID, `Status: available`.
**Rollback:** N/A — failover is one-way. Original primary rejoins as replica automatically.

---

## Failure Scenario: Full Cluster Failure (backup_fallback)

**Recovery Steps — Recreate from Snapshot:**
1. List available snapshots:
   ```bash
   aws elasticache describe-snapshots \
     --replication-group-id app-redis \
     --query 'Snapshots[*].{Name:SnapshotName,Created:SnapshotCreateTime,Status:SnapshotStatus}' \
     --output table
   ```
2. Restore cluster from snapshot:
   ```bash
   aws elasticache create-replication-group \
     --replication-group-id app-redis-restored \
     --replication-group-description "Restored from DR snapshot" \
     --snapshot-name <snapshot-name> \
     --cache-node-type cache.r7g.large \
     --num-node-groups 1 \
     --replicas-per-node-group 2 \
     --automatic-failover-enabled \
     --security-group-ids <sg-id> \
     --cache-subnet-group-name <subnet-group>
   ```
3. Update application configuration to point to new primary endpoint
4. Warm up cache: replay recent request logs or trigger cache-warming jobs
5. Expected RTO: 10–20 minutes from snapshot

**Cold Start (no snapshot):**
- Create empty cluster (same command without `--snapshot-name`)
- Accept cold cache: application falls back to database for all requests temporarily
- Monitor `DatabaseConnections` on Aurora — expect spike during cache warm-up
- RTO: 5 minutes, but expect 50–70% additional DB load for 15–30 minutes while cache warms

---

## Failure Scenario: Replication Lag Alert

**Symptoms:** `ElastiCache/ReplicationLag` > 10 seconds on one or more replicas.

**Investigation:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ElastiCache \
  --metric-name ReplicationLag \
  --dimensions Name=ReplicationGroupId,Value=app-redis \
  --start-time $(date -u -d '30 min ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics Maximum
```

**Recovery:**
1. Check for write amplification on primary (high `CacheWrites` metric)
2. Check primary node CPU — if > 90%, consider scaling up: `aws elasticache modify-replication-group --replication-group-id app-redis --cache-node-type cache.r7g.xlarge`
3. If lag persists > 5 minutes, isolate lagging replica: remove from read endpoint rotation
4. Replication recovers automatically once write pressure reduces

---

## Monitoring & Alerting

Key CloudWatch metrics for `aws_elasticache_cluster`:
- `ElastiCache/ReplicationLag` — alert at > 5 seconds (replica lagging)
- `ElastiCache/CacheHitRatio` — alert at < 70% (cache ineffective)
- `ElastiCache/EngineCPUUtilization` — alert at > 80%
- `ElastiCache/FreeableMemory` — alert at < 100 MB (evictions imminent)
- `ElastiCache/Evictions` — alert at > 1000/min (memory pressure)
- `ElastiCache/CurrConnections` — monitor for connection exhaustion

CloudWatch alarm for replica lag:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name redis-replication-lag-high \
  --metric-name ReplicationLag \
  --namespace AWS/ElastiCache \
  --statistic Maximum \
  --period 60 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3 \
  --dimensions Name=ReplicationGroupId,Value=app-redis
```

---

## Cascading Failure Risk

Redis failure cascades to:
1. **Application servers (aws_instance)** — all cache misses fall through to Aurora, causing DB connection surge
2. **Aurora (aws_rds_cluster)** — sudden 3–10x increase in read queries may saturate DB connections or trigger CPU alarm
3. **API response times** — cache miss adds 50–200ms latency per request

Mitigation: connection pool circuit breaker; fallback TTL-based in-memory cache at application layer; `READONLY` client detection for replica routing.

---

## Application-Level Redis Client Best Practices

For Node.js (ioredis):
```javascript
const redis = new Redis({
  host: process.env.REDIS_HOST,
  retryStrategy: (times) => Math.min(times * 100, 3000),
  maxRetriesPerRequest: 3,
  enableReadyCheck: true,
  lazyConnect: true,
});
```

For Python (redis-py):
```python
redis_client = redis.Redis(
    host=REDIS_HOST,
    decode_responses=True,
    retry_on_timeout=True,
    retry=Retry(ExponentialBackoff(), 3),
    health_check_interval=30,
)
```
