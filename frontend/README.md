# Digital Twin DR Platform — Frontend

React-based frontend for the Digital Twin Disaster Recovery simulation platform. Visualizes infrastructure topology and enables disaster simulation scenarios.

## Features

- **Topology Viewer**: Browse and select infrastructure nodes from the neo4j database
- **Disaster Simulation**: Trigger cascading failure simulations on selected nodes
- **Timeline Playback**: Replay disaster simulations step-by-step with temporal visualization
- **Metrics Dashboard**: Monitor node health, RTO/RPO metrics, and replication lag
- **Real-time Updates**: Auto-refetch data every 10 seconds via React Query

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
- **TopologyViewer.jsx**: Tree view of infrastructure grouped by type, node selection
- **DisasterPanel.jsx**: Simulation controls (depth input, Simulate/Reset buttons)
- **SimulationTimeline.jsx**: Timeline player for replaying disaster steps
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

## Development Notes

### Known Issues

1. **Graph3D disabled**: react-force-graph has unresolvable sub-dependency conflicts (aframe-extras, three.js multiple instances). TopologyViewer provides functional alternative for node selection.

### Future Enhancements

1. Re-enable 3D graph visualization once dependency conflicts are resolved
2. Add 3D node positioning to timeline player
3. Implement live metrics streaming (WebSocket)
4. Add historical simulation playback and comparison
5. Export simulation reports (JSON/PDF)

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
