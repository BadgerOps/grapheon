import { useState, useEffect } from 'react'
import NetworkMap from '../components/NetworkMap'
import * as api from '../api/client'

/**
 * Map Page - Network topology visualization
 *
 * Features:
 * - Interactive network graph
 * - Subnet filtering
 * - Stats summary
 * - Traceroute path overlay
 */
export default function Map() {
  const [mapData, setMapData] = useState({ nodes: [], edges: [], groups: {}, stats: {} })
  const [subnets, setSubnets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedSubnet, setSelectedSubnet] = useState('')
  const [groupBySubnet, setGroupBySubnet] = useState(true)
  const [showRoutes, setShowRoutes] = useState(false)
  const [routeData, setRouteData] = useState({ traces: {}, path_edges: [] })

  useEffect(() => {
    fetchNetworkMap()
    fetchSubnets()
  }, [selectedSubnet, groupBySubnet])

  useEffect(() => {
    if (showRoutes) {
      fetchRoutes()
    }
  }, [showRoutes])

  const fetchNetworkMap = async () => {
    try {
      setLoading(true)
      const params = {
        group_by_subnet: groupBySubnet,
      }
      if (selectedSubnet) {
        params.subnet_filter = selectedSubnet
      }
      const data = await api.getNetworkMap(params)
      setMapData(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchSubnets = async () => {
    try {
      const data = await api.getSubnets()
      setSubnets(data.subnets || [])
    } catch (err) {
      console.error('Failed to fetch subnets:', err)
    }
  }

  const fetchRoutes = async () => {
    try {
      const data = await api.getNetworkRoutes()
      setRouteData(data)
    } catch (err) {
      console.error('Failed to fetch routes:', err)
    }
  }

  const handleNodeClick = (node) => {
    // Node selection is handled by NetworkMap component
    // This callback can be used for additional actions if needed
  }

  const handleRefresh = () => {
    fetchNetworkMap()
    if (showRoutes) {
      fetchRoutes()
    }
  }

  return (
    <div className="p-6 h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Network Map</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Interactive topology visualization
          </p>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Subnet filter */}
          <select
            value={selectedSubnet}
            onChange={(e) => setSelectedSubnet(e.target.value)}
            className="select max-w-[200px]"
          >
            <option value="">All Subnets</option>
            {subnets.map((subnet) => (
              <option key={subnet.subnet} value={subnet.subnet.split('/')[0]}>
                {subnet.subnet} ({subnet.host_count} hosts)
              </option>
            ))}
          </select>

          {/* Group toggle */}
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={groupBySubnet}
              onChange={(e) => setGroupBySubnet(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
            />
            Group by Subnet
          </label>

          {/* Routes toggle */}
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={showRoutes}
              onChange={(e) => setShowRoutes(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
            />
            Show Routes
          </label>

          {/* Refresh button */}
          <button
            onClick={handleRefresh}
            className="btn btn-secondary flex items-center gap-2"
            disabled={loading}
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Stats bar */}
      {mapData.stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="card p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Hosts</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {mapData.stats.total_hosts || 0}
            </p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Connections</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {mapData.stats.total_connections || 0}
            </p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Subnets</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {mapData.stats.subnets || 0}
            </p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Load Time</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {mapData.stats.generation_time_ms || 0}ms
            </p>
          </div>
        </div>
      )}

      {/* Network Map */}
      <div className="card" style={{ height: 'calc(100% - 180px)', minHeight: '500px' }}>
        <NetworkMap
          nodes={mapData.nodes}
          edges={mapData.edges}
          groups={mapData.groups}
          onNodeClick={handleNodeClick}
          loading={loading}
        />
      </div>

      {/* Route traces info */}
      {showRoutes && routeData.traces && Object.keys(routeData.traces).length > 0 && (
        <div className="mt-4 card p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Traceroute Data
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {Object.keys(routeData.traces).length} traces loaded with {routeData.path_edges.length} path segments
          </p>
        </div>
      )}
    </div>
  )
}
