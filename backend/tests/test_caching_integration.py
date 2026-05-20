"""
Integration test: verify Anthropic prompt caching actually engages.

Requires a real API key — skipped automatically when ANTHROPIC_API_KEY is not set.
Uses claude-sonnet-4-6 (1 024-token minimum) with a padded system block that
guarantees the cached prefix exceeds 1 024 tokens, so cache_read_input_tokens > 0
on the second identical call.

Run:
    ANTHROPIC_API_KEY=sk-ant-... pytest tests/test_caching_integration.py -v
"""
import os
import textwrap

import pytest

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

pytestmark = pytest.mark.skipif(
    not ANTHROPIC_API_KEY,
    reason="ANTHROPIC_API_KEY not set — skipping live caching integration test",
)

# Sonnet 4.6: 1 024-token minimum cacheable prefix.
# We build a system block of ~5 000 chars (~1 250 tokens) to safely clear the bar.
_PADDING = textwrap.dedent("""\
    ## AWS Disaster Recovery Reference

    This section provides foundational AWS DR knowledge used across all runbooks.

    ### RTO/RPO Targets
    RTO (Recovery Time Objective) is the maximum acceptable downtime. RPO (Recovery Point
    Objective) is the maximum acceptable data loss window. Both are stored per InfraNode in
    Neo4j and compared against effective values computed from the node's recovery strategy:
      - replica_fallback  → effective_rto = base_rto × 0.5
      - multi_az          → effective_rto = base_rto × 0.3
      - stateless         → effective_rto = base_rto × 0.4
      - backup_fallback   → effective_rto = base_rto × 2.0

    ### Aurora Failover
    Aurora promotes a read replica in ~30 seconds when Multi-AZ is enabled. The cluster
    endpoint DNS automatically updates; applications using the cluster endpoint reconnect
    without configuration changes. RDS Proxy reduces connection storms by maintaining a
    persistent pool and queuing new connections during failover.

    ### ElastiCache Redis Failover
    ElastiCache with cluster mode disabled promotes the primary replica in <60 seconds.
    Cluster mode enabled shards across multiple nodes; a shard failure triggers promotion
    of the replica for that shard only. ReplicationLag metric is the live RPO proxy.

    ### Application Load Balancer
    ALBs are inherently multi-AZ. Route53 health checks (10-second interval, 3 failures)
    detect ALB unhealthiness in ~30 seconds. With AliasTarget records (no TTL), DNS
    propagation after a health check state change takes effect in the next resolver refresh.

    ### EC2 / Auto Scaling Groups
    ASGs replace unhealthy instances automatically. The replacement timeline is:
      1. Health check grace period expires (~300 s default)
      2. ASG marks instance unhealthy
      3. ASG launches replacement in a healthy AZ
      4. New instance passes ELB health checks and enters InService state
    Warm pools (pre-launched instances) reduce cold-start time from 5 min to <60 s.

    ### S3 Cross-Region Replication
    CRR with Replication Time Control (RTC) guarantees 99.99% of objects replicated
    within 15 minutes. Without RTC, replication is best-effort (typically < 1 hour).
    S3 standard is 11-nines durability; RPO for CRR is the replication lag at failure time.

    ### SQS Dead-Letter Queues
    Messages that fail processing N times (maxReceiveCount) move to the DLQ. During DR,
    redrive the DLQ back to the source queue once the consumer is healthy:
      aws sqs start-message-move-task \\
        --source-arn <dlq-arn> --destination-arn <source-queue-arn>

    ### Route53 Failover Routing
    Failover routing requires one PRIMARY and one SECONDARY record set. When the PRIMARY
    health check fails, Route53 serves the SECONDARY record. Minimum TTL for fast failover
    is 60 seconds. Use AliasTarget for ALB endpoints (no TTL, AWS-managed).

    ### IAM Prerequisites for DR
    All DR automation assumes the following roles exist in the DR region:
      - athena-dr-rds-role        (rds:FailoverDBCluster, rds:PromoteReadReplica)
      - athena-dr-elasticache-role (elasticache:TestFailover, elasticache:ModifyReplicationGroup)
      - athena-dr-route53-role    (route53:ChangeResourceRecordSets)
      - athena-dr-asg-role        (autoscaling:SetDesiredCapacity, ec2:TerminateInstances)

    Assume these roles before executing any recovery step that touches AWS resources.
""")

# Pad to ~5 000 chars to guarantee > 1 024 tokens
_SYSTEM_BLOCK = ("You are a senior SRE specializing in AWS disaster recovery. "
                 "Answer concisely and only about DR topics.\n\n" + _PADDING * 3)


@pytest.mark.asyncio
async def test_cache_activates_on_second_call():
    """Second call with identical prefix must have cache_read_input_tokens > 0."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    cache_ctrl = {"type": "ephemeral"}

    kwargs = dict(
        model="claude-sonnet-4-6",
        max_tokens=64,
        system=[{"type": "text", "text": _SYSTEM_BLOCK, "cache_control": cache_ctrl}],
        messages=[{"role": "user", "content": "What is RTO?"}],
    )

    # First call — writes the cache
    r1 = await client.messages.create(**kwargs)
    u1 = r1.usage
    created = getattr(u1, "cache_creation_input_tokens", 0)
    assert created > 0, (
        f"First call did not write cache (cache_creation_input_tokens={created}). "
        f"Likely the system block is below the 1 024-token minimum for claude-sonnet-4-6. "
        f"input_tokens={u1.input_tokens}"
    )

    # Second call — must read from cache
    r2 = await client.messages.create(**kwargs)
    u2 = r2.usage
    cache_read = getattr(u2, "cache_read_input_tokens", 0)
    assert cache_read > 0, (
        f"Second call did not hit cache (cache_read_input_tokens={cache_read}). "
        f"cache_creation_input_tokens={getattr(u2, 'cache_creation_input_tokens', 0)}, "
        f"input_tokens={u2.input_tokens}"
    )


@pytest.mark.asyncio
async def test_cache_miss_when_prefix_changes():
    """Changing the user message must NOT invalidate the system-level cache."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    cache_ctrl = {"type": "ephemeral"}

    system = [{"type": "text", "text": _SYSTEM_BLOCK, "cache_control": cache_ctrl}]

    # First call — writes cache for system block
    r1 = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=32,
        system=system,
        messages=[{"role": "user", "content": "What is RTO?"}],
    )
    _ = getattr(r1.usage, "cache_creation_input_tokens", 0)

    # Second call — different user message; system block cache should still be read
    r2 = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=32,
        system=system,
        messages=[{"role": "user", "content": "What is RPO?"}],
    )
    cache_read = getattr(r2.usage, "cache_read_input_tokens", 0)
    assert cache_read > 0, (
        "Changing the user message should NOT invalidate the cached system block. "
        f"cache_read_input_tokens={cache_read}"
    )
