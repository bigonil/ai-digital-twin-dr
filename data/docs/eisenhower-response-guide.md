# Eisenhower DR Response Guide — ATHENA Platform

## Overview

ATHENA classifies every disaster simulation into one of four Eisenhower quadrants based on urgency (RTO breach, cascade in progress, replication lag) and importance (affects production, critical blast radius ≤ 2 hops). The quadrant determines the response posture, escalation path, and whether the MCP server auto-routes to a recovery plan.

---

## Q1 — Urgent + Important: ACT IMMEDIATELY

**Definition:** RTO or RPO is breached, or cascade is actively spreading to critical (distance ≤ 2) production nodes.

**Trigger conditions (any one sufficient):**
- `worst_case_rto_minutes > rto_target_minutes` (RTO already breached)
- `replication_lag_min > rpo_target_minutes` (RPO breached)
- `cascade_in_progress = True` AND (`affects_production = True` OR `critical_blast = True`)

**Automatic MCP action:** `simulate_disaster` immediately appends `get_recovery_plan` response — no second tool call needed.

**Response protocol:**
1. **T+0:** Page on-call SRE via PagerDuty — P1 incident
2. **T+2min:** Start executing recovery runbook — no investigation delay
3. **T+5min:** Post to #incidents Slack: "P1 ACTIVE — [node] failing, blast radius [N] nodes, RTO breached"
4. **T+10min:** Escalate to engineering lead if recovery not progressing
5. **T+15min:** Executive update if user impact confirmed and RTO still breached
6. **T+30min:** War room if multiple nodes still failing

**Examples of Q1 scenarios:**
- Aurora primary fails → 3 app servers cascade → ALB returns 503 (full outage)
- RTO target = 15 min; actual RTO = 45 min (3x breach)
- Replication lag = 20 min on Aurora replica (RPO breached before failover)
- AZ failure affecting both Aurora and Redis simultaneously

**Key metrics to monitor during Q1 response:**
- `RDS/DatabaseConnections` — must recover to > 0
- `ApplicationELB/HealthyHostCount` — must recover to ≥ 2
- Error rate — must drop below 1% before declaring resolved
- Replication lag — must drop to < 30 seconds

---

## Q2 — Not Urgent + Important: PLAN & SCHEDULE

**Definition:** No active breach, but the system is in a degraded state that will breach SLAs if unaddressed. Affects production.

**Trigger conditions:**
- `worst_case_rto_minutes` is 70–100% of `rto_target_minutes` (warning zone, not yet breached)
- `affects_production = True` or `critical_blast = True`
- No active cascade (`cascade_in_progress = False`)

**Response protocol:**
1. **T+0:** Create tracking ticket in issue tracker (not a pager alert)
2. **T+30min:** Assign to on-call or next available engineer
3. **T+2h:** Complete investigation and document findings
4. **T+4h:** Execute remediation during low-traffic window if possible
5. **T+24h:** Close ticket with root cause and prevention steps

**Examples of Q2 scenarios:**
- Aurora replica lag at 25 seconds (threshold = 30 seconds) — approaching RPO limit
- One of two ALB targets unhealthy — capacity reduced but service still up
- Redis `FreeableMemory` at 150 MB — approaching eviction threshold
- ASG running at `min_size` (2 instances) after one was terminated by spot reclaim

**Recommended actions for Q2:**
- Scale up before problem becomes urgent (add replica, increase ASG desired capacity)
- Review and adjust CloudWatch alarm thresholds if false-positive rate is high
- Run `check_drift` tool to compare Terraform state vs actual Neo4j graph
- Schedule maintenance window for full remediation

**Q2 escalation to Q1:** If `apply_escalation` detects Q2 event unresolved after 15 minutes and conditions worsen to breach, reclassify to Q1 and page on-call.

---

## Q3 — Urgent + Not Important: DELEGATE & MONITOR

**Definition:** Active failure or cascade, but the affected nodes are non-critical (distance > 2, non-production, or internal tooling).

**Trigger conditions:**
- `cascade_in_progress = True` OR RTO-related urgency signal
- `affects_production = False` AND `critical_blast = False` (no nodes at distance ≤ 2)

**Response protocol:**
1. **T+0:** Automated alert to team Slack channel (not pager)
2. **T+5min:** Acknowledge and assign to next available engineer (not on-call rotation)
3. **T+30min:** Begin investigation — lower urgency, can wait for context
4. **T+4h:** Resolve or create tracking ticket for next sprint

**Escalation timer:** If Q3 event is unresolved after **15 minutes** (`ESCALATION_WINDOW_MIN`), `apply_escalation()` promotes it to Q1. This prevents neglected Q3 events from becoming production crises.

**Examples of Q3 scenarios:**
- Development environment database failing (cascade in progress, non-production)
- Internal monitoring tool (Grafana) down — urgent but non-critical to users
- Batch processing job failing in background (cascade in SQS consumers, no user impact)
- DR region (eu-west-1) resources failing when primary (us-east-1) is healthy

**Actions for Q3:**
- Do NOT page on-call engineer unless escalation timer fires
- Investigate and document root cause
- Fix within business hours if in working hours; otherwise log for next day

---

## Q4 — Not Urgent + Not Important: DEFER

**Definition:** Failure detected in non-critical component with no production impact and no active cascade. System is within RTO/RPO targets.

**Trigger conditions:**
- `cascade_in_progress = False`
- `affects_production = False`
- `critical_blast = False`
- `worst_case_rto_minutes` well within `rto_target_minutes`

**Response protocol:**
1. Create backlog ticket
2. Review in next sprint planning
3. No immediate action required

**Examples of Q4 scenarios:**
- Unused staging resource failing (no dependencies, non-production)
- Slow replication on replica that is not currently used for reads
- Monitoring exporter failing on non-critical internal service
- Log aggregation pipeline delayed (no user impact)

---

## Eisenhower Escalation Flow

```
Simulation result → classify_dr_event(EisenhowerInput)
      │
      ├── Q1 → Page on-call NOW + auto-attach recovery plan (MCP)
      │         Execute runbook immediately
      │
      ├── Q2 → Create ticket + notify team (Slack)
      │         Remediate within 4 hours
      │         Monitor for escalation to Q1
      │
      ├── Q3 → Notify team (Slack only)
      │         15-min escalation timer starts (apply_escalation)
      │         → if unresolved: escalate to Q1
      │
      └── Q4 → Create backlog ticket
                No immediate action
```

---

## Classification Constants

| Parameter | Value | Description |
|---|---|---|
| `URGENCY_RATIO_WARN` | 0.70 | RTO at 70% of target triggers warning (Q2 consideration) |
| `ESCALATION_WINDOW_MIN` | 15.0 | Minutes before Q3 auto-escalates to Q1 |
| `critical_blast` threshold | distance ≤ 2 | Nodes within 2 hops of origin are "critical blast" |

---

## Response Time SLA by Quadrant

| Quadrant | Acknowledge | First Action | Resolution Target |
|---|---|---|---|
| Q1 | 2 minutes | 5 minutes | Within RTO target |
| Q2 | 30 minutes | 2 hours | 24 hours |
| Q3 | 15 minutes | 30 minutes | 4 hours (or escalate to Q1) |
| Q4 | Next business day | Next sprint | Best effort |

---

## Communication Templates

**Q1 Incident Slack message:**
```
🚨 P1 ACTIVE — [node_name] ([node_type]) FAILING
Blast radius: [N] nodes affected | Max depth: [D] hops
Worst-case RTO: [X] min (target: [Y] min) — BREACHED
Eisenhower: Q1 — ACT IMMEDIATELY
Runbook: [link] | Incident: [PagerDuty link]
On-call: @[engineer]
```

**Q2 Alert Slack message:**
```
⚠️ Q2 DR Warning — [node_name] approaching SLA threshold
RTO at [X]% of target ([Y]min / [Z]min)
Blast radius: [N] nodes | Affects production: Yes
Action required within 4 hours. Ticket: [link]
```

**Q3 Alert Slack message:**
```
🔔 Q3 DR Alert — [node_name] cascade in non-critical path
Affected nodes: [N] | Production impact: No
Escalation in 15 minutes if unresolved. Assign: @team
```
