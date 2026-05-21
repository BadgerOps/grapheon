import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

const AuthContext = createContext(null)

function readStoredToken() {
  try {
    return localStorage.getItem('auth_token')
  } catch {
    return null
  }
}

function storeToken(nextToken) {
  try {
    if (nextToken) {
      localStorage.setItem('auth_token', nextToken)
    } else {
      localStorage.removeItem('auth_token')
    }
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(readStoredToken)
  const [loading, setLoading] = useState(true)
  const [demoMode, setDemoMode] = useState(false)
  const navigate = useNavigate()

  // Validate existing token on mount, with demo mode support
  useEffect(() => {
    let active = true
    const validatedToken = token

    const init = async () => {
      try {
        // Check if demo mode is enabled
        const demoRes = await fetch('/api/demo-info')
        if (demoRes.ok) {
          const demoData = await demoRes.json()
          if (!active) return
          if (demoData.demo_mode) {
            setDemoMode(true)
            // In demo mode, /api/auth/me works without a token
            if (!validatedToken) {
              const meRes = await fetch('/api/auth/me')
              if (!active) return
              if (meRes.ok) {
                const userData = await meRes.json()
                if (!active) return
                setUser(userData)
                setLoading(false)
                return
              }
            }
          }
        }
      } catch {
        // Demo info endpoint not available, continue normally
      }

      // Normal token validation
      if (validatedToken) {
        try {
          const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${validatedToken}` },
          })
          if (!res.ok) throw new Error('Invalid token')
          const userData = await res.json()
          if (!active || readStoredToken() !== validatedToken) return
          setUser(userData)
        } catch {
          if (!active) return
          if (readStoredToken() === validatedToken) {
            storeToken(null)
          }
          setToken(null)
          setUser(null)
        }
      }
      if (active) setLoading(false)
    }

    init()

    return () => {
      active = false
    }
  }, [token])

  const login = useCallback((tokenResponse) => {
    const { access_token, ...userData } = tokenResponse
    storeToken(access_token)
    setToken(access_token)
    setUser({
      id: userData.user_id,
      username: userData.username,
      email: userData.email,
      role: userData.role,
    })
  }, [])

  const logout = useCallback(() => {
    // Fire-and-forget audit log
    if (token) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {})
    }
    storeToken(null)
    setToken(null)
    setUser(null)
    navigate('/login')
  }, [token, navigate])

  const hasRole = useCallback((requiredRole) => {
    if (!user) return false
    const rolePriority = { viewer: 1, editor: 2, admin: 3 }
    if (!Object.prototype.hasOwnProperty.call(rolePriority, user.role)) return false
    if (!Object.prototype.hasOwnProperty.call(rolePriority, requiredRole)) return false
    return rolePriority[user.role] >= rolePriority[requiredRole]
  }, [user])

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    hasRole,
    demoMode,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
