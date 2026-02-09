/**
 * Isoflow Data Transformer
 *
 * Converts Cytoscape.js elements (from /api/network/map) into the Isoflow
 * initialData format for isometric network diagram rendering.
 *
 * TESTING: This module is experimental — evaluating whether isometric
 * visualization provides value for network topology diagrams.
 */

// Device type → isoflow icon ID mapping
const DEVICE_ICON_MAP = {
  router: 'router',
  switch: 'switch-module',
  firewall: 'firewall',
  server: 'server',
  workstation: 'desktop',
  printer: 'printer',
  iot: 'cube',
  unknown: 'block',
}

// Fallback icon for unrecognized device types
const DEFAULT_ICON = 'block'

// Connection type → color mapping
const CONNECTION_COLORS = {
  same_subnet: { id: 'color-same-subnet', value: '#6b7280' },
  cross_subnet: { id: 'color-cross-subnet', value: '#f59e0b' },
  cross_vlan: { id: 'color-cross-vlan', value: '#f97316' },
  route: { id: 'color-route', value: '#22c55e' },
  internet: { id: 'color-internet', value: '#06b6d4' },
  to_gateway: { id: 'color-to-gateway', value: '#a855f7' },
}

// Connection type → line style
const CONNECTION_STYLES = {
  same_subnet: 'SOLID',
  cross_subnet: 'DASHED',
  cross_vlan: 'DASHED',
  route: 'DOTTED',
  internet: 'SOLID',
  to_gateway: 'SOLID',
}

/**
 * Extract only host nodes (not compound/internet nodes) from Cytoscape elements.
 */
export function extractHostNodes(elements) {
  const compoundTypes = new Set(['vlan', 'subnet', 'internet', 'public_ips'])
  return (elements.nodes || []).filter(
    (n) => !compoundTypes.has(n.data.type)
  )
}

/**
 * Extract subnet/VLAN compound nodes for rectangle zones.
 */
export function extractCompoundNodes(elements) {
  const zoneTypes = new Set(['vlan', 'subnet'])
  return (elements.nodes || []).filter(
    (n) => zoneTypes.has(n.data.type)
  )
}

/**
 * Compute tile positions for hosts using a simple grid layout.
 *
 * Groups hosts by their parent (subnet/VLAN) and arranges each group
 * in a grid block on the isometric plane. Groups are placed in rows,
 * with spacing between them.
 *
 * Returns a Map of nodeId → { x, y } tile coordinates.
 */
export function computeTilePositions(hostNodes, compoundNodes) {
  const positions = new Map()

  // Group hosts by parent
  const groups = new Map()
  const noParent = []

  for (const node of hostNodes) {
    const parent = node.data.parent
    if (parent) {
      if (!groups.has(parent)) groups.set(parent, [])
      groups.get(parent).push(node)
    } else {
      noParent.push(node)
    }
  }

  // Add ungrouped hosts as their own group
  if (noParent.length > 0) {
    groups.set('__ungrouped__', noParent)
  }

  // Layout groups in a staggered grid arrangement
  const GROUP_SPACING = 6 // tiles between groups
  const NODE_SPACING = 3 // tiles between nodes within a group
  const COLS_PER_GROUP = 4 // max columns within a group

  let groupOffsetX = 2
  let groupOffsetY = 2
  let maxGroupHeight = 0
  let groupCol = 0
  const MAX_GROUPS_PER_ROW = 3

  for (const [, nodes] of groups) {
    for (let i = 0; i < nodes.length; i++) {
      const col = i % COLS_PER_GROUP
      const row = Math.floor(i / COLS_PER_GROUP)
      const x = groupOffsetX + col * NODE_SPACING
      const y = groupOffsetY + row * NODE_SPACING
      positions.set(nodes[i].data.id, { x, y })

      const rowsNeeded = Math.floor(i / COLS_PER_GROUP) + 1
      if (rowsNeeded * NODE_SPACING > maxGroupHeight) {
        maxGroupHeight = rowsNeeded * NODE_SPACING
      }
    }

    groupCol++
    const groupWidth = Math.min(nodes.length, COLS_PER_GROUP) * NODE_SPACING
    groupOffsetX += groupWidth + GROUP_SPACING

    if (groupCol >= MAX_GROUPS_PER_ROW) {
      groupCol = 0
      groupOffsetX = 2
      groupOffsetY += maxGroupHeight + GROUP_SPACING
      maxGroupHeight = 0
    }
  }

  return positions
}

/**
 * Compute bounding rectangles for compound nodes (subnets/VLANs).
 *
 * Returns an array of isoflow rectangle definitions based on the
 * tile positions of the child nodes.
 */
export function computeRectangles(compoundNodes, hostNodes, tilePositions) {
  const rectangles = []

  // VLAN colors (cycling through a palette)
  const VLAN_COLORS = [
    { id: 'zone-blue', value: 'rgba(59, 130, 246, 0.15)' },
    { id: 'zone-green', value: 'rgba(34, 197, 94, 0.15)' },
    { id: 'zone-purple', value: 'rgba(168, 85, 247, 0.15)' },
    { id: 'zone-amber', value: 'rgba(245, 158, 11, 0.15)' },
    { id: 'zone-red', value: 'rgba(239, 68, 68, 0.15)' },
    { id: 'zone-cyan', value: 'rgba(6, 182, 212, 0.15)' },
  ]

  let colorIdx = 0

  for (const compound of compoundNodes) {
    // Find children positioned within this compound node
    const children = hostNodes.filter((n) => n.data.parent === compound.data.id)
    if (children.length === 0) continue

    // Get bounding box from tile positions
    const childPositions = children
      .map((c) => tilePositions.get(c.data.id))
      .filter(Boolean)

    if (childPositions.length === 0) continue

    const minX = Math.min(...childPositions.map((p) => p.x)) - 1
    const minY = Math.min(...childPositions.map((p) => p.y)) - 1
    const maxX = Math.max(...childPositions.map((p) => p.x)) + 1
    const maxY = Math.max(...childPositions.map((p) => p.y)) + 1

    const color = VLAN_COLORS[colorIdx % VLAN_COLORS.length]
    colorIdx++

    rectangles.push({
      id: `rect-${compound.data.id}`,
      color: color.id,
      from: { x: minX, y: minY },
      to: { x: maxX, y: maxY },
    })
  }

  return { rectangles, zoneColors: VLAN_COLORS.slice(0, colorIdx) }
}

/**
 * Build isoflow connectors from Cytoscape edges.
 *
 * Only includes edges where both source and target are in the host node set
 * (i.e., skips edges to compound nodes).
 */
export function buildConnectors(edges, hostNodeIds) {
  const connectors = []
  const hostIdSet = new Set(hostNodeIds)

  for (const edge of edges || []) {
    const { source, target, connection_type, id } = edge.data || {}
    if (!source || !target) continue
    if (!hostIdSet.has(source) || !hostIdSet.has(target)) continue

    const colorDef = CONNECTION_COLORS[connection_type] || CONNECTION_COLORS.same_subnet
    const style = CONNECTION_STYLES[connection_type] || 'SOLID'

    connectors.push({
      id: id || `conn-${source}-${target}`,
      color: colorDef.id,
      style,
      width: connection_type === 'cross_vlan' ? 2 : 1,
      anchors: [{ item: source }, { item: target }],
    })
  }

  return connectors
}

/**
 * Main transformer: converts Cytoscape elements into isoflow initialData.
 *
 * @param {Object} elements - Cytoscape elements { nodes: [...], edges: [...] }
 * @param {Object} options - Optional overrides
 * @returns {Object} Isoflow initialData object
 */
export function transformToIsoflow(elements, options = {}) {
  const { title = 'Network Topology' } = options

  if (!elements || !elements.nodes || elements.nodes.length === 0) {
    return {
      title,
      icons: [],
      colors: [],
      items: [],
      views: [{ id: 'main', name: 'Network', items: [], connectors: [], rectangles: [] }],
    }
  }

  const hostNodes = extractHostNodes(elements)
  const compoundNodes = extractCompoundNodes(elements)
  const tilePositions = computeTilePositions(hostNodes, compoundNodes)

  // Build icon list from what's actually used
  const usedIconIds = new Set()
  for (const node of hostNodes) {
    const iconId = DEVICE_ICON_MAP[node.data.device_type] || DEFAULT_ICON
    usedIconIds.add(iconId)
  }

  // Items (logical node definitions)
  const items = hostNodes.map((node) => ({
    id: node.data.id,
    name: node.data.label || node.data.hostname || node.data.ip || node.data.id,
    description: buildNodeDescription(node.data),
    icon: DEVICE_ICON_MAP[node.data.device_type] || DEFAULT_ICON,
  }))

  // ViewItems (placed instances on the grid)
  const viewItems = hostNodes
    .map((node) => {
      const pos = tilePositions.get(node.data.id)
      if (!pos) return null
      return {
        id: node.data.id,
        tile: pos,
      }
    })
    .filter(Boolean)

  // Connectors
  const hostNodeIds = hostNodes.map((n) => n.data.id)
  const connectors = buildConnectors(elements.edges, hostNodeIds)

  // Rectangles for compound nodes
  const { rectangles, zoneColors } = computeRectangles(
    compoundNodes,
    hostNodes,
    tilePositions
  )

  // Collect all colors
  const colors = [
    ...Object.values(CONNECTION_COLORS),
    ...zoneColors,
  ]

  // Deduplicate colors by id
  const colorMap = new Map()
  for (const c of colors) {
    colorMap.set(c.id, c)
  }

  return {
    title,
    icons: [], // Will be injected from isopacks at render time
    colors: Array.from(colorMap.values()),
    items,
    views: [
      {
        id: 'main',
        name: 'Network Topology',
        items: viewItems,
        connectors,
        rectangles,
      },
    ],
  }
}

/**
 * Build a markdown description string for a host node.
 */
function buildNodeDescription(data) {
  const lines = []
  if (data.ip) lines.push(`**IP:** ${data.ip}`)
  if (data.mac) lines.push(`**MAC:** ${data.mac}`)
  if (data.os) lines.push(`**OS:** ${data.os}`)
  if (data.vendor) lines.push(`**Vendor:** ${data.vendor}`)
  if (data.device_type && data.device_type !== 'unknown') {
    lines.push(`**Type:** ${data.device_type}`)
  }
  if (data.open_ports) lines.push(`**Open Ports:** ${data.open_ports}`)
  if (data.subnet) lines.push(`**Subnet:** ${data.subnet}`)
  if (data.vlan_name) {
    lines.push(`**VLAN:** ${data.vlan_name} (${data.vlan_id})`)
  }
  if (data.is_gateway) lines.push('**Role:** Gateway')
  return lines.join('\n\n') || undefined
}

// Re-export constants for testing
export { DEVICE_ICON_MAP, DEFAULT_ICON, CONNECTION_COLORS, CONNECTION_STYLES }
