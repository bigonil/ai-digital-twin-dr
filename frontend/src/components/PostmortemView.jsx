import React, { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import * as client from '../api/client'

export default function PostmortemView({ topology }) {
  const [tab, setTab] = useState('new') // 'new' or 'history'
  const [title, setTitle] = useState('')
  const [occurredAt, setOccurredAt] = useState('')
  const [originNode, setOriginNode] = useState('')
  const [failedNodes, setFailedNodes] = useState({})
  const [actualRto, setActualRto] = useState('')
  const [actualRpo, setActualRpo] = useState('')
  const [referenceNode, setReferenceNode] = useState('')
  const [referenceDepth, setReferenceDepth] = useState(5)
  const [result, setResult] = useState(null)

  // Fetch postmortem history
  const { data: reports, isLoading: reportsLoading } = useQuery({
    queryKey: ['postmortem_reports'],
    queryFn: client.listPostmortems,
    enabled: tab === 'history',
  })

  // Create postmortem mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        title,
        occurred_at: occurredAt,
        actual_origin_node_id: originNode,
        actually_failed_node_ids: Object.keys(failedNodes).filter(k => failedNodes[k]),
        actual_rto_minutes: parseInt(actualRto),
        actual_rpo_minutes: actualRpo ? parseInt(actualRpo) : null,
        reference_simulation_node_id: referenceNode || null,
        reference_simulation_depth: referenceDepth,
      }
      const res = await client.createPostmortem(payload)
      setResult(res)
      return res
    },
    onError: (error) => {
      const message = error.userMessage || error.message || 'Failed to create postmortem report'
      alert(`❌ ${message}`)
      console.error('Create postmortem error:', error)
    },
  })

  const allNodeIds = topology?.nodes?.map(n => n.id) || []

  const handleToggleNode = (nodeId) => {
    setFailedNodes(prev => ({
      ...prev,
      [nodeId]: !prev[nodeId],
    }))
  }

  const handleSubmit = () => {
    if (!title || !occurredAt || !originNode || Object.values(failedNodes).every(v => !v)) {
      return
    }
    createMutation.mutate()
  }

  const formatAccuracy = (score) => {
    if (score >= 0.9) return { text: 'Excellent', color: 'text-green-400' }
    if (score >= 0.7) return { text: 'Good', color: 'text-yellow-400' }
    return { text: 'Poor', color: 'text-red-400' }
  }

  if (tab === 'history') {
    return (
      <div className="flex flex-col h-full bg-dt-bg text-gray-100 overflow-hidden">
        <div className="shrink-0 p-6 border-b border-dt-border bg-dt-surface">
          <h2 className="text-2xl font-bold mb-4">Postmortem History</h2>
          <div className="flex gap-2">
            <button
              onClick={() => setTab('new')}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-mono"
            >
              New Postmortem
            </button>
            <button
              onClick={() => setTab('history')}
              className="px-4 py-2 bg-dt-accent text-white rounded text-sm font-mono"
            >
              History
            </button>
          </div>
        </div>

        {reportsLoading ? (
          <div className="flex items-center justify-center h-full text-gray-400">Loading…</div>
        ) : (
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm font-mono">
              <thead className="sticky top-0 bg-dt-surface border-b border-dt-border">
                <tr className="text-gray-400 text-xs uppercase">
                  <th className="text-left px-6 py-3">Title</th>
                  <th className="text-left px-6 py-3">Date</th>
                  <th className="text-center px-6 py-3">Accuracy</th>
                  <th className="text-right px-6 py-3">RTO Delta</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dt-border">
                {reports?.map(report => {
                  const acc = formatAccuracy(report.prediction_accuracy.accuracy_score)
                  return (
                    <tr key={report.report_id} className="hover:bg-dt-surface/50">
                      <td className="px-6 py-3">{report.title}</td>
                      <td className="px-6 py-3 text-gray-400">{report.occurred_at.split('T')[0]}</td>
                      <td className={`px-6 py-3 text-center ${acc.color}`}>
                        {(report.prediction_accuracy.accuracy_score * 100).toFixed(0)}% ({acc.text})
                      </td>
                      <td className="px-6 py-3 text-right">
                        {report.prediction_accuracy.rto_delta_minutes > 0 ? '↑' : '↓'} {Math.abs(report.prediction_accuracy.rto_delta_minutes)}m
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-dt-bg text-gray-100 overflow-y-auto p-6">
      <h2 className="text-2xl font-bold mb-4">Create Postmortem Report</h2>

      <div className="max-w-2xl space-y-6">
        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setTab('new')}
            className="px-4 py-2 bg-dt-accent text-white rounded text-sm font-mono"
          >
            New Postmortem
          </button>
          <button
            onClick={() => setTab('history')}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-mono"
          >
            History
          </button>
        </div>

        {/* Form */}
        <div className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-mono text-gray-400 mb-2">Incident Title</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g., Database failover on 2026-04-21"
              className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
            />
          </div>

          {/* Occurred At */}
          <div>
            <label className="block text-sm font-mono text-gray-400 mb-2">Occurred At (ISO timestamp)</label>
            <input
              type="text"
              value={occurredAt}
              onChange={e => setOccurredAt(e.target.value)}
              placeholder="2026-04-21T15:30:00Z"
              className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
            />
          </div>

          {/* Origin Node */}
          <div>
            <label className="block text-sm font-mono text-gray-400 mb-2">Origin Node</label>
            <select
              value={originNode}
              onChange={e => setOriginNode(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
            >
              <option value="">Select origin node…</option>
              {allNodeIds.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </div>

          {/* Failed Nodes */}
          <div>
            <label className="block text-sm font-mono text-gray-400 mb-2">Failed Nodes</label>
            <div className="grid grid-cols-2 gap-3">
              {allNodeIds.map(nodeId => (
                <label key={nodeId} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={failedNodes[nodeId] || false}
                    onChange={() => handleToggleNode(nodeId)}
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-300">{nodeId}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Actual RTO/RPO */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-mono text-gray-400 mb-2">Actual RTO (minutes)</label>
              <input
                type="number"
                value={actualRto}
                onChange={e => setActualRto(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-mono text-gray-400 mb-2">Actual RPO (minutes, optional)</label>
              <input
                type="number"
                value={actualRpo}
                onChange={e => setActualRpo(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100"
              />
            </div>
          </div>

          {/* Reference Simulation */}
          <div>
            <label className="block text-sm font-mono text-gray-400 mb-2">Reference Simulation Node (optional)</label>
            <select
              value={referenceNode}
              onChange={e => setReferenceNode(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-dt-border rounded text-gray-100 mb-3"
            >
              <option value="">None (compare with empty set)</option>
              {allNodeIds.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            {referenceNode && (
              <div>
                <label className="block text-sm font-mono text-gray-400 mb-2">Depth</label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={referenceDepth}
                  onChange={e => setReferenceDepth(parseInt(e.target.value))}
                  className="w-full"
                />
                <div className="text-xs text-gray-500 mt-1">{referenceDepth}</div>
              </div>
            )}
          </div>

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={createMutation.isPending || !title || !occurredAt || !originNode}
            className="w-full px-4 py-3 bg-dt-accent hover:bg-blue-600 text-white font-bold rounded disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating…' : 'Create Report'}
          </button>

          {createMutation.isError && (
            <div className="p-3 bg-red-900/20 border border-red-700 rounded text-red-400 text-sm font-mono">
              Error: {createMutation.error?.message}
            </div>
          )}
        </div>

        {/* Results */}
        {result && (
          <div className="p-6 bg-dt-surface border border-dt-border rounded">
            <h3 className="font-bold text-lg mb-4">Report Generated</h3>
            <div className="space-y-4">
              <div>
                <div className="text-xs text-gray-400 font-mono mb-1">Accuracy Score</div>
                <div className={`text-3xl font-bold ${formatAccuracy(result.prediction_accuracy.accuracy_score).color}`}>
                  {(result.prediction_accuracy.accuracy_score * 100).toFixed(1)}%
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-xs text-gray-400">Precision</div>
                  <div className="text-xl font-bold text-gray-100">
                    {(result.prediction_accuracy.precision * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">Recall</div>
                  <div className="text-xl font-bold text-gray-100">
                    {(result.prediction_accuracy.recall * 100).toFixed(0)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400">RTO Delta</div>
                  <div className="text-xl font-bold text-gray-100">
                    {result.prediction_accuracy.rto_delta_minutes}m
                  </div>
                </div>
              </div>

              <div className="border-t border-dt-border pt-4">
                <div className="text-xs text-gray-400 font-mono mb-2">True Positives (predicted & actual)</div>
                <div className="text-sm text-gray-300 mb-3">
                  {result.prediction_accuracy.true_positives.join(', ') || '—'}
                </div>

                <div className="text-xs text-gray-400 font-mono mb-2">False Positives (predicted but not actual)</div>
                <div className="text-sm text-yellow-400 mb-3">
                  {result.prediction_accuracy.false_positives.join(', ') || 'None (good!)'}
                </div>

                <div className="text-xs text-gray-400 font-mono mb-2">False Negatives (missed predictions)</div>
                <div className="text-sm text-red-400 mb-3">
                  {result.prediction_accuracy.false_negatives.join(', ') || 'None (perfect!)'}
                </div>
              </div>

              <div className="border-t border-dt-border pt-4">
                <div className="text-xs text-gray-400 font-mono mb-2">Recommendations</div>
                <ul className="space-y-2">
                  {result.recommendations.map((rec, idx) => (
                    <li key={idx} className="text-sm text-gray-300">• {rec}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
