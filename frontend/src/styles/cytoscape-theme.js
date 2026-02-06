/**
 * Cytoscape.js stylesheet for Graphēon network topology visualization.
 *
 * Defines visual styling for:
 * - VLAN compound nodes (colored bordered regions)
 * - Subnet compound nodes (nested regions)
 * - Device type nodes (shaped & colored by type)
 * - Connection edges (styled by connection type)
 * - Interaction states (selected, hover)
 *
 * Supports light and dark mode variants.
 */

// ── Shared base styles ──────────────────────────────────────────────

const baseNodeStyles = {
  'content': 'data(label)',
  'text-wrap': 'wrap',
  'text-max-width': '120px',
  'font-family': 'Inter, system-ui, -apple-system, sans-serif',
  'min-zoomed-font-size': 8,
}

const baseEdgeStyles = {
  'curve-style': 'bezier',
  'target-arrow-shape': 'none',
  'line-opacity': 0.7,
  'width': 1.5,
}

// ── Device type configurations ──────────────────────────────────────

const DEVICE_SHAPES = {
  router:      'diamond',
  switch:      'vee',
  firewall:    'star',
  server:      'round-rectangle',
  workstation: 'ellipse',
  printer:     'rectangle',
  iot:         'hexagon',
  unknown:     'ellipse',
}

const DEVICE_COLORS = {
  router:      { bg: '#f97316', border: '#ea580c' },
  switch:      { bg: '#8b5cf6', border: '#7c3aed' },
  firewall:    { bg: '#ef4444', border: '#dc2626' },
  server:      { bg: '#3b82f6', border: '#2563eb' },
  workstation: { bg: '#22c55e', border: '#16a34a' },
  printer:     { bg: '#ec4899', border: '#db2777' },
  iot:         { bg: '#06b6d4', border: '#0891b2' },
  unknown:     { bg: '#6b7280', border: '#4b5563' },
}

// ── Build device type selectors ─────────────────────────────────────

function buildDeviceTypeStyles(isDark) {
  const styles = []

  for (const [type, shape] of Object.entries(DEVICE_SHAPES)) {
    const colors = DEVICE_COLORS[type]
    styles.push({
      selector: `node[device_type="${type}"]`,
      style: {
        'shape': shape,
        'background-color': colors.bg,
        'border-color': colors.border,
        'border-width': 2,
        'width': 'data(node_size)',
        'height': 'data(node_size)',
      }
    })
  }

  return styles
}

// ── Light mode stylesheet ───────────────────────────────────────────

export function getLightStyles() {
  return [
    // ── Default node ────────────────────────────────────────
    {
      selector: 'node',
      style: {
        ...baseNodeStyles,
        'background-color': '#6b7280',
        'border-color': '#4b5563',
        'border-width': 2,
        'font-size': 11,
        'color': '#1f2937',
        'text-halign': 'center',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'overlay-padding': 6,
        'z-index': 10,
      }
    },

    // ── VLAN compound node ──────────────────────────────────
    {
      selector: 'node[type="vlan"]',
      style: {
        'background-color': 'data(color)',
        'background-opacity': 0.08,
        'border-width': 3,
        'border-color': 'data(color)',
        'border-style': 'solid',
        'border-opacity': 0.6,
        'shape': 'round-rectangle',
        'font-size': 16,
        'font-weight': 'bold',
        'color': '#111827',
        'text-halign': 'center',
        'text-valign': 'top',
        'text-margin-y': -8,
        'padding': '40px',
        'z-index': 1,
      }
    },

    // ── Subnet compound node ────────────────────────────────
    {
      selector: 'node[type="subnet"]',
      style: {
        'background-color': 'data(color)',
        'background-opacity': 0.06,
        'border-width': 2,
        'border-color': 'data(color)',
        'border-style': 'dashed',
        'border-opacity': 0.4,
        'shape': 'round-rectangle',
        'font-size': 12,
        'font-weight': 'normal',
        'color': '#4b5563',
        'text-halign': 'center',
        'text-valign': 'top',
        'text-margin-y': -6,
        'padding': '25px',
        'z-index': 2,
      }
    },

    // ── Gateway nodes ───────────────────────────────────────
    {
      selector: 'node[?is_gateway]',
      style: {
        'border-width': 4,
        'border-color': '#ea580c',
        'font-weight': 'bold',
      }
    },

    // ── Device type specific styles ─────────────────────────
    ...buildDeviceTypeStyles(false),

    // ── Default edge ────────────────────────────────────────
    {
      selector: 'edge',
      style: {
        ...baseEdgeStyles,
        'line-color': '#9ca3af',
        'target-arrow-color': '#9ca3af',
      }
    },

    // ── Same subnet edge ────────────────────────────────────
    {
      selector: 'edge[connection_type="same_subnet"]',
      style: {
        'line-color': '#9ca3af',
        'width': 1.5,
        'line-style': 'solid',
        'line-opacity': 0.5,
      }
    },

    // ── Cross-subnet edge ───────────────────────────────────
    {
      selector: 'edge[connection_type="cross_subnet"]',
      style: {
        'line-color': '#f59e0b',
        'width': 2,
        'line-style': 'dashed',
        'line-opacity': 0.7,
        'line-dash-pattern': [8, 4],
      }
    },

    // ── Cross-VLAN edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="cross_vlan"]',
      style: {
        'line-color': '#f97316',
        'width': 2.5,
        'line-style': 'dashed',
        'line-opacity': 0.8,
        'line-dash-pattern': [10, 5],
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#f97316',
        'arrow-scale': 0.8,
      }
    },

    // ── Route path edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="route"]',
      style: {
        'line-color': '#22c55e',
        'width': 2,
        'line-style': 'dotted',
        'line-opacity': 0.7,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#22c55e',
        'arrow-scale': 0.6,
      }
    },

    // ── Internet cloud node ────────────────────────────────
    {
      selector: 'node[type="internet"]',
      style: {
        'background-color': '#0ea5e9',
        'background-opacity': 0.15,
        'border-width': 3,
        'border-color': '#0ea5e9',
        'border-style': 'solid',
        'border-opacity': 0.6,
        'shape': 'ellipse',
        'width': 90,
        'height': 60,
        'font-size': 16,
        'font-weight': 'bold',
        'color': '#0369a1',
        'text-halign': 'center',
        'text-valign': 'center',
        'z-index': 1,
      }
    },

    // Public IPs compound node
    {
      selector: 'node[type="public_ips"]',
      style: {
        'background-color': '#0ea5e9',
        'background-opacity': 0.08,
        'border-color': '#0284c7',
        'border-width': 3,
        'border-style': 'dashed',
        'label': 'data(label)',
        'font-size': 14,
        'font-weight': 'bold',
        'text-halign': 'center',
        'text-valign': 'top',
        'color': '#0c4a6e',
        'padding': '20px',
      }
    },
    // Shared gateway node (multi-homed router)
    {
      selector: 'node[?is_shared_gateway]',
      style: {
        'background-color': '#f97316',
        'border-color': '#c2410c',
        'border-width': 4,
        'shape': 'diamond',
        'width': 55,
        'height': 55,
        'font-weight': 'bold',
        'font-size': 11,
      }
    },
    // Public IP host nodes
    {
      selector: 'node[?is_public]',
      style: {
        'background-color': '#0ea5e9',
        'border-color': '#0284c7',
        'border-width': 2,
      }
    },

    // ── Synthetic gateway node ──────────────────────────────
    {
      selector: 'node[?is_synthetic]',
      style: {
        'border-style': 'dashed',
        'border-opacity': 0.7,
      }
    },

    // ── To-gateway edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="to_gateway"]',
      style: {
        'line-color': '#94a3b8',
        'width': 1.5,
        'line-style': 'solid',
        'line-opacity': 0.4,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#94a3b8',
        'arrow-scale': 0.5,
      }
    },

    // ── Internet edge (gateway → cloud) ─────────────────────
    {
      selector: 'edge[connection_type="internet"]',
      style: {
        'line-color': '#0ea5e9',
        'width': 3,
        'line-style': 'solid',
        'line-opacity': 0.7,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#0ea5e9',
        'arrow-scale': 1,
        'curve-style': 'unbundled-bezier',
      }
    },

    // ── Interaction: selected ───────────────────────────────
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': '#3b82f6',
        'overlay-color': '#3b82f6',
        'overlay-opacity': 0.15,
        'z-index': 999,
      }
    },

    // ── Interaction: hover ──────────────────────────────────
    {
      selector: 'node:active',
      style: {
        'overlay-color': '#60a5fa',
        'overlay-opacity': 0.2,
      }
    },

    // ── Edge selected ───────────────────────────────────────
    {
      selector: 'edge:selected',
      style: {
        'line-color': '#3b82f6',
        'width': 3,
        'line-opacity': 1,
        'z-index': 999,
      }
    },

    // ── Dimmed (filtered out) ───────────────────────────────
    {
      selector: '.dimmed',
      style: {
        'opacity': 0.15,
      }
    },

    // ── Highlighted (search match) ──────────────────────────
    {
      selector: '.highlighted',
      style: {
        'border-width': 5,
        'border-color': '#fbbf24',
        'overlay-color': '#fbbf24',
        'overlay-opacity': 0.3,
        'z-index': 999,
      }
    },
  ]
}

// ── Dark mode stylesheet ────────────────────────────────────────────

export function getDarkStyles() {
  return [
    // ── Default node ────────────────────────────────────────
    {
      selector: 'node',
      style: {
        ...baseNodeStyles,
        'background-color': '#9ca3af',
        'border-color': '#d1d5db',
        'border-width': 2,
        'font-size': 11,
        'color': '#e5e7eb',
        'text-halign': 'center',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'overlay-padding': 6,
        'z-index': 10,
      }
    },

    // ── VLAN compound node ──────────────────────────────────
    {
      selector: 'node[type="vlan"]',
      style: {
        'background-color': 'data(color)',
        'background-opacity': 0.12,
        'border-width': 3,
        'border-color': 'data(color)',
        'border-style': 'solid',
        'border-opacity': 0.7,
        'shape': 'round-rectangle',
        'font-size': 16,
        'font-weight': 'bold',
        'color': '#f3f4f6',
        'text-halign': 'center',
        'text-valign': 'top',
        'text-margin-y': -8,
        'padding': '40px',
        'z-index': 1,
      }
    },

    // ── Subnet compound node ────────────────────────────────
    {
      selector: 'node[type="subnet"]',
      style: {
        'background-color': 'data(color)',
        'background-opacity': 0.08,
        'border-width': 2,
        'border-color': 'data(color)',
        'border-style': 'dashed',
        'border-opacity': 0.5,
        'shape': 'round-rectangle',
        'font-size': 12,
        'font-weight': 'normal',
        'color': '#9ca3af',
        'text-halign': 'center',
        'text-valign': 'top',
        'text-margin-y': -6,
        'padding': '25px',
        'z-index': 2,
      }
    },

    // ── Gateway nodes ───────────────────────────────────────
    {
      selector: 'node[?is_gateway]',
      style: {
        'border-width': 4,
        'border-color': '#fb923c',
        'font-weight': 'bold',
      }
    },

    // ── Device type specific styles ─────────────────────────
    ...buildDeviceTypeStyles(true),

    // ── Default edge ────────────────────────────────────────
    {
      selector: 'edge',
      style: {
        ...baseEdgeStyles,
        'line-color': '#4b5563',
        'target-arrow-color': '#4b5563',
      }
    },

    // ── Same subnet edge ────────────────────────────────────
    {
      selector: 'edge[connection_type="same_subnet"]',
      style: {
        'line-color': '#4b5563',
        'width': 1.5,
        'line-style': 'solid',
        'line-opacity': 0.5,
      }
    },

    // ── Cross-subnet edge ───────────────────────────────────
    {
      selector: 'edge[connection_type="cross_subnet"]',
      style: {
        'line-color': '#f59e0b',
        'width': 2,
        'line-style': 'dashed',
        'line-opacity': 0.7,
        'line-dash-pattern': [8, 4],
      }
    },

    // ── Cross-VLAN edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="cross_vlan"]',
      style: {
        'line-color': '#fb923c',
        'width': 2.5,
        'line-style': 'dashed',
        'line-opacity': 0.8,
        'line-dash-pattern': [10, 5],
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#fb923c',
        'arrow-scale': 0.8,
      }
    },

    // ── Route path edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="route"]',
      style: {
        'line-color': '#4ade80',
        'width': 2,
        'line-style': 'dotted',
        'line-opacity': 0.7,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#4ade80',
        'arrow-scale': 0.6,
      }
    },

    // ── Internet cloud node ────────────────────────────────
    {
      selector: 'node[type="internet"]',
      style: {
        'background-color': '#0ea5e9',
        'background-opacity': 0.2,
        'border-width': 3,
        'border-color': '#38bdf8',
        'border-style': 'solid',
        'border-opacity': 0.7,
        'shape': 'ellipse',
        'width': 90,
        'height': 60,
        'font-size': 16,
        'font-weight': 'bold',
        'color': '#7dd3fc',
        'text-halign': 'center',
        'text-valign': 'center',
        'z-index': 1,
      }
    },

    // Public IPs compound node (dark)
    {
      selector: 'node[type="public_ips"]',
      style: {
        'background-color': '#0ea5e9',
        'background-opacity': 0.15,
        'border-color': '#38bdf8',
        'border-width': 3,
        'border-style': 'dashed',
        'label': 'data(label)',
        'font-size': 14,
        'font-weight': 'bold',
        'text-halign': 'center',
        'text-valign': 'top',
        'color': '#7dd3fc',
        'padding': '20px',
      }
    },
    // Shared gateway node (dark)
    {
      selector: 'node[?is_shared_gateway]',
      style: {
        'background-color': '#f97316',
        'border-color': '#fb923c',
        'border-width': 4,
        'shape': 'diamond',
        'width': 55,
        'height': 55,
        'font-weight': 'bold',
        'font-size': 11,
      }
    },
    // Public IP host nodes (dark)
    {
      selector: 'node[?is_public]',
      style: {
        'background-color': '#0ea5e9',
        'border-color': '#38bdf8',
        'border-width': 2,
      }
    },

    // ── Synthetic gateway node ──────────────────────────────
    {
      selector: 'node[?is_synthetic]',
      style: {
        'border-style': 'dashed',
        'border-opacity': 0.7,
      }
    },

    // ── To-gateway edge ─────────────────────────────────────
    {
      selector: 'edge[connection_type="to_gateway"]',
      style: {
        'line-color': '#64748b',
        'width': 1.5,
        'line-style': 'solid',
        'line-opacity': 0.4,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#64748b',
        'arrow-scale': 0.5,
      }
    },

    // ── Internet edge (gateway → cloud) ─────────────────────
    {
      selector: 'edge[connection_type="internet"]',
      style: {
        'line-color': '#38bdf8',
        'width': 3,
        'line-style': 'solid',
        'line-opacity': 0.7,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#38bdf8',
        'arrow-scale': 1,
        'curve-style': 'unbundled-bezier',
      }
    },

    // ── Interaction: selected ───────────────────────────────
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': '#60a5fa',
        'overlay-color': '#60a5fa',
        'overlay-opacity': 0.2,
        'z-index': 999,
      }
    },

    // ── Interaction: hover ──────────────────────────────────
    {
      selector: 'node:active',
      style: {
        'overlay-color': '#93c5fd',
        'overlay-opacity': 0.2,
      }
    },

    // ── Edge selected ───────────────────────────────────────
    {
      selector: 'edge:selected',
      style: {
        'line-color': '#60a5fa',
        'width': 3,
        'line-opacity': 1,
        'z-index': 999,
      }
    },

    // ── Dimmed (filtered out) ───────────────────────────────
    {
      selector: '.dimmed',
      style: {
        'opacity': 0.1,
      }
    },

    // ── Highlighted (search match) ──────────────────────────
    {
      selector: '.highlighted',
      style: {
        'border-width': 5,
        'border-color': '#fbbf24',
        'overlay-color': '#fbbf24',
        'overlay-opacity': 0.3,
        'z-index': 999,
      }
    },
  ]
}

// ── Layout presets ──────────────────────────────────────────────────

export const layoutPresets = {
  hierarchical: {
    name: 'dagre',
    rankDir: 'TB',
    nodeSep: 60,
    edgeSep: 20,
    rankSep: 80,
    spacingFactor: 1.2,
    animate: true,
    animationDuration: 500,
  },
  grouped: {
    name: 'fcose',
    quality: 'default',
    randomize: false,
    animate: true,
    animationDuration: 500,
    nodeDimensionsIncludeLabels: true,
    packComponents: true,
    nodeRepulsion: 8000,
    idealEdgeLength: 100,
    edgeElasticity: 0.45,
    nestingFactor: 0.1,
    gravity: 0.25,
    gravityRange: 3.8,
    gravityCompound: 1.5,
    gravityRangeCompound: 2.0,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 20,
    tilingPaddingHorizontal: 20,
  },
  force: {
    name: 'cola',
    animate: true,
    maxSimulationTime: 3000,
    nodeSpacing: 30,
    edgeLength: 120,
    handleDisconnected: true,
    avoidOverlap: true,
    convergenceThreshold: 0.01,
  },
}

// ── Device legend data ──────────────────────────────────────────────

export const deviceLegend = [
  { type: 'router',      label: 'Router',      color: '#f97316', shape: 'diamond' },
  { type: 'switch',      label: 'Switch',      color: '#8b5cf6', shape: 'vee' },
  { type: 'firewall',    label: 'Firewall',    color: '#ef4444', shape: 'star' },
  { type: 'server',      label: 'Server',      color: '#3b82f6', shape: 'round-rectangle' },
  { type: 'workstation', label: 'Workstation', color: '#22c55e', shape: 'circle' },
  { type: 'printer',     label: 'Printer',     color: '#ec4899', shape: 'rectangle' },
  { type: 'iot',         label: 'IoT',         color: '#06b6d4', shape: 'hexagon' },
  { type: 'unknown',     label: 'Unknown',     color: '#6b7280', shape: 'circle' },
  { type: 'internet',    label: 'Internet',    color: '#0ea5e9', shape: 'circle' },
]

export function getEdgeLegend(isDark = false) {
  return [
    { type: 'same_subnet',  label: 'Same Subnet',  color: isDark ? '#4b5563' : '#9ca3af', style: 'solid' },
    { type: 'cross_subnet', label: 'Cross-Subnet',  color: '#f59e0b', style: 'dashed' },
    { type: 'cross_vlan',   label: 'Cross-VLAN',    color: isDark ? '#fb923c' : '#f97316', style: 'dashed' },
    { type: 'internet',     label: 'Internet',       color: isDark ? '#38bdf8' : '#0ea5e9', style: 'solid' },
    { type: 'route',        label: 'Route Path',    color: isDark ? '#4ade80' : '#22c55e', style: 'dotted' },
    { type: 'to_gateway',   label: 'To Gateway',    color: isDark ? '#64748b' : '#94a3b8', style: 'solid' },
  ]
}

// Backward-compatible static export (light mode defaults)
export const edgeLegend = getEdgeLegend(false)
