# Digital Twin DR Platform — Frontend

React-based frontend for the Digital Twin Disaster Recovery simulation platform. Visualizes infrastructure topology and enables disaster simulation scenarios.

## Features

- **Topology Viewer**: Browse and select infrastructure nodes from the neo4j database with search and filtering
- **Disaster Simulation**: Trigger cascading failure simulations on selected nodes with configurable depth
- **2D Propagation Visualization**: 
  - Concentric circle layout showing disaster propagation distance (hop-by-hop)
  - Real-time node state rendering (healthy → degraded → failed)
  - Animated edge flows showing propagation paths
  - Full-screen "WoW" visualization with glow effects and pulsing animations
  - Synchronized with timeline playback for temporal visualization
- **Timeline Playback**: Replay disaster simulations step-by-step with play/pause/speed controls
- **Metrics Dashboard**: Monitor node health, RTO/RPO metrics, and replication lag
- **Real-time Updates**: Auto-refetch data every 10 seconds via React Query
- **Tabular View**: Detailed blast radius table with node names, types, and RTO values

## Stack

- **Framework**: React 18.3
- **Build Tool**: Vite 5.4
- **Styling**: Tailwind CSS with custom dark theme
- **Data Fetching**: axios + @tanstack/react-query
- **Icons**: lucide-react
- **Charting**: recharts (for future dashboard enhancements)

## Setup

### Prerequisites
- Node.js 18+
- Backend API running on `http://localhost:8001` (or configured via Vite proxy)

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

Dev server runs on `http://localhost:3000`

### Production Build

```bash
npm run build
npm run preview
```

## Architecture

### Components

- **App.jsx**: Main layout with header, topology viewer, sidebar, and disaster panel
- **TopologyViewer.jsx**: Tree view of infrastructure grouped by type with search/filter capability
- **DisasterPanel.jsx**: Simulation controls (depth input, Simulate/Reset buttons, Map/Table toggle, Fullscreen button)
- **DisasterVisualization.jsx**: Compact 2D map view with concentric circle layout
- **DisasterVisualizationTab.jsx**: Full-screen immersive visualization with:
  - Animated glow effects for actively failing nodes
  - Flowing edge animations showing propagation
  - Gradient backgrounds and distance rings
  - Real-time synchronization with timeline playback
  - Legend and node statistics
- **SimulationTimeline.jsx**: Timeline player for replaying disaster steps with speed controls
- **MetricsSidebar.jsx**: Metrics display for selected node (RTO, RPO, status)
- **Graph3D.jsx**: 3D force-directed graph (currently disabled due to react-force-graph dependency issues)

### API Integration

All API calls proxy through `/api` to backend:

```
GET  /api/graph/topology          → Infrastructure topology (nodes + edges)
POST /api/dr/simulate             → Run disaster simulation
POST /api/dr/reset/{nodeId}       → Reset node state
GET  /api/metrics/replication-lag → Replication lag metric
GET  /api/metrics/health/{nodeId} → Node health status
```

### State Management

- **React Query**: Server state (topology, metrics)
- **React Hooks** (useState): Local UI state (selected node, simulation time)

## Configuration

**Vite Proxy** (`vite.config.js`):
```javascript
proxy: {
  '/api': {
    target: 'http://localhost:8001',  // Backend URL
    changeOrigin: true,
  },
}
```

**React Query** (`src/main.jsx`):
- `staleTime: 10s`
- `refetchInterval: 10s`

## Usage

### Running a Disaster Simulation

1. **Select a Node**: Click on any infrastructure node in the TopologyViewer (left panel)
2. **Configure Simulation**: Set the propagation depth (default: 5 hops)
3. **Simulate**: Click the red "Simulate" button
4. **Review Results**:
   - Timeline appears below showing the cascade sequence
   - Blast radius table shows all affected nodes
   - Click **Fullscreen** button to open immersive 2D visualization
5. **Playback**:
   - Click **Play** to animate the disaster propagation in real-time
   - Adjust **Speed** slider to control animation speed
   - Nodes will glow red as they fail in sequence
   - Edges show blue flow animation indicating propagation paths

### Visualization Details

**2D Propagation Map**:
- Center point: Initial failure node
- Concentric circles: Propagation distance (hop count)
- Node colors:
  - 🟢 Green: Healthy (normal operation)
  - 🟡 Amber: Degraded (performance issues)
  - 🔴 Red: Failed
  - 🔴 Bright Red: Currently failing (with glow animation)
- Edge flows: Blue animated lines showing cascade propagation
- Timeline sync: Nodes animate in real-time during playback

## Development Notes

### Known Issues

1. **Graph3D disabled**: react-force-graph has unresolvable sub-dependency conflicts (aframe-extras, three.js multiple instances). TopologyViewer and 2D DisasterVisualization provide functional alternatives.
2. **Update depth warning**: Maximum update depth exceeded warning in console during timeline playback (harmless, useEffect dependencies optimized)

### Recent Changes (v1.1)

- Added DisasterVisualizationTab for full-screen immersive 2D visualization
- Implemented animated propagation effects with glow and flow animations
- Added Fullscreen button to DisasterPanel
- Enhanced timeline synchronization with real-time node state rendering
- Added comprehensive legend and node statistics display

### Future Enhancements

1. Re-enable 3D graph visualization once dependency conflicts are resolved
2. 3D node positioning synchronized with 2D propagation map
3. Implement live metrics streaming (WebSocket)
4. Add historical simulation playback and comparison
5. Export simulation reports (JSON/PDF)
6. Performance metrics overlay during timeline playback
7. Keyboard shortcuts for simulation controls

## Troubleshooting

### Dev Server Issues

```bash
# Hard refresh frontend (clear Vite cache)
Ctrl+Shift+R

# Full clean rebuild
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### API Connection Issues

Check backend is running:
```bash
curl -I http://localhost:8001/api/graph/topology
```

If backend is on different port, update `vite.config.js` proxy target.

## Testing

```bash
# No tests configured yet
# Use browser DevTools (F12) to debug API calls and React state
```
