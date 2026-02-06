import { useState, useEffect, useRef, useCallback } from 'react'
import CytoscapeNetworkMap from '../components/CytoscapeNetworkMap'
import MapErrorBoundary from '../components/MapErrorBoundary'
import { searchAndFocus, filterByDeviceType, filterByVlan, clearAllFilters } from '../services/graphFilters'
import { deviceLegend } from '../styles/cytoscape-theme'
import * as api from '../api/client'

/**
 * Map Page — Network topology visualization
 *
 * Features:
 * - Cytoscape.js interactive graph with compound node hierarchy
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
  const [routeData, setRouteData] = useState({ traces: {}, path_edges: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState([])

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

  // ── Cytoscape ref ───────────────────────────────────────────────
  const cyRef = useRef(null)

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
  }, [groupBy, layoutMode, selectedVlan, internetMode, routeThroughGateway])

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
  }, [fetchNetworkMap])

  useEffect(() => {
    if (showRoutes) fetchRoutes()
  }, [showRoutes])

  // ── Merge route edges into elements ─────────────────────────────
  const mergedElements = (() => {
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
  })()

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

  const handleClearFilters = () => {
    setSelectedDeviceTypes([])
    setSearchQuery('')
    setSelectedVlan('')
    if (cyRef.current) {
      clearAllFilters(cyRef.current)
    }
  }

  const handleCyReady = (cy) => {
    cyRef.current = cy
  }

  const handleRefresh = () => {
    fetchNetworkMap()
    if (showRoutes) fetchRoutes()
  }

  const hasActiveFilters = selectedDeviceTypes.length > 0 || searchQuery || selectedVlan

  return (
    <div className="p-6 h-[calc(100vh-8rem)]">
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
          {/* Layout mode */}
          <select
            value={layoutMode}
            onChange={(e) => setLayoutMode(e.target.value)}
            className="select max-w-[180px]"
          >
            <option value="grouped">Grouped Layout</option>
            <option value="hierarchical">Hierarchical Layout</option>
            <option value="force">Force-Directed Layout</option>
          </select>

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

          {/* Refresh */}
          <button onClick={handleRefresh} className="btn btn-secondary flex items-center gap-2" disabled={loading}>
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* ── Filter bar (collapsible) ────────────────────────── */}
      {showFilters && (
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
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-4">
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Hosts</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.total_hosts || 0}</p>
          </div>
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Edges</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.total_edges || 0}</p>
          </div>
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">VLANs</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.vlans || 0}</p>
          </div>
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Subnets</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.subnets || 0}</p>
          </div>
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Cross-VLAN</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.cross_vlan_edges || 0}</p>
          </div>
          {stats.internet_connections > 0 && (
            <div className="card p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">Internet</p>
              <p className="text-xl font-bold text-sky-600 dark:text-sky-400">{stats.internet_connections}</p>
            </div>
          )}
          <div className="card p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Load Time</p>
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{stats.generation_time_ms || 0}ms</p>
          </div>
        </div>
      )}

      {/* ── Network Map ────────────────────────────────────── */}
      {!error && (
        <div className="card" style={{ height: 'calc(100% - 180px)', minHeight: '500px' }}>
          <MapErrorBoundary>
            <CytoscapeNetworkMap
              elements={mergedElements}
              layoutMode={layoutMode}
              onNodeClick={() => {}}
              onCyReady={handleCyReady}
              loading={loading}
            />
          </MapErrorBoundary>
        </div>
      )}
    </div>
  )
}
