import { memo } from 'react'
import { X } from 'lucide-react'

function DeltaBadge({ a, b, unit = '', lowerIsBetter = true }) {
  if (a == null || b == null) return <span className="text-gray-500">—</span>
  const diff = b - a
  if (diff === 0) return <span className="text-gray-500">=</span>
  const better = lowerIsBetter ? diff < 0 : diff > 0
  const color = better ? 'text-dt-success' : 'text-dt-danger'
  const sign = diff > 0 ? '+' : ''
  return (
    <span className={`font-mono text-xs ${color}`}>
      {sign}{Number(diff.toFixed(1))}{unit}
    </span>
  )
}

function CompareRow({ label, valA, valB, unit = '', lowerIsBetter = true }) {
  return (
    <tr className="border-b border-dt-border hover:bg-slate-900/20">
      <td className="px-3 py-2 text-gray-400 text-xs">{label}</td>
      <td className="px-3 py-2 font-mono text-xs text-gray-200 text-right">
        {valA != null ? `${valA}${unit}` : '—'}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-gray-200 text-right">
        {valB != null ? `${valB}${unit}` : '—'}
      </td>
      <td className="px-3 py-2 text-right">
        <DeltaBadge a={valA} b={valB} unit={unit} lowerIsBetter={lowerIsBetter} />
      </td>
    </tr>
  )
}

function SimulationComparison({ simA, simB, labelA = 'Sim A', labelB = 'Sim B', onClose }) {
  if (!simA || !simB) return null

  const costA = simA.total_recovery_cost_usd
  const costB = simB.total_recovery_cost_usd

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-dt-surface border border-dt-border rounded-lg shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-dt-border sticky top-0 bg-dt-surface">
          <h2 className="text-sm font-mono font-bold text-gray-100 tracking-widest">
            SIMULATION COMPARISON
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Simulation labels */}
          <div className="grid grid-cols-2 gap-3">
            {[{ label: labelA, sim: simA }, { label: labelB, sim: simB }].map(({ label, sim }) => (
              <div key={label} className="bg-slate-900/30 rounded p-3">
                <div className="text-xs text-gray-500 font-mono mb-1">{label}</div>
                <div className="text-sm font-mono text-gray-100 truncate">
                  {sim.origin_node_id}
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  {sim.blast_radius?.length} nodes · max hop {sim.max_distance}
                </div>
              </div>
            ))}
          </div>

          {/* Comparison table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-dt-border">
                  <th className="text-left px-3 py-2 text-gray-500">Metric</th>
                  <th className="text-right px-3 py-2 text-gray-500">{labelA}</th>
                  <th className="text-right px-3 py-2 text-gray-500">{labelB}</th>
                  <th className="text-right px-3 py-2 text-gray-500">Delta</th>
                </tr>
              </thead>
              <tbody>
                <CompareRow
                  label="Affected nodes"
                  valA={simA.blast_radius?.length}
                  valB={simB.blast_radius?.length}
                  lowerIsBetter={true}
                />
                <CompareRow
                  label="Max propagation (hops)"
                  valA={simA.max_distance}
                  valB={simB.max_distance}
                  lowerIsBetter={true}
                />
                <CompareRow
                  label="Worst RTO"
                  valA={simA.worst_case_rto_minutes}
                  valB={simB.worst_case_rto_minutes}
                  unit=" min"
                  lowerIsBetter={true}
                />
                <CompareRow
                  label="Worst RPO"
                  valA={simA.worst_case_rpo_minutes}
                  valB={simB.worst_case_rpo_minutes}
                  unit=" min"
                  lowerIsBetter={true}
                />
                <CompareRow
                  label="Total recovery cost"
                  valA={costA != null ? Math.round(costA) : null}
                  valB={costB != null ? Math.round(costB) : null}
                  unit=" $"
                  lowerIsBetter={true}
                />
                <CompareRow
                  label="Simulation duration"
                  valA={simA.total_duration_ms}
                  valB={simB.total_duration_ms}
                  unit=" ms"
                  lowerIsBetter={true}
                />
              </tbody>
            </table>
          </div>

          {/* Blast radius diff */}
          <div>
            <h3 className="text-xs font-mono text-gray-400 mb-2">BLAST RADIUS OVERLAP</h3>
            {(() => {
              const idsA = new Set(simA.blast_radius?.map(n => n.id) ?? [])
              const idsB = new Set(simB.blast_radius?.map(n => n.id) ?? [])
              const common = [...idsA].filter(id => idsB.has(id))
              const onlyA = [...idsA].filter(id => !idsB.has(id))
              const onlyB = [...idsB].filter(id => !idsA.has(id))
              return (
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div className="bg-slate-900/30 rounded p-3">
                    <div className="text-gray-500 mb-1">Common</div>
                    <div className="font-mono text-dt-warning text-lg">{common.length}</div>
                    <div className="text-gray-600 mt-1 space-y-0.5">
                      {common.slice(0, 3).map(id => <div key={id} className="truncate">{id}</div>)}
                      {common.length > 3 && <div className="text-gray-600">+{common.length - 3} more</div>}
                    </div>
                  </div>
                  <div className="bg-slate-900/30 rounded p-3">
                    <div className="text-gray-500 mb-1">Only in {labelA}</div>
                    <div className="font-mono text-blue-400 text-lg">{onlyA.length}</div>
                    <div className="text-gray-600 mt-1 space-y-0.5">
                      {onlyA.slice(0, 3).map(id => <div key={id} className="truncate">{id}</div>)}
                      {onlyA.length > 3 && <div className="text-gray-600">+{onlyA.length - 3} more</div>}
                    </div>
                  </div>
                  <div className="bg-slate-900/30 rounded p-3">
                    <div className="text-gray-500 mb-1">Only in {labelB}</div>
                    <div className="font-mono text-purple-400 text-lg">{onlyB.length}</div>
                    <div className="text-gray-600 mt-1 space-y-0.5">
                      {onlyB.slice(0, 3).map(id => <div key={id} className="truncate">{id}</div>)}
                      {onlyB.length > 3 && <div className="text-gray-600">+{onlyB.length - 3} more</div>}
                    </div>
                  </div>
                </div>
              )
            })()}
          </div>
        </div>
      </div>
    </div>
  )
}

export default memo(SimulationComparison)
