import { useQuery } from '@tanstack/react-query'
import { Activity, Database, AlertCircle, CheckCircle } from 'lucide-react'
import { getNodeHealth, getReplicationLag } from '../api/client.js'

const STATUS_ICON = {
  healthy:  <CheckCircle size={14} className="text-dt-success" />,
  degraded: <AlertCircle size={14} className="text-dt-warning" />,
  failed:   <AlertCircle size={14} className="text-dt-danger" />,
  unknown:  <AlertCircle size={14} className="text-gray-500" />,
}

function MetricRow({ label, value, unit = '' }) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-dt-border/40">
      <span className="text-xs text-gray-500 font-mono">{label}</span>
      <span className="text-xs text-gray-200 font-mono">{value ?? '—'}{unit}</span>
    </div>
  )
}

export default function MetricsSidebar({ selectedNode }) {
  const { data: health } = useQuery({
    queryKey: ['health', selectedNode?.id],
    queryFn: () => getNodeHealth(selectedNode.id),
    enabled: !!selectedNode,
    refetchInterval: 10_000,
  })

  const { data: lagData } = useQuery({
    queryKey: ['replication-lag'],
    queryFn: getReplicationLag,
    refetchInterval: 15_000,
  })

  return (
    <aside className="w-64 bg-dt-surface border-l border-dt-border flex flex-col p-4 gap-4 overflow-y-auto shrink-0">
      <div className="flex items-center gap-2 text-xs font-mono text-gray-400 uppercase tracking-widest">
        <Activity size={12} className="text-dt-accent" /> Live Metrics
      </div>

      {selectedNode ? (
        <section>
          <div className="flex items-center gap-2 mb-2">
            {STATUS_ICON[health?.status ?? 'unknown']}
            <span className="text-sm font-mono text-gray-100 truncate">{selectedNode.name}</span>
          </div>
          <MetricRow label="Status"   value={health?.status ?? '—'} />
          <MetricRow label="CPU"      value={health?.cpu_percent?.toFixed(1) ?? '—'} unit="%" />
          <MetricRow label="Memory"   value={health?.memory_percent?.toFixed(1) ?? '—'} unit="%" />
          <MetricRow label="Errors/s" value={health?.error_rate?.toFixed(3) ?? '—'} />
          <MetricRow label="RTO"      value={selectedNode.rto_minutes} unit=" min" />
          <MetricRow label="RPO"      value={selectedNode.rpo_minutes} unit=" min" />
        </section>
      ) : (
        <p className="text-xs text-gray-600 font-mono">Select a node to see metrics.</p>
      )}

      <div className="flex items-center gap-2 text-xs font-mono text-gray-400 uppercase tracking-widest mt-2">
        <Database size={12} className="text-dt-accent" /> Replication
      </div>
      {lagData?.lag_seconds != null ? (
        <div>
          <MetricRow label="Lag" value={lagData.lag_seconds.toFixed(2)} unit="s" />
          {lagData.lag_seconds > 5 && (
            <p className="text-xs text-dt-warning font-mono mt-1">⚠ Replication lag elevated</p>
          )}
        </div>
      ) : (
        <p className="text-xs text-gray-600 font-mono">No replication data.</p>
      )}
    </aside>
  )
}
