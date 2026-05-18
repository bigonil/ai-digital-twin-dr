# AWS RDS Aurora PostgreSQL — Disaster Recovery Runbook

## Resource Type: aws_rds_cluster | Strategy: replica_fallback, multi_az, backup_fallback

### Overview

Aurora PostgreSQL clusters (`aws_rds_cluster`) consist of one writer instance and up to 15 read replicas across multiple Availability Zones. Aurora storage is replicated 6-way across 3 AZs automatically. The cluster endpoint always points to the current writer — DNS failover happens within 30–120 seconds.

RTO targets: 1–2 min (auto-failover) | 15–30 min (manual promote) | 60–90 min (restore from backup)
RPO targets: < 30 seconds (replica lag) | < 5 min (automated backup)

---

## Failure Scenario: Writer Instance Failure (replica_fallback)

**Symptoms:**
- CloudWatch alarm: `RDS/DBInstanceNotAvailable` on writer instance
- Application errors: `FATAL: remaining connection slots are reserved`
- CloudWatch metric: `RDS/DatabaseConnections` drops to 0 on writer

**Detection Commands:**
```bash
aws rds describe-db-clusters \
  --db-cluster-identifier app-postgres \
  --query 'DBClusters[0].{Status:Status,Writer:DBClusterMembers[?IsClusterWriter==`true`]}'

aws rds describe-events \
  --source-identifier app-postgres \
  --source-type db-cluster \
  --duration 60
```

**Recovery Steps — replica_fallback:**
1. Confirm failure is real (not monitoring flap): check 3 consecutive alarm data points
2. Aurora initiates auto-failover — a replica is promoted in 30–120 seconds
3. Monitor failover progress:
   ```bash
   aws rds describe-db-clusters \
     --db-cluster-identifier app-postgres \
     --query 'DBClusters[0].Status'
   ```
4. Verify cluster endpoint resolves to new writer IP:
   ```bash
   nslookup app-postgres.cluster-<id>.us-east-1.rds.amazonaws.com
   ```
5. Check replica lag on remaining replicas drops to 0:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/RDS \
     --metric-name AuroraReplicaLag \
     --dimensions Name=DBInstanceIdentifier,Value=app-postgres-0 \
     --start-time $(date -u -d '5 min ago' +%FT%TZ) \
     --end-time $(date -u +%FT%TZ) \
     --period 60 --statistics Average
   ```
6. Validate application connectivity — check app health endpoint returns 200
7. Update Neo4j node status: `MATCH (n:InfraNode {id: $id}) SET n.status = 'healthy'`

**Verification:** `aws rds describe-db-clusters` shows `Status: available`, writer instance is different from before failover.
**Rollback:** Not applicable — replica promotion is one-way. Keep old writer as new replica.

---

## Failure Scenario: Multi-AZ Failover (multi_az)

**Recovery Steps:**
1. Confirm AZ failure via AWS Health Dashboard: `aws health describe-events --filter eventTypeCategories=issue`
2. Force failover if auto-failover stalls:
   ```bash
   aws rds failover-db-cluster \
     --db-cluster-identifier app-postgres \
     --target-db-instance-identifier app-postgres-1
   ```
3. Monitor: failover completes in 20–35 seconds for Multi-AZ instances
4. DNS propagation: cluster endpoint TTL is 5 seconds, clients reconnect automatically
5. Scale down failed AZ capacity if needed; Aurora storage is unaffected

---

## Failure Scenario: Full Cluster Failure (backup_fallback)

**Recovery Steps — Restore from Snapshot:**
1. List available snapshots within RPO window:
   ```bash
   aws rds describe-db-cluster-snapshots \
     --db-cluster-identifier app-postgres \
     --query 'sort_by(DBClusterSnapshots,&SnapshotCreateTime)[-3:]' \
     --output table
   ```
2. Restore to new cluster:
   ```bash
   aws rds restore-db-cluster-from-snapshot \
     --db-cluster-identifier app-postgres-restored \
     --snapshot-identifier <snapshot-id> \
     --engine aurora-postgresql \
     --engine-version 15.4 \
     --db-subnet-group-name <subnet-group> \
     --vpc-security-group-ids <sg-id>
   ```
3. Add writer instance:
   ```bash
   aws rds create-db-instance \
     --db-instance-identifier app-postgres-restored-writer \
     --db-cluster-identifier app-postgres-restored \
     --db-instance-class db.r7g.large \
     --engine aurora-postgresql
   ```
4. Update application connection string to new cluster endpoint
5. Validate data integrity: `SELECT COUNT(*) FROM critical_table; SELECT MAX(created_at) FROM orders;`
6. Expected RTO: 45–90 minutes depending on snapshot size

---

## Monitoring & Alerting

Key CloudWatch metrics for `aws_rds_cluster`:
- `RDS/CPUUtilization` — alert at > 80% for 5 minutes
- `RDS/AuroraReplicaLag` — alert at > 30 seconds (replica falling behind)
- `RDS/DatabaseConnections` — alert if drops to 0 (writer failure)
- `RDS/FreeableMemory` — alert at < 500 MB
- `RDS/BufferCacheHitRatio` — informational, target > 99%
- `RDS/CommitLatency` — alert at > 10 ms (storage pressure)
- `RDS/SelectLatency` — alert at > 5 ms
- `RDS/WriteIOPS` — monitor for unusual spikes

CloudWatch alarm for writer failure:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name aurora-writer-connections-zero \
  --metric-name DatabaseConnections \
  --namespace AWS/RDS \
  --statistic Average \
  --period 60 \
  --threshold 0 \
  --comparison-operator LessThanOrEqualToThreshold \
  --evaluation-periods 2 \
  --dimensions Name=DBClusterIdentifier,Value=app-postgres
```

---

## Cascading Failure Risk

Aurora failure cascades to:
1. **Application servers (aws_instance / ASG)** — connection errors → increased error rate → possible OOM from retry storms
2. **Cache (ElastiCache Redis)** — if app falls back to direct DB reads during cache miss, amplifies DB load
3. **SQS consumers** — jobs requiring DB writes fail and route to DLQ

Mitigation: circuit breaker on DB connection pool; `max_connections` parameter group tuned per instance class.

---

## DR Region Failover (us-east-1 → eu-west-1)

1. Promote Aurora Global Database secondary cluster in eu-west-1:
   ```bash
   aws rds failover-global-cluster \
     --global-cluster-identifier app-postgres-global \
     --target-db-cluster-identifier arn:aws:rds:eu-west-1:<account>:cluster:app-postgres-dr
   ```
2. Update Route53 records to point to eu-west-1 cluster endpoint
3. Scale up eu-west-1 Aurora cluster: add writer + 1 replica
4. Verify replication lag was < 5 min before failover (check `AuroraGlobalDBReplicatedWriteIO`)
