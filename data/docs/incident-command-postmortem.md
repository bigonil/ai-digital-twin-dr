# Incident Command Structure & Post-Mortem Guide

## Overview

Effective disaster recovery requires clear role assignment, structured communication, and systematic post-mortem analysis. Disorganized incident response is a leading cause of RTO overrun. This guide defines the incident command structure, communication protocols, and blameless post-mortem framework used alongside ATHENA DR simulations.

---

## Incident Command Structure

### Role Definitions

**Incident Commander (IC):**
- Single decision-maker. All escalation flows through IC.
- Coordinates between SRE, DBA, and Product/Customer teams
- Makes the call to failover, rollback, or declare resolved
- Does NOT perform technical tasks — delegates to responders
- Owns status page updates every 15 minutes during active incident

**Primary SRE (Technical Lead):**
- Executes recovery runbook steps
- Reports status to IC every 5 minutes
- Calls out blockers immediately
- Documents all actions with timestamps in incident channel

**Secondary SRE (Shadow):**
- Reviews each step before execution (two-pair review for destructive actions)
- Runs verification commands to confirm recovery progress
- Takes over as primary if primary SRE is unavailable

**DBA (for database incidents):**
- Owns Aurora/RDS failover decisions
- Validates data integrity after restore
- Confirms RPO (actual data loss window)

**Communications Lead:**
- Updates status page (never wait for IC to remember)
- Drafts customer communication for P1 incidents with user impact
- Handles Slack #incidents channel and executive updates

---

## P1 War Room Protocol (Q1 Eisenhower Events)

### Activation Criteria
- ATHENA classifies event as Q1 (urgent + important)
- ALB `HealthyHostCount` = 0 for > 2 consecutive minutes
- Aurora `DatabaseConnections` = 0 for > 2 consecutive minutes
- Multiple services failing simultaneously

### War Room Setup (first 5 minutes)
1. IC pages all roles via PagerDuty using "War Room" escalation policy
2. All responders join video call within 2 minutes of page
3. IC takes roll call: confirm IC, Primary SRE, Secondary SRE, DBA present
4. Primary SRE shares screen showing ATHENA dashboard + CloudWatch
5. IC states: "This is a P1 incident. [Node name] is failing, blast radius [N] nodes. RTO target [X] min. Primary SRE, begin runbook."

### Communication Cadence During P1
- **T+0:** #incidents "🚨 P1 ACTIVE — [service] down. War room started. IC: @[name]"
- **T+5min:** Status page: "We are investigating an issue affecting [service]."
- **T+15min:** Status page update (even if no progress): "Investigation ongoing. Next update in 10 minutes."
- **T+30min:** Executive update via direct message if RTO target will be missed
- **Every 15min:** Status page update until resolved

### Decision Points Requiring IC Authorization
- Initiate region failover (us-east-1 → eu-west-1)
- Roll back a deployment
- Take a service into maintenance mode
- Extend RTO beyond target (declare "we won't hit SLA")
- Page additional on-call engineers from other teams

---

## P2/P3 Protocol (Q2/Q3 Eisenhower Events)

**P2 (Q2):** Assign to on-call engineer. No war room. Update every 30 minutes in Slack thread.

**P3 (Q3):** Assign to team queue. Handle within 4 hours. Escalation timer running (15 minutes → Q1 if unresolved).

---

## Incident Timeline Logging

Every action must be logged with timestamp in the incident Slack channel. Template:

```
[HH:MM UTC] ACTION: [what was done]
[HH:MM UTC] VERIFY: [command run and output]
[HH:MM UTC] STATUS: [healthy/degraded/failing]
[HH:MM UTC] BLOCKER: [what's preventing progress] (if applicable)
```

Example:
```
[14:23 UTC] ACTION: Started Aurora failover: aws rds failover-db-cluster --db-cluster-identifier app-postgres
[14:25 UTC] VERIFY: aws rds describe-db-clusters → Status: available, new writer: app-postgres-2
[14:26 UTC] STATUS: Aurora healthy. Starting app connection pool reset.
[14:28 UTC] ACTION: SSM Run Command → systemctl restart app-service on all 6 instances
[14:31 UTC] VERIFY: ALB HealthyHostCount = 6. Error rate = 0.02%.
[14:31 UTC] STATUS: Service recovered. Monitoring for 10 minutes before declaring resolved.
```

---

## Incident Severity Classification

| Severity | Definition | RTO Target | Communication |
|---|---|---|---|
| P1 | Full service outage — all users affected | 15 min | Status page, Slack #incidents, executive |
| P2 | Partial outage — subset of users or features affected | 1 hour | Slack #incidents |
| P3 | Degraded performance — no data loss, no outage | 4 hours | Slack thread |
| P4 | Minor issue — single user or internal tool | Next business day | Ticket only |

---

## Blameless Post-Mortem Framework

### Timing
- P1: Post-mortem within 48 hours of resolution
- P2: Post-mortem within 1 week
- P3/P4: Brief retrospective in next team meeting (optional)

### Document Structure

**Section 1: Executive Summary (3 sentences)**
- What failed, for how long, and what the user impact was
- What was the actual RTO and RPO (vs target)
- One-sentence summary of root cause

**Section 2: Incident Timeline**
Complete chronological log from first alert to full resolution. Include:
- Detection delay (T_failure → T_detected)
- Time to first action (T_detected → T_action)
- Each major recovery step with duration
- Any delays and why they occurred

**Section 3: Root Cause Analysis — Five Whys**
```
Symptom: [what users experienced]
Why 1: [immediate cause]
Why 2: [cause of Why 1]
Why 3: [cause of Why 2]
Why 4: [cause of Why 3]
Why 5: [systemic root cause]
```
Example:
```
Symptom: Users received 503 errors for 12 minutes
Why 1: ALB had 0 healthy targets
Why 2: All app instances failed health checks
Why 3: Aurora failover caused connection pool exhaustion
Why 4: Connection pool had no pre-ping configured (stale connections hung)
Why 5: No standard connection pool configuration existed; each team configured independently
```

**Section 4: Contributing Factors (NOT blame)**
List conditions that made the incident worse or harder to resolve:
- Monitoring gap: alarm threshold was too high (fired too late)
- Process gap: runbook didn't cover connection pool reset step
- Tool gap: ATHENA simulation didn't account for connection storm in RTO estimate
- Knowledge gap: on-call engineer was first week on rotation

**Section 5: Action Items**

| Action | Owner | Due Date | Priority |
|---|---|---|---|
| Add `pool_pre_ping=True` to all SQLAlchemy configs | Backend team | +7 days | P0 |
| Add connection storm simulation to ATHENA model | SRE | +14 days | P1 |
| Lower Aurora `HealthyHostCount` alarm threshold | SRE | +3 days | P1 |
| Add runbook step for connection pool reset | On-call lead | +7 days | P1 |

**Section 6: What Went Well**
- Honest recognition of things that helped or worked better than expected
- Examples: ATHENA correctly predicted blast radius; PagerDuty paged the right team; DBA had runbook ready

---

## ATHENA Integration with Post-Mortem

After each real incident, update ATHENA:
1. **Compare predicted vs actual RTO:**
   ```bash
   # Run simulation on the failed node
   curl -X POST http://localhost:8001/api/dr/simulate \
     -H "Content-Type: application/json" \
     -d '{"node_id": "<node-id>", "depth": 5}'
   # Compare worst_case_rto_minutes with actual RTO from incident timeline
   ```
2. **Update RTO/RPO values** if ATHENA was systematically off:
   ```bash
   # Via ATHENA API or direct Neo4j Cypher
   curl -X PATCH http://localhost:8001/api/graph/nodes/<node-id> \
     -d '{"rto_minutes": <actual-average>, "rpo_minutes": <actual-observed>}'
   ```
3. **Log prediction accuracy** for compliance: `POST /api/postmortem` with actual vs predicted values
4. **Update recovery strategy** if incident revealed node is incorrectly classified (e.g., `generic` → `replica_fallback`)
