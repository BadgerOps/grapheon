/**
 * Map export and fullscreen utilities for the network topology visualization.
 */

/**
 * Export the current Cytoscape graph as a PNG image.
 * Uses Cytoscape's built-in png() method with high resolution.
 */
export function exportMapAsPNG(cy, filename = 'network-map.png') {
  if (!cy) return

  const isDark = document.documentElement.classList.contains('dark')
  const bgColor = isDark ? '#111827' : '#f9fafb'

  const pngData = cy.png({
    full: true,
    maxWidth: 4096,
    maxHeight: 4096,
    bg: bgColor,
    scale: 2,
  })

  const link = document.createElement('a')
  link.href = pngData
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/**
 * Export the current Cytoscape graph as an SVG vector image.
 */
export function exportMapAsSVG(cy, filename = 'network-map.svg') {
  if (!cy) return

  const svgContent = cy.svg({
    full: true,
    scale: 1,
  })

  const blob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)

  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Download a network topology export from the backend API.
 * Triggers a file download in the browser.
 *
 * @param {'graphml'|'drawio'} format - Export format
 * @param {string|null} subnetFilter - Optional subnet CIDR filter
 * @param {string} showInternet - Public IP mode (cloud/hide/show)
 */
export async function exportNetworkGraph(format, subnetFilter = null, showInternet = 'cloud') {
  const params = new URLSearchParams()
  if (subnetFilter) params.append('subnet_filter', subnetFilter)
  if (showInternet) params.append('show_internet', showInternet)
  const paramStr = params.toString()
  const url = `/api/export/network/${format}${paramStr ? '?' + paramStr : ''}`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }

  // Get filename from Content-Disposition header or generate one
  const disposition = response.headers.get('content-disposition')
  let filename = `network-topology.${format}`
  if (disposition) {
    const match = disposition.match(/filename=(.+)/)
    if (match) filename = match[1]
  }

  const blob = await response.blob()
  const blobUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(blobUrl)
}

/**
 * Toggle fullscreen mode on the given element.
 * Returns true if entering fullscreen, false if exiting.
 */
export function toggleFullscreen(element) {
  if (!element) return false

  if (document.fullscreenElement) {
    document.exitFullscreen()
    return false
  } else {
    element.requestFullscreen?.() ||
      element.webkitRequestFullscreen?.() ||
      element.mozRequestFullScreen?.()
    return true
  }
}
