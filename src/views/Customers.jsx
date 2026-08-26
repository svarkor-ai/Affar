import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'

// Customers (C10) — list + create form. Swedish UI copy.
export default function Customers() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canEdit = user && ['admin', 'sales'].includes(user.role)

  const reload = useCallback(() => {
    setLoading(true)
    api.listCustomers(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  const [form, setForm] = useState({ name: '', email: '', phone: '', org_no: '' })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  function onField(e) { setForm({ ...form, [e.target.name]: e.target.value }) }

  async function onCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!form.name.trim()) {
      setFormError('Kundnamn krävs.')
      return
    }
    setSaving(true)
    try {
      await api.createCustomer(token, {
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        org_no: form.org_no.trim() || null,
      })
      setForm({ name: '', email: '', phone: '', org_no: '' })
      setNotice('Kunden skapades.')
      reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const columns = [
    { key: 'name', label: 'Namn' },
    { key: 'email', label: 'E-post', render: (r) => r.email || <span className="muted">—</span> },
    { key: 'phone', label: 'Telefon', render: (r) => r.phone || <span className="muted">—</span> },
    { key: 'org_no', label: 'Org.nr', render: (r) => r.org_no || <span className="muted">—</span> },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Kunder</h2>
          <p>Registrerade kunder.</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga kunder ännu."
        ariaLabel="Kundlista"
        keyOf={(r) => r.id}
      />

      {canEdit && (
        <form className="card" onSubmit={onCreate} noValidate>
          <h3>Ny kund</h3>
          {formError && <p className="notice-error" role="alert">{formError}</p>}
          <div className="fieldset-inline">
            <div className="field line" style={{ flexGrow: 2 }}>
              <label htmlFor="name">Namn</label>
              <input id="name" name="name" value={form.name} onChange={onField} required />
            </div>
            <div className="field line">
              <label htmlFor="email">E-post</label>
              <input id="email" name="email" type="email" value={form.email} onChange={onField} />
            </div>
            <div className="field line">
              <label htmlFor="phone">Telefon</label>
              <input id="phone" name="phone" value={form.phone} onChange={onField} />
            </div>
            <div className="field line">
              <label htmlFor="org_no">Organisationsnr</label>
              <input id="org_no" name="org_no" value={form.org_no} onChange={onField} />
            </div>
          </div>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Sparar…' : 'Skapa kund'}
          </button>
        </form>
      )}
    </div>
  )
}
