#!/bin/bash
# Seed RTO/RPO values into Neo4j sample infrastructure
# Run this after ingesting Terraform data to enable compliance auditing

NEO4J_URL="${NEO4J_URL:-http://localhost:7474}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASS="${NEO4J_PASS:-changeme_neo4j}"

echo "Seeding RTO/RPO values into Neo4j..."

# Set default values for all nodes
curl -s -X POST "$NEO4J_URL/db/neo4j/tx/commit" \
  -H "Content-Type: application/json" \
  -u "$NEO4J_USER:$NEO4J_PASS" \
  -d '{
    "statements": [
      {
        "statement": "MATCH (n:InfraNode) SET n.rto_minutes = 45, n.rpo_minutes = 15"
      }
    ]
  }' > /dev/null

# Set specific values by node type
curl -s -X POST "$NEO4J_URL/db/neo4j/tx/commit" \
  -H "Content-Type: application/json" \
  -u "$NEO4J_USER:$NEO4J_PASS" \
  -d '{
    "statements": [
      {"statement": "MATCH (n:InfraNode {type: \"aws_vpc\"}) SET n.rto_minutes = 60, n.rpo_minutes = 30"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_subnet\"}) SET n.rto_minutes = 30, n.rpo_minutes = 15"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_lb\"}) SET n.rto_minutes = 5, n.rpo_minutes = 0"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_autoscaling_group\"}) SET n.rto_minutes = 10, n.rpo_minutes = 0"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_rds_cluster\"}) SET n.rto_minutes = 15, n.rpo_minutes = 1"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_rds_cluster_instance\"}) SET n.rto_minutes = 15, n.rpo_minutes = 1"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_s3_bucket\"}) SET n.rto_minutes = 30, n.rpo_minutes = 1"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_sqs_queue\"}) SET n.rto_minutes = 20, n.rpo_minutes = 0"},
      {"statement": "MATCH (n:InfraNode {type: \"aws_elasticache_replication_group\"}) SET n.rto_minutes = 5, n.rpo_minutes = 0"}
    ]
  }' > /dev/null

# Verify results
echo "Verifying seed data..."
RESULT=$(curl -s -X POST "$NEO4J_URL/db/neo4j/tx/commit" \
  -H "Content-Type: application/json" \
  -u "$NEO4J_USER:$NEO4J_PASS" \
  -d '{
    "statements": [
      {"statement": "MATCH (n:InfraNode) WHERE n.rto_minutes IS NOT NULL RETURN count(n) as nodes_with_rto"}
    ]
  }')

echo "$RESULT" | grep -q "14\|13" && echo "✓ RTO/RPO values seeded successfully" || echo "✗ Failed to seed RTO/RPO values"

echo ""
echo "Node Types and Default Values:"
echo "  AWS VPC                      : RTO=60min, RPO=30min"
echo "  AWS Subnet                   : RTO=30min, RPO=15min"
echo "  AWS Load Balancer            : RTO=5min,  RPO=0min"
echo "  AWS Auto Scaling Group       : RTO=10min, RPO=0min"
echo "  AWS RDS Cluster              : RTO=15min, RPO=1min"
echo "  AWS RDS Cluster Instance     : RTO=15min, RPO=1min"
echo "  AWS S3 Bucket                : RTO=30min, RPO=1min"
echo "  AWS SQS Queue                : RTO=20min, RPO=0min"
echo "  AWS ElastiCache              : RTO=5min,  RPO=0min"
echo ""
echo "Compliance Thresholds (from settings):"
echo "  RTO: 60 minutes"
echo "  RPO: 15 minutes"
echo ""
