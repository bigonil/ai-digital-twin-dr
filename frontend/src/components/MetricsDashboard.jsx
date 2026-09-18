/**
 * MetricsDashboard.jsx
 * Right-side panel showing per-node metrics with sparklines and status indicators.
 *
 * Features:
 * - CPU/Memory bars with sparkline graphs
 * - 8+ observability metrics (request rate, error rate, latency, throughput, etc.)
 * - RTO/RPO display
 * - Seeded deterministic mock data via useNodeMetrics hook
 * - Idle state message when no node selected
 */

import React from 'react'
import useNodeMetrics from '../hooks/useNodeMetrics'

/**
 * Sparkline component — renders 12-point history as SVG polyline
 */
function Sparkline({ data, color = '#3b82f6', height = 24, width = 100 }) {
  if (!data || data.length === 0) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - ((v - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * BarGauge component — horizontal bar with color-coded fill
 */
function BarGauge({ value = 0, max = 100, label = '' }) {
  const pct = Math.min(100, (value / max) * 100)
  const barColor = pct > 85 ? '#ef4444' : pct > 65 ? '#f59e0b' : '#10b981'

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-700 rounded overflow-hidden">
        <div
          className="h-full rounded transition-all"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
      <span className="text-xs font-mono w-12 text-right" style={{ color: barColor }}>
        {value.toFixed(1)}%
      </span>
    </div>
  )
}

/**
 * MetricValue component — single metric row with icon and value
 */
function MetricValue({ label, value, unit = '', color = '#94a3b8' }) {
  return (
    <div className="flex justify-between items-center py-1">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs font-mono" style={{ color }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
        {unit && <span className="text-gray-600 ml-1">{unit}</span>}
      </span>
    </div>
  )
}

export default function MetricsDashboard({ selectedNode = null, topology = { nodes: [] } }) {
  const metrics = useNodeMetrics(selectedNode)

  return (
    <aside className="flex flex-col h-full bg-dt-surface border-l border-dt-border overflow-hidden">
      {selectedNode ? (
        <>
          {/* Header */}
          <div className="shrink-0 border-b border-dt-border p-3">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <div className="truncate">
                <div className="text-xs font-mono font-bold text-gray-100 truncate">
                  {selectedNode.name}
                </div>
                <div className="text-xs text-gray-500 truncate">
                  {selectedNode.type}
                </div>
              </div>
            </div>
            <div className="text-xs text-gray-600 space-y-0.5">
              <div>Region: {selectedNode.region || 'N/A'}</div>
              <div>AZ: {selectedNode.az || 'N/A'}</div>
            </div>
          </div>

          {/* Scrollable metrics section */}
          <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs">
            {/* CPU Section */}
            {metrics && (
              <>
                <div>
                  <div className="text-gray-400 font-mono mb-1.5">CPU</div>
                  <BarGauge value={metrics.cpu} max={100} />
                  {metrics.cpuHistory && (
                    <div className="mt-1">
                      <Sparkline data={metrics.cpuHistory} color="#3b82f6" height={20} width={100} />
                    </div>
                  )}
                </div>

                {/* Memory Section */}
                <div>
                  <div className="text-gray-400 font-mono mb-1.5">Memory</div>
                  <BarGauge value={metrics.memory} max={100} />
                  {metrics.memHistory && (
                    <div className="mt-1">
                      <Sparkline data={metrics.memHistory} color="#8b5cf6" height={20} width={100} />
                    </div>
                  )}
                </div>

                {/* Divider */}
                <div className="border-t border-dt-border pt-3" />

                {/* Request metrics */}
                <div className="space-y-1.5">
                  <MetricValue label="Request Rate" value={metrics.requestRate} unit="req/s" />
                  <MetricValue label="Error Rate" value={metrics.errorRate} unit="%" color="#ef4444" />
                </div>

                {/* Latency metrics */}
                <div className="space-y-1.5">
                  <div className="text-gray-400 font-mono mb-1">Latency</div>
                  <MetricValue label="  p50" value={metrics.latencyP50} unit="ms" />
                  <MetricValue label="  p95" value={metrics.latencyP95} unit="ms" color="#f59e0b" />
                  <MetricValue label="  p99" value={metrics.latencyP99} unit="ms" color="#ef4444" />
                  {metrics.latHistory && (
                    <div className="mt-2">
                      <Sparkline data={metrics.latHistory} color="#f59e0b" height={20} width={100} />
                    </div>
                  )}
                </div>

                {/* Resource metrics */}
                <div className="space-y-1.5">
                  <MetricValue label="Throughput" value={metrics.throughput} unit="MB/s" />
                  <MetricValue label="Disk I/O" value={metrics.diskIo} unit="MB/s" />
                  {metrics.replicationLag !== null && (
                    <MetricValue
                      label="Replication Lag"
                      value={metrics.replicationLag}
                      unit="s"
                      color={metrics.replicationLag > 5 ? '#f59e0b' : '#10b981'}
                    />
                  )}
                </div>

                {/* Divider */}
                <div className="border-t border-dt-border pt-3" />

                {/* RTO/RPO */}
                <div className="space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-gray-400">RTO</span>
                    <span className="font-mono text-cyan-400">
                      {selectedNode.rto_minutes || 'N/A'}
                      {selectedNode.rto_minutes && <span className="text-gray-600"> min</span>}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">RPO</span>
                    <span className="font-mono text-cyan-400">
                      {selectedNode.rpo_minutes || 'N/A'}
                      {selectedNode.rpo_minutes && <span className="text-gray-600"> min</span>}
                    </span>
                  </div>
                </div>

                {/* Redundancy */}
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Redundant</span>
                  <span className="font-mono">
                    {selectedNode.is_redundant ? (
                      <span className="text-green-400">Yes</span>
                    ) : (
                      <span className="text-gray-500">No</span>
                    )}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Footer notes */}
          <div className="shrink-0 border-t border-dt-border px-3 py-2 bg-slate-900/30">
            <div className="text-xs text-gray-600">Live metrics updated every 10s</div>
          </div>
        </>
      ) : (
        /* Idle state */
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-500 px-4">
            <div className="text-sm font-mono mb-2">Select a node</div>
            <div className="text-xs">to view observability metrics</div>
          </div>
        </div>
      )}
    </aside>
  )
}
