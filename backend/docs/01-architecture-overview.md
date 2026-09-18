# Infrastructure Architecture Overview

## Multi-Region Disaster Recovery Setup

This document describes the complete AWS infrastructure for the Digital Twin Disaster Recovery system, spanning two regions (us-east-1 primary, us-west-2 secondary) with cross-region failover capability.

## Regional Architecture

### Primary Region (us-east-1)

**VPC:** 10.0.0.0/16

#### Public Subnets (Application Layer)
- **primary_a:** 10.0.1.0/24 (us-east-1a)
- **primary_b:** 10.0.2.0/24 (us-east-1b)

Purpose: Public-facing application servers. Not used for database in new setup.

#### Private Subnets (Database Layer)
- **private_a:** 10.0.11.0/24 (us-east-1a)
- **private_b:** 10.0.12.0/24 (us-east-1b)

Purpose: Isolated database layer. RDS Aurora PostgreSQL cluster runs here for security and isolation from public internet.

### Secondary Region (us-west-2)

**VPC:** 10.1.0.0/16

#### Private Subnets (Database Layer)
- **secondary_private_a:** 10.1.11.0/24 (us-west-2a)
- **secondary_private_b:** 10.1.12.0/24 (us-west-2b)

Purpose: Read replica cluster for disaster recovery. Cross-region replication from primary.

## Key Components

### 1. CloudFront CDN

**Origin:** S3 bucket (app-content-{ACCOUNT_ID})

**Features:**
- HTTP to HTTPS redirect enforcement
- Default caching: 3600 seconds (1 hour) with 86400 max (24 hours)
- COSINE similarity-based edge routing
- Serves static content and assets globally

**Purpose:** High-availability content delivery, reduces latency worldwide

### 2. RDS Aurora PostgreSQL Cluster

#### Primary Cluster (us-east-1)
- **Identifier:** postgres
- **Instance Class:** db.t4.medium (upgraded from db.t3.small)
- **Engine:** aurora-postgresql
- **Subnet Group:** private subnets (private_a, private_b)
- **Security Group:** app-db (restrictive ingress rules)

**Purpose:** Main transactional database for DR simulation state, topology, and operational data

#### Secondary Cluster (us-west-2)
- **Identifier:** postgres-secondary
- **Instance Class:** db.t4.medium (matches primary)
- **Engine:** aurora-postgresql
- **Replication:** Read replica of primary cluster
- **Subnet Group:** secondary private subnets
- **Security Group:** app-db-secondary

**Purpose:** Standby database for automatic failover. Routes failover traffic during primary region outage.

### 3. Route53 Failover Routing

**Hosted Zone:** app.example.com

**Primary Record (postgres.app.example.com)**
- Type: CNAME
- Value: aws_rds_cluster.postgres.endpoint
- Health Check: Route53 health check on primary RDS endpoint
- Failover Policy: PRIMARY

**Secondary Record (postgres.app.example.com)**
- Type: CNAME
- Value: aws_rds_cluster.postgres_secondary.endpoint
- Health Check: Route53 health check on secondary RDS endpoint
- Failover Policy: SECONDARY

**Behavior:** When primary fails health checks (3 consecutive failures, 30-second intervals), Route53 automatically routes traffic to secondary. TTL set to 60 seconds for quick failover.

## Network Isolation Strategy

### Public Subnets (primary_a, primary_b)
- **CIDR:** 10.0.1.0/24, 10.0.2.0/24
- **Routing:** Internet Gateway attached
- **Usage:** Application servers (future)
- **Database Access:** Restricted — apps must route through NAT or security groups

### Private Subnets (primary + secondary)
- **CIDR:** 10.0.11.0/24, 10.0.12.0/24, 10.1.11.0/24, 10.1.12.0/24
- **Routing:** No direct internet access (NAT required for outbound)
- **Usage:** RDS Aurora PostgreSQL clusters only
- **Security:** Security groups enforce restricted ingress from app servers only

## Cross-Region Dependency Flow

```
aws_rds_cluster.postgres (primary)
    ↓ DEPENDS_ON
aws_rds_cluster.postgres_secondary (secondary)
    ↓
Route53 Failover Routing
    ↓
Automatic DNS switchover on health check failure
```

## RDS Instance Classes

**Previously:** db.t3.small (burstable, 2 vCPU, 2 GB memory)
**Now:** db.t4.medium (burstable, 1 vCPU, 4 GB memory, better price-performance)

**Rationale:** t4 family provides better burst performance and memory allocation for baseline DR workloads while maintaining cost efficiency.

## Redundancy Strategy

### Active-Active vs Active-Passive

- **CloudFront:** Active-active global distribution (passive origin = S3)
- **RDS:** Active-passive (primary in us-east-1, read-only replica in us-west-2)
- **Failover Time:** ~60 seconds (Route53 health check interval + DNS propagation)

### High Availability

- **RDS Multi-AZ:** Yes (primary and secondary clusters span 2 AZs each)
- **CloudFront:** Global CDN edge locations (80+ globally)
- **Route53:** Managed DNS with global routing policies

## Security Architecture

### Security Groups

**app-db (Primary Region)**
- Allows inbound traffic from application servers on port 5432 (PostgreSQL)
- Blocks all other inbound by default
- Outbound: Unrestricted (allows replication)

**app-db-secondary (Secondary Region)**
- Same rules as primary
- Allows cross-region replication traffic from primary security group

### Data Protection

- **Encryption in Transit:** RDS uses SSL/TLS for connections
- **Encryption at Rest:** Enabled for EBS volumes backing RDS
- **Backup Strategy:** Aurora automatic backups retained for 7 days default
- **S3 Bucket:** Not publicly accessible; CloudFront is sole origin

## Monitoring & Observability

### Health Checks
- Route53 health checks every 30 seconds
- Failure threshold: 3 consecutive failures before failover
- TCP health checks on port 5432

### Metrics
- CloudFront request counts and cache hit ratio
- RDS CPU, storage, and connection metrics
- Route53 DNS query latency

## Disaster Recovery Procedures

### Automatic Failover (RDS)
1. Primary RDS health check fails
2. Route53 waits 3 intervals (90 seconds) for confirmation
3. DNS record switches to secondary cluster
4. Clients reconnect to secondary within 60 seconds (TTL)

### Manual Failback
1. Primary region restored
2. Manual DNS failback via Route53 console (can be automated)
3. Data reconciliation (secondary reads from primary during failover)

## Cost Optimization

- **t4.medium instances:** Better memory allocation reduces need for larger instances
- **CloudFront:** Reduces data transfer costs via edge caching
- **Private subnets:** No NAT Gateway costs (databases don't need outbound internet)
- **Aurora:** Pay-per-second pricing with auto-scaling capacity

## Deployment Order

1. Primary VPC + subnets
2. Private subnets for database
3. RDS Aurora cluster (primary)
4. Secondary region VPC + subnets
5. Secondary RDS cluster
6. S3 bucket + CloudFront distribution
7. Route53 hosted zone + health checks + failover records

## Future Enhancements

- [ ] Add RDS read replicas within primary region
- [ ] Implement cross-region S3 replication for DR
- [ ] Add Lambda functions for automated failover procedures
- [ ] Enable Performance Insights for RDS diagnostics
- [ ] Implement AWS Backup service for unified recovery management
