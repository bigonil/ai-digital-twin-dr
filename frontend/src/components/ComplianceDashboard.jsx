import React, { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import * as client from '../api/client'

export default function ComplianceDashboard() {
  const [filterStatus, setFilterStatus] = useState('all')

  // Fetch current report
  const { data: report, isLoading: reportLoading, refetch } = useQuery({
    queryKey: ['compliance_report'],
    queryFn: client.getComplianceReport,
    enabled: false, // Don't auto-fetch initially
  })

  // Run audit mutation
  const auditMutation = useMutation({
    mutationFn: async () => {
      const result = await client.runComplianceAudit()
      return result
    },
    onSuccess: () => {
      refetch()
    },
  })

  // Download mutation
  const downloadMutation = useMutation({
    mutationFn: client.downloadComplianceReport,
  })

  const handleRunAudit = () => {
    auditMutation.mutate()
  }

  const handleDownload = () => {
    downloadMutation.mutate()
  }

  if (reportLoading || auditMutation.isPending) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-400 font-mono">Running compliance audit…</div>
      </div>
    )
  }

  if (auditMutation.isError) {
    return (
      <div className="p-6 text-red-400 font-mono text-sm">
        Error: {auditMutation.error?.message}
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-100 mb-2">Compliance & Testing</h2>
          <p className="text-gray-400 text-sm">Run a full RTO/RPO compliance audit on all nodes</p>
        </div>
        <button
          onClick={handleRunAudit}
          disabled={auditMutation.isPending}
          className="px-6 py-3 bg-dt-accent hover:bg-blue-600 text-white font-mono rounded text-sm disabled:opacity-50"
        >
          {auditMutation.isPending ? 'Auditing…' : 'Run Full Audit'}
        </button>
      </div>
    )
  }

  // Filter results
  const filtered = report.results.filter(r => {
    if (filterStatus === 'all') return true
    if (filterStatus === 'pass') return r.rto_status === 'pass' && r.rpo_status === 'pass'
    if (filterStatus === 'warning') return r.rto_status === 'warning' || r.rpo_status === 'warning'
    if (filterStatus === 'fail') return r.rto_status === 'fail' || r.rpo_status === 'fail'
    return true
  })

  const getStatusColor = (status) => {
    if (status === 'pass') return 'text-green-400'
    if (status === 'fail') return 'text-red-400'
    if (status === 'warning') return 'text-yellow-400'
    return 'text-gray-400'
  }

  const getStatusBg = (status) => {
    if (status === 'pass') return 'bg-green-900/20'
    if (status === 'fail') return 'bg-red-900/20'
    if (status === 'warning') return 'bg-yellow-900/20'
    return 'bg-gray-900/20'
  }

  return (
    <div className="flex flex-col h-full bg-dt-bg text-gray-100 overflow-hidden">
      {/* Header */}
      <div className="shrink-0 p-6 border-b border-dt-border bg-dt-surface">
        <h2 className="text-2xl font-bold mb-2">Compliance & Testing</h2>
        <p className="text-gray-400 text-sm mb-4">Generated: {report.generated_at.split('T')[0]}</p>

        {/* Summary Stat Boxes */}
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div className="bg-green-900/20 border border-green-700 rounded p-3">
            <div className="text-green-400 text-2xl font-bold">{report.pass_count}</div>
            <div className="text-green-400 text-xs font-mono">PASS</div>
          </div>
          <div className="bg-red-900/20 border border-red-700 rounded p-3">
            <div className="text-red-400 text-2xl font-bold">{report.fail_count}</div>
            <div className="text-red-400 text-xs font-mono">FAIL</div>
          </div>
          <div className="bg-yellow-900/20 border border-yellow-700 rounded p-3">
            <div className="text-yellow-400 text-2xl font-bold">{report.warning_count}</div>
            <div className="text-yellow-400 text-xs font-mono">WARNING</div>
          </div>
          <div className="bg-gray-900/20 border border-gray-700 rounded p-3">
            <div className="text-gray-400 text-2xl font-bold">{report.skipped_count}</div>
            <div className="text-gray-400 text-xs font-mono">SKIPPED</div>
          </div>
        </div>

        {/* Buttons */}
        <div className="flex gap-3">
          <button
            onClick={handleRunAudit}
            className="px-4 py-2 bg-dt-accent hover:bg-blue-600 text-white font-mono rounded text-sm"
          >
            Re-run Audit
          </button>
          <button
            onClick={handleDownload}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white font-mono rounded text-sm"
          >
            Download JSON
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="shrink-0 flex gap-4 px-6 py-3 border-b border-dt-border bg-dt-surface/50">
        {['all', 'pass', 'warning', 'fail'].map(status => (
          <button
            key={status}
            onClick={() => setFilterStatus(status)}
            className={`text-sm font-mono px-3 py-1 rounded ${
              filterStatus === status
                ? 'bg-dt-accent text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {status.toUpperCase()} ({report.results.filter(r => {
              if (status === 'all') return true
              if (status === 'pass') return r.rto_status === 'pass' && r.rpo_status === 'pass'
              if (status === 'warning') return r.rto_status === 'warning' || r.rpo_status === 'warning'
              if (status === 'fail') return r.rto_status === 'fail' || r.rpo_status === 'fail'
              return false
            }).length})
          </button>
        ))}
      </div>

      {/* Results Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm font-mono">
          <thead className="sticky top-0 bg-dt-surface border-b border-dt-border">
            <tr className="text-gray-400 text-xs uppercase">
              <th className="text-left px-6 py-3">Node</th>
              <th className="text-left px-6 py-3">Type</th>
              <th className="text-left px-6 py-3">RTO (min)</th>
              <th className="text-left px-6 py-3">RPO (min)</th>
              <th className="text-center px-6 py-3">RTO Status</th>
              <th className="text-center px-6 py-3">RPO Status</th>
              <th className="text-right px-6 py-3">Blast Radius</th>
              <th className="text-right px-6 py-3">Worst RTO</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dt-border">
            {filtered.map(result => (
              <tr key={result.node_id} className="hover:bg-dt-surface/50">
                <td className="px-6 py-3 text-gray-300">{result.node_name}</td>
                <td className="px-6 py-3 text-gray-400 text-xs">{result.node_type}</td>
                <td className="px-6 py-3 text-gray-300">{result.rto_minutes ?? '—'}</td>
                <td className="px-6 py-3 text-gray-300">{result.rpo_minutes ?? '—'}</td>
                <td className={`px-6 py-3 text-center ${getStatusColor(result.rto_status)}`}>
                  <span className={`px-2 py-1 rounded text-xs ${getStatusBg(result.rto_status)}`}>
                    {result.rto_status}
                  </span>
                </td>
                <td className={`px-6 py-3 text-center ${getStatusColor(result.rpo_status)}`}>
                  <span className={`px-2 py-1 rounded text-xs ${getStatusBg(result.rpo_status)}`}>
                    {result.rpo_status}
                  </span>
                </td>
                <td className="px-6 py-3 text-right text-gray-300">{result.blast_radius_size}</td>
                <td className="px-6 py-3 text-right text-gray-300">{result.worst_case_rto ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
