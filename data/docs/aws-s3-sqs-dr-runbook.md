# AWS S3 & SQS — Disaster Recovery Runbook

## Resource Types: aws_s3_bucket | aws_sqs_queue | Strategy: backup_fallback, stateless

---

# Part 1: S3 — Cross-Region Replication & Data Recovery

## Overview

S3 buckets (`aws_s3_bucket`) with Cross-Region Replication (CRR) replicate objects to a replica bucket in eu-west-1 with < 15-minute replication lag (S3 Replication Time Control guarantees 99.99% of objects replicated within 15 minutes). S3 itself is 11 9s durability — bucket-level failure is extremely rare.

RTO targets: < 5 min (enable write on replica) | 30 min (restore from versioning) | 2–4 hours (restore from Glacier)
RPO: < 15 min (CRR) | 0 for versioned objects (no data loss, only access delay)

---

## Failure Scenario: Accidental Object Deletion (backup_fallback)

**Symptoms:** Application returns 404 or 403 for specific S3 keys; S3 access logs show `DELETE` operations.

**Detection Commands:**
```bash
aws s3api list-object-versions \
  --bucket app-data-primary-<account-id> \
  --prefix <deleted-key-prefix> \
  --query '{Versions:Versions[*].{Key:Key,Version:VersionId,Modified:LastModified},DeleteMarkers:DeleteMarkers[*].{Key:Key,Version:VersionId}}'
```

**Recovery Steps — Restore Specific Object:**
1. Identify delete marker:
   ```bash
   aws s3api list-object-versions \
     --bucket app-data-primary-<account-id> \
     --prefix uploads/2026/ \
     --query 'DeleteMarkers[*].{Key:Key,VersionId:VersionId}'
   ```
2. Remove delete marker to restore object:
   ```bash
   aws s3api delete-object \
     --bucket app-data-primary-<account-id> \
     --key <object-key> \
     --version-id <delete-marker-version-id>
   ```
3. Verify object is accessible: `aws s3 ls s3://app-data-primary-<account-id>/<object-key>`
4. If no versioning, restore from replica bucket:
   ```bash
   aws s3 cp s3://app-data-replica-<account-id>/<key> s3://app-data-primary-<account-id>/<key>
   ```

---

## Failure Scenario: Primary Region S3 Unavailable — Failover to Replica

**Symptoms:** S3 endpoint in us-east-1 returns 503; all S3 operations fail.

**Recovery Steps:**
1. Verify outage is region-wide: `aws health describe-events --filter services=S3,regions=us-east-1`
2. Disable replication rules on replica to allow writes (otherwise replica is read-only):
   ```bash
   aws s3api put-bucket-replication \
     --bucket app-data-replica-<account-id> \
     --replication-configuration '{"Role":"","Rules":[]}'
   ```
3. Update application configuration to use replica bucket:
   ```bash
   aws ssm put-parameter \
     --name /app/s3_bucket \
     --value "app-data-replica-<account-id>" \
     --overwrite
   ```
4. Restart application to pick up new bucket name
5. Monitor: new writes go to replica; prepare to re-sync when primary recovers
6. When primary recovers: enable reverse replication (replica → primary) to catch up

**Post-Recovery Data Sync:**
```bash
aws s3 sync s3://app-data-replica-<account-id> s3://app-data-primary-<account-id> \
  --source-region eu-west-1 \
  --region us-east-1 \
  --delete
```

---

## Failure Scenario: Bulk Accidental Deletion / Ransomware

**Recovery Steps:**
1. Enable S3 Object Lock on bucket immediately (prevents further deletion):
   ```bash
   aws s3api put-object-lock-configuration \
     --bucket app-data-primary-<account-id> \
     --object-lock-configuration '{"ObjectLockEnabled":"Enabled","Rule":{"DefaultRetention":{"Mode":"GOVERNANCE","Days":30}}}'
   ```
2. Identify scope of deletion from CloudTrail:
   ```bash
   aws cloudtrail lookup-events \
     --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteObject \
     --start-time $(date -u -d '2 hours ago' +%FT%TZ) \
     --query 'Events[*].{Time:EventTime,User:Username,Key:Resources[0].ResourceName}'
   ```
3. Restore all deleted objects by removing delete markers in bulk:
   ```bash
   aws s3api list-object-versions \
     --bucket app-data-primary-<account-id> \
     --query 'DeleteMarkers[*].{Key:Key,VersionId:VersionId}' \
     --output json | \
   jq -r '.[] | "aws s3api delete-object --bucket app-data-primary-<account-id> --key \(.Key) --version-id \(.VersionId)"' | bash
   ```

---

## S3 Monitoring & Alerting

Key CloudWatch metrics for `aws_s3_bucket`:
- `AWS/S3/4xxErrors` — alert at > 100/min (access errors or missing objects)
- `AWS/S3/5xxErrors` — alert at > 10/min (S3 service errors)
- `AWS/S3/TotalRequestLatency` — alert at p99 > 500ms
- Replication lag: `aws s3api get-bucket-replication --bucket app-data-primary` + CloudWatch `ReplicationLatency`
- CloudTrail: alert on `DeleteBucket`, `DeleteObjects`, `PutBucketPolicy` via EventBridge rule

---

# Part 2: SQS — Queue Backlog & Dead-Letter Recovery

## Overview

SQS FIFO queues (`aws_sqs_queue`) are fully managed with at-least-once delivery. `app-jobs.fifo` processes background jobs; `app-jobs-dlq.fifo` receives messages that failed processing 3 times. SQS itself has 11 9s durability; DR focuses on consumer failures and DLQ management.

RTO targets: 2–5 min (restart consumers) | 30 min (redrive DLQ messages)
RPO: 0 (messages are retained for up to 14 days by default)

---

## Failure Scenario: Consumer Failure — Queue Depth Growing

**Symptoms:**
- CloudWatch: `SQS/ApproximateNumberOfMessagesNotVisible` growing
- Application logs: worker instances failing to process jobs
- DLQ `ApproximateNumberOfMessagesVisible` increasing

**Detection Commands:**
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/<account>/app-jobs.fifo \
  --attribute-names ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible,ApproximateAgeOfOldestMessage

aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/<account>/app-jobs-dlq.fifo \
  --max-number-of-messages 5 \
  --attribute-names All
```

**Recovery Steps — stateless:**
1. Identify failing consumers: check EC2 instance health in ASG
2. If all consumers are down, increase ASG capacity temporarily:
   ```bash
   aws autoscaling set-desired-capacity --auto-scaling-group-name app-asg --desired-capacity 5
   ```
3. Fix root cause (dependency failure, code bug, configuration issue)
4. Deploy fix and verify consumers start processing: watch `MessagesVisible` decline
5. Increase `VisibilityTimeout` on main queue if messages keep re-appearing (processing too slow):
   ```bash
   aws sqs set-queue-attributes \
     --queue-url https://sqs.us-east-1.amazonaws.com/<account>/app-jobs.fifo \
     --attributes VisibilityTimeout=600
   ```

---

## Failure Scenario: Dead-Letter Queue Redrive

**Recovery Steps — After fixing root cause:**
1. Inspect DLQ messages to confirm fix addresses the failure:
   ```bash
   aws sqs receive-message \
     --queue-url https://sqs.us-east-1.amazonaws.com/<account>/app-jobs-dlq.fifo \
     --max-number-of-messages 10 --visibility-timeout 30
   ```
2. Redrive DLQ messages back to main queue:
   ```bash
   aws sqs start-message-move-task \
     --source-arn arn:aws:sqs:us-east-1:<account>:app-jobs-dlq.fifo \
     --destination-arn arn:aws:sqs:us-east-1:<account>:app-jobs.fifo \
     --max-number-of-messages-per-second 5
   ```
3. Monitor redrive progress:
   ```bash
   aws sqs list-message-move-tasks \
     --source-arn arn:aws:sqs:us-east-1:<account>:app-jobs-dlq.fifo
   ```
4. Watch error rate after redrive — if messages fail again, they return to DLQ

---

## SQS Monitoring & Alerting

Key CloudWatch metrics for `aws_sqs_queue`:
- `SQS/ApproximateNumberOfMessagesVisible` — alert at > 1000 (backlog growing)
- `SQS/ApproximateAgeOfOldestMessage` — alert at > 300 seconds (jobs stale)
- `SQS/NumberOfMessagesSent` / `NumberOfMessagesReceived` — compare to detect consumer lag
- DLQ `ApproximateNumberOfMessagesVisible` — alert at > 10 (jobs failing)

EventBridge rule for DLQ depth:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name sqs-dlq-messages-found \
  --metric-name ApproximateNumberOfMessagesVisible \
  --namespace AWS/SQS \
  --statistic Maximum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --dimensions Name=QueueName,Value=app-jobs-dlq.fifo
```
