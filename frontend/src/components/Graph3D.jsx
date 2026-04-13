import { useRef, useCallback, useMemo } from 'react'
import ForceGraph3D from 'react-force-graph'

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

function nodeColor(node, blastSet) {
  if (blastSet.has(node.id)) return '#dc2626'
  return STATUS_COLOR[node.status] ?? '#6b7280'
}

function nodeSize(node) {
  return TYPE_SIZE[node.type] ?? 5
}

export default function Graph3D({ topology, blastRadius, onNodeClick }) {
  const fgRef = useRef()
  const blastSet = useMemo(() => new Set(blastRadius.map(n => n.id)), [blastRadius])

  const graphData = useMemo(() => {
    if (!topology) return { nodes: [], links: [] }
    return {
      nodes: topology.nodes.map(n => ({ ...n, __color: nodeColor(n, blastSet), __size: nodeSize(n) })),
      links: topology.edges.map(e => ({ source: e.source, target: e.target, type: e.type })),
    }
  }, [topology, blastSet])

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

  return (
    <ForceGraph3D
      ref={fgRef}
      graphData={graphData}
      backgroundColor="#0a0e1a"
      nodeColor={n => n.__color}
      nodeVal={n => n.__size}
      nodeLabel={n => `${n.name}\n${n.type}\n${n.region ?? ''}`}
      linkColor={l => l.type === 'DEPENDS_ON' ? '#3b82f6' : '#6b7280'}
      linkWidth={1}
      linkDirectionalArrowLength={4}
      linkDirectionalArrowRelPos={1}
      onNodeClick={handleNodeClick}
      nodeThreeObjectExtend={false}
    />
  )
}
