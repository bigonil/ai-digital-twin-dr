import { useMemo } from 'react'

const STATUS_COLOR = {
  healthy: '#10b981',
  degraded: '#f59e0b',
  failed: '#ef4444',
  simulated_failure: '#dc2626',
  unknown: '#6b7280',
}

function calculateLayout(blastRadius, topology) {
  if (!topology?.nodes) return { nodes: [], edges: [] }

  const positions = {}
  const centerX = 300
  const centerY = 250

  // Group nodes by distance
  const byDistance = {}
  blastRadius.forEach(br => {
    if (!byDistance[br.distance]) byDistance[br.distance] = []
    byDistance[br.distance].push(br)
  })

  // Layout: concentric circles by distance
  Object.entries(byDistance).forEach(([distance, nodes]) => {
    const dist = parseInt(distance)
    const radius = 60 + dist * 50
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

  // Find edges that connect blast nodes
  const blastIds = new Set(blastRadius.map(b => b.id))
  const edges = (topology.edges || []).filter(e =>
    blastIds.has(e.source) && blastIds.has(e.target)
  )

  return {
    nodes: Object.values(positions),
    edges,
  }
}

export default function DisasterVisualization({
  blastRadius,
  topology,
  simulationTime,
}) {
  const { nodes, edges } = useMemo(
    () => calculateLayout(blastRadius, topology),
    [blastRadius, topology]
  )

  const getNodeFill = (node) => {
    // If timeline is playing, highlight nodes currently failing
    if (node.step_time_ms !== undefined && simulationTime !== null) {
      if (simulationTime >= node.step_time_ms && simulationTime < (node.step_time_ms + 500)) {
        return '#ff6b6b' // bright red while activating
      }
      if (simulationTime >= node.step_time_ms) {
        return '#dc2626' // failed
      }
    }
    return STATUS_COLOR[node.status] ?? '#6b7280'
  }

  const viewBox = `0 0 600 500`

  return (
    <div className="w-full h-full bg-dt-bg flex items-center justify-center p-4">
      <svg viewBox={viewBox} className="w-full max-w-2xl aspect-video bg-dt-surface rounded border border-dt-border">
        {/* Grid background */}
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#374151" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="600" height="500" fill="url(#grid)" />

        {/* Center marker */}
        <circle cx="300" cy="250" r="4" fill="#6366f1" opacity="0.5" />

        {/* Edges */}
        <g stroke="#4b5563" strokeWidth="1" opacity="0.6">
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
              />
            )
          })}
        </g>

        {/* Nodes */}
        {nodes.map(node => (
          <g key={node.id}>
            {/* Glow effect for activating nodes */}
            {node.step_time_ms !== undefined &&
              simulationTime !== null &&
              simulationTime >= node.step_time_ms &&
              simulationTime < node.step_time_ms + 500 && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r="20"
                  fill="none"
                  stroke="#ff6b6b"
                  strokeWidth="2"
                  opacity="0.3"
                  className="animate-pulse"
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
              className="transition-all"
            />

            {/* Distance label */}
            <text
              x={node.x}
              y={node.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize="8"
              fontWeight="bold"
              fill="#000"
              className="pointer-events-none"
            >
              {node.distance}
            </text>

            {/* Tooltip on hover */}
            <g className="group">
              <rect
                x={node.x - 8}
                y={node.y - 8}
                width="16"
                height="16"
                fill="transparent"
                className="hover:fill-white/5 cursor-help"
              />
              <title>{node.name} (Distance: {node.distance})</title>
            </g>
          </g>
        ))}

        {/* Legend */}
        <g transform="translate(10, 10)">
          <text x="0" y="0" fontSize="10" fontWeight="bold" fill="#9ca3af">
            Legend
          </text>
          {[
            { color: '#10b981', label: 'Healthy' },
            { color: '#f59e0b', label: 'Degraded' },
            { color: '#dc2626', label: 'Failed' },
            { color: '#ff6b6b', label: 'Activating' },
          ].map((item, i) => (
            <g key={i} transform={`translate(0, ${(i + 1) * 12})`}>
              <circle cx="4" cy="0" r="2" fill={item.color} />
              <text x="10" y="3" fontSize="8" fill="#d1d5db">
                {item.label}
              </text>
            </g>
          ))}
        </g>

        {/* Title */}
        <text
          x="300"
          y="20"
          textAnchor="middle"
          fontSize="12"
          fontWeight="bold"
          fill="#d1d5db"
        >
          Disaster Propagation Map
        </text>

        {/* Node count */}
        <text
          x="300"
          y="480"
          textAnchor="middle"
          fontSize="9"
          fill="#6b7280"
        >
          {nodes.length} nodes affected across {Math.max(...blastRadius.map(b => b.distance), 0)} hops
        </text>
      </svg>
    </div>
  )
}
