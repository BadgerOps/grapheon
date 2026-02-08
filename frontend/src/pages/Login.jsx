import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Generate PKCE code verifier and challenge
async function generatePKCE() {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  const verifier = btoa(String.fromCharCode(...array))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const encoder = new TextEncoder()
  const data = encoder.encode(verifier)
  const digest = await crypto.subtle.digest('SHA-256', data)
  const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return { verifier, challenge }
}

export default function Login() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [providers, setProviders] = useState([])
  const [localAuthEnabled, setLocalAuthEnabled] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [callbackLoading, setCallbackLoading] = useState(false)

  // Fetch available providers
  useEffect(() => {
    fetch('/api/auth/providers')
      .then(res => res.json())
      .then(data => {
        setProviders(data.providers || [])
        setLocalAuthEnabled(data.local_auth_enabled || false)
      })
      .catch(() => setError('Failed to load authentication providers'))
  }, [])

  // Handle OIDC callback (code in URL)
  const handleCallback = useCallback(async () => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    if (!code) return

    setCallbackLoading(true)
    setError('')

    try {
      // Recover provider and PKCE verifier from sessionStorage
      const providerName = sessionStorage.getItem('oidc_provider')
      const codeVerifier = sessionStorage.getItem('oidc_code_verifier')
      const redirectUri = `${window.location.origin}/login`

      if (!providerName) {
        throw new Error('Missing OIDC state. Please try logging in again.')
      }

      const res = await fetch('/api/auth/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          provider: providerName,
          redirect_uri: redirectUri,
          code_verifier: codeVerifier || undefined,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Authentication failed')
      }

      const tokenResponse = await res.json()
      sessionStorage.removeItem('oidc_provider')
      sessionStorage.removeItem('oidc_code_verifier')
      login(tokenResponse)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setCallbackLoading(false)
    }
  }, [searchParams, login, navigate])

  useEffect(() => {
    handleCallback()
  }, [handleCallback])

  // Handle OIDC/OAuth2 provider login redirect
  const handleOIDCLogin = async (provider) => {
    try {
      const redirectUri = `${window.location.origin}/login`
      const isOIDC = provider.provider_type === 'oidc'

      sessionStorage.setItem('oidc_provider', provider.name)

      const params = new URLSearchParams({
        client_id: provider.client_id,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: provider.scope || (isOIDC ? 'openid profile email' : 'read:user user:email'),
        state: crypto.randomUUID(),
      })

      // PKCE is only supported by OIDC providers (and GitHub Apps).
      // Plain OAuth2 apps (e.g. GitHub OAuth Apps) don't support it.
      if (isOIDC) {
        const { verifier, challenge } = await generatePKCE()
        sessionStorage.setItem('oidc_code_verifier', verifier)
        params.set('code_challenge', challenge)
        params.set('code_challenge_method', 'S256')
      } else {
        sessionStorage.removeItem('oidc_code_verifier')
      }

      window.location.href = `${provider.authorization_endpoint}?${params}`
    } catch (err) {
      setError('Failed to initiate login')
    }
  }

  // Handle local admin login
  const handleLocalLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/auth/login/local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Login failed')
      }

      const tokenResponse = await res.json()
      login(tokenResponse)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Provider icon mapping
  const getProviderIcon = (name) => {
    const lower = name.toLowerCase()
    if (lower.includes('github')) return '🔗'
    if (lower.includes('google')) return '🔍'
    if (lower.includes('okta')) return '🔐'
    if (lower.includes('gitlab')) return '🦊'
    if (lower.includes('authentik')) return '🛡️'
    return '🔑'
  }

  if (callbackLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Completing sign-in...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Graphēon</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Sign in to continue</p>
        </div>

        {/* Card */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
          {/* Error */}
          {error && (
            <div className="mb-6 p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* OIDC Providers */}
          {providers.length > 0 && (
            <div className="space-y-3 mb-6">
              {providers.map(provider => (
                <button
                  key={provider.name}
                  onClick={() => handleOIDCLogin(provider)}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors font-medium"
                >
                  <span className="text-lg">{getProviderIcon(provider.name)}</span>
                  Continue with {provider.display_name}
                </button>
              ))}
            </div>
          )}

          {/* Divider */}
          {providers.length > 0 && localAuthEnabled && (
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                  or sign in with credentials
                </span>
              </div>
            </div>
          )}

          {/* Local Login Form */}
          {localAuthEnabled && (
            <form onSubmit={handleLocalLogin} className="space-y-4">
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  placeholder="admin"
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  placeholder="••••••••"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl bg-blue-600 text-white font-medium hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          )}

          {/* No auth available */}
          {providers.length === 0 && !localAuthEnabled && !error && (
            <p className="text-center text-gray-500 dark:text-gray-400 text-sm">
              No authentication providers configured. Contact your administrator.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
