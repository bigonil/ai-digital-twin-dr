# Backup Testing & Chaos Engineering Procedures

## Overview

Untested backups are not backups. Untested runbooks fail under pressure. This guide covers the monthly backup validation schedule, chaos engineering test procedures that validate ATHENA's blast radius predictions, and the criteria for declaring DR readiness. Every test result should be logged in the ATHENA postmortem system.

---

## Backup Validation Schedule

### Monthly Tests (first Tuesday of each month, 10:00 UTC)

**Test 1: Aurora Snapshot Restore**
```bash
# Find latest automated snapshot
SNAPSHOT=$(aws rds describe-db-cluster-snapshots \
  --db-cluster-identifier app-postgres \
  --snapshot-type automated \
  --query 'sort_by(DBClusterSnapshots,&SnapshotCreateTime)[-1].DBClusterSnapshotIdentifier' \
  --output text)

# Restore to validation cluster
aws rds restore-db-cluster-from-snapshot \
  --db-cluster-identifier backup-validation-$(date +%Y%m%d) \
  --snapshot-identifier $SNAPSHOT \
  --engine aurora-postgresql \
  --engine-version 15.4 \
  --db-subnet-group-name <subnet-group> \
  --vpc-security-group-ids <sg-id> \
  --no-deletion-protection

# Add writer instance
aws rds create-db-instance \
  --db-instance-identifier backup-validation-writer-$(date +%Y%m%d) \
  --db-cluster-identifier backup-validation-$(date +%Y%m%d) \
  --db-instance-class db.t3.medium \
  --engine aurora-postgresql

# Wait for available state (~15-20 min)
aws rds wait db-instance-available \
  --db-instance-identifier backup-validation-writer-$(date +%Y%m%d)

# Validate data integrity
ENDPOINT=$(aws rds describe-db-clusters \
  --db-cluster-identifier backup-validation-$(date +%Y%m%d) \
  --query 'DBClusters[0].Endpoint' --output text)

psql -h $ENDPOINT -U admin -d appdb << 'SQL'
  SELECT 'row_count' AS check, COUNT(*) AS value FROM critical_table
  UNION ALL
  SELECT 'max_id', MAX(id) FROM critical_table
  UNION ALL
  SELECT 'latest_created', EXTRACT(EPOCH FROM MAX(created_at))::bigint FROM critical_table;
SQL

# Clean up after validation
aws rds delete-db-instance \
  --db-instance-identifier backup-validation-writer-$(date +%Y%m%d) \
  --skip-final-snapshot

aws rds delete-db-cluster \
  --db-cluster-identifier backup-validation-$(date +%Y%m%d) \
  --skip-final-snapshot
```

**Record results:** `POST /api/postmortem` with `test_type=backup_validation`, `rto_minutes=<actual>`, `data_loss=<rows_missing>`.

---

**Test 2: ElastiCache Snapshot Restore**
```bash
# Create manual snapshot before test
aws elasticache create-snapshot \
  --replication-group-id app-redis \
  --snapshot-name manual-validation-$(date +%Y%m%d)

# Restore to validation cluster
aws elasticache create-replication-group \
  --replication-group-id redis-validation-$(date +%Y%m%d) \
  --replication-group-description "Backup validation" \
  --snapshot-name manual-validation-$(date +%Y%m%d) \
  --cache-node-type cache.t3.micro \
  --num-node-groups 1 --replicas-per-node-group 0

# Validate key count
redis-cli -h <validation-endpoint> DBSIZE

# Clean up
aws elasticache delete-replication-group \
  --replication-group-id redis-validation-$(date +%Y%m%d) \
  --retain-primary-cluster false
```

---

**Test 3: S3 Cross-Region Replication Lag**
```bash
# Write test object to primary with timestamp
TEST_KEY="dr-test/$(date +%s).json"
aws s3 cp - s3://app-data-primary-<account>/$TEST_KEY \
  <<< "{\"written_at\": \"$(date -u +%FT%TZ)\", \"test\": true}"

# Poll replica until object appears
START=$(date +%s)
while ! aws s3 ls s3://app-data-replica-<account>/$TEST_KEY --region eu-west-1 > /dev/null 2>&1; do
  sleep 5
done
ELAPSED=$(( $(date +%s) - START ))
echo "S3 CRR lag: ${ELAPSED} seconds"

# Cleanup
aws s3 rm s3://app-data-primary-<account>/$TEST_KEY
```

**Pass criteria:** S3 CRR lag < 300 seconds (5 minutes).

---

## Quarterly DR Drill (full regional failover test)

**Scope:** Complete failover test from us-east-1 to eu-west-1 during low-traffic window (Sunday 02:00 UTC).

**Duration:** 2 hours (60 min drill + 60 min failback)

**Procedure:**
1. Notify customers 48 hours in advance (maintenance window)
2. Set status page to "Scheduled Maintenance"
3. Execute `multi-region-failover-playbook.md` Phase 0–6 verbatim
4. Validate all health checks in eu-west-1 for 15 minutes
5. Execute failback procedure (eu-west-1 → us-east-1)
6. Confirm all traffic back in us-east-1
7. Log actual RTO, RPO, and any deviations from expected runbook steps

**Pass criteria:**
- RTO < 15 minutes (Phase 0 decision → Phase 6 validation complete)
- RPO < 5 minutes (Aurora Global DB lag at failover time)
- Zero data loss confirmed by row count comparison
- All ATHENA simulations run during drill show Q1/Q2 classification correctly

---

## Chaos Engineering Tests

### Test 1: Aurora Failover Simulation

**ATHENA setup:**
```bash
# Simulate from ATHENA (marks nodes as simulated_failure in Neo4j)
curl -X POST http://localhost:8001/api/dr/simulate \
  -H "Content-Type: application/json" \
  -d '{"node_id": "app-postgres", "depth": 5, "include_monitoring": true}'

# Note: eisenhower_quadrant, worst_case_rto_minutes, blast_radius from response
```

**Actual test execution (in non-production or during maintenance):**
```bash
aws rds failover-db-cluster --db-cluster-identifier app-postgres

# Measure actual recovery time
START=$(date +%s)
while ! aws rds describe-db-clusters \
  --db-cluster-identifier app-postgres \
  --query 'DBClusters[0].Status' --output text | grep -q "available"; do
  sleep 5
done
ACTUAL_RTO=$(( $(date +%s) - START ))
echo "Actual DB failover RTO: ${ACTUAL_RTO}s"
```

**Compare with ATHENA prediction:**
```bash
# ATHENA predicted RTO × 60 (minutes → seconds)
PREDICTED_RTO=$(curl -s http://localhost:8001/api/dr/simulate \
  -H "Content-Type: application/json" \
  -d '{"node_id": "app-postgres", "depth": 1}' | \
  jq '.worst_case_rto_minutes * 60')

echo "Predicted: ${PREDICTED_RTO}s | Actual: ${ACTUAL_RTO}s | Delta: $(( ACTUAL_RTO - PREDICTED_RTO ))s"
```

---

### Test 2: ASG Instance Termination (stateless)

```bash
# Terminate one instance in ASG
INSTANCE=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-name app-asg \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

START=$(date +%s)
aws ec2 terminate-instances --instance-ids $INSTANCE

# Wait for replacement to be healthy
while [ $(aws elbv2 describe-target-health \
  --target-group-arn <tg-arn> \
  --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`]|length(@)' \
  --output text) -lt 3 ]; do
  sleep 10
done
ACTUAL_RTO=$(( $(date +%s) - START ))
echo "Stateless node replacement RTO: ${ACTUAL_RTO}s"
```

---

### Test 3: Redis Failover

```bash
START=$(date +%s)
aws elasticache test-failover \
  --replication-group-id app-redis \
  --node-group-id 0001

while [ "$(aws elasticache describe-replication-groups \
  --replication-group-id app-redis \
  --query 'ReplicationGroups[0].Status' --output text)" != "available" ]; do
  sleep 5
done
ACTUAL_RTO=$(( $(date +%s) - START ))
echo "Redis failover RTO: ${ACTUAL_RTO}s"
```

---

## DR Readiness Criteria

The system is declared DR-ready when ALL of the following pass:

| Criterion | Test Method | Frequency | Pass Threshold |
|---|---|---|---|
| Aurora backup restores successfully | Monthly snapshot restore test | Monthly | < 30 min RTO, 0 data loss |
| S3 CRR lag within RPO | Object replication timing test | Monthly | < 5 min |
| Aurora failover within RTO | `test-failover` CLI | Monthly | < 2 min |
| ASG instance replacement | Instance termination test | Monthly | < 5 min |
| DNS cutover within target | Route53 update + nslookup timing | Quarterly | < 90 seconds propagation |
| Full region failover | DR drill | Quarterly | < 15 min end-to-end |
| ATHENA prediction accuracy | Compare predicted vs actual RTO | Per incident | ± 20% error rate |
| All runbook steps executable | Hands-on walkthrough | Quarterly | 0 missing permissions |

**DR readiness score:** `(passed criteria / total criteria) × 100`
Target: ≥ 90% (at least 8 of 8 for full readiness, 7 of 8 for conditional readiness).

---

## Test Result Logging

After each test, submit to ATHENA:
```bash
curl -X POST http://localhost:8001/api/postmortem \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "test-$(date +%Y%m%d)-aurora",
    "origin_node_id": "app-postgres",
    "predicted_rto_minutes": <athena-prediction>,
    "actual_rto_minutes": <measured>,
    "predicted_blast_radius": <athena-count>,
    "actual_blast_radius": <observed>,
    "test_type": "chaos_failover",
    "passed": true,
    "notes": "Monthly backup validation. No deviations from runbook."
  }'
```
