# Recovery Strategies Guide — ATHENA DR Platform

## Overview of Recovery Strategies

ATHENA classifies each infrastructure node with a recovery strategy. The strategy determines RTO, RPO, recovery cost, and the runbook approach. Strategies are stored as `recovery_strategy` on Neo4j `InfraNode` nodes.

---

## Strategy: replica_fallback

**Definition:** A standby replica of the primary resource exists and can be promoted with minimal data loss.

**Applicable node types:** aws_rds_cluster, aws_db_instance, aws_elasticache_cluster

**Effective RTO:** 1–5 minutes (automatic promotion) / 10–15 minutes (manual)
**Effective RPO:** < 30 seconds (synchronous replication) / < 5 minutes (asynchronous)

**How it works:**
1. Health check detects primary failure (10–30 second interval)
2. Replica with most recent data is selected for promotion
3. DNS endpoint is updated to point to new primary
4. Existing connections receive error and must reconnect
5. Old primary is demoted to replica role when it recovers

**Cost multiplier:** 1.5x (brief extra compute during promotion + double-write during catch-up)

**Prerequisites for strategy to work:**
- `automatic_failover_enabled = true` on ElastiCache
- Aurora Multi-AZ enabled with at least 1 replica
- Application using cluster endpoint (not instance endpoint) for Aurora
- Connection pool with retry logic and exponential backoff

**Red flags indicating strategy will fail:**
- Replica lag > 30 seconds at time of primary failure (risk of data loss beyond RPO)
- All replicas in same AZ as failed primary
- Application hardcoded to instance endpoint instead of cluster endpoint

---

## Strategy: multi_az

**Definition:** Resource is automatically distributed across multiple Availability Zones. AWS manages failover transparently.

**Applicable node types:** aws_lb, aws_rds_cluster (Multi-AZ deployment), aws_db_instance (Multi-AZ)

**Effective RTO:** < 2 minutes (automatic) / < 30 seconds for ALB
**Effective RPO:** 0 for ALB (stateless) / < 60 seconds for RDS Multi-AZ

**How it works:**
1. Primary instance fails or AZ becomes unavailable
2. AWS promotes standby in different AZ automatically
3. DNS CNAME for the endpoint is updated (60-second propagation)
4. No manual intervention required under normal conditions

**Cost multiplier:** 1.2x (standby instance always running, minimal extra during failover)

**Key difference from replica_fallback:**
- `multi_az` implies AWS-managed automatic failover with no manual steps
- `replica_fallback` may require manual promotion or monitoring confirmation

**Prerequisites:**
- RDS Multi-AZ enabled (`multi_az = true`)
- ALB subnets in ≥ 2 AZs
- Route53 health checks configured for DNS-level failover

---

## Strategy: stateless

**Definition:** Resource holds no persistent state. Recovery means simply replacing the failed instance; data comes from external stores (Aurora, Redis, S3).

**Applicable node types:** aws_instance, aws_autoscaling_group, aws_lambda_function, aws_eks_cluster (worker nodes)

**Effective RTO:** 1–3 minutes (ASG self-healing) / 5–10 minutes (new deployment)
**Effective RPO:** 0 (no state on instance)

**How it works:**
1. Health check fails on instance
2. ASG terminates unhealthy instance and launches replacement
3. New instance bootstraps via user-data / cloud-init
4. Load balancer registers new instance after health check passes

**Cost multiplier:** 1.1x (brief extra cost to run replacement in parallel)

**Prerequisites for quick recovery:**
- ASG `health_check_type = "ELB"` (faster detection than EC2 checks)
- `health_check_grace_period` set appropriately for application startup time
- Launch template uses latest AMI with pre-installed dependencies
- Application configuration loaded from SSM Parameter Store / Secrets Manager (no manual config)

**Anti-patterns to avoid:**
- Storing session state in-memory on instances (lost on replacement)
- Hardcoded IP addresses in configuration
- Long instance startup sequences (> 2 minutes) that delay health check pass

---

## Strategy: backup_fallback

**Definition:** No live replica exists. Recovery requires restoring from a point-in-time snapshot or backup. This is the slowest strategy with highest data loss risk.

**Applicable node types:** aws_s3_bucket (without CRR), aws_db_instance (single-AZ, no replica), aws_elasticache_cluster (without replicas)

**Effective RTO:** 30–120 minutes (restore time depends on data volume)
**Effective RPO:** Time since last backup (typically 1–24 hours)

**How it works:**
1. Failure detected on primary resource
2. Latest valid backup within RPO window is identified
3. New resource instance is provisioned from backup
4. Data integrity is validated
5. Application is reconfigured to use new instance

**Cost multiplier:** 4.0x (slow restore, temporary extra instances, engineering time)

**Recovery time estimates by data volume:**
- < 100 GB: 30–45 minutes
- 100 GB – 1 TB: 1–3 hours
- > 1 TB: 3–8 hours (consider S3 Glacier Instant Retrieval for faster access)

**Critical prerequisites:**
- Automated daily backups enabled and tested (last restore test < 30 days ago)
- Backup stored in different region or account (protection against account-level incidents)
- Known-good backup identified BEFORE declaring incident (saves 15–30 min during recovery)

**Backup validation procedure (run monthly):**
```bash
# Test restore to non-production environment
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier validation-test-$(date +%Y%m%d) \
  --db-snapshot-identifier <latest-snapshot-id> \
  --db-instance-class db.t3.medium \
  --no-multi-az \
  --tags Key=Purpose,Value=BackupValidation
# Run integrity checks, then delete
aws rds delete-db-instance --db-instance-identifier validation-test-$(date +%Y%m%d) --skip-final-snapshot
```

---

## Strategy: generic

**Definition:** No specific recovery strategy is defined. Recovery requires manual investigation, identification of root cause, and improvised recovery steps.

**Effective RTO:** 30–120 minutes (highly variable)
**Effective RPO:** Unknown (depends on last good state)

**Cost multiplier:** 2.5x

**This strategy indicates a gap in the DR design.** Nodes with `generic` strategy should be assessed and migrated to a more specific strategy. Priority order: `replica_fallback` > `multi_az` > `stateless` > `backup_fallback` > `generic`.

**Minimum recovery steps for generic strategy:**
1. Confirm failure is not a false positive (check 3 independent monitoring sources)
2. Identify last known good state (recent snapshots, recent successful health checks)
3. Isolate failed component to prevent cascading failures
4. Attempt restart / recreation of the resource
5. Validate all downstream dependencies after recovery

---

## RTO/RPO Target Reference

| Strategy | P50 RTO | P95 RTO | P50 RPO | P95 RPO | Cost Multiplier |
|---|---|---|---|---|---|
| replica_fallback | 2 min | 10 min | 10 sec | 5 min | 1.5x |
| multi_az | 30 sec | 2 min | 0 | 60 sec | 1.2x |
| stateless | 2 min | 5 min | 0 | 0 | 1.1x |
| backup_fallback | 45 min | 3 hr | 4 hr | 24 hr | 4.0x |
| generic | 30 min | 2 hr | Unknown | Unknown | 2.5x |

---

## Choosing the Right Strategy

Decision tree for architects assigning `recovery_strategy` to new nodes:

1. **Is the resource stateless?** → `stateless`
2. **Does the resource have a continuously-updated replica?** → `replica_fallback`
3. **Is AWS managing failover automatically across AZs?** → `multi_az`
4. **Is there a recent snapshot/backup but no live replica?** → `backup_fallback`
5. **None of the above** → `generic` (and open an architecture review ticket)
