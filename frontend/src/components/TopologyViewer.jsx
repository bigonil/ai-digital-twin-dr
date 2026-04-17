import { useState } from 'react'
import { ChevronRight } from 'lucide-react'

const TYPE_ICON = {
  aws_db_instance: '🗄️',
  aws_rds_cluster: '📊',
  aws_lb: '⚖️',
  aws_instance: '🖥️',
  aws_s3_bucket: '💾',
  aws_sqs_queue: '📬',
  CodeFunction: '⚙️',
  Document: '📄',
}

const STATUS_BG = {
  healthy: 'bg-green-900/30',
  degraded: 'bg-amber-900/30',
  failed: 'bg-red-900/30',
  unknown: 'bg-gray-900/30',
}

export default function TopologyViewer({ topology, selectedNode, onNodeSelect }) {
  const [filter, setFilter] = useState('')
  const [expandedGroups, setExpandedGroups] = useState({})

  if (!topology?.nodes?.length) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 font-mono text-sm">
        No nodes loaded
      </div>
    )
  }

  const filteredNodes = topology.nodes.filter(n =>
    n.name.toLowerCase().includes(filter.toLowerCase()) ||
    n.type.toLowerCase().includes(filter.toLowerCase())
  )

  const grouped = filteredNodes.reduce((acc, node) => {
    const key = node.type || 'unknown'
    if (!acc[key]) acc[key] = []
    acc[key].push(node)
    return acc
  }, {})

  const toggleGroup = (type) => {
    setExpandedGroups(prev => ({
      ...prev,
      [type]: !prev[type]
    }))
  }

  return (
    <div className="flex flex-col h-full bg-dt-bg text-gray-100">
      {/* Header */}
      <div className="px-4 py-3 border-b border-dt-border shrink-0">
        <p className="text-xs font-mono text-gray-400 uppercase tracking-widest mb-2">
          Infrastructure Topology
        </p>
        <input
          type="text"
          placeholder="Filter nodes..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full bg-dt-surface border border-dt-border rounded px-2 py-1.5 text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-dt-accent"
        />
        <p className="text-xs text-gray-500 mt-2">
          {filteredNodes.length} of {topology.nodes.length} nodes
        </p>
      </div>

      {/* Grouped List */}
      <div className="flex-1 overflow-y-auto">
        {Object.entries(grouped).map(([type, nodes]) => (
          <div key={type} className="border-b border-dt-border/30">
            <button
              onClick={() => toggleGroup(type)}
              className="w-full flex items-center gap-2 px-4 py-2 hover:bg-dt-surface text-left text-xs font-mono text-gray-400 transition-colors"
            >
              <ChevronRight
                size={14}
                className={`transition-transform ${expandedGroups[type] ? 'rotate-90' : ''}`}
              />
              <span>{TYPE_ICON[type] || '•'}</span>
              <span className="flex-1">{type}</span>
              <span className="text-gray-600">{nodes.length}</span>
            </button>

            {expandedGroups[type] && (
              <div className="bg-dt-surface/30">
                {nodes.map(node => (
                  <button
                    key={node.id}
                    onClick={() => onNodeSelect(node)}
                    className={`w-full flex items-center gap-2 px-8 py-1.5 text-left text-xs font-mono border-l-2 border-transparent transition-colors ${
                      selectedNode?.id === node.id
                        ? 'border-dt-accent bg-dt-accent/10 text-dt-accent'
                        : `${STATUS_BG[node.status] || 'bg-gray-900/10'} text-gray-300 hover:text-gray-100 hover:bg-gray-900/30`
                    }`}
                  >
                    <span className="text-gray-600">•</span>
                    <span className="flex-1 truncate">{node.name}</span>
                    <span className="text-gray-600 text-xs">{node.status}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Stats Footer */}
      {selectedNode && (
        <div className="border-t border-dt-border px-4 py-2 bg-dt-surface/50 shrink-0">
          <p className="text-xs text-gray-500 font-mono">
            Selected: <span className="text-dt-accent">{selectedNode.name}</span>
          </p>
          {selectedNode.estimated_rto_minutes && (
            <p className="text-xs text-gray-600 font-mono">
              RTO: {selectedNode.estimated_rto_minutes} min
            </p>
          )}
        </div>
      )}
    </div>
  )
}
