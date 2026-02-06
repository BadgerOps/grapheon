/**
 * Client-side graph filtering and search for Cytoscape.js network map.
 *
 * All operations work directly on the Cytoscape instance without
 * requiring API re-fetches — filters toggle visibility via CSS classes.
 */

/**
 * Filter by VLAN IDs — show only nodes within specified VLANs.
 * Pass empty array to show all.
 */
export function filterByVlan(cy, vlanIds) {
  if (!cy || !vlanIds) return

  // Show all if empty filter
  if (vlanIds.length === 0) {
    cy.elements().removeClass('dimmed')
    return
  }

  const vlanNodeIds = vlanIds.map(id => `vlan_${id}`)

  cy.batch(() => {
    cy.elements().addClass('dimmed')

    // Show matching VLAN compounds and all their descendants
    vlanNodeIds.forEach(vlanId => {
      const vlanNode = cy.getElementById(vlanId)
      if (vlanNode.length) {
        vlanNode.removeClass('dimmed')
        vlanNode.descendants().removeClass('dimmed')
      }
    })

    // Keep internet node visible if connected gateways are visible
    cy.nodes('[type="internet"]').forEach(internet => {
      const connectedEdges = internet.connectedEdges()
      const hasVisibleNeighbor = connectedEdges.some(edge => {
        const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
        return !other.hasClass('dimmed')
      })
      if (hasVisibleNeighbor) {
        internet.removeClass('dimmed')
        connectedEdges.forEach(edge => {
          const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
          if (!other.hasClass('dimmed')) edge.removeClass('dimmed')
        })
      }
    })

    // Show edges between visible nodes
    cy.edges().forEach(edge => {
      const source = edge.source()
      const target = edge.target()
      if (!source.hasClass('dimmed') && !target.hasClass('dimmed')) {
        edge.removeClass('dimmed')
      }
    })
  })
}

/**
 * Filter by device types — show only nodes of specified types.
 * Pass empty array to show all.
 */
export function filterByDeviceType(cy, deviceTypes) {
  if (!cy || !deviceTypes) return

  if (deviceTypes.length === 0) {
    cy.elements().removeClass('dimmed')
    return
  }

  cy.batch(() => {
    // Dim all leaf nodes
    cy.nodes().forEach(node => {
      const type = node.data('type')
      if (type === 'vlan' || type === 'subnet' || type === 'internet') return // Skip compounds and internet node

      const deviceType = node.data('device_type')
      if (deviceTypes.includes(deviceType)) {
        node.removeClass('dimmed')
      } else {
        node.addClass('dimmed')
      }
    })

    // Show compound nodes that have visible children
    cy.nodes('[type="subnet"]').forEach(subnet => {
      const hasVisible = subnet.children().some(child => !child.hasClass('dimmed'))
      if (hasVisible) {
        subnet.removeClass('dimmed')
      } else {
        subnet.addClass('dimmed')
      }
    })

    cy.nodes('[type="vlan"]').forEach(vlan => {
      const hasVisible = vlan.descendants().some(desc => !desc.hasClass('dimmed') && desc.data('type') !== 'subnet')
      if (hasVisible) {
        vlan.removeClass('dimmed')
      } else {
        vlan.addClass('dimmed')
      }
    })

    // Always keep internet node visible when there are connected visible nodes
    cy.nodes('[type="internet"]').forEach(internet => {
      const connectedEdges = internet.connectedEdges()
      const hasVisibleNeighbor = connectedEdges.some(edge => {
        const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
        return !other.hasClass('dimmed')
      })
      if (hasVisibleNeighbor) {
        internet.removeClass('dimmed')
        connectedEdges.forEach(edge => {
          const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
          if (!other.hasClass('dimmed')) edge.removeClass('dimmed')
        })
      } else {
        internet.addClass('dimmed')
      }
    })

    // Show edges between visible non-dimmed nodes
    cy.edges().forEach(edge => {
      const source = edge.source()
      const target = edge.target()
      if (!source.hasClass('dimmed') && !target.hasClass('dimmed')) {
        edge.removeClass('dimmed')
      } else {
        edge.addClass('dimmed')
      }
    })
  })
}

/**
 * Filter by subnet CIDRs — show only nodes in specified subnets.
 * Pass empty array to show all.
 */
export function filterBySubnet(cy, subnets) {
  if (!cy || !subnets) return

  if (subnets.length === 0) {
    cy.elements().removeClass('dimmed')
    return
  }

  const subnetNodeIds = subnets.map(s => `subnet_${s}`)

  cy.batch(() => {
    cy.elements().addClass('dimmed')

    subnetNodeIds.forEach(subnetId => {
      const subnetNode = cy.getElementById(subnetId)
      if (subnetNode.length) {
        subnetNode.removeClass('dimmed')
        subnetNode.children().removeClass('dimmed')

        // Also show parent VLAN
        const parent = subnetNode.parent()
        if (parent.length) {
          parent.removeClass('dimmed')
        }
      }
    })

    // Keep internet node visible if connected gateways are visible
    cy.nodes('[type="internet"]').forEach(internet => {
      const connectedEdges = internet.connectedEdges()
      const hasVisibleNeighbor = connectedEdges.some(edge => {
        const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
        return !other.hasClass('dimmed')
      })
      if (hasVisibleNeighbor) {
        internet.removeClass('dimmed')
        connectedEdges.forEach(edge => {
          const other = edge.source().id() === internet.id() ? edge.target() : edge.source()
          if (!other.hasClass('dimmed')) edge.removeClass('dimmed')
        })
      }
    })

    // Show edges between visible nodes
    cy.edges().forEach(edge => {
      const source = edge.source()
      const target = edge.target()
      if (!source.hasClass('dimmed') && !target.hasClass('dimmed')) {
        edge.removeClass('dimmed')
      }
    })
  })
}

/**
 * Search for a device by IP or hostname and focus on it.
 * Returns the matched node or null.
 */
export function searchAndFocus(cy, query) {
  if (!cy || !query || query.trim() === '') {
    // Clear any existing highlights
    if (cy) cy.elements().removeClass('highlighted')
    return null
  }

  const searchTerm = query.toLowerCase().trim()

  // Clear previous highlights
  cy.elements().removeClass('highlighted')

  // Search through leaf nodes (not compound)
  let matchedNode = null

  cy.nodes().forEach(node => {
    const type = node.data('type')
    if (type === 'vlan' || type === 'subnet') return

    const ip = (node.data('ip') || '').toLowerCase()
    const hostname = (node.data('hostname') || '').toLowerCase()
    const label = (node.data('label') || '').toLowerCase()

    if (ip.includes(searchTerm) || hostname.includes(searchTerm) || label.includes(searchTerm)) {
      node.addClass('highlighted')
      if (!matchedNode) matchedNode = node
    }
  })

  // Center view on first match
  if (matchedNode) {
    cy.animate({
      center: { eles: matchedNode },
      zoom: Math.max(cy.zoom(), 1.2),
    }, {
      duration: 400,
    })
  }

  return matchedNode
}

/**
 * Clear all filters and highlights.
 */
export function clearAllFilters(cy) {
  if (!cy) return
  cy.elements().removeClass('dimmed highlighted')
}

/**
 * Get unique values for filter dropdowns from current graph data.
 */
export function getFilterOptions(cy) {
  if (!cy) return { vlans: [], subnets: [], deviceTypes: [] }

  const vlans = new Map()
  const subnets = new Map()
  const deviceTypes = new Set()

  cy.nodes().forEach(node => {
    const type = node.data('type')

    if (type === 'vlan') {
      vlans.set(node.data('vlan_id'), node.data('label'))
    } else if (type === 'subnet') {
      subnets.set(node.data('subnet_cidr'), node.data('label'))
    } else {
      const dt = node.data('device_type')
      if (dt) deviceTypes.add(dt)
    }
  })

  return {
    vlans: Array.from(vlans, ([id, label]) => ({ id, label })),
    subnets: Array.from(subnets, ([cidr, label]) => ({ cidr, label })),
    deviceTypes: Array.from(deviceTypes).sort(),
  }
}
