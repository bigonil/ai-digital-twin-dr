# AWS Lambda & CloudFront — Disaster Recovery Runbook

## Resource Types: aws_lambda_function | aws_cloudfront | Strategy: stateless

### Overview

Lambda functions (`aws_lambda_function`) are serverless, inherently multi-AZ, and stateless. AWS manages all underlying infrastructure. DR for Lambda focuses on concurrency limits, dead-letter queues, and region failover. CloudFront (`aws_cloudfront`) is a global CDN with 99.99% SLA — failure is typically origin-based, not CDN-based.

RTO targets: Lambda < 30 seconds (auto-restart) | CloudFront < 2 min (origin failover) | Region failover 5–10 min
RPO: 0 for both (stateless)

---

## Lambda — Failure Scenario: Function Throttling

**Symptoms:**
- CloudWatch: `Lambda/Throttles` metric > 0
- Downstream services receive `TooManyRequestsException` (HTTP 429)
- SQS DLQ filling up if Lambda is an SQS consumer

**Detection Commands:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=<function-name> \
  --start-time $(date -u -d '15 min ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics Sum

aws lambda get-function-concurrency --function-name <function-name>
aws lambda get-account-settings  # Check account-level concurrency limits
```

**Recovery Steps — stateless:**
1. Check reserved concurrency — if set too low, increase it:
   ```bash
   aws lambda put-function-concurrency \
     --function-name <function-name> \
     --reserved-concurrent-executions 500
   ```
2. If account limit is reached (default 1000), request increase:
   ```bash
   aws service-quotas request-service-quota-increase \
     --service-code lambda \
     --quota-code L-B99A9384 \
     --desired-value 3000
   ```
3. Enable provisioned concurrency to pre-warm instances (avoids cold starts during burst):
   ```bash
   aws lambda put-provisioned-concurrency-config \
     --function-name <function-name> \
     --qualifier <alias-or-version> \
     --provisioned-concurrent-executions 100
   ```
4. Throttled SQS messages: increase SQS batch size to reduce invocation rate, or increase concurrency

---

## Lambda — Failure Scenario: Function Error Rate Spike

**Symptoms:**
- CloudWatch: `Lambda/Errors` metric spikes
- `Lambda/Duration` p99 approaching timeout limit
- DLQ receiving messages (for async invocations)

**Detection Commands:**
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/<function-name> \
  --filter-pattern "ERROR" \
  --start-time $(date -u -d '30 min ago' +%s000) \
  --limit 20

aws lambda list-function-event-invoke-configs \
  --function-name <function-name>
```

**Recovery Steps:**
1. Check recent deployments — correlate error spike with deploy time:
   ```bash
   aws lambda list-versions-by-function --function-name <function-name> \
     --query 'Versions[-5:].{Version:Version,Modified:LastModified}'
   ```
2. Roll back to last stable version:
   ```bash
   aws lambda update-alias \
     --function-name <function-name> \
     --name production \
     --function-version <last-stable-version>
   ```
3. Check environment variables and secrets (missing config causes errors):
   ```bash
   aws lambda get-function-configuration \
     --function-name <function-name> \
     --query 'Environment.Variables'
   ```
4. If timeout-related: increase timeout (max 15 minutes):
   ```bash
   aws lambda update-function-configuration \
     --function-name <function-name> \
     --timeout 300
   ```
5. Inspect DLQ and redrive failed messages after fix

---

## Lambda — Failure Scenario: Region Failover

**Recovery Steps:**
1. Verify Lambda function exists in DR region with same code version:
   ```bash
   aws lambda get-function --function-name <function-name> --region eu-west-1
   ```
2. If not deployed, deploy from S3 artifact:
   ```bash
   aws lambda create-function \
     --function-name <function-name> \
     --runtime python3.12 \
     --role arn:aws:iam::<account>:role/<lambda-role> \
     --handler handler.main \
     --code S3Bucket=<artifact-bucket>,S3Key=<function>.zip \
     --region eu-west-1
   ```
3. Update EventBridge rules, SQS triggers, or API Gateway to use DR region function
4. Verify function health: `aws lambda invoke --function-name <fn> --region eu-west-1 /tmp/out.json && cat /tmp/out.json`

---

## Lambda — Monitoring & Alerting

Key CloudWatch metrics for `aws_lambda_function`:
- `Lambda/Errors` — alert at error rate > 1% (errors/invocations)
- `Lambda/Throttles` — alert at > 10/min
- `Lambda/Duration` — alert at p99 > 80% of timeout value
- `Lambda/ConcurrentExecutions` — alert at > 80% of reserved concurrency
- `Lambda/IteratorAge` (for stream consumers) — alert at > 60 seconds (falling behind)
- `Lambda/DeadLetterErrors` — alert at > 0 (DLQ write failing)

---

## CloudFront — Failure Scenario: Origin Unavailable (503/504)

**Symptoms:**
- Users see `504 Gateway Timeout` or `502 Bad Gateway` from CloudFront
- CloudWatch: `CloudFront/5xxErrorRate` > 1%
- CloudFront logs show `x-edge-result-type: Error`

**Note:** CloudFront itself rarely fails — 99.9% of "CloudFront outages" are origin failures (ALB, API Gateway, S3).

**Detection Commands:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/CloudFront \
  --metric-name 5xxErrorRate \
  --dimensions Name=DistributionId,Value=<dist-id> Name=Region,Value=Global \
  --start-time $(date -u -d '30 min ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics Average

# Check origin health
curl -I https://<alb-origin-dns>/health
```

**Recovery Steps — stateless:**
1. Identify failing origin from CloudFront access logs (S3 log bucket):
   ```bash
   aws s3 cp s3://<cf-logs-bucket>/<dist-id>/<date>/ . --recursive
   # Check x-edge-result-type and sc-status columns
   ```
2. If origin (ALB) is down, fix the origin first (see ALB runbook)
3. Enable CloudFront origin failover (if configured):
   ```bash
   aws cloudfront get-distribution-config --id <dist-id> | \
     jq '.DistributionConfig.Origins.Items[].CustomOriginConfig'
   ```
4. If no origin failover configured, temporarily point to S3 static error page:
   ```bash
   aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
   ```
5. Set custom error response to serve cached or static page during outage:
   ```bash
   # In distribution config: add CustomErrorResponses for 502/503/504
   # ErrorCachingMinTTL: 10, ResponsePagePath: /maintenance.html
   ```

---

## CloudFront — Failure Scenario: SSL/TLS Certificate Expiry

**Symptoms:** Browsers show `NET::ERR_CERT_DATE_INVALID`; HTTPS requests fail.

**Recovery Steps:**
1. Check certificate status:
   ```bash
   aws acm describe-certificate \
     --certificate-arn <cert-arn> \
     --region us-east-1 \  # CloudFront certs MUST be in us-east-1
     --query 'Certificate.{Status:Status,Expiry:NotAfter,Domain:DomainName}'
   ```
2. Request replacement certificate (ACM auto-renews if DNS validation is active)
3. Update CloudFront distribution to use new certificate:
   ```bash
   aws cloudfront update-distribution \
     --id <dist-id> \
     --distribution-config file://dist-config-updated.json  # With new cert ARN
     --if-match <etag>
   ```
4. Note: CloudFront certificate deployment takes 5–15 minutes globally

---

## CloudFront — Monitoring & Alerting

Key CloudWatch metrics for `aws_cloudfront`:
- `CloudFront/4xxErrorRate` — alert at > 5% (client errors or auth issues)
- `CloudFront/5xxErrorRate` — alert at > 1% (origin failures)
- `CloudFront/BytesDownloaded` — monitor for unusual drops (traffic lost)
- `CloudFront/Requests` — monitor for traffic spikes (DDoS indicator)
- `CloudFront/TotalErrorRate` — alert at > 2%

---

## Cascading Failure Risk

Lambda failures cascade to:
1. **SQS queues** — throttled Lambda consumers → queue depth grows → DLQ fills
2. **Aurora** — Lambda functions may hold DB connections; sudden restart = connection storm
3. **CloudFront** — if Lambda@Edge fails, CloudFront returns 502 for all requests using that function

CloudFront failures cascade to:
1. All end-users — 100% user-facing traffic loss if origin also fails
2. **No internal system cascade** — CloudFront is at the edge, no downstream dependencies
