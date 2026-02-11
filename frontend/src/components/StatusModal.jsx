import { useEffect } from 'react'
import { useHealthStatus } from '../hooks/useHealthStatus'
import { version as frontendVersion } from '../../package.json'

const STATUS_CONFIG = {
  healthy:     { label: 'Operational',  dotClass: 'status-online',  textClass: 'text-green-600 dark:text-green-400' },
  degraded:    { label: 'Degraded',     dotClass: 'status-warning', textClass: 'text-amber-600 dark:text-amber-400' },
  unhealthy:   { label: 'Unhealthy',    dotClass: 'status-offline', textClass: 'text-red-600 dark:text-red-400' },
  unreachable: { label: 'Unreachable',  dotClass: 'status-offline', textClass: 'text-red-600 dark:text-red-400' },
}

const CHECK_STATUS = {
  ok:       { dotClass: 'bg-green-500' },
  degraded: { dotClass: 'bg-amber-500' },
  error:    { dotClass: 'bg-red-500' },
}

export default function StatusModal({ open, onClose }) {
  const { status: healthStatus, health, lastChecked } = useHealthStatus()

  useEffect(() => {
    if (!open) return
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  const statusCfg = STATUS_CONFIG[healthStatus] || STATUS_CONFIG.unreachable

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            System Status
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4">
          {/* Overall Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Overall Status</span>
            <div className="flex items-center gap-2">
              <span className={`status-dot ${statusCfg.dotClass}`} />
              <span className={`text-sm font-semibold ${statusCfg.textClass}`}>
                {statusCfg.label}
              </span>
            </div>
          </div>

          {/* Per-component checks */}
          {health?.checks && (
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">
                Component Checks
              </p>
              <div className="space-y-2">
                {health.checks.map((check) => {
                  const checkCfg = CHECK_STATUS[check.status] || CHECK_STATUS.error
                  return (
                    <div key={check.name} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full ${checkCfg.dotClass}`}></span>
                        <span className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                          {check.name.replace(/_/g, ' ')}
                        </span>
                      </div>
                      {check.response_time_ms != null && (
                        <span className="text-xs font-mono text-gray-400 dark:text-gray-500">
                          {check.response_time_ms.toFixed(0)}ms
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Versions */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">
              Versions
            </p>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Backend</span>
              <span className="text-sm font-mono text-gray-900 dark:text-gray-100">
                {health?.version ? `v${health.version}` : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Frontend</span>
              <span className="text-sm font-mono text-gray-900 dark:text-gray-100">
                v{frontendVersion}
              </span>
            </div>
          </div>

          {/* Uptime */}
          {health?.uptime_seconds != null && (
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Uptime</span>
              <span className="text-sm font-mono text-gray-900 dark:text-gray-100">
                {formatUptime(health.uptime_seconds)}
              </span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {lastChecked
              ? `Last checked: ${lastChecked.toLocaleTimeString()}`
              : 'Not yet checked'}
          </p>
        </div>
      </div>
    </div>
  )
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h ${mins}m`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}
