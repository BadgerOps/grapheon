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
