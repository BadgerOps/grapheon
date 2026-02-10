import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)
  const [demoMode, setDemoMode] = useState(false)
  const navigate = useNavigate()

  // Validate existing token on mount, with demo mode support
  useEffect(() => {
    const init = async () => {
      try {
        // Check if demo mode is enabled
        const demoRes = await fetch('/api/demo-info')
        if (demoRes.ok) {
          const demoData = await demoRes.json()
          if (demoData.demo_mode) {
            setDemoMode(true)
            // In demo mode, /api/auth/me works without a token
            if (!token) {
              const meRes = await fetch('/api/auth/me')
              if (meRes.ok) {
                const userData = await meRes.json()
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
      if (token) {
        try {
          const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (!res.ok) throw new Error('Invalid token')
          const userData = await res.json()
          setUser(userData)
        } catch {
          localStorage.removeItem('auth_token')
          setToken(null)
          setUser(null)
        }
      }
      setLoading(false)
    }

    init()
  }, [token])

  const login = useCallback((tokenResponse) => {
    const { access_token, ...userData } = tokenResponse
    localStorage.setItem('auth_token', access_token)
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
    localStorage.removeItem('auth_token')
    setToken(null)
    setUser(null)
    navigate('/login')
  }, [token, navigate])

  const hasRole = useCallback((requiredRole) => {
    if (!user) return false
    const rolePriority = { viewer: 1, editor: 2, admin: 3 }
    return (rolePriority[user.role] || 0) >= (rolePriority[requiredRole] || 0)
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
