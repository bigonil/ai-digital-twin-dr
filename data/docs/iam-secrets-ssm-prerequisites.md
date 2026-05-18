# IAM, Secrets Manager & SSM — DR Prerequisites

## Overview

Every recovery runbook assumes specific IAM permissions, secrets, and configuration parameters are available and valid. IAM role failures, expired secrets, or missing SSM parameters are among the most common causes of RTO overrun — the runbook is correct but the operator lacks permission to execute it. This guide covers prerequisites validation before executing any DR procedure.

---

## IAM Role Verification

### On-Call Engineer IAM Requirements

Before starting any recovery, verify operator has these permissions:

```bash
# Test EC2 permissions
aws ec2 describe-instances --region us-east-1 --max-results 1
aws ec2 terminate-instances --dry-run --instance-ids i-000000000000000a

# Test RDS permissions
aws rds describe-db-clusters --region us-east-1
aws rds failover-db-cluster --dry-run --db-cluster-identifier app-postgres 2>&1 | grep -v "DryRunOperation"

# Test ELB permissions
aws elbv2 describe-load-balancers --region us-east-1

# Test Route53 permissions
aws route53 list-hosted-zones

# Test SSM permissions (critical for config updates)
aws ssm get-parameter --name /app/db_host
aws ssm put-parameter --name /dr-test/permission-check --value test --type String --overwrite
aws ssm delete-parameter --name /dr-test/permission-check
```

**If any command fails:** escalate to AWS Account Admin immediately. DR cannot proceed without correct IAM permissions.

### Lambda Execution Role Requirements

Lambda functions need these permissions to operate during DR:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["rds-data:*"], "Resource": "*"},
    {"Effect": "Allow", "Action": ["elasticache:*"], "Resource": "*"},
    {"Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:GetParametersByPath"], "Resource": "arn:aws:ssm:*:*:parameter/app/*"},
    {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"], "Resource": "arn:aws:secretsmanager:*:*:secret:app/*"},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": "arn:aws:s3:::app-data-*/*"}
  ]
}
```

### EKS Node IAM Role Requirements

Worker nodes must have the `AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, and `AmazonEC2ContainerRegistryReadOnly` managed policies. Verify:
```bash
aws iam list-attached-role-policies \
  --role-name <eks-node-role> \
  --query 'AttachedPolicies[*].PolicyName'
```

---

## AWS Secrets Manager — Recovery Credentials

### Database Credentials

Never hardcode DB credentials in application config. During DR, Secrets Manager must be available and application must be able to retrieve secrets from the DR region.

```bash
# Verify secret exists in both regions
aws secretsmanager describe-secret \
  --secret-id app/postgres/credentials \
  --region us-east-1

aws secretsmanager describe-secret \
  --secret-id app/postgres/credentials \
  --region eu-west-1

# Test retrieval (confirm JSON format and expected keys)
aws secretsmanager get-secret-value \
  --secret-id app/postgres/credentials \
  --region eu-west-1 \
  --query 'SecretString' --output text | python -m json.tool
```

Expected secret JSON:
```json
{
  "username": "admin",
  "password": "<password>",
  "host": "app-postgres.cluster-<id>.eu-west-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "appdb"
}
```

### Update Secret After Aurora Failover

After promoting eu-west-1 Aurora cluster, update the secret with new endpoint:
```bash
NEW_ENDPOINT=$(aws rds describe-db-clusters \
  --db-cluster-identifier app-postgres-dr \
  --region eu-west-1 \
  --query 'DBClusters[0].Endpoint' --output text)

aws secretsmanager update-secret \
  --secret-id app/postgres/credentials \
  --region eu-west-1 \
  --secret-string "{\"username\":\"admin\",\"password\":\"<password>\",\"host\":\"$NEW_ENDPOINT\",\"port\":5432,\"dbname\":\"appdb\"}"
```

### Secret Rotation

Secrets with automatic rotation must not be rotating during DR (rotation temporarily invalidates secret):
```bash
aws secretsmanager describe-secret \
  --secret-id app/postgres/credentials \
  --query 'RotationEnabled'

# Disable rotation during DR if needed
aws secretsmanager cancel-rotate-secret \
  --secret-id app/postgres/credentials
```

---

## AWS Systems Manager — Parameter Store

SSM Parameter Store holds non-secret configuration that changes during DR (endpoints, bucket names, feature flags).

### Critical Parameters

| Parameter | Type | Description |
|---|---|---|
| `/app/db_host` | String | Aurora cluster endpoint |
| `/app/redis_host` | String | ElastiCache primary endpoint |
| `/app/s3_bucket` | String | Active S3 bucket name |
| `/app/region` | String | Active region (us-east-1 or eu-west-1) |
| `/app/feature/maintenance_mode` | String | true/false — maintenance page override |
| `/app/rto_target_minutes` | String | Current RTO target |

### Pre-DR Parameter Check

```bash
# Dump all app parameters (verify they're populated and correct)
aws ssm get-parameters-by-path \
  --path /app/ \
  --with-decryption \
  --query 'Parameters[*].{Name:Name,Value:Value,Modified:LastModifiedDate}' \
  --output table

# Verify eu-west-1 parameters exist (needed for DR region)
aws ssm get-parameters-by-path \
  --path /app/ \
  --region eu-west-1 \
  --query 'Parameters[*].Name' \
  --output table
```

### Activate Maintenance Mode

Before DR cutover, enable maintenance mode to stop new writes:
```bash
aws ssm put-parameter \
  --name /app/feature/maintenance_mode \
  --value "true" \
  --overwrite

# Deactivate after DR is complete
aws ssm put-parameter \
  --name /app/feature/maintenance_mode \
  --value "false" \
  --overwrite \
  --region eu-west-1
```

---

## IAM Cross-Region Role Assumption

During DR, operations in eu-west-1 require cross-region access. Verify STS can assume DR role:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::<account>:role/dr-operations-role \
  --role-session-name dr-session-$(date +%s) \
  --region eu-west-1

# Configure AWS CLI profile for DR region
aws configure set role_arn arn:aws:iam::<account>:role/dr-operations-role --profile dr
aws configure set region eu-west-1 --profile dr
export AWS_PROFILE=dr
```

---

## Certificate Validation (ACM)

SSL certificates must be valid in the DR region. CloudFront certificates MUST be in us-east-1.

```bash
# Check all certificates expiry in eu-west-1
aws acm list-certificates \
  --region eu-west-1 \
  --query 'CertificateSummaryList[*].{Domain:DomainName,ARN:CertificateArn,Status:Status}'

# Check days until expiry for each cert
for ARN in $(aws acm list-certificates --region eu-west-1 --query 'CertificateSummaryList[*].CertificateArn' --output text); do
  aws acm describe-certificate --certificate-arn $ARN --region eu-west-1 \
    --query '{Domain:Certificate.DomainName,Expiry:Certificate.NotAfter}'
done
```

**Alert:** Any certificate expiring in < 30 days must be renewed before DR is declared production-ready.

---

## Pre-Disaster Readiness Checklist

Run monthly or after any infrastructure change:

**IAM:**
- [ ] On-call engineer IAM permissions tested in eu-west-1
- [ ] Lambda execution role has SSM and Secrets Manager access in eu-west-1
- [ ] EKS node role policies verified
- [ ] `dr-operations-role` can be assumed cross-region

**Secrets:**
- [ ] `app/postgres/credentials` exists in eu-west-1 with correct endpoint
- [ ] `app/redis/credentials` exists in eu-west-1 (if Redis requires auth)
- [ ] Secret rotation is NOT scheduled during maintenance window

**SSM Parameters:**
- [ ] All `/app/*` parameters exist in eu-west-1
- [ ] `/app/feature/maintenance_mode` parameter exists
- [ ] Parameters point to eu-west-1 endpoints in eu-west-1 region

**Certificates:**
- [ ] All ACM certs in eu-west-1 valid for > 60 days
- [ ] CloudFront cert in us-east-1 valid for > 60 days
