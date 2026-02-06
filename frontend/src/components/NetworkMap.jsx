import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { DataSet, Network } from 'vis-network/standalone/esm/vis-network'
import 'vis-network/styles/vis-network.css'

/**
 * NetworkMap - Interactive network topology visualization using vis-network
 *
 * Features:
 * - Force-directed physics layout
 * - Subnet grouping with colored clusters
 * - Click-to-drill-down navigation
 * - Zoom and pan controls
 * - Node tooltips with host details
 */
export default function NetworkMap({ nodes = [], edges = [], groups = {}, onNodeClick, loading = false }) {
  const containerRef = useRef(null)
  const networkRef = useRef(null)
  const navigate = useNavigate()
  const [selectedNode, setSelectedNode] = useState(null)
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })
  const [hasRouteEdges, setHasRouteEdges] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(() =>
    document.documentElement.classList.contains('dark')
  )

  // Watch for theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          const isDark = document.documentElement.classList.contains('dark')
          setIsDarkMode(isDark)
        }
      })
    })

    observer.observe(document.documentElement, { attributes: true })
    return () => observer.disconnect()
  }, [])

  const buildGroupConfig = (groups, isDark) => {
    const config = {}
    Object.entries(groups).forEach(([subnet, data]) => {
      config[subnet] = {
        color: {
          background: data.color || '#6b7280',
          border: isDark ? '#374151' : '#d1d5db',
          highlight: {
            background: data.color || '#6b7280',
            border: '#3b82f6',
          },
        },
      }
    })
    return config
  }

  // Enhance nodes with gateway styling
  const enhanceNodes = useCallback((rawNodes, fontDefaults) => {
    return rawNodes.map(node => {
      if (node.is_gateway) {
        return {
          ...node,
          shape: 'diamond',
          size: 30,
          color: {
            background: '#f97316',
            border: '#ea580c',
            highlight: { background: '#fb923c', border: '#3b82f6' },
          },
          font: { ...fontDefaults, size: 14 },
          borderWidth: 3,
        }
      }
      return node
    })
  }, [])

  // Enhance edges with cross-segment and route styling
  const enhanceEdges = useCallback((rawEdges) => {
    return rawEdges.map(edge => {
      // Handle route edges
      if (edge.route_edge) {
        return {
          ...edge,
          color: '#22c55e',
          dashes: [5, 5],
          arrows: {
            to: { enabled: true, scaleFactor: 0.5 },
          },
          smooth: {
            type: 'curvedCW',
          },
        }
      }

      // Handle cross-segment edges
      if (edge.cross_segment) {
        return {
          ...edge,
          color: '#fbbf24',
          dashes: [8, 4],
          smooth: {
            type: 'curvedCCW',
          },
        }
      }

      // Regular edges remain unchanged
      return edge
    })
  }, [])

  const initNetwork = useCallback(() => {
    if (!containerRef.current) return

    // Destroy previous instance first
    if (networkRef.current) {
      networkRef.current.destroy()
      networkRef.current = null
    }

    const isDark = isDarkMode

    const fontDefaults = {
      size: 12,
      color: isDark ? '#e5e7eb' : '#1f2937',
      face: 'Inter, system-ui, sans-serif',
    }

    const options = {
      nodes: {
        borderWidth: 2,
        borderWidthSelected: 4,
        font: fontDefaults,
        shadow: {
          enabled: true,
          color: 'rgba(0,0,0,0.2)',
          size: 8,
          x: 2,
          y: 2,
        },
      },
      edges: {
        width: 1.5,
        smooth: {
          type: 'continuous',
          roundness: 0.5,
        },
        arrows: {
          to: { enabled: false },
        },
        color: {
          color: isDark ? '#4b5563' : '#9ca3af',
          highlight: '#3b82f6',
          hover: '#60a5fa',
        },
      },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -50,
          centralGravity: 0.01,
          springLength: 150,
          springConstant: 0.08,
          damping: 0.4,
          avoidOverlap: 0.5,
        },
        stabilization: {
          enabled: true,
          iterations: 200,
          updateInterval: 25,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        hideEdgesOnDrag: true,
        hideEdgesOnZoom: true,
        navigationButtons: true,
        keyboard: {
          enabled: true,
          bindToWindow: false,
        },
      },
      groups: buildGroupConfig(groups, isDark),
    }

    const enhancedNodes = enhanceNodes(nodes, fontDefaults)
    const enhancedEdges = enhanceEdges(edges)

    const nodesDataset = new DataSet(enhancedNodes)
    const edgesDataset = new DataSet(enhancedEdges)

    networkRef.current = new Network(
      containerRef.current,
      { nodes: nodesDataset, edges: edgesDataset },
      options
    )

    networkRef.current.on('click', (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0]
        const node = nodes.find(n => n.id === nodeId)
        setSelectedNode(node)

        if (onNodeClick) {
          onNodeClick(node)
        }
      } else {
        setSelectedNode(null)
      }
    })

    networkRef.current.on('doubleClick', (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0]
        navigate(`/hosts/${nodeId}`)
      }
    })

    networkRef.current.on('stabilizationIterationsDone', () => {
      if (networkRef.current) {
        networkRef.current.setOptions({ physics: { enabled: false } })
      }
    })

    setStats({ nodes: nodes.length, edges: edges.length })

    // Check if any route edges exist
    const hasRoutes = edges.some(edge => edge.route_edge)
    setHasRouteEdges(hasRoutes)
  }, [nodes, edges, groups, navigate, onNodeClick, isDarkMode, enhanceNodes, enhanceEdges])

  // Single effect: rebuild network when data or settings change
  useEffect(() => {
    if (!containerRef.current || loading) return
    initNetwork()

    return () => {
      if (networkRef.current) {
        networkRef.current.destroy()
        networkRef.current = null
      }
    }
  }, [loading, initNetwork])

  // Control functions
  const handleZoomIn = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale()
      networkRef.current.moveTo({ scale: scale * 1.3 })
    }
  }

  const handleZoomOut = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale()
      networkRef.current.moveTo({ scale: scale / 1.3 })
    }
  }

  const handleFit = () => {
    if (networkRef.current) {
      networkRef.current.fit({ animation: true })
    }
  }

  const handleTogglePhysics = () => {
    if (networkRef.current) {
      const physics = networkRef.current.physics
      networkRef.current.setOptions({
        physics: { enabled: !physics.options.enabled }
      })
    }
  }

  return (
    <div className="relative h-full">
      {/* Network visualization container — always mounted to prevent vis-network DOM errors */}
      <div
        ref={containerRef}
        className="network-canvas bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700"
        style={{ height: '100%', minHeight: '500px', display: (loading || nodes.length === 0) ? 'none' : 'block' }}
      />

      {/* Loading overlay */}
      {loading && (
        <div className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700" style={{ height: '100%', minHeight: '500px' }}>
          <div className="text-center">
            <div className="spinner mx-auto mb-4"></div>
            <p className="text-gray-600 dark:text-gray-400">Loading network map...</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && nodes.length === 0 && (
        <div className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700" style={{ height: '100%', minHeight: '500px' }}>
          <div className="text-center">
            <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
            </svg>
            <p className="text-gray-600 dark:text-gray-400">No hosts to display</p>
            <p className="text-sm text-gray-500 dark:text-gray-500 mt-2">Import network data to see the topology</p>
          </div>
        </div>
      )}

      {/* Controls overlay */}
      <div className="absolute top-4 right-4 flex flex-col gap-2">
        <button
          onClick={handleZoomIn}
          className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          title="Zoom In"
        >
          <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
          </svg>
        </button>
        <button
          onClick={handleZoomOut}
          className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          title="Zoom Out"
        >
          <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
          </svg>
        </button>
        <button
          onClick={handleFit}
          className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          title="Fit to View"
        >
          <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
          </svg>
        </button>
        <button
          onClick={handleTogglePhysics}
          className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          title="Toggle Physics"
        >
          <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </button>
      </div>

      {/* Stats overlay */}
      <div className="absolute bottom-4 left-4 flex gap-4">
        <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
          <span className="text-gray-500 dark:text-gray-400">Nodes:</span>
          <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.nodes}</span>
        </div>
        <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
          <span className="text-gray-500 dark:text-gray-400">Edges:</span>
          <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.edges}</span>
        </div>
      </div>

      {/* Selected node info */}
      {selectedNode && (
        <div className="absolute bottom-4 right-4 max-w-xs p-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100">{selectedNode.hostname || selectedNode.ip}</h4>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
            <p><span className="text-gray-500">IP:</span> {selectedNode.ip}</p>
            {selectedNode.os && <p><span className="text-gray-500">OS:</span> {selectedNode.os}</p>}
            {selectedNode.device_type && <p><span className="text-gray-500">Type:</span> {selectedNode.device_type}</p>}
            {selectedNode.is_gateway && <p className="text-orange-500 font-medium">Gateway / Router</p>}
            <p><span className="text-gray-500">Open Ports:</span> {selectedNode.open_ports || 0}</p>
            <p><span className="text-gray-500">Subnet:</span> {selectedNode.subnet}</p>
            {selectedNode.segment && <p><span className="text-gray-500">Segment:</span> {selectedNode.segment}</p>}
            {selectedNode.group && selectedNode.group !== selectedNode.subnet && (
              <p><span className="text-gray-500">Segment:</span> {selectedNode.group}</p>
            )}
          </div>
          <button
            onClick={() => navigate(`/hosts/${selectedNode.id}`)}
            className="mt-3 w-full btn btn-primary text-sm"
          >
            View Details
          </button>
        </div>
      )}

      {/* Legend */}
      <div className="absolute top-4 left-4 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-md text-xs">
        <h5 className="font-semibold text-gray-700 dark:text-gray-300 mb-2">Device Types</h5>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-blue-500"></span>
            <span className="text-gray-600 dark:text-gray-400">Server</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-green-500"></span>
            <span className="text-gray-600 dark:text-gray-400">Workstation</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-orange-500"></span>
            <span className="text-gray-600 dark:text-gray-400">Router</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-purple-500"></span>
            <span className="text-gray-600 dark:text-gray-400">Switch</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-500"></span>
            <span className="text-gray-600 dark:text-gray-400">Firewall</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rotate-45 bg-orange-500" style={{ clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)' }}></span>
            <span className="text-gray-600 dark:text-gray-400">Gateway</span>
          </div>
        </div>

        <h5 className="font-semibold text-gray-700 dark:text-gray-300 mb-2 mt-3">Edge Types</h5>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4 bg-gray-400" style={{ backgroundColor: isDarkMode ? '#4b5563' : '#9ca3af' }}></span>
            <span className="text-gray-600 dark:text-gray-400">Regular</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4" style={{ backgroundColor: '#fbbf24', backgroundImage: 'repeating-linear-gradient(90deg, #fbbf24 0px, #fbbf24 8px, transparent 8px, transparent 12px)' }}></span>
            <span className="text-gray-600 dark:text-gray-400">Cross-segment</span>
          </div>
          {hasRouteEdges && (
            <div className="flex items-center gap-2">
              <span className="h-0.5 w-4" style={{ backgroundColor: '#22c55e', backgroundImage: 'repeating-linear-gradient(90deg, #22c55e 0px, #22c55e 5px, transparent 5px, transparent 10px)' }}></span>
              <span className="text-gray-600 dark:text-gray-400">Route path</span>
            </div>
          )}
        </div>

        <p className="mt-2 text-gray-500 dark:text-gray-500">Double-click to open details</p>
      </div>
    </div>
  )
}
