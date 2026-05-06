# Digital Twin DR Platform — Features Guide

This document describes the 4 new features added to the Digital Twin DR Platform: Compliance, What-If Analysis, Chaos Engineering, and Postmortem Analysis.

## Navigation

All features are accessible via the tab bar at the top of the application:
- **DR Simulator** — Original 3-column disaster simulation interface
- **Compliance** — Audit infrastructure against RTO/RPO thresholds
- **What-If** — Model architecture changes before deployment
- **Postmortem** — Analyze incidents against predictions
- **Chaos** — Run chaos engineering experiments and calculate resilience

---

## Compliance

### Purpose
Continuously audit your infrastructure against compliance thresholds (RTO and RPO), identify vulnerable nodes, and export reports for stakeholders.

### How to Use

1. **Run Audit**: Click "Run Full Audit" to scan all nodes in your topology
2. **View Results**: Results show by status (Pass/Fail/Warning/Skipped)
3. **Filter**: Use the status tabs to focus on failures or warnings
4. **Export**: Download the full audit as JSON for documentation

### What Gets Measured

| Metric | Threshold | Status Logic |
|--------|-----------|---|
| RTO (Recovery Time Objective) | 60 minutes | **Pass** < 48m · **Warning** 48-60m · **Fail** > 60m |
| RPO (Recovery Point Objective) | 15 minutes | **Pass** < 12m · **Warning** 12-15m · **Fail** > 15m |

**Worst-Case Values**: For each node, we calculate the longest RTO/RPO in its entire blast radius. This is the value compared against thresholds.

### Typical Workflow
1. Infrastructure team makes topology changes (adds nodes, changes redundancy)
2. Someone runs audit to verify compliance
3. If failures found, mitigate (add replicas, improve failover)
4. Export report and share with executives

---

## What-If Analysis

### Purpose
Test architecture changes in simulation before deploying to production. Add virtual replicas, change connectivity, and see the impact on blast radius and recovery time.

### How to Use

1. **Select Origin Node**: Choose which node to fail
2. **Add Virtual Nodes**: Create simulated infrastructure (replicas, caches, etc.)
   - ID must start with "virtual-" (auto-prefixed if you enter just a name)
   - Set RTO/RPO if different from baseline
   - Mark as redundant if failover target
3. **Add Virtual Edges**: Connect virtual nodes to existing infrastructure
4. **Run Simulation**: Click "Run What-If" to see baseline vs proposed
5. **Review Delta**: Check blast radius and RTO differences

### Example: Adding a Replica Database

```
Origin Node: primary-db
Virtual Node ID: virtual-replica-db
Type: database
RTO: 30 minutes (same as primary)
Is Redundant: ✓ (can take over if primary fails)

Virtual Edge:
  From: app-server
  To: virtual-replica-db
  Type: DEPENDS_ON
```

Expected result: Reduced blast radius (secondary can serve requests), lower RTO (faster failover).

### Reading Results

- **Blast Radius Delta**: Number of additional/fewer nodes affected (–2 = improvement)
- **RTO Delta**: Time saved/added for recovery (–10m = good)
- **RPO Delta**: Data loss reduction (–5m = less data loss if we fail over)

---

## Chaos Engineering

### Purpose
Proactively test your system's resilience by simulating failures and comparing predictions (what our model says happens) against actual observations.

### How to Use

#### Creating an Experiment

1. **Target Node**: Which component to fail?
2. **Scenario**: What kind of failure?
   - **Terminate**: Complete node removal
   - **Network Loss**: All connections severed
   - **CPU Hog**: High CPU, degraded performance
   - **Disk Full**: No more space
   - **Memory Pressure**: Slowdown due to memory exhaustion
3. **Depth**: How many hops to trace blast radius (1-10)
4. **Notes**: Context for the experiment (optional)

#### Recording Actual Results

After running the test in your lab:

1. **Actual RTO**: How long actual recovery took (minutes)
2. **Failed Nodes**: Which nodes actually went down (may differ from prediction)
3. **Notes**: Observations (e.g., "Failover triggered at 30s, DNS took extra time")

### Resilience Score

```
resilience_score = (RTO Accuracy + Node Accuracy) / 2

RTO Accuracy:
  - If actual ≤ predicted: 1.0 (better than expected)
  - Otherwise: predicted / actual (partially right)

Node Accuracy:
  - Intersection ÷ Union of predicted vs actual failed nodes
  - 1.0 = perfect prediction, 0.0 = completely wrong
```

**Interpretation**:
- **≥ 0.8** → System performed well, predictions accurate
- **0.5 - 0.8** → System had moderate issues or predictions were rough
- **< 0.5** → Significant issues or model needs tuning

### Example Workflow

1. Prediction from simulation: "cpu-hog on db-primary will affect 8 nodes, RTO 45 min"
2. Run actual test: CPU maxes out, triggers failover at 30 min, affects 7 nodes
3. Record: actual_rto_minutes=30, actual_nodes=[7 nodes], notes="faster than expected"
4. Resilience score calculated: ~0.85 (RTO beat prediction, node count close)

---

## Postmortem Analysis

### Purpose
After a real incident, analyze how well your predictive model performed. Compare what you predicted would happen vs what actually happened, measure prediction accuracy, and get recommendations for improvement.

### How to Use

1. **Incident Details**:
   - Title: Descriptive name (e.g., "Primary DB Failover on 2026-04-21")
   - Occurred At: ISO timestamp when incident started
   - Origin Node: Which component actually failed first

2. **Actual Impact**:
   - Failed Nodes: Which nodes went down (multi-select)
   - Actual RTO: Minutes to full recovery
   - Actual RPO: Minutes of data loss (optional)

3. **Reference Simulation** (optional):
   - Compare against a baseline simulation
   - Choose origin node and depth for reference

4. **Results**:
   - Accuracy score shows how well predictions matched reality
   - True Positives: Correctly predicted failures
   - False Positives: Predicted but didn't happen (pessimistic)
   - False Negatives: Missed predictions (optimistic, risky!)

### Accuracy Metrics

```
Precision = TP / (TP + FP)
  → Of the nodes we predicted would fail, how many actually did?

Recall = TP / (TP + FN)
  → Of the nodes that actually failed, how many did we predict?

Accuracy (F1) = 2 * (precision * recall) / (precision + recall)
  → Overall correctness (balanced between false positives and false negatives)
```

**Targets**:
- **Precision ≥ 0.85**: Minimize false alarms (false positives)
- **Recall ≥ 0.85**: Minimize surprises (false negatives)
- **Accuracy ≥ 0.9**: High-quality predictions

### Recommendations

The system automatically generates recommendations based on false negatives:
- **If we missed a node**: Suggests adding edges or adjusting propagation depth
- **If RTO was way off**: Suggests re-tuning timeout/retry settings
- **Pattern**: "X failed but we didn't predict it → increase blast radius tracing"

### Example: Post-Incident Analysis

**Incident**: Cache node crashed; took 35 min to detect and failover

**What we predicted**: Cache down → 12 nodes affected, RTO 40 min

**What actually happened**: Cache down → 10 nodes affected, RTO 35 min (better!)

**Results**:
- True Positives: 10 nodes
- False Positives: 2 nodes (we were pessimistic)
- False Negatives: 0 nodes (perfect recall!)
- Accuracy: 0.91 (excellent)

**Recommendation**: "Predictions are accurate; consider slightly reducing blast radius conservatism to avoid false positives."

---

## Workflow Examples

### Example 1: Prepare for Planned Maintenance

1. **Compliance**: Run audit to baseline the current state
2. **What-If**: Model taking primary-db offline and promoting replica
3. **Verify**: Blast radius reduces, RTO acceptable
4. **Execute**: Perform maintenance; Postmortem shows accuracy was high

### Example 2: Improve Chaos Test Process

1. **Chaos**: Create experiment simulating network partition
2. **Record**: Manually run test, note which nodes actually failed, RTO
3. **Postmortem**: Analyze accuracy, identify if model was too optimistic/pessimistic
4. **Tune**: Adjust edge weights or blast radius logic
5. **Repeat**: Next chaos test should be more accurate

### Example 3: Stakeholder Communication

1. **Compliance**: Run audit, export JSON
2. **What-If**: Model adding redundancy (second data center)
3. **Demonstrate**: Show blast radius reduced by 30%, RTO by 20 min
4. **Postmortem**: Share real incident analysis showing prediction accuracy
5. **Present**: "With these changes, we'd be in compliance and incidents resolve faster"

---

## FAQ

**Q: What if I add a virtual node but don't specify RTO?**
A: It inherits the RTO/RPO from the node type defaults (60 min RTO, 15 min RPO).

**Q: Can I run multiple experiments at the same time?**
A: Yes. Each experiment is independent. You can list them all and compare results.

**Q: Why is the resilience score so low even though RTO was good?**
A: The score blends RTO accuracy and node accuracy. If node prediction was far off, it drags down the overall score.

**Q: How often should we run compliance audits?**
A: Whenever topology changes. Integrate it into your CI/CD to run on every infrastructure commit.

**Q: What if a node has no RTO/RPO configured?**
A: It's marked "skipped" in compliance. Configure it in your topology to include in audits.

---

## See Also

- [Architecture Overview](./ARCHITECTURE.md)
- [API Reference](./API.md)
- [Simulation Mechanics](./SIMULATION.md)
