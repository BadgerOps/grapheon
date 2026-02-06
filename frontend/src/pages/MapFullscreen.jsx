import Map from './Map'

/**
 * MapFullscreen — Dedicated fullscreen map view.
 * Opens in a new window via the "Pop Out" button.
 * Renders the Map page without the main app navigation chrome.
 */
export default function MapFullscreen() {
  return (
    <div className="w-screen h-screen overflow-hidden bg-white dark:bg-gray-900">
      <Map />
    </div>
  )
}
