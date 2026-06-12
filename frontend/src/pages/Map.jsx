import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import CytoscapeNetworkMap from '../components/CytoscapeNetworkMap'
import IsoflowNetworkMap from '../components/IsoflowNetworkMap'
import MapErrorBoundary from '../components/MapErrorBoundary'
import { searchAndFocus, filterByDeviceType, filterByVlan, clearAllFilters } from '../services/graphFilters'
import { deviceLegend } from '../styles/cytoscape-theme'
import * as api from '../api/client'

const AGENT_RELATIONSHIP_OPTIONS = [
  { value: 'collector_interface', label: 'Collector' },
  { value: 'arp_neighbor', label: 'ARP' },
  { value: 'connection_remote', label: 'Connections' },
  { value: 'route_gateway', label: 'Routes' },
]
const DEFAULT_AGENT_RELATIONSHIPS = AGENT_RELATIONSHIP_OPTIONS.map(option => option.value)
const TOPOLOGY_LAYER_OPTIONS = [
  { key: 'physical', label: 'Physical/L2', relationships: ['l2_neighbor', 'switch_port_attachment'] },
  { key: 'routes', label: 'Routes/Gateways', relationships: ['route'] },
  { key: 'dhcp', label: 'DHCP identity', relationships: ['dhcp_lease', 'mac_ip_binding'] },
  { key: 'dns', label: 'DNS names', relationships: ['dns_name'] },
  { key: 'flows', label: 'Flow relationships', relationships: ['flow_relationship'] },
  { key: 'segments', label: 'Manual/saved groups', relationships: ['network_segment'] },
]
const DEFAULT_TOPOLOGY_LAYERS = {
  physical: false,
  routes: false,
  dhcp: false,
  dns: false,
  flows: false,
  segments: true,
}
const EVIDENCE_SOURCE_OPTIONS = [
  'agent', 'snmp', 'dhcp', 'dhcpv6', 'dns', 'mdns', 'llmnr', 'nbns',
  'zeek', 'lldp', 'cdp', 'ssdp', 'wsd', 'stp', 'lacp',
  'hsrp', 'vrrp', 'carp', 'ospf', 'rip', 'eigrp', 'bgp', 'manual',
]

/**
 * Map Page — Network topology visualization
 *
 * Features:
 * - Cytoscape.js interactive graph with compound node hierarchy
 * - Isoflow isometric diagram view (TESTING / experimental)
 * - Layout mode switching (hierarchical, grouped, force-directed)
 * - VLAN, subnet, and device type filtering
 * - Search to find and focus on devices
 * - Traceroute path overlay
 * - Stats summary
 */
export default function Map() {
  // ── Data state ──────────────────────────────────────────────────
  const [elements, setElements] = useState({ nodes: [], edges: [] })
  const [stats, setStats] = useState({})
  const [vlans, setVlans] = useState([])
  const [subnets, setSubnets] = useState([])
  const [agents, setAgents] = useState([])
  const [networkGroups, setNetworkGroups] = useState([])
  const [routeData, setRouteData] = useState({ traces: {}, path_edges: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState([])
  const [networkGroupError, setNetworkGroupError] = useState('')

  // ── View mode ──────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState('graph') // 'graph' | 'isometric'

  // ── Filter state ────────────────────────────────────────────────
  const [layoutMode, setLayoutMode] = useState('grouped')
  const [groupBy, setGroupBy] = useState('subnet')
  const [selectedVlan, setSelectedVlan] = useState('')
  const [selectedDeviceTypes, setSelectedDeviceTypes] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [showRoutes, setShowRoutes] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [internetMode, setInternetMode] = useState('cloud') // 'cloud', 'hide', 'show'
  const [routeThroughGateway, setRouteThroughGateway] = useState(false)
  const [observedByAgentId, setObservedByAgentId] = useState('')
  const [relationshipTypes, setRelationshipTypes] = useState(DEFAULT_AGENT_RELATIONSHIPS)
  const [topologyLayers, setTopologyLayers] = useState(DEFAULT_TOPOLOGY_LAYERS)
  const [evidenceSources, setEvidenceSources] = useState([])
  const [minConfidence, setMinConfidence] = useState(0)
  const [includeCollectorNodes, setIncludeCollectorNodes] = useState(true)
  const [cidrHints, setCidrHints] = useState('')
  const [networkGroupForm, setNetworkGroupForm] = useState({
    cidr: '',
    label: '',
    is_expected: true,
    is_hidden: false,
  })
  const [editingNetworkGroupId, setEditingNetworkGroupId] = useState(null)
  const [networkGroupDraft, setNetworkGroupDraft] = useState(null)
  const [promoteDrafts, setPromoteDrafts] = useState({})

  // ── Cytoscape ref ───────────────────────────────────────────────
  const cyRef = useRef(null)
  const networkCidrHints = useMemo(
    () => cidrHints.split(/[\s,]+/).map(item => item.trim()).filter(Boolean),
    [cidrHints],
  )
  const unresolvedGroups = useMemo(
    () => (elements.nodes || [])
      .filter(node => node.data?.type === 'subnet' && node.data?.is_inferred)
      .map(node => ({
        id: node.data.id,
        label: node.data.label,
        subnet_cidr: node.data.subnet_cidr,
      })),
    [elements.nodes],
  )
  const activeRelationshipTypes = useMemo(() => {
    const active = new Set(relationshipTypes)
    TOPOLOGY_LAYER_OPTIONS.forEach(layer => {
      if (topologyLayers[layer.key]) {
        layer.relationships.forEach(value => active.add(value))
      }
    })
    return [...active]
  }, [relationshipTypes, topologyLayers])

  // ── Fetch data ──────────────────────────────────────────────────
  const fetchNetworkMap = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const params = {
        group_by: groupBy,
        layout_mode: layoutMode,
        format: 'cytoscape',
      }
      if (selectedVlan) {
        params.vlan_filter = selectedVlan
      }
      if (observedByAgentId) {
        params.observed_by_agent_id = observedByAgentId
      }
      if (activeRelationshipTypes.length > 0) {
        params.relationship_types = activeRelationshipTypes
      }
      if (evidenceSources.length > 0) {
        params.evidence_sources = evidenceSources
      }
      if (minConfidence > 0) {
        params.min_confidence = minConfidence
      }
      if (includeCollectorNodes) {
        params.include_collector_nodes = true
      }
      if (networkCidrHints.length > 0) {
        params.network_cidrs = networkCidrHints
      }
      params.show_internet = internetMode
      params.route_through_gateway = routeThroughGateway
      const data = await api.getNetworkMap(params)
      setElements(data.elements || { nodes: [], edges: [] })
      setStats(data.stats || {})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [
    groupBy,
    layoutMode,
    selectedVlan,
    observedByAgentId,
    activeRelationshipTypes,
    evidenceSources,
    minConfidence,
    includeCollectorNodes,
    networkCidrHints,
    internetMode,
    routeThroughGateway,
  ])

  const fetchVlans = async () => {
    try {
      const data = await api.getVlans()
      setVlans(data.vlans || [])
    } catch (err) {
      console.error('Failed to fetch VLANs:', err)
      setWarnings(prev => [...prev.filter(w => w.key !== 'vlans'), { key: 'vlans', msg: 'Could not load VLAN list' }])
    }
  }

  const fetchSubnets = async () => {
    try {
      const data = await api.getSubnets()
      setSubnets(data.subnets || [])
    } catch (err) {
      console.error('Failed to fetch subnets:', err)
      setWarnings(prev => [...prev.filter(w => w.key !== 'subnets'), { key: 'subnets', msg: 'Could not load subnet list' }])
    }
  }

  const fetchAgents = async () => {
    try {
      const response = await api.getAgents({ limit: 1000, enrollment_state: 'active', is_active: true })
      setAgents(response.items || [])
    } catch (err) {
      console.error('Failed to fetch agents:', err)
      setWarnings(prev => [...prev.filter(w => w.key !== 'agents'), { key: 'agents', msg: 'Could not load agent list' }])
    }
  }

  const fetchNetworkGroups = async () => {
    try {
      const data = await api.getNetworkGroups({ include_hidden: true })
      setNetworkGroups(data.items || [])
    } catch (err) {
      console.error('Failed to fetch network groups:', err)
      setWarnings(prev => [...prev.filter(w => w.key !== 'network-groups'), { key: 'network-groups', msg: 'Could not load saved network groups' }])
    }
  }

  const fetchRoutes = async () => {
    try {
      const data = await api.getNetworkRoutes()
      setRouteData(data)
    } catch (err) {
      console.error('Failed to fetch routes:', err)
      setWarnings(prev => [...prev.filter(w => w.key !== 'routes'), { key: 'routes', msg: 'Could not load route data' }])
    }
  }

  // ── Effects ─────────────────────────────────────────────────────
  useEffect(() => {
    fetchNetworkMap()
    fetchVlans()
    fetchSubnets()
    fetchAgents()
    fetchNetworkGroups()
  }, [fetchNetworkMap])

  useEffect(() => {
    if (showRoutes) fetchRoutes()
  }, [showRoutes])

  // ── Merge route edges into elements ─────────────────────────────
  const mergedElements = useMemo(() => {
    if (!showRoutes || !routeData.path_edges || routeData.path_edges.length === 0) {
      return elements
    }

    // Map IPs to host node IDs
    const ipToId = {}
    ;(elements.nodes || []).forEach(node => {
      if (node.data.ip) {
        ipToId[node.data.ip] = node.data.id
      }
    })

    const routeEdges = routeData.path_edges
      .filter(edge => {
        const sourceIp = edge.data?.source_ip || edge.from_ip
        const targetIp = edge.data?.target_ip || edge.to_ip
        return ipToId[sourceIp] && ipToId[targetIp]
      })
      .map((edge, idx) => {
        const sourceIp = edge.data?.source_ip || edge.from_ip
        const targetIp = edge.data?.target_ip || edge.to_ip
        return {
          data: {
            id: `route_${idx}`,
            source: ipToId[sourceIp],
            target: ipToId[targetIp],
            connection_type: 'route',
            tooltip: edge.data?.tooltip || `Route: ${sourceIp} → ${targetIp}`,
          }
        }
      })

    return {
      nodes: elements.nodes,
      edges: [...(elements.edges || []), ...routeEdges],
    }
  }, [elements, routeData.path_edges, showRoutes])

  // ── Client-side filter handlers ─────────────────────────────────
  const handleSearch = (query) => {
    setSearchQuery(query)
    if (cyRef.current) {
      searchAndFocus(cyRef.current, query)
    }
  }

  const handleDeviceTypeToggle = (deviceType) => {
    const updated = selectedDeviceTypes.includes(deviceType)
      ? selectedDeviceTypes.filter(t => t !== deviceType)
      : [...selectedDeviceTypes, deviceType]
    setSelectedDeviceTypes(updated)

    if (cyRef.current) {
      if (updated.length === 0) {
        clearAllFilters(cyRef.current)
      } else {
        filterByDeviceType(cyRef.current, updated)
      }
    }
  }

  const handleRelationshipToggle = (relationshipType) => {
    setRelationshipTypes(current => (
      current.includes(relationshipType)
        ? current.filter(item => item !== relationshipType)
        : [...current, relationshipType]
    ))
  }

  const handleTopologyLayerToggle = (layerKey) => {
    setTopologyLayers(current => ({ ...current, [layerKey]: !current[layerKey] }))
  }

  const handleEvidenceSourceToggle = (source) => {
    setEvidenceSources(current => (
      current.includes(source)
        ? current.filter(item => item !== source)
        : [...current, source]
    ))
  }

  const handleClearFilters = () => {
    setSelectedDeviceTypes([])
    setSearchQuery('')
    setSelectedVlan('')
    setObservedByAgentId('')
    setRelationshipTypes(DEFAULT_AGENT_RELATIONSHIPS)
    setTopologyLayers(DEFAULT_TOPOLOGY_LAYERS)
    setEvidenceSources([])
    setMinConfidence(0)
    setIncludeCollectorNodes(true)
    setCidrHints('')
    if (cyRef.current) {
      clearAllFilters(cyRef.current)
    }
  }

  const handleCreateNetworkGroup = async (event) => {
    event.preventDefault()
    setNetworkGroupError('')
    try {
      await api.createNetworkGroup({
        cidr: networkGroupForm.cidr,
        label: networkGroupForm.label || null,
        is_expected: networkGroupForm.is_expected,
        is_hidden: networkGroupForm.is_hidden,
      })
      setNetworkGroupForm({
        cidr: '',
        label: '',
        is_expected: true,
        is_hidden: false,
      })
      await fetchNetworkGroups()
      await fetchNetworkMap()
    } catch (err) {
      setNetworkGroupError(err.message)
    }
  }

  const handleEditNetworkGroup = (group) => {
    setNetworkGroupError('')
    setEditingNetworkGroupId(group.id)
    setNetworkGroupDraft({
      cidr: group.cidr,
      label: group.label || '',
      description: group.description || '',
      is_expected: Boolean(group.is_expected),
      is_hidden: Boolean(group.is_hidden),
      confidence: group.confidence ?? 100,
    })
  }

  const handleSaveNetworkGroup = async (groupId) => {
    if (!networkGroupDraft) return
    setNetworkGroupError('')
    try {
      await api.updateNetworkGroup(groupId, {
        cidr: networkGroupDraft.cidr,
        label: networkGroupDraft.label || null,
        description: networkGroupDraft.description || null,
        is_expected: networkGroupDraft.is_expected,
        is_hidden: networkGroupDraft.is_hidden,
        confidence: Number(networkGroupDraft.confidence) || 0,
      })
      setEditingNetworkGroupId(null)
      setNetworkGroupDraft(null)
      await fetchNetworkGroups()
      await fetchNetworkMap()
    } catch (err) {
      setNetworkGroupError(err.message)
    }
  }

  const handleDeleteNetworkGroup = async (groupId) => {
    setNetworkGroupError('')
    try {
      await api.deleteNetworkGroup(groupId)
      if (editingNetworkGroupId === groupId) {
        setEditingNetworkGroupId(null)
        setNetworkGroupDraft(null)
      }
      await fetchNetworkGroups()
      await fetchNetworkMap()
    } catch (err) {
      setNetworkGroupError(err.message)
    }
  }

  const handlePromoteUnresolvedGroup = async (groupId) => {
    const draft = promoteDrafts[groupId] || {}
    if (!draft.cidr) return
    setNetworkGroupError('')
    try {
      await api.createNetworkGroup({
        cidr: draft.cidr,
        label: draft.label || null,
        is_expected: true,
        is_hidden: false,
      })
      setPromoteDrafts(current => {
        const next = { ...current }
        delete next[groupId]
        return next
      })
      await fetchNetworkGroups()
      await fetchNetworkMap()
    } catch (err) {
      setNetworkGroupError(err.message)
    }
  }

  const handleNodeClick = useCallback(() => {}, [])

  const handleCyReady = useCallback((cy) => {
    cyRef.current = cy
  }, [])

  const handleRefresh = () => {
    fetchNetworkMap()
    if (showRoutes) fetchRoutes()
  }

  const hasAgentTopologyFilters = (
    observedByAgentId
    || relationshipTypes.length !== DEFAULT_AGENT_RELATIONSHIPS.length
    || Object.keys(DEFAULT_TOPOLOGY_LAYERS).some(key => topologyLayers[key] !== DEFAULT_TOPOLOGY_LAYERS[key])
    || evidenceSources.length > 0
    || minConfidence > 0
    || !includeCollectorNodes
    || networkCidrHints.length > 0
  )
  const hasActiveFilters = selectedDeviceTypes.length > 0 || searchQuery || selectedVlan || hasAgentTopologyFilters

  return (
    <div className="p-6 h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Network Map</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Interactive topology visualization
          </p>
        </div>

        {/* Primary controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* View mode switcher */}
          <div className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
            <button
              onClick={() => setViewMode('graph')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'graph'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
              title="Cytoscape.js graph view"
            >
              <svg className="w-4 h-4 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Graph
            </button>
            <button
              onClick={() => setViewMode('isometric')}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'isometric'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
              title="Isometric diagram view (experimental)"
            >
              <svg className="w-4 h-4 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
              Isometric
            </button>
          </div>

          {/* Layout mode (graph view only) */}
          {viewMode === 'graph' && (
          <select
            value={layoutMode}
            onChange={(e) => setLayoutMode(e.target.value)}
            className="select max-w-[180px]"
          >
            <option value="grouped">Grouped Layout</option>
            <option value="hierarchical">Hierarchical Layout</option>
            <option value="force">Force-Directed Layout</option>
          </select>
          )}

          {/* Graph-only controls */}
          {viewMode === 'graph' && (
          <>
          {/* Group by */}
          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
            className="select max-w-[170px]"
          >
            <option value="subnet">Group by Subnet</option>
            <option value="segment">Group by Segment</option>
            <option value="vlan">Group by VLAN</option>
          </select>

          {/* VLAN filter */}
          {vlans.length > 0 && (
            <select
              value={selectedVlan}
              onChange={(e) => setSelectedVlan(e.target.value)}
              className="select max-w-[180px]"
            >
              <option value="">All VLANs</option>
              {vlans.map(v => (
                <option key={v.vlan_id} value={v.vlan_id}>
                  {v.vlan_name} ({v.host_count})
                </option>
              ))}
            </select>
          )}

          {/* Internet / Public IP mode */}
          <select
            value={internetMode}
            onChange={(e) => setInternetMode(e.target.value)}
            className="select max-w-[180px]"
          >
            <option value="cloud">Public IPs → Internet</option>
            <option value="hide">Hide Public IPs</option>
            <option value="show">Show All IPs</option>
          </select>

          {/* Search */}
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Find device..."
              className="input pl-8 w-44"
            />
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          {/* Filter toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`btn ${showFilters ? 'btn-primary' : 'btn-secondary'} flex items-center gap-1.5`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
            Filters
            {hasActiveFilters && (
              <span className="w-2 h-2 rounded-full bg-blue-400"></span>
            )}
          </button>

          {/* Routes toggle */}
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={showRoutes}
              onChange={(e) => setShowRoutes(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
            />
            Routes
          </label>

          {/* Route through gateway toggle */}
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={routeThroughGateway}
              onChange={(e) => setRouteThroughGateway(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
            />
            Route via GW
          </label>
          </>
          )}

          {/* Refresh */}
          <button onClick={handleRefresh} className="btn btn-secondary flex items-center gap-2" disabled={loading}>
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* ── Filter bar (collapsible, graph view only) ─────── */}
      {showFilters && viewMode === 'graph' && (
        <div className="mb-4 p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Device Type Filter</h3>
            {hasActiveFilters && (
              <button onClick={handleClearFilters} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                Clear all filters
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {deviceLegend.map(({ type, label, color }) => (
              <button
                key={type}
                onClick={() => handleDeviceTypeToggle(type)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  selectedDeviceTypes.includes(type)
                    ? 'ring-2 ring-offset-1 ring-blue-500 bg-white dark:bg-gray-700 dark:ring-offset-gray-800'
                    : selectedDeviceTypes.length > 0
                    ? 'opacity-40 bg-gray-100 dark:bg-gray-700'
                    : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                } text-gray-800 dark:text-gray-200`}
              >
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }}></span>
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Agent Topology</h3>
            <div className="grid gap-3 lg:grid-cols-[minmax(180px,240px)_1fr_minmax(180px,260px)] lg:items-center">
              <select
                value={observedByAgentId}
                onChange={(e) => setObservedByAgentId(e.target.value)}
                className="select"
              >
                <option value="">All observers</option>
                {agents.map(agent => (
                  <option key={agent.id} value={agent.id}>
                    {agent.display_name || agent.hostname || agent.agent_uuid}
                  </option>
                ))}
              </select>
              <div className="flex flex-wrap gap-2">
                {AGENT_RELATIONSHIP_OPTIONS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleRelationshipToggle(value)}
                    className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                      relationshipTypes.includes(value)
                        ? 'bg-teal-600 text-white'
                        : 'bg-gray-100 text-gray-800 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={includeCollectorNodes}
                    onChange={(e) => setIncludeCollectorNodes(e.target.checked)}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
                  />
                  Collectors
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <span>Confidence</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={minConfidence}
                    onChange={(e) => setMinConfidence(Number(e.target.value) || 0)}
                    className="input w-20"
                  />
                </label>
              </div>
            </div>
          </div>
          <div className="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Topology Evidence Layers</h3>
            <div className="flex flex-wrap gap-2">
              {TOPOLOGY_LAYER_OPTIONS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleTopologyLayerToggle(key)}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                    topologyLayers[key]
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-100 text-gray-800 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Sources</span>
              {EVIDENCE_SOURCE_OPTIONS.map(source => (
                <button
                  key={source}
                  type="button"
                  onClick={() => handleEvidenceSourceToggle(source)}
                  className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    evidenceSources.includes(source)
                      ? 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {source.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Network Grouping Hints</h3>
            <input
              type="text"
              value={cidrHints}
              onChange={(e) => setCidrHints(e.target.value)}
              placeholder="192.168.224.0/23, 10.10.10.0/24"
              className="input w-full"
            />
          </div>
          <div className="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Saved Network Groups</h3>
              <span className="text-xs text-gray-500 dark:text-gray-400">{networkGroups.length} saved</span>
            </div>
            {networkGroupError && (
              <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                {networkGroupError}
              </div>
            )}
            <form onSubmit={handleCreateNetworkGroup} className="grid gap-2 lg:grid-cols-[minmax(150px,220px)_minmax(150px,1fr)_auto_auto_auto] lg:items-center">
              <input
                type="text"
                value={networkGroupForm.cidr}
                onChange={(e) => setNetworkGroupForm(current => ({ ...current, cidr: e.target.value }))}
                placeholder="192.168.224.0/23"
                className="input"
                required
              />
              <input
                type="text"
                value={networkGroupForm.label}
                onChange={(e) => setNetworkGroupForm(current => ({ ...current, label: e.target.value }))}
                placeholder="Label"
                className="input"
              />
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={networkGroupForm.is_expected}
                  onChange={(e) => setNetworkGroupForm(current => ({ ...current, is_expected: e.target.checked }))}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
                />
                Expected
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={networkGroupForm.is_hidden}
                  onChange={(e) => setNetworkGroupForm(current => ({ ...current, is_hidden: e.target.checked }))}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
                />
                Hidden
              </label>
              <button type="submit" className="btn btn-primary">
                Save
              </button>
            </form>
            {networkGroups.length > 0 && (
              <div className="mt-3 max-h-56 overflow-y-auto rounded border border-gray-200 dark:border-gray-700">
                {networkGroups.map(group => {
                  const editing = editingNetworkGroupId === group.id
                  const draft = editing ? networkGroupDraft : null
                  return (
                    <div key={group.id} className="border-b border-gray-200 p-3 last:border-b-0 dark:border-gray-700">
                      {editing ? (
                        <div className="grid gap-2 lg:grid-cols-[minmax(150px,210px)_minmax(130px,1fr)_auto_auto_auto_auto] lg:items-center">
                          <input
                            type="text"
                            value={draft.cidr}
                            onChange={(e) => setNetworkGroupDraft(current => ({ ...current, cidr: e.target.value }))}
                            className="input"
                          />
                          <input
                            type="text"
                            value={draft.label}
                            onChange={(e) => setNetworkGroupDraft(current => ({ ...current, label: e.target.value }))}
                            className="input"
                          />
                          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                            <input
                              type="checkbox"
                              checked={draft.is_expected}
                              onChange={(e) => setNetworkGroupDraft(current => ({ ...current, is_expected: e.target.checked }))}
                              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
                            />
                            Expected
                          </label>
                          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                            <input
                              type="checkbox"
                              checked={draft.is_hidden}
                              onChange={(e) => setNetworkGroupDraft(current => ({ ...current, is_hidden: e.target.checked }))}
                              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600"
                            />
                            Hidden
                          </label>
                          <button type="button" onClick={() => handleSaveNetworkGroup(group.id)} className="btn btn-primary">
                            Save
                          </button>
                          <button type="button" onClick={() => { setEditingNetworkGroupId(null); setNetworkGroupDraft(null) }} className="btn btn-secondary">
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-sm text-gray-900 dark:text-gray-100">{group.cidr}</span>
                              {group.label && (
                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{group.label}</span>
                              )}
                              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300">{group.source}</span>
                              {group.is_expected && (
                                <span className="rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300">Expected</span>
                              )}
                              {group.is_hidden && (
                                <span className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">Hidden</span>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button type="button" onClick={() => handleEditNetworkGroup(group)} className="btn btn-secondary text-xs">
                              Edit
                            </button>
                            <button type="button" onClick={() => handleDeleteNetworkGroup(group.id)} className="btn btn-secondary text-xs">
                              Delete
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {unresolvedGroups.length > 0 && (
              <div className="mt-4">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Unresolved Groups</h4>
                <div className="space-y-2">
                  {unresolvedGroups.map(group => {
                    const draft = promoteDrafts[group.id] || { cidr: '', label: '' }
                    return (
                      <div key={group.id} className="grid gap-2 rounded border border-gray-200 p-2 dark:border-gray-700 lg:grid-cols-[minmax(130px,180px)_minmax(150px,220px)_minmax(130px,1fr)_auto] lg:items-center">
                        <span className="text-sm text-gray-700 dark:text-gray-300">{group.label}</span>
                        <input
                          type="text"
                          value={draft.cidr}
                          onChange={(e) => setPromoteDrafts(current => ({ ...current, [group.id]: { ...draft, cidr: e.target.value } }))}
                          placeholder="Actual CIDR"
                          className="input"
                        />
                        <input
                          type="text"
                          value={draft.label}
                          onChange={(e) => setPromoteDrafts(current => ({ ...current, [group.id]: { ...draft, label: e.target.value } }))}
                          placeholder="Label"
                          className="input"
                        />
                        <button
                          type="button"
                          onClick={() => handlePromoteUnresolvedGroup(group.id)}
                          className="btn btn-primary"
                          disabled={!draft.cidr}
                        >
                          Save
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Inline warnings for secondary fetch failures */}
      {warnings.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {warnings.map(({ key, msg }) => (
            <div
              key={key}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg text-sm"
            >
              <svg className="w-4 h-4 text-yellow-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span className="text-yellow-700 dark:text-yellow-400">{msg}</span>
              <button
                onClick={() => setWarnings(prev => prev.filter(w => w.key !== key))}
                className="text-yellow-500 hover:text-yellow-700 dark:hover:text-yellow-300 ml-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Stats bar ──────────────────────────────────────── */}
      {stats.total_hosts !== undefined && (
        <div className="flex flex-nowrap gap-2 mb-2 overflow-x-auto">
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Hosts</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.total_hosts || 0}</p>
          </div>
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Edges</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.total_edges || 0}</p>
          </div>
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">VLANs</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.vlans || 0}</p>
          </div>
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Subnets</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.subnets || 0}</p>
          </div>
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Cross-VLAN</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.cross_vlan_edges || 0}</p>
          </div>
          {stats.internet_connections > 0 && (
            <div className="card px-3 py-2 flex-1 min-w-0">
              <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Internet</p>
              <p className="text-lg font-bold text-sky-600 dark:text-sky-400">{stats.internet_connections}</p>
            </div>
          )}
          {stats.agent_topology_edges > 0 && (
            <div className="card px-3 py-2 flex-1 min-w-0">
              <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Agent Edges</p>
              <p className="text-lg font-bold text-teal-600 dark:text-teal-400">{stats.agent_topology_edges}</p>
            </div>
          )}
          <div className="card px-3 py-2 flex-1 min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Load Time</p>
            <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.generation_time_ms || 0}ms</p>
          </div>
        </div>
      )}

      {/* ── Network Map ────────────────────────────────────── */}
      {!error && (
        <div className="card flex-1 min-h-0" style={{ minHeight: '400px' }}>
          <MapErrorBoundary>
            {viewMode === 'graph' ? (
              <CytoscapeNetworkMap
                elements={mergedElements}
                layoutMode={layoutMode}
                onNodeClick={handleNodeClick}
                onCyReady={handleCyReady}
                loading={loading}
              />
            ) : (
              <IsoflowNetworkMap
                elements={mergedElements}
                loading={loading}
              />
            )}
          </MapErrorBoundary>
        </div>
      )}
    </div>
  )
}
