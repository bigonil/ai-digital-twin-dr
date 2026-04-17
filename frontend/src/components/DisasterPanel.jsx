import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Zap, RotateCcw, AlertTriangle, Eye, EyeOff, Maximize2 } from 'lucide-react'
import { simulateDisaster, resetNode } from '../api/client.js'
import SimulationTimeline from './SimulationTimeline.jsx'
import DisasterVisualization from './DisasterVisualization.jsx'
import DisasterVisualizationTab from './DisasterVisualizationTab.jsx'

export default function DisasterPanel({ selectedNode, onSimulationResult, onReset, onSimulationTimeChange, topology }) {
  const [depth, setDepth] = useState(5)
  const [blastRows, setBlastRows] = useState([])
  const [simulationTime, setSimulationTime] = useState(0)
  const [simulationResult, setSimulationResult] = useState(null)
  const [showVisualization, setShowVisualization] = useState(true)
  const [showFullscreenViz, setShowFullscreenViz] = useState(false)
  const qc = useQueryClient()

  const simMutation = useMutation({
    mutationFn: () => simulateDisaster(selectedNode.id, depth),
    onSuccess: (data) => {
      setBlastRows(data.blast_radius ?? [])
      setSimulationResult(data)
      onSimulationResult(data.blast_radius ?? [])
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => resetNode(selectedNode.id),
    onSuccess: () => {
      setBlastRows([])
      setSimulationTime(0)
      setSimulationResult(null)
      onReset()
      qc.invalidateQueries({ queryKey: ['topology'] })
    },
  })

  return (
    <div className="bg-dt-surface border-t border-dt-border px-4 py-3 shrink-0" style={{ maxHeight: '340px' }}>
      <div className="flex items-center gap-4 mb-2">
        <span className="text-xs font-mono text-gray-400 uppercase tracking-widest flex items-center gap-1">
          <AlertTriangle size={12} className="text-dt-warning" /> Disaster Simulation
        </span>

        <div className="flex items-center gap-2 ml-auto">
          <label className="text-xs text-gray-500">Depth</label>
          <input
            type="number" min={1} max={10} value={depth}
            onChange={e => setDepth(Number(e.target.value))}
            className="w-14 bg-dt-bg border border-dt-border rounded px-2 py-1 text-xs font-mono text-gray-200"
          />
          <button
            onClick={() => simMutation.mutate()}
            disabled={!selectedNode || simMutation.isPending}
            className="flex items-center gap-1 bg-dt-danger hover:bg-red-700 disabled:opacity-40 text-white text-xs font-mono px-3 py-1.5 rounded transition-colors"
          >
            <Zap size={12} /> Simulate
          </button>
          <button
            onClick={() => resetMutation.mutate()}
            disabled={!selectedNode || blastRows.length === 0}
            className="flex items-center gap-1 border border-dt-border hover:border-dt-accent text-gray-400 hover:text-dt-accent text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-40"
          >
            <RotateCcw size={12} /> Reset
          </button>
        </div>
      </div>

      {selectedNode ? (
        <p className="text-xs text-gray-500 font-mono mb-2">
          Target: <span className="text-dt-accent">{selectedNode.name}</span> ({selectedNode.type})
        </p>
      ) : (
        <p className="text-xs text-gray-600 font-mono mb-2">Click a node in the graph to select it.</p>
      )}

      {simulationResult && (
        <div className="mb-3 pb-3 border-b border-dt-border/30">
          <SimulationTimeline
            simulationResult={simulationResult}
            onTimeChange={(time) => {
              setSimulationTime(time)
              if (onSimulationTimeChange) onSimulationTimeChange(time)
            }}
          />
        </div>
      )}

      {simulationResult && (
        <>
          <div className="flex items-center gap-2 mb-2 px-4 py-1 border-b border-dt-border/30">
            <button
              onClick={() => setShowVisualization(!showVisualization)}
              className="flex items-center gap-1 text-xs font-mono text-gray-400 hover:text-dt-accent transition-colors"
            >
              {showVisualization ? (
                <>
                  <Eye size={12} /> Map
                </>
              ) : (
                <>
                  <EyeOff size={12} /> Table
                </>
              )}
            </button>
            <button
              onClick={() => setShowFullscreenViz(true)}
              className="flex items-center gap-1 text-xs font-mono text-gray-400 hover:text-dt-accent transition-colors"
              title="Open full-screen visualization"
            >
              <Maximize2 size={12} /> Fullscreen
            </button>
            <span className="text-xs text-gray-600 ml-auto">
              {blastRows.length} nodes affected
            </span>
          </div>

          {showVisualization ? (
            <div style={{ maxHeight: '140px', overflow: 'hidden' }}>
              {blastRows.length > 0 ? (
                <DisasterVisualization
                  blastRadius={blastRows}
                  topology={topology}
                  simulationTime={simulationTime}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-gray-600 font-mono text-xs">
                  No blast radius data received
                </div>
              )}
            </div>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: '140px' }}>
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-gray-500 text-left border-b border-dt-border">
                    <th className="pb-1 pr-4">Depth</th><th className="pb-1 pr-4">Node</th>
                    <th className="pb-1 pr-4">Type</th><th className="pb-1 pr-4">RTO</th>
                  </tr>
                </thead>
                <tbody>
                  {blastRows.map((r, i) => (
                    <tr key={i} className="border-b border-dt-border/30 hover:bg-dt-bg/50">
                      <td className="py-0.5 pr-4 text-dt-danger">{r.distance}</td>
                      <td className="py-0.5 pr-4 text-gray-200">{r.name}</td>
                      <td className="py-0.5 pr-4 text-gray-400">{r.type}</td>
                      <td className="py-0.5 pr-4 text-dt-warning">{r.estimated_rto_minutes ? `${r.estimated_rto_minutes}m` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Fullscreen Visualization Modal */}
      {showFullscreenViz && (
        <DisasterVisualizationTab
          blastRadius={blastRows}
          topology={topology}
          simulationTime={simulationTime}
          onClose={() => setShowFullscreenViz(false)}
        />
      )}
    </div>
  )
}
