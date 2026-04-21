# Sample Terraform — multi-region AWS DR topology for Phase 1 testing
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
  region = "eu-west-1"
  alias  = "dr"
}

# ─── Networking ──────────────────────────────────────────────────────────────

resource "aws_vpc" "primary" {
  provider   = aws.primary
  cidr_block = "10.0.0.0/16"
  tags       = { Name = "primary-vpc", Environment = "prod" }
}

resource "aws_vpc" "dr" {
  provider   = aws.dr
  cidr_block = "10.1.0.0/16"
  tags       = { Name = "dr-vpc", Environment = "dr" }
}

resource "aws_subnet" "primary_a" {
  provider          = aws.primary
  vpc_id            = aws_vpc.primary.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "primary_b" {
  provider          = aws.primary
  vpc_id            = aws_vpc.primary.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

# ─── Load Balancer ───────────────────────────────────────────────────────────

resource "aws_lb" "app" {
  provider           = aws.primary
  name               = "app-alb"
  load_balancer_type = "application"
  subnets            = [aws_subnet.primary_a.id, aws_subnet.primary_b.id]
  tags               = { Name = "app-alb" }
}

# ─── Auto Scaling Group (EC2) ─────────────────────────────────────────────────

resource "aws_autoscaling_group" "app" {
  provider            = aws.primary
  name                = "app-asg"
  min_size            = 2
  max_size            = 10
  desired_capacity    = 3
  vpc_zone_identifier = [aws_subnet.primary_a.id, aws_subnet.primary_b.id]

  tag {
    key                 = "Name"
    value               = "app-server"
    propagate_at_launch = true
  }
}

# ─── RDS Multi-AZ ────────────────────────────────────────────────────────────

resource "aws_rds_cluster" "postgres" {
  provider                = aws.primary
  cluster_identifier      = "app-postgres"
  engine                  = "aurora-postgresql"
  engine_version          = "15.4"
  availability_zones      = ["us-east-1a", "us-east-1b", "us-east-1c"]
  database_name           = "appdb"
  master_username         = "admin"
  master_password         = var.db_password
  backup_retention_period = 7
  preferred_backup_window = "03:00-04:00"
  skip_final_snapshot     = false

  tags = { Name = "app-postgres-primary" }
}

resource "aws_rds_cluster_instance" "postgres_instances" {
  count              = 2
  provider           = aws.primary
  identifier         = "app-postgres-${count.index}"
  cluster_identifier = aws_rds_cluster.postgres.id
  instance_class     = "db.r7g.large"
  engine             = aws_rds_cluster.postgres.engine
}

# ─── S3 with Cross-Region Replication ───────────────────────────────────────

resource "aws_s3_bucket" "data" {
  provider = aws.primary
  bucket   = "app-data-primary-${var.account_id}"
  tags     = { Name = "app-data-primary" }
}

resource "aws_s3_bucket" "data_replica" {
  provider = aws.dr
  bucket   = "app-data-replica-${var.account_id}"
  tags     = { Name = "app-data-replica", ReplicaOf = "app-data-primary" }
}

# ─── SQS ─────────────────────────────────────────────────────────────────────

resource "aws_sqs_queue" "jobs" {
  provider                   = aws.primary
  name                       = "app-jobs.fifo"
  fifo_queue                 = true
  content_based_deduplication = true
  tags                       = { Name = "app-jobs" }
}

resource "aws_sqs_queue" "dlq" {
  provider = aws.primary
  name     = "app-jobs-dlq.fifo"
  fifo_queue = true
  tags     = { Name = "app-jobs-dlq" }
}

# ─── ElastiCache Redis ────────────────────────────────────────────────────────

resource "aws_elasticache_replication_group" "redis" {
  provider                   = aws.primary
  replication_group_id       = "app-redis"
  description                = "Application Redis cache"
  node_type                  = "cache.r7g.large"
  num_node_groups            = 1
  replicas_per_node_group    = 2
  automatic_failover_enabled = true
  tags                       = { Name = "app-redis" }
}

# ─── Variables ───────────────────────────────────────────────────────────────

variable "db_password" {
  type      = string
  sensitive = true
}

variable "account_id" {
  type = string
}
