# AWS Application Load Balancer — Disaster Recovery Runbook

## Resource Type: aws_lb | Strategy: stateless, multi_az

### Overview

Application Load Balancers (`aws_lb`) are fully managed, multi-AZ Layer 7 load balancers. ALB nodes run in every enabled AZ automatically; there is no single point of failure at the load balancer level. ALB DR focuses on target group health, listener rules, SSL certificates, and cross-zone routing.

RTO targets: < 30 seconds (target group routing change) | 2–5 min (DNS-based failover) | 10 min (new ALB provisioning)
RPO: 0 (ALB is stateless)

---

## Failure Scenario: All Targets Unhealthy (503)

**Symptoms:**
- ALB returns 503 to all requests
- CloudWatch: `HealthyHostCount` = 0 in target group
- Access logs show `"target_status_code": "-"` (no healthy targets)

**Detection Commands:**
```bash
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn>

aws elbv2 describe-load-balancers \
  --names app-alb \
  --query 'LoadBalancers[0].{State:State,DNSName:DNSName,AZs:AvailabilityZones}'

aws logs filter-log-events \
  --log-group-name /aws/alb/app-alb \
  --filter-pattern '"503"' \
  --start-time $(date -u -d '5 min ago' +%s000)
```

**Recovery Steps — stateless:**
1. Identify root cause: are targets unhealthy (app issue) or deregistered (deployment issue)?
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <arn> \
     --query 'TargetHealthDescriptions[*].{Id:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Desc:TargetHealth.Description}'
   ```
2. If targets are draining (deployment gone wrong), cancel in-progress deployment:
   ```bash
   aws deploy stop-deployment --deployment-id <d-id> --auto-rollback-enabled
   ```
3. If targets are unhealthy due to app failure, trigger ASG instance refresh:
   ```bash
   aws autoscaling start-instance-refresh \
     --auto-scaling-group-name app-asg \
     --preferences '{"MinHealthyPercentage":50}'
   ```
4. Override health check to allow temporarily unhealthy targets (emergency only):
   ```bash
   aws elbv2 modify-target-group \
     --target-group-arn <arn> \
     --healthy-threshold-count 2 \
     --unhealthy-threshold-count 10 \
     --health-check-interval-seconds 30
   ```
5. Verify recovery: wait for `HealthyHostCount` ≥ 1 before removing override

**Verification:** `curl -I https://<alb-dns-name>/health` returns 200.

---

## Failure Scenario: AZ Outage — ALB Node Failure (multi_az)

**Symptoms:** Traffic from one AZ fails; some users see errors, others don't.

**Recovery Steps:**
1. ALB automatically stops routing to nodes in failed AZ — no manual action required
2. Verify cross-zone load balancing is enabled (distributes load from healthy AZs):
   ```bash
   aws elbv2 describe-load-balancer-attributes \
     --load-balancer-arn <arn> \
     --query 'Attributes[?Key==`load_balancing.cross_zone.enabled`]'
   ```
3. If cross-zone is disabled, enable it:
   ```bash
   aws elbv2 modify-load-balancer-attributes \
     --load-balancer-arn <arn> \
     --attributes Key=load_balancing.cross_zone.enabled,Value=true
   ```
4. Monitor `TargetResponseTime` — cross-zone increases latency slightly but improves availability
5. Temporarily reduce desired capacity in failed AZ's target group if stale targets remain

---

## Failure Scenario: SSL Certificate Expiry

**Symptoms:** HTTPS traffic fails; browsers show `NET::ERR_CERT_DATE_INVALID`; CloudWatch `TLSNegotiationErrorCount` spikes.

**Recovery Steps:**
1. Check certificate expiry:
   ```bash
   aws acm list-certificates --query 'CertificateSummaryList[*].{ARN:CertificateArn,Domain:DomainName,Status:Status}'
   aws acm describe-certificate --certificate-arn <arn> --query 'Certificate.NotAfter'
   ```
2. Request new certificate (if ACM auto-renewal failed):
   ```bash
   aws acm request-certificate \
     --domain-name app.company.com \
     --validation-method DNS \
     --subject-alternative-names "*.app.company.com"
   ```
3. After DNS validation, update HTTPS listener:
   ```bash
   aws elbv2 modify-listener \
     --listener-arn <https-listener-arn> \
     --certificates CertificateArn=<new-cert-arn>
   ```
4. Expected RTO: 5–15 minutes (DNS validation) + immediate for listener update

---

## Failure Scenario: DR Region Failover via Route53

**Symptoms:** Primary region (us-east-1) ALB unhealthy; Route53 health check fails.

**Recovery Steps:**
1. Verify Route53 health check status:
   ```bash
   aws route53 list-health-checks \
     --query 'HealthChecks[?HealthCheckConfig.FullyQualifiedDomainName==`app-alb.us-east-1.amazonaws.com`]'
   ```
2. If health check is failing, Route53 failover routing policy automatically routes to eu-west-1 ALB (30–60 second propagation)
3. Manually force failover if automatic routing is delayed:
   ```bash
   aws route53 change-resource-record-sets \
     --hosted-zone-id <zone-id> \
     --change-batch file://failover-to-dr.json
   ```
4. Verify DNS resolves to DR ALB: `nslookup app.company.com`
5. Scale up eu-west-1 ASG: `aws autoscaling set-desired-capacity --auto-scaling-group-name app-asg-dr --desired-capacity 3`

---

## Monitoring & Alerting

Key CloudWatch metrics for `aws_lb`:
- `AWS/ApplicationELB/HealthyHostCount` — alert at < 2 (target group)
- `AWS/ApplicationELB/UnHealthyHostCount` — alert at ≥ 1
- `AWS/ApplicationELB/HTTPCode_ELB_5XX_Count` — alert at > 10/min (ALB-generated errors)
- `AWS/ApplicationELB/HTTPCode_Target_5XX_Count` — alert at > 50/min
- `AWS/ApplicationELB/TargetResponseTime` — alert at p95 > 2 seconds
- `AWS/ApplicationELB/RejectedConnectionCount` — alert at > 0 (connection surge)
- `AWS/ApplicationELB/TLSNegotiationErrorCount` — alert at > 0 (cert/TLS issue)
- `AWS/ApplicationELB/ActiveConnectionCount` — monitor for traffic spikes

---

## Access Log Analysis for Root Cause

ALB access logs in S3 (`s3://access-logs-bucket/AWSLogs/<account>/elasticloadbalancing/`):
```bash
# Top error types in last hour
aws s3 cp s3://<log-bucket>/<prefix>/$(date +%Y/%m/%d)/<latest>.log.gz - | \
  gunzip | awk '{print $9}' | sort | uniq -c | sort -rn | head -20

# Identify slowest targets
aws s3 cp s3://<log-bucket>/<prefix>/<file>.log.gz - | \
  gunzip | awk '{print $5, $8}' | sort -k2 -rn | head -10
```
