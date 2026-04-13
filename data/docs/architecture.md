# Architecture & Disaster Recovery Runbook

## System Overview

This platform is a multi-region AWS deployment consisting of:

- **Region primary**: `us-east-1` (active)
- **Region DR**: `eu-west-1` (warm standby)

All stateful services replicate cross-region. RTO target is **15 minutes**, RPO target is **5 minutes**.

---

## Component Inventory

| Component | Type | Region | Redundancy |
|---|---|---|---|
| app-alb | Application Load Balancer | us-east-1 | Multi-AZ |
| app-asg | Auto Scaling Group | us-east-1 | 2–10 instances |
| app-postgres | Aurora PostgreSQL Cluster | us-east-1 | 3 AZ, 2 replicas |
| app-redis | ElastiCache Redis | us-east-1 | 2 replicas + auto-failover |
| app-data-primary | S3 Bucket | us-east-1 | Cross-region replication |
| app-data-replica | S3 Bucket (replica) | eu-west-1 | Replica target |
| app-jobs | SQS FIFO Queue | us-east-1 | Managed, DLQ configured |

---

## Failure Scenarios & Recovery Procedures

### Scenario 1: Database Primary Failure (Aurora)

**Symptoms**: Application errors writing to DB, CloudWatch `DBInstanceNotAvailable` alarm.

**Recovery Steps**:
1. Verify failure: `aws rds describe-db-cluster-members --db-cluster-identifier app-postgres`
2. Aurora auto-promotes replica in ~30s — monitor CloudWatch for failover completion
3. Verify application can reconnect via cluster endpoint (endpoint does not change)
4. If all replicas fail: restore from latest automated backup (last 7 days retention)
5. Update application config if using instance endpoint (migrate to cluster endpoint)

**RTO**: 1–2 min (auto-failover) / 15 min (manual restore)
**RPO**: < 1 min (replica lag)

---

### Scenario 2: Region Failure (us-east-1)

**Symptoms**: All us-east-1 health checks fail, Route53 health check triggers DNS failover.

**Recovery Steps**:
1. Confirm region failure via AWS Health Dashboard
2. Activate DR region: verify `eu-west-1` resources are healthy
3. Promote S3 replica: disable replication rules to make `app-data-replica` writable
4. Point application to DR database (deploy Aurora in eu-west-1 from latest snapshot)
5. Update Route53 health-check weights to route 100% traffic to eu-west-1
6. Scale up ASG in eu-west-1 to full production capacity
7. Notify on-call team and open incident ticket

**RTO**: 10–15 min
**RPO**: < 5 min (S3 CRR replication lag)

---

### Scenario 3: Cache (Redis) Failure

**Symptoms**: Latency spike, application logs show Redis connection timeouts.

**Recovery Steps**:
1. Check ElastiCache replication group status:  
   `aws elasticache describe-replication-groups --replication-group-id app-redis`
2. ElastiCache auto-failover promotes a replica in ~30s
3. If entire cluster fails: create new cluster from latest snapshot
4. Application should use retry logic with exponential backoff (code-level)

**RTO**: 1 min (auto-failover) / 5 min (manual restore)
**RPO**: 0 (Redis persistence disabled, cache is ephemeral)

---

### Scenario 4: Message Queue Backlog (SQS)

**Symptoms**: `app-jobs.fifo` depth growing, `app-jobs-dlq.fifo` receiving messages.

**Recovery Steps**:
1. Identify failing consumer workers (check ASG instance health)
2. Inspect DLQ messages for root cause: `aws sqs receive-message --queue-url <dlq-url>`
3. Fix underlying issue (code bug, dependency failure)
4. Redrive DLQ messages back to main queue after fix is deployed
5. Scale ASG temporarily to drain backlog faster

---

## Monitoring & Alerting

Key CloudWatch metrics to monitor:
- `RDS/CPUUtilization` > 80%
- `RDS/ReplicaLag` > 30s
- `ElastiCache/ReplicationLag` > 5s
- `ApplicationELB/HealthyHostCount` < 2
- `SQS/ApproximateNumberOfMessagesNotVisible` > 1000

---

## Contact & Escalation

| Level | Contact | Response Time |
|---|---|---|
| P1 (full outage) | on-call@company.com | 5 min |
| P2 (partial degradation) | team@company.com | 15 min |
| P3 (non-critical) | backlog ticket | Next business day |
