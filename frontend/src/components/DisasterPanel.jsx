/**
 * DisasterPanel.jsx (Simplified)
 * Controls-only version: depth input, Simulate button, Reset button.
 * All visualization and timeline state is now managed in App.jsx.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Zap, RotateCcw, AlertTriangle } from 'lucide-react'
import { simulateDisaster, resetNode } from '../api/client.js'

export default function DisasterPanel({ selectedNode, onSimulationResult, onReset }) {
  const [depth, setDepth] = useState(5)
  const qc = useQueryClient()

  const simMutation = useMutation({
    mutationFn: () => simulateDisaster(selectedNode.id, depth),
    onSuccess: (data) => {
      // Pass the full SimulationWithTimeline object to parent
      onSimulationResult(data)
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => resetNode(selectedNode.id),
    onSuccess: () => {
      onReset()
      qc.invalidateQueries({ queryKey: ['topology'] })
    },
  })

  return (
    <div className="shrink-0 bg-dt-surface border-t border-dt-border px-4 py-2 h-14 flex items-center gap-4">
      {/* Label */}
      <span className="text-xs font-mono text-gray-400 uppercase tracking-widest flex items-center gap-1">
        <AlertTriangle size={12} className="text-dt-warning" /> Disaster Simulation
      </span>

      {/* Selected node indicator */}
      {selectedNode && (
        <span className="text-xs font-mono text-gray-500">
          Target: <span className="text-dt-accent">{selectedNode.name}</span>
        </span>
      )}

      {/* Controls on the right */}
      <div className="flex items-center gap-3 ml-auto">
        <label className="text-xs text-gray-500">Depth</label>
        <input
          type="number"
          min={1}
          max={10}
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
          className="w-14 bg-dt-bg border border-dt-border rounded px-2 py-1 text-xs font-mono text-gray-200"
        />
        <button
          onClick={() => simMutation.mutate()}
          disabled={!selectedNode || simMutation.isPending}
          className="flex items-center gap-1 bg-dt-danger hover:bg-red-700 disabled:opacity-40 text-white text-xs font-mono px-3 py-1.5 rounded transition-colors"
          title="Run disaster simulation"
        >
          <Zap size={12} /> Simulate
        </button>
        <button
          onClick={() => resetMutation.mutate()}
          disabled={!selectedNode || resetMutation.isPending}
          className="flex items-center gap-1 border border-dt-border hover:border-dt-accent text-gray-400 hover:text-dt-accent text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-40"
          title="Reset simulation state"
        >
          <RotateCcw size={12} /> Reset
        </button>
      </div>
    </div>
  )
}
