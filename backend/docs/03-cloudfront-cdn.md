# CloudFront CDN Configuration

## Overview

CloudFront is a content delivery network (CDN) that serves static content from S3 with global edge locations, reducing latency and improving availability. This document describes the CloudFront distribution configuration for the Digital Twin DR infrastructure.

## Distribution Details

### Resource

```hcl
resource "aws_cloudfront_distribution" "main" {
  provider = aws.primary
  enabled  = true
}
```

**Region:** Deployed in primary region (us-east-1) but serves globally
**Status:** Enabled (active)

## Origin Configuration

### S3 Bucket Origin

```hcl
origin {
  domain_name = aws_s3_bucket.origin.bucket_regional_domain_name
  origin_id   = "s3Origin"
}
```

**Bucket Name:** `app-content-{AWS_ACCOUNT_ID}`
**Region:** us-east-1 (primary)
**Domain:** Automatically generated S3 regional endpoint

**Purpose:** Single source of truth for application content (assets, static files, documentation)

### Origin Security

- **Public Access:** Bucket is NOT publicly accessible
- **Access Method:** CloudFront Origin Access Control (OAC) — CloudFront can access, external clients cannot
- **Bucket Policy:** Restricted to CloudFront distribution only (not configured in initial Terraform, should be added)

**Recommended Bucket Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Service": "cloudfront.amazonaws.com"
    },
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::app-content-{ACCOUNT_ID}/*",
    "Condition": {
      "StringEquals": {
        "AWS:SourceArn": "arn:aws:cloudfront::ACCOUNT_ID:distribution/{DISTRIBUTION_ID}"
      }
    }
  }]
}
```

## Caching Behavior

### Default Cache Behavior

```hcl
default_cache_behavior {
  allowed_methods  = ["GET", "HEAD"]
  cached_methods   = ["GET", "HEAD"]
  target_origin_id = "s3Origin"
}
```

**Allowed Methods:** GET, HEAD only (no PUT, POST, DELETE from edge)
**Cached Methods:** GET, HEAD (responses cached at edges)

### TTL Configuration

| Parameter | Value | Duration | Purpose |
|-----------|-------|----------|---------|
| min_ttl | 0 | immediately | Minimum cache time at edge |
| default_ttl | 3600 | 1 hour | Default cache duration |
| max_ttl | 86400 | 24 hours | Maximum cache age before revalidation |

**Behavior:**
1. S3 object requested via CloudFront
2. If in cache and age < default_ttl (1 hour): served from cache
3. If age > default_ttl: revalidate with S3 (If-Modified-Since)
4. If age > max_ttl (24 hours): must fetch fresh copy from S3

### Query String & Cookie Forwarding

```hcl
forwarded_values {
  query_string = false
  cookies {
    forward = "none"
  }
}
```

**Query Strings:** Not forwarded to S3 origin
  - `GET /file.html?v=1` and `GET /file.html?v=2` treated as same cached object
  - Reduces cache misses for versioned assets

**Cookies:** Not forwarded
  - CloudFront ignores cookies in request
  - Static S3 content doesn't need cookies

## Viewer Protocol Policy

```hcl
viewer_protocol_policy = "redirect-to-https"
```

**Behavior:**
- HTTP requests → 301 redirect to HTTPS
- HTTPS requests → direct response from edge
- Enforces encryption in transit

**Alternative Policies:**
- `allow-all`: Both HTTP and HTTPS (not secure)
- `https-only`: Reject HTTP (403) without redirect

## SSL/TLS Configuration

```hcl
viewer_certificate {
  cloudfront_default_certificate = true
}
```

**Certificate:** CloudFront default certificate (*.cloudfront.net)
**Domain:** Distribution domain automatically assigned (e.g., d123abc.cloudfront.net)

**Alternative (Recommended for Production):**
```hcl
viewer_certificate {
  acm_certificate_arn      = aws_acm_certificate.main.arn
  ssl_support_method       = "sni-only"
  minimum_tls_version      = "TLSv1.2_2021"
}
```

This would:
- Use custom domain (e.g., cdn.app.example.com)
- Require ACM certificate
- Support SNI (Server Name Indication)
- Enforce minimum TLS 1.2

## Geo-Restriction

```hcl
restrictions {
  geo_restriction {
    restriction_type = "none"
  }
}
```

**Type:** none — no geographic restrictions
**Alternative Types:**
- `whitelist`: Only serve in specified countries
- `blacklist`: Block specified countries

**Use Case:** GDPR compliance, licensing restrictions, DDoS mitigation

## Distribution Domains

### CloudFront Domain

Automatically assigned domain:
```
https://d{random-id}.cloudfront.net
```

Example: `https://d3a1b2c3d.cloudfront.net`

### Custom Domain (Future)

To use custom domain (e.g., `cdn.app.example.com`):

1. Create ACM certificate for domain
2. Add Route53 A record pointing to CloudFront domain
3. Update viewer_certificate configuration
4. Update S3 bucket policy to include custom domain

## Cache Invalidation

### Automatic Invalidation
- TTL-based: Automatic revalidation after max_ttl (24 hours)
- S3 invalidation: Not automatic

### Manual Invalidation
Terraform doesn't support cache invalidation, but can be done via:

```bash
# Clear entire distribution cache
aws cloudfront create-invalidation \
  --distribution-id {DISTRIBUTION_ID} \
  --paths "/*"

# Clear specific paths
aws cloudfront create-invalidation \
  --distribution-id {DISTRIBUTION_ID} \
  --paths "/api/*" "/static/*"
```

**Cost:** First 1000 invalidations per month free, then $0.005 per invalidation

## Request Flow

### Cache HIT (Edge Has Current Copy)

```
Client Request
    ↓
CloudFront Edge Location (nearest geographically)
    ↓
Cache HIT — object present and not expired
    ↓
Serve from cache (instant response)
```

**Metrics:** Low latency, reduced S3 requests

### Cache MISS (Edge Needs Fresh Copy)

```
Client Request
    ↓
CloudFront Edge Location
    ↓
Cache MISS — object not in cache or expired
    ↓
Forward to Origin (S3 bucket in us-east-1)
    ↓
S3 returns object
    ↓
Edge caches response
    ↓
Client receives response (higher latency than cache hit)
```

**Metrics:** Higher latency on first request, S3 data transfer charges

## Performance Metrics

### Cache Hit Ratio

**Expected:** 80-95% for static content

If serving dynamic content:
- Lower cache hit ratio (50-70%)
- Consider moving dynamic content to different endpoint
- Use CloudFront Lambda@Edge for dynamic transformations

### Edge Locations Used

CloudFront automatically routes requests to nearest edge based on:
- Geographic proximity
- Current latency
- Network availability

**Global Coverage:** 80+ edge locations worldwide

## Compression

Not explicitly configured, but CloudFront automatically compresses:
- Text formats (HTML, CSS, JavaScript, JSON)
- Content-Type: application/json, text/*, etc.
- Reduces bandwidth by ~60-70% for text content

## Monitoring & Logging

### CloudWatch Metrics (Enabled by Default)

- Requests (GET, HEAD, etc.)
- Bytes in/out
- Cache hit/miss ratios
- 4xx, 5xx error rates
- Origin latency

### Access Logs (Optional, Not Enabled)

Would log each request to S3 with details:
- Request timestamp
- Edge location
- Client IP
- Request path
- HTTP status
- Bytes sent/received

**Enable for audit/debugging:**

```hcl
logging_config {
  include_cookies = false
  bucket          = aws_s3_bucket.logs.bucket_regional_domain_name
  prefix          = "cloudfront-logs/"
}
```

## Security Best Practices

### Implemented
✓ HTTPS enforcement (redirect-to-https)
✓ S3 bucket not publicly accessible
✓ GET/HEAD only (no mutations at edge)

### Recommended (Not Yet Implemented)
- [ ] Enable WAF (Web Application Firewall)
- [ ] Add origin shield (extra caching layer)
- [ ] Enable access logs for audit trail
- [ ] Use custom domain with ACM certificate
- [ ] Implement CloudFront functions for request filtering
- [ ] Add Origin Access Identity (OAI) or OAC for S3 access control

## Cost Analysis

### Pricing Components

| Component | Cost (Estimate) | Notes |
|-----------|-----------------|-------|
| Data transfer out | $0.085/GB | Variable by region |
| HTTP/HTTPS requests | $0.0075/10K reqs | Depends on traffic |
| Invalidations | $0.005 per (after 1000 free/month) | For cache refresh |
| Origin shield | $0.01/request | Optional, recommended |

### Cost Optimization
- Cache long-lived content (increase default_ttl)
- Use Gzip compression (enabled by default for text)
- Minimize cache invalidations
- Monitor cache hit ratio (target: >80%)

## Deployment Order

1. Create S3 bucket: `aws_s3_bucket.origin`
2. Create CloudFront distribution
3. Get distribution domain (d{id}.cloudfront.net)
4. (Optional) Add Route53 ALIAS record pointing to CloudFront
5. Test access via CloudFront domain
6. Enable access logs (optional)
7. Configure WAF (optional)

## Integration with Disaster Recovery

- **Primary Region Failure:** CloudFront still serves cached content from edge locations
- **S3 Bucket Failure:** CloudFront returns 503 (Service Unavailable) after origin timeout
- **Cross-Region Replication (Future):** Add secondary S3 bucket in us-west-2 with failover origin

**Example Failover Configuration (Future):**

```hcl
origin {
  domain_name = aws_s3_bucket.primary.regional_domain_name
  origin_id   = "primary"
  failover_criteria {
    status_codes = [500, 502, 503, 504]
  }
}

origin {
  domain_name = aws_s3_bucket.secondary.regional_domain_name
  origin_id   = "secondary"
}

default_cache_behavior {
  origin_id = "primary"
  # Terraform doesn't support origin failover in default_cache_behavior
  # Must use Lambda@Edge or origin groups workaround
}
```

## Troubleshooting

### High Latency
- Check cache hit ratio (CloudWatch)
- Verify S3 bucket is in same region as origin
- Check origin shield enabled
- Monitor network latency to nearest edge

### Cache Not Updating
- Verify TTL settings (min_ttl, default_ttl, max_ttl)
- Check if S3 object is actually updated (version ID)
- Perform manual invalidation if needed
- Wait for object age to exceed max_ttl

### 503 Service Unavailable
- S3 bucket down or unreachable
- S3 bucket policy doesn't allow CloudFront
- Health check failing on origin
