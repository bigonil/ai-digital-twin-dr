# Infrastructure Dependencies & Relationships

## Dependency Graph

```
aws_vpc.primary (10.0.0.0/16)
├── aws_subnet.primary_a (10.0.1.0/24)
├── aws_subnet.primary_b (10.0.2.0/24)
├── aws_subnet.private_a (10.0.11.0/24)
│   └── aws_rds_cluster_instance.postgres_primary
├── aws_subnet.private_b (10.0.12.0/24)
│   └── aws_rds_cluster_instance.postgres_primary
├── aws_security_group.db
│   └── aws_rds_cluster.postgres
│       ├── aws_db_subnet_group.postgres
│       │   ├── aws_subnet.private_a
│       │   └── aws_subnet.private_b
│       └── DEPENDS_ON: aws_rds_cluster.postgres_secondary
│
└── aws_s3_bucket.origin
    └── aws_cloudfront_distribution.main

aws_vpc.secondary (10.1.0.0/16)
├── aws_subnet.secondary_private_a (10.1.11.0/24)
│   └── aws_rds_cluster_instance.postgres_secondary
├── aws_subnet.secondary_private_b (10.1.12.0/24)
│   └── aws_rds_cluster_instance.postgres_secondary
├── aws_security_group.db_secondary
│   └── aws_rds_cluster.postgres_secondary
│       ├── aws_db_subnet_group.postgres_secondary
│       │   ├── aws_subnet.secondary_private_a
│       │   └── aws_subnet.secondary_private_b
│       └── READS_FROM: aws_rds_cluster.postgres (replication)

Route53
├── aws_route53_zone.main
│   ├── aws_route53_record.postgres_primary
│   │   ├── DEPENDS_ON: aws_route53_health_check.primary_rds
│   │   └── POINTS_TO: aws_rds_cluster.postgres.endpoint
│   │
│   └── aws_route53_record.postgres_secondary
│       ├── DEPENDS_ON: aws_route53_health_check.secondary_rds
│       └── POINTS_TO: aws_rds_cluster.postgres_secondary.endpoint
```

## Relationship Types (Neo4j Labels)

When the Terraform parser ingests these resources into Neo4j, relationships are created using the `DEPENDS_ON` edge type for explicit references:

### Explicit DEPENDS_ON (Terraform References)

```
aws_db_subnet_group.postgres --[DEPENDS_ON]-> aws_subnet.private_a
aws_db_subnet_group.postgres --[DEPENDS_ON]-> aws_subnet.private_b
aws_rds_cluster.postgres --[DEPENDS_ON]-> aws_security_group.db
aws_rds_cluster.postgres --[DEPENDS_ON]-> aws_db_subnet_group.postgres
aws_rds_cluster_instance.postgres_primary --[DEPENDS_ON]-> aws_rds_cluster.postgres
aws_cloudfront_distribution.main --[DEPENDS_ON]-> aws_s3_bucket.origin
aws_route53_record.postgres_primary --[DEPENDS_ON]-> aws_route53_health_check.primary_rds
aws_route53_record.postgres_secondary --[DEPENDS_ON]-> aws_route53_health_check.secondary_rds
```

### Implicit DEPENDS_ON (Documented via Comments)

```
# In Terraform: aws_rds_cluster.postgres_secondary has comment:
# DEPENDS_ON: aws_rds_cluster.postgres (primary region)

# Parser recognizes comment pattern and may create:
aws_rds_cluster.postgres_secondary --[DEPENDS_ON]-> aws_rds_cluster.postgres
```

**Note:** Current parser doesn't extract comments. Future enhancement could parse `# DEPENDS_ON: resource_type.resource_name` comments.

## Cross-Region Dependencies

### Replication Relationship

```
aws_rds_cluster.postgres (us-east-1, primary)
    --[REPLICATES_TO]->
aws_rds_cluster.postgres_secondary (us-west-2, secondary)
```

**Direction:** Primary → Secondary (one-way replication)
**Type:** Master-Replica relationship
**Latency:** <1 second typical
**Data Consistency:** Synchronous at commit level

### Failover Relationship

```
aws_route53_record.postgres_primary
    --[FAILOVER_TO]->
aws_route53_record.postgres_secondary
```

**Type:** DNS failover policy
**Trigger:** Health check failure on primary
**Automatic:** Yes (Route53 manages)

## Resource Dependencies by Type

### VPC & Networking

| Resource | Depends On | Reason |
|----------|-----------|--------|
| aws_subnet.private_a | aws_vpc.primary | Subnet must belong to VPC |
| aws_security_group.db | aws_vpc.primary | SG must belong to VPC |
| aws_db_subnet_group.postgres | aws_subnet.private_a, aws_subnet.private_b | Group lists subnets for RDS placement |

### Database Layer

| Resource | Depends On | Reason |
|----------|-----------|--------|
| aws_rds_cluster.postgres | aws_security_group.db, aws_db_subnet_group.postgres | Cluster requires security and subnet config |
| aws_rds_cluster_instance.postgres_primary | aws_rds_cluster.postgres | Instance must belong to cluster |
| aws_rds_cluster.postgres_secondary | (implicit) aws_rds_cluster.postgres | Secondary replicates from primary |

### CDN & Content

| Resource | Depends On | Reason |
|----------|-----------|--------|
| aws_cloudfront_distribution.main | aws_s3_bucket.origin | CloudFront requires origin to serve from |

### DNS & Routing

| Resource | Depends On | Reason |
|----------|-----------|--------|
| aws_route53_record.postgres_primary | aws_route53_zone.main, aws_route53_health_check.primary_rds | Record lives in zone, health check controls routing |
| aws_route53_health_check.primary_rds | (implicit) aws_rds_cluster.postgres.endpoint | Health check monitors primary endpoint |

## Dependency Chains (Critical Path)

### Application Starts

```
1. aws_vpc.primary created
   ↓
2. aws_subnet.private_a, aws_subnet.private_b created
   ↓
3. aws_security_group.db created
   ↓
4. aws_db_subnet_group.postgres created (lists private subnets)
   ↓
5. aws_rds_cluster.postgres created
   ↓
6. aws_rds_cluster_instance.postgres_primary created
   ↓
7. postgres.app.example.com CNAME resolves to primary endpoint
   ↓
[Application can connect to postgres.app.example.com:5432]
```

**Critical Path Length:** 7 steps (sequential)
**Time Estimate:** 15-20 minutes (RDS cluster creation is slowest)

### Failover Setup

```
1. aws_rds_cluster.postgres_secondary created (depends on primary existing)
   ↓
2. aws_route53_zone.main created
   ↓
3. aws_route53_health_check.primary_rds created
   ↓
4. aws_route53_health_check.secondary_rds created
   ↓
5. aws_route53_record.postgres_primary created
   ↓
6. aws_route53_record.postgres_secondary created
   ↓
[Route53 begins health monitoring]
```

**Critical Path Length:** 6 steps (mostly parallel after health checks)
**Time Estimate:** 10-15 minutes

## Blast Radius (Failure Impact)

### If aws_vpc.primary fails
**Blast Radius:** ALL resources in primary region
- Subnets unavailable
- RDS cluster unreachable
- CloudFront can still serve cached content
- Failover to secondary via Route53

### If aws_rds_cluster.postgres fails
**Blast Radius:** Application queries (30 seconds → 3 minutes)
- Route53 detects failure (90 seconds)
- Automatic failover to secondary
- Secondary is read-only unless promoted
- Replication catches up within 1 second post-failover

### If aws_s3_bucket.origin fails
**Blast Radius:** CloudFront returns 503 (after TTL expiry)
- Cached content still served from edge
- New requests fail after 1 hour TTL
- CDN unavailable until bucket restored

### If aws_route53_zone.main fails
**Blast Radius:** DNS lookups fail, no failover possible
- Critical — must be prevented via high availability
- AWS automatically manages Route53 HA

## Redundancy Assessment

| Component | Redundancy | Level |
|-----------|-----------|-------|
| VPC | Single region | Low (can replicate config to us-west-2) |
| Subnets | Multi-AZ (primary has 2, secondary has 2) | High |
| RDS Cluster | Multi-AZ within each region + cross-region replica | Very High |
| Security Groups | Single per region | Medium (easily recreated) |
| CloudFront | Global CDN with edge caching | Very High |
| Route53 | Managed globally by AWS | Very High |
| S3 Bucket | Single region | Low (can add cross-region replication) |

## Cascade Failure Scenarios

### Scenario 1: Primary Region Outage (All Infrastructure Down)

```
aws_vpc.primary unavailable
    ↓ CASCADES TO ↓
[All subnets, security groups, RDS inaccessible]
    ↓ ROUTED TO ↓
aws_vpc.secondary (via Route53 failover)
    ↓ RESOLVES TO ↓
aws_rds_cluster.postgres_secondary.endpoint
    ↓ READ-ONLY MODE ↓
Applications can query but cannot write
```

**RTO:** 1.5-3 minutes (health check + DNS propagation)
**RPO:** <1 second
**Manual Action Needed:** Promote secondary to read-write (if permanent failover)

### Scenario 2: Primary RDS Fails (Network Accessible, DB Unreachable)

```
aws_rds_cluster.postgres.endpoint unresponsive
    ↓ DETECTED BY ↓
aws_route53_health_check.primary_rds (after 90 seconds)
    ↓ SWITCHES TO ↓
aws_route53_record.postgres_primary (failover_policy: SECONDARY)
    ↓ ROUTES TO ↓
aws_rds_cluster.postgres_secondary.endpoint
    ↓
[Replication continues from recovering primary]
```

**RTO:** ~90 seconds (detection only, no recovery needed)
**RPO:** <1 second
**Automatic:** Yes

### Scenario 3: S3 Bucket Corrupted (CloudFront Affected)

```
aws_s3_bucket.origin inaccessible
    ↓ AFTER TTL EXPIRY ↓
aws_cloudfront_distribution.main returns 503
    ↓
[Cached content still served from edges until cache TTL expires]
    ↓ FALLBACK NEEDED ↓
Either: restore bucket OR failover to secondary S3 (not implemented)
```

**RTO:** 24 hours (max TTL) without restoration
**RPO:** N/A (bucket failure, not data loss)
**Automatic:** No (requires manual intervention)

## Monitoring Dependencies

### Health Check Metrics

```bash
# Monitor primary health status
aws cloudwatch get-metric-statistics \
  --namespace AWS/Route53 \
  --metric-name HealthCheckStatus \
  --dimensions Name=HealthCheckId,Value={CHECK_ID} \
  --statistics Minimum \
  --period 60 \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z
```

### Replication Status

```bash
# Check replication lag
aws rds describe-db_clusters \
  --db-cluster-identifier postgres-secondary \
  --query 'DBClusters[0].ReplicationSourceIdentifier'
```

### Dependency Chain Validation

```bash
# Verify all resources exist and are linked
terraform state show aws_rds_cluster.postgres
terraform state show aws_rds_cluster.postgres_secondary
terraform state show aws_route53_record.postgres_primary
terraform state show aws_route53_record.postgres_secondary
```

## Future Dependency Enhancements

- [ ] Add S3 cross-region replication (us-west-2 backup bucket)
- [ ] Implement Lambda for automatic secondary promotion
- [ ] Add VPC peering between regions for direct communication
- [ ] Create CloudFormation StackSets for multi-region deployment
- [ ] Implement backup to S3 for point-in-time recovery
- [ ] Add parameter store for shared configuration across regions
