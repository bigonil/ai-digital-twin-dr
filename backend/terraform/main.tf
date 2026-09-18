# Sample Terraform — AWS DR topology
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = "us-east-1"
  alias  = "primary"
}

provider "aws" {
  region = "us-west-2"
  alias  = "secondary"
}

# Networking
resource "aws_vpc" "primary" {
  provider   = aws.primary
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "primary_a" {
  provider   = aws.primary
  vpc_id     = aws_vpc.primary.id
  cidr_block = "10.0.1.0/24"
}

resource "aws_subnet" "primary_b" {
  provider   = aws.primary
  vpc_id     = aws_vpc.primary.id
  cidr_block = "10.0.2.0/24"
}

# Private subnets for databases
resource "aws_subnet" "private_a" {
  provider   = aws.primary
  vpc_id     = aws_vpc.primary.id
  cidr_block = "10.0.11.0/24"
}

resource "aws_subnet" "private_b" {
  provider   = aws.primary
  vpc_id     = aws_vpc.primary.id
  cidr_block = "10.0.12.0/24"
}

# Database dependencies
resource "aws_security_group" "db" {
  provider = aws.primary
  vpc_id   = aws_vpc.primary.id
  name     = "app-db"
}

resource "aws_db_subnet_group" "postgres" {
  provider   = aws.primary
  name       = "postgres-sg"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_rds_cluster" "postgres" {
  provider             = aws.primary
  cluster_identifier   = "postgres"
  engine               = "aurora-postgresql"
  db_subnet_group_name = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.db.id]
}

resource "aws_rds_cluster_instance" "postgres_primary" {
  provider           = aws.primary
  cluster_identifier = aws_rds_cluster.postgres.id
  instance_class     = "db.t4.medium"
  engine             = aws_rds_cluster.postgres.engine
  engine_version     = aws_rds_cluster.postgres.engine_version
}

# S3 bucket for CloudFront origin
resource "aws_s3_bucket" "origin" {
  provider = aws.primary
  bucket   = "app-content-${data.aws_caller_identity.current.account_id}"
}

data "aws_caller_identity" "current" {
  provider = aws.primary
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "main" {
  provider = aws.primary
  enabled  = true

  origin {
    domain_name = aws_s3_bucket.origin.bucket_regional_domain_name
    origin_id   = "s3Origin"
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3Origin"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Secondary region VPC and networking
resource "aws_vpc" "secondary" {
  provider   = aws.secondary
  cidr_block = "10.1.0.0/16"
}

resource "aws_subnet" "secondary_private_a" {
  provider   = aws.secondary
  vpc_id     = aws_vpc.secondary.id
  cidr_block = "10.1.11.0/24"
}

resource "aws_subnet" "secondary_private_b" {
  provider   = aws.secondary
  vpc_id     = aws_vpc.secondary.id
  cidr_block = "10.1.12.0/24"
}

resource "aws_security_group" "db_secondary" {
  provider = aws.secondary
  vpc_id   = aws_vpc.secondary.id
  name     = "app-db-secondary"
}

resource "aws_db_subnet_group" "postgres_secondary" {
  provider   = aws.secondary
  name       = "postgres-sg-secondary"
  subnet_ids = [aws_subnet.secondary_private_a.id, aws_subnet.secondary_private_b.id]
}

# Secondary RDS cluster — read replica of primary (cross-region failover)
# DEPENDS_ON: aws_rds_cluster.postgres (primary region)
resource "aws_rds_cluster" "postgres_secondary" {
  provider             = aws.secondary
  cluster_identifier   = "postgres-secondary"
  engine               = "aurora-postgresql"
  db_subnet_group_name = aws_db_subnet_group.postgres_secondary.name
  vpc_security_group_ids = [aws_security_group.db_secondary.id]
}

resource "aws_rds_cluster_instance" "postgres_secondary" {
  provider           = aws.secondary
  cluster_identifier = aws_rds_cluster.postgres_secondary.id
  instance_class     = "db.t4.medium"
  engine             = aws_rds_cluster.postgres_secondary.engine
  engine_version     = aws_rds_cluster.postgres_secondary.engine_version
}

# Route53 hosted zone for failover routing
resource "aws_route53_zone" "main" {
  provider = aws.primary
  name     = "app.example.com"
}

# Health check for primary RDS endpoint
resource "aws_route53_health_check" "primary_rds" {
  provider          = aws.primary
  type              = "HTTPS"
  ip_address        = "0.0.0.0"  # Placeholder; replace with actual RDS endpoint
  port              = 5432
  failure_threshold = 3
  request_interval  = 30
}

# Health check for secondary RDS endpoint
resource "aws_route53_health_check" "secondary_rds" {
  provider          = aws.primary
  type              = "HTTPS"
  ip_address        = "0.0.0.0"  # Placeholder; replace with actual secondary RDS endpoint
  port              = 5432
  failure_threshold = 3
  request_interval  = 30
}

# Primary failover record
resource "aws_route53_record" "postgres_primary" {
  provider        = aws.primary
  zone_id         = aws_route53_zone.main.zone_id
  name            = "postgres.app.example.com"
  type            = "CNAME"
  ttl             = 60
  set_identifier  = "primary"
  failover_routing_policy {
    type = "PRIMARY"
  }
  records         = [aws_rds_cluster.postgres.endpoint]
  health_check_id = aws_route53_health_check.primary_rds.id
}

# Secondary failover record
resource "aws_route53_record" "postgres_secondary" {
  provider        = aws.primary
  zone_id         = aws_route53_zone.main.zone_id
  name            = "postgres.app.example.com"
  type            = "CNAME"
  ttl             = 60
  set_identifier  = "secondary"
  failover_routing_policy {
    type = "SECONDARY"
  }
  records         = [aws_rds_cluster.postgres_secondary.endpoint]
  health_check_id = aws_route53_health_check.secondary_rds.id
}
