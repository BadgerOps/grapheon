import { useMemo, useState } from 'react'
import { transformToIsoflow } from '../services/isoflowTransformer'

/**
 * IsoflowNetworkMap — Isometric network topology visualization
 *
 * TESTING: This component is experimental. We're evaluating whether
 * isometric diagrams provide value alongside the existing Cytoscape.js
 * graph view. This may be removed in a future release if it doesn't
 * prove useful.
 *
 * Renders network topology data as an isometric diagram using the
 * isoflow library. Takes the same Cytoscape elements format as input
 * and transforms it into isoflow's initialData format.
 */
export default function IsoflowNetworkMap({
  elements = { nodes: [], edges: [] },
  loading = false,
}) {
  const [isoflowError, setIsoflowError] = useState(null)
  const [IsoflowComponent, setIsoflowComponent] = useState(null)
  const [icons, setIcons] = useState(null)
  const [loadingLib, setLoadingLib] = useState(false)

  // Lazy-load isoflow and isopacks on first render with data
  const hasElements = (elements.nodes || []).length > 0

  useMemo(() => {
    if (!hasElements || IsoflowComponent || loadingLib) return

    setLoadingLib(true)
    Promise.all([
      import('isoflow'),
      import('@isoflow/isopacks/dist/isoflow'),
    ])
      .then(([isoflowMod, isopackMod]) => {
        const Isoflow = isoflowMod.default || isoflowMod
        const isopack = isopackMod.default || isopackMod
        setIsoflowComponent(() => Isoflow)
        setIcons(isopack.icons || [])
        setLoadingLib(false)
      })
      .catch((err) => {
        console.error('Failed to load isoflow:', err)
        setIsoflowError(`Failed to load isometric view library: ${err.message}`)
        setLoadingLib(false)
      })
  }, [hasElements, IsoflowComponent, loadingLib])

  // Transform Cytoscape elements → isoflow format
  const isoflowData = useMemo(() => {
    if (!hasElements) return null

    try {
      const data = transformToIsoflow(elements)
      // Inject icons from isopacks
      if (icons) {
        data.icons = icons
      }
      return data
    } catch (err) {
      console.error('Failed to transform data for isoflow:', err)
      setIsoflowError(`Data transformation failed: ${err.message}`)
      return null
    }
  }, [elements, icons, hasElements])

  // Loading state
  if (loading || loadingLib) {
    return (
      <div
        className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"
        style={{ height: '100%', minHeight: '500px' }}
      >
        <div className="text-center">
          <div className="spinner mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">
            {loadingLib ? 'Loading isometric view...' : 'Computing network topology...'}
          </p>
        </div>
      </div>
    )
  }

  // Empty state
  if (!hasElements) {
    return (
      <div
        className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"
        style={{ height: '100%', minHeight: '500px' }}
      >
        <div className="text-center">
          <svg className="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
          <p className="text-gray-600 dark:text-gray-400">No hosts to display</p>
          <p className="text-sm text-gray-500 mt-2">Import network data to see the topology</p>
        </div>
      </div>
    )
  }

  // Error state
  if (isoflowError) {
    return (
      <div
        className="flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"
        style={{ height: '100%', minHeight: '500px' }}
      >
        <div className="text-center max-w-md">
          <svg className="w-12 h-12 mx-auto mb-3 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-red-600 dark:text-red-400 font-medium mb-1">Isometric View Error</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">{isoflowError}</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
            Try switching back to Graph View
          </p>
        </div>
      </div>
    )
  }

  // Render isoflow
  if (!IsoflowComponent || !isoflowData) {
    return null
  }

  return (
    <div className="relative h-full">
      <div
        className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
        style={{ height: '100%', minHeight: '500px' }}
      >
        <IsoflowComponent initialData={isoflowData} />
      </div>

      {/* Experimental badge */}
      <div className="absolute top-4 left-4 px-3 py-1.5 bg-amber-100 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-700 rounded-lg shadow-sm">
        <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
          EXPERIMENTAL — Isometric View
        </span>
      </div>
    </div>
  )
}
