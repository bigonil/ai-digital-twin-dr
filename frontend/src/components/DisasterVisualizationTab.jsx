import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

const STATUS_COLOR = {
  healthy: '#10b981',
  degraded: '#f59e0b',
  failed: '#ef4444',
  simulated_failure: '#dc2626',
  unknown: '#6b7280',
}

function calculateLayout(blastRadius, topology) {
  if (!topology?.nodes || !blastRadius?.length) return { nodes: [], edges: [] }

  const positions = {}
  const centerX = 400
  const centerY = 300

  // Group nodes by distance
  const byDistance = {}
  blastRadius.forEach(br => {
    if (!byDistance[br.distance]) byDistance[br.distance] = []
    byDistance[br.distance].push(br)
  })

  // Layout: concentric circles by distance
  Object.entries(byDistance).forEach(([distance, nodes]) => {
    const dist = parseInt(distance)
    const radius = 80 + dist * 70
    const angleStep = (2 * Math.PI) / Math.max(nodes.length, 1)

    nodes.forEach((node, i) => {
      const angle = i * angleStep
      positions[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        ...node,
      }
    })
  })

  // Find edges between blast nodes
  const blastIds = new Set(blastRadius.map(b => b.id))
  const edges = (topology.edges || []).filter(e =>
    blastIds.has(e.source) && blastIds.has(e.target)
  )

  return { nodes: Object.values(positions), edges }
}

export default function DisasterVisualizationTab({
  blastRadius,
  topology,
  simulationTime,
  onClose,
}) {
  const { nodes, edges } = calculateLayout(blastRadius, topology)
  const [activatingNodes, setActivatingNodes] = useState(new Set())

  // Sync activating nodes with simulation time
  useEffect(() => {
    if (simulationTime === null) return

    const now = new Set()
    nodes.forEach(node => {
      if (node.step_time_ms !== undefined &&
          simulationTime >= node.step_time_ms &&
          simulationTime < node.step_time_ms + 800) {
        now.add(node.id)
      }
    })
    setActivatingNodes(now)
  }, [simulationTime, nodes])

  const getNodeFill = (node) => {
    if (activatingNodes.has(node.id)) return '#ff6b6b'
    if (node.step_time_ms !== undefined && simulationTime >= node.step_time_ms) {
      return '#dc2626'
    }
    return STATUS_COLOR[node.status] ?? '#6b7280'
  }

  return (
    <div className="fixed inset-0 bg-black/95 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-8 py-4 border-b border-dt-border bg-dt-surface/50">
        <div>
          <h2 className="text-lg font-bold text-dt-accent font-mono tracking-wider">
            Disaster Propagation Visualization
          </h2>
          <p className="text-xs text-gray-500 font-mono mt-1">
            {nodes.length} nodes affected • Max distance: {Math.max(...blastRadius.map(b => b.distance), 0)} hops
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-dt-bg rounded transition-colors text-gray-400 hover:text-gray-200"
        >
          <X size={20} />
        </button>
      </div>

      {/* Visualization Area */}
      <div className="flex-1 overflow-hidden relative bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 flex items-center justify-center">
        {nodes.length > 0 ? (
          <svg className="w-full h-full" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid meet">
            <defs>
              {/* Gradient backgrounds */}
              <radialGradient id="glowGradient">
                <stop offset="0%" stopColor="#ff6b6b" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#ff6b6b" stopOpacity="0" />
              </radialGradient>

              {/* Animation definitions */}
              <style>{`
                @keyframes pulse-glow {
                  0%, 100% { r: 16; filter: drop-shadow(0 0 8px #ff6b6b) drop-shadow(0 0 16px rgba(255, 107, 107, 0.5)); }
                  50% { r: 22; filter: drop-shadow(0 0 16px #ff6b6b) drop-shadow(0 0 32px rgba(255, 107, 107, 0.8)); }
                }
                @keyframes pulse-healthy {
                  0%, 100% { filter: drop-shadow(0 0 4px rgba(16, 185, 129, 0.3)); }
                  50% { filter: drop-shadow(0 0 12px rgba(16, 185, 129, 0.6)); }
                }
                @keyframes pulse-failed {
                  0%, 100% { filter: drop-shadow(0 0 4px rgba(220, 38, 38, 0.3)); }
                  50% { filter: drop-shadow(0 0 12px rgba(220, 38, 38, 0.6)); }
                }
                .node-activating { animation: pulse-glow 0.8s ease-in-out; }
                .node-healthy { animation: pulse-healthy 2s ease-in-out infinite; }
                .node-failed { animation: pulse-failed 1.5s ease-in-out infinite; }
                @keyframes flow-animation {
                  0% { stroke-dashoffset: 20; opacity: 0; }
                  50% { opacity: 1; }
                  100% { stroke-dashoffset: -20; opacity: 0; }
                }
                .edge-flow { stroke-dasharray: 10, 10; animation: flow-animation 1.5s linear infinite; }
              `}</style>

              {/* Gradients for edges */}
              {edges.map((_, i) => (
                <linearGradient key={`edgeGrad-${i}`} id={`edgeGrad${i}`}>
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity="0" />
                  <stop offset="50%" stopColor="#3b82f6" stopOpacity="1" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                </linearGradient>
              ))}
            </defs>

            {/* Grid background */}
            <pattern id="gridPattern" width="50" height="50" patternUnits="userSpaceOnUse">
              <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#374151" strokeWidth="0.5" opacity="0.3" />
            </pattern>
            <rect width="800" height="600" fill="url(#gridPattern)" />

            {/* Center point */}
            <circle cx="400" cy="300" r="6" fill="#6366f1" opacity="0.4" />
            <circle cx="400" cy="300" r="3" fill="#6366f1" />

            {/* Concentric distance rings */}
            {[1, 2, 3, 4, 5].map(i => (
              <circle
                key={`ring-${i}`}
                cx="400"
                cy="300"
                r={80 + i * 70}
                fill="none"
                stroke="#4b5563"
                strokeWidth="0.5"
                strokeDasharray="5,5"
                opacity="0.2"
              />
            ))}

            {/* Distance labels */}
            {[1, 2, 3, 4, 5].map(i => (
              <text
                key={`label-${i}`}
                x="410"
                y={300 - (80 + i * 70)}
                fontSize="10"
                fill="#6b7280"
                opacity="0.6"
              >
                Hop {i}
              </text>
            ))}

            {/* Edges with flow animation */}
            {edges.map((edge, i) => {
              const source = nodes.find(n => n.id === edge.source)
              const target = nodes.find(n => n.id === edge.target)
              if (!source || !target) return null
              return (
                <line
                  key={`edge-${i}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={`url(#edgeGrad${i})`}
                  strokeWidth="2"
                  className="edge-flow"
                />
              )
            })}

            {/* Nodes */}
            {nodes.map(node => {
              const isActivating = activatingNodes.has(node.id)
              const isFailed = node.step_time_ms !== undefined && simulationTime >= node.step_time_ms
              const isHealthy = node.status === 'healthy'

              return (
                <g key={node.id}>
                  {/* Outer glow for activating nodes */}
                  {isActivating && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r="16"
                      fill="url(#glowGradient)"
                      opacity="0.6"
                    />
                  )}

                  {/* Node circle */}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r="12"
                    fill={getNodeFill(node)}
                    stroke="#1f2937"
                    strokeWidth="2"
                    className={
                      isActivating
                        ? 'node-activating'
                        : isFailed
                        ? 'node-failed'
                        : isHealthy
                        ? 'node-healthy'
                        : ''
                    }
                  />

                  {/* Inner label */}
                  <text
                    x={node.x}
                    y={node.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize="7"
                    fontWeight="bold"
                    fill={isActivating || isFailed ? '#fff' : '#000'}
                    className="pointer-events-none select-none"
                  >
                    {node.distance}
                  </text>

                  {/* Tooltip */}
                  <title>
                    {node.name} • Hop {node.distance} • {node.status}
                    {node.estimated_rto_minutes ? ` • RTO: ${node.estimated_rto_minutes}m` : ''}
                  </title>
                </g>
              )
            })}
          </svg>
        ) : (
          <div className="text-center text-gray-500 font-mono">
            <p className="text-lg">No propagation data</p>
            <p className="text-xs text-gray-600 mt-2">Run a simulation to visualize the disaster</p>
          </div>
        )}
      </div>

      {/* Legend Footer */}
      <div className="px-8 py-4 border-t border-dt-border bg-dt-surface/50 grid grid-cols-4 gap-6">
        {[
          { color: '#10b981', label: 'Healthy', desc: 'Normal operation' },
          { color: '#f59e0b', label: 'Degraded', desc: 'Performance degraded' },
          { color: '#dc2626', label: 'Failed', desc: 'Node failed' },
          { color: '#ff6b6b', label: 'Activating', desc: 'Currently failing' },
        ].map(item => (
          <div key={item.label} className="flex items-center gap-2">
            <div
              className="w-4 h-4 rounded-full border-2 border-gray-700"
              style={{ backgroundColor: item.color }}
            />
            <div>
              <p className="text-xs font-mono font-bold text-gray-200">{item.label}</p>
              <p className="text-xs text-gray-600">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
