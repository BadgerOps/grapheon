/**
 * Unit tests for the isoflow data transformer.
 *
 * Tests cover:
 * - Host node extraction from Cytoscape elements
 * - Compound node extraction
 * - Tile position computation (grid layout)
 * - Connector building from edges
 * - Rectangle computation for compound nodes
 * - Full transformation pipeline
 * - Edge cases (empty data, missing fields)
 */
import { describe, it, expect } from 'vitest'
import {
  extractHostNodes,
  extractCompoundNodes,
  computeTilePositions,
  buildConnectors,
  computeRectangles,
  transformToIsoflow,
  DEVICE_ICON_MAP,
  DEFAULT_ICON,
  CONNECTION_COLORS,
  CONNECTION_STYLES,
} from '../isoflowTransformer.js'

// ── Test fixtures ────────────────────────────────────────────────

function makeNode(id, type, overrides = {}) {
  return {
    data: {
      id,
      type,
      label: overrides.label || id,
      ip: overrides.ip || `10.0.0.${id}`,
      hostname: overrides.hostname || `host-${id}`,
      device_type: overrides.device_type || 'server',
      mac: overrides.mac || '00:11:22:33:44:55',
      os: overrides.os || 'Linux',
      vendor: overrides.vendor || 'Dell',
      open_ports: overrides.open_ports || 3,
      subnet: overrides.subnet || '10.0.0.0/24',
      parent: overrides.parent || null,
      vlan_id: overrides.vlan_id || null,
      vlan_name: overrides.vlan_name || null,
      is_gateway: overrides.is_gateway || false,
      color: overrides.color || '#3b82f6',
      ...overrides,
    },
  }
}

function makeEdge(id, source, target, connectionType = 'same_subnet') {
  return {
    data: {
      id,
      source,
      target,
      connection_type: connectionType,
      tooltip: `${source} → ${target}`,
    },
  }
}

function makeSampleElements() {
  return {
    nodes: [
      // Compound nodes
      makeNode('vlan-10', 'vlan', { label: 'VLAN 10' }),
      makeNode('subnet-10.0.0.0/24', 'subnet', { label: '10.0.0.0/24', parent: 'vlan-10' }),
      // Host nodes
      makeNode('1', 'host', { device_type: 'router', parent: 'subnet-10.0.0.0/24', ip: '10.0.0.1', is_gateway: true }),
      makeNode('2', 'host', { device_type: 'server', parent: 'subnet-10.0.0.0/24', ip: '10.0.0.2' }),
      makeNode('3', 'host', { device_type: 'workstation', parent: 'subnet-10.0.0.0/24', ip: '10.0.0.3' }),
      makeNode('4', 'host', { device_type: 'switch', parent: 'subnet-10.0.0.0/24', ip: '10.0.0.4' }),
      // Internet node (should be filtered out)
      makeNode('internet', 'internet', { label: 'Internet' }),
    ],
    edges: [
      makeEdge('e1', '1', '2', 'same_subnet'),
      makeEdge('e2', '1', '3', 'same_subnet'),
      makeEdge('e3', '2', '4', 'same_subnet'),
      makeEdge('e4', '1', 'internet', 'internet'), // should be filtered
    ],
  }
}

// ── Tests ────────────────────────────────────────────────────────

describe('extractHostNodes', () => {
  it('filters out compound and internet nodes', () => {
    const elements = makeSampleElements()
    const hosts = extractHostNodes(elements)

    expect(hosts).toHaveLength(4)
    const ids = hosts.map((n) => n.data.id)
    expect(ids).toContain('1')
    expect(ids).toContain('2')
    expect(ids).toContain('3')
    expect(ids).toContain('4')
    expect(ids).not.toContain('vlan-10')
    expect(ids).not.toContain('subnet-10.0.0.0/24')
    expect(ids).not.toContain('internet')
  })

  it('returns empty array for empty elements', () => {
    expect(extractHostNodes({ nodes: [] })).toHaveLength(0)
    expect(extractHostNodes({})).toHaveLength(0)
  })

  it('filters out public_ips compound nodes', () => {
    const elements = {
      nodes: [
        makeNode('pub', 'public_ips'),
        makeNode('h1', 'host'),
      ],
    }
    const hosts = extractHostNodes(elements)
    expect(hosts).toHaveLength(1)
    expect(hosts[0].data.id).toBe('h1')
  })
})

describe('extractCompoundNodes', () => {
  it('extracts only vlan and subnet nodes', () => {
    const elements = makeSampleElements()
    const compounds = extractCompoundNodes(elements)

    expect(compounds).toHaveLength(2)
    const types = compounds.map((n) => n.data.type)
    expect(types).toContain('vlan')
    expect(types).toContain('subnet')
  })

  it('excludes internet and host nodes', () => {
    const elements = makeSampleElements()
    const compounds = extractCompoundNodes(elements)
    const ids = compounds.map((n) => n.data.id)
    expect(ids).not.toContain('internet')
    expect(ids).not.toContain('1')
  })
})

describe('computeTilePositions', () => {
  it('assigns unique tile positions to all hosts', () => {
    const elements = makeSampleElements()
    const hosts = extractHostNodes(elements)
    const compounds = extractCompoundNodes(elements)
    const positions = computeTilePositions(hosts, compounds)

    expect(positions.size).toBe(4)

    // Verify all positions are unique
    const posSet = new Set()
    for (const [, pos] of positions) {
      const key = `${pos.x},${pos.y}`
      expect(posSet.has(key)).toBe(false)
      posSet.add(key)
    }
  })

  it('returns tile objects with x and y', () => {
    const hosts = [makeNode('h1', 'host')]
    const positions = computeTilePositions(hosts, [])

    expect(positions.size).toBe(1)
    const pos = positions.get('h1')
    expect(pos).toBeDefined()
    expect(typeof pos.x).toBe('number')
    expect(typeof pos.y).toBe('number')
  })

  it('groups hosts by parent', () => {
    const hosts = [
      makeNode('a1', 'host', { parent: 'group-a' }),
      makeNode('a2', 'host', { parent: 'group-a' }),
      makeNode('b1', 'host', { parent: 'group-b' }),
    ]
    const positions = computeTilePositions(hosts, [])

    // a1 and a2 should be closer together than a1 and b1
    const posA1 = positions.get('a1')
    const posA2 = positions.get('a2')
    const posB1 = positions.get('b1')

    const distA = Math.abs(posA1.x - posA2.x) + Math.abs(posA1.y - posA2.y)
    const distB = Math.abs(posA1.x - posB1.x) + Math.abs(posA1.y - posB1.y)
    expect(distA).toBeLessThan(distB)
  })

  it('handles ungrouped hosts', () => {
    const hosts = [
      makeNode('u1', 'host', { parent: null }),
      makeNode('u2', 'host', { parent: null }),
    ]
    const positions = computeTilePositions(hosts, [])
    expect(positions.size).toBe(2)
  })

  it('handles empty input', () => {
    const positions = computeTilePositions([], [])
    expect(positions.size).toBe(0)
  })
})

describe('buildConnectors', () => {
  it('creates connectors for edges between host nodes', () => {
    const edges = [
      makeEdge('e1', 'h1', 'h2', 'same_subnet'),
      makeEdge('e2', 'h2', 'h3', 'cross_vlan'),
    ]
    const hostIds = ['h1', 'h2', 'h3']
    const connectors = buildConnectors(edges, hostIds)

    expect(connectors).toHaveLength(2)
    expect(connectors[0].anchors).toEqual([{ item: 'h1' }, { item: 'h2' }])
    expect(connectors[1].anchors).toEqual([{ item: 'h2' }, { item: 'h3' }])
  })

  it('filters out edges to non-host nodes', () => {
    const edges = [
      makeEdge('e1', 'h1', 'h2', 'same_subnet'),
      makeEdge('e2', 'h1', 'internet', 'internet'),
    ]
    const hostIds = ['h1', 'h2']
    const connectors = buildConnectors(edges, hostIds)

    expect(connectors).toHaveLength(1)
    expect(connectors[0].id).toBe('e1')
  })

  it('maps connection types to correct colors and styles', () => {
    const edges = [
      makeEdge('e1', 'h1', 'h2', 'same_subnet'),
      makeEdge('e2', 'h1', 'h3', 'cross_vlan'),
      makeEdge('e3', 'h2', 'h3', 'route'),
    ]
    const hostIds = ['h1', 'h2', 'h3']
    const connectors = buildConnectors(edges, hostIds)

    expect(connectors[0].color).toBe('color-same-subnet')
    expect(connectors[0].style).toBe('SOLID')

    expect(connectors[1].color).toBe('color-cross-vlan')
    expect(connectors[1].style).toBe('DASHED')
    expect(connectors[1].width).toBe(2) // cross_vlan is wider

    expect(connectors[2].color).toBe('color-route')
    expect(connectors[2].style).toBe('DOTTED')
  })

  it('handles empty edges', () => {
    expect(buildConnectors([], ['h1'])).toHaveLength(0)
    expect(buildConnectors(null, ['h1'])).toHaveLength(0)
    expect(buildConnectors(undefined, ['h1'])).toHaveLength(0)
  })

  it('handles edges with missing source/target', () => {
    const edges = [
      { data: { id: 'bad1', source: null, target: 'h1' } },
      { data: { id: 'bad2', source: 'h1' } },
      { data: {} },
    ]
    const connectors = buildConnectors(edges, ['h1'])
    expect(connectors).toHaveLength(0)
  })
})

describe('computeRectangles', () => {
  it('creates rectangles for compound nodes with children', () => {
    const compounds = [makeNode('s1', 'subnet', { label: 'Subnet 1' })]
    const hosts = [
      makeNode('h1', 'host', { parent: 's1' }),
      makeNode('h2', 'host', { parent: 's1' }),
    ]
    const positions = new Map([
      ['h1', { x: 5, y: 5 }],
      ['h2', { x: 8, y: 5 }],
    ])

    const { rectangles } = computeRectangles(compounds, hosts, positions)
    expect(rectangles).toHaveLength(1)
    expect(rectangles[0].id).toBe('rect-s1')
    expect(rectangles[0].from.x).toBeLessThan(5) // padding before min
    expect(rectangles[0].to.x).toBeGreaterThan(8) // padding after max
  })

  it('skips compounds with no children', () => {
    const compounds = [makeNode('empty', 'subnet')]
    const { rectangles } = computeRectangles(compounds, [], new Map())
    expect(rectangles).toHaveLength(0)
  })

  it('assigns zone colors', () => {
    const compounds = [
      makeNode('s1', 'subnet'),
      makeNode('s2', 'subnet'),
    ]
    const hosts = [
      makeNode('h1', 'host', { parent: 's1' }),
      makeNode('h2', 'host', { parent: 's2' }),
    ]
    const positions = new Map([
      ['h1', { x: 2, y: 2 }],
      ['h2', { x: 10, y: 10 }],
    ])

    const { rectangles, zoneColors } = computeRectangles(compounds, hosts, positions)
    expect(rectangles).toHaveLength(2)
    expect(zoneColors.length).toBe(2)
    // Each rectangle should have a different color
    expect(rectangles[0].color).not.toBe(rectangles[1].color)
  })
})

describe('transformToIsoflow', () => {
  it('produces valid isoflow initialData structure', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    // Required top-level keys
    expect(result).toHaveProperty('title')
    expect(result).toHaveProperty('icons')
    expect(result).toHaveProperty('colors')
    expect(result).toHaveProperty('items')
    expect(result).toHaveProperty('views')

    // Views structure
    expect(result.views).toHaveLength(1)
    const view = result.views[0]
    expect(view).toHaveProperty('id', 'main')
    expect(view).toHaveProperty('name')
    expect(view).toHaveProperty('items')
    expect(view).toHaveProperty('connectors')
    expect(view).toHaveProperty('rectangles')
  })

  it('creates items for host nodes only', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    // Should have 4 host items (not compound/internet nodes)
    expect(result.items).toHaveLength(4)

    const itemIds = result.items.map((i) => i.id)
    expect(itemIds).toContain('1')
    expect(itemIds).toContain('2')
    expect(itemIds).toContain('3')
    expect(itemIds).toContain('4')
  })

  it('maps device types to correct icons', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    const iconById = Object.fromEntries(result.items.map((i) => [i.id, i.icon]))
    expect(iconById['1']).toBe('router') // router device
    expect(iconById['2']).toBe('server') // server device
    expect(iconById['3']).toBe('desktop') // workstation device
    expect(iconById['4']).toBe('switch-module') // switch device
  })

  it('creates view items with tile positions', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    const viewItems = result.views[0].items
    expect(viewItems).toHaveLength(4)

    for (const vi of viewItems) {
      expect(vi).toHaveProperty('id')
      expect(vi).toHaveProperty('tile')
      expect(vi.tile).toHaveProperty('x')
      expect(vi.tile).toHaveProperty('y')
      expect(typeof vi.tile.x).toBe('number')
      expect(typeof vi.tile.y).toBe('number')
    }
  })

  it('filters connectors to host-to-host edges only', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    const connectors = result.views[0].connectors
    // e4 (to internet) should be filtered out, leaving 3
    expect(connectors).toHaveLength(3)
  })

  it('creates rectangles for compound nodes', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    const rectangles = result.views[0].rectangles
    // subnet-10.0.0.0/24 has children; vlan-10 does not directly
    expect(rectangles.length).toBeGreaterThanOrEqual(1)
  })

  it('includes connection colors', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements)

    expect(result.colors.length).toBeGreaterThan(0)
    const colorIds = result.colors.map((c) => c.id)
    expect(colorIds).toContain('color-same-subnet')
  })

  it('uses custom title when provided', () => {
    const elements = makeSampleElements()
    const result = transformToIsoflow(elements, { title: 'My Network' })
    expect(result.title).toBe('My Network')
  })

  it('returns empty structure for empty elements', () => {
    const result = transformToIsoflow({ nodes: [], edges: [] })
    expect(result.items).toHaveLength(0)
    expect(result.views[0].items).toHaveLength(0)
    expect(result.views[0].connectors).toHaveLength(0)
  })

  it('returns empty structure for null elements', () => {
    const result = transformToIsoflow(null)
    expect(result.items).toHaveLength(0)
  })

  it('handles items with missing optional fields', () => {
    const elements = {
      nodes: [
        {
          data: {
            id: 'minimal',
            type: 'host',
            ip: '1.2.3.4',
          },
        },
      ],
      edges: [],
    }
    const result = transformToIsoflow(elements)
    expect(result.items).toHaveLength(1)
    expect(result.items[0].icon).toBe(DEFAULT_ICON)
  })

  it('builds markdown description for nodes', () => {
    const elements = {
      nodes: [
        makeNode('1', 'host', {
          ip: '10.0.0.1',
          mac: 'AA:BB:CC:DD:EE:FF',
          os: 'Ubuntu 22.04',
          vendor: 'Dell',
          device_type: 'server',
          open_ports: 5,
          subnet: '10.0.0.0/24',
          vlan_name: 'Management',
          vlan_id: 10,
          is_gateway: true,
        }),
      ],
      edges: [],
    }
    const result = transformToIsoflow(elements)
    const desc = result.items[0].description

    expect(desc).toContain('**IP:** 10.0.0.1')
    expect(desc).toContain('**MAC:** AA:BB:CC:DD:EE:FF')
    expect(desc).toContain('**OS:** Ubuntu 22.04')
    expect(desc).toContain('**Vendor:** Dell')
    expect(desc).toContain('**Type:** server')
    expect(desc).toContain('**Open Ports:** 5')
    expect(desc).toContain('**Subnet:** 10.0.0.0/24')
    expect(desc).toContain('**VLAN:** Management (10)')
    expect(desc).toContain('**Role:** Gateway')
  })
})

describe('DEVICE_ICON_MAP', () => {
  it('maps all expected device types', () => {
    const expectedTypes = ['router', 'switch', 'firewall', 'server', 'workstation', 'printer', 'iot', 'unknown']
    for (const type of expectedTypes) {
      expect(DEVICE_ICON_MAP[type]).toBeDefined()
    }
  })

  it('has unique icon mappings for each device type', () => {
    const icons = Object.values(DEVICE_ICON_MAP)
    const unique = new Set(icons)
    expect(unique.size).toBe(icons.length)
  })
})

describe('CONNECTION_COLORS', () => {
  it('defines colors for all connection types', () => {
    const types = ['same_subnet', 'cross_subnet', 'cross_vlan', 'route', 'internet', 'to_gateway']
    for (const type of types) {
      expect(CONNECTION_COLORS[type]).toBeDefined()
      expect(CONNECTION_COLORS[type].id).toBeTruthy()
      expect(CONNECTION_COLORS[type].value).toBeTruthy()
    }
  })

  it('has unique color IDs', () => {
    const ids = Object.values(CONNECTION_COLORS).map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('CONNECTION_STYLES', () => {
  it('defines valid styles for all connection types', () => {
    const validStyles = ['SOLID', 'DASHED', 'DOTTED']
    const types = ['same_subnet', 'cross_subnet', 'cross_vlan', 'route', 'internet', 'to_gateway']
    for (const type of types) {
      expect(validStyles).toContain(CONNECTION_STYLES[type])
    }
  })
})
