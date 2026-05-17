/**
 * PlaybookPanel.jsx
 * Displays a Claude-AI-generated disaster recovery runbook with full detail.
 */
import { memo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  BookOpen, RefreshCw, Clock, User, Terminal,
  ChevronDown, ChevronRight, Zap, ShieldAlert,
  CheckCircle2, Undo2, AlertTriangle, Radio,
  ListChecks, MessageSquare, Info,
} from 'lucide-react'
import { generatePlaybook } from '../api/client.js'

/* ── Risk badge ─────────────────────────────────────── */
function RiskBadge({ level }) {
  const styles = {
    high:   'bg-red-900/40 text-red-400 border border-red-800',
    medium: 'bg-yellow-900/30 text-yellow-400 border border-yellow-800',
    low:    'bg-green-900/20 text-green-400 border border-green-800',
  }
  const icons = { high: '🔴', medium: '🟡', low: '🟢' }
  const s = level?.toLowerCase() || 'low'
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${styles[s] || styles.low}`}>
      {icons[s]} {s}
    </span>
  )
}

/* ── Owner badge ─────────────────────────────────────── */
function OwnerBadge({ owner }) {
  const styles = {
    DBA:             'text-purple-400 bg-purple-900/20',
    SRE:             'text-blue-400 bg-blue-900/20',
    'on-call':       'text-yellow-400 bg-yellow-900/20',
    'platform-team': 'text-cyan-400 bg-cyan-900/20',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${styles[owner] || 'text-gray-400 bg-gray-800'}`}>
      {owner}
    </span>
  )
}

/* ── Step card ───────────────────────────────────────── */
function StepCard({ step, isExpanded, onToggle }) {
  return (
    <div className="border border-dt-border rounded mb-2 overflow-hidden">
      {/* Header row */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-white/5 transition-colors"
      >
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-dt-accent/20 text-dt-accent text-xs font-bold flex items-center justify-center">
          {step.step}
        </span>
        <span className="flex-1 text-sm text-gray-200 leading-snug">{step.action}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <RiskBadge level={step.risk_level} />
          <OwnerBadge owner={step.owner} />
          {step.estimated_minutes != null && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <Clock size={10} />{step.estimated_minutes}m
            </span>
          )}
          {isExpanded
            ? <ChevronDown size={14} className="text-gray-500" />
            : <ChevronRight size={14} className="text-gray-500" />}
        </div>
      </button>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="bg-black/20 border-t border-dt-border px-4 py-3 space-y-3">

          {/* Shell commands */}
          {step.commands?.filter(Boolean).length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-green-400 font-mono mb-1.5">
                <Terminal size={11} /> Commands
              </div>
              <div className="space-y-1">
                {step.commands.filter(Boolean).map((cmd, i) => (
                  <code key={i} className="block text-xs text-green-300 font-mono bg-black/40 rounded px-3 py-1.5 break-all">
                    {cmd}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Verification */}
          {step.verification && (
            <div className="flex gap-2">
              <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <div className="text-xs text-emerald-400 font-mono mb-0.5">Verification</div>
                <p className="text-xs text-gray-300 leading-relaxed">{step.verification}</p>
              </div>
            </div>
          )}

          {/* Rollback */}
          {step.rollback && (
            <div className="flex gap-2">
              <Undo2 size={13} className="text-orange-400 flex-shrink-0 mt-0.5" />
              <div>
                <div className="text-xs text-orange-400 font-mono mb-0.5">Rollback</div>
                <p className="text-xs text-gray-300 leading-relaxed">{step.rollback}</p>
              </div>
            </div>
          )}

          {/* Notes */}
          {step.notes && (
            <div className="flex gap-2">
              <Info size={13} className="text-gray-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-gray-400 italic leading-relaxed">{step.notes}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Collapsible section ─────────────────────────────── */
function Section({ icon: Icon, title, color = 'text-gray-400', children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-dt-border rounded overflow-hidden mb-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-white/5 transition-colors text-left"
      >
        <Icon size={13} className={color} />
        <span className={`text-xs font-mono font-bold ${color}`}>{title}</span>
        <ChevronDown size={12} className="text-gray-600 ml-auto transition-transform" style={{ transform: open ? '' : 'rotate(-90deg)' }} />
      </button>
      {open && <div className="px-3 pb-3 pt-1 bg-black/10">{children}</div>}
    </div>
  )
}

/* ── Main component ──────────────────────────────────── */
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

  if (!mutation.isSuccess && !mutation.isPending) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-8 text-center">
        <BookOpen size={32} className="text-gray-600" />
        <div>
          <p className="text-sm text-gray-400 mb-1">Generate an AI-powered recovery runbook</p>
          <p className="text-xs text-gray-600">
            Uses Claude AI · topology context · documentation
          </p>
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
        <p className="text-xs text-gray-400 font-mono">Generating runbook with Claude AI…</p>
      </div>
    )
  }

  const isAI = playbook.generation_source === 'claude'
  const totalMin = playbook.estimated_total_minutes
    ?? playbook.steps.reduce((s, step) => s + (step.estimated_minutes || 0), 0)

  return (
    <div className="flex flex-col gap-3">

      {/* ── Top header ── */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <BookOpen size={14} className="text-dt-accent" />
            <span className="text-sm font-bold text-gray-100">{playbook.node_name}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-mono ${
              isAI ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
            }`}>
              {isAI ? '✨ Claude AI' : '📋 Static'}
            </span>
            {playbook.llm_model !== 'none' && (
              <span className="text-xs text-gray-600 font-mono">{playbook.llm_model}</span>
            )}
          </div>
          <p className="text-xs text-gray-400 italic leading-relaxed">{playbook.summary}</p>
        </div>
        <button
          onClick={() => mutation.mutate({ forceRegenerate: true })}
          title="Regenerate"
          className="flex-shrink-0 p-1.5 rounded hover:bg-white/10 text-gray-500 hover:text-dt-accent transition-colors"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* ── Meta strip ── */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500 font-mono border-t border-dt-border pt-2">
        <span className="flex items-center gap-1"><Clock size={10} /> ~{totalMin} min total</span>
        <span>{playbook.steps.length} steps</span>
        <span>Strategy: {playbook.recovery_strategy}</span>
        {playbook.rto_minutes && <span>RTO: {playbook.rto_minutes} min</span>}
        {playbook.rpo_minutes && <span>RPO: {playbook.rpo_minutes} min</span>}
      </div>

      {/* ── Business impact ── */}
      {playbook.business_impact && (
        <div className="flex gap-2 bg-red-950/20 border border-red-900/40 rounded p-3">
          <ShieldAlert size={14} className="text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs text-red-400 font-mono font-bold mb-0.5">BUSINESS IMPACT</div>
            <p className="text-xs text-gray-300 leading-relaxed">{playbook.business_impact}</p>
          </div>
        </div>
      )}

      {/* ── Risk assessment ── */}
      {playbook.risk_assessment && (
        <div className="flex gap-2 bg-yellow-950/20 border border-yellow-900/40 rounded p-3">
          <AlertTriangle size={14} className="text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs text-yellow-400 font-mono font-bold mb-0.5">RISK ASSESSMENT</div>
            <p className="text-xs text-gray-300 leading-relaxed">{playbook.risk_assessment}</p>
          </div>
        </div>
      )}

      {/* ── Prerequisites ── */}
      {playbook.prerequisites?.length > 0 && (
        <Section icon={ListChecks} title="PREREQUISITES" color="text-cyan-400" defaultOpen={true}>
          <ul className="space-y-1 mt-1">
            {playbook.prerequisites.map((p, i) => (
              <li key={i} className="flex gap-2 text-xs text-gray-300">
                <span className="text-cyan-500 flex-shrink-0">✓</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Communication plan ── */}
      {playbook.communication_plan?.length > 0 && (
        <Section icon={MessageSquare} title="COMMUNICATION PLAN" color="text-purple-400" defaultOpen={false}>
          <ul className="space-y-1.5 mt-1">
            {playbook.communication_plan.map((c, i) => (
              <li key={i} className="flex gap-2 text-xs text-gray-300">
                <Radio size={10} className="text-purple-400 flex-shrink-0 mt-0.5" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Steps ── */}
      <div>
        <div className="text-xs font-mono text-gray-500 mb-2 flex items-center gap-2">
          <span>RECOVERY STEPS</span>
          <span className="text-gray-700">·</span>
          <span className="text-gray-600">click to expand verification &amp; rollback</span>
        </div>
        {playbook.steps.map((step) => (
          <StepCard
            key={step.step}
            step={step}
            isExpanded={expandedStep === step.step}
            onToggle={() => setExpandedStep(expandedStep === step.step ? null : step.step)}
          />
        ))}
      </div>

      {/* ── Doc references ── */}
      {playbook.doc_references?.length > 0 && (
        <div className="pt-2 border-t border-dt-border">
          <p className="text-xs text-gray-500 mb-1 font-mono">Sources used:</p>
          {playbook.doc_references.map((ref, i) => (
            <p key={i} className="text-xs text-blue-400/60 font-mono truncate">{ref}</p>
          ))}
        </div>
      )}
    </div>
  )
})
