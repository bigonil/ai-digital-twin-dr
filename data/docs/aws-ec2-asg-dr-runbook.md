# AWS EC2 / Auto Scaling Group — Disaster Recovery Runbook

## Resource Type: aws_instance | Strategy: stateless, backup_fallback

### Overview

Auto Scaling Groups (ASG) manage fleets of EC2 instances (`aws_instance`) for stateless application workloads. ASGs automatically replace unhealthy instances within 1–5 minutes. All application state is external (Aurora, Redis, S3). Instance termination is non-destructive for stateless services.

RTO targets: 1–3 min (ASG self-healing) | 5–10 min (manual intervention) | 15 min (full fleet rebuild)
RPO: 0 (stateless — no data stored on instances)

---

## Failure Scenario: Single Instance Failure (stateless)

**Symptoms:**
- ALB health check fails for one target (`HealthyHostCount` drops by 1)
- EC2 instance shows `impaired` in CloudWatch Instance Status Check
- Application logs: connection refused on specific instance IP

**Detection Commands:**
```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names app-asg \
  --query 'AutoScalingGroups[0].{Desired:DesiredCapacity,InService:Instances[?LifecycleState==`InService`]|length(@),Min:MinSize,Max:MaxSize}'

aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --query 'TargetHealthDescriptions[*].{Id:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason}'
```

**Recovery Steps — stateless (auto):**
1. ASG detects instance failure via EC2 health checks (every 300 seconds by default)
2. ASG terminates unhealthy instance and launches replacement automatically
3. New instance registers with ALB and passes health check (30–120 second warmup)
4. Monitor: `aws autoscaling describe-scaling-activities --auto-scaling-group-name app-asg`

**Recovery Steps — stateless (manual accelerated):**
1. Manually terminate unhealthy instance to trigger immediate replacement:
   ```bash
   aws ec2 terminate-instances --instance-ids <instance-id>
   ```
2. Force ASG to refresh all instances with latest launch template:
   ```bash
   aws autoscaling start-instance-refresh \
     --auto-scaling-group-name app-asg \
     --preferences '{"MinHealthyPercentage":80,"InstanceWarmup":120}'
   ```
3. Monitor refresh: `aws autoscaling describe-instance-refreshes --auto-scaling-group-name app-asg`

**Verification:** `aws elbv2 describe-target-health` shows all registered targets as `healthy`.

---

## Failure Scenario: Full Fleet Failure (stateless)

**Symptoms:** ALB `HealthyHostCount` = 0; all application requests return 503.

**Recovery Steps:**
1. Check ASG desired vs running:
   ```bash
   aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names app-asg \
     --query 'AutoScalingGroups[0].{Desired:DesiredCapacity,Running:Instances|length(@)}'
   ```
2. Check EC2 launch template for misconfigurations:
   ```bash
   aws ec2 describe-launch-template-versions \
     --launch-template-name app-server-lt \
     --versions '$Latest'
   ```
3. Check if instances are launching but failing health checks:
   ```bash
   aws ec2 get-console-output --instance-id <new-instance-id>
   ```
4. If AMI is broken, revert to last known good AMI:
   ```bash
   aws autoscaling create-launch-template-version \
     --launch-template-id <lt-id> \
     --source-version <last-good-version>
   aws autoscaling update-auto-scaling-group \
     --auto-scaling-group-name app-asg \
     --launch-template LaunchTemplateId=<lt-id>,Version='$Latest'
   ```
5. Manually set desired capacity to trigger immediate launches:
   ```bash
   aws autoscaling set-desired-capacity \
     --auto-scaling-group-name app-asg \
     --desired-capacity 3
   ```
6. Expected RTO: 5–10 minutes from root cause identification

---

## Failure Scenario: AZ Outage

**Symptoms:** Instances in one AZ fail; ASG `AvailabilityZoneRebalancing` alarms.

**Recovery Steps:**
1. Temporarily remove failed AZ from ASG:
   ```bash
   aws autoscaling update-auto-scaling-group \
     --auto-scaling-group-name app-asg \
     --availability-zones us-east-1b us-east-1c
   ```
2. Increase desired capacity to compensate for reduced AZs:
   ```bash
   aws autoscaling set-desired-capacity \
     --auto-scaling-group-name app-asg \
     --desired-capacity 4
   ```
3. Monitor `HealthyHostCount` recovers to ≥ 2 in remaining AZs
4. When AZ recovers, re-add it and rebalance: `aws autoscaling update-auto-scaling-group --availability-zones us-east-1a us-east-1b us-east-1c`

---

## Scaling Events & Blast Radius

When EC2/ASG fails, cascading impact:
1. **ALB (aws_lb)** — reduced capacity; latency increases; if all instances unhealthy, ALB returns 503 to all clients
2. **Aurora (aws_rds_cluster)** — connection count drops to 0 then spikes when new instances launch (connection storm)
3. **SQS consumers** — job processing stops; queue depth grows; DLQ starts receiving messages after visibility timeout

Mitigation:
- Pre-warm connection pools with `max_connections` limits per instance
- Set `MinHealthyPercentage = 80` in instance refresh to maintain minimum capacity
- SQS consumers: set `VisibilityTimeout` to `MaxProcessingTime × 1.5`

---

## Monitoring & Alerting

Key CloudWatch metrics for `aws_instance` / ASG:
- `AWS/AutoScaling/GroupInServiceInstances` — alert at < 2 (below minimum redundancy)
- `AWS/EC2/CPUUtilization` — alert at > 80% for 10 minutes (capacity pressure)
- `AWS/EC2/StatusCheckFailed` — alert immediately (hardware failure indicator)
- `AWS/ApplicationELB/HealthyHostCount` — alert at < 2
- `AWS/ApplicationELB/HTTPCode_Target_5XX_Count` — alert at > 50/min
- `AWS/ApplicationELB/TargetResponseTime` — alert at p95 > 2 seconds

CloudWatch alarm for minimum fleet size:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name asg-below-minimum-healthy \
  --metric-name GroupInServiceInstances \
  --namespace AWS/AutoScaling \
  --statistic Minimum \
  --period 60 \
  --threshold 2 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=AutoScalingGroupName,Value=app-asg
```

---

## Instance Replacement Verification Checklist

After ASG replaces instances:
- [ ] New instance passes EC2 Status Checks (System + Instance)
- [ ] ALB target shows `healthy` within 2 minutes of launch
- [ ] Application startup logs show no errors (check CloudWatch Logs `/app/startup`)
- [ ] Metrics: CPU < 50%, memory < 70%, error rate < 0.1%
- [ ] Redis connection established (check app log for "Connected to Redis")
- [ ] Aurora connection established (check app log for "DB pool ready")
