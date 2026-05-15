import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import TopologyViewer from './components/TopologyViewer.jsx'
import InfrastructureMap from './components/InfrastructureMap.jsx'
import MetricsDashboard from './components/MetricsDashboard.jsx'
import DisasterPanel from './components/DisasterPanel.jsx'
import SimulationTimeline from './components/SimulationTimeline.jsx'
import SimulationReport from './components/SimulationReport.jsx'
import ComplianceDashboard from './components/ComplianceDashboard.jsx'
import ArchitecturePlanner from './components/ArchitecturePlanner.jsx'
import PostmortemView from './components/PostmortemView.jsx'
import ChaosDashboard from './components/ChaosDashboard.jsx'
import { getTopology } from './api/client.js'

// Error Boundary Fallback
function ErrorFallback({ error }) {
  return (
    <div className="flex items-center justify-center h-screen bg-dt-bg text-center px-8">
      <div>
        <h1 className="text-2xl font-bold text-dt-danger mb-4">Something went wrong</h1>
        <p className="text-gray-400 font-mono text-sm mb-6">{error?.message || 'Unknown error'}</p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-dt-accent hover:bg-blue-600 text-white rounded font-mono text-sm"
        >
          Reload Page
        </button>
      </div>
    </div>
  )
}

// Simple Error Boundary Class Component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} />
    }
    return this.props.children
  }
}

export default function App() {
  // State management
  const [activeView, setActiveView] = useState('simulator')
  const [selectedNode, setSelectedNode] = useState(null)
  const [simulationResult, setSimulationResult] = useState(null)
  const [simulationTime, setSimulationTime] = useState(0)

  // Derived state
  const isSimulationDone = simulationResult && simulationTime >= (simulationResult.total_duration_ms - 50)

  // Fetch topology
  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology'],
    queryFn: getTopology,
  })

  // Handlers
  const handleSimulation = (result) => {
    setSimulationResult(result)
    setSimulationTime(0)
  }

  const handleReset = () => {
    setSimulationResult(null)
    setSimulationTime(0)
  }

  const handleTimeChange = (ms) => {
    setSimulationTime(ms)
  }

  return (
    <ErrorBoundary>
      <div className="flex flex-col h-screen bg-dt-bg text-gray-100 overflow-hidden">
        {/* Header */}
        <header className="flex flex-col bg-dt-surface border-b border-dt-border shrink-0">
          <div className="flex items-center justify-between px-6 py-3">
            <div className="flex items-center gap-3">
              <span className="text-2xl" title="Athena - Predictive Resilience Engine">🔮</span>
              <span className="font-mono font-bold text-dt-accent tracking-widest text-sm uppercase">
                Athena — Predictive Resilience Engine
              </span>
            </div>
            <div className="text-xs text-gray-500 font-mono">
              {topology ? `${topology.nodes?.length ?? 0} nodes · ${topology.edges?.length ?? 0} edges` : 'Loading…'}
            </div>
          </div>

          {/* Tabs Navigation */}
          <div className="flex gap-1 px-6 py-2 border-t border-dt-border">
            {['simulator', 'compliance', 'whatif', 'postmortem', 'chaos'].map(view => (
              <button
                key={view}
                onClick={() => setActiveView(view)}
                className={`px-4 py-2 text-sm font-mono rounded ${
                  activeView === view
                    ? 'bg-dt-accent text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {view === 'simulator' && 'DR Simulator'}
                {view === 'compliance' && 'Compliance'}
                {view === 'whatif' && 'What-If'}
                {view === 'postmortem' && 'Postmortem'}
                {view === 'chaos' && 'Chaos'}
              </button>
            ))}
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex flex-1 overflow-hidden">
          {/* DR Simulator View (3-column layout) */}
          {activeView === 'simulator' && (
            <>
              {/* Column A: Topology Viewer (left sidebar, fixed width) */}
              <aside className="w-56 shrink-0 overflow-y-auto border-r border-dt-border">
                {isLoading ? (
                  <div className="flex items-center justify-center h-full text-gray-500 font-mono text-sm">
                    Connecting…
                  </div>
                ) : (
                  <TopologyViewer
                    topology={topology}
                    selectedNode={selectedNode}
                    onNodeSelect={setSelectedNode}
                  />
                )}
              </aside>

              {/* Column B: Infrastructure Map (center, flex-1) */}
              <main className="flex-1 overflow-hidden flex flex-col">
                <InfrastructureMap
                  topology={topology}
                  simulationResult={simulationResult}
                  simulationTime={simulationTime}
                  selectedNode={selectedNode}
                  onNodeSelect={setSelectedNode}
                />

                {/* Row 3: Simulation Controls */}
                <DisasterPanel
                  selectedNode={selectedNode}
                  onSimulationResult={handleSimulation}
                  onReset={handleReset}
                />

                {/* Row 4: Timeline (conditional) */}
                {simulationResult && (
                  <div className="shrink-0 bg-dt-surface border-t border-dt-border h-20">
                    <SimulationTimeline simulationResult={simulationResult} onTimeChange={handleTimeChange} />
                  </div>
                )}

                {/* Row 5: Report (conditional) */}
                {isSimulationDone && <SimulationReport simulationResult={simulationResult} topology={topology} />}
              </main>

              {/* Column C: Metrics Dashboard (right sidebar, fixed width) */}
              <MetricsDashboard selectedNode={selectedNode} topology={topology} />
            </>
          )}

          {/* Feature Views */}
          {activeView === 'compliance' && <ComplianceDashboard />}
          {activeView === 'whatif' && <ArchitecturePlanner topology={topology} />}
          {activeView === 'postmortem' && <PostmortemView topology={topology} />}
          {activeView === 'chaos' && <ChaosDashboard topology={topology} />}
        </div>
      </div>
    </ErrorBoundary>
  )
}
