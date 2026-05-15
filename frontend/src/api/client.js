import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

/**
 * Response interceptor to extract user-friendly error messages.
 * Catches error responses and re-throws with enhanced error object.
 */
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If error has a response from server (4xx, 5xx)
    if (error.response) {
      const { status, data } = error.response
      const message = data?.message || data?.detail || 'An error occurred'
      const errorCode = data?.error || 'ERROR'
      const requestId = data?.request_id || 'unknown'

      // Create enhanced error object with user-friendly message
      const enhancedError = new Error(message)
      enhancedError.status = status
      enhancedError.code = errorCode
      enhancedError.requestId = requestId
      enhancedError.details = data

      // Log error details for debugging
      console.error(`[${errorCode}] ${message} (req: ${requestId})`, data)

      // Show user-friendly toast/alert based on status
      if (status === 404) {
        enhancedError.userMessage = `Resource not found: ${message}`
      } else if (status === 400) {
        enhancedError.userMessage = `Invalid request: ${message}`
      } else if (status === 403) {
        enhancedError.userMessage = `Access denied: ${message}`
      } else if (status === 429) {
        enhancedError.userMessage = `Too many requests. Please wait before retrying.`
      } else if (status >= 500) {
        enhancedError.userMessage = `Server error: ${message}. Please contact support with request ID: ${requestId}`
      } else {
        enhancedError.userMessage = message
      }

      return Promise.reject(enhancedError)
    }

    // Network error or no response from server
    if (error.request) {
      error.userMessage = 'Network error: Unable to reach the server. Please check your connection.'
      console.error('Network error:', error.message)
    } else {
      error.userMessage = 'An unexpected error occurred. Please try again.'
      console.error('Error:', error.message)
    }

    return Promise.reject(error)
  }
)

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

// ============================================================================
// RECOVERY PLAYBOOKS (LLM-GENERATED)
// ============================================================================

export const generatePlaybook = (nodeId, forceRegenerate = false) =>
  api.post(`/dr/playbook/${nodeId}?force_regenerate=${forceRegenerate}`).then(r => r.data)

// ============================================================================
// METRICS RANGE (HISTORICAL)
// ============================================================================

export const getMetricsRange = (nodeId, metric, hours = 24) =>
  api.get(`/metrics/range`, { params: { node_id: nodeId, metric, hours } }).then(r => r.data)
