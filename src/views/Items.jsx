import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'
import Money from '../components/Money.jsx'

// Catalog (C8) — item list + create form. Money values are owned by
// the server; the form submits unit_price as a plain string and the
// server normalises it (C23). Views only what it was asked to show.
export default function Items() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const canEdit = user && ['admin', 'sales', 'procurement'].includes(user.role)

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    api
      .listItems(token, { active: 1 })
      .then((data) => setRows(data || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => {
    reload()
  }, [reload])

  // blank create form
  const [form, setForm] = useState({ sku: '', name: '', unit_price: '', qty_on_hand: '', description: '' })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  function onField(e) {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  async function onCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!form.sku.trim() || !form.name.trim()) {
      setFormError('Artikelnummer (SKU) och namn krävs.')
      return
    }
    setSaving(true)
    try {
      await api.createItem(token, {
        sku: form.sku.trim(),
        name: form.name.trim(),
        description: form.description.trim() || null,
        unit_price: form.unit_price,
        qty_on_hand: Number(form.qty_on_hand) || 0,
      })
      setForm({ sku: '', name: '', unit_price: '', qty_on_hand: '', description: '' })
      setNotice('Artikeln skapades.')
      reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const columns = [
    { key: 'sku', label: 'Artikelnr', render: (r) => <span className="mono">{r.sku}</span> },
    { key: 'name', label: 'Namn' },
    { key: 'unit_price', label: 'Pris', align: 'num', render: (r) => <Money value={r.unit_price} /> },
    { key: 'qty_on_hand', label: 'Lager', align: 'num' },
    { key: 'active', label: 'Aktiv', render: (r) => (r.active ? 'Ja' : 'Nej') },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Artiklar</h2>
          <p>Produktkatalog och lagersaldo.</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga artiklar ännu."
        ariaLabel="Artikellista"
        keyOf={(r) => r.id}
      />

      {canEdit && (
        <form className="card" onSubmit={onCreate} noValidate>
          <h3>Ny artikel</h3>
          {formError && <p className="notice-error" role="alert">{formError}</p>}
          <div className="fieldset-inline">
            <div className="field line" style={{ flexBasis: '140px' }}>
              <label htmlFor="sku">Artikelnummer</label>
              <input id="sku" name="sku" value={form.sku} onChange={onField} required />
            </div>
            <div className="field line" style={{ flexGrow: 2 }}>
              <label htmlFor="name">Namn</label>
              <input id="name" name="name" value={form.name} onChange={onField} required />
            </div>
            <div className="field line">
              <label htmlFor="unit_price">Pris (kr)</label>
              <input id="unit_price" name="unit_price" value={form.unit_price} onChange={onField} inputMode="decimal" placeholder="0,00" />
            </div>
            <div className="field line" style={{ flexBasis: '110px' }}>
              <label htmlFor="qty_on_hand">Lagersaldo</label>
              <input id="qty_on_hand" name="qty_on_hand" value={form.qty_on_hand} onChange={onField} inputMode="numeric" placeholder="0" />
            </div>
          </div>
          <div className="field">
            <label htmlFor="description">Beskrivning</label>
            <textarea id="description" name="description" rows={2} value={form.description} onChange={onField} />
          </div>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Sparar…' : 'Skapa artikel'}
          </button>
        </form>
      )}
    </div>
  )
}
