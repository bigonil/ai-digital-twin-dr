/**
 * InfrastructureMap.jsx
 * Unified 2D visualization showing all topology nodes + blast propagation animation.
 *
 * Features:
 * - Tiered layout for all infrastructure nodes
 * - Blast radius highlighting with animated propagation
 * - WoW animations: pulse-glow, edge-flow, hop-rings
 * - Real-time synchronization with simulationTime prop
 * - Node selection and hover tooltips
 */

import React, { useMemo } from 'react'
import { computeLayout, getEdgePath, getBezierPath } from '../utils/mapLayout'

const TYPE_ICONS = {
  aws_lb: '🔀',
  aws_elb: '🔀',
  aws_alb: '🔀',
  aws_nlb: '🔀',
  aws_instance: '⚙️',
  aws_autoscaling_group: '📦',
  aws_lambda: 'ƛ',
  aws_ecs_service: '🐳',
  aws_eks_cluster: '⛵',
  aws_db_instance: '🗄️',
  aws_rds_cluster: '🗄️',
  aws_dynamodb_table: '🗄️',
  aws_elasticache_cluster: '⚡',
  aws_sqs_queue: '📬',
  aws_kinesis_stream: '🌊',
  aws_s3_bucket: '📦',
  aws_ebs_volume: '💾',
  aws_efs: '📁',
  Document: '📄',
  CodeFunction: 'ƛ',
  _default: '🔧',
}

function getIcon(nodeType) {
  if (TYPE_ICONS[nodeType]) return TYPE_ICONS[nodeType]
  for (const [type, icon] of Object.entries(TYPE_ICONS)) {
    if (type !== '_default' && nodeType.includes(type)) return icon
  }
  return TYPE_ICONS._default
}

// Color codes by node status
const STATUS_COLORS = {
  healthy: '#10b981',
  degraded: '#f59e0b',
  failed: '#ef4444',
  simulated_failure: '#ef4444',
  unknown: '#6b7280',
}

function getStatusColor(status) {
  return STATUS_COLORS[status] || STATUS_COLORS.unknown
}

/**
 * Inline CSS keyframes for SVG animations
 */
const ANIMATION_STYLES = `
@keyframes pulse-glow {
  0%, 100% {
    opacity: 0.3;
    r: 20;
  }
  50% {
    opacity: 0.8;
    r: 28;
  }
}

@keyframes pulse-healthy {
  0%, 100% {
    filter: drop-shadow(0 0 4px rgba(16, 185, 129, 0.3));
  }
  50% {
    filter: drop-shadow(0 0 12px rgba(16, 185, 129, 0.6));
  }
}

@keyframes pulse-failed {
  0%, 100% {
    filter: drop-shadow(0 0 4px rgba(220, 38, 38, 0.3));
  }
  50% {
    filter: drop-shadow(0 0 12px rgba(220, 38, 38, 0.6));
  }
}

@keyframes flow-animation {
  0% {
    stroke-dashoffset: 20;
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
  100% {
    stroke-dashoffset: -20;
    opacity: 0;
  }
}

@keyframes node-idle {
  0%, 100% {
    opacity: 0.85;
  }
  50% {
    opacity: 1;
  }
}

@keyframes hop-ring {
  0% {
    r: 18;
    opacity: 0.8;
  }
  100% {
    r: 50;
    opacity: 0;
  }
}

@keyframes particle-pulse {
  0%, 100% {
    r: 4;
    opacity: 0.6;
  }
  50% {
    r: 6;
    opacity: 1;
  }
}

@keyframes edge-active-glow {
  0%, 100% {
    stroke-opacity: 0.6;
    stroke-width: 3;
    filter: drop-shadow(0 0 2px rgba(239, 68, 68, 0.3));
  }
  50% {
    stroke-opacity: 1;
    stroke-width: 4;
    filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.8));
  }
}

@keyframes edge-pending-pulse {
  0%, 100% {
    stroke-opacity: 0.4;
  }
  50% {
    stroke-opacity: 0.8;
  }
}

@keyframes dash-flow {
  0% {
    stroke-dashoffset: 0;
  }
  100% {
    stroke-dashoffset: -20;
  }
}

@keyframes particle-flow {
  0% {
    offset-distance: 0%;
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 1;
  }
  100% {
    offset-distance: 100%;
    opacity: 0;
  }
}

.node-activating { animation: pulse-glow 0.8s ease-in-out infinite; }
.node-healthy { animation: pulse-healthy 2s ease-in-out infinite; }
.node-failed { animation: pulse-failed 1.5s ease-in-out infinite; }
.node-idle { animation: node-idle 3s ease-in-out infinite; }
.edge-flow { stroke-dasharray: 10, 10; animation: flow-animation 1.5s linear infinite; }
.hop-ring { animation: hop-ring 2s ease-out infinite; }
.edge-active { animation: edge-active-glow 0.6s ease-in-out infinite, dash-flow 0.8s linear infinite; }
.edge-pending { animation: edge-pending-pulse 1.2s ease-in-out infinite; }
.particle-pulse { animation: particle-pulse 0.6s ease-in-out infinite; }
`

export default function InfrastructureMap({
  topology = { nodes: [], edges: [] },
  simulationResult = null,
  simulationTime = 0,
  selectedNode = null,
  onNodeSelect = () => {},
}) {
  // Compute layout for all nodes
  const positions = useMemo(
    () => computeLayout(topology.nodes, topology.edges, 900, 580),
    [topology]
  )

  // Build sets for animation classes
  const blastIds = useMemo(
    () => new Set(simulationResult?.blast_radius?.map((b) => b.id) ?? []),
    [simulationResult]
  )

  const activatingIds = useMemo(() => {
    if (!simulationResult || simulationTime === null) return new Set()
    const WINDOW = 600 // ms — window during which a node shows activation glow
    return new Set(
      simulationResult.blast_radius
        .filter((n) => simulationTime >= n.step_time_ms && simulationTime < n.step_time_ms + WINDOW)
        .map((n) => n.id)
    )
  }, [simulationResult, simulationTime])

  const failedIds = useMemo(() => {
    if (!simulationResult || simulationTime === null) return new Set()
    return new Set(
      simulationResult.blast_radius
        .filter((n) => simulationTime >= n.step_time_ms + 600)
        .map((n) => n.id)
    )
  }, [simulationResult, simulationTime])

  // Build a map of nodes for quick lookup
  const nodeMap = useMemo(() => {
    const m = new Map()
    for (const node of topology.nodes) {
      m.set(node.id, node)
    }
    return m
  }, [topology.nodes])

  // Map blast radius nodes by ID for quick lookup during edge state calculation
  const blastNodeMap = useMemo(() => {
    if (!simulationResult) return new Map()
    return new Map(simulationResult.blast_radius.map(n => [n.id, n]))
  }, [simulationResult])

  // Calculate state of each edge based on propagation timeline
  const edgeStates = useMemo(() => {
    if (!simulationResult) {
      return topology.edges.map((edge, idx) => ({
        idx,
        edge,
        state: 'idle',
        isPropagation: false,
      }))
    }

    const FLOW_WINDOW = 800 // ms window before target activation to show flowing

    return topology.edges.map((edge, idx) => {
      const src = blastNodeMap.get(edge.source)
      const tgt = blastNodeMap.get(edge.target)

      if (!src || !tgt) {
        return { idx, edge, state: 'idle', isPropagation: false }
      }

      const isPropagation = src.distance < tgt.distance
      const activateAt = tgt.step_time_ms

      let state = 'idle'
      if (simulationTime < activateAt - FLOW_WINDOW) {
        state = 'pending'
      } else if (simulationTime < activateAt) {
        state = 'flowing'
      } else {
        state = 'burned'
      }

      return { idx, edge, state, isPropagation }
    })
  }, [topology.edges, blastNodeMap, simulationTime, simulationResult])

  // Derive node animating state
  const getNodeClass = (nodeId) => {
    if (activatingIds.has(nodeId)) return 'node-activating'
    if (failedIds.has(nodeId)) return 'node-failed'
    if (blastIds.has(nodeId)) return 'node-healthy'
    return 'node-idle'
  }

  const SVG_WIDTH = 900
  const SVG_HEIGHT = 580

  // Collect edges that are within the blast radius (both endpoints in blastIds)
  const blastEdges = useMemo(() => {
    if (blastIds.size === 0) return []
    return topology.edges.filter((e) => blastIds.has(e.source) && blastIds.has(e.target))
  }, [topology.edges, blastIds])

  return (
    <div className="w-full h-full relative bg-dt-bg overflow-hidden flex items-center justify-center">
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full"
        style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)' }}
      >
        {/* Embedded styles and defs */}
        <defs>
          <style>{ANIMATION_STYLES}</style>

          {/* Arrowhead markers for edge direction — larger for visibility */}
          <marker id="arrowhead" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
            <path d="M 0 0 L 12 6 L 0 12 Z" fill="#64748b" opacity="0.9" />
          </marker>
          <marker id="arrowhead-active" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
            <path d="M 0 0 L 12 6 L 0 12 Z" fill="#ef4444" opacity="1" />
          </marker>

          {/* Grid background pattern */}
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#334155" strokeWidth="0.5" opacity="0.3" />
          </pattern>
        </defs>

        {/* Background grid */}
        <rect width={SVG_WIDTH} height={SVG_HEIGHT} fill="url(#grid)" />

        {/* Base layer: All topology edges with Bezier curves (always visible, directional) */}
        {topology.edges.map((edge, idx) => {
          const bezier = getBezierPath(positions, edge)
          if (!bezier) return null

          // Get edge state from edgeStates array
          const edgeState = edgeStates[idx]
          const { state } = edgeState || { state: 'idle' }

          // Check if this edge is in the blast radius
          const inBlastRadius = simulationResult && blastIds.has(edge.source) && blastIds.has(edge.target)
          const edgeStroke = inBlastRadius ? '#ef4444' : '#64748b'
          const edgeWidth = inBlastRadius ? 3 : 2
          const edgeOpacity = inBlastRadius ? 0.9 : 0.7

          return (
            <g key={`edge-group-${idx}`}>
              <path
                key={`edge-${idx}`}
                d={bezier.d}
                fill="none"
                stroke={edgeStroke}
                strokeWidth={edgeWidth}
                opacity={edgeOpacity}
                strokeDasharray={inBlastRadius ? '10, 10' : 'none'}
                className={inBlastRadius ? 'edge-active' : ''}
                markerEnd={inBlastRadius ? 'url(#arrowhead-active)' : 'url(#arrowhead)'}
                pointerEvents="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {/* Animated particle flowing along edge during propagation */}
              {state === 'flowing' && (
                <circle
                  r="4"
                  fill="#ef4444"
                  opacity="0.9"
                  className="particle-pulse"
                >
                  <animateMotion
                    dur="0.8s"
                    repeatCount="indefinite"
                    path={bezier.d}
                  />
                </circle>
              )}
            </g>
          )
        })}

        {/* Node layer */}
        {topology.nodes.map((node) => {
          const pos = positions.get(node.id)
          if (!pos) return null

          const isSelected = selectedNode?.id === node.id
          const nodeAnimClass = getNodeClass(node.id)
          const statusColor = getStatusColor(node.status)
          const icon = getIcon(node.type)

          return (
            <g
              key={`node-${node.id}`}
              transform={`translate(${pos.x}, ${pos.y})`}
              className="cursor-pointer"
              onClick={() => onNodeSelect(node)}
              style={{ opacity: blastIds.has(node.id) || !simulationResult ? 1 : 0.4 }}
            >
              {/* Outer pulse ring (animated when activating) */}
              {activatingIds.has(node.id) && (
                <circle
                  r={20}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth="2"
                  className="node-activating"
                  opacity="0.6"
                />
              )}

              {/* Selected node highlight ring */}
              {isSelected && (
                <circle
                  r={22}
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="2"
                  opacity="0.8"
                />
              )}

              {/* Main circle */}
              <circle
                r={16}
                fill={statusColor}
                className={nodeAnimClass}
                opacity={activatingIds.has(node.id) ? 0.9 : 0.7}
              />

              {/* Type icon label (centered in circle) */}
              <text
                x={0}
                y={0}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="14"
                fontWeight="bold"
              >
                {icon}
              </text>

              {/* Node name label (below circle) */}
              <text
                x={0}
                y={28}
                textAnchor="middle"
                fontSize="10"
                fill="#e2e8f0"
                fontFamily="monospace"
                className="pointer-events-none"
              >
                {node.name?.substring(0, 12)}
              </text>

              {/* Status badge (top-right) */}
              <circle
                cx={12}
                cy={-12}
                r={5}
                fill={statusColor}
                opacity="0.9"
              />

              {/* Tooltip on hover */}
              <title>
                {`${node.name} (${node.type})\nStatus: ${node.status}\nRegion: ${node.region || 'N/A'}\nAZ: ${node.az || 'N/A'}\nRTO: ${node.rto_minutes || 'N/A'}m | RPO: ${node.rpo_minutes || 'N/A'}m`}
              </title>
            </g>
          )
        })}

        {/* Concentric hop rings on origin node (only during simulation) */}
        {simulationResult && positions.has(simulationResult.origin_node_id) && (
          <>
            {[0, 1, 2].map((delayIdx) => {
              const originPos = positions.get(simulationResult.origin_node_id)
              return (
                <circle
                  key={`hop-ring-${delayIdx}`}
                  cx={originPos.x}
                  cy={originPos.y}
                  r={18}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth="2"
                  className="hop-ring"
                  style={{
                    animationDelay: `${delayIdx * 0.66}s`,
                    opacity: 0.8,
                  }}
                />
              )
            })}
          </>
        )}

        {/* Legend and info overlay */}
        {simulationResult && (
          <g>
            {/* Semi-transparent legend background */}
            <rect
              x={10}
              y={SVG_HEIGHT - 70}
              width={280}
              height={60}
              fill="#0f172a"
              opacity="0.85"
              rx={4}
              stroke="#475569"
              strokeWidth="1"
            />

            {/* Legend text */}
            <text x={20} y={SVG_HEIGHT - 50} fontSize="11" fill="#cbd5e1" fontWeight="bold">
              Blast Radius Status
            </text>
            <circle cx={20} cy={SVG_HEIGHT - 35} r={4} fill="#ef4444" />
            <text x={28} y={SVG_HEIGHT - 32} fontSize="10" fill="#e2e8f0">
              Activating
            </text>

            <circle cx={130} cy={SVG_HEIGHT - 35} r={4} fill="#ef4444" opacity="0.6" />
            <text x={138} y={SVG_HEIGHT - 32} fontSize="10" fill="#e2e8f0">
              Failed
            </text>

            <circle cx={200} cy={SVG_HEIGHT - 35} r={4} fill="#10b981" />
            <text x={208} y={SVG_HEIGHT - 32} fontSize="10" fill="#e2e8f0">
              Healthy
            </text>

            {/* Node count */}
            <text x={20} y={SVG_HEIGHT - 15} fontSize="10" fill="#94a3b8" fontFamily="monospace">
              Affected: {blastIds.size} nodes
            </text>
          </g>
        )}
      </svg>

      {/* Idle state message */}
      {!simulationResult && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/40 pointer-events-none">
          <div className="text-center text-gray-400">
            <div className="text-lg font-mono">Select a node and click Simulate</div>
            <div className="text-xs mt-2">Infrastructure topology ready</div>
          </div>
        </div>
      )}
    </div>
  )
}
