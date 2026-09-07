import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'

// Admin-users (MC 1120.1) — list + create + role/deactivate management.
// This view is admin-role only; the App.jsx route gate and the backend
// require_role(["admin"]) both enforce that. Swedish UI copy.
const ROLE_LABEL = {
  admin: 'Admin',
  sales: 'Försäljning',
  finance: 'Ekonomi',
  procurement: 'Inköp',
  customer: 'Kund',
}

export default function AdminUsers() {
  const { token } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const reload = useCallback(() => {
    setLoading(true)
    api.listAdminUsers(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  // ---- create form ----
  const [form, setForm] = useState({ username: '', role: 'sales', email: '', password: '' })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  function onField(e) { setForm({ ...form, [e.target.name]: e.target.value }) }

  async function onCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!form.username.trim()) {
      setFormError('Användarnamn krävs.')
      return
    }
    if (form.password.length < 6) {
      setFormError('Lösenordet måste vara minst 6 tecken.')
      return
    }
    setSaving(true)
    try {
      await api.createAdminUser(token, {
        username: form.username.trim(),
        role: form.role,
        email: form.email.trim() || null,
        password: form.password,
      })
      setForm({ username: '', role: 'sales', email: '', password: '' })
      setNotice(`Användaren skapades.`)
      reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function onSetRole(u, role) {
    try {
      await api.updateAdminUser(token, u.id, { role })
      setNotice(`Rollen för ${u.username} ändrades till ${ROLE_LABEL[role] || role}.`)
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  async function onToggleActive(u) {
    try {
      await api.updateAdminUser(token, u.id, { is_active: !u.is_active })
      setNotice(u.is_active ? `${u.username} avaktiverades.` : `${u.username} aktiverades.`)
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  const columns = [
    { key: 'username', label: 'Användarnamn' },
    { key: 'role', label: 'Roll', render: (r) => ROLE_LABEL[r.role] || r.role },
    { key: 'email', label: 'E-post', render: (r) => r.email || <span className="muted">—</span> },
    {
      key: 'is_active', label: 'Status', render: (r) =>
        r.is_active
          ? <span className="badge badge-paid">Aktiv</span>
          : <span className="badge badge-draft">Avaktiverad</span>,
    },
  ]

  const roleOptions = Object.keys(ROLE_LABEL)

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Användare</h2>
          <p>Skapa, hantera roller och aktivera/avaktivera användare (admin).</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga användare ännu."
        ariaLabel="Användarlista"
        keyOf={(r) => r.id}
        actions={(u) => (
          <span className="row-actions">
            <select
              className="role-select"
              value={u.role}
              aria-label={`Ändra roll för ${u.username}`}
              onChange={(e) => onSetRole(u, e.target.value)}
            >
              {roleOptions.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onToggleActive(u)}
            >
              {u.is_active ? 'Avaktivera' : 'Aktivera'}
            </button>
          </span>
        )}
      />

      <form className="card" onSubmit={onCreate} noValidate>
        <h3>Ny användare</h3>
        {formError && <p className="notice-error" role="alert">{formError}</p>}
        <div className="fieldset-inline">
          <div className="field line">
            <label htmlFor="username">Användarnamn</label>
            <input id="username" name="username" value={form.username} onChange={onField} required />
          </div>
          <div className="field line">
            <label htmlFor="role">Roll</label>
            <select id="role" name="role" value={form.role} onChange={onField}>
              {roleOptions.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </div>
          <div className="field line" style={{ flexGrow: 2 }}>
            <label htmlFor="email">E-post</label>
            <input id="email" name="email" type="email" value={form.email} onChange={onField} />
          </div>
          <div className="field line">
            <label htmlFor="password">Lösenord</label>
            <input id="password" name="password" type="password" value={form.password} onChange={onField} required />
          </div>
        </div>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Sparar…' : 'Skapa användare'}
        </button>
      </form>
    </div>
  )
}
