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

# Database dependencies
resource "aws_security_group" "db" {
  provider = aws.primary
  vpc_id   = aws_vpc.primary.id
  name     = "app-db"
}

resource "aws_db_subnet_group" "postgres" {
  provider   = aws.primary
  name       = "postgres-sg"
  subnet_ids = [aws_subnet.primary_a.id, aws_subnet.primary_b.id]
}

resource "aws_rds_cluster" "postgres" {
  provider             = aws.primary
  cluster_identifier   = "postgres"
  engine               = "aurora-postgresql"
  db_subnet_group_name = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.db.id]
}
