import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'

/**
 * Config Page - System settings and maintenance
 *
 * Features:
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
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [cleanupDays, setCleanupDays] = useState(90)
  const [cleanupPreview, setCleanupPreview] = useState(null)

  useEffect(() => {
    fetchStats()
    fetchBackups()
  }, [])

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
      setSuccess(`Vendor lookup complete: ${result.updated} hosts updated, ${result.not_found} not found`)
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
            <div className="flex gap-4">
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
