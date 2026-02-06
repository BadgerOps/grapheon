import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'
import { version as frontendVersion } from '../../package.json'

/**
 * Config Page - System settings and maintenance
 *
 * Features:
 * - Software update check
 * - Database statistics
 * - MAC vendor lookup
 * - Database backup/restore
 * - Data cleanup
 */
export default function Config() {
  const [stats, setStats] = useState(null)
  const [backups, setBackups] = useState([])
  const [loading, setLoading] = useState({
    stats: true,
    backups: true,
    vendor: false,
    backup: false,
    restore: false,
    cleanup: false,
    updateCheck: false,
    upload: false,
    seed: false,
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [cleanupDays, setCleanupDays] = useState(90)
  const [cleanupPreview, setCleanupPreview] = useState(null)
  const uploadInputRef = useRef(null)
  const [seedOutput, setSeedOutput] = useState(null)

  // Update check state
  const [updateInfo, setUpdateInfo] = useState(null)
  const [showUpdateModal, setShowUpdateModal] = useState(false)
  const [upgradeStep, setUpgradeStep] = useState(null) // null, 'confirm', 'in_progress', 'completed', 'failed'
  const [upgradeMessage, setUpgradeMessage] = useState('')
  const statusPollRef = useRef(null)
  const reloadTimeoutRef = useRef(null)
  const [backendVersion, setBackendVersion] = useState('...')

  useEffect(() => {
    fetchStats()
    fetchBackups()
    api.getBackendInfo()
      .then(info => setBackendVersion(info.version))
      .catch(() => setBackendVersion('?'))
    return () => {
      if (statusPollRef.current) clearInterval(statusPollRef.current)
      if (reloadTimeoutRef.current) clearTimeout(reloadTimeoutRef.current)
    }
  }, [])

  const handleCheckForUpdates = async () => {
    try {
      setLoading(prev => ({ ...prev, updateCheck: true }))
      setError('')
      const data = await api.checkForUpdates()
      setUpdateInfo(data)
      setShowUpdateModal(true)
      setUpgradeStep(null)
      setUpgradeMessage('')
    } catch (err) {
      setError('Failed to check for updates: ' + err.message)
    } finally {
      setLoading(prev => ({ ...prev, updateCheck: false }))
    }
  }

  const handleStartUpgrade = async () => {
    setUpgradeStep('in_progress')
    setUpgradeMessage('Starting upgrade...')
    try {
      await api.triggerUpgrade()
      let attempt = 0
      const maxAttempts = 120
      statusPollRef.current = setInterval(async () => {
        attempt++
        try {
          const status = await api.getUpgradeStatus()
          if (status.status === 'running') {
            setUpgradeMessage(status.message || 'Upgrading...')
          } else if (status.status === 'completed') {
            clearInterval(statusPollRef.current)
            setUpgradeStep('completed')
            setUpgradeMessage('Upgrade complete! Refreshing in 3 seconds...')
            reloadTimeoutRef.current = setTimeout(() => window.location.reload(), 3000)
          } else if (status.status === 'failed') {
            clearInterval(statusPollRef.current)
            setUpgradeStep('failed')
            setUpgradeMessage(status.message || 'Upgrade failed.')
          }
        } catch {
          if (attempt >= maxAttempts) {
            clearInterval(statusPollRef.current)
            setUpgradeStep('failed')
            setUpgradeMessage('Status check timed out. The upgrade may still be running.')
          }
        }
      }, 5000)
    } catch (err) {
      setUpgradeStep('failed')
      setUpgradeMessage('Failed to start upgrade: ' + err.message)
    }
  }

  const closeUpdateModal = () => {
    if (statusPollRef.current) clearInterval(statusPollRef.current)
    setShowUpdateModal(false)
    setUpgradeStep(null)
    setUpgradeMessage('')
  }

  const fetchStats = async () => {
    try {
      setLoading(prev => ({ ...prev, stats: true }))
      const data = await api.getDatabaseStats()
      setStats(data)
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    } finally {
      setLoading(prev => ({ ...prev, stats: false }))
    }
  }

  const fetchBackups = async () => {
    try {
      setLoading(prev => ({ ...prev, backups: true }))
      const data = await api.listBackups()
      setBackups(data.backups || [])
    } catch (err) {
      console.error('Failed to fetch backups:', err)
    } finally {
      setLoading(prev => ({ ...prev, backups: false }))
    }
  }

  const handleVendorLookup = async () => {
    try {
      setLoading(prev => ({ ...prev, vendor: true }))
      setError('')
      const result = await api.updateVendorInfo()
      const parts = [`${result.vendors_updated} resolved`]
      if (result.vendors_local_admin) parts.push(`${result.vendors_local_admin} locally administered`)
      if (result.vendors_not_found) parts.push(`${result.vendors_not_found} not found`)
      setSuccess(`Vendor lookup complete: ${parts.join(', ')}`)
      setTimeout(() => setSuccess(''), 5000)
      fetchStats()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, vendor: false }))
    }
  }

  const handleCreateBackup = async () => {
    try {
      setLoading(prev => ({ ...prev, backup: true }))
      setError('')
      const result = await api.createBackup()
      setSuccess(`Backup created: ${result.filename}`)
      setTimeout(() => setSuccess(''), 5000)
      fetchBackups()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, backup: false }))
    }
  }

  const handleDownloadBackup = async (filename) => {
    try {
      const response = await api.downloadBackup(filename)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRestoreBackup = async (filename) => {
    if (!window.confirm(`Are you sure you want to restore from ${filename}? This will replace ALL current data.`)) {
      return
    }
    try {
      setLoading(prev => ({ ...prev, restore: true }))
      setError('')
      await api.restoreBackup(filename)
      setSuccess('Database restored successfully. Please refresh the page.')
      setTimeout(() => setSuccess(''), 10000)
      fetchStats()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, restore: false }))
    }
  }

  const handleDeleteBackup = async (filename) => {
    if (!window.confirm(`Are you sure you want to delete backup ${filename}?`)) {
      return
    }
    try {
      await api.deleteBackup(filename)
      setSuccess('Backup deleted')
      setTimeout(() => setSuccess(''), 3000)
      fetchBackups()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleUploadBackup = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.name.endsWith('.db')) {
      setError('Invalid file type. Only .db (SQLite database) files are accepted.')
      return
    }

    try {
      setLoading(prev => ({ ...prev, upload: true }))
      setError('')
      const result = await api.uploadBackup(file)
      setSuccess(`Backup uploaded: ${result.filename} (${formatBytes(result.size_bytes)})`)
      setTimeout(() => setSuccess(''), 5000)
      fetchBackups()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, upload: false }))
      // Reset file input so the same file can be re-selected
      if (uploadInputRef.current) uploadInputRef.current.value = ''
    }
  }

  const handleSeedDemoData = async (append = false) => {
    const action = append
      ? 'add demo data to your existing data'
      : 'replace ALL existing data with demo data'
    if (!window.confirm(`This will ${action}. Continue?`)) {
      return
    }
    try {
      setLoading(prev => ({ ...prev, seed: true }))
      setError('')
      setSeedOutput(null)
      const result = await api.seedDemoData(append)
      setSeedOutput(result.output)
      setSuccess(result.message)
      setTimeout(() => setSuccess(''), 8000)
      fetchStats()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, seed: false }))
    }
  }

  const handlePreviewCleanup = async () => {
    try {
      const data = await api.previewCleanup(cleanupDays)
      setCleanupPreview(data)
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRunCleanup = async () => {
    if (!window.confirm(`This will permanently delete data older than ${cleanupDays} days. Continue?`)) {
      return
    }
    try {
      setLoading(prev => ({ ...prev, cleanup: true }))
      setError('')
      const result = await api.runCleanup(cleanupDays)
      setSuccess(`Cleanup complete: ${result.hosts_deleted} hosts, ${result.ports_deleted} ports, ${result.connections_deleted} connections deleted`)
      setTimeout(() => setSuccess(''), 5000)
      setCleanupPreview(null)
      fetchStats()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(prev => ({ ...prev, cleanup: false }))
    }
  }

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString()
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">System configuration and maintenance</p>
        </div>
        <Link
          to="/"
          className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-100 dark:bg-red-900/30 border border-red-400 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg">
          {error}
        </div>
      )}

      {success && (
        <div className="mb-6 p-4 bg-green-100 dark:bg-green-900/30 border border-green-400 dark:border-green-800 text-green-700 dark:text-green-400 rounded-lg">
          {success}
        </div>
      )}

      <div className="grid gap-6">
        {/* Software Updates */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Software Updates
          </h2>
          <div className="flex flex-wrap items-center gap-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="inline-flex items-center gap-1.5">
                Running:
                <span className="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs font-medium">
                  UI v{frontendVersion}
                </span>
                <span className="px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs font-medium">
                  API v{backendVersion}
                </span>
              </span>
            </div>
            <button
              onClick={handleCheckForUpdates}
              disabled={loading.updateCheck}
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-300 dark:disabled:bg-indigo-800 text-white rounded-md transition-colors flex items-center gap-2"
            >
              {loading.updateCheck ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Checking...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  Check for Updates
                </>
              )}
            </button>
          </div>
        </section>

        {/* Update Modal */}
        {showUpdateModal && updateInfo && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
              {/* Modal header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {upgradeStep === 'in_progress' ? 'Upgrading...' :
                   upgradeStep === 'completed' ? 'Upgrade Complete' :
                   upgradeStep === 'failed' ? 'Upgrade Failed' :
                   updateInfo.update_available ? 'Update Available' : 'Up to Date'}
                </h3>
                {upgradeStep !== 'in_progress' && (
                  <button
                    onClick={closeUpdateModal}
                    className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    <svg className="w-5 h-5 text-gray-500 dark:text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </button>
                )}
              </div>

              {/* Modal body */}
              <div className="px-6 py-4 overflow-y-auto flex-1">
                {/* Upgrade in progress */}
                {upgradeStep === 'in_progress' && (
                  <div className="flex flex-col items-center py-8 gap-4">
                    <svg className="animate-spin w-10 h-10 text-indigo-500" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p className="text-gray-700 dark:text-gray-300 text-center">{upgradeMessage}</p>
                  </div>
                )}

                {/* Upgrade completed */}
                {upgradeStep === 'completed' && (
                  <div className="flex flex-col items-center py-8 gap-4">
                    <svg className="w-12 h-12 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <p className="text-gray-700 dark:text-gray-300 text-center">{upgradeMessage}</p>
                  </div>
                )}

                {/* Upgrade failed */}
                {upgradeStep === 'failed' && (
                  <div className="flex flex-col items-center py-8 gap-4">
                    <svg className="w-12 h-12 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <p className="text-red-600 dark:text-red-400 text-center">{upgradeMessage}</p>
                  </div>
                )}

                {/* Normal state: show version info + release notes */}
                {upgradeStep === null && (
                  <>
                    {updateInfo.update_available ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
                            v{updateInfo.latest_version}
                          </span>
                          {updateInfo.published_at && (
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              Released {new Date(updateInfo.published_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>

                        <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                          <p>Current backend: <span className="font-mono">{updateInfo.current_backend_version}</span></p>
                          <p>Latest backend: <span className="font-mono">{updateInfo.latest_backend_version}</span></p>
                          {updateInfo.latest_frontend_version && (
                            <p>Latest frontend: <span className="font-mono">{updateInfo.latest_frontend_version}</span></p>
                          )}
                        </div>

                        {updateInfo.release_notes && (
                          <div className="mt-4">
                            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Release Notes</h4>
                            <pre className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-sans leading-relaxed">
                              {updateInfo.release_notes}
                            </pre>
                          </div>
                        )}

                        {updateInfo.release_url && (
                          <a
                            href={updateInfo.release_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
                          >
                            View on GitHub
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        )}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center py-6 gap-3">
                        <svg className="w-12 h-12 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <p className="text-gray-700 dark:text-gray-300 font-medium">You're running the latest version.</p>
                        {updateInfo.error && (
                          <p className="text-sm text-amber-600 dark:text-amber-400">{updateInfo.error}</p>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Modal footer */}
              <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                {upgradeStep === null && updateInfo.update_available && (
                  <>
                    <button
                      onClick={closeUpdateModal}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                    >
                      Later
                    </button>
                    <button
                      onClick={handleStartUpgrade}
                      className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
                    >
                      Upgrade now
                    </button>
                  </>
                )}
                {upgradeStep === null && !updateInfo.update_available && (
                  <button
                    onClick={closeUpdateModal}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                  >
                    Close
                  </button>
                )}
                {upgradeStep === 'failed' && (
                  <>
                    <button
                      onClick={closeUpdateModal}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                    >
                      Dismiss
                    </button>
                    <button
                      onClick={handleStartUpgrade}
                      className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
                    >
                      Try again
                    </button>
                  </>
                )}
                {upgradeStep === 'completed' && (
                  <button
                    onClick={() => window.location.reload()}
                    className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
                  >
                    Refresh now
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Database Statistics */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            Database Statistics
          </h2>
          {loading.stats ? (
            <p className="text-gray-500 dark:text-gray-400">Loading statistics...</p>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-sm text-gray-500 dark:text-gray-400">Hosts</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.hosts || 0}</p>
              </div>
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-sm text-gray-500 dark:text-gray-400">Ports</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.ports || 0}</p>
              </div>
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-sm text-gray-500 dark:text-gray-400">Connections</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.connections || 0}</p>
              </div>
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-sm text-gray-500 dark:text-gray-400">Database Size</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{formatBytes(stats.database_size || 0)}</p>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">Failed to load statistics</p>
          )}
        </section>

        {/* MAC Vendor Lookup */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            MAC Vendor Lookup
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Update vendor information for all hosts based on their MAC addresses using the OUI database.
          </p>
          <button
            onClick={handleVendorLookup}
            disabled={loading.vendor}
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 dark:disabled:bg-blue-800 text-white rounded-md transition-colors flex items-center gap-2"
          >
            {loading.vendor ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Updating...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Update All Vendors
              </>
            )}
          </button>
        </section>

        {/* Database Backup */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
            Database Backup & Restore
          </h2>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-4">
              <button
                onClick={handleCreateBackup}
                disabled={loading.backup}
                className="px-4 py-2 bg-green-500 hover:bg-green-600 disabled:bg-green-300 dark:disabled:bg-green-800 text-white rounded-md transition-colors flex items-center gap-2"
              >
                {loading.backup ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Creating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Create Backup
                  </>
                )}
              </button>

              <input
                type="file"
                ref={uploadInputRef}
                accept=".db"
                onChange={handleUploadBackup}
                className="hidden"
              />
              <button
                onClick={() => uploadInputRef.current?.click()}
                disabled={loading.upload}
                className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 dark:disabled:bg-blue-800 text-white rounded-md transition-colors flex items-center gap-2"
              >
                {loading.upload ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Uploading...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    Import Backup
                  </>
                )}
              </button>
            </div>

            {/* Backup list */}
            <div className="mt-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">Available Backups</h3>
              {loading.backups ? (
                <p className="text-gray-500 dark:text-gray-400">Loading backups...</p>
              ) : backups.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400">No backups available</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="bg-gray-100 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600">
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">Filename</th>
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">Size</th>
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">Created</th>
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backups.map((backup) => (
                        <tr key={backup.filename} className="border-b border-gray-200 dark:border-gray-700">
                          <td className="px-4 py-2 text-gray-900 dark:text-gray-100 font-mono text-sm">{backup.filename}</td>
                          <td className="px-4 py-2 text-gray-600 dark:text-gray-400 text-sm">{formatBytes(backup.size_bytes)}</td>
                          <td className="px-4 py-2 text-gray-600 dark:text-gray-400 text-sm">{formatDate(backup.created_at)}</td>
                          <td className="px-4 py-2">
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleDownloadBackup(backup.filename)}
                                className="px-2 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded text-xs transition-colors"
                                title="Download"
                              >
                                Download
                              </button>
                              <button
                                onClick={() => handleRestoreBackup(backup.filename)}
                                disabled={loading.restore}
                                className="px-2 py-1 bg-yellow-500 hover:bg-yellow-600 disabled:bg-yellow-300 text-white rounded text-xs transition-colors"
                                title="Restore"
                              >
                                Restore
                              </button>
                              <button
                                onClick={() => handleDeleteBackup(backup.filename)}
                                className="px-2 py-1 bg-red-500 hover:bg-red-600 text-white rounded text-xs transition-colors"
                                title="Delete"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Demo Data Generation */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
            Test Data Generation
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Generate a realistic demo network with 6 VLANs, ~48 hosts, ports, connections, ARP entries, and traceroute data for testing and demonstration purposes.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={() => handleSeedDemoData(false)}
              disabled={loading.seed}
              className="px-4 py-2 bg-purple-500 hover:bg-purple-600 disabled:bg-purple-300 dark:disabled:bg-purple-800 text-white rounded-md transition-colors flex items-center gap-2"
            >
              {loading.seed ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                  </svg>
                  Generate Fresh Data
                </>
              )}
            </button>
            <button
              onClick={() => handleSeedDemoData(true)}
              disabled={loading.seed}
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-300 dark:disabled:bg-indigo-800 text-white rounded-md transition-colors flex items-center gap-2"
            >
              {loading.seed ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  Append to Existing
                </>
              )}
            </button>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
            <strong>Generate Fresh</strong> clears all data first. <strong>Append</strong> adds demo data alongside your existing records.
          </p>

          {seedOutput && (
            <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg">
              <h4 className="font-medium text-gray-700 dark:text-gray-300 mb-2 text-sm">Script Output</h4>
              <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono leading-relaxed max-h-48 overflow-y-auto">
                {seedOutput}
              </pre>
            </div>
          )}
        </section>

        {/* Data Cleanup */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Data Cleanup
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Remove old data from the database. This will delete hosts, ports, and connections not seen in the specified number of days.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <label htmlFor="cleanupDays" className="text-gray-700 dark:text-gray-300">Days to keep:</label>
              <input
                type="number"
                id="cleanupDays"
                value={cleanupDays}
                onChange={(e) => setCleanupDays(parseInt(e.target.value) || 90)}
                min="1"
                max="365"
                className="w-20 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <button
              onClick={handlePreviewCleanup}
              className="px-4 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-md transition-colors"
            >
              Preview
            </button>
            <button
              onClick={handleRunCleanup}
              disabled={loading.cleanup}
              className="px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-red-300 dark:disabled:bg-red-800 text-white rounded-md transition-colors flex items-center gap-2"
            >
              {loading.cleanup ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Running...
                </>
              ) : (
                'Run Cleanup'
              )}
            </button>
          </div>

          {cleanupPreview && (
            <div className="mt-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <h4 className="font-medium text-yellow-800 dark:text-yellow-200 mb-2">Cleanup Preview</h4>
              <p className="text-yellow-700 dark:text-yellow-300 text-sm">
                This will delete: {cleanupPreview.hosts_to_delete || 0} hosts, {cleanupPreview.ports_to_delete || 0} ports, {cleanupPreview.connections_to_delete || 0} connections
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
