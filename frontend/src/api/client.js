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

// ============================================================================
// COMPLIANCE & TESTING
// ============================================================================

export const runComplianceAudit = () =>
  api.post('/compliance/run').then(r => r.data)

export const getComplianceReport = () =>
  api.get('/compliance/report').then(r => r.data)

export const downloadComplianceReport = async () => {
  const response = await api.get('/compliance/export', { responseType: 'blob' })
  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', `compliance_report_${new Date().toISOString().split('T')[0]}.json`)
  document.body.appendChild(link)
  link.click()
  link.parentNode.removeChild(link)
}

// ============================================================================
// ARCHITECTURE PLANNING (WHAT-IF)
// ============================================================================

export const runWhatIfSimulation = (payload) =>
  api.post('/whatif/simulate', payload).then(r => r.data)

// ============================================================================
// CHAOS ENGINEERING
// ============================================================================

export const listChaosExperiments = () =>
  api.get('/chaos/experiments').then(r => r.data)

export const runChaosExperiment = (payload) =>
  api.post('/chaos/experiments', payload).then(r => r.data)

export const getChaosExperiment = (id) =>
  api.get(`/chaos/experiments/${id}`).then(r => r.data)

export const submitChaosActuals = (id, payload) =>
  api.post(`/chaos/experiments/${id}/actuals`, payload).then(r => r.data)

export const deleteChaosExperiment = (id) =>
  api.delete(`/chaos/experiments/${id}`).then(r => r.data)

// ============================================================================
// INCIDENT POSTMORTEM
// ============================================================================

export const listPostmortems = () =>
  api.get('/postmortem/reports').then(r => r.data)

export const createPostmortem = (payload) =>
  api.post('/postmortem/reports', payload).then(r => r.data)

export const getPostmortem = (id) =>
  api.get(`/postmortem/reports/${id}`).then(r => r.data)
