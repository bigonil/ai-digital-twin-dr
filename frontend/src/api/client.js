import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getTopology = () =>
  api.get('/graph/topology').then(r => r.data)

export const getNodes = () =>
  api.get('/graph/nodes').then(r => r.data)

export const simulateDisaster = (nodeId, depth = 5) =>
  api.post('/dr/simulate', { node_id: nodeId, depth }).then(r => r.data)

export const resetNode = (nodeId) =>
  api.post(`/dr/reset/${nodeId}`).then(r => r.data)

export const getNodeHealth = (nodeId) =>
  api.get(`/metrics/health/${nodeId}`).then(r => r.data)

export const getReplicationLag = () =>
  api.get('/metrics/replication-lag').then(r => r.data)

export const getDrift = () =>
  api.get('/dr/drift').then(r => r.data)

export const ingestTerraform = (directory) =>
  api.post('/graph/ingest/terraform', { directory }).then(r => r.data)
