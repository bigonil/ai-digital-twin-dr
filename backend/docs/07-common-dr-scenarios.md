# Common Disaster Recovery Scenarios

## Scenario 1: Primary RDS Database Becomes Unresponsive

**Symptoms:**
- Application logs: `Connection timeout to postgres.app.example.com:5432`
- CloudWatch: RDS CPU at 100%, queries timing out
- Route53: Health check failing

**Root Causes:**
- Runaway query (JOIN on unindexed column)
- Out of memory (max_connections exceeded)
- Storage full (disk space exhausted)
- Network partition between app and database

**Diagnosis Steps:**

```bash
# 1. Can you connect to primary?
psql -h postgres.c9akciq32.us-east-1.rds.amazonaws.com -U postgres -d postgres
# If connection refused → database is down

# 2. Check RDS cluster status
aws rds describe-db-clusters --db-cluster-identifier postgres --region us-east-1

# 3. Check active queries
psql -c "SELECT pid, usename, query, state FROM pg_stat_activity WHERE state != 'idle';"

# 4. Check connections
psql -c "SELECT count(*) FROM pg_stat_activity;"

# 5. Check disk usage
psql -c "SELECT pg_database.datname, 
    pg_size_pretty(pg_database_size(pg_database.datname)) 
    FROM pg_database 
    ORDER BY pg_database_size(pg_database.datname) DESC;"
```

**Decision Tree:**

```
Is disk full (>95%)?
├─ Yes → Delete old logs/backups, increase storage (wait 5 min)
└─ No → Continue

Are connections maxed out?
├─ Yes → Kill idle connections, increase max_connections parameter
└─ No → Continue

Is CPU at 100%?
├─ Yes → Identify slow query with pg_stat_statements
│        Kill query: SELECT pg_terminate_backend(pid)
│        Add index: CREATE INDEX ... on unindexed column
└─ No → Continue

Is network reachable?
├─ Yes → Primary is healthy, might be app-side issue
└─ No → Network partition, failover to secondary
```

**Resolution:**

1. **If recoverable** (5-10 min):
   - Kill slow queries: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%slowquery%';`
   - Increase memory: `SET work_mem = '256MB';`
   - Add indexes to slow tables
   - Monitor recovery, do NOT failover

2. **If unrecoverable** (>10 min):
   - Initiate automatic failover (Route53 handles this)
   - Or manually failover to secondary
   - Primary becomes read-only replica
   - Investigate root cause post-incident

**Prevention:**

- Monitor top 10 slowest queries daily
- Set up CloudWatch alarm: RDS CPU >80% for 5 minutes
- Implement connection pooling (PgBouncer, Hikari)
- Regular VACUUM and ANALYZE maintenance

---

## Scenario 2: Entire Primary Region Goes Offline

**Symptoms:**
- All AWS services in us-east-1 unreachable
- CloudFront still serving cached content
- RDS primary endpoint unresponsive
- DNS resolves but connections timeout

**Root Causes:**
- AWS regional outage (rare, but happened: us-east-1 outage 2021)
- VPC or security group misconfiguration
- Internet Gateway removed or route table corrupted
- DDoS attack on region

**Diagnosis Steps:**

```bash
# 1. Check AWS status page
curl https://status.aws.amazon.com/ | grep us-east-1

# 2. Try reaching any service in us-east-1
aws s3 ls --region us-east-1

# 3. Check if secondary region is up
aws rds describe-db-clusters --db-cluster-identifier postgres-secondary --region us-west-2

# 4. Verify Route53 health checks
aws route53 get-health-check-status --health-check-id {CHECK_ID}
```

**Resolution:**

1. **Automatic failover** (if Route53 health checks work):
   - Route53 detects primary is down (~90 seconds)
   - Automatically switches DNS to secondary endpoint
   - Applications reconnect to postgres-secondary in us-west-2
   - RTO: ~3 minutes, RPO: <1 second

2. **Manual failover** (if Route53 is also down):
   - Update application connection string manually to `postgres-secondary.abc123.us-west-2.rds.amazonaws.com`
   - Promote secondary to read-write: `aws rds modify-db-cluster --db-cluster-identifier postgres-secondary --region us-west-2`
   - RTO: ~15 minutes, RPO: <1 second

3. **CloudFront behavior**:
   - Edge caches continue serving cached content
   - New requests fail after 24-hour TTL expires
   - No intervention needed—CDN keeps serving old content temporarily

**Prevention:**

- Multi-region architecture (you have it: us-east-1 + us-west-2)
- Route53 health checks with proper failover configuration
- Redundant DNS (Route53 is managed by AWS, highly available)
- Regular failover drills (test secondary promotion quarterly)

---

## Scenario 3: Replication Lag Spikes (>30 seconds)

**Symptoms:**
- Reads from secondary are stale
- Application shows "eventual consistency" warnings
- CloudWatch metric: `AuroraBinlogReplicaLag > 30000 ms`

**Root Causes:**
- Network congestion between regions
- Large transaction on primary (COPY, bulk INSERT)
- Secondary cluster is overloaded (read queries)
- Replication queue building up

**Diagnosis Steps:**

```bash
# 1. Check replication lag
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name AuroraBinlogReplicaLag \
  --dimensions Name=DBClusterIdentifier,Value=postgres-secondary \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average,Maximum

# 2. Check network latency between regions
ping -c 5 postgres-secondary.abc123.us-west-2.rds.amazonaws.com

# 3. Check secondary RDS CPU and connections
aws rds describe-db-clusters --db-cluster-identifier postgres-secondary --region us-west-2

# 4. Check transaction log shipping
psql -U postgres -h postgres.c9akciq32.us-east-1.rds.amazonaws.com \
  -c "SELECT slot_name, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots;"
```

**Resolution:**

1. **If lag is temporary** (<1 minute spike):
   - Do nothing, lag will catch up automatically
   - Applications should handle eventual consistency

2. **If lag is persistent** (>5 seconds for >10 minutes):
   - Kill long-running reads on secondary: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND duration > 60000;`
   - Scale up secondary instance class (db.t4.large)
   - Check network path: `mtr -c 100 10.1.11.1` (from primary to secondary)

3. **If lag is caused by large transaction**:
   - Wait for transaction to complete (monitor lock table)
   - Optimize transaction: `COPY` instead of INSERT, disable triggers, batch operations
   - Schedule large operations during low-traffic windows

**Prevention:**

- Monitor replication lag continuously (alert >5 seconds)
- Avoid long-running transactions during peak traffic
- Batch large operations (1000 rows at a time, not 1M rows)
- Use connection pooling to avoid connection storms

---

## Scenario 4: CloudFront Returns 503 (Origin Unreachable)

**Symptoms:**
- HTTP 503 Service Unavailable from CloudFront edge
- Cached content should still be served
- S3 bucket logs show access errors

**Root Causes:**
- S3 bucket deleted or access denied
- S3 bucket policy doesn't allow CloudFront
- CloudFront OAC (Origin Access Control) misconfigured
- S3 bucket is in wrong region

**Diagnosis Steps:**

```bash
# 1. Verify S3 bucket exists and has objects
aws s3 ls s3://app-content-{ACCOUNT_ID} --region us-east-1

# 2. Check S3 bucket policy
aws s3api get-bucket-policy --bucket app-content-{ACCOUNT_ID}

# 3. Verify CloudFront distribution configuration
aws cloudfront get-distribution --id {DISTRIBUTION_ID}

# 4. Check CloudFront origin access
aws cloudfront get-distribution-config --id {DISTRIBUTION_ID} | jq '.DistributionConfig.Origins[0]'

# 5. Try direct S3 access (should fail if OAC is configured correctly)
curl -I https://app-content-{ACCOUNT_ID}.s3.amazonaws.com/index.html
# Should return 403 Forbidden (only CloudFront can access)
```

**Resolution:**

1. **Restore S3 bucket**:
   ```bash
   # If deleted, restore from backup
   # If access denied, fix bucket policy
   aws s3api put-bucket-policy --bucket app-content-{ACCOUNT_ID} --policy file://bucket-policy.json
   ```

2. **Verify CloudFront can reach origin**:
   ```bash
   # CloudFront will automatically retry failed requests
   # Monitor error rate: AWS Console → CloudFront → Monitoring → Error Rate
   ```

3. **Invalidate CloudFront cache** (optional, accelerates propagation):
   ```bash
   aws cloudfront create-invalidation --distribution-id {DISTRIBUTION_ID} --paths "/*"
   ```

**Prevention:**

- S3 bucket versioning enabled (can recover deleted objects)
- CloudFront origin shield enabled (extra caching layer)
- Regular validation: `curl -H "X-Cache-Status" https://cdn.app.example.com/test.txt`
- Monitor 5xx error rate in CloudWatch

---

## Scenario 5: DNS Failover Not Working

**Symptoms:**
- Application always connects to primary endpoint
- Health check shows secondary is healthy but DNS doesn't switch
- Manual DNS updates don't take effect

**Root Causes:**
- TTL too high (clients cached old DNS response)
- Route53 health check is broken
- Health check failing but Route53 not switching
- Failover routing policy misconfigured

**Diagnosis Steps:**

```bash
# 1. Check Route53 record configuration
aws route53 list-resource-record-sets --hosted-zone-id {ZONE_ID} \
  --query 'ResourceRecordSets[?Name==`postgres.app.example.com.`]'

# 2. Check health check status
aws route53 get-health-check-status --health-check-id {CHECK_ID}

# 3. Verify DNS resolution
dig postgres.app.example.com +short
# Should return primary RDS endpoint

# 4. Force DNS refresh (on client machine)
nslookup -type=A postgres.app.example.com 8.8.8.8
# Should show current endpoint

# 5. Check CloudWatch health check metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Route53 \
  --metric-name HealthCheckStatus \
  --dimensions Name=HealthCheckId,Value={CHECK_ID} \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Minimum
```

**Resolution:**

1. **If TTL is too high**:
   ```bash
   # Reduce TTL to 60 seconds
   aws route53 change-resource-record-sets --hosted-zone-id {ZONE_ID} \
     --change-batch '{"Changes": [{"Action": "UPSERT", "ResourceRecordSet": {"Name": "postgres.app.example.com", "Type": "CNAME", "TTL": 60, "ResourceRecords": [{"Value": "..."}]}}]}'
   # Wait for propagation (5-10 minutes)
   ```

2. **If health check is broken**:
   ```bash
   # Verify health check target is correct
   aws route53 get-health-check --health-check-id {CHECK_ID}
   
   # Test health check target manually
   nc -zv postgres.c9akciq32.us-east-1.rds.amazonaws.com 5432
   # Should connect successfully if healthy
   ```

3. **If failover policy is wrong**:
   - Ensure primary record has `failover_routing_policy: {type: PRIMARY}`
   - Ensure secondary record has `failover_routing_policy: {type: SECONDARY}`
   - Both records must have same FQDN (`postgres.app.example.com`)

**Prevention:**

- Reduce TTL to 60 seconds (not 300 or 3600)
- Test health checks weekly: `aws route53 test-dns-answer --hosted-zone-id {ZONE_ID} --record-name postgres.app.example.com --record-type CNAME`
- Monitor Route53 health check status in CloudWatch
- Setup CloudWatch alarm on health check failures

---

## Quick Decision Matrix

| **What's broken?** | **RTO** | **RPO** | **Automatic?** | **What to do** |
|---|---|---|---|---|
| Primary RDS unresponsive | 1.5-3 min | <1s | Yes | Wait for Route53 failover |
| Primary region offline | 3-5 min | <1s | Yes (if Route53 up) | Manual failover if Route53 down |
| Replication lag >30s | N/A | Risk of stale reads | No | Kill slow reads, scale secondary |
| S3 bucket down | 24h (max TTL) | Full | No | Restore bucket or add failover |
| DNS not switching | 5-60 min | Depends | No | Check TTL, health checks, policy |

---

**Last Updated:** 2024-01-22  
**Common Incident Resolution Time:** 3-15 minutes  
**Escalation Path:** See Procedure 5 for contact tree
