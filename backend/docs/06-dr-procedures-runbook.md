# Disaster Recovery Procedures Runbook

## Quick Reference: When to Failover

| Scenario | Decision | Action | Time |
|----------|----------|--------|------|
| Primary RDS CPU >95% for 5 min | Wait for autoscaling | Monitor, no failover | N/A |
| Primary RDS unresponsive | Automatic → Secondary | Route53 detects (90s) | ~3 min |
| Primary region outage (all services down) | Manual failover | Update Route53 record | Immediate |
| Replication lag >30 seconds | Alert and investigate | Check network, don't failover | N/A |
| Secondary region healthy? | Check before promoting | Verify secondary_rds endpoint | 60s |

## Procedure 1: Automatic Failover (RDS Primary Fails)

**Trigger:** Route53 health check detects primary RDS unresponsive (TCP port 5432 fails 3x every 30 seconds)

### Timeline

```
Minute 0:00 — Primary RDS fails (CPU spike, query timeout, or crash)
Minute 0:30 — Health check attempt #1 fails
Minute 1:00 — Health check attempt #2 fails
Minute 1:30 — Health check attempt #3 fails → PRIMARY marked UNHEALTHY
Minute 1:35 — Route53 automatically resolves postgres.app.example.com to secondary endpoint
Minute 1:36 — Client connection timeout on old primary
Minute 1:37 — Client retries → connects to secondary (read-only)
Minute 2:00 — Application fully rerouted to secondary
```

**What the agent should advise:**
- RTO is 1.5-3 minutes (Route53 health check detection + DNS propagation)
- RPO is <1 second (replication lag is synchronous at commit level)
- No data loss on committed transactions
- Secondary is read-only until manually promoted
- Primary can be recovered in parallel without affecting failover

### Manual Steps (if automatic failover doesn't trigger)

```bash
# 1. Verify secondary is healthy
aws rds describe-db-clusters \
  --db-cluster-identifier postgres-secondary \
  --region us-west-2 \
  --query 'DBClusters[0].Status'

# 2. Check replication lag
aws rds describe-db_clusters \
  --db-cluster-identifier postgres-secondary \
  --region us-west-2 \
  --query 'DBClusters[0].ReplicationSourceIdentifier'

# 3. If lag is acceptable (<5 seconds), manually update Route53
aws route53 change-resource-record-sets \
  --hosted-zone-id {ZONE_ID} \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "postgres.app.example.com",
        "Type": "CNAME",
        "TTL": 60,
        "SetIdentifier": "secondary",
        "FailoverRoutingPolicy": {"Type": "PRIMARY"},
        "ResourceRecords": [{"Value": "postgres-secondary.abc123.us-west-2.rds.amazonaws.com"}]
      }
    }]
  }'

# 4. Promote secondary to read-write (permanent failover only)
aws rds modify-db-cluster \
  --db-cluster-identifier postgres-secondary \
  --region us-west-2 \
  --enable-iam-database-authentication
```

## Procedure 2: Planned Maintenance (Taking Primary Offline)

**Use case:** Apply security patches, upgrade PostgreSQL version, resize instance

### Steps

1. **Notify operations team:** Expected 5-10 minute downtime
2. **Verify secondary health:**
   ```bash
   aws rds describe-db-clusters --db-cluster-identifier postgres-secondary \
     --region us-west-2 --query 'DBClusters[0].Status'
   ```
3. **Optional: Force immediate failover to secondary** (skip health check wait)
   ```bash
   # Manually update Route53 to use secondary as PRIMARY
   ```
4. **Perform maintenance on primary:**
   ```bash
   # Apply patches
   aws rds modify-db-cluster \
     --db-cluster-identifier postgres \
     --apply-immediately \
     --engine-version 15.3
   # Wait for completion (10-20 minutes)
   ```
5. **Monitor replication lag** during maintenance
6. **Test primary cluster** after update completes
7. **Failback to primary** (automatic or manual)

### What agents should know:
- Planned maintenance can be coordinated with low-traffic windows
- Secondary remains read-only throughout—no service interruption if configured correctly
- Replication lag must be <5 seconds before maintenance starts
- If replication fails during maintenance, secondary cannot serve as backup

## Procedure 3: Secondary Region Promotion (Permanent Failover)

**Use case:** Primary region is destroyed or unrecoverable

### Steps

1. **Assess primary region:**
   ```bash
   # Can it be recovered in <1 hour?
   # If yes → skip promotion, focus on recovery
   # If no → proceed to promotion
   ```

2. **Verify secondary replication lag:**
   ```bash
   aws rds describe-db-clusters \
     --db-cluster-identifier postgres-secondary \
     --region us-west-2 \
     --query 'DBClusters[0].GlobalWriteForwardingStatus'
   ```

3. **Promote secondary to read-write:**
   ```bash
   # THIS IS PERMANENT — primary will become secondary when it recovers
   aws rds modify-db-cluster \
     --db-cluster-identifier postgres-secondary \
     --region us-west-2 \
     --enable-iam-database-authentication
   # Wait for status change to "Available" (~5-10 minutes)
   ```

4. **Update application connection strings** (if hardcoded):
   ```bash
   # From: postgres.c9akciq32.us-east-1.rds.amazonaws.com
   # To: postgres-secondary.abc123def.us-west-2.rds.amazonaws.com
   ```

5. **Update Route53 record:**
   ```bash
   aws route53 change-resource-record-sets \
     --hosted-zone-id {ZONE_ID} \
     --change-batch '{
       "Changes": [{
         "Action": "UPSERT",
         "ResourceRecordSet": {
           "Name": "postgres.app.example.com",
           "Type": "CNAME",
           "TTL": 60,
           "SetIdentifier": "secondary",
           "FailoverRoutingPolicy": {"Type": "PRIMARY"},
           "ResourceRecords": [{"Value": "postgres-secondary.abc123def.us-west-2.rds.amazonaws.com"}]
         }
       }]
     }'
   ```

6. **Verify all writes are going to new primary:**
   ```bash
   psql -h postgres.app.example.com -U postgres -d postgres \
     -c "INSERT INTO health_check (status) VALUES ('promoted');"
   ```

7. **Establish new replication** from secondary back to recovered primary (when it comes online)

### What agents should know:
- Permanent promotion takes 10-15 minutes total (5-10 for promotion + 5 for DNS propagation)
- Applications will be in read-only mode for a brief window during promotion
- Once promoted, the original primary becomes a read-only replica (role reversal)
- Data consistency is maintained—no transactions are lost

## Procedure 4: Recovering Primary After Failover

**Use case:** Primary region recovered but secondary is now active

### Steps

1. **Assess primary cluster health:**
   ```bash
   aws rds describe-db-clusters \
     --db-cluster-identifier postgres \
     --region us-east-1 \
     --query 'DBClusters[0]'
   ```

2. **Check if primary has diverged from secondary:**
   - If failover was automatic → Primary is stale, secondary is current
   - If failover was manual during maintenance → Primary is current
   
3. **Failback strategy:**
   
   **Option A: Promote primary back (if it's current)**
   ```bash
   # Only if replication was continuous
   aws route53 change-resource-record-sets \
     --hosted-zone-id {ZONE_ID} \
     --change-batch '{
       "Changes": [{
         "Action": "UPSERT",
         "ResourceRecordSet": {
           "Name": "postgres.app.example.com",
           "Type": "CNAME",
           "TTL": 60,
           "SetIdentifier": "primary",
           "FailoverRoutingPolicy": {"Type": "PRIMARY"},
           "ResourceRecords": [{"Value": "postgres.c9akciq32.us-east-1.rds.amazonaws.com"}]
         }
       }]
     }'
   ```

   **Option B: Rebuild primary as read-only replica (if secondary is current)**
   ```bash
   # Destroy and recreate primary RDS cluster
   # Set up replication from secondary back to primary
   # Then promote primary back to PRIMARY role
   ```

4. **Monitor replication lag** until sync is complete
5. **Test failover path** to ensure automatic failover still works

### What agents should know:
- Failback should happen during low-traffic window
- Automatic failover does NOT automatically failback—it requires manual intervention
- If primary diverged from secondary, data loss is possible—investigate discrepancies first
- Failback is risky and should be done incrementally (test in non-prod first)

## Procedure 5: CloudFront Cache Invalidation (S3 Bucket Failure)

**Scenario:** S3 bucket is corrupted or inaccessible, CloudFront edge caches are stale

### Timeline

```
Minute 0:00 — S3 bucket goes down
Minute 0:00 — CloudFront edge caches are still serving (cache hit)
Minute 1:00 — Cache TTL expires on some edges (regional variation)
Minute 24:00 — Max TTL reached, all edges must fetch from S3
Minute 24:00+ — CloudFront returns 503 (Service Unavailable) for all requests
```

### Recovery Options

**Option 1: Restore S3 bucket quickly**
```bash
# Restore from CloudFront origin (if backup exists)
# Usually takes 1-2 hours
```

**Option 2: Serve cached content indefinitely**
```bash
# Increase max_ttl in CloudFront to 31536000 (1 year)
# Update cache headers in S3 objects
# Requires CloudFront cache invalidation after restoration
```

**Option 3: Setup failover origin (future)**
```bash
# Create secondary S3 bucket in us-west-2
# Configure CloudFront origin failover
# Automatic redirect to secondary bucket
```

### Current procedure:

```bash
# 1. Manually invalidate CloudFront cache (forces re-fetch from S3)
aws cloudfront create-invalidation \
  --distribution-id {DISTRIBUTION_ID} \
  --paths "/*"

# 2. Wait for S3 to be restored

# 3. Verify S3 bucket is accessible
aws s3 ls s3://app-content-{ACCOUNT_ID}

# 4. Check invalidation status
aws cloudfront get-invalidation \
  --distribution-id {DISTRIBUTION_ID} \
  --id {INVALIDATION_ID}
```

### What agents should know:
- S3 failures affect CDN but cached content protects against brief outages
- RTO for S3 failures can be 24 hours (max TTL) without manual action
- CloudFront invalidations cost $0.005 per invalidation (after 1000 free/month)
- Cross-region S3 replication is not yet enabled—secondary bucket should be added

## Monitoring & Alert Thresholds

**Critical metrics agents should check:**

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| Replication Lag | >5 seconds | Investigate network, check Route53 health check status |
| Primary RDS CPU | >85% for 5 min | Scale up instance or optimize queries |
| Primary RDS Connections | >80% of max | Identify long-running queries, kill if needed |
| Route53 Health Check | Unhealthy | Automatic failover triggered, monitor secondary |
| CloudFront Cache Hit Ratio | <70% | Review cache TTL settings, check origin latency |
| S3 Access Errors (4xx/5xx) | >1% of requests | Check bucket policy, CloudFront OAC configuration |

## Emergency Contact Tree

```
Primary on-call:    [phone/email]
Secondary on-call:  [phone/email]
AWS Support:        [premium support case]
Database team:      [slack channel: #db-emergencies]
Network team:       [slack channel: #network-ops]
```

---

**Last Updated:** 2024-01-22  
**Tested By:** DevOps Team  
**Next Review:** 2024-04-22
