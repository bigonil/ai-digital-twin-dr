/**
 * useNodeMetrics.js
 * Generates deterministic, seeded mock metrics for infrastructure nodes.
 *
 * Strategy:
 * - Hash node id to deterministic seed
 * - Use Linear Congruential Generator (LCG) for pseudo-random floats
 * - Type-aware baselines (DBs high memory, LBs high request rate)
 * - Generate 12-point sparkline history for each metric
 * - Guarantees: same node = same values (deterministic)
 *              different nodes = different values (seeded)
 */

import { useMemo } from 'react'

/**
 * djb2 hash algorithm — converts string to deterministic integer
 */
function hashStr(str) {
  let h = 5381
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) ^ str.charCodeAt(i)
  }
  return Math.abs(h)
}

/**
 * Linear Congruential Generator — produces deterministic float [0, 1)
 * @param {number} seed - base seed value
 * @param {number} index - additional entropy (different metric gets different value)
 * @returns {number} float in range [0, 1)
 */
function seededRand(seed, index) {
  const a = 1664525
  const c = 1013904223
  const m = 2 ** 32
  return ((seed * a + c + index * 1337) % m) / m
}

/**
 * React hook: generate realistic per-node metrics
 * @param {Object} node - InfraNode object with id, type, name, region, az
 * @returns {Object | null} Metrics object with current values and sparkline history
 */
export default function useNodeMetrics(node) {
  return useMemo(() => {
    if (!node) return null

    const seed = hashStr(node.id)
    const r = (i) => seededRand(seed, i)

    // Type detection for baseline adjustment
    const isDatabase = node.type.includes('db') || node.type.includes('rds') || node.type.includes('dynamodb')
    const isLoadBalancer = node.type.includes('lb') || node.type.includes('elb') || node.type.includes('alb')
    const isStorage = node.type.includes('s3') || node.type.includes('ebs') || node.type.includes('efs')
    const isCompute = node.type.includes('instance') || node.type.includes('lambda') || node.type.includes('ecs')

    // Current metric values with type-aware baselines
    const cpu = isDatabase ? 35 + r(0) * 45 : isLoadBalancer ? 25 + r(0) * 40 : 30 + r(0) * 50
    const memory = isDatabase ? 65 + r(1) * 30 : isLoadBalancer ? 30 + r(1) * 50 : 40 + r(1) * 50
    const requestRate = isLoadBalancer ? 1200 + r(2) * 4000 : isDatabase ? 100 + r(2) * 300 : 200 + r(2) * 800
    const errorRate = Math.max(0, r(3) * 2.5 + (isDatabase ? -0.5 : 0))
    const latencyP50 = isDatabase ? 15 + r(4) * 50 : 5 + r(4) * 30
    const latencyP95 = isDatabase ? 50 + r(5) * 150 : 20 + r(5) * 100
    const latencyP99 = isDatabase ? 150 + r(6) * 400 : 80 + r(6) * 300
    const throughput = isDatabase ? 250 + r(7) * 1750 : isLoadBalancer ? 500 + r(7) * 2000 : 50 + r(7) * 500
    const diskIo = isDatabase ? 80 + r(8) * 220 : isStorage ? 100 + r(8) * 300 : 5 + r(8) * 35
    const replicationLag = isDatabase ? r(9) * 12 : null // seconds, only for DBs

    // Generate 12-point sparkline history for key metrics
    // Each point adds some variance around the current value
    const cpuHistory = Array.from({ length: 12 }, (_, i) =>
      Math.max(0, Math.min(100, cpu + (seededRand(seed, i + 100) - 0.5) * 20))
    )

    const memHistory = Array.from({ length: 12 }, (_, i) =>
      Math.max(0, Math.min(100, memory + (seededRand(seed, i + 200) - 0.5) * 15))
    )

    const latHistory = Array.from({ length: 12 }, (_, i) =>
      Math.max(1, latencyP95 + (seededRand(seed, i + 300) - 0.5) * 40)
    )

    const errHistory = Array.from({ length: 12 }, (_, i) =>
      Math.max(0, errorRate + (seededRand(seed, i + 400) - 0.5) * 1.5)
    )

    return {
      // Current metrics
      cpu: Math.round(cpu * 10) / 10,
      memory: Math.round(memory * 10) / 10,
      requestRate: Math.round(requestRate),
      errorRate: Math.round(errorRate * 100) / 100,
      latencyP50: Math.round(latencyP50 * 10) / 10,
      latencyP95: Math.round(latencyP95 * 10) / 10,
      latencyP99: Math.round(latencyP99 * 10) / 10,
      throughput: Math.round(throughput),
      diskIo: Math.round(diskIo * 10) / 10,
      replicationLag: replicationLag !== null ? Math.round(replicationLag * 10) / 10 : null,

      // Sparkline data (12 historical points)
      cpuHistory: cpuHistory.map((v) => Math.round(v * 10) / 10),
      memHistory: memHistory.map((v) => Math.round(v * 10) / 10),
      latHistory: latHistory.map((v) => Math.round(v * 10) / 10),
      errHistory: errHistory.map((v) => Math.round(v * 100) / 100),

      // Type indicators (optional, for UI logic)
      isDatabase,
      isLoadBalancer,
      isStorage,
      isCompute,
    }
  }, [node?.id, node?.type])
}
