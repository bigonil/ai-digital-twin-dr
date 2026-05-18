# Multi-Region Failover Playbook — us-east-1 → eu-west-1

## Overview

This playbook orchestrates a full failover from the primary region (us-east-1) to the DR region (eu-west-1). It covers all services in dependency order: database first, then cache, then application, then DNS. Total expected RTO: 10–15 minutes for planned failover, 20–30 minutes for unplanned.

Region architecture:
- **Primary (active):** us-east-1 — all write traffic, full capacity
- **DR (warm standby):** eu-west-1 — read replicas, scaled-down app fleet, pre-provisioned

RPO at failover decision: < 5 min (S3 CRR lag + Aurora Global DB lag combined)

---

## Phase 0: Decision to Failover

**Trigger criteria for full region failover:**
- AWS Health Dashboard shows multi-service event in us-east-1 lasting > 5 minutes
- All three of the following metrics fail simultaneously:
  - ALB `HealthyHostCount` = 0
  - Aurora `DatabaseConnections` = 0
  - ElastiCache `CacheHitRatio` = 0
- Engineering leadership approves failover (requires explicit authorization)

**DO NOT failover for:**
- Single-service failures (use service-specific runbook instead)
- Failures lasting < 5 minutes (auto-recovery likely)
- Partial degradation (one AZ down, other AZs healthy)

**Pre-failover checklist:**
- [ ] Confirm eu-west-1 Aurora replica lag < 5 minutes: `aws rds describe-db-clusters --region eu-west-1`
- [ ] Confirm S3 CRR last sync < 15 minutes
- [ ] Verify eu-west-1 ACM certificate is valid: `aws acm list-certificates --region eu-west-1`
- [ ] Confirm on-call SRE, DBA, and engineering lead are on the war room call
- [ ] Set incident status page to "Investigating"

---

## Phase 1: Database Failover (T+0 to T+5 min)

### 1a. Aurora Global Database Failover (PRIMARY — do this first)

```bash
# Promote eu-west-1 cluster to writer
aws rds failover-global-cluster \
  --global-cluster-identifier app-postgres-global \
  --target-db-cluster-identifier arn:aws:rds:eu-west-1:<account>:cluster:app-postgres-dr \
  --region us-east-1

# Monitor promotion (takes 1–2 minutes)
watch -n 5 'aws rds describe-db-clusters \
  --db-cluster-identifier app-postgres-dr \
  --region eu-west-1 \
  --query "DBClusters[0].{Status:Status,Writer:DBClusterMembers[?IsClusterWriter==\`true\`]}"'
```

**Expected:** Cluster status transitions `promoting → available`. New writer endpoint active.

```bash
# Capture new endpoint for downstream steps
NEW_DB_ENDPOINT=$(aws rds describe-db-clusters \
  --db-cluster-identifier app-postgres-dr \
  --region eu-west-1 \
  --query 'DBClusters[0].Endpoint' --output text)
echo "New DB endpoint: $NEW_DB_ENDPOINT"
```

### 1b. Record actual RPO

```bash
# Check Aurora lag at time of failover
aws rds describe-global-clusters \
  --global-cluster-identifier app-postgres-global \
  --query 'GlobalClusters[0].GlobalClusterMembers[?IsWriter==`false`].GlobalWriteForwardingStatus'
```

---

## Phase 2: Cache Failover (T+3 to T+6 min)

```bash
# Check eu-west-1 Redis status
aws elasticache describe-replication-groups \
  --replication-group-id app-redis-dr \
  --region eu-west-1 \
  --query 'ReplicationGroups[0].{Status:Status,Primary:NodeGroups[0].PrimaryEndpoint}'

# If Redis in eu-west-1 is a replica of us-east-1, remove replication link to enable writes
aws elasticache modify-replication-group \
  --replication-group-id app-redis-dr \
  --remove-member-cluster-ids app-redis-dr-001 \
  --region eu-west-1
# (Or: delete and recreate as standalone cluster)

REDIS_ENDPOINT=$(aws elasticache describe-replication-groups \
  --replication-group-id app-redis-dr \
  --region eu-west-1 \
  --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text)
echo "New Redis endpoint: $REDIS_ENDPOINT"
```

---

## Phase 3: S3 — Enable Writes on Replica (T+5 to T+7 min)

```bash
# Disable replication rules so replica bucket accepts writes
aws s3api delete-bucket-replication \
  --bucket app-data-replica-<account-id> \
  --region eu-west-1

# Update SSM parameter to point app at DR bucket
aws ssm put-parameter \
  --name /app/s3_bucket \
  --value app-data-replica-<account-id> \
  --overwrite \
  --region eu-west-1
```

---

## Phase 4: Application Scale-Up (T+5 to T+10 min)

```bash
# Scale ASG to production capacity in eu-west-1
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name app-asg-dr \
  --min-size 3 \
  --desired-capacity 6 \
  --max-size 15 \
  --region eu-west-1

# Update application config with new DB and Redis endpoints via SSM
aws ssm put-parameter --name /app/db_host --value $NEW_DB_ENDPOINT --overwrite --region eu-west-1
aws ssm put-parameter --name /app/redis_host --value $REDIS_ENDPOINT --overwrite --region eu-west-1

# Trigger rolling restart to pick up new config (if app reads config at startup)
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name app-asg-dr \
  --region eu-west-1 \
  --preferences '{"MinHealthyPercentage":50,"InstanceWarmup":60}'

# Monitor fleet health
watch -n 10 'aws elbv2 describe-target-health \
  --target-group-arn <eu-west-1-tg-arn> \
  --region eu-west-1 \
  --query "TargetHealthDescriptions[*].{Id:Target.Id,State:TargetHealth.State}"'
```

---

## Phase 5: DNS Cutover (T+10 min — POINT OF NO RETURN)

**This step routes all user traffic to eu-west-1. Confirm Phase 1–4 complete before proceeding.**

```bash
# Verify eu-west-1 ALB has healthy targets
HEALTHY=$(aws elbv2 describe-target-health \
  --target-group-arn <eu-west-1-tg-arn> \
  --region eu-west-1 \
  --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`] | length(@)' --output text)
echo "Healthy targets: $HEALTHY"  # Must be >= 2 before proceeding

# Update Route53 — weight 100% to eu-west-1
aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "app.company.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "<eu-west-1-alb-zone-id>",
          "DNSName": "<eu-west-1-alb-dns>",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'

# Verify DNS propagation (TTL = 60 seconds)
watch -n 5 'nslookup app.company.com 8.8.8.8 | grep Address'
```

---

## Phase 6: Validation (T+12 to T+15 min)

```bash
# End-to-end health check
curl -I https://app.company.com/health
curl -s https://app.company.com/api/health | python -m json.tool

# DB connectivity from eu-west-1
psql -h $NEW_DB_ENDPOINT -U admin -d appdb -c "SELECT NOW(), version();"

# Check error rates in eu-west-1 ALB
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value=<eu-west-1-alb-arn-suffix> \
  --start-time $(date -u -d '5 min ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics Sum \
  --region eu-west-1
```

**Validation checklist:**
- [ ] `app.company.com` resolves to eu-west-1 ALB IP
- [ ] Health endpoint returns 200 with `{"status": "healthy"}`
- [ ] Error rate < 1% on eu-west-1 ALB for 5 consecutive minutes
- [ ] No `FATAL` errors in application logs (CloudWatch Logs eu-west-1)
- [ ] Aurora connections > 0 in eu-west-1
- [ ] Redis cache hit rate recovering (> 50% after 10 min warm-up)

---

## Phase 7: Communication

**At T+0 (decision to failover):**
- Update status page: "We are experiencing issues in our primary region. Failover in progress."

**At T+10 (DNS cutover):**
- Update status page: "Traffic routed to DR region. Service restoring."

**At T+15 (validation complete):**
- Update status page: "Service restored. Monitoring closely."
- Post to #incidents: "Failover complete. us-east-1 → eu-west-1. Actual RTO: [X] min, RPO: [Y] min."
- Notify customer success for enterprise accounts with SLA

---

## Failback to us-east-1

After us-east-1 recovers, failback during low-traffic window:
1. Re-sync data: enable reverse replication eu-west-1 → us-east-1 Aurora
2. Wait for replication lag < 30 seconds
3. Repeat failover procedure in reverse (us-east-1 becomes writer again)
4. Scale down eu-west-1 back to warm-standby capacity
5. Expected failback time: 20–30 minutes

**Failback is lower urgency — always schedule, never emergency.**
