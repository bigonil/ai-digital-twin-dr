# Network Topology & Subnets

## VPC Design

### Primary Region (us-east-1)

```
VPC: 10.0.0.0/16
├── Public Subnets (Application)
│   ├── primary_a: 10.0.1.0/24 (us-east-1a)
│   └── primary_b: 10.0.2.0/24 (us-east-1b)
└── Private Subnets (Database)
    ├── private_a: 10.0.11.0/24 (us-east-1a)
    └── private_b: 10.0.12.0/24 (us-east-1b)
```

### Secondary Region (us-west-2)

```
VPC: 10.1.0.0/16
└── Private Subnets (Database Replica)
    ├── secondary_private_a: 10.1.11.0/24 (us-west-2a)
    └── secondary_private_b: 10.1.12.0/24 (us-west-2b)
```

## Subnet Strategy

### Public Subnets (primary_a, primary_b)

**Characteristics:**
- Internet Gateway attached
- Route table includes: `0.0.0.0/0 → IGW`
- Auto-assign public IPv4: Disabled by default (specify per instance)
- NAT Gateway: Not configured (optional for outbound from private)

**Current Use:** Reserved for future application servers
**Security:** Security groups block direct RDS connections

### Private Subnets (All Database Subnets)

**Characteristics:**
- No direct internet access
- Route table: No igw route (must use NAT for outbound)
- Only accessible via:
  - Same VPC communication
  - VPC Peering (cross-region, not configured)
  - VPN/Direct Connect (not configured)
- Security groups enforce strict access control

**Primary Region Private (private_a, private_b):**
- CIDR: 10.0.11.0/24, 10.0.12.0/24
- Host RDS Aurora primary cluster
- IP range supports ~251 usable IPs per subnet

**Secondary Region Private (secondary_private_a, secondary_private_b):**
- CIDR: 10.1.11.0/24, 10.1.12.0/24
- Host RDS Aurora replica cluster
- Cross-region replication from primary

## Availability Zone Spread

**Primary Region (us-east-1):**
- AZ-a: public primary_a (10.0.1.0/24) + private private_a (10.0.11.0/24)
- AZ-b: public primary_b (10.0.2.0/24) + private private_b (10.0.12.0/24)

**Secondary Region (us-west-2):**
- AZ-a: private secondary_private_a (10.1.11.0/24)
- AZ-b: private secondary_private_b (10.1.12.0/24)

**Benefit:** Multi-AZ resilience within each region. RDS spans both AZs for automatic failover.

## Security Groups

### app-db (Primary Region)

**ID:** Terraform: aws_security_group.db

**Rules:**
| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Ingress | TCP | 5432 | app security group | PostgreSQL from app servers |
| Egress | All | All | 0.0.0.0/0 | Outbound replication to secondary |

**VPC:** aws_vpc.primary (10.0.0.0/16)

### app-db-secondary (Secondary Region)

**ID:** Terraform: aws_security_group.db_secondary

**Rules:**
| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Ingress | TCP | 5432 | primary app security group | Replication from primary |
| Egress | All | All | 0.0.0.0/0 | Outbound responses |

**VPC:** aws_vpc.secondary (10.1.0.0/16)

## Cross-Region Replication

**Source:** aws_rds_cluster.postgres (primary)
**Target:** aws_rds_cluster.postgres_secondary (secondary)

**Protocol:** Aurora Global Database (automatic cross-region replication)
**Latency:** Typically <1 second replication lag
**Direction:** One-way (primary → secondary read-only)

**Network Path:**
```
Primary RDS (private_a, private_b)
    ↓ AWS internal network
Secondary RDS (secondary_private_a, secondary_private_b)
```

No explicit VPN or VPC Peering needed — AWS manages replication over backbone.

## DB Subnet Groups

### postgres (Primary Region)

```hcl
resource "aws_db_subnet_group" "postgres" {
  name       = "postgres-sg"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}
```

**Subnets:** private_a (10.0.11.0/24), private_b (10.0.12.0/24)
**Purpose:** Defines where RDS can launch instances within VPC

### postgres_secondary (Secondary Region)

```hcl
resource "aws_db_subnet_group" "postgres_secondary" {
  name       = "postgres-sg-secondary"
  subnet_ids = [aws_subnet.secondary_private_a.id, aws_subnet.secondary_private_b.id]
}
```

**Subnets:** secondary_private_a (10.1.11.0/24), secondary_private_b (10.1.12.0/24)
**Purpose:** Defines where replica RDS launches in secondary region

## IP Address Management

### Subnet IP Capacity

| Subnet | CIDR | AWS Reserved | Usable IPs | Current Use |
|--------|------|--------------|-----------|-------------|
| primary_a | 10.0.1.0/24 | 5 | 251 | ~0 (reserved) |
| primary_b | 10.0.2.0/24 | 5 | 251 | ~0 (reserved) |
| private_a | 10.0.11.0/24 | 5 | 251 | RDS (2 writer instances) |
| private_b | 10.0.12.0/24 | 5 | 251 | RDS (2 writer instances) |
| secondary_private_a | 10.1.11.0/24 | 5 | 251 | RDS secondary (2 reader instances) |
| secondary_private_b | 10.1.12.0/24 | 5 | 251 | RDS secondary (2 reader instances) |

**AWS Reserved per subnet:**
- x.x.x.0 (network address)
- x.x.x.1 (VPC router)
- x.x.x.2 (DNS resolver)
- x.x.x.3 (future AWS use)
- x.x.x.255 (broadcast)

## Network Flow Diagrams

### Inbound Traffic (Client → Database)

```
Client Request
    ↓
Route53 (failover routing)
    ↓
Primary: postgres.app.example.com → RDS endpoint
    or
Secondary: postgres.app.example.com → RDS secondary endpoint
    ↓
Security Group (app-db or app-db-secondary) — Allow :5432
    ↓
RDS Cluster Instance
```

### Replication Traffic (Primary → Secondary)

```
Primary RDS Cluster (us-east-1)
    ↓ Aurora Global Database
    ↓ AWS internal backbone
    ↓
Secondary RDS Cluster (us-west-2)
    ↓
Replica instances in secondary_private_a, secondary_private_b
```

### CDN Traffic (Client → S3)

```
Client Request
    ↓
CloudFront Edge Location
    ↓ (cache miss)
S3 Bucket Origin (app-content-{ACCOUNT_ID})
    ↓
Response cached at edge
```

## NAT Gateway (Optional, Not Configured)

If RDS needs outbound internet (for patches, SNS notifications):
1. Create NAT Gateway in public subnet (costs ~$32/month + data transfer)
2. Add route in private subnet: `0.0.0.0/0 → NAT Gateway`
3. Currently not required (RDS doesn't need outbound internet)

## Network ACLs (Not Modified)

Default NACLs permit:
- All inbound traffic from within VPC
- All outbound traffic
- Stateful for external traffic

Security enforced at Security Group level (app-db, app-db-secondary).

## Future Scaling

### Adding More Subnets
- Public: 10.0.3.0/24, 10.0.4.0/24 (for more apps)
- Private: 10.0.13.0/24, 10.0.14.0/24 (for more databases)
- Secondary: 10.1.13.0/24, 10.1.14.0/24

### VPC Peering or Transit Gateway
If connecting to other VPCs/regions not yet configured.

## Monitoring Network Health

- **Route53 Health Checks:** Every 30 seconds on RDS endpoint
- **VPC Flow Logs:** Can enable to debug security group rules
- **CloudWatch:** RDS network metrics (bytes in/out, connections)
