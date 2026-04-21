import React, { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import * as client from '../api/client'

const CHAOS_SCENARIOS = ['terminate', 'network_loss', 'cpu_hog', 'disk_full', 'memory_pressure']

export default function ChaosDashboard({ topology }) {
  const [tab, setTab] = useState('list') // 'list' or 'new'
  const [selectedExperiment, setSelectedExperiment] = useState(null)
  const [nodeId, setNodeId] = useState('')
  const [scenario, setScenario] = useState('terminate')
  const [depth, setDepth] = useState(5)
  const [notes, setNotes] = useState('')
  const [actualRto, setActualRto] = useState('')
  const [actualNodes, setActualNodes] = useState([])
  const [actualNotes, setActualNotes] = useState('')

  // Fetch experiments list
  const { data: experiments, isLoading: expsLoading, refetch: refetchExps } = useQuery({
    queryKey: ['chaos_experiments'],
    queryFn: client.listChaosExperiments,
  })

  // Create experiment mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = { node_id: nodeId, scenario, depth, notes }
      return client.runChaosExperiment(payload)
    },
    onSuccess: () => {
      setNodeId('')
      setScenario('terminate')
      setDepth(5)
      setNotes('')
      setTab('list')
      refetchExps()
    },
  })

  // Submit actuals mutation
  const actualsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedExperiment) return
      const payload = {
        actual_rto_minutes: actualRto ? parseInt(actualRto) : null,
        actual_blast_radius: actualNodes,
        notes: actualNotes,
      }
      return client.submitChaosActuals(selectedExperiment.experiment_id, payload)
    },
    onSuccess: () => {
      setActualRto('')
      setActualNodes([])
      setActualNotes('')
      refetchExps()
    },
  })

  // Delete experiment mutation
  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      return client.deleteChaosExperiment(id)
    },
    onSuccess: () => {
      setSelectedExperiment(null)
      refetchExps()
    },
  })

  const allNodeIds = topology?.nodes?.map(n => n.id) || []

  const handleCreateExperiment = () => {
    if (!nodeId) return
    createMutation.mutate()
  }

  const handleSelectExperiment = (exp) => {
    setSelectedExperiment(exp)
    setActualRto('')
    setActualNodes([])
    setActualNotes('')
  }

  const handleToggleActualNode = (nodeId) => {
    if (actualNodes.includes(nodeId)) {
      setActualNodes(actualNodes.filter(n => n !== nodeId))
    } else {
      setActualNodes([...actualNodes, nodeId])
    }
  }

  const handleSubmitActuals = () => {
    actualsMutation.mutate()
  }

  const getResilienceColor = (score) => {
    if (score === null) return 'text-gray-400'
    if (score >= 0.8) return 'text-green-400'
    if (score >= 0.5) return 'text-yellow-400'
    return 'text-red-400'
  }

  if (tab === 'list') {
    return (
      <div className="flex flex-col h-full bg-dt-bg text-gray-100 overflow-hidden">
        <div className="shrink-0 p-6 border-b border-dt-border bg-dt-surface">
          <h2 className="text-2xl font-bold mb-4">Chaos Engineering</h2>
          <button
            onClick={() => setTab('new')}
            className="px-4 py-2 bg-dt-accent hover:bg-blue-600 text-white font-mono rounded text-sm"
          >
            New Experiment
          </button>
        </div>

        {expsLoading ? (
          <div className="flex items-center justify-center h-full text-gray-400">Loading…</div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* Experiments List */}
            <div className="w-80 border-r border-dt-border overflow-y-auto">
              <div className="divide-y divide-dt-border">
                {experiments?.map(exp => (
                  <div
                    key={exp.experiment_id}
                    onClick={() => handleSelectExperiment(exp)}
                    className={`p-4 cursor-pointer hover:bg-dt-surface/50 ${
                      selectedExperiment?.experiment_id === exp.experiment_id ? 'bg-dt-surface border-l-2 border-dt-accent' : ''
                    }`}
                  >
                    <div className="text-sm font-mono font-bold mb-1">{exp.node_name}</div>
                    <div className="text-xs text-gray-400 mb-2">
                      <span className="inline-block bg-gray-700 px-2 py-1 rounded">{exp.scenario}</span>
                    </div>
                    <div className={`text-sm font-bold ${getResilienceColor(exp.resilience_score)}`}>
                      {exp.resilience_score ? `${(exp.resilience_score * 100).toFixed(0)}%` : 'Pending'}
                    </div>
                    <div className="text-xs text-gray-500 mt-2">{exp.created_at.split('T')[0]}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Experiment Detail */}
            {selectedExperiment ? (
              <div className="flex-1 overflow-y-auto p-6">
                <h3 className="text-xl font-bold mb-4">{selectedExperiment.node_name}</h3>

                <div className="space-y-6">
                  {/* Simulation Results */}
                  <div className="bg-dt-surface border border-dt-border rounded p-4">
                    <h4 className="font-bold text-sm mb-3">Predicted Impact</h4>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <div className="text-xs text-gray-400">Affected Nodes</div>
                        <div className="text-xl font-bold">{selectedExperiment.simulation.total_affected}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">RTO</div>
                        <div className="text-xl font-bold">
                          {selectedExperiment.simulation.worst_case_rto_minutes ?? '—'} min
                        </div>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="text-xs text-gray-400 font-mono mb-2">Nodes in Blast Radius</div>
                      <div className="space-y-1">
                        {selectedExperiment.simulation.affected_nodes?.slice(0, 5).map(n => (
                          <div key={n.id} className="text-xs text-gray-300">
                            • {n.name} (distance: {n.distance})
                          </div>
                        ))}
                        {selectedExperiment.simulation.affected_nodes?.length > 5 && (
                          <div className="text-xs text-gray-500">
                            +{selectedExperiment.simulation.affected_nodes.length - 5} more
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Resilience Score */}
                  {selectedExperiment.resilience_score !== null && (
                    <div className="bg-dt-surface border border-dt-border rounded p-4">
                      <h4 className="font-bold text-sm mb-3">Resilience Score</h4>
                      <div className={`text-4xl font-bold ${getResilienceColor(selectedExperiment.resilience_score)}`}>
                        {(selectedExperiment.resilience_score * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs text-gray-400 mt-2">
                        {selectedExperiment.resilience_score >= 0.8 && 'System performed well'}
                        {selectedExperiment.resilience_score >= 0.5 && selectedExperiment.resilience_score < 0.8 && 'System had moderate issues'}
                        {selectedExperiment.resilience_score < 0.5 && 'System failed to meet expectations'}
                      </div>
                    </div>
                  )}

                  {/* Record Actuals (if not yet recorded) */}
                  {selectedExperiment.resilience_score === null && (
                    <div className="bg-dt-surface border border-dt-border rounded p-4">
                      <h4 className="font-bold text-sm mb-3">Record Actual Results</h4>

                      <div className="space-y-4">
                        <div>
                          <label className="block text-xs text-gray-400 font-mono mb-2">Actual RTO (minutes)</label>
                          <input
                            type="number"
                            value={actualRto}
                            onChange={e => setActualRto(e.target.value)}
                            className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
                          />
                        </div>

                        <div>
                          <label className="block text-xs text-gray-400 font-mono mb-2">Nodes That Failed</label>
                          <div className="space-y-2">
                            {allNodeIds.map(nid => (
                              <label key={nid} className="flex items-center gap-2 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={actualNodes.includes(nid)}
                                  onChange={() => handleToggleActualNode(nid)}
                                  className="w-3 h-3"
                                />
                                <span className="text-xs text-gray-300">{nid}</span>
                              </label>
                            ))}
                          </div>
                        </div>

                        <div>
                          <label className="block text-xs text-gray-400 font-mono mb-2">Notes</label>
                          <input
                            type="text"
                            value={actualNotes}
                            onChange={e => setActualNotes(e.target.value)}
                            placeholder="Observations during test…"
                            className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-sm text-gray-100"
                          />
                        </div>

                        <button
                          onClick={handleSubmitActuals}
                          disabled={actualsMutation.isPending}
                          className="w-full px-3 py-2 bg-dt-accent hover:bg-blue-600 text-white font-mono rounded text-sm disabled:opacity-50"
                        >
                          {actualsMutation.isPending ? 'Submitting…' : 'Submit Actual Results'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Delete Button */}
                  <button
                    onClick={() => deleteMutation.mutate(selectedExperiment.experiment_id)}
                    className="w-full px-3 py-2 bg-red-900/20 hover:bg-red-900/40 text-red-400 font-mono rounded text-sm border border-red-700"
                  >
                    Delete Experiment
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-500">
                <div className="text-center">
                  <div className="font-mono text-sm">Select an experiment to view details</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // New Experiment Tab
  return (
    <div className="flex flex-col h-full bg-dt-bg text-gray-100 p-6 overflow-y-auto">
      <h2 className="text-2xl font-bold mb-6">Create New Chaos Experiment</h2>

      <div className="max-w-xl space-y-6">
        {/* Node Selection */}
        <div>
          <label className="block text-sm font-mono text-gray-400 mb-2">Target Node</label>
          <select
            value={nodeId}
            onChange={e => setNodeId(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
          >
            <option value="">Select a node…</option>
            {allNodeIds.map(id => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
        </div>

        {/* Scenario Selection */}
        <div>
          <label className="block text-sm font-mono text-gray-400 mb-3">Chaos Scenario</label>
          <div className="space-y-2">
            {CHAOS_SCENARIOS.map(scen => (
              <label key={scen} className="flex items-center gap-3 cursor-pointer p-3 bg-gray-800 rounded hover:bg-gray-700">
                <input
                  type="radio"
                  name="scenario"
                  value={scen}
                  checked={scenario === scen}
                  onChange={e => setScenario(e.target.value)}
                  className="w-4 h-4"
                />
                <div>
                  <div className="text-sm font-mono font-bold capitalize">{scen.replace('_', ' ')}</div>
                  <div className="text-xs text-gray-400">
                    {scen === 'terminate' && 'Node completely removed from system'}
                    {scen === 'network_loss' && 'All network connections severed'}
                    {scen === 'cpu_hog' && 'High CPU usage, degraded performance'}
                    {scen === 'disk_full' && 'Disk space exhausted'}
                    {scen === 'memory_pressure' && 'Memory exhaustion, slowdown'}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Depth */}
        <div>
          <label className="block text-sm font-mono text-gray-400 mb-2">Simulation Depth</label>
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

        {/* Notes */}
        <div>
          <label className="block text-sm font-mono text-gray-400 mb-2">Notes</label>
          <input
            type="text"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Optional notes about this experiment"
            className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
          />
        </div>

        {/* Submit */}
        <button
          onClick={handleCreateExperiment}
          disabled={createMutation.isPending || !nodeId}
          className="w-full px-4 py-3 bg-dt-accent hover:bg-blue-600 text-white font-bold rounded disabled:opacity-50"
        >
          {createMutation.isPending ? 'Running Experiment…' : 'Run Chaos Experiment'}
        </button>

        {createMutation.isError && (
          <div className="p-3 bg-red-900/20 border border-red-700 rounded text-red-400 text-sm font-mono">
            Error: {createMutation.error?.message}
          </div>
        )}

        {/* Back Button */}
        <button
          onClick={() => setTab('list')}
          className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white font-mono rounded"
        >
          Back to List
        </button>
      </div>
    </div>
  )
}
