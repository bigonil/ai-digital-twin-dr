import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import TopologyViewer from './components/TopologyViewer.jsx'
import DisasterPanel from './components/DisasterPanel.jsx'
import MetricsSidebar from './components/MetricsSidebar.jsx'
import { getTopology } from './api/client.js'

// Error Boundary Fallback
function ErrorFallback({error}) {
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
  const [selectedNode, setSelectedNode] = useState(null)
  const [blastRadius, setBlastRadius] = useState([])
  const [simulationTime, setSimulationTime] = useState(null)

  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology'],
    queryFn: getTopology,
  })

  return (
    <ErrorBoundary>
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
        {/* Topology Viewer */}
        <main className="flex-1 relative">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 font-mono text-sm">
              Connecting to graph database…
            </div>
          ) : (
            <TopologyViewer
              topology={topology}
              selectedNode={selectedNode}
              onNodeSelect={setSelectedNode}
            />
          )}
        </main>

        {/* Right sidebar — metrics */}
        <MetricsSidebar selectedNode={selectedNode} />
      </div>

      {/* Bottom panel — disaster sim */}
      <DisasterPanel
        selectedNode={selectedNode}
        topology={topology}
        onSimulationResult={setBlastRadius}
        onReset={() => {
          setBlastRadius([])
          setSimulationTime(null)
        }}
        onSimulationTimeChange={setSimulationTime}
      />
    </div>
    </ErrorBoundary>
  )
}
