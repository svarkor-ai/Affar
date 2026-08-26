import { useState } from 'react'
import { useAuth } from '../auth.context.jsx'

// Login (C6). Demo credentials are shown on-screen for the throwaway
// demo (seed password policy: demo-only, not secrets — C22/I4).
export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError(null)
    if (!username.trim() || !password) {
      setError('Fyll i både användarnamn och lösenord.')
      return
    }
    setBusy(true)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err.message || 'Inloggning misslyckades.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand">Affär</div>
        <p className="sub">Affärssystem — order, faktura, betalning, spårning och inköp.</p>

        <form onSubmit={onSubmit} noValidate>
          {error && (
            <p className="notice-error" role="alert">{error}</p>
          )}
          <div className="field">
            <label htmlFor="username">Användarnamn</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="password">Lösenord</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy} style={{ width: '100%' }}>
            {busy ? 'Loggar in…' : 'Logga in'}
          </button>
        </form>

        <div className="demo">
          <strong>Demokonton (endast demo)</strong>
          {[
            ['admin', 'demo-admin-2026'],
            ['sales', 'demo-sales-2026'],
            ['finance', 'demo-finance-2026'],
            ['procurement', 'demo-procurement-2026'],
            ['customer', 'demo-customer-2026'],
          ].map(([u, p]) => (
            <div key={u}>
              <code>{u}</code> / <code>{p}</code>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
