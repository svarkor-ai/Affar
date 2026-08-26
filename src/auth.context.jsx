import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from './api.js'

const TOKEN_KEY = 'affar.token'

// Role → capabilities map for the 5 fleet roles (C-F / C4 ROLES).
// Mirrors the architecture's coarse `require_role` gates; this is presentational
// only — the backend is the real authority (C25).
const PERMS = {
  admin: ['orders', 'invoices', 'payments', 'items', 'customers', 'suppliers', 'purchase'],
  sales: ['orders', 'items', 'customers', 'payments'],
  finance: ['invoices', 'payments', 'items', 'customers'],
  procurement: ['purchase', 'suppliers', 'items'],
  customer: [],
}

// Public label for each role — Swedish copy (frontend user-facing is sv).
const ROLE_LABEL = {
  admin: 'Admin',
  sales: 'Försäljning',
  finance: 'Ekonomi',
  procurement: 'Inköp',
  customer: 'Kund',
}

export function useAuth() {
  return useContext(AuthContext)
}

export const AuthContext = createContext(null)

export default AuthProvider

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || null)
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading') // loading | authed | anonymous

  // On first mount, if a token exists, hydrate the user via /me.
  useEffect(() => {
    let cancelled = false
    if (!token) {
      setStatus('anonymous')
      return
    }
    api
      .me(token)
      .then((u) => {
        if (cancelled) return
        setUser(u)
        setStatus('authed')
      })
      .catch(() => {
        if (cancelled) return
        // Invalid/expired token — clear it and go anonymous.
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUser(null)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const login = useCallback(async (username, password) => {
    const data = await api.login(username, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
    setUser(data.user)
    setStatus('authed')
    return data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(
    () => ({
      token,
      user,
      status,
      login,
      logout,
      role: user?.role || null,
      roleLabel: user ? ROLE_LABEL[user.role] || user.role : null,
      can: (cap) => Boolean(user && PERMS[user.role]?.includes(cap)),
    }),
    [token, user, status, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
