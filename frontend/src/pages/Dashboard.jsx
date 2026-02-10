import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client'
import { useHealthStatus } from '../hooks/useHealthStatus'

export default function Dashboard() {
  const [stats, setStats] = useState({
    hostsCount: 0,
    portsCount: 0,
    conflictsCount: 0,
    connectionsCount: 0,
    arpCount: 0,
  })
  const [recentImports, setRecentImports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const [hostsRes, importsRes, connectionsRes, arpRes] = await Promise.all([
          api.getHosts(),
          api.getImports(),
          api.getConnections(),
          api.getArpEntries(),
        ])

        // API returns {total, items, skip, limit}
        setStats({
          hostsCount: hostsRes.total || 0,
          portsCount: hostsRes.items?.reduce((acc, h) => acc + (h.ports_count || 0), 0) || 0,
          conflictsCount: 0,
          connectionsCount: connectionsRes.total || 0,
          arpCount: arpRes.total || 0,
        })
        setRecentImports((importsRes.items || []).slice(0, 5))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const { status: healthStatus, health } = useHealthStatus()

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Dashboard</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Overview of your network data
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3">
          <svg className="w-5 h-5 text-red-500 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <h4 className="font-medium text-red-800 dark:text-red-200">Error loading data</h4>
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-6 mb-8">
        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Total Hosts
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {loading ? (
                  <span className="inline-block w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                ) : (
                  stats.hostsCount
                )}
              </p>
            </div>
            <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
              </svg>
            </div>
          </div>
          <Link
            to="/hosts"
            className="mt-4 inline-flex items-center text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
          >
            View all hosts
            <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Open Ports
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {loading ? (
                  <span className="inline-block w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                ) : (
                  stats.portsCount
                )}
              </p>
            </div>
            <div className="w-12 h-12 bg-indigo-100 dark:bg-indigo-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-indigo-600 dark:text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6l4 2" />
              </svg>
            </div>
          </div>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Recent Imports
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {loading ? (
                  <span className="inline-block w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                ) : (
                  recentImports.length
                )}
              </p>
            </div>
            <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
          </div>
          <Link
            to="/import"
            className="mt-4 inline-flex items-center text-sm font-medium text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300"
          >
            Import data
            <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Connections
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {loading ? (
                  <span className="inline-block w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                ) : (
                  stats.connectionsCount
                )}
              </p>
            </div>
            <div className="w-12 h-12 bg-slate-100 dark:bg-slate-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-slate-600 dark:text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h10M7 16h10" />
              </svg>
            </div>
          </div>
          <Link
            to="/connections"
            className="mt-4 inline-flex items-center text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-slate-700 dark:hover:text-slate-200"
          >
            View connections
            <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                ARP Entries
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {loading ? (
                  <span className="inline-block w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"></span>
                ) : (
                  stats.arpCount
                )}
              </p>
            </div>
            <div className="w-12 h-12 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7h16M4 12h16M4 17h10" />
              </svg>
            </div>
          </div>
          <Link
            to="/arp"
            className="mt-4 inline-flex items-center text-sm font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
          >
            View ARP entries
            <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Network Map
              </p>
              <p className="text-xl font-semibold text-gray-900 dark:text-gray-100 mt-2">
                Visualization
              </p>
            </div>
            <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900/30 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
            </div>
          </div>
          <Link
            to="/map"
            className="mt-4 inline-flex items-center text-sm font-medium text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300"
          >
            View topology
            <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                System Status
              </p>
              <p className={`text-xl font-semibold mt-2 ${
                healthStatus === 'healthy' ? 'text-green-600 dark:text-green-400' :
                healthStatus === 'degraded' ? 'text-amber-600 dark:text-amber-400' :
                'text-red-600 dark:text-red-400'
              }`}>
                {healthStatus === 'healthy' ? 'Operational' :
                 healthStatus === 'degraded' ? 'Degraded' :
                 healthStatus === 'unreachable' ? 'Unreachable' :
                 'Unhealthy'}
              </p>
            </div>
            <div className="w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-xl flex items-center justify-center">
              <span className="relative flex h-3 w-3">
                {healthStatus === 'healthy' && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-3 w-3 ${
                  healthStatus === 'healthy' ? 'bg-green-500' :
                  healthStatus === 'degraded' ? 'bg-amber-500' :
                  'bg-red-500'
                }`}></span>
              </span>
            </div>
          </div>
          {health?.checks ? (
            <div className="mt-3 space-y-1">
              {health.checks.map((check) => (
                <div key={check.name} className="flex items-center gap-2 text-sm">
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    check.status === 'ok' ? 'bg-green-500' :
                    check.status === 'degraded' ? 'bg-amber-500' :
                    'bg-red-500'
                  }`}></span>
                  <span className="text-gray-600 dark:text-gray-400 capitalize">
                    {check.name.replace(/_/g, ' ')}
                  </span>
                  {check.response_time_ms != null && (
                    <span className="text-gray-400 dark:text-gray-500 text-xs">
                      {check.response_time_ms.toFixed(0)}ms
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
              {healthStatus === 'unreachable' ? 'Cannot reach API' : 'Checking...'}
            </p>
          )}
        </div>
      </div>

      {/* Recent Imports Section */}
      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Recent Imports
          </h2>
          <Link
            to="/import"
            className="btn btn-primary text-sm"
          >
            New Import
          </Link>
        </div>
        <div className="card-body">
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg animate-pulse">
                  <div className="w-10 h-10 bg-gray-200 dark:bg-gray-600 rounded-lg"></div>
                  <div className="flex-1">
                    <div className="h-4 w-24 bg-gray-200 dark:bg-gray-600 rounded"></div>
                    <div className="h-3 w-32 bg-gray-200 dark:bg-gray-600 rounded mt-2"></div>
                  </div>
                </div>
              ))}
            </div>
          ) : recentImports.length === 0 ? (
            <div className="empty-state">
              <svg className="empty-state-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-lg font-medium">No imports yet</p>
              <p className="text-sm mt-1">Get started by importing network data</p>
              <Link to="/import" className="btn btn-primary mt-4">
                Import Data
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {recentImports.map((imp) => (
                <div
                  key={imp.id}
                  className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                      <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-gray-100">
                        {imp.source_type}
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {imp.filename || 'Pasted data'}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`badge ${
                      imp.parse_status === 'success' ? 'badge-success' :
                      imp.parse_status === 'failed' ? 'badge-error' :
                      'badge-warning'
                    }`}>
                      {imp.parse_status}
                    </span>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {new Date(imp.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
