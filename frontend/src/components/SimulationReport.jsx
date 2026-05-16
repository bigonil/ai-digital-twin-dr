/**
 * SimulationReport.jsx
 * Post-simulation report with 5 sections:
 * 1. Executive Summary
 * 2. Impact Table
 * 3. Timeline of Events
 * 4. Root Cause Analysis
 * 5. Mitigation Actions + Architecture Recommendations
 */

import React, { useState, useMemo, memo } from 'react'
import { ChevronDown, Download } from 'lucide-react'
import PlaybookPanel from './PlaybookPanel.jsx'

function exportJSON(simulationResult) {
  const blob = new Blob([JSON.stringify(simulationResult, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `simulation_${simulationResult.origin_node_id}_${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function exportCSV(simulationResult) {
  const header = ['Hop', 'Node ID', 'Name', 'Type', 'RTO (min)', 'RPO (min)', 'Recovery Cost (USD)']
  const rows = (simulationResult.blast_radius || [])
    .sort((a, b) => a.distance - b.distance)
    .map(n => [
      n.distance, n.id, n.name, n.type,
      n.estimated_rto_minutes ?? '', n.estimated_rpo_minutes ?? '',
      n.recovery_cost_usd ?? '',
    ])
  const csv = [header, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `simulation_${simulationResult.origin_node_id}_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Derive root cause description from origin node type
 */
function deriveRootCause(originNode) {
  const type = originNode?.type || 'unknown'
  const failureDescriptions = {
    aws_db_instance: 'Database instance failure — primary data store became unavailable, triggering cascade across all dependent application tiers. Connections timed out and queries failed.',
    aws_rds_cluster: 'RDS cluster failure — Aurora cluster lost quorum, causing read replicas to disconnect and application connections to time out. Failover mechanisms engaged but not fast enough.',
    aws_lb: 'Load balancer failure — entry-point became unavailable, routing all traffic to a single backend or dropping requests entirely. Single point of failure in distribution layer.',
    aws_instance: 'Compute instance failure — EC2 instance terminated unexpectedly (likely due to health check or resource exhaustion), causing in-flight requests to fail and downstream services to lose their upstream.',
    aws_s3_bucket: 'Object storage failure — S3 bucket access was denied or throttled, blocking all artifact reads and application startup sequences. Configuration drift or IAM policy issue.',
    aws_sqs_queue: 'Message queue failure — SQS queue became inaccessible, halting all async message processing and causing producer backpressure. Dead letter queue overflow risk.',
    aws_elasticache_cluster: 'Cache cluster failure — Redis/Memcached nodes evicted or crashed, causing cache misses that cascaded to database. No fallback cache layer in place.',
    aws_eks_cluster: 'Kubernetes cluster failure — control plane or etcd became unavailable, preventing pod scheduling and updates. Node affinity and pod disruption budgets failed.',
    _default: `Infrastructure node of type "${type}" failed, propagating across dependent services in a cascading manner.`,
  }
  return failureDescriptions[type] || failureDescriptions._default
}

/**
 * Architecture recommendations by node type
 */
const ARCH_RECOMMENDATIONS = {
  aws_db_instance: [
    'Migrate to RDS Multi-AZ for automatic failover with RTO < 2 min',
    'Add read replicas in separate AZs to absorb read traffic during primary failure',
    'Implement connection pooling (PgBouncer/RDS Proxy) to reduce connection storm on restart',
    'Enable automated backups with 7-day retention for faster recovery',
  ],
  aws_rds_cluster: [
    'Enable Global Database for cross-region recovery with < 1s RPO',
    'Configure enhanced monitoring and Performance Insights for early anomaly detection',
    'Set up Aurora Auto Scaling for reader nodes to handle failover traffic',
    'Define custom RTO/RPO targets in Disaster Recovery runbook',
  ],
  aws_lb: [
    'Enable cross-zone load balancing to prevent AZ-level failure propagation',
    'Add AWS WAF and Shield Standard for DDoS protection at load balancer level',
    'Configure health check thresholds: interval 10s, unhealthy threshold 2 checks',
    'Implement connection draining timeout of 60s for graceful shutdown',
  ],
  aws_instance: [
    'Deploy in Auto Scaling Group with min=2 across 2 AZs for high availability',
    'Use spot instances only for stateless, interruption-tolerant workloads',
    'Implement graceful shutdown hooks (SIGTERM) to drain connections before termination',
    'Enable detailed CloudWatch monitoring for early warning signals',
  ],
  aws_s3_bucket: [
    'Enable Cross-Region Replication (CRR) for critical data buckets',
    'Set up S3 versioning with lifecycle policies for point-in-time recovery',
    'Configure bucket policies to prevent accidental deletions',
    'Monitor S3 metrics and set up CloudWatch alarms for unusual access patterns',
  ],
  _default: [
    'Apply N+1 redundancy across all critical path components',
    'Define and test RTO/RPO targets in Disaster Recovery runbook',
    'Run quarterly GameDay exercises to validate recovery procedures',
    'Implement comprehensive health checks and circuit breakers',
  ],
}

function getRecommendations(nodeType) {
  if (ARCH_RECOMMENDATIONS[nodeType]) return ARCH_RECOMMENDATIONS[nodeType]
  return ARCH_RECOMMENDATIONS._default
}

/**
 * Collapsible section component
 */
function ReportSection({ title, children, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="border-b border-dt-border">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-900/30 transition"
      >
        <h3 className="text-sm font-mono font-bold text-gray-100">{title}</h3>
        <ChevronDown
          size={16}
          className="text-gray-500 transition-transform"
          style={{ transform: isOpen ? 'rotate(0deg)' : 'rotate(-90deg)' }}
        />
      </button>
      {isOpen && <div className="px-4 py-3 bg-slate-900/20 text-xs">{children}</div>}
    </div>
  )
}

function SimulationReport({ simulationResult = null, topology = { nodes: [] } }) {
  if (!simulationResult) return null

  const originNode = useMemo(
    () => topology.nodes.find((n) => n.id === simulationResult.origin_node_id),
    [topology.nodes, simulationResult.origin_node_id]
  )

  const blastRadius = simulationResult.blast_radius || []
  const timelineSteps = simulationResult.timeline_steps || []
  const recoverySteps = simulationResult.recovery_steps || []

  const worstRto = simulationResult.worst_case_rto_minutes
  const worstRpo = simulationResult.worst_case_rpo_minutes
  const rootCause = deriveRootCause(originNode)
  const archRecs = getRecommendations(originNode?.type)

  // Build timeline events from timeline_steps
  const timelineEvents = useMemo(() =>
    timelineSteps.map((step) => ({
      timeMs: step.step_time_ms,
      nodeId: step.node_id,
      nodeName: step.node_name,
      distance: step.distance,
    })),
    [timelineSteps]
  )

  return (
    <div className="shrink-0 bg-dt-surface border-t border-dt-border overflow-y-auto max-h-64 flex flex-col">
      <div className="sticky top-0 bg-dt-bg border-b border-dt-border px-4 py-2 flex items-center justify-between">
        <h2 className="text-sm font-mono font-bold text-gray-100">SIMULATION REPORT</h2>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{blastRadius.length} nodes affected</span>
          {simulationResult.total_recovery_cost_usd != null && (
            <span className="text-yellow-400 font-mono">
              ~${simulationResult.total_recovery_cost_usd.toLocaleString()} recovery cost
            </span>
          )}
          <button
            onClick={() => exportJSON(simulationResult)}
            className="flex items-center gap-1 px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
            title="Export as JSON"
          >
            <Download size={12} /> JSON
          </button>
          <button
            onClick={() => exportCSV(simulationResult)}
            className="flex items-center gap-1 px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
            title="Export blast radius as CSV"
          >
            <Download size={12} /> CSV
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Section 1: Executive Summary */}
        <ReportSection title="EXECUTIVE SUMMARY" defaultOpen={true}>
          <div className="space-y-2 text-xs text-gray-300">
            <div>
              <span className="text-gray-500">Origin:</span>{' '}
              <span className="font-mono">{originNode?.name}</span> ({originNode?.type})
            </div>
            <div>
              <span className="text-gray-500">Total Affected:</span> {blastRadius.length} nodes
            </div>
            <div>
              <span className="text-gray-500">Max Propagation:</span> {simulationResult.max_distance} hops in{' '}
              {simulationResult.total_duration_ms / 1000}s
            </div>
            <div>
              <span className="text-gray-500">Worst RTO:</span>{' '}
              <span className="font-mono text-cyan-400">{worstRto || 'N/A'} min</span>
            </div>
            <div>
              <span className="text-gray-500">Worst RPO:</span>{' '}
              <span className="font-mono text-cyan-400">{worstRpo || 'N/A'} min</span>
            </div>
          </div>
        </ReportSection>

        {/* Section 2: Impact Table */}
        <ReportSection title="IMPACT TABLE" defaultOpen={true}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-dt-border">
                  <th className="text-left px-2 py-1 text-gray-500">Hop</th>
                  <th className="text-left px-2 py-1 text-gray-500">Node</th>
                  <th className="text-left px-2 py-1 text-gray-500">Type</th>
                  <th className="text-right px-2 py-1 text-gray-500">RTO</th>
                  <th className="text-right px-2 py-1 text-gray-500">RPO</th>
                </tr>
              </thead>
              <tbody>
                {blastRadius
                  .sort((a, b) => a.distance - b.distance)
                  .map((node) => (
                    <tr key={node.id} className="border-b border-dt-border hover:bg-slate-800/30">
                      <td className="px-2 py-1 font-mono text-gray-400">{node.distance}</td>
                      <td className="px-2 py-1 font-mono text-gray-300 truncate max-w-xs">
                        {node.name}
                      </td>
                      <td className="px-2 py-1 text-gray-400 text-xs">{node.type}</td>
                      <td className="text-right px-2 py-1 font-mono text-cyan-400">
                        {node.estimated_rto_minutes || 'N/A'}
                      </td>
                      <td className="text-right px-2 py-1 font-mono text-cyan-400">
                        {node.estimated_rpo_minutes || 'N/A'}
                      </td>
                      {node.recovery_cost_usd != null && (
                        <td className="text-right px-2 py-1 font-mono text-yellow-400">
                          ${node.recovery_cost_usd}
                        </td>
                      )}
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </ReportSection>

        {/* Section 3: Timeline of Events */}
        <ReportSection title="TIMELINE OF EVENTS" defaultOpen={false}>
          <div className="space-y-1 text-xs text-gray-300 font-mono">
            {timelineEvents.length > 0 ? (
              timelineEvents.map((event, idx) => (
                <div key={idx} className="flex gap-2">
                  <span className="text-gray-600">T+{event.timeMs}ms</span>
                  <span className="text-gray-500">●</span>
                  <span>
                    {event.nodeName} entered failure state (hop {event.distance})
                  </span>
                </div>
              ))
            ) : (
              <div className="text-gray-500">No timeline events recorded</div>
            )}
          </div>
        </ReportSection>

        {/* Section 4: Root Cause Analysis */}
        <ReportSection title="ROOT CAUSE ANALYSIS" defaultOpen={true}>
          <div className="text-xs text-gray-300 leading-relaxed">{rootCause}</div>
        </ReportSection>

        {/* Section 5: LLM Recovery Playbook */}
        {simulationResult.origin_node_id && (
          <ReportSection title="AI RECOVERY PLAYBOOK" defaultOpen={false}>
            <PlaybookPanel
              nodeId={simulationResult.origin_node_id}
              nodeName={originNode?.name || simulationResult.origin_node_id}
            />
          </ReportSection>
        )}

        {/* Section 6: Mitigation & Recommendations */}
        <ReportSection title="MITIGATION ACTIONS & RECOMMENDATIONS" defaultOpen={false}>
          <div className="space-y-3">
            {/* Recovery steps from API */}
            {recoverySteps.length > 0 && (
              <div>
                <h4 className="text-xs font-mono text-gray-400 mb-1.5">Recovery Steps (from API)</h4>
                <ol className="text-xs text-gray-300 space-y-1 list-decimal list-inside">
                  {recoverySteps.map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {/* Architecture recommendations */}
            <div>
              <h4 className="text-xs font-mono text-gray-400 mb-1.5">Architecture Recommendations</h4>
              <ul className="text-xs text-gray-300 space-y-1 list-disc list-inside">
                {archRecs.map((rec, idx) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>

            {/* Generic best practices */}
            <div>
              <h4 className="text-xs font-mono text-gray-400 mb-1.5">General Best Practices</h4>
              <ul className="text-xs text-gray-300 space-y-1 list-disc list-inside">
                <li>Implement comprehensive health checks on all services</li>
                <li>Set up circuit breakers to prevent cascade propagation</li>
                <li>Enable detailed logging for rapid troubleshooting</li>
                <li>Define clear runbooks for each failure scenario</li>
              </ul>
            </div>
          </div>
        </ReportSection>
      </div>
    </div>
  )
}

export default memo(SimulationReport)
