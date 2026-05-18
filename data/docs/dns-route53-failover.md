# DNS & Route53 Failover — DR Guide

## Overview

Route53 is the DNS layer that controls which region receives traffic. Correct DNS configuration is the difference between a 2-minute failover and a 30-minute outage. This guide covers health checks, failover routing policies, TTL management, and common DNS-related DR failures.

---

## Route53 Health Check Configuration

### ALB Health Check (Primary)

```bash
# Create health check for us-east-1 ALB
aws route53 create-health-check \
  --caller-reference "app-alb-primary-$(date +%s)" \
  --health-check-config '{
    "Type": "HTTPS",
    "ResourcePath": "/health",
    "FullyQualifiedDomainName": "<us-east-1-alb-dns>",
    "Port": 443,
    "RequestInterval": 10,
    "FailureThreshold": 3,
    "EnableSNI": true,
    "Regions": ["us-east-1", "eu-west-1", "ap-southeast-1"]
  }'
```

**Failover timing:** 10-second interval × 3 failures = **30-second detection** + 60-second DNS TTL = ~90 seconds to route switch.

### Health Check Status Monitoring

```bash
# Get health check status
aws route53 get-health-check-status \
  --health-check-id <hc-id> \
  --query 'HealthCheckObservations[*].{Region:Region,Status:StatusReport.Status,Checked:StatusReport.CheckedTime}'

# List all health checks with status
aws route53 list-health-checks \
  --query 'HealthChecks[*].{Id:Id,Type:HealthCheckConfig.Type,Domain:HealthCheckConfig.FullyQualifiedDomainName}'
```

---

## Failover Routing Policy Setup

### Active-Passive Failover (Primary + DR)

```bash
# Primary record (us-east-1) — FAILOVER type, PRIMARY
aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "app.company.com",
        "Type": "A",
        "SetIdentifier": "primary-us-east-1",
        "Failover": "PRIMARY",
        "HealthCheckId": "<us-east-1-hc-id>",
        "TTL": 60,
        "ResourceRecords": [{"Value": "<us-east-1-alb-ip>"}]
      }
    }]
  }'

# DR record (eu-west-1) — FAILOVER type, SECONDARY
aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "app.company.com",
        "Type": "A",
        "SetIdentifier": "secondary-eu-west-1",
        "Failover": "SECONDARY",
        "TTL": 60,
        "ResourceRecords": [{"Value": "<eu-west-1-alb-ip>"}]
      }
    }]
  }'
```

**Note:** Use `AliasTarget` instead of `ResourceRecords` for ALB targets (no TTL, faster propagation):

```bash
aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "app.company.com",
        "Type": "A",
        "SetIdentifier": "primary-us-east-1",
        "Failover": "PRIMARY",
        "HealthCheckId": "<hc-id>",
        "AliasTarget": {
          "HostedZoneId": "Z35SXDOTRQ7X7K",
          "DNSName": "<alb-dns>.us-east-1.elb.amazonaws.com",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'
```

---

## TTL Management During DR

### Before Planned DR Test (reduce TTL in advance)

```bash
# Lower TTL 24 hours before DR test (from 300s to 60s)
aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "app.company.com",
        "Type": "A",
        "TTL": 60,
        "ResourceRecords": [{"Value": "<current-ip>"}]
      }
    }]
  }'
```

**Wait for cache to expire before DR:** TTL lowered at T-24h; at T-0 all resolvers have 60-second TTL. Failover propagates in 60–90 seconds instead of 300 seconds.

### Emergency TTL Override

For unplanned DR with high TTL cached by resolvers:
- CloudFront + Route53 can bypass ISP DNS caches via anycast propagation
- For A records: resolvers honor TTL; can't force cache purge
- Mitigation: target 60-second TTL as default for all production A records

---

## Manual DNS Failover (Emergency)

When automatic failover is not triggering or is too slow:

```bash
# Force immediate DNS cutover to DR (update to point directly to eu-west-1)
cat > /tmp/failover.json << 'EOF'
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "app.company.com",
      "Type": "A",
      "SetIdentifier": "primary-us-east-1",
      "Failover": "PRIMARY",
      "HealthCheckId": "<hc-id>",
      "AliasTarget": {
        "HostedZoneId": "<eu-west-1-alb-zone-id>",
        "DNSName": "<eu-west-1-alb-dns>",
        "EvaluateTargetHealth": true
      }
    }
  }]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id <zone-id> \
  --change-batch file:///tmp/failover.json

# Track change propagation
CHANGE_ID=$(aws route53 change-resource-record-sets ... --query 'ChangeInfo.Id' --output text)
aws route53 wait resource-record-sets-changed --id $CHANGE_ID
echo "DNS change propagated globally"
```

---

## DNS Propagation Verification

```bash
# Check from multiple global DNS resolvers
for RESOLVER in 8.8.8.8 1.1.1.1 208.67.222.222 9.9.9.9; do
  echo -n "Resolver $RESOLVER: "
  nslookup app.company.com $RESOLVER | grep -A1 "Name:" | tail -1
done

# Track propagation over time
for i in $(seq 1 12); do
  echo "$(date): $(dig +short app.company.com @8.8.8.8)"
  sleep 10
done

# From specific AWS regions (simulates what Lambda/EC2 in those regions see)
aws lambda invoke \
  --function-name dns-probe \
  --region eu-west-1 \
  --payload '{"hostname":"app.company.com"}' \
  /tmp/probe.json && cat /tmp/probe.json
```

---

## Private DNS — Internal Services

Internal services use Route53 Private Hosted Zones for service discovery. During DR:

```bash
# Check private hosted zone exists in eu-west-1 VPC
aws route53 list-hosted-zones \
  --query 'HostedZones[?Config.PrivateZone==`true`]'

# Verify internal service records point to DR region resources
aws route53 list-resource-record-sets \
  --hosted-zone-id <private-zone-id> \
  --query 'ResourceRecordSets[?Type==`CNAME`]'

# Update internal DB record to point to eu-west-1 Aurora endpoint
aws route53 change-resource-record-sets \
  --hosted-zone-id <private-zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "postgres.internal",
        "Type": "CNAME",
        "TTL": 30,
        "ResourceRecords": [{"Value": "<eu-west-1-aurora-endpoint>"}]
      }
    }]
  }'
```

---

## Common DNS-Related DR Failures

**Failure 1: TTL too high → slow failover**
- Symptom: Failover took 10+ minutes despite Route53 updating
- Root cause: ISP resolvers cached old IP for full TTL duration
- Prevention: Set production TTL to 60 seconds; lower to 30 seconds for critical records

**Failure 2: Health check checking wrong path**
- Symptom: Route53 health check fails even when ALB is healthy
- Root cause: Health check path `/` returns 301 redirect, which Route53 counts as failure
- Fix: Set health check path to `/health` which returns 200 directly

**Failure 3: Split-brain — some clients in primary, some in DR**
- Symptom: Inconsistent errors; some users fine, others failing
- Root cause: Different resolvers have cached different records during cutover
- Timeline: Normal — split-brain lasts 60–300 seconds during TTL expiry
- Fix: Ensure application is stateless or uses distributed session (Redis in DR region)

**Failure 4: Internal DNS not updated — app connects to dead DB**
- Symptom: EC2 instances in eu-west-1 can reach ALB but get DB connection errors
- Root cause: Private hosted zone still points to us-east-1 Aurora endpoint
- Fix: Update private zone records (see Private DNS section above)

**Failure 5: Alias target zone ID mismatch**
- Symptom: Route53 change rejected with `InvalidInput` error
- Root cause: ALB hosted zone IDs differ by region: `Z35SXDOTRQ7X7K` (us-east-1) vs `Z32O12XQLNTSW2` (eu-west-1)
- Fix: Always look up the ALB zone ID dynamically: `aws elbv2 describe-load-balancers --region eu-west-1 --query 'LoadBalancers[0].CanonicalHostedZoneId'`
