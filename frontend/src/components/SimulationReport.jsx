/**
 * SimulationReport.jsx — Full-screen modal report with 6 sections + left nav
 */
import React, { useState, useMemo, useRef, memo } from 'react'
import {
  X, Download, ChevronDown, FileJson, FileText,
  Zap, Network, Clock, Search, BookOpen, Shield,
  AlertTriangle, Activity, TrendingDown,
} from 'lucide-react'
import PlaybookPanel from './PlaybookPanel.jsx'

/* ── Exports ──────────────────────────────────────────────────── */
function exportJSON(sim) {
  const blob = new Blob([JSON.stringify(sim, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `simulation_${sim.origin_node_id}_${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function exportCSV(sim) {
  const header = ['Hop', 'Node ID', 'Name', 'Type', 'RTO (min)', 'RPO (min)', 'Recovery Cost (EUR)']
  const rows = (sim.blast_radius || [])
    .sort((a, b) => a.distance - b.distance)
    .map(n => [n.distance, n.id, n.name, n.type,
      n.estimated_rto_minutes ?? '', n.estimated_rpo_minutes ?? '', n.recovery_cost_usd ?? ''])
  const csv = [header, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `simulation_${sim.origin_node_id}_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/* ── Root cause ───────────────────────────────────────────────── */
function deriveRootCause(originNode) {
  const type = originNode?.type || 'unknown'
  const map = {
    aws_db_instance: 'Database instance failure — primary data store became unavailable, triggering cascade across all dependent application tiers. Connections timed out and queries failed.',
    aws_rds_cluster: 'RDS cluster failure — Aurora cluster lost quorum, causing read replicas to disconnect and application connections to time out. Failover mechanisms engaged but not fast enough.',
    aws_lb: 'Load balancer failure — entry-point became unavailable, routing all traffic to a single backend or dropping requests entirely. Single point of failure in distribution layer.',
    aws_instance: 'Compute instance failure — EC2 instance terminated unexpectedly (likely due to health check or resource exhaustion), causing in-flight requests to fail and downstream services to lose their upstream.',
    aws_s3_bucket: 'Object storage failure — S3 bucket access was denied or throttled, blocking all artifact reads and application startup sequences. Configuration drift or IAM policy issue.',
    aws_sqs_queue: 'Message queue failure — SQS queue became inaccessible, halting all async message processing and causing producer backpressure. Dead letter queue overflow risk.',
    aws_elasticache_cluster: 'Cache cluster failure — Redis/Memcached nodes evicted or crashed, causing cache misses that cascaded to database. No fallback cache layer in place.',
    aws_eks_cluster: 'Kubernetes cluster failure — control plane or etcd became unavailable, preventing pod scheduling and updates. Node affinity and pod disruption budgets failed.',
  }
  return map[type] || `Infrastructure node of type "${type}" failed, propagating across dependent services in a cascading manner.`
}

/* ── Architecture recommendations ────────────────────────────── */
const ARCH_RECS = {
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
function getRecommendations(type) {
  return ARCH_RECS[type] || ARCH_RECS._default
}

/* ── Left nav sections ────────────────────────────────────────── */
const SECTIONS = [
  { id: 'executive',  label: 'Executive Summary',           Icon: Zap       },
  { id: 'impact',     label: 'Impact Table',                Icon: Network   },
  { id: 'timeline',   label: 'Timeline of Events',          Icon: Clock     },
  { id: 'rootcause',  label: 'Root Cause Analysis',         Icon: Search    },
  { id: 'playbook',   label: 'AI Recovery Playbook',        Icon: BookOpen  },
  { id: 'mitigation', label: 'Mitigation & Recommendations',Icon: Shield    },
]

/* ── Stat card ────────────────────────────────────────────────── */
function StatCard({ label, value, sub, color = 'text-gray-100' }) {
  return (
    <div className="bg-dt-bg border border-dt-border rounded-lg px-4 py-3">
      <div className="text-xs text-gray-500 mb-1 font-mono">{label}</div>
      <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}

/* ── Section wrapper ──────────────────────────────────────────── */
function Section({ id, Icon, title, badge, children, sectionRef }) {
  const [open, setOpen] = useState(true)
  return (
    <div id={id} ref={sectionRef} className="bg-dt-surface border border-dt-border rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-white/5 transition text-left"
      >
        <Icon size={16} className="text-dt-accent flex-shrink-0" />
        <span className="font-mono font-bold text-sm text-gray-100 flex-1">{title}</span>
        {badge && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-dt-accent/20 text-dt-accent font-mono">{badge}</span>
        )}
        <ChevronDown
          size={15}
          className="text-gray-500 transition-transform"
          style={{ transform: open ? 'rotate(0deg)' : 'rotate(-90deg)' }}
        />
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  )
}

/* ── Main component ───────────────────────────────────────────── */
function SimulationReport({ simulationResult = null, topology = { nodes: [] }, onClose }) {
  if (!simulationResult) return null

  const [activeSection, setActiveSection] = useState('executive')

  const sectionRefs = useRef({})
  const contentRef = useRef(null)

  const originNode = useMemo(
    () => topology.nodes?.find(n => n.id === simulationResult.origin_node_id),
    [topology.nodes, simulationResult.origin_node_id]
  )

  const blastRadius   = useMemo(() => simulationResult.blast_radius || [], [simulationResult])
  const timelineSteps = useMemo(() => simulationResult.timeline_steps || [], [simulationResult])
  const recoverySteps = simulationResult.recovery_steps || []
  const worstRto      = simulationResult.worst_case_rto_minutes
  const worstRpo      = simulationResult.worst_case_rpo_minutes
  const rootCause     = deriveRootCause(originNode)
  const archRecs      = getRecommendations(originNode?.type)

  const sortedBlast = useMemo(
    () => [...blastRadius].sort((a, b) => a.distance - b.distance),
    [blastRadius]
  )

  const timelineEvents = useMemo(() =>
    timelineSteps.map(s => ({ timeMs: s.step_time_ms, nodeId: s.node_id, nodeName: s.node_name, distance: s.distance })),
    [timelineSteps]
  )

  function scrollTo(id) {
    setActiveSection(id)
    sectionRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-dt-bg" role="dialog" aria-modal="true">

      {/* ── Modal header ── */}
      <div className="shrink-0 flex items-center justify-between px-6 py-3 bg-dt-surface border-b border-dt-border">
        <div className="flex items-center gap-3">
          <span className="text-xl">🔮</span>
          <div>
            <div className="font-mono font-bold text-sm text-gray-100 tracking-widest">SIMULATION REPORT</div>
            <div className="text-xs text-gray-500 font-mono mt-0.5">
              {originNode?.name || simulationResult.origin_node_id}
              {originNode?.type && <span className="ml-2 text-gray-600">· {originNode.type}</span>}
              {originNode?.region && <span className="ml-2 text-gray-600">· {originNode.region}</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {simulationResult.total_recovery_cost_usd != null && (
            <span className="text-xs font-mono text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 px-2 py-1 rounded">
              ~€{Math.round(simulationResult.total_recovery_cost_usd).toLocaleString()} recovery cost
            </span>
          )}
          <span className="text-xs font-mono text-gray-500 bg-dt-bg border border-dt-border px-2 py-1 rounded">
            {blastRadius.length} nodes affected
          </span>
          <button
            onClick={() => exportJSON(simulationResult)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
            title="Export as JSON"
          >
            <FileJson size={13} /> JSON
          </button>
          <button
            onClick={() => exportCSV(simulationResult)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
            title="Export blast radius as CSV"
          >
            <FileText size={13} /> CSV
          </button>
          <button
            onClick={onClose}
            className="p-2 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition ml-1"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* ── Body: nav + scrollable content ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left nav */}
        <nav className="w-52 shrink-0 border-r border-dt-border overflow-y-auto py-4 px-3 space-y-1">
          <div className="text-xs text-gray-600 font-mono px-2 mb-3 uppercase tracking-widest">Sections</div>
          {SECTIONS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => scrollTo(id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded text-left text-xs font-mono transition ${
                activeSection === id
                  ? 'bg-dt-accent/20 text-dt-accent'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}

          {/* Quick stats in nav */}
          <div className="pt-4 border-t border-dt-border mt-4 space-y-2 px-2">
            <div className="text-xs text-gray-600 font-mono uppercase tracking-widest mb-2">Quick Stats</div>
            <div className="text-xs text-gray-500">
              <span className="text-gray-400">RTO worst:</span>
              <span className="font-mono text-cyan-400 ml-1">{worstRto ?? '—'} min</span>
            </div>
            <div className="text-xs text-gray-500">
              <span className="text-gray-400">RPO worst:</span>
              <span className="font-mono text-cyan-400 ml-1">{worstRpo ?? '—'} min</span>
            </div>
            <div className="text-xs text-gray-500">
              <span className="text-gray-400">Max hops:</span>
              <span className="font-mono text-gray-300 ml-1">{simulationResult.max_distance}</span>
            </div>
            <div className="text-xs text-gray-500">
              <span className="text-gray-400">Duration:</span>
              <span className="font-mono text-gray-300 ml-1">{simulationResult.total_duration_ms} ms</span>
            </div>
          </div>
        </nav>

        {/* Scrollable content */}
        <div ref={contentRef} className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* ── 1. Executive Summary ── */}
          <Section
            id="executive" Icon={Zap} title="EXECUTIVE SUMMARY"
            badge={`${blastRadius.length} nodes`}
            sectionRef={el => sectionRefs.current['executive'] = el}
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-4">
              <StatCard label="Origin Node"    value={originNode?.name || simulationResult.origin_node_id} sub={originNode?.type} />
              <StatCard label="Affected Nodes" value={blastRadius.length}    sub="in blast radius" color="text-dt-danger" />
              <StatCard label="Max Propagation" value={`${simulationResult.max_distance} hops`} sub={`in ${simulationResult.total_duration_ms / 1000}s`} />
              <StatCard label="Sim Duration"   value={`${simulationResult.total_duration_ms} ms`} />
              <StatCard label="Worst RTO"      value={worstRto != null ? `${worstRto} min` : 'N/A'} sub="recovery time objective" color="text-cyan-400" />
              <StatCard label="Worst RPO"      value={worstRpo != null ? `${worstRpo} min` : 'N/A'} sub="recovery point objective" color="text-cyan-400" />
              {simulationResult.total_recovery_cost_usd != null && (
                <StatCard label="Total Recovery Cost" value={`€${Math.round(simulationResult.total_recovery_cost_usd).toLocaleString()}`} sub="estimated" color="text-yellow-400" />
              )}
              <StatCard label="Strategy" value={originNode?.recovery_strategy || '—'} />
            </div>
          </Section>

          {/* ── 2. Impact Table ── */}
          <Section
            id="impact" Icon={Network} title="IMPACT TABLE"
            badge={`${blastRadius.length} nodes`}
            sectionRef={el => sectionRefs.current['impact'] = el}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-dt-border">
                    <th className="text-left px-3 py-2 text-gray-500 font-mono">Hop</th>
                    <th className="text-left px-3 py-2 text-gray-500 font-mono">Node</th>
                    <th className="text-left px-3 py-2 text-gray-500 font-mono">Type</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-mono">RTO</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-mono">RPO</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-mono">Cost (€)</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedBlast.map(node => (
                    <tr key={node.id} className="border-b border-dt-border/50 hover:bg-slate-800/30">
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-dt-accent/20 text-dt-accent font-mono text-xs font-bold">
                          {node.distance}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-gray-200">{node.name}</td>
                      <td className="px-3 py-2 text-gray-500">{node.type}</td>
                      <td className="px-3 py-2 text-right font-mono text-cyan-400">
                        {node.estimated_rto_minutes != null ? `${node.estimated_rto_minutes} min` : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-cyan-400">
                        {node.estimated_rpo_minutes != null ? `${node.estimated_rpo_minutes} min` : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-yellow-400">
                        {node.recovery_cost_usd != null ? `€${node.recovery_cost_usd}` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {/* ── 3. Timeline of Events ── */}
          <Section
            id="timeline" Icon={Clock} title="TIMELINE OF EVENTS"
            badge={`${timelineEvents.length} events`}
            sectionRef={el => sectionRefs.current['timeline'] = el}
          >
            {timelineEvents.length > 0 ? (
              <div className="relative pl-6">
                {/* vertical line */}
                <div className="absolute left-2 top-1 bottom-1 w-px bg-dt-border" />
                <div className="space-y-3">
                  {timelineEvents.map((ev, idx) => (
                    <div key={idx} className="relative flex items-start gap-3">
                      <div className="absolute -left-4 mt-0.5 w-2.5 h-2.5 rounded-full bg-dt-accent border-2 border-dt-bg" />
                      <div className="flex-shrink-0 font-mono text-xs text-gray-600 w-20 pt-0.5">
                        T+{ev.timeMs} ms
                      </div>
                      <div>
                        <span className="font-mono text-xs text-gray-200">{ev.nodeName}</span>
                        <span className="text-xs text-gray-500 ml-2">entered failure state</span>
                        <span className="text-xs text-gray-600 ml-2">· hop {ev.distance}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500 italic">No timeline events recorded.</p>
            )}
          </Section>

          {/* ── 4. Root Cause Analysis ── */}
          <Section
            id="rootcause" Icon={Search} title="ROOT CAUSE ANALYSIS"
            sectionRef={el => sectionRefs.current['rootcause'] = el}
          >
            <div className="flex gap-3 bg-red-950/20 border border-red-900/30 rounded-lg p-4">
              <AlertTriangle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-mono text-red-400 mb-1.5">Failure origin: {originNode?.type}</div>
                <p className="text-sm text-gray-300 leading-relaxed">{rootCause}</p>
              </div>
            </div>
            {originNode?.region && (
              <div className="mt-3 flex gap-6 text-xs text-gray-500 font-mono">
                <span>Region: <span className="text-gray-300">{originNode.region}</span></span>
                {originNode?.recovery_strategy && (
                  <span>Strategy: <span className="text-gray-300">{originNode.recovery_strategy}</span></span>
                )}
              </div>
            )}
          </Section>

          {/* ── 5. AI Recovery Playbook ── */}
          {simulationResult.origin_node_id && (
            <Section
              id="playbook" Icon={BookOpen} title="AI RECOVERY PLAYBOOK"
              badge="Claude AI"
              sectionRef={el => sectionRefs.current['playbook'] = el}
            >
              <PlaybookPanel
                nodeId={simulationResult.origin_node_id}
                nodeName={originNode?.name || simulationResult.origin_node_id}
              />
            </Section>
          )}

          {/* ── 6. Mitigation & Recommendations ── */}
          <Section
            id="mitigation" Icon={Shield} title="MITIGATION ACTIONS & RECOMMENDATIONS"
            sectionRef={el => sectionRefs.current['mitigation'] = el}
          >
            <div className="space-y-5">
              {/* Recovery steps from API */}
              {recoverySteps.length > 0 && (
                <div>
                  <h4 className="text-xs font-mono text-gray-400 uppercase tracking-wide mb-2 flex items-center gap-2">
                    <Activity size={12} /> Recovery Steps (from API)
                  </h4>
                  <ol className="space-y-1.5 list-none">
                    {recoverySteps.map((step, idx) => (
                      <li key={idx} className="flex gap-2 text-xs text-gray-300">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-dt-accent/20 text-dt-accent text-xs flex items-center justify-center font-mono">
                          {idx + 1}
                        </span>
                        <span className="leading-relaxed pt-0.5">{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Architecture recommendations */}
              <div>
                <h4 className="text-xs font-mono text-gray-400 uppercase tracking-wide mb-2 flex items-center gap-2">
                  <TrendingDown size={12} /> Architecture Recommendations
                </h4>
                <ul className="space-y-2">
                  {archRecs.map((rec, idx) => (
                    <li key={idx} className="flex gap-2 text-xs text-gray-300">
                      <span className="text-dt-accent flex-shrink-0 mt-0.5">›</span>
                      <span className="leading-relaxed">{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* General best practices */}
              <div className="border-t border-dt-border pt-4">
                <h4 className="text-xs font-mono text-gray-400 uppercase tracking-wide mb-2 flex items-center gap-2">
                  <Shield size={12} /> General Best Practices
                </h4>
                <ul className="space-y-2">
                  {[
                    'Implement comprehensive health checks on all services',
                    'Set up circuit breakers to prevent cascade propagation',
                    'Enable detailed logging and distributed tracing for rapid troubleshooting',
                    'Define clear runbooks for each failure scenario',
                    'Run quarterly GameDay exercises to validate recovery procedures',
                    'Monitor blast radius size trends over time to catch architecture regressions',
                  ].map((bp, idx) => (
                    <li key={idx} className="flex gap-2 text-xs text-gray-300">
                      <span className="text-green-500 flex-shrink-0 mt-0.5">✓</span>
                      <span className="leading-relaxed">{bp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Section>

          <div className="h-8" /> {/* bottom spacer */}
        </div>
      </div>
    </div>
  )
}

export default memo(SimulationReport)
