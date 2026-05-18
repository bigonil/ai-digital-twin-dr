# RTO/RPO Monitoring & Measurement Guide — ATHENA Platform

## Overview

RTO (Recovery Time Objective) and RPO (Recovery Point Objective) are the core SLA parameters for disaster recovery. ATHENA calculates **effective RTO/RPO** per node by applying recovery strategy multipliers to base targets, then propagates the worst case across the blast radius.

---

## Definitions

**RTO (Recovery Time Objective):**
The maximum acceptable downtime from failure detection to full service restoration. Measured in minutes. Stored as `rto_minutes` on each Neo4j `InfraNode`.

**RPO (Recovery Point Objective):**
The maximum acceptable data loss, expressed as time. A 5-minute RPO means at most 5 minutes of data can be lost. Stored as `rpo_minutes` on each Neo4j `InfraNode`.

**Effective RTO:**
ATHENA calculates effective RTO per node factoring in recovery strategy:
- `replica_fallback`: effective_rto = base_rto × 0.5 (fast replica promotion)
- `multi_az`: effective_rto = base_rto × 0.3 (AWS-managed, very fast)
- `stateless`: effective_rto = base_rto × 0.4 (ASG self-healing)
- `backup_fallback`: effective_rto = base_rto × 2.0 (slow restore)
- `generic`: effective_rto = base_rto × 1.0 (no improvement assumed)

**Worst-case RTO/RPO:**
`max(effective_rto for all nodes in blast_radius)` — this is what ATHENA reports and compares against targets for Eisenhower classification.

---

## RTO/RPO Targets by Node Type

| Node Type | Base RTO (min) | Base RPO (min) | Recommended Strategy |
|---|---|---|---|
| aws_rds_cluster (Aurora) | 15 | 1 | replica_fallback |
| aws_db_instance (RDS Multi-AZ) | 5 | 5 | multi_az |
| aws_elasticache_cluster | 5 | 0 | replica_fallback |
| aws_lb (ALB) | 1 | 0 | multi_az |
| aws_instance (EC2/ASG) | 5 | 0 | stateless |
| aws_s3_bucket (with CRR) | 15 | 15 | replica_fallback |
| aws_s3_bucket (no CRR) | 60 | 240 | backup_fallback |
| aws_sqs_queue | 2 | 0 | stateless |
| aws_eks_cluster | 10 | 0 | stateless |
| aws_lambda_function | 1 | 0 | stateless |

---

## Measuring Actual RTO in Production

### Automated RTO Measurement with CloudWatch

CloudWatch Contributor Insights + Metric Math can track actual recovery time:

```bash
# Create metric alarm that tracks time from failure to recovery
aws cloudwatch put-composite-alarm \
  --alarm-name actual-rto-tracker \
  --alarm-rule "ALARM(db-failure-detected) AND OK(db-healthy-again)" \
  --actions-enabled
```

### Manual RTO Measurement for Post-Mortem

Collect these timestamps for each incident:
1. `T_failure` — first alarm fires (or first user report)
2. `T_detected` — on-call acknowledges and confirms failure
3. `T_action` — first recovery action taken
4. `T_partial` — service partially restored (some users can access)
5. `T_full` — full service restoration, all health checks green

**Actual RTO = T_full − T_failure**
**Detection delay = T_detected − T_failure** (target: < 2 minutes with CloudWatch alarms)

---

## Measuring Actual RPO in Production

### For Aurora/RDS

Check replication lag at time of failure:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name AuroraReplicaLag \
  --dimensions Name=DBClusterIdentifier,Value=app-postgres \
  --start-time <T_failure - 5 min> \
  --end-time <T_failure> \
  --period 60 --statistics Maximum \
  --output text
```

The maximum lag at `T_failure` = actual RPO for replica_fallback scenarios.

### For ElastiCache Redis

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ElastiCache \
  --metric-name ReplicationLag \
  --dimensions Name=ReplicationGroupId,Value=app-redis \
  --start-time <T_failure - 5 min> \
  --end-time <T_failure> \
  --period 60 --statistics Maximum
```

### For S3 (CRR)

```bash
aws s3api get-bucket-replication --bucket app-data-primary-<account>
# Check ReplicationTime for SLA-backed replication (S3 RTC)
# Without RTC: measure lag via CloudWatch S3/ReplicationLatency metric
```

---

## CloudWatch Dashboard for RTO/RPO Tracking

Set up a DR metrics dashboard with these widgets:

**Widget 1: Replication Lag (live RPO proxy)**
```json
{
  "type": "metric",
  "properties": {
    "metrics": [
      ["AWS/RDS", "AuroraReplicaLag", "DBClusterIdentifier", "app-postgres"],
      ["AWS/ElastiCache", "ReplicationLag", "ReplicationGroupId", "app-redis"]
    ],
    "period": 60,
    "stat": "Maximum",
    "title": "Live Replication Lag (RPO proxy)"
  }
}
```

**Widget 2: Recovery Readiness**
```json
{
  "type": "metric",
  "properties": {
    "metrics": [
      ["AWS/RDS", "DatabaseConnections", "DBClusterIdentifier", "app-postgres"],
      ["AWS/ElastiCache", "CacheHitRatio", "ReplicationGroupId", "app-redis"],
      ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", "app/app-alb/<id>"]
    ],
    "title": "Recovery Readiness Indicators"
  }
}
```

---

## Compliance Audit: RTO/RPO Breach Detection

ATHENA's `/api/compliance` endpoint runs automated audits:

```bash
curl -X POST http://localhost:8001/api/compliance/audit \
  -H "Content-Type: application/json" \
  -d '{"rto_target_minutes": 60, "rpo_target_minutes": 15}'
```

Response includes:
- `compliant_nodes`: nodes where effective_rto < target and effective_rpo < target
- `warning_nodes`: effective_rto is 70–100% of target (URGENCY_RATIO_WARN threshold)
- `breach_nodes`: effective_rto > target (immediate Q1 escalation)

Recommended schedule: run compliance audit every 15 minutes in production, hourly in staging.

---

## RTO/RPO Improvement Recommendations

### To reduce RTO:
1. **Upgrade `backup_fallback` to `replica_fallback`:** Add read replica to single-AZ RDS instances
2. **Enable Multi-AZ on Aurora clusters:** Reduces failover time from 120s to 30s
3. **Pre-warm ASG instances:** Keep warm pool to reduce cold-start time
4. **Use RDS Proxy:** Reduces connection storm after DB failover from 120s to < 30s
5. **Enable ElastiCache auto-failover:** Reduces Redis RTO from 5–10 min to < 1 min

### To reduce RPO:
1. **Increase Aurora backup frequency:** Enable continuous backup (Aurora default)
2. **Enable S3 Replication Time Control (RTC):** Guarantees 99.99% of objects replicated in 15 minutes
3. **Reduce ElastiCache sync interval:** Use `appendfsync always` for Redis persistence (trades throughput for durability)
4. **Enable Aurora Global Database:** RPO < 1 second for cross-region writes

---

## Monitoring Alarm Reference

RTO/RPO-related CloudWatch alarms to maintain:

| Alarm Name | Metric | Threshold | Impact |
|---|---|---|---|
| `aurora-replica-lag-rpo-warn` | RDS/AuroraReplicaLag | > 60s | RPO warning |
| `aurora-replica-lag-rpo-breach` | RDS/AuroraReplicaLag | > 300s | RPO breached |
| `redis-lag-rpo-warn` | ElastiCache/ReplicationLag | > 10s | RPO warning |
| `alb-healthy-host-rto-warn` | ALB/HealthyHostCount | < 2 | RTO risk |
| `alb-healthy-host-rto-breach` | ALB/HealthyHostCount | < 1 | RTO breached |
| `asg-below-minimum` | AutoScaling/GroupInServiceInstances | < 2 | RTO risk |
| `aurora-connections-zero` | RDS/DatabaseConnections | = 0 | RTO breached |

---

## Incident Retrospective: RTO/RPO Accuracy

After each incident, record in post-mortem:
- **Predicted RTO** (from ATHENA simulation before incident): `X` minutes
- **Actual RTO** (from incident timeline): `Y` minutes
- **Prediction error:** `(Y - X) / X × 100%`
- **Predicted RPO** vs **Actual data loss**

Target prediction accuracy: ± 20% for RTO, ± 50% for RPO.
Update Neo4j `rto_minutes` / `rpo_minutes` on affected nodes if systematic bias detected.
