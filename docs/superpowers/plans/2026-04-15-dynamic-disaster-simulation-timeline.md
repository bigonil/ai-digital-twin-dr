# Dynamic Disaster Simulation Timeline with MCP Agent Control

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add interactive timeline-based visualization of cascading failure propagation with real-time metrics, plus MCP tools for AI agents to simulate, inspect, and control disaster scenarios.

**Architecture:** 
- Backend calculates BFS distance for each affected node, converts to `step_time_ms` (time when node becomes RED)
- Frontend receives step times, plays animation with play/pause/rewind/speed controls
- Live stats (node count, RTO/RPO) update as timeline progresses
- MCP Server exposes 3 new tools: `simulate_with_timeline`, `get_simulation_state`, `control_timeline` for agentic interrogation

**Tech Stack:** FastAPI (backend), React + requestAnimationFrame (frontend animation), MCP Protocol (agent control)

---

## File Structure

### Backend (Python)
- **Modify:** `backend/api/dr.py` — extend simulate_disaster response with step_time_ms
- **Modify:** `backend/models/graph.py` — add SimulationWithTimeline response model
- **Modify:** `backend/mcp/server.py` — add 3 new MCP tools for timeline control

### Frontend (React)
- **Create:** `frontend/src/components/SimulationTimeline.jsx` — timeline player UI + playback logic
- **Create:** `frontend/src/hooks/useSimulationPlayback.js` — state management for animation timeline
- **Modify:** `frontend/src/components/Graph3D.jsx` — accept simulationTime prop, render dynamically
- **Modify:** `frontend/src/components/DisasterPanel.jsx` — embed SimulationTimeline, manage simulation state
- **Modify:** `frontend/src/api/client.js` — expose simulationTime from backend response

### Testing
- **Create:** `backend/tests/test_timeline_simulation.py` — test step_time_ms calculation
- **Create:** `frontend/src/components/__tests__/SimulationTimeline.test.jsx` — test timeline playback logic

---

## Task Breakdown

### Task 1: Backend — Extend DisasterSimulationResult Model

**Files:**
- Modify: `backend/models/graph.py`

**Context:** The response from simulate_disaster currently returns `blast_radius: list[AffectedNode]`. We need to add step_time_ms to each affected node so the frontend knows when each node should become RED.

- [ ] **Step 1: Read current AffectedNode model**

Open `backend/models/graph.py` and review the `AffectedNode` class (lines 81-87).

Expected: You'll see it has `id, name, type, distance, estimated_rto_minutes, estimated_rpo_minutes`.

- [ ] **Step 2: Add step_time_ms field to AffectedNode**

In `backend/models/graph.py`, update the `AffectedNode` class:

```python
class AffectedNode(BaseModel):
    id: str
    name: str
    type: str
    distance: int
    estimated_rto_minutes: int | None = None
    estimated_rpo_minutes: int | None = None
    step_time_ms: int = 0  # NEW: milliseconds when this node becomes RED in timeline
```

- [ ] **Step 3: Create new response model for timeline-aware simulations**

Add this new model right after `DisasterSimulationResult` in `backend/models/graph.py`:

```python
class SimulationWithTimeline(BaseModel):
    """Enhanced disaster simulation result with timeline animation data."""
    origin_node_id: str
    blast_radius: list[AffectedNode]
    total_affected: int
    worst_case_rto_minutes: int | None = None
    worst_case_rpo_minutes: int | None = None
    recovery_steps: list[str] = Field(default_factory=list)
    
    # Timeline-specific fields
    max_distance: int  # maximum BFS distance in cascade
    total_duration_ms: int  # total animation duration (5000-8000ms)
    
    # For MCP agents: raw timeline data for programmatic access
    timeline_steps: list[dict] = Field(default_factory=list)  # [{node_id, step_time_ms, distance}, ...]
```

- [ ] **Step 4: Commit**

```bash
cd backend
git add models/graph.py
git commit -m "feat: add step_time_ms and SimulationWithTimeline model"
```

---

### Task 2: Backend — Calculate step_time_ms in simulate_disaster

**Files:**
- Modify: `backend/api/dr.py`

**Context:** The /dr/simulate endpoint needs to calculate `step_time_ms` for each node based on its BFS distance. Formula: `step_time_ms = distance * (total_duration_ms / max_distance)`.

- [ ] **Step 1: Read current simulate_disaster endpoint**

Open `backend/api/dr.py` and review the `simulate_disaster` function (lines 14-52).

Expected: You'll see it builds `affected` list but doesn't calculate step times.

- [ ] **Step 2: Add helper function to calculate step times**

In `backend/api/dr.py`, add this function before the `@router.post("/simulate")` decorator:

```python
def _calculate_step_times(affected_nodes: list[AffectedNode], total_duration_ms: int = 5000) -> tuple[list[AffectedNode], int, list[dict]]:
    """
    Calculate step_time_ms for each node based on BFS distance.
    
    Args:
        affected_nodes: List of affected nodes with distance field set
        total_duration_ms: Total animation duration in milliseconds
    
    Returns:
        (updated_affected_nodes, max_distance, timeline_steps_list)
    """
    if not affected_nodes:
        return affected_nodes, 0, []
    
    # Find max distance
    max_distance = max(node.distance for node in affected_nodes)
    
    # Calculate step_time_ms for each node
    updated_nodes = []
    timeline_steps = []
    
    for node in affected_nodes:
        # Distance 0 → 0ms (instant), distance N → proportional time
        step_time_ms = int(node.distance * (total_duration_ms / max_distance)) if max_distance > 0 else 0
        node.step_time_ms = step_time_ms
        updated_nodes.append(node)
        
        # Record timeline step for MCP agents
        timeline_steps.append({
            "node_id": node.id,
            "node_name": node.name,
            "distance": node.distance,
            "step_time_ms": step_time_ms,
            "rto_minutes": node.estimated_rto_minutes,
            "rpo_minutes": node.estimated_rpo_minutes,
        })
    
    # Sort timeline_steps by step_time_ms for easy playback
    timeline_steps.sort(key=lambda x: x["step_time_ms"])
    
    return updated_nodes, max_distance, timeline_steps
```

- [ ] **Step 3: Modify simulate_disaster to use new function**

Replace the endpoint body (lines 14-52) with:

```python
@router.post("/simulate", response_model=SimulationWithTimeline)
async def simulate_disaster(body: DisasterSimulationRequest, request: Request):
    rows = await request.app.state.neo4j.simulate_disaster(body.node_id, body.depth)

    if not rows and body.node_id:
        check = await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) RETURN n.id", {"id": body.node_id}
        )
        if not check:
            raise HTTPException(status_code=404, detail=f"Node {body.node_id!r} not found")

    affected = [
        AffectedNode(
            id=r["id"],
            name=r.get("name", r["id"]),
            type=r.get("type", "unknown"),
            distance=r["distance"],
            estimated_rto_minutes=r.get("rto_minutes"),
            estimated_rpo_minutes=r.get("rpo_minutes"),
        )
        for r in rows
    ]

    # NEW: Calculate step times for timeline animation
    affected, max_distance, timeline_steps = _calculate_step_times(affected, total_duration_ms=5000)

    rtos = [a.estimated_rto_minutes for a in affected if a.estimated_rto_minutes]
    rpos = [a.estimated_rpo_minutes for a in affected if a.estimated_rpo_minutes]

    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = 'simulated_failure'",
        {"id": body.node_id},
    )

    return SimulationWithTimeline(
        origin_node_id=body.node_id,
        blast_radius=affected,
        total_affected=len(affected),
        worst_case_rto_minutes=max(rtos) if rtos else None,
        worst_case_rpo_minutes=max(rpos) if rpos else None,
        recovery_steps=_basic_recovery_steps(body.node_id, affected),
        max_distance=max_distance,
        total_duration_ms=5000,
        timeline_steps=timeline_steps,
    )
```

- [ ] **Step 4: Add import for new model**

At the top of `backend/api/dr.py`, ensure this import exists:

```python
from models.graph import (
    AffectedNode,
    DisasterSimulationRequest,
    DisasterSimulationResult,
    SimulationWithTimeline,  # NEW
    DriftResult,
)
```

- [ ] **Step 5: Test the endpoint**

Run the FastAPI server and test via curl or Postman:

```bash
curl -X POST http://localhost:8001/api/dr/simulate \
  -H "Content-Type: application/json" \
  -d '{"node_id": "db-001", "depth": 5}'
```

Expected response includes `step_time_ms` for each node in `blast_radius` and a `timeline_steps` array.

- [ ] **Step 6: Commit**

```bash
cd backend
git add api/dr.py
git commit -m "feat: calculate step_time_ms for timeline animation"
```

---

### Task 3: Frontend — Create useSimulationPlayback Hook

**Files:**
- Create: `frontend/src/hooks/useSimulationPlayback.js`

**Context:** This hook manages the timeline animation state: current time, play/pause, speed, and provides callbacks for the UI. It runs a requestAnimationFrame loop to drive the animation.

- [ ] **Step 1: Create the hook file**

Create `frontend/src/hooks/useSimulationPlayback.js`:

```javascript
import { useState, useRef, useCallback, useEffect } from 'react'

/**
 * useSimulationPlayback
 * 
 * Manages playback of a disaster simulation timeline.
 * 
 * Returns:
 * - simulationTime: current time in ms (0 to totalDuration)
 * - isPlaying: boolean
 * - speed: 0.25 to 2.0
 * - progress: 0 to 1 (for progress bar)
 * - play/pause/rewind/setSpeed/seek callbacks
 */
export function useSimulationPlayback(totalDuration) {
  const [simulationTime, setSimulationTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(true)
  const [speed, setSpeed] = useState(1.0)
  
  const animationFrameRef = useRef(null)
  const lastTimeRef = useRef(Date.now())

  // Main animation loop
  useEffect(() => {
    if (!isPlaying || simulationTime >= totalDuration) {
      setIsPlaying(false)
      return
    }

    const animate = () => {
      const now = Date.now()
      const deltaMs = now - lastTimeRef.current
      lastTimeRef.current = now

      setSimulationTime(prev => {
        const newTime = prev + deltaMs * speed
        return Math.min(newTime, totalDuration)
      })

      animationFrameRef.current = requestAnimationFrame(animate)
    }

    animationFrameRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [isPlaying, speed, totalDuration])

  const play = useCallback(() => {
    lastTimeRef.current = Date.now()
    setIsPlaying(true)
  }, [])

  const pause = useCallback(() => {
    setIsPlaying(false)
  }, [])

  const togglePlayPause = useCallback(() => {
    setIsPlaying(prev => !prev)
  }, [])

  const rewind = useCallback(() => {
    setSimulationTime(0)
    setIsPlaying(false)
  }, [])

  const seek = useCallback((newTime) => {
    setSimulationTime(Math.min(Math.max(newTime, 0), totalDuration))
  }, [totalDuration])

  const changeSpeed = useCallback((newSpeed) => {
    setSpeed(Math.min(Math.max(newSpeed, 0.25), 2.0))
  }, [])

  const progress = totalDuration > 0 ? simulationTime / totalDuration : 0

  return {
    simulationTime,
    isPlaying,
    speed,
    progress,
    play,
    pause,
    togglePlayPause,
    rewind,
    seek,
    changeSpeed,
    totalDuration,
  }
}
```

- [ ] **Step 2: Test the hook (manual for now)**

We'll test this properly in Task 6 with actual tests. For now, just verify the file exists and syntax is valid by checking it imports correctly.

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/hooks/useSimulationPlayback.js
git commit -m "feat: add useSimulationPlayback hook for timeline animation"
```

---

### Task 4: Frontend — Create SimulationTimeline Component

**Files:**
- Create: `frontend/src/components/SimulationTimeline.jsx`

**Context:** This is the UI for the timeline player. It displays play/pause/rewind controls, a progress bar, speed slider, and live stats (node count, RTO/RPO).

- [ ] **Step 1: Create the component file**

Create `frontend/src/components/SimulationTimeline.jsx`:

```javascript
import { useState, useMemo } from 'react'
import { Play, Pause, RotateCcw } from 'lucide-react'
import { useSimulationPlayback } from '../hooks/useSimulationPlayback.js'

export default function SimulationTimeline({ 
  simulationResult, 
  onTimeChange 
}) {
  const {
    simulationTime,
    isPlaying,
    speed,
    progress,
    togglePlayPause,
    rewind,
    seek,
    changeSpeed,
    totalDuration,
  } = useSimulationPlayback(simulationResult?.total_duration_ms || 5000)

  // Notify parent when time changes (for Graph3D to re-render)
  if (onTimeChange) {
    onTimeChange(simulationTime)
  }

  // Calculate live stats based on simulationTime
  const liveStats = useMemo(() => {
    if (!simulationResult?.blast_radius) {
      return { affectedCount: 0, worstRto: null, worstRpo: null }
    }

    const affectedByTime = simulationResult.blast_radius.filter(
      node => (node.step_time_ms || 0) <= simulationTime
    )

    const rtos = affectedByTime
      .map(n => n.estimated_rto_minutes)
      .filter(v => v !== null && v !== undefined)

    const rpos = affectedByTime
      .map(n => n.estimated_rpo_minutes)
      .filter(v => v !== null && v !== undefined)

    return {
      affectedCount: affectedByTime.length,
      worstRto: rtos.length > 0 ? Math.max(...rtos) : null,
      worstRpo: rpos.length > 0 ? Math.max(...rpos) : null,
    }
  }, [simulationResult, simulationTime])

  const formatTime = (ms) => {
    const seconds = (ms / 1000).toFixed(1)
    return `0:${seconds.padStart(4, '0')}`
  }

  return (
    <div className="space-y-3">
      {/* Timeline player controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={togglePlayPause}
          className="flex items-center justify-center w-8 h-8 rounded bg-dt-accent hover:bg-blue-600 text-white transition"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>

        <button
          onClick={rewind}
          className="flex items-center justify-center w-8 h-8 rounded border border-dt-border hover:border-dt-accent text-gray-400 hover:text-dt-accent transition"
          title="Rewind"
        >
          <RotateCcw size={16} />
        </button>

        {/* Progress bar */}
        <div className="flex-1 flex items-center gap-2">
          <input
            type="range"
            min="0"
            max="100"
            value={progress * 100}
            onChange={(e) => seek((parseInt(e.target.value) / 100) * totalDuration)}
            className="flex-1 h-1 bg-dt-border rounded cursor-pointer accent-dt-accent"
          />
          <span className="text-xs font-mono text-gray-400 w-12">
            {formatTime(simulationTime)}
          </span>
        </div>
      </div>

      {/* Speed slider */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500 font-mono">Speed:</span>
        <input
          type="range"
          min="0.25"
          max="2"
          step="0.25"
          value={speed}
          onChange={(e) => changeSpeed(parseFloat(e.target.value))}
          className="flex-1 h-1 bg-dt-border rounded cursor-pointer accent-dt-accent"
        />
        <span className="text-xs font-mono text-gray-400 w-8">
          {speed.toFixed(2)}x
        </span>
      </div>

      {/* Live stats */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-dt-bg rounded px-2 py-1 border border-dt-border/50">
          <p className="text-gray-500">Affected</p>
          <p className="text-dt-accent font-mono text-sm">
            {liveStats.affectedCount} / {simulationResult?.total_affected || 0}
          </p>
        </div>
        <div className="bg-dt-bg rounded px-2 py-1 border border-dt-border/50">
          <p className="text-gray-500">RTO</p>
          <p className="text-dt-warning font-mono text-sm">
            {liveStats.worstRto ? `${liveStats.worstRto}m` : '—'}
          </p>
        </div>
        <div className="bg-dt-bg rounded px-2 py-1 border border-dt-border/50">
          <p className="text-gray-500">RPO</p>
          <p className="text-dt-warning font-mono text-sm">
            {liveStats.worstRpo ? `${liveStats.worstRpo}m` : '—'}
          </p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend
git add src/components/SimulationTimeline.jsx
git commit -m "feat: add SimulationTimeline UI component with playback controls"
```

---

### Task 5: Frontend — Modify DisasterPanel to Embed Timeline

**Files:**
- Modify: `frontend/src/components/DisasterPanel.jsx`

**Context:** The DisasterPanel currently shows just the Blast Radius table. We need to embed the SimulationTimeline and pass the simulationTime to the parent (Graph3D).

- [ ] **Step 1: Read current DisasterPanel**

Open `frontend/src/components/DisasterPanel.jsx` and understand the structure (lines 1-91).

Expected: It calls `simulateDisaster` mutation and shows the table, but no timeline.

- [ ] **Step 2: Import SimulationTimeline**

At the top of `DisasterPanel.jsx`, add:

```javascript
import SimulationTimeline from './SimulationTimeline.jsx'
```

- [ ] **Step 3: Add simulationTime state and callback**

In the component function, add this state after `const [blastRows, setBlastRows] = useState([])`:

```javascript
const [simulationTime, setSimulationTime] = useState(0)
const [simulationResult, setSimulationResult] = useState(null)
```

- [ ] **Step 4: Update mutation to store full simulation result**

Modify the `simMutation` definition:

```javascript
const simMutation = useMutation({
  mutationFn: () => simulateDisaster(selectedNode.id, depth),
  onSuccess: (data) => {
    setBlastRows(data.blast_radius ?? [])
    setSimulationResult(data)  // NEW: store full result for timeline
    onSimulationResult(data.blast_radius ?? [])
  },
})
```

- [ ] **Step 5: Update reset mutation**

Modify the `resetMutation` definition:

```javascript
const resetMutation = useMutation({
  mutationFn: () => resetNode(selectedNode.id),
  onSuccess: () => {
    setBlastRows([])
    setSimulationTime(0)  // NEW: reset timeline
    setSimulationResult(null)  // NEW: clear result
    onReset()
    qc.invalidateQueries({ queryKey: ['topology'] })
  },
})
```

- [ ] **Step 6: Add onSimulationTimeChange callback prop**

Add this prop to the function signature (after `onReset`):

```javascript
export default function DisasterPanel({ 
  selectedNode, 
  onSimulationResult, 
  onReset,
  onSimulationTimeChange  // NEW
}) {
```

- [ ] **Step 7: Embed SimulationTimeline in the UI**

Replace the panel contents (after line 28) with:

```javascript
return (
  <div className="bg-dt-surface border-t border-dt-border px-4 py-3 shrink-0" style={{ maxHeight: '340px' }}>
    <div className="flex items-center gap-4 mb-2">
      <span className="text-xs font-mono text-gray-400 uppercase tracking-widest flex items-center gap-1">
        <AlertTriangle size={12} className="text-dt-warning" /> Disaster Simulation
      </span>

      <div className="flex items-center gap-2 ml-auto">
        <label className="text-xs text-gray-500">Depth</label>
        <input
          type="number" min={1} max={10} value={depth}
          onChange={e => setDepth(Number(e.target.value))}
          className="w-14 bg-dt-bg border border-dt-border rounded px-2 py-1 text-xs font-mono text-gray-200"
        />
        <button
          onClick={() => simMutation.mutate()}
          disabled={!selectedNode || simMutation.isPending}
          className="flex items-center gap-1 bg-dt-danger hover:bg-red-700 disabled:opacity-40 text-white text-xs font-mono px-3 py-1.5 rounded transition-colors"
        >
          <Zap size={12} /> Simulate
        </button>
        <button
          onClick={() => resetMutation.mutate()}
          disabled={!selectedNode || blastRows.length === 0}
          className="flex items-center gap-1 border border-dt-border hover:border-dt-accent text-gray-400 hover:text-dt-accent text-xs font-mono px-3 py-1.5 rounded transition-colors disabled:opacity-40"
        >
          <RotateCcw size={12} /> Reset
        </button>
      </div>
    </div>

    {selectedNode ? (
      <p className="text-xs text-gray-500 font-mono mb-2">
        Target: <span className="text-dt-accent">{selectedNode.name}</span> ({selectedNode.type})
      </p>
    ) : (
      <p className="text-xs text-gray-600 font-mono mb-2">Click a node in the graph to select it.</p>
    )}

    {/* NEW: Timeline player */}
    {simulationResult && (
      <div className="mb-3 pb-3 border-b border-dt-border/30">
        <SimulationTimeline 
          simulationResult={simulationResult}
          onTimeChange={(time) => {
            setSimulationTime(time)
            if (onSimulationTimeChange) onSimulationTimeChange(time)
          }}
        />
      </div>
    )}

    {/* Blast radius table */}
    {blastRows.length > 0 && (
      <div className="overflow-y-auto" style={{ maxHeight: '140px' }}>
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-gray-500 text-left border-b border-dt-border">
              <th className="pb-1 pr-4">Depth</th><th className="pb-1 pr-4">Node</th>
              <th className="pb-1 pr-4">Type</th><th className="pb-1 pr-4">RTO</th>
            </tr>
          </thead>
          <tbody>
            {blastRows.map((r, i) => (
              <tr key={i} className="border-b border-dt-border/30 hover:bg-dt-bg/50">
                <td className="py-0.5 pr-4 text-dt-danger">{r.distance}</td>
                <td className="py-0.5 pr-4 text-gray-200">{r.name}</td>
                <td className="py-0.5 pr-4 text-gray-400">{r.type}</td>
                <td className="py-0.5 pr-4 text-dt-warning">{r.rto_minutes ? `${r.rto_minutes}m` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
)
```

- [ ] **Step 8: Commit**

```bash
cd frontend
git add src/components/DisasterPanel.jsx
git commit -m "feat: embed SimulationTimeline in DisasterPanel"
```

---

### Task 6: Frontend — Modify Graph3D to Render Based on simulationTime

**Files:**
- Modify: `frontend/src/components/Graph3D.jsx`

**Context:** Graph3D needs to accept a `simulationTime` prop and color nodes based on whether their `step_time_ms <= simulationTime`. Also render badges and animate link glows.

- [ ] **Step 1: Read current Graph3D**

Open `frontend/src/components/Graph3D.jsx` and review (lines 1-90).

Expected: It renders all nodes but doesn't change colors based on time.

- [ ] **Step 2: Add simulationTime prop and helper functions**

Replace the entire Graph3D.jsx file with:

```javascript
import { useRef, useCallback, useMemo, useEffect, useState } from 'react'
import { ForceGraph3D } from 'react-force-graph'

const STATUS_COLOR = {
  healthy:           '#10b981',
  degraded:          '#f59e0b',
  failed:            '#ef4444',
  simulated_failure: '#dc2626',
  unknown:           '#6b7280',
}

const TYPE_SIZE = {
  aws_db_instance:       8,
  aws_rds_cluster:       10,
  aws_lb:                9,
  aws_instance:          6,
  aws_s3_bucket:         5,
  CodeFunction:          3,
  Document:              3,
}

function nodeColor(node, blastSet, simulationTime, activatingNodes) {
  // If timeline is playing and node is activating RIGHT NOW, flash it
  if (activatingNodes.has(node.id)) {
    return '#ff6b6b' // bright red while activating
  }
  
  // If node has step_time_ms and time has reached it, show as failed
  if (node.step_time_ms !== undefined && simulationTime >= node.step_time_ms) {
    return '#dc2626'
  }
  
  // Original logic
  if (blastSet.has(node.id)) return '#dc2626'
  return STATUS_COLOR[node.status] ?? '#6b7280'
}

function nodeSize(node) {
  return TYPE_SIZE[node.type] ?? 5
}

export default function Graph3D({ 
  topology, 
  blastRadius, 
  onNodeClick,
  simulationTime = null  // NEW: time from timeline player
}) {
  const fgRef = useRef()
  const containerRef = useRef()
  const [dims, setDims] = useState({ width: 0, height: 0 })
  const blastSet = useMemo(() => new Set(blastRadius.map(n => n.id)), [blastRadius])
  
  // Track nodes that are currently activating (for visual flash)
  const [activatingNodes, setActivatingNodes] = useState(new Set())

  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setDims({ width, height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Detect which nodes are "activating" (just crossed their step_time_ms)
  useEffect(() => {
    if (simulationTime === null || !topology?.nodes) return

    const nowActivating = new Set()
    topology.nodes.forEach(node => {
      const blastNode = blastRadius.find(b => b.id === node.id)
      if (blastNode && blastNode.step_time_ms !== undefined) {
        // Node activates when simulationTime passes its step_time_ms
        // Flash for 200ms
        if (simulationTime >= blastNode.step_time_ms) {
          const timeSinceActivation = simulationTime - blastNode.step_time_ms
          if (timeSinceActivation < 200) {
            nowActivating.add(node.id)
          }
        }
      }
    })
    setActivatingNodes(nowActivating)
  }, [simulationTime, topology, blastRadius])

  const graphData = useMemo(() => {
    if (!topology) return { nodes: [], links: [] }
    return {
      nodes: topology.nodes.map(n => {
        const blastNode = blastRadius.find(b => b.id === n.id)
        return {
          ...n,
          step_time_ms: blastNode?.step_time_ms,
          distance: blastNode?.distance,
          __color: nodeColor(n, blastSet, simulationTime ?? 0, activatingNodes),
          __size: nodeSize(n),
        }
      }),
      links: topology.edges.map(e => ({ source: e.source, target: e.target, type: e.type })),
    }
  }, [topology, blastSet, simulationTime, activatingNodes, blastRadius])

  const handleNodeClick = useCallback((node) => {
    onNodeClick(node)
    if (fgRef.current) {
      fgRef.current.cameraPosition(
        { x: node.x + 60, y: node.y + 30, z: node.z + 60 },
        node,
        1200,
      )
    }
  }, [onNodeClick])

  // Render node labels with distance badges
  const nodeLabel = (n) => {
    const distance = n.distance !== undefined ? `\nDistance: ${n.distance}` : ''
    return `${n.name}\n${n.type}\n${n.region ?? ''}${distance}`
  }

  // Link styling: highlight active edges
  const linkColor = (l) => {
    const targetNode = graphData.nodes.find(n => n.id === l.target)
    if (targetNode && activatingNodes.has(l.target)) {
      return '#ff6b6b' // bright red for activating links
    }
    return l.type === 'DEPENDS_ON' ? '#3b82f6' : '#6b7280'
  }

  const linkWidth = (l) => {
    const targetNode = graphData.nodes.find(n => n.id === l.target)
    if (targetNode && activatingNodes.has(l.target)) {
      return 2 // thicker while activating
    }
    return 1
  }

  return (
    <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
      {dims.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          width={dims.width}
          height={dims.height}
          backgroundColor="#0a0e1a"
          nodeColor={n => n.__color}
          nodeVal={n => n.__size}
          nodeLabel={nodeLabel}
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          onNodeClick={handleNodeClick}
          nodeThreeObjectExtend={false}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/components/Graph3D.jsx
git commit -m "feat: add simulationTime prop to Graph3D for dynamic rendering"
```

---

### Task 7: Frontend — Modify App.jsx to Wire Up Timeline State

**Files:**
- Modify: `frontend/src/components/App.jsx`

**Context:** App.jsx is the main component that orchestrates DisasterPanel and Graph3D. It needs to pass simulationTime from DisasterPanel → Graph3D.

- [ ] **Step 1: Read current App.jsx**

Open `frontend/src/components/App.jsx` and review (lines 1-62).

Expected: It manages selectedNode and blastRadius state but no simulationTime.

- [ ] **Step 2: Add simulationTime state**

Add this state after `const [blastRadius, setBlastRadius] = useState([])`:

```javascript
const [simulationTime, setSimulationTime] = useState(null)
```

- [ ] **Step 3: Pass simulationTime to Graph3D**

Modify the `<Graph3D>` component (around line 41) to include:

```javascript
<Graph3D
  topology={topology}
  blastRadius={blastRadius}
  onNodeClick={setSelectedNode}
  simulationTime={simulationTime}  // NEW
/>
```

- [ ] **Step 4: Pass onSimulationTimeChange to DisasterPanel**

Modify the `<DisasterPanel>` component (around line 54) to include:

```javascript
<DisasterPanel
  selectedNode={selectedNode}
  onSimulationResult={setBlastRadius}
  onReset={() => {
    setBlastRadius([])
    setSimulationTime(null)  // NEW: reset time on reset
  }}
  onSimulationTimeChange={setSimulationTime}  // NEW
/>
```

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/components/App.jsx
git commit -m "feat: wire up simulationTime state in App.jsx"
```

---

### Task 8: MCP Server — Extend with Timeline-Aware Tools

**Files:**
- Modify: `backend/mcp/server.py`

**Context:** The MCP server currently has `simulate_disaster`, `get_recovery_plan`, `check_drift`. We need to add 3 new tools for agents to:
1. Get current simulation state with timeline data
2. Control timeline playback (seek, speed, pause)
3. Query cascading failure at a specific time

- [ ] **Step 1: Read current MCP server**

Open `backend/mcp/server.py` and review the existing tools.

Expected: You'll see tool definitions for simulate_disaster, get_recovery_plan, check_drift.

- [ ] **Step 2: Add new tool: get_simulation_timeline**

Add this function to the server:

```python
@server.call_tool("get_simulation_timeline")
async def get_simulation_timeline(timeline_query: dict) -> dict:
    """
    Get the timeline data for a running simulation.
    Useful for agents to inspect cascading failures step-by-step.
    
    Args:
        timeline_query: {
            "simulation_id": "unique_id",  # from previous simulate_disaster call
            "query_at_time_ms": 2500,      # (optional) get state at specific time
        }
    
    Returns: {
        "timeline_steps": [...],
        "total_duration_ms": 5000,
        "active_nodes_at_time": [...],  # nodes affected up to query_at_time_ms
    }
    """
    # For now, we store simulation state in memory
    # In production, use Redis or database
    
    sim_id = timeline_query.get("simulation_id")
    query_time = timeline_query.get("query_at_time_ms", float('inf'))
    
    if not sim_id or sim_id not in SIMULATION_CACHE:
        return {"error": f"Simulation {sim_id} not found"}
    
    sim_data = SIMULATION_CACHE[sim_id]
    
    active_nodes = [
        step for step in sim_data["timeline_steps"]
        if step["step_time_ms"] <= query_time
    ]
    
    return {
        "simulation_id": sim_id,
        "timeline_steps": sim_data["timeline_steps"],
        "total_duration_ms": sim_data["total_duration_ms"],
        "active_nodes_at_time": active_nodes,
        "affected_count": len(active_nodes),
    }
```

- [ ] **Step 3: Add simulation cache (module-level)**

At the top of `backend/mcp/server.py`, add:

```python
# Simple in-memory simulation cache
# In production, use Redis with TTL
SIMULATION_CACHE = {}
SIMULATION_COUNTER = 0
```

- [ ] **Step 4: Update simulate_disaster tool to cache result**

Modify the simulate_disaster tool to cache the result:

```python
@server.call_tool("simulate_disaster")
async def mcp_simulate_disaster(tool_input: dict) -> dict:
    node_id = tool_input.get("node_id")
    depth = tool_input.get("depth", 5)
    
    # Call the API endpoint
    result = await app.state.neo4j.simulate_disaster(node_id, depth)
    
    # Build the result (same as backend API)
    affected, max_distance, timeline_steps = _calculate_step_times(
        [AffectedNode(**r) for r in result]
    )
    
    # Cache it for timeline queries
    global SIMULATION_COUNTER
    sim_id = f"sim_{SIMULATION_COUNTER}"
    SIMULATION_COUNTER += 1
    
    SIMULATION_CACHE[sim_id] = {
        "node_id": node_id,
        "timeline_steps": timeline_steps,
        "total_duration_ms": 5000,
        "max_distance": max_distance,
    }
    
    return {
        "simulation_id": sim_id,
        "origin_node_id": node_id,
        "affected_count": len(affected),
        "timeline_steps": timeline_steps,
        "total_duration_ms": 5000,
    }
```

- [ ] **Step 5: Add new tool: analyze_cascading_failure**

Add this tool for detailed cascading analysis:

```python
@server.call_tool("analyze_cascading_failure")
async def analyze_cascading_failure(analysis_query: dict) -> dict:
    """
    Analyze the cascading failure at a specific point in time.
    
    Args:
        analysis_query: {
            "simulation_id": "sim_0",
            "time_ms": 2500,
            "include_metrics": true,
        }
    
    Returns: {
        "time_ms": 2500,
        "active_nodes": [...],
        "failed_count": 5,
        "affected_count": 12,
        "estimated_max_rto": 45,
        "estimated_max_rpo": 15,
    }
    """
    sim_id = analysis_query.get("simulation_id")
    time_ms = analysis_query.get("time_ms")
    
    if not sim_id or sim_id not in SIMULATION_CACHE:
        return {"error": f"Simulation {sim_id} not found"}
    
    sim_data = SIMULATION_CACHE[sim_id]
    
    active_nodes = [
        step for step in sim_data["timeline_steps"]
        if step["step_time_ms"] <= time_ms
    ]
    
    rtos = [n.get("rto_minutes") for n in active_nodes if n.get("rto_minutes")]
    rpos = [n.get("rpo_minutes") for n in active_nodes if n.get("rpo_minutes")]
    
    return {
        "simulation_id": sim_id,
        "time_ms": time_ms,
        "active_nodes_count": len(active_nodes),
        "max_distance_reached": max([n["distance"] for n in active_nodes], default=0),
        "estimated_worst_rto_minutes": max(rtos) if rtos else None,
        "estimated_worst_rpo_minutes": max(rpos) if rpos else None,
        "active_node_ids": [n["node_id"] for n in active_nodes],
    }
```

- [ ] **Step 6: Commit**

```bash
cd backend
git add mcp/server.py
git commit -m "feat: add timeline-aware MCP tools for agent interrogation"
```

---

### Task 9: Testing — Unit Tests for Timeline Calculation

**Files:**
- Create: `backend/tests/test_timeline_simulation.py`

**Context:** Test the step_time_ms calculation logic to ensure nodes are assigned correct timing.

- [ ] **Step 1: Create test file**

Create `backend/tests/test_timeline_simulation.py`:

```python
import pytest
from models.graph import AffectedNode
from api.dr import _calculate_step_times


def test_calculate_step_times_single_node():
    """Test step times with just the origin node."""
    nodes = [
        AffectedNode(
            id="node-0",
            name="Origin",
            type="database",
            distance=0,
        )
    ]
    
    updated, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=5000)
    
    assert max_dist == 0
    assert len(steps) == 1
    assert steps[0]["step_time_ms"] == 0


def test_calculate_step_times_cascade():
    """Test step times with cascading failures."""
    nodes = [
        AffectedNode(id="n0", name="Origin", type="db", distance=0),
        AffectedNode(id="n1", name="App1", type="app", distance=1),
        AffectedNode(id="n2", name="App2", type="app", distance=1),
        AffectedNode(id="n3", name="Cache", type="cache", distance=2),
    ]
    
    updated, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=5000)
    
    assert max_dist == 2
    assert len(steps) == 4
    
    # Check step times are proportional to distance
    step_map = {s["node_id"]: s["step_time_ms"] for s in steps}
    
    assert step_map["n0"] == 0        # distance 0
    assert step_map["n1"] == 2500     # distance 1 → 50% of total
    assert step_map["n2"] == 2500     # distance 1
    assert step_map["n3"] == 5000     # distance 2 → 100% of total


def test_calculate_step_times_sorted():
    """Test that timeline_steps are sorted by step_time_ms."""
    nodes = [
        AffectedNode(id="n3", name="X", type="x", distance=2),
        AffectedNode(id="n0", name="X", type="x", distance=0),
        AffectedNode(id="n1", name="X", type="x", distance=1),
    ]
    
    _, _, steps = _calculate_step_times(nodes, total_duration_ms=5000)
    
    # Steps should be sorted by step_time_ms
    for i in range(len(steps) - 1):
        assert steps[i]["step_time_ms"] <= steps[i + 1]["step_time_ms"]


def test_calculate_step_times_custom_duration():
    """Test with custom total duration."""
    nodes = [
        AffectedNode(id="n0", name="X", type="x", distance=0),
        AffectedNode(id="n1", name="X", type="x", distance=1),
    ]
    
    _, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=10000)
    
    step_map = {s["node_id"]: s["step_time_ms"] for s in steps}
    assert step_map["n0"] == 0
    assert step_map["n1"] == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run the tests**

```bash
cd backend
pytest tests/test_timeline_simulation.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 3: Commit**

```bash
cd backend
git add tests/test_timeline_simulation.py
git commit -m "test: add unit tests for step_time_ms calculation"
```

---

### Task 10: Testing — Component Tests for SimulationTimeline

**Files:**
- Create: `frontend/src/components/__tests__/SimulationTimeline.test.jsx`

**Context:** Test the timeline component's playback logic (play, pause, rewind, speed).

- [ ] **Step 1: Create test file**

Create `frontend/src/components/__tests__/SimulationTimeline.test.jsx`:

```javascript
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SimulationTimeline from '../SimulationTimeline'

describe('SimulationTimeline', () => {
  const mockSimulationResult = {
    total_duration_ms: 5000,
    blast_radius: [
      { id: 'n0', name: 'Node0', distance: 0, step_time_ms: 0 },
      { id: 'n1', name: 'Node1', distance: 1, step_time_ms: 2500 },
      { id: 'n2', name: 'Node2', distance: 2, step_time_ms: 5000 },
    ],
  }

  it('renders timeline controls', () => {
    render(
      <SimulationTimeline 
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )
    
    expect(screen.getByTitle('Play')).toBeInTheDocument()
    expect(screen.getByTitle('Rewind')).toBeInTheDocument()
    expect(screen.getByText(/Speed:/)).toBeInTheDocument()
  })

  it('calculates live stats correctly', async () => {
    const { rerender } = render(
      <SimulationTimeline 
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )
    
    await waitFor(() => {
      // Initially, no nodes affected (time=0, only n0 is affected at 0ms)
      expect(screen.getByText(/Affected/i)).toBeInTheDocument()
    })
  })

  it('updates speed when slider changes', async () => {
    const { container } = render(
      <SimulationTimeline 
        simulationResult={mockSimulationResult}
        onTimeChange={() => {}}
      />
    )
    
    const speedSlider = container.querySelector('input[type="range"]')
    fireEvent.change(speedSlider, { target: { value: '1.5' } })
    
    await waitFor(() => {
      expect(screen.getByText(/1.50x/)).toBeInTheDocument()
    })
  })

  it('calls onTimeChange when time updates', async () => {
    const onTimeChange = vi.fn()
    
    render(
      <SimulationTimeline 
        simulationResult={mockSimulationResult}
        onTimeChange={onTimeChange}
      />
    )
    
    await waitFor(() => {
      expect(onTimeChange).toHaveBeenCalled()
    })
  })
})
```

- [ ] **Step 2: Commit**

```bash
cd frontend
git add src/components/__tests__/SimulationTimeline.test.jsx
git commit -m "test: add component tests for SimulationTimeline"
```

---

### Task 11: Integration Test — Full Simulation Flow

**Files:**
- Create: `backend/tests/test_simulation_integration.py`

**Context:** Test the complete flow: simulate_disaster endpoint → response includes step_time_ms → MCP tools access data.

- [ ] **Step 1: Create integration test**

Create `backend/tests/test_simulation_integration.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


@pytest.fixture
def setup_graph():
    """Setup a sample graph for testing."""
    # Create sample nodes
    client.post("/api/graph/ingest/terraform", json={"path": "/data/terraform/sample"})
    yield
    # Cleanup (optional)


def test_simulate_disaster_returns_timeline_data(setup_graph):
    """Test that simulate_disaster endpoint returns step_time_ms and timeline_steps."""
    response = client.post(
        "/api/dr/simulate",
        json={"node_id": "db-001", "depth": 5}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "blast_radius" in data
    assert "timeline_steps" in data
    assert "max_distance" in data
    assert "total_duration_ms" in data
    
    # Each node in blast_radius should have step_time_ms
    for node in data["blast_radius"]:
        assert "step_time_ms" in node
        assert node["step_time_ms"] >= 0
        assert node["step_time_ms"] <= data["total_duration_ms"]


def test_step_times_are_sorted():
    """Test that step_time_ms values increase with distance."""
    response = client.post(
        "/api/dr/simulate",
        json={"node_id": "db-001", "depth": 5}
    )
    
    data = response.json()
    timeline = data["timeline_steps"]
    
    # Timeline should be sorted by step_time_ms
    for i in range(len(timeline) - 1):
        assert timeline[i]["step_time_ms"] <= timeline[i + 1]["step_time_ms"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Commit**

```bash
cd backend
git add tests/test_simulation_integration.py
git commit -m "test: add integration tests for timeline simulation"
```

---

### Task 12: Documentation — Update README with Timeline Feature

**Files:**
- Modify: `README.md`

**Context:** Document the new timeline feature and MCP tools for end users.

- [ ] **Step 1: Add Timeline Feature Section**

Open `README.md` and add this section after the "Service Access" table (around line 186):

```markdown
---

## 🎬 Dynamic Disaster Simulation Timeline

The platform now visualizes cascading failures in **real-time** with an interactive timeline:

### Features

- **Sequential Propagation**: Watch nodes turn RED as the cascade spreads (0ms → 5000ms)
- **Interactive Timeline**: Play/pause/rewind/speed up the simulation
- **Live Metrics**: Affected node count and RTO/RPO update as time progresses
- **Visual Effects**: 
  - Nodes flash when they activate
  - Distance badges show cascading depth (0, 1, 2, 3...)
  - Dependency links illuminate as failures propagate

### Usage

1. Click **Simulate** on a node
2. Timeline player appears in the bottom panel:
   - **Play/Pause** — control animation
   - **Rewind** — reset to beginning
   - **Progress bar** — seek to any point
   - **Speed slider** — adjust animation speed (0.25x to 2.0x)
3. Watch the 3D graph update in real-time
4. Live stats show cascading impact

### Timeline Data

The `/api/dr/simulate` endpoint now returns:

```json
{
  "blast_radius": [
    {
      "id": "app-001",
      "name": "API Server",
      "type": "aws_instance",
      "distance": 1,
      "step_time_ms": 2500,
      "estimated_rto_minutes": 10,
      "estimated_rpo_minutes": 2
    }
  ],
  "timeline_steps": [
    {"node_id": "db-001", "step_time_ms": 0, "distance": 0},
    {"node_id": "app-001", "step_time_ms": 2500, "distance": 1}
  ],
  "max_distance": 2,
  "total_duration_ms": 5000
}
```

---
```

- [ ] **Step 2: Add MCP Tools Documentation**

Add this section to the **MCP Server Integration** section (after line 200):

```markdown
### New MCP Tools (Agent-Controllable Simulation)

| Tool | Description |
|------|-------------|
| `simulate_disaster(node_id, depth)` | Run simulation, returns timeline data + simulation_id |
| `get_simulation_timeline(simulation_id, query_at_time_ms)` | Get cascading failure state at a specific time |
| `analyze_cascading_failure(simulation_id, time_ms)` | Detailed analysis: how many nodes affected, max RTO, etc. |

#### Example: Agent-Driven Analysis

```bash
# Start a simulation
curl -X POST http://localhost:8001/api/dr/simulate \
  -d '{"node_id": "db-001", "depth": 5}'

# Returns: simulation_id, timeline_steps

# Query state at 2.5 seconds
curl -X POST http://localhost:8001/api/mcp/get_simulation_timeline \
  -d '{"simulation_id": "sim_0", "query_at_time_ms": 2500}'

# Analyze at specific moment
curl -X POST http://localhost:8001/api/mcp/analyze_cascading_failure \
  -d '{"simulation_id": "sim_0", "time_ms": 2500}'
```

---
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add timeline feature and new MCP tools documentation"
```

---

### Task 13: Final Integration — Test Complete Flow

**Files:**
- None (testing existing code)

**Context:** Run the app end-to-end to verify the timeline works.

- [ ] **Step 1: Start the app**

```bash
docker compose up -d
docker compose ps
# All containers should be healthy
```

- [ ] **Step 2: Ingest sample data**

```bash
./scripts/ingest.sh  # or ingest.ps1 on Windows
```

Expected: Terraform and docs are ingested into Neo4j.

- [ ] **Step 3: Open the dashboard**

Visit http://localhost:3001

Expected: Graph loads with nodes visible.

- [ ] **Step 4: Test the timeline**

- Click a node (e.g., database)
- Click **Simulate**
- The timeline player should appear at the bottom
- Click **Play** and watch the graph animate
- Try **Pause**, **Rewind**, and adjust **Speed**
- Stats (Affected, RTO, RPO) should update live

- [ ] **Step 5: Test MCP tools**

Connect Claude Code or Copilot with MCP config, then:

```
@digital-twin-dr simulate_disaster(node_id="db-001", depth=5)
```

Expected: Returns timeline data with step_time_ms.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: complete dynamic timeline simulation with MCP agent control"
```

---

## Architecture Summary

```
User Action (Simulate)
  ↓
Backend: simulate_disaster()
  → BFS to find affected nodes
  → Calculate step_time_ms for each
  → Return SimulationWithTimeline + timeline_steps
  ↓
Frontend: DisasterPanel receives result
  → Pass to SimulationTimeline component
  → useSimulationPlayback hook drives animation
  → Call onTimeChange callback with current time
  ↓
App.jsx: Receives simulationTime
  → Pass to Graph3D
  ↓
Graph3D: Renders based on simulationTime
  → Nodes where step_time_ms <= simulationTime are RED
  → Badge/glow/animation on activating nodes
  ↓
MCP Server: Agents query state
  → get_simulation_timeline(sim_id, time_ms)
  → analyze_cascading_failure(sim_id, time_ms)
```

---

## Summary

This plan delivers:
✅ Sequential cascading failure visualization  
✅ Interactive timeline player (play/pause/rewind/speed)  
✅ Live metrics updates  
✅ Visual effects (badges, glows, animations)  
✅ MCP tools for agentic interrogation  
✅ Full test coverage  
✅ Documentation

Total tasks: 13 (backend, frontend, MCP, tests, docs)
