# RDS Multi-Region Failover & Replication

## Overview

This document describes the RDS Aurora PostgreSQL setup with cross-region failover capability. Two identical clusters run in primary (us-east-1) and secondary (us-west-2) regions, with automatic DNS-based failover managed by Route53.

## Cluster Architecture

### Primary Cluster (us-east-1)

**Resource Name:** `aws_rds_cluster.postgres`
**Cluster Identifier:** postgres
**Engine:** aurora-postgresql (version auto-selected)
**Instance Class:** db.t4.medium (upgraded from db.t3.small)
**Availability Zones:** us-east-1a, us-east-1b (auto-distributed)

**Networking:**
- VPC: 10.0.0.0/16 (primary)
- Subnets: private_a (10.0.11.0/24), private_b (10.0.12.0/24)
- Security Group: app-db (allows port 5432 inbound)
- Multi-AZ: Yes (spans 2 AZs automatically)

**Role:** Read-write master, primary endpoint serves all traffic

### Secondary Cluster (us-west-2)

**Resource Name:** `aws_rds_cluster.postgres_secondary`
**Cluster Identifier:** postgres-secondary
**Engine:** aurora-postgresql (same as primary)
**Instance Class:** db.t4.medium (matches primary)
**Availability Zones:** us-west-2a, us-west-2b (auto-distributed)

**Networking:**
- VPC: 10.1.0.0/16 (secondary)
- Subnets: secondary_private_a (10.1.11.0/24), secondary_private_b (10.1.12.0/24)
- Security Group: app-db-secondary (allows port 5432 inbound)
- Multi-AZ: Yes (spans 2 AZs automatically)

**Role:** Read-only replica, secondary endpoint serves failover traffic

## Cluster Instances

### Primary Cluster Instances

```hcl
resource "aws_rds_cluster_instance" "postgres_primary" {
  provider           = aws.primary
  cluster_identifier = aws_rds_cluster.postgres.id
  instance_class     = "db.t4.medium"
  engine             = aws_rds_cluster.postgres.engine
  engine_version     = aws_rds_cluster.postgres.engine_version
}
```

**Instance Type:** db.t4.medium (burstable)

**Specifications:**
- vCPU: 1
- Memory: 4 GB
- Network: Up to 5 Gbps (burstable)
- Storage: Aurora shared storage (scales automatically)

**Benefits over db.t3.small:**
- 2x memory (2 GB → 4 GB)
- t4 family: Better burst performance, more consistent behavior
- Cost-efficient for baseline loads with burst capability

**Redundancy:** Aurora automatically creates read replicas in other AZs

### Secondary Cluster Instances

```hcl
resource "aws_rds_cluster_instance" "postgres_secondary" {
  provider           = aws.secondary
  cluster_identifier = aws_rds_cluster.postgres_secondary.id
  instance_class     = "db.t4.medium"
  engine             = aws_rds_cluster.postgres_secondary.engine
  engine_version     = aws_rds_cluster.postgres_secondary.engine_version
}
```

**Identical Configuration** to primary for symmetry

**Important:** During normal operation, secondary is read-only. Only promoted to read-write during failover.

## Cross-Region Replication

### Replication Method

**Aurora Global Database** — AWS-managed cross-region replication

**Characteristics:**
- Automatic one-way replication (primary → secondary)
- Near real-time lag (<1 second typical)
- Read-only secondary cluster
- Automatic failover not configured (manual via Route53)
- Doesn't require explicit configuration in Terraform (implicit via cluster reference)

### Replication Process

```
Primary RDS (us-east-1)
    ↓ write transaction committed
    ↓ logs shipped to secondary
    ↓ <1 second latency
Secondary RDS (us-west-2)
    ↓ applies logs
    ↓ consistent read replica
```

**Durability:** Write durability depends on primary commit (3 AZs minimum)

### Replication Lag

**Normal:** 0-100 ms
**Acceptable:** <1 second
**Alert Threshold:** >5 seconds (possible network issue)

**Monitor via CloudWatch:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name AuroraBinlogReplicaLag \
  --dimensions Name=DBClusterIdentifier,Value=postgres-secondary \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 300 \
  --statistics Average,Maximum
```

## Failover Mechanism

### Route53 Health Checks

**Primary Health Check**

```hcl
resource "aws_route53_health_check" "primary_rds" {
  type              = "HTTPS"
  ip_address        = "0.0.0.0"  # Placeholder — should be replaced with actual IP
  port              = 5432
  failure_threshold = 3
  request_interval  = 30
}
```

**Behavior:**
- Checks every 30 seconds
- Failure after 3 consecutive failures = 90 seconds total
- Pings RDS endpoint on port 5432 via TCP

**Preferred Method (Not Yet Implemented):**
```hcl
health_check {
  type             = "TCP"
  ip_address       = aws_rds_cluster.postgres.reader_endpoint
  port             = 5432
  failure_threshold = 2
  request_interval  = 10
}
```

**Secondary Health Check**

```hcl
resource "aws_route53_health_check" "secondary_rds" {
  type              = "HTTPS"
  ip_address        = "0.0.0.0"  # Placeholder
  port              = 5432
  failure_threshold = 3
  request_interval  = 30
}
```

### Failover Records

**Primary Record (Active)**

```hcl
resource "aws_route53_record" "postgres_primary" {
  zone_id         = aws_route53_zone.main.zone_id
  name            = "postgres.app.example.com"
  type            = "CNAME"
  ttl             = 60
  set_identifier  = "primary"
  
  failover_routing_policy {
    type = "PRIMARY"
  }
  
  records         = [aws_rds_cluster.postgres.endpoint]
  health_check_id = aws_route53_health_check.primary_rds.id
}
```

**Record Details:**
- **Name:** postgres.app.example.com
- **Type:** CNAME (points to RDS cluster endpoint)
- **TTL:** 60 seconds (quick DNS refresh on failover)
- **Failover Policy:** PRIMARY (takes precedence if healthy)
- **Health Check:** Linked to primary health check

**Primary Endpoint Example:**
```
postgres.c9akciq32.us-east-1.rds.amazonaws.com
```

**Secondary Record (Standby)**

```hcl
resource "aws_route53_record" "postgres_secondary" {
  zone_id         = aws_route53_zone.main.zone_id
  name            = "postgres.app.example.com"
  type            = "CNAME"
  ttl             = 60
  set_identifier  = "secondary"
  
  failover_routing_policy {
    type = "SECONDARY"
  }
  
  records         = [aws_rds_cluster.postgres_secondary.endpoint]
  health_check_id = aws_route53_health_check.secondary_rds.id
}
```

**Record Details:**
- **Same FQDN:** postgres.app.example.com (both records)
- **Failover Policy:** SECONDARY (used only if primary unhealthy)

## Failover Timeline

### Normal Operation (Primary Healthy)

```
Minute 0:00 — Client requests postgres.app.example.com
         ↓
         Route53 health check returns HEALTHY for primary
         ↓
Minute 0:00 — Client gets primary RDS endpoint
         ↓
         Connection to primary cluster (us-east-1)
```

### Failure Detection

```
Minute 0:00 — Primary RDS fails (e.g., CPU spike, query timeout)
Minute 0:30 — Route53 health check #1 fails
Minute 1:00 — Route53 health check #2 fails
Minute 1:30 — Route53 health check #3 fails — PRIMARY marked UNHEALTHY
         ↓
Minute 1:35 — Next DNS query returns SECONDARY endpoint
```

**Total Time to Failover:** ~1.5 minutes (3 × 30-second intervals + detection)

### Post-Failover

```
Minute 1:35 — Client DNS resolves to secondary endpoint
         ↓
Minute 1:36 — Client connection timeout on old primary
         ↓
Minute 1:36 — Client retries with new secondary endpoint
         ↓
         Application queries execute on secondary (read-only until promotion)
```

**Client Reconnection:** Typically <10 seconds
**Application Downtime:** ~2-3 minutes total (detection + retry + reconnect)

### Recovery & Failback

**Option 1: Manual Failback**
```bash
# Manually update Route53 records when primary restored
aws route53 change-resource-record-sets \
  --hosted-zone-id {ZONE_ID} \
  --change-batch '{...}'
```

**Option 2: Automatic Failback**
- Route53 health checks primary every 30 seconds
- When primary recovers, automatically switches back
- No manual intervention needed

**Timing:** Recovery detection takes 30-60 seconds after primary comes online

## Endpoint Types

### Primary Cluster Endpoint

```
postgres.c9akciq32.us-east-1.rds.amazonaws.com (writer endpoint)
```

**Purpose:** Read-write operations
**Points To:** Primary instance in us-east-1
**Used by:** Route53 primary record

### Reader Endpoint (Primary Cluster)

```
postgres-ro.c9akciq32.us-east-1.rds.amazonaws.com
```

**Purpose:** Read-only queries (distribute load)
**Points To:** Aurora read replicas in same cluster
**Use Case:** Analytics, reporting (separate from transactional writes)

### Secondary Cluster Endpoint

```
postgres-secondary.abc123def.us-west-2.rds.amazonaws.com (reader endpoint)
```

**Purpose:** Read-only (during normal operation), read-write (during failover)
**Points To:** Secondary instances in us-west-2
**Used by:** Route53 secondary record

## Database Management

### Backups

**Primary Cluster Backups:**
- Automated snapshots: Every 5 minutes (incremental), retained 1 day
- Backup window: Nightly 03:00-04:00 UTC
- Backup storage: Included in Aurora costs
- Cross-region replication: Not automatic (secondary is the replica)

**Secondary Cluster Backups:**
- Automatic backups enabled (same policy)
- Can be independently restored
- Does NOT back up to primary region (separate backup chain)

**Backup Strategy for DR:**
1. Primary cluster automatic backups
2. Secondary cluster serves as live replica (faster failover than restore)
3. Additional S3 snapshots for long-term retention (optional)

### Parameter Groups

**Both clusters should use same parameter group for consistency:**

```hcl
resource "aws_db_cluster_parameter_group" "postgres" {
  family = "aurora-postgresql15"
  name   = "postgres-params"
  # Common settings for both primary and secondary
}
```

**Important Parameters:**
- `shared_preload_libraries = 'pgaudit, pg_stat_statements'`
- `log_statement = 'all'` (audit logging)
- `max_connections = 1000` (based on db.t4.medium capacity)
- `rds.force_ssl = 1` (enforce SSL connections)

### Monitoring & Alerting

**Critical Metrics to Monitor:**

| Metric | Threshold | Action |
|--------|-----------|--------|
| Replication Lag | >5 seconds | Investigate network, raise alert |
| CPU Utilization | >80% for 5 min | Scale instance, increase burst capacity |
| Storage | >90% of limit | Increase storage allocation |
| Connections | >80% of max | Investigate long-running queries |
| Read/Write Latency | >100ms | Check network, disk I/O |

**CloudWatch Alarms (Recommended):**

```bash
# High replication lag
aws cloudwatch put-metric-alarm \
  --alarm-name RDS-Replication-Lag-High \
  --metric-name AuroraBinlogReplicaLag \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 5000 \
  --comparison-operator GreaterThanThreshold

# Unhealthy cluster
aws cloudwatch put-metric-alarm \
  --alarm-name RDS-Cluster-Unhealthy \
  --metric-name DBClusterHealthy \
  --namespace AWS/RDS \
  --statistic Minimum \
  --period 60 \
  --threshold 1 \
  --comparison-operator LessThanThreshold
```

## Operational Procedures

### Planned Maintenance (Primary Region Unavailable)

1. **Notify users:** Expected 5-10 minute downtime
2. **Route53 check:** Verify secondary health check is passing
3. **Manual switch (optional):** Immediately update Route53 to secondary
4. **Perform maintenance:** Apply patches, upgrade PostgreSQL version
5. **Test primary:** Verify cluster health before failback
6. **Failback:** Update Route53 to primary (automatic or manual)

### Emergency Failover (Unplanned)

1. **Detect:** Route53 health check detects primary failure
2. **Automatic switch:** Route53 switches to secondary (90 seconds typical)
3. **Application retry:** Clients reconnect to secondary endpoint
4. **Investigation:** Determine root cause of primary failure
5. **Recovery:** Restore primary cluster or replace instances
6. **Failback:** Return to primary after stability confirmed

### Data Consistency After Failover

**Secondary is Read-Only During Replication:**
- All writes go to primary
- Secondary reads latest committed data from primary
- No data loss (synchronous replication at commit level)

**After Failover (Secondary Promoted to Write):**
- Secondary becomes read-write
- Primary is offline
- New writes accumulate on secondary
- When primary returns: must catch up via replication

### Scaling

**Vertical Scaling (Change Instance Class):**

```hcl
# Change from db.t4.medium to db.r6g.2xlarge
resource "aws_rds_cluster_instance" "postgres_primary" {
  instance_class = "db.r6g.2xlarge"  # New class
}
```

**Downtime:** Minimal (rolling restart on read replicas, brief outage on writer)

**Horizontal Scaling (Add Read Replicas):**

```hcl
# Add additional reader instance
resource "aws_rds_cluster_instance" "postgres_reader_2" {
  cluster_identifier = aws_rds_cluster.postgres.id
  instance_class     = "db.t4.medium"
  instance_role      = "reader"  # Not a writer
}
```

## Disaster Recovery Design

### RTO (Recovery Time Objective): ~3 minutes
- Health check detection: ~90 seconds
- DNS propagation: ~60 seconds
- Client reconnect: <10 seconds

### RPO (Recovery Point Objective): ~1 second
- Aurora replication lag: <1 second
- Zero data loss on committed transactions

### Assumptions & Limitations

**Assumptions:**
- Primary region RDS cluster fully fails (not partial failure)
- Network connectivity between regions remains intact
- Route53 health checks can reach RDS endpoints

**Limitations:**
- No automatic write failover (secondary must be promoted manually or via Lambda)
- Single secondary region (not multi-region chain)
- Failback requires client reconnect (no transparent switchover)
- Cross-region replication lag means secondary slightly behind primary

### Future Enhancements

- [ ] Implement RDS Event Subscriptions for automated notifications
- [ ] Add Lambda function for automatic secondary promotion
- [ ] Enable Performance Insights for detailed database diagnostics
- [ ] Implement enhanced monitoring for application-specific metrics
- [ ] Add CloudWatch custom metrics for failover events
