# Disaster Recovery FAQ for AI Agents

These FAQs are designed to answer common questions AI agents will ask when consulting on disaster recovery decisions.

## Understanding the Architecture

### Q: What is the difference between multi-AZ and multi-region redundancy?

**A:** Multi-AZ is within one region, multi-region is across continents.

- **Multi-AZ (Primary: us-east-1)**
  - RDS cluster spans us-east-1a and us-east-1b
  - Automatic failover between AZs: <30 seconds
  - Protects against: single AZ failure, hardware failure
  - Data loss: Zero (synchronous replication)

- **Multi-Region (Primary us-east-1 → Secondary us-west-2)**
  - RDS cluster in different region
  - Automatic failover: 1.5-3 minutes
  - Protects against: entire region outage
  - Data loss: Zero (continuous replication, <1 second lag)

**Agent decision:** If disaster requires region-level recovery, use secondary region. If only AZ outage, primary cluster handles automatically.

### Q: How does the system know when to failover?

**A:** Route53 health checks detect failure and Route53 routing automatically redirects.

```
Primary endpoint: postgres.c9akciq32.us-east-1.rds.amazonaws.com
  ↓ (health check every 30 seconds)
Route53: Is primary healthy? TCP port 5432 responds?
  ├─ Yes → return primary endpoint to client
  └─ No (3 failures = 90 seconds) → return secondary endpoint
Secondary endpoint: postgres-secondary.abc123.us-west-2.rds.amazonaws.com
```

**Agent decision:** Failover is automatic. No manual action needed if Route53 and secondary are both healthy.

### Q: What happens to CloudFront when S3 goes down?

**A:** CloudFront continues serving cached content for up to 24 hours.

- T=0: S3 bucket fails
- T=0-1 hour: CloudFront edge caches serve cached content (no error)
- T=1-24 hours: Expired cache → 503 Service Unavailable
- T=24+ hours: All content returns 503 until S3 is restored

**Agent decision:** S3 failures have long RTO (24 hours). Implement S3 cross-region replication and CloudFront origin failover for production.

### Q: Are writes to the secondary database possible?

**A:** No. Secondary is read-only unless explicitly promoted.

- **Primary (us-east-1):** Read + Write
- **Secondary (us-west-2):** Read-only (unless promoted after primary fails)

Writes always go to primary. Secondary is a continuous read replica.

**Agent decision:** After automatic failover, applications can read from secondary but cannot write. If persistent failover needed, manually promote secondary to read-write.

---

## Recovery Time Objectives (RTO)

### Q: How long until users are impacted after primary RDS fails?

**A:** 1.5-3 minutes (automatic failover) or 5-15 minutes (manual failover).

**Timeline:**
- 0-90 seconds: Primary RDS down, health checks detect failure
- 90-120 seconds: Route53 switches to secondary endpoint
- 120+ seconds: Client DNS refresh, connection retry
- 3 min: Application fully rerouted (assuming client retries within 30 seconds)

**Agent advice:**
- RTO is acceptable for non-critical applications
- Set client connection timeout to <30 seconds to minimize impact
- For critical applications, implement connection pooling with fast failover

### Q: What if the entire us-east-1 region goes offline?

**A:** Full failover to us-west-2 within 3-5 minutes (automatic via Route53).

**Process:**
- T=0: Region outage (all services in us-east-1 down)
- T=0-90s: Route53 health checks fail continuously
- T=90-120s: Route53 switches DNS to secondary endpoint
- T=120s-3min: Applications reconnect to secondary region
- T=3min: All traffic now routing to us-west-2

**Agent advice:**
- RPO is zero (no data loss)
- RTO is 3-5 minutes (acceptable for most applications)
- Manual failover only needed if Route53 is also down

### Q: How long to recover if secondary region fails during primary outage?

**A:** Cannot recover. This is a cascade failure.

**Scenario:**
- Primary RDS fails → Route53 switches to secondary
- But secondary is also unreachable (network partition, hardware failure)
- Result: Complete loss of database access

**Agent mitigation:**
- Test secondary health weekly: `aws rds describe-db-clusters --db-cluster-identifier postgres-secondary`
- Monitor replication lag: alert if >30 seconds
- Maintain snapshots in S3 for point-in-time recovery

---

## Recovery Point Objectives (RPO)

### Q: How much data is lost if primary RDS crashes?

**A:** Zero. Replication is synchronous at commit level.

**Guarantee:**
- All COMMITTED transactions are replicated to secondary in <1 second
- All UNCOMMITTED transactions are lost (normal database behavior)
- Example: If query fails mid-transaction, no data loss

**Agent advice:**
- RPO is <1 second (excellent)
- No backup strategy needed beyond replication
- Implement automated backups for point-in-time recovery beyond replication

### Q: What about CloudFront cache? What's the RPO for content changes?

**A:** Content changes propagate to secondary S3 within seconds, but edge caches take up to 24 hours.

**Timeline for content update:**
- T=0: Upload new version to S3 bucket
- T=0-1s: Secondary S3 bucket updated (cross-region replication)
- T=0-3600s: CloudFront edge caches still serving old content (cache TTL)
- T=3600s+: Edges fetch new content from S3 origin

**Agent decision:**
- To accelerate cache refresh, manually invalidate CloudFront: `aws cloudfront create-invalidation --distribution-id ... --paths "/*"`
- Cost: Free for first 1000/month, then $0.005 per invalidation

---

## Failover and Failback

### Q: How do we know if failover was successful?

**A:** Application can successfully connect to secondary endpoint and execute queries.

**Verification:**
```bash
# 1. Check DNS resolves to secondary
dig postgres.app.example.com +short
# Should return: postgres-secondary.abc123.us-west-2.rds.amazonaws.com

# 2. Test connection
psql -h postgres.app.example.com -U postgres -d postgres -c "SELECT now();"
# Should execute successfully

# 3. Verify no writes possible
psql -h postgres.app.example.com -U postgres -d postgres -c "INSERT INTO test VALUES (1);"
# Should fail with "read-only replica" error
```

**Agent advice:**
- Failover is successful when reads work and writes fail (read-only expected)
- If secondary is also inaccessible, investigate network between regions

### Q: How do we failback to primary after it recovers?

**A:** Update Route53 to prefer primary again. Only do this if primary is fully recovered and in sync.

**Steps:**
1. Verify primary is healthy and replication lag <5 seconds
2. Update Route53 to make primary PRIMARY again
3. Monitor failover path (ensure automatic failover still works)
4. Run post-incident review

**Agent caution:**
- Do NOT failback without verifying primary is current (check replication lag)
- Failback is risky—prefer to run on secondary for 24+ hours and monitor
- If primary diverged from secondary, manual data reconciliation needed

---

## Incidents and Troubleshooting

### Q: RDS CPU is at 100%. Should we failover?

**A:** No. Failing over will not fix the problem and will impact more users.

**Decision tree:**
```
Is primary RDS responding to queries?
├─ Yes → Keep on primary, optimize queries (add index, kill slow query, scale instance)
└─ No → Failover to secondary

Is replication lag <5 seconds?
├─ Yes → Failover is safe
└─ No → Wait for lag to catch up before failing over
```

**Agent advice:**
- High CPU is usually a slow query issue, not a hardware issue
- Killing one slow query may resolve CPU spike
- Only failover if primary is unresponsive to NEW queries

### Q: Health check says primary is healthy but DNS still points to secondary. Why?

**A:** Possible causes:
1. TTL is high (client cached old response)
2. Health check took time to recover
3. Failover routing policy is misconfigured

**Troubleshooting:**
```bash
# 1. Check current DNS
dig postgres.app.example.com +nocmd +noall +answer

# 2. Force DNS refresh on your client
nslookup postgres.app.example.com 8.8.8.8

# 3. Check Route53 failover config
aws route53 list-resource-record-sets --hosted-zone-id {ZONE_ID} \
  --query 'ResourceRecordSets[?Name==`postgres.app.example.com.`]'

# 4. Reduce TTL to 60 seconds (if currently higher)
```

**Agent advice:**
- DNS propagation takes 5-10 minutes
- TTL of 60 seconds is required for fast failover
- Do NOT increase TTL above 300 seconds

### Q: Replication lag spiked to 100 seconds. Should we failover?

**A:** No. Investigate root cause first.

**Causes of replication lag spikes:**
1. Large transaction on primary (COPY 1M rows)
2. Network congestion between regions
3. Secondary RDS is overloaded (too many read queries)

**Troubleshooting:**
```bash
# 1. Check what's running on primary
psql -h primary.rds.amazonaws.com -c "SELECT query, duration FROM pg_stat_activity WHERE duration > 10000 ORDER BY duration DESC LIMIT 5;"

# 2. Check secondary CPU/connections
aws rds describe-db-clusters --db-cluster-identifier postgres-secondary

# 3. Wait for spike to pass (usually 30-60 seconds)
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name AuroraBinlogReplicaLag --start-time ... --end-time ...
```

**Agent advice:**
- Spikes up to 30 seconds are normal during heavy writes
- Spike >30 seconds indicates a problem, but failover is extreme
- First response: identify and kill slow query, scale secondary if needed

### Q: S3 bucket is corrupted. What's our RTO?

**A:** 24 hours (max CloudFront cache TTL) unless you manually invalidate and restore.

**Options:**
1. **Restore from backup** (fast): 1-2 hours
   - Assume you have S3 versioning enabled
   - Restore previous object versions
   - Manually invalidate CloudFront cache

2. **Wait for cache to expire** (slow): 24 hours
   - No action needed
   - CloudFront continues serving from cache
   - After max_ttl, returns 503 until S3 restored

3. **Setup failover bucket** (future): 0 seconds
   - Implement secondary S3 bucket in us-west-2
   - CloudFront origin failover (not yet configured)

**Agent advice:**
- S3 failures should NOT use database failover (unrelated systems)
- Implement S3 cross-region replication for production
- RTO of 24 hours is unacceptable for most applications

---

## Monitoring and Prevention

### Q: What metrics should we monitor to prevent disasters?

**A:** These are the critical four:

| Metric | Alert Threshold | Why | Action |
|--------|-----------------|-----|--------|
| Replication Lag | >30 seconds | Stale reads, data divergence | Check network, scale secondary |
| Route53 Health Check Status | Unhealthy | Failover in progress | Monitor secondary, expect 3-5 min impact |
| RDS CPU | >85% for 5 min | Query performance degrading | Identify slow query, scale instance |
| CloudFront Error Rate | >1% 4xx/5xx | Origin issue or cache misconfiguration | Check S3 access, CloudFront logs |

**Agent advice:**
- Set up CloudWatch alarms for all four metrics
- Monitor dashboards during business hours
- Investigate alarms within 5 minutes

### Q: How often should we test failover?

**A:** Quarterly (every 3 months) for critical applications.

**Test procedure:**
1. Kill primary RDS (in test environment, or during maintenance window)
2. Verify Route53 switches to secondary within 3 minutes
3. Verify application reconnects and queries succeed
4. Document any issues, update runbook
5. Promote secondary back to read-only, verify replication resumes

**Agent advice:**
- Never test in production without pre-notification
- Test during low-traffic windows (early morning, weekends)
- Automated failover tests can be run weekly

---

## Cost and Trade-Offs

### Q: What's the cost of this multi-region setup?

**A:** Approximately $500-1000/month for RTO of 3 minutes.

**Breakdown:**
- Primary RDS (db.t4.medium): $100-150/month
- Secondary RDS (db.t4.medium): $100-150/month
- CloudFront data transfer: $50-200/month (depends on traffic)
- Route53 hosted zone: $0.50/month
- Route53 health checks: $0.50/month

**Agent cost optimization:**
- If RTO can be 10 minutes instead of 3, use smaller secondary instance (t4.small)
- If RTO can be 30 minutes, use on-demand secondary (promote only on failure)
- For non-critical apps, implement database snapshots instead of replication

### Q: What's the trade-off between RTO and cost?

**A:** Shorter RTO costs exponentially more.

| RTO | RPO | Cost | Implementation |
|-----|-----|------|-----------------|
| <1 min | <1 sec | $1000+/mo | Multi-region, multi-AZ, real-time replication |
| 3-5 min | <1 sec | $500-800/mo | Multi-region replication (current setup) |
| 10-30 min | <1 sec | $300-500/mo | On-demand secondary, snapshots |
| 1-24 hours | 1 hour | $100-200/mo | Snapshots to S3, manual restore |

**Agent recommendation:**
- For business-critical apps: Use current setup (3-5 min RTO)
- For important apps: Use on-demand secondary (10-30 min RTO)
- For non-critical apps: Use snapshots (24+ hour RTO, minimal cost)

---

**Last Updated:** 2024-01-22  
**Audience:** AI Agents, DevOps Teams, On-Call Engineers  
**Review Frequency:** Quarterly
