import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  // Validate existing token on mount
  useEffect(() => {
    if (token) {
      fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(res => {
          if (!res.ok) throw new Error('Invalid token')
          return res.json()
        })
        .then(userData => setUser(userData))
        .catch(() => {
          localStorage.removeItem('auth_token')
          setToken(null)
          setUser(null)
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
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
    isAuthenticated: !!user && !!token,
    login,
    logout,
    hasRole,
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
