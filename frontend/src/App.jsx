import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Graph3D from './components/Graph3D.jsx'
import DisasterPanel from './components/DisasterPanel.jsx'
import MetricsSidebar from './components/MetricsSidebar.jsx'
import { getTopology } from './api/client.js'

export default function App() {
  const [selectedNode, setSelectedNode] = useState(null)
  const [blastRadius, setBlastRadius] = useState([])
  const [simulationTime, setSimulationTime] = useState(null)

  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology'],
    queryFn: getTopology,
  })

  return (
    <div className="flex flex-col h-screen bg-dt-bg text-gray-100 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 bg-dt-surface border-b border-dt-border shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-dt-accent animate-pulse" />
          <span className="font-mono font-bold text-dt-accent tracking-widest text-sm uppercase">
            Digital Twin DR Platform
          </span>
        </div>
        <div className="text-xs text-gray-500 font-mono">
          {topology ? `${topology.nodes?.length ?? 0} nodes · ${topology.edges?.length ?? 0} edges` : 'Loading…'}
        </div>
      </header>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* 3D Graph — takes remaining space */}
        <main className="flex-1 relative">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 font-mono text-sm">
              Connecting to graph database…
            </div>
          ) : (
            <Graph3D
              topology={topology}
              blastRadius={blastRadius}
              onNodeClick={setSelectedNode}
              simulationTime={simulationTime}
            />
          )}
        </main>

        {/* Right sidebar — metrics */}
        <MetricsSidebar selectedNode={selectedNode} />
      </div>

      {/* Bottom panel — disaster sim */}
      <DisasterPanel
        selectedNode={selectedNode}
        onSimulationResult={setBlastRadius}
        onReset={() => {
          setBlastRadius([])
          setSimulationTime(null)
        }}
        onSimulationTimeChange={setSimulationTime}
      />
    </div>
  )
}
