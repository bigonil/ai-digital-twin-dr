import { useEffect } from 'react'
import { Play, Pause, RotateCcw } from 'lucide-react'
import { useSimulationPlayback } from '../hooks/useSimulationPlayback'

/**
 * SimulationTimeline Component
 *
 * Displays a timeline player UI with:
 * - Play/Pause and Rewind controls
 * - Seekable progress bar
 * - Time display (MM:SS.M format)
 * - Speed slider (0.25x to 2.0x)
 * - Live stats: affected nodes, worst RTO, worst RPO
 *
 * @param {Object} simulationResult - Result from disaster simulation with:
 *   - total_duration_ms: number (total simulation duration)
 *   - blast_radius: Array of node objects with:
 *       - name, type, distance
 *       - step_time_ms: when this node enters the blast radius
 *       - rto_minutes: recovery time objective
 *       - rpo_minutes: recovery point objective
 * @param {Function} onTimeChange - Callback(currentTime) when simulation time updates
 */
export default function SimulationTimeline({ simulationResult, onTimeChange }) {
  const playback = useSimulationPlayback(simulationResult?.total_duration_ms || 0)

  // Notify parent of time changes
  useEffect(() => {
    onTimeChange?.(playback.simulationTime)
  }, [playback.simulationTime, onTimeChange])

  // Calculate live stats based on current simulation time
  const blastRadius = simulationResult?.blast_radius || []
  const affectedNodes = blastRadius.filter(
    (node) => node.step_time_ms <= playback.simulationTime
  )

  const worstRto = affectedNodes.length > 0
    ? Math.max(...affectedNodes.map((n) => n.estimated_rto_minutes || 0))
    : null

  const worstRpo = affectedNodes.length > 0
    ? Math.max(...affectedNodes.map((n) => n.estimated_rpo_minutes || 0))
    : null

  // Format time as MM:SS.M
  const formatTime = (ms) => {
    const totalSeconds = Math.floor(ms / 1000)
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    const tenths = Math.floor((ms % 1000) / 100)
    return `${minutes}:${String(seconds).padStart(2, '0')}.${tenths}`
  }

  // Format duration for display
  const durationMs = simulationResult?.total_duration_ms || 0
  const totalDurationStr = formatTime(durationMs)
  const currentTimeStr = formatTime(playback.simulationTime)

  return (
    <div className="bg-dt-surface border-t border-dt-border px-4 py-4 shrink-0">
      {/* Title */}
      <div className="text-xs font-mono text-gray-400 uppercase tracking-widest mb-3">
        Simulation Timeline
      </div>

      {/* Control Row 1: Play/Pause, Rewind, Progress Bar, Time Display */}
      <div className="flex items-center gap-3 mb-3">
        {/* Play/Pause Button */}
        <button
          onClick={playback.togglePlayPause}
          disabled={!simulationResult}
          className="flex items-center justify-center w-8 h-8 rounded bg-dt-accent hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
          title={playback.isPlaying ? 'Pause' : 'Play'}
        >
          {playback.isPlaying ? (
            <Pause size={16} />
          ) : (
            <Play size={16} />
          )}
        </button>

        {/* Rewind Button */}
        <button
          onClick={playback.rewind}
          disabled={!simulationResult}
          className="flex items-center justify-center w-8 h-8 rounded border border-dt-border hover:border-dt-accent hover:text-dt-accent text-gray-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Rewind to start"
        >
          <RotateCcw size={16} />
        </button>

        {/* Progress Bar */}
        <input
          type="range"
          min="0"
          max={durationMs}
          value={playback.simulationTime}
          onChange={(e) => playback.seek(Number(e.target.value))}
          disabled={!simulationResult}
          className="flex-1 h-1.5 rounded bg-dt-border cursor-pointer accent-dt-accent disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${playback.progress * 100}%, #1f2937 ${playback.progress * 100}%, #1f2937 100%)`
          }}
        />

        {/* Time Display */}
        <div className="text-xs font-mono text-gray-400 whitespace-nowrap">
          {currentTimeStr} / {totalDurationStr}
        </div>
      </div>

      {/* Control Row 2: Speed Slider and Stats */}
      <div className="flex items-center gap-4">
        {/* Speed Control */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 font-mono">Speed:</label>
          <input
            type="range"
            min="0.25"
            max="2.0"
            step="0.25"
            value={playback.speed}
            onChange={(e) => playback.changeSpeed(Number(e.target.value))}
            disabled={!simulationResult}
            className="w-20 h-1.5 rounded bg-dt-border cursor-pointer accent-dt-accent disabled:opacity-40 disabled:cursor-not-allowed"
          />
          <span className="text-xs font-mono text-gray-400 w-6 text-right">
            {playback.speed.toFixed(2)}x
          </span>
        </div>

        {/* Stats: Affected Nodes */}
        <div className="flex-1 flex items-center gap-6">
          <div className="bg-dt-bg/50 rounded px-3 py-1.5 border border-dt-border/50">
            <div className="text-xs text-gray-500 font-mono uppercase tracking-wide mb-0.5">
              Affected
            </div>
            <div className="text-sm font-mono text-dt-accent font-bold">
              {affectedNodes.length} / {blastRadius.length}
            </div>
          </div>

          {/* Stats: Worst RTO */}
          <div className="bg-dt-bg/50 rounded px-3 py-1.5 border border-dt-border/50">
            <div className="text-xs text-gray-500 font-mono uppercase tracking-wide mb-0.5">
              Worst RTO
            </div>
            <div className="text-sm font-mono text-dt-warning font-bold">
              {worstRto ? `${worstRto}m` : '—'}
            </div>
          </div>

          {/* Stats: Worst RPO */}
          <div className="bg-dt-bg/50 rounded px-3 py-1.5 border border-dt-border/50">
            <div className="text-xs text-gray-500 font-mono uppercase tracking-wide mb-0.5">
              Worst RPO
            </div>
            <div className="text-sm font-mono text-dt-success font-bold">
              {worstRpo ? `${worstRpo}m` : '—'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
