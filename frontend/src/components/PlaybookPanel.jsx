/**
 * PlaybookPanel.jsx
 * Displays an LLM-generated recovery runbook for a selected node.
 */
import { memo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { BookOpen, RefreshCw, Clock, User, Terminal, ChevronDown, ChevronRight, Zap } from 'lucide-react'
import { generatePlaybook } from '../api/client.js'

function StepCard({ step, isExpanded, onToggle }) {
  const ownerColors = {
    DBA: 'text-purple-400 bg-purple-900/20',
    SRE: 'text-blue-400 bg-blue-900/20',
    'on-call': 'text-yellow-400 bg-yellow-900/20',
  }
  const ownerStyle = ownerColors[step.owner] || 'text-gray-400 bg-gray-800'

  return (
    <div className="border border-dt-border rounded mb-2 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-dt-accent/20 text-dt-accent text-xs font-bold flex items-center justify-center">
          {step.step}
        </span>
        <span className="flex-1 text-sm text-gray-200">{step.action}</span>
        <span className={`text-xs px-2 py-0.5 rounded font-mono ${ownerStyle}`}>{step.owner}</span>
        {step.estimated_minutes && (
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <Clock size={10} />
            {step.estimated_minutes}m
          </span>
        )}
        {isExpanded ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
      </button>

      {isExpanded && step.commands && step.commands.length > 0 && (
        <div className="px-4 pb-3 pt-1 bg-black/20 border-t border-dt-border">
          {step.commands.filter(Boolean).map((cmd, i) => (
            <div key={i} className="flex items-start gap-2 mt-1">
              <Terminal size={11} className="text-green-400 mt-0.5 flex-shrink-0" />
              <code className="text-xs text-green-300 font-mono break-all">{cmd}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default memo(function PlaybookPanel({ nodeId, nodeName }) {
  const [expandedStep, setExpandedStep] = useState(null)

  const mutation = useMutation({
    mutationFn: ({ forceRegenerate }) => generatePlaybook(nodeId, forceRegenerate),
    onError: (error) => {
      const message = error.userMessage || error.message || 'Playbook generation failed'
      alert(`❌ ${message}`)
    },
  })

  const playbook = mutation.data

  const totalMinutes = playbook?.steps.reduce((sum, s) => sum + (s.estimated_minutes || 0), 0)

  if (!mutation.isSuccess && !mutation.isPending) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-8 text-center">
        <BookOpen size={32} className="text-gray-600" />
        <div>
          <p className="text-sm text-gray-400 mb-1">Generate an AI-powered recovery runbook</p>
          <p className="text-xs text-gray-600">Uses Ollama LLM + topology context + documentation</p>
        </div>
        <button
          onClick={() => mutation.mutate({ forceRegenerate: false })}
          className="flex items-center gap-2 px-4 py-2 bg-dt-accent hover:bg-blue-600 text-white text-xs font-mono rounded transition-colors"
        >
          <Zap size={12} /> Generate Playbook
        </button>
      </div>
    )
  }

  if (mutation.isPending) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-8">
        <div className="w-6 h-6 border-2 border-dt-accent border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-gray-400 font-mono">Generating playbook with LLM…</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <BookOpen size={14} className="text-dt-accent" />
            <span className="text-sm font-bold text-gray-100">{playbook.node_name}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-mono ${
              playbook.generation_source === 'llm'
                ? 'bg-green-900/30 text-green-400'
                : 'bg-yellow-900/30 text-yellow-400'
            }`}>
              {playbook.generation_source === 'llm' ? '🤖 LLM' : '📋 Static'}
            </span>
          </div>
          <p className="text-xs text-gray-400 italic">{playbook.summary}</p>
        </div>
        <button
          onClick={() => mutation.mutate({ forceRegenerate: true })}
          title="Regenerate"
          className="flex-shrink-0 p-1.5 rounded hover:bg-white/10 text-gray-500 hover:text-dt-accent transition-colors"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-4 text-xs text-gray-500 font-mono">
        <span className="flex items-center gap-1">
          <Clock size={10} />
          ~{totalMinutes}min total
        </span>
        <span>{playbook.steps.length} steps</span>
        <span>Strategy: {playbook.recovery_strategy}</span>
        {playbook.rto_minutes && <span>RTO: {playbook.rto_minutes}min</span>}
      </div>

      {/* Steps */}
      <div className="mt-1">
        {playbook.steps.map((step) => (
          <StepCard
            key={step.step}
            step={step}
            isExpanded={expandedStep === step.step}
            onToggle={() => setExpandedStep(expandedStep === step.step ? null : step.step)}
          />
        ))}
      </div>

      {/* Doc References */}
      {playbook.doc_references.length > 0 && (
        <div className="pt-2 border-t border-dt-border">
          <p className="text-xs text-gray-500 mb-1">Sources used:</p>
          {playbook.doc_references.map((ref, i) => (
            <p key={i} className="text-xs text-blue-400/60 font-mono truncate">{ref}</p>
          ))}
        </div>
      )}
    </div>
  )
})
