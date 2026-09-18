/**
 * mapLayout.js
 * Tiered layout algorithm for positioning infrastructure nodes in a 2D SVG canvas.
 *
 * Strategy:
 * 1. Group nodes by type into architectural tiers (LB → compute → data → storage)
 * 2. Space nodes horizontally within each tier
 * 3. Assign fixed y per tier
 * 4. Apply collision prevention nudging
 * 5. Return deterministic positions
 */

// Node type to architectural tier mapping
const TIER_ORDER = {
  // Tier 0: Entry points / Load balancers
  aws_lb: 0,
  aws_elb: 0,
  aws_alb: 0,
  aws_nlb: 0,

  // Tier 1: Compute / Application servers
  aws_instance: 1,
  aws_autoscaling_group: 1,
  aws_lambda: 1,
  aws_ecs_service: 1,
  CodeFunction: 1,
  aws_eks_cluster: 1,

  // Tier 2: Data / Queues / Caches
  aws_db_instance: 2,
  aws_rds_cluster: 2,
  aws_elasticache_cluster: 2,
  aws_sqs_queue: 2,
  aws_kinesis_stream: 2,
  aws_dynamodb_table: 2,
  aws_memcached: 2,
  aws_redis: 2,

  // Tier 3: Storage / Backup
  aws_s3_bucket: 3,
  aws_ebs_volume: 3,
  aws_efs: 3,
  Document: 3,
  aws_backup: 3,

  // Default: Middle tier for unknowns
  _default: 2,
}

/**
 * Determine architectural tier for a node type
 */
function getNodeTier(nodeType) {
  // Exact match
  if (TIER_ORDER[nodeType]) return TIER_ORDER[nodeType]

  // Partial match (e.g., "aws_instance_profile" matches "aws_instance")
  for (const [type, tier] of Object.entries(TIER_ORDER)) {
    if (type !== '_default' && nodeType.includes(type)) {
      return tier
    }
  }

  // Fallback
  return TIER_ORDER._default
}

/**
 * Compute layout for all nodes
 * Returns a Map of nodeId → { x, y, node }
 *
 * @param {Object[]} nodes - Array of InfraNode objects with id, type, name, region, az
 * @param {Object[]} edges - Array of InfraEdge objects (not used for positioning, but for validation)
 * @param {number} viewWidth - SVG canvas width (default 900)
 * @param {number} viewHeight - SVG canvas height (default 580)
 * @returns {Map<string, {x: number, y: number, node: Object}>}
 */
export function computeLayout(nodes, edges = [], viewWidth = 900, viewHeight = 580) {
  const positions = new Map()

  if (!nodes || nodes.length === 0) {
    return positions
  }

  // Step 1: Group nodes by tier
  const tierMap = {}
  for (let i = 0; i < 5; i++) tierMap[i] = []

  for (const node of nodes) {
    const tier = getNodeTier(node.type)
    tierMap[tier].push(node)
  }

  // Step 2: Sort within each tier by region/az for visual clustering
  for (let tier = 0; tier < 5; tier++) {
    tierMap[tier].sort((a, b) => {
      const regionA = a.region || ''
      const regionB = b.region || ''
      if (regionA !== regionB) return regionA.localeCompare(regionB)
      const azA = a.az || ''
      const azB = b.az || ''
      return azA.localeCompare(azB)
    })
  }

  // Step 3: Assign x and y coordinates per tier
  const tierHeight = 110
  const topPadding = 40
  const sidePadding = 40
  const minNodeSpacing = 30

  for (let tier = 0; tier < 5; tier++) {
    const nodesInTier = tierMap[tier]
    if (nodesInTier.length === 0) continue

    const y = topPadding + tier * tierHeight

    // Distribute nodes horizontally across the tier
    const usableWidth = viewWidth - 2 * sidePadding
    for (let i = 0; i < nodesInTier.length; i++) {
      const node = nodesInTier[i]
      let x

      if (nodesInTier.length === 1) {
        // Center single node
        x = viewWidth / 2
      } else {
        // Evenly space multiple nodes
        const fraction = i / (nodesInTier.length - 1)
        x = sidePadding + fraction * usableWidth
      }

      positions.set(node.id, { x, y, node })
    }
  }

  // Step 4: Apply collision prevention (nudge overlapping nodes)
  const positioned = Array.from(positions.values())
  for (let i = 0; i < positioned.length; i++) {
    for (let j = i + 1; j < positioned.length; j++) {
      const p1 = positioned[i]
      const p2 = positioned[j]

      // Only check nodes in the same tier
      if (Math.abs(p1.y - p2.y) > 5) continue

      const dx = p2.x - p1.x
      if (Math.abs(dx) < minNodeSpacing) {
        // Nodes are too close; nudge horizontally
        const nudge = (minNodeSpacing - Math.abs(dx)) / 2 + 2
        if (dx > 0) {
          p2.x += nudge
          p1.x -= nudge
        } else {
          p1.x += nudge
          p2.x -= nudge
        }
      }
    }
  }

  return positions
}

/**
 * Get edge path coordinates for drawing a line and flow animation
 * @param {Map} positions - Result from computeLayout
 * @param {Object} edge - InfraEdge with source and target id
 * @returns {{x1, y1, x2, y2, midX, midY} | null}
 */
export function getEdgePath(positions, edge) {
  if (!positions.has(edge.source) || !positions.has(edge.target)) {
    return null
  }

  const p1 = positions.get(edge.source)
  const p2 = positions.get(edge.target)

  const x1 = p1.x
  const y1 = p1.y
  const x2 = p2.x
  const y2 = p2.y

  const midX = (x1 + x2) / 2
  const midY = (y1 + y2) / 2

  return { x1, y1, x2, y2, midX, midY }
}

/**
 * Get edge path as SVG quadratic Bezier curve for smooth, animated propagation
 * @param {Map} positions - Result from computeLayout
 * @param {Object} edge - InfraEdge with source and target id
 * @returns {{x1, y1, x2, y2, d: string, cpX, cpY} | null}
 */
export function getBezierPath(positions, edge) {
  const linear = getEdgePath(positions, edge)
  if (!linear) return null

  const { x1, y1, x2, y2, midX, midY } = linear

  // Offset control point laterally to create gentle curve
  // Perpendicular to edge direction, scaled by 0.15x edge length
  const dx = x2 - x1
  const dy = y2 - y1
  const cpX = midX - dy * 0.15
  const cpY = midY + dx * 0.15

  return {
    x1, y1, x2, y2,
    midX, midY,
    cpX, cpY,
    d: `M ${x1} ${y1} Q ${cpX} ${cpY} ${x2} ${y2}`,
  }
}

/**
 * Get the Euclidean distance between two positioned nodes
 * (used for edge thickness weighting, optional)
 */
export function getDistance(p1, p2) {
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  return Math.sqrt(dx * dx + dy * dy)
}

/**
 * Compute a deterministic color based on node type
 * (for optional type-based node coloring)
 */
export const TYPE_COLORS = {
  aws_lb: '#3b82f6',
  aws_instance: '#8b5cf6',
  aws_db_instance: '#ec4899',
  aws_rds_cluster: '#f43f5e',
  aws_s3_bucket: '#f59e0b',
  aws_lambda: '#06b6d4',
  _default: '#6b7280',
}

export function getTypeColor(nodeType) {
  if (TYPE_COLORS[nodeType]) return TYPE_COLORS[nodeType]
  for (const [type, color] of Object.entries(TYPE_COLORS)) {
    if (type !== '_default' && nodeType.includes(type)) {
      return color
    }
  }
  return TYPE_COLORS._default
}
