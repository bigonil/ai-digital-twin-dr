import { useRef, useCallback, useMemo, useEffect, useState } from 'react'
import { ForceGraph3D } from 'react-force-graph'

const STATUS_COLOR = {
  healthy:           '#10b981',
  degraded:          '#f59e0b',
  failed:            '#ef4444',
  simulated_failure: '#dc2626',
  unknown:           '#6b7280',
}

const TYPE_SIZE = {
  aws_db_instance:       8,
  aws_rds_cluster:       10,
  aws_lb:                9,
  aws_instance:          6,
  aws_s3_bucket:         5,
  aws_sqs_queue:         4,
  CodeFunction:          3,
  Document:              3,
}

function nodeColor(node, blastSet, simulationTime, activatingNodes) {
  // If timeline is playing and node is activating RIGHT NOW, flash it
  if (activatingNodes.has(node.id)) {
    return '#ff6b6b' // bright red while activating
  }

  // If node has step_time_ms and time has reached it, show as failed
  if (node.step_time_ms !== undefined && simulationTime >= node.step_time_ms) {
    return '#dc2626'
  }

  // Original logic
  if (blastSet.has(node.id)) return '#dc2626'
  return STATUS_COLOR[node.status] ?? '#6b7280'
}

function nodeSize(node) {
  return TYPE_SIZE[node.type] ?? 5
}

export default function Graph3D({
  topology,
  blastRadius,
  onNodeClick,
  simulationTime = null  // NEW: time from timeline player
}) {
  const fgRef = useRef()
  const containerRef = useRef()
  const [dims, setDims] = useState({ width: 0, height: 0 })
  const blastSet = useMemo(() => new Set(blastRadius.map(n => n.id)), [blastRadius])

  // Track nodes that are currently activating (for visual flash)
  const [activatingNodes, setActivatingNodes] = useState(new Set())

  useEffect(() => {
    if (!containerRef.current) return

    // Set initial dimensions from container
    const updateDims = () => {
      if (containerRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect()
        if (width > 0 && height > 0) {
          setDims({ width, height })
        }
      }
    }

    updateDims()

    const ro = new ResizeObserver(() => {
      updateDims()
    })
    ro.observe(containerRef.current)

    // Fallback: retry after a delay if dimensions not set
    const timer = setTimeout(() => {
      if (dims.width === 0) {
        updateDims()
      }
    }, 500)

    return () => {
      ro.disconnect()
      clearTimeout(timer)
    }
  }, [])

  // Detect which nodes are "activating" (just crossed their step_time_ms)
  useEffect(() => {
    if (simulationTime === null || !topology?.nodes) return

    const nowActivating = new Set()
    topology.nodes.forEach(node => {
      const blastNode = blastRadius.find(b => b.id === node.id)
      if (blastNode && blastNode.step_time_ms !== undefined) {
        // Node activates when simulationTime passes its step_time_ms
        // Flash for 200ms
        if (simulationTime >= blastNode.step_time_ms) {
          const timeSinceActivation = simulationTime - blastNode.step_time_ms
          if (timeSinceActivation < 200) {
            nowActivating.add(node.id)
          }
        }
      }
    })
    setActivatingNodes(nowActivating)
  }, [simulationTime, topology, blastRadius])

  const graphData = useMemo(() => {
    if (!topology) return { nodes: [], links: [] }
    return {
      nodes: topology.nodes.map(n => {
        const blastNode = blastRadius.find(b => b.id === n.id)
        return {
          ...n,
          step_time_ms: blastNode?.step_time_ms,
          distance: blastNode?.distance,
          __color: nodeColor(n, blastSet, simulationTime ?? 0, activatingNodes),
          __size: nodeSize(n),
        }
      }),
      links: topology.edges.map(e => ({ source: e.source, target: e.target, type: e.type })),
    }
  }, [topology, blastSet, simulationTime, activatingNodes, blastRadius])

  const handleNodeClick = useCallback((node) => {
    onNodeClick(node)
    if (fgRef.current) {
      fgRef.current.cameraPosition(
        { x: node.x + 60, y: node.y + 30, z: node.z + 60 },
        node,
        1200,
      )
    }
  }, [onNodeClick])

  // Render node labels with distance badges
  const nodeLabel = (n) => {
    const distance = n.distance !== undefined ? `\nDistance: ${n.distance}` : ''
    return `${n.name}\n${n.type}\n${n.region ?? ''}${distance}`
  }

  // Link styling: highlight active edges
  const linkColor = (l) => {
    const targetNode = graphData.nodes.find(n => n.id === l.target)
    if (targetNode && activatingNodes.has(l.target)) {
      return '#ff6b6b' // bright red for activating links
    }
    return l.type === 'DEPENDS_ON' ? '#3b82f6' : '#6b7280'
  }

  const linkWidth = (l) => {
    const targetNode = graphData.nodes.find(n => n.id === l.target)
    if (targetNode && activatingNodes.has(l.target)) {
      return 2 // thicker while activating
    }
    return 1
  }

  return (
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
      {dims.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          width={dims.width}
          height={dims.height}
          backgroundColor="#0a0e1a"
          nodeColor={n => n.__color}
          nodeVal={n => n.__size}
          nodeLabel={nodeLabel}
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          onNodeClick={handleNodeClick}
          nodeThreeObjectExtend={false}
        />
      )}
    </div>
  )
}
