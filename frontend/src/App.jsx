import { useState, useEffect } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Hosts from './pages/Hosts'
import HostDetail from './pages/HostDetail'
import Import from './pages/Import'
import Map from './pages/Map'
import MapFullscreen from './pages/MapFullscreen'
import Search from './pages/Search'
import Connections from './pages/Connections'
import Arp from './pages/Arp'
import Changelog from './pages/Changelog'
import Config from './pages/Config'
import AuthAdmin from './pages/AuthAdmin'
import Login from './pages/Login'
import ProtectedRoute from './components/ProtectedRoute'
import UserMenu from './components/UserMenu'
import UpdateBanner from './components/UpdateBanner'
import { useAuth } from './context/AuthContext'
import { useHealthStatus } from './hooks/useHealthStatus'
import { version as frontendVersion } from '../package.json'
import * as api from './api/client'

// Theme detection and management with localStorage persistence
function useTheme() {
  const [themePreference, setThemePreference] = useState(() => {
    const stored = window.localStorage.getItem('theme')
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored
    }
    return 'system'
  })
  const [systemTheme, setSystemTheme] = useState(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  const theme = themePreference === 'system' ? systemTheme : themePreference

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  useEffect(() => {
    window.localStorage.setItem('theme', themePreference)
  }, [themePreference])

  const toggleTheme = () => {
    setThemePreference(theme === 'dark' ? 'light' : 'dark')
  }

  return { theme, toggleTheme }
}

// Navigation link component with light/dark mode support
function NavLink({ to, children, icon }) {
  const location = useLocation()
  const isActive = location.pathname === to || (to !== '/' && location.pathname.startsWith(to))

  return (
    <Link
      to={to}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-200 ${
        isActive
          ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25'
          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
      }`}
    >
      {icon}
      <span className="font-medium">{children}</span>
    </Link>
  )
}

export default function App() {
  const { theme, toggleTheme } = useTheme()
  const { isAuthenticated, hasRole, loading: authLoading, demoMode } = useAuth()
  const [backendVersion, setBackendVersion] = useState('...')
  const location = useLocation()
  const { status: healthStatus } = useHealthStatus()

  useEffect(() => {
    api.getBackendInfo()
      .then(info => setBackendVersion(info.version))
      .catch(() => setBackendVersion('?'))
  }, [])

  // Hide nav/footer on fullscreen map route
  const isMapFullscreen = location.pathname.startsWith('/map/fullscreen')

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors duration-200">
      {/* Navigation */}
      {!isMapFullscreen && isAuthenticated && (<nav className="bg-white dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800 sticky top-0 z-50">
        <div className="max-w-full mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link
              to="/"
              className="flex items-center gap-3 text-gray-900 dark:text-white hover:opacity-90 transition-opacity"
            >
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight">Graphēon</h1>
                <p className="text-xs text-gray-500 dark:text-gray-400 -mt-0.5">Data Analysis Platform</p>
              </div>
            </Link>

            {/* Navigation Links */}
            <div className="flex items-center gap-2">
              <NavLink
                to="/"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                }
              >
                Dashboard
              </NavLink>

              <NavLink
                to="/hosts"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                }
              >
                Hosts
              </NavLink>

              <NavLink
                to="/map"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                  </svg>
                }
              >
                Map
              </NavLink>

              <NavLink
                to="/connections"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h10M7 16h10M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z" />
                  </svg>
                }
              >
                Connections
              </NavLink>

              <NavLink
                to="/arp"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7h16M4 12h16M4 17h10" />
                  </svg>
                }
              >
                ARP
              </NavLink>

              <NavLink
                to="/search"
                icon={
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                }
              >
                Search
              </NavLink>

              {hasRole('editor') && (
                <NavLink
                  to="/import"
                  icon={
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                  }
                >
                  Import
                </NavLink>
              )}

              {hasRole('admin') && (
                <NavLink
                  to="/auth-admin"
                  icon={
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                  }
                >
                  Identity
                </NavLink>
              )}

              {hasRole('admin') && (
                <NavLink
                  to="/config"
                  icon={
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  }
                >
                  Settings
                </NavLink>
              )}
            </div>

            {/* Theme toggle */}
            <div className="flex items-center gap-3">
              <UserMenu />
              <button
                type="button"
                onClick={toggleTheme}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800/80 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                aria-pressed={theme === 'dark'}
              >
                {theme === 'dark' ? (
                  <>
                    <svg className="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                    </svg>
                    <span>Light mode</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
                    </svg>
                    <span>Dark mode</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </nav>
      )}

      {/* Update notification banner */}
      {!isMapFullscreen && isAuthenticated && <UpdateBanner />}

      {/* Demo mode banner */}
      {!isMapFullscreen && demoMode && (
        <div className="bg-amber-500 text-white text-center py-1.5 px-4 text-sm font-medium">
          Demo Mode — Browse with read-only access. Data resets periodically.
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/map/fullscreen" element={<ProtectedRoute><MapFullscreen /></ProtectedRoute>} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/hosts" element={<ProtectedRoute><Hosts /></ProtectedRoute>} />
          <Route path="/hosts/:id" element={<ProtectedRoute><HostDetail /></ProtectedRoute>} />
          <Route path="/map" element={<ProtectedRoute><Map /></ProtectedRoute>} />
          <Route path="/connections" element={<ProtectedRoute><Connections /></ProtectedRoute>} />
          <Route path="/arp" element={<ProtectedRoute><Arp /></ProtectedRoute>} />
          <Route path="/search" element={<ProtectedRoute><Search /></ProtectedRoute>} />
          <Route path="/import" element={<ProtectedRoute requiredRole="editor"><Import /></ProtectedRoute>} />
          <Route path="/changelog" element={<ProtectedRoute><Changelog /></ProtectedRoute>} />
          <Route path="/config" element={<ProtectedRoute requiredRole="admin"><Config /></ProtectedRoute>} />
          <Route path="/auth-admin" element={<ProtectedRoute requiredRole="admin"><AuthAdmin /></ProtectedRoute>} />
        </Routes>
      </main>

      {/* Footer */}
      {!isMapFullscreen && isAuthenticated && (<footer className="bg-white dark:bg-gray-950 border-t border-gray-200 dark:border-gray-800 py-6">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Graphēon - Built with React, FastAPI & SQLite
            </p>
            <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <Link
                to="/changelog"
                className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                <span className="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs">
                  UI v{frontendVersion}
                </span>
                <span className="px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs">
                  API v{backendVersion}
                </span>
              </Link>
              <span className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${
                  healthStatus === 'healthy' ? 'bg-green-500 animate-pulse' :
                  healthStatus === 'degraded' ? 'bg-amber-500 animate-pulse' :
                  'bg-red-500'
                }`}></span>
                {healthStatus === 'healthy' ? 'System Online' :
                 healthStatus === 'degraded' ? 'System Degraded' :
                 healthStatus === 'unreachable' ? 'API Unreachable' :
                 'System Unhealthy'}
              </span>
            </div>
          </div>
        </div>
      </footer>
      )}
    </div>
  )
}
