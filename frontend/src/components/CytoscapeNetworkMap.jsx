import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import fcose from 'cytoscape-fcose'
import cola from 'cytoscape-cola'
import { getLightStyles, getDarkStyles, layoutPresets, deviceLegend, edgeLegend } from '../styles/cytoscape-theme'
import { exportMapAsPNG, exportMapAsSVG, toggleFullscreen } from '../services/mapExport'

// Register layout extensions
cytoscape.use(dagre)
cytoscape.use(fcose)
cytoscape.use(cola)

/**
 * CytoscapeNetworkMap — Interactive network topology visualization
 *
 * Features:
 * - Compound nodes: VLAN → Subnet → Host hierarchy
 * - Three layout modes: hierarchical (dagre), grouped (fcose), force-directed (cola)
 * - Device type styling with distinct shapes and colors
 * - Dark/light mode support
 * - Click to select, double-click to navigate
 * - Zoom/pan/fit controls
 * - Stats and legend overlays
 */
export default function CytoscapeNetworkMap({
  elements = { nodes: [], edges: [] },
  layoutMode = 'grouped',
  onNodeClick,
  onCyReady,
  loading = false,
}) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const navigate = useNavigate()
  const [selectedNode, setSelectedNode] = useState(null)
  const [stats, setStats] = useState({ nodes: 0, edges: 0, vlans: 0, subnets: 0 })
  const [isDarkMode, setIsDarkMode] = useState(() =>
    document.documentElement.classList.contains('dark')
  )
  const [showLegend, setShowLegend] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)

  // Watch for theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          setIsDarkMode(document.documentElement.classList.contains('dark'))
        }
      })
    })
    observer.observe(document.documentElement, { attributes: true })
    return () => observer.disconnect()
  }, [])

  // Watch for fullscreen changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isFs = !!document.fullscreenElement
      setIsFullscreen(isFs)
      // Re-fit the graph when fullscreen changes
      if (cyRef.current) {
        setTimeout(() => {
          cyRef.current.resize()
          cyRef.current.fit(40)
        }, 100)
      }
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  // Get current style based on theme
  const currentStyle = useMemo(() => {
    return isDarkMode ? getDarkStyles() : getLightStyles()
  }, [isDarkMode])

  // ── Initialize Cytoscape ──────────────────────────────────────
  const initCytoscape = useCallback(() => {
    if (!containerRef.current) return

    // Destroy previous instance
    if (cyRef.current) {
      cyRef.current.destroy()
      cyRef.current = null
    }

    const allNodes = elements.nodes || []
    const allEdges = elements.edges || []

    if (allNodes.length === 0) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...allNodes, ...allEdges],
      style: currentStyle,
      layout: { name: 'preset' }, // We'll run layout separately
      minZoom: 0.1,
      maxZoom: 5,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: true,
      selectionType: 'single',
    })

    cyRef.current = cy

    // ── Event handlers ────────────────────────────────────────
    cy.on('tap', 'node', (evt) => {
      const node = evt.target
      const data = node.data()

      // Skip compound nodes
      if (data.type === 'vlan' || data.type === 'subnet') return

      setSelectedNode(data)
      if (onNodeClick) onNodeClick(data)
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        setSelectedNode(null)
      }
    })

    cy.on('dbltap', 'node', (evt) => {
      const data = evt.target.data()
      if (data.type !== 'vlan' && data.type !== 'subnet' && data.id) {
        navigate(`/hosts/${data.id}`)
      }
    })

    // Tooltip on hover
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target
      containerRef.current.style.cursor = 'pointer'
      // Could add tippy.js tooltip here in future
    })

    cy.on('mouseout', 'node', () => {
      containerRef.current.style.cursor = 'default'
    })

    // ── Calculate stats ───────────────────────────────────────
    const hostNodes = allNodes.filter(n => n.data.type !== 'vlan' && n.data.type !== 'subnet' && n.data.type !== 'internet')
    const vlanNodes = allNodes.filter(n => n.data.type === 'vlan')
    const subnetNodes = allNodes.filter(n => n.data.type === 'subnet')

    setStats({
      nodes: hostNodes.length,
      edges: allEdges.length,
      vlans: vlanNodes.length,
      subnets: subnetNodes.length,
    })

    // ── Run layout ────────────────────────────────────────────
    const layoutConfig = layoutPresets[layoutMode] || layoutPresets.grouped
    const layout = cy.layout(layoutConfig)
    layout.run()

    // Notify parent when cy is ready
    if (onCyReady) {
      onCyReady(cy)
    }
  }, [elements, currentStyle, layoutMode, navigate, onNodeClick, onCyReady])

  // ── Lifecycle: rebuild on data/theme change ───────────────────
  useEffect(() => {
    if (!containerRef.current || loading) return
    initCytoscape()

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [loading, initCytoscape])

  // ── Update stylesheet on theme change without full rebuild ────
  useEffect(() => {
    if (cyRef.current) {
      cyRef.current.style(currentStyle)
    }
  }, [currentStyle])

  // ── Re-run layout when mode changes ──────────────────────────
  const runLayout = useCallback((mode) => {
    if (!cyRef.current) return
    const config = layoutPresets[mode] || layoutPresets.grouped
    const layout = cyRef.current.layout(config)
    layout.run()
  }, [])

  // ── Control functions ─────────────────────────────────────────
  const handleZoomIn = () => {
    if (cyRef.current) {
      cyRef.current.zoom({
        level: cyRef.current.zoom() * 1.3,
        renderedPosition: { x: containerRef.current.clientWidth / 2, y: containerRef.current.clientHeight / 2 }
      })
    }
  }

  const handleZoomOut = () => {
    if (cyRef.current) {
      cyRef.current.zoom({
        level: cyRef.current.zoom() / 1.3,
        renderedPosition: { x: containerRef.current.clientWidth / 2, y: containerRef.current.clientHeight / 2 }
      })
    }
  }

  const handleFit = () => {
    if (cyRef.current) {
      cyRef.current.animate({ fit: { padding: 40 } }, { duration: 400 })
    }
  }

  const handleCenter = () => {
    if (cyRef.current) {
      cyRef.current.animate({ center: {} }, { duration: 300 })
    }
  }

  const hasElements = (elements.nodes || []).length > 0

  return (
    <div className="relative h-full">
      {/* Cytoscape container */}
      <div
        ref={containerRef}
        className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg"
        style={{
          height: '100%',
          minHeight: '500px',
          display: (loading || !hasElements) ? 'none' : 'block',
        }}
      />

      {/* Loading overlay */}
      {loading && (
        <div className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700" style={{ height: '100%', minHeight: '500px' }}>
          <div className="text-center">
            <div className="spinner mx-auto mb-4"></div>
            <p className="text-gray-600 dark:text-gray-400">Computing network topology...</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !hasElements && (
        <div className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700" style={{ height: '100%', minHeight: '500px' }}>
          <div className="text-center">
            <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
            </svg>
            <p className="text-gray-600 dark:text-gray-400">No hosts to display</p>
            <p className="text-sm text-gray-500 mt-2">Import network data to see the topology</p>
          </div>
        </div>
      )}

      {/* ── Controls overlay ─────────────────────────────────── */}
      {hasElements && !loading && (
        <div className="absolute top-4 right-4 flex flex-col gap-2">
          <button onClick={handleZoomIn} className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors" title="Zoom In">
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
            </svg>
          </button>
          <button onClick={handleZoomOut} className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors" title="Zoom Out">
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
            </svg>
          </button>
          <button onClick={handleFit} className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors" title="Fit to View">
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
            </svg>
          </button>
          <button onClick={handleCenter} className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors" title="Center">
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm0 0V4m0 16v-4m8-4h-4M4 12h4" />
            </svg>
          </button>
          <button onClick={() => runLayout(layoutMode)} className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors" title="Re-run Layout">
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {/* Separator */}
          <div className="w-8 h-px bg-gray-300 dark:bg-gray-600 mx-auto"></div>

          {/* Fullscreen toggle */}
          <button
            onClick={() => toggleFullscreen(containerRef.current?.parentElement)}
            className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {isFullscreen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              )}
            </svg>
          </button>

          {/* Export PNG */}
          <button
            onClick={() => {
              const date = new Date().toISOString().slice(0, 10)
              exportMapAsPNG(cyRef.current, `network-map-${date}.png`)
            }}
            className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Export as PNG"
          >
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </button>

          {/* Pop out */}
          <button
            onClick={() => window.open('/map/fullscreen', 'network-map-full', 'width=1920,height=1080')}
            className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Open in New Window"
          >
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
            </svg>
          </button>
        </div>
      )}

      {/* ── Stats overlay ────────────────────────────────────── */}
      {hasElements && !loading && (
        <div className="absolute bottom-4 left-4 flex flex-wrap gap-2">
          <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
            <span className="text-gray-500 dark:text-gray-400">Hosts:</span>
            <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.nodes}</span>
          </div>
          <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
            <span className="text-gray-500 dark:text-gray-400">Edges:</span>
            <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.edges}</span>
          </div>
          {stats.vlans > 0 && (
            <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
              <span className="text-gray-500 dark:text-gray-400">VLANs:</span>
              <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.vlans}</span>
            </div>
          )}
          <div className="px-3 py-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-md text-sm">
            <span className="text-gray-500 dark:text-gray-400">Subnets:</span>
            <span className="ml-1 font-medium text-gray-900 dark:text-gray-100">{stats.subnets}</span>
          </div>
        </div>
      )}

      {/* ── Selected node info panel ─────────────────────────── */}
      {selectedNode && (
        <div className="absolute bottom-4 right-4 max-w-xs p-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {selectedNode.hostname || selectedNode.ip}
            </h4>
            <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 ml-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
            <p><span className="text-gray-500">IP:</span> {selectedNode.ip}</p>
            {selectedNode.mac && <p><span className="text-gray-500">MAC:</span> {selectedNode.mac}</p>}
            {selectedNode.os && <p><span className="text-gray-500">OS:</span> {selectedNode.os}</p>}
            {selectedNode.vendor && <p><span className="text-gray-500">Vendor:</span> {selectedNode.vendor}</p>}
            {selectedNode.device_type && selectedNode.device_type !== 'unknown' && (
              <p>
                <span className="text-gray-500">Type:</span>{' '}
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: selectedNode.color }}></span>
                  {selectedNode.device_type}
                </span>
              </p>
            )}
            {selectedNode.is_gateway && <p className="text-orange-500 font-medium">Gateway / Router</p>}
            <p><span className="text-gray-500">Open Ports:</span> {selectedNode.open_ports || 0}</p>
            <p><span className="text-gray-500">Subnet:</span> {selectedNode.subnet}</p>
            {selectedNode.vlan_id != null && (
              <p>
                <span className="text-gray-500">VLAN:</span>{' '}
                {selectedNode.vlan_name || `VLAN ${selectedNode.vlan_id}`} ({selectedNode.vlan_id})
              </p>
            )}
            {selectedNode.segment && (
              <p><span className="text-gray-500">Segment:</span> {selectedNode.segment}</p>
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

      {/* ── Legend ────────────────────────────────────────────── */}
      {hasElements && !loading && showLegend && (
        <div className="absolute top-4 left-4 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-md text-xs max-h-[80%] overflow-y-auto">
          <div className="flex items-center justify-between mb-2">
            <h5 className="font-semibold text-gray-700 dark:text-gray-300">Legend</h5>
            <button onClick={() => setShowLegend(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Device types */}
          <h6 className="text-gray-500 dark:text-gray-400 mt-1 mb-1 uppercase tracking-wider" style={{ fontSize: '10px' }}>Devices</h6>
          <div className="space-y-1 mb-3">
            {deviceLegend.map(({ type, label, color, shape }) => (
              <div key={type} className="flex items-center gap-2">
                <span
                  className="w-3 h-3 flex-shrink-0"
                  style={{
                    backgroundColor: color,
                    borderRadius: shape === 'circle' ? '50%' : shape === 'diamond' ? '2px' : '1px',
                    transform: shape === 'diamond' ? 'rotate(45deg) scale(0.7)' : 'none',
                    clipPath: shape === 'triangle' ? 'polygon(50% 0%, 0% 100%, 100% 100%)' :
                              shape === 'star' ? 'polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)' :
                              shape === 'hexagon' ? 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)' :
                              'none',
                  }}
                ></span>
                <span className="text-gray-600 dark:text-gray-400">{label}</span>
              </div>
            ))}
          </div>

          {/* Edge types */}
          <h6 className="text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wider" style={{ fontSize: '10px' }}>Connections</h6>
          <div className="space-y-1 mb-3">
            {edgeLegend.map(({ type, label, color, style }) => (
              <div key={type} className="flex items-center gap-2">
                <span
                  className="h-0.5 w-4 flex-shrink-0"
                  style={{
                    backgroundColor: color,
                    borderTop: style === 'dashed' ? `2px dashed ${color}` : style === 'dotted' ? `2px dotted ${color}` : 'none',
                    height: style !== 'solid' ? 0 : undefined,
                  }}
                ></span>
                <span className="text-gray-600 dark:text-gray-400">{label}</span>
              </div>
            ))}
          </div>

          {/* Compound nodes */}
          <h6 className="text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wider" style={{ fontSize: '10px' }}>Groups</h6>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border-2 border-blue-500 bg-blue-500/10"></span>
              <span className="text-gray-600 dark:text-gray-400">VLAN</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border border-dashed border-gray-400 bg-gray-400/10"></span>
              <span className="text-gray-600 dark:text-gray-400">Subnet</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border-2 border-dashed border-sky-500 bg-sky-500/10"></span>
              <span className="text-gray-600 dark:text-gray-400">Public IPs</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 flex-shrink-0" style={{ backgroundColor: '#f97316', transform: 'rotate(45deg) scale(0.8)', borderRadius: '2px', border: '2px solid #c2410c' }}></span>
              <span className="text-gray-600 dark:text-gray-400">Shared Gateway</span>
            </div>
          </div>

          <p className="mt-2 text-gray-500 dark:text-gray-500">Double-click to open details</p>
        </div>
      )}

      {/* Legend toggle (when hidden) */}
      {hasElements && !loading && !showLegend && (
        <button
          onClick={() => setShowLegend(true)}
          className="absolute top-4 left-4 p-2 bg-white dark:bg-gray-800 rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          title="Show Legend"
        >
          <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      )}
    </div>
  )
}
