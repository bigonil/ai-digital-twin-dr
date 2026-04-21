import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import * as client from '../api/client'

export default function ArchitecturePlanner({ topology }) {
  const [originNode, setOriginNode] = useState('')
  const [depth, setDepth] = useState(5)
  const [virtualNodes, setVirtualNodes] = useState([])
  const [virtualEdges, setVirtualEdges] = useState([])
  const [newNodeId, setNewNodeId] = useState('')
  const [newNodeName, setNewNodeName] = useState('')
  const [newNodeType, setNewNodeType] = useState('database')
  const [newNodeRto, setNewNodeRto] = useState('')
  const [newEdgeSource, setNewEdgeSource] = useState('')
  const [newEdgeTarget, setNewEdgeTarget] = useState('')
  const [result, setResult] = useState(null)

  const simulationMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        origin_node_id: originNode,
        depth,
        virtual_nodes: virtualNodes,
        virtual_edges: virtualEdges,
      }
      return client.runWhatIfSimulation(payload)
    },
  })

  const handleAddVirtualNode = () => {
    if (!newNodeId || !newNodeName) return
    setVirtualNodes([
      ...virtualNodes,
      {
        id: newNodeId.startsWith('virtual-') ? newNodeId : `virtual-${newNodeId}`,
        name: newNodeName,
        type: newNodeType,
        rto_minutes: newNodeRto ? parseInt(newNodeRto) : null,
        is_redundant: false,
      },
    ])
    setNewNodeId('')
    setNewNodeName('')
    setNewNodeType('database')
    setNewNodeRto('')
  }

  const handleRemoveVirtualNode = (id) => {
    setVirtualNodes(virtualNodes.filter(n => n.id !== id))
  }

  const handleAddVirtualEdge = () => {
    if (!newEdgeSource || !newEdgeTarget) return
    setVirtualEdges([...virtualEdges, { source: newEdgeSource, target: newEdgeTarget, type: 'DEPENDS_ON' }])
    setNewEdgeSource('')
    setNewEdgeTarget('')
  }

  const handleRemoveVirtualEdge = (idx) => {
    setVirtualEdges(virtualEdges.filter((_, i) => i !== idx))
  }

  const handleSimulate = () => {
    if (!originNode) return
    simulationMutation.mutate()
  }

  const allNodeIds = topology?.nodes?.map(n => n.id) || []
  const allNodeOptions = [...allNodeIds, ...virtualNodes.map(n => n.id)]

  const getDelta = (value) => {
    if (value === null || value === undefined) return '—'
    if (value === 0) return '→'
    return value > 0 ? `↑ +${value}` : `↓ ${value}`
  }

  if (simulationMutation.isPending) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-400 font-mono">Running simulation…</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-dt-bg text-gray-100 gap-6 p-6 overflow-y-auto">
      <div>
        <h2 className="text-2xl font-bold mb-4">Architecture Planning (What-If)</h2>

        {/* Origin Selection */}
        <div className="mb-6 p-4 bg-dt-surface border border-dt-border rounded">
          <label className="block text-sm font-mono text-gray-400 mb-2">Origin Node</label>
          <select
            value={originNode}
            onChange={e => setOriginNode(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100 font-mono text-sm"
          >
            <option value="">Select a node…</option>
            {allNodeIds.map(id => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>

          <label className="block text-sm font-mono text-gray-400 mt-3 mb-2">Simulation Depth</label>
          <input
            type="range"
            min="1"
            max="10"
            value={depth}
            onChange={e => setDepth(parseInt(e.target.value))}
            className="w-full"
          />
          <div className="text-xs text-gray-500 mt-1">{depth}</div>
        </div>

        {/* Add Virtual Node */}
        <div className="mb-6 p-4 bg-dt-surface border border-dt-border rounded">
          <h3 className="font-bold text-sm mb-3">Add Virtual Node</h3>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <input
              type="text"
              placeholder="Node ID (e.g., replica-db)"
              value={newNodeId}
              onChange={e => setNewNodeId(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            />
            <input
              type="text"
              placeholder="Node Name"
              value={newNodeName}
              onChange={e => setNewNodeName(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            />
            <select
              value={newNodeType}
              onChange={e => setNewNodeType(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            >
              <option>database</option>
              <option>cache</option>
              <option>service</option>
              <option>storage</option>
            </select>
            <input
              type="number"
              placeholder="RTO (minutes)"
              value={newNodeRto}
              onChange={e => setNewNodeRto(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            />
          </div>
          <button
            onClick={handleAddVirtualNode}
            className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-mono"
          >
            Add Virtual Node
          </button>

          {/* Virtual Nodes List */}
          {virtualNodes.length > 0 && (
            <div className="mt-3 space-y-2">
              {virtualNodes.map(node => (
                <div key={node.id} className="flex justify-between items-center px-2 py-1 bg-gray-900 rounded text-xs">
                  <span className="font-mono">{node.name} ({node.id})</span>
                  <button
                    onClick={() => handleRemoveVirtualNode(node.id)}
                    className="text-red-400 hover:text-red-300"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Add Virtual Edge */}
        <div className="mb-6 p-4 bg-dt-surface border border-dt-border rounded">
          <h3 className="font-bold text-sm mb-3">Add Virtual Edge</h3>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <select
              value={newEdgeSource}
              onChange={e => setNewEdgeSource(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            >
              <option value="">Source node…</option>
              {allNodeOptions.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            <select
              value={newEdgeTarget}
              onChange={e => setNewEdgeTarget(e.target.value)}
              className="px-2 py-1 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
            >
              <option value="">Target node…</option>
              {allNodeOptions.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleAddVirtualEdge}
            className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-mono"
          >
            Add Virtual Edge
          </button>

          {/* Virtual Edges List */}
          {virtualEdges.length > 0 && (
            <div className="mt-3 space-y-2">
              {virtualEdges.map((edge, idx) => (
                <div key={idx} className="flex justify-between items-center px-2 py-1 bg-gray-900 rounded text-xs">
                  <span className="font-mono">{edge.source} → {edge.target}</span>
                  <button
                    onClick={() => handleRemoveVirtualEdge(idx)}
                    className="text-red-400 hover:text-red-300"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Simulate Button */}
        <button
          onClick={handleSimulate}
          disabled={!originNode || simulationMutation.isPending}
          className="w-full px-4 py-3 bg-dt-accent hover:bg-blue-600 text-white font-bold rounded disabled:opacity-50"
        >
          {simulationMutation.isPending ? 'Simulating…' : 'Run What-If Simulation'}
        </button>

        {simulationMutation.isError && (
          <div className="mt-4 p-3 bg-red-900/20 border border-red-700 rounded text-red-400 text-sm font-mono">
            Error: {simulationMutation.error?.message}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className="p-6 bg-dt-surface border border-dt-border rounded">
          <h3 className="font-bold text-lg mb-4">Comparison Results</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-gray-400 font-mono mb-2">BASELINE</div>
              <div className="space-y-2 text-sm">
                <div>Affected: {result.baseline.total_affected}</div>
                <div>RTO: {result.baseline.worst_case_rto_minutes ?? '—'} min</div>
                <div>RPO: {result.baseline.worst_case_rpo_minutes ?? '—'} min</div>
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 font-mono mb-2">PROPOSED</div>
              <div className="space-y-2 text-sm">
                <div>Affected: {result.proposed.total_affected} {getDelta(result.blast_radius_delta)}</div>
                <div>RTO: {result.proposed.worst_case_rto_minutes ?? '—'} min {getDelta(result.rto_delta_minutes)}</div>
                <div>RPO: {result.proposed.worst_case_rpo_minutes ?? '—'} min {getDelta(result.rpo_delta_minutes)}</div>
              </div>
            </div>
          </div>
          <div className="mt-4 text-xs text-gray-400 font-mono">
            Virtual nodes: +{result.virtual_nodes_added} | Virtual edges: +{result.virtual_edges_added}
          </div>
        </div>
      )}
    </div>
  )
}
