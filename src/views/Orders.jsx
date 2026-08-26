import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import Money from '../components/Money.jsx'

function formatWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('sv-SE', { dateStyle: 'short', timeStyle: 'short' }).format(d)
}

// Only lifecycle transition the backend exposes: draft -> confirmed via
// POST /orders/{id}/confirm (C14 rev-2). No shipped/delivered transition
// endpoint exists on orders, so the UI offers exactly the confirm action.

// Orders (C14). Create order with customer + lines (item_id + qty —
// NO price; the server derives line prices and the total, C23/C14).
// Inline status transitions on confirmed+ orders.
export default function Orders() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canEdit = user && ['admin', 'sales'].includes(user.role)

  const [customers, setCustomers] = useState([])
  const [items, setItems] = useState([])

  const reload = useCallback(() => {
    setLoading(true)
    api.listOrders(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  // options for create form
  useEffect(() => {
    if (!canEdit) return
    api.listCustomers(token).then((d) => setCustomers(d || [])).catch(() => {})
    api.listItems(token, { active: 1 }).then((d) => setItems(d || [])).catch(() => {})
  }, [canEdit, token])

  // create form
  const [custId, setCustId] = useState('')
  const [lines, setLines] = useState([{ item_id: '', qty: 1 }])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  function updateLine(i, field, value) {
    setLines(lines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln)))
  }
  function addLine() { setLines([...lines, { item_id: '', qty: 1 }]) }
  function removeLine(i) { setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ item_id: '', qty: 1 }]) }

  async function onCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!custId) { setFormError('Välj en kund.'); return }
    const clean = lines.filter((ln) => ln.item_id)
    if (clean.length === 0) { setFormError('Lägg till minst en orderrad med vald artikel.'); return }
    setSaving(true)
    try {
      await api.createOrder(token, {
        customer_id: Number(custId),
        lines: clean.map((ln) => ({ item_id: Number(ln.item_id), qty: Number(ln.qty) || 1 })),
      })
      setCustId(''); setLines([{ item_id: '', qty: 1 }])
      setNotice('Ordern skapades.')
      reload()
    } catch (err) { setFormError(err.message) } finally { setSaving(false) }
  }

  async function confirm(order) {
    // Only draft orders can be confirmed via the backend endpoint.
    if (order.status !== 'draft') return
    try {
      await api.confirmOrder(token, order.id)
      setNotice(`Ordern ${order.id} bekräftades.`)
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  async function makeInvoice(order) {
    try {
      await api.createInvoiceFromOrder(token, order.id)
      setNotice(`Faktura skapades för order ${order.id}.`)
    } catch (err) {
      setError(err.message)
    }
  }

  const columns = [
    { key: 'id', label: 'Nr', render: (r) => <span className="mono">#{r.id}</span> },
    {
      key: 'customer_id', label: 'Kund', render: (r) =>
        r.customer_name || (customers.find((c) => c.id === r.customer_id)?.name) || `#${r.customer_id}`,
    },
    { key: 'status', label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'total', label: 'Totalt', align: 'num', render: (r) => <Money value={r.total} /> },
    { key: 'created_at', label: 'Skapad', render: (r) => formatWhen(r.created_at) },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Order</h2>
          <p>Skapa och följ kundorder genom leveransflödet.</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga order ännu."
        ariaLabel="Orderlista"
        keyOf={(r) => r.id}
        actions={(r) => (
          <span className="row-actions">
            {r.status === 'draft' && (
              <button type="button" className="btn btn-mini" onClick={() => confirm(r)}>
                Bekräfta
              </button>
            )}
            {r.status === 'confirmed' && (
              <button type="button" className="btn btn-mini" onClick={() => makeInvoice(r)}>
                Fakturera
              </button>
            )}
          </span>
        )}
      />

      {canEdit && (
        <form className="card" onSubmit={onCreate} noValidate>
          <h3>Ny order</h3>
          {formError && <p className="notice-error" role="alert">{formError}</p>}

          <div className="field">
            <label htmlFor="customer_id">Kund</label>
            <select id="customer_id" value={custId} onChange={(e) => setCustId(e.target.value)}>
              <option value="">— välj kund —</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          <div className="order-lines">
            {lines.map((ln, i) => (
              <div className="order-line" key={i}>
                <div className="field line" style={{ flexGrow: 2 }}>
                  <label htmlFor={`line-item-${i}`}>Artikel</label>
                  <select
                    id={`line-item-${i}`}
                    value={ln.item_id}
                    onChange={(e) => updateLine(i, 'item_id', e.target.value)}
                  >
                    <option value="">— välj artikel —</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.sku} — {it.name}</option>
                    ))}
                  </select>
                </div>
                <div className="field line" style={{ flexBasis: '80px' }}>
                  <label htmlFor={`line-qty-${i}`}>Antal</label>
                  <input
                    id={`line-qty-${i}`}
                    type="number"
                    min="1"
                    value={ln.qty}
                    onChange={(e) => updateLine(i, 'qty', e.target.value)}
                  />
                </div>
                <button type="button" className="btn btn-mini btn-ghost" onClick={() => removeLine(i)} aria-label="Ta bort rad">
                  Ta bort
                </button>
              </div>
            ))}
            <button type="button" className="btn btn-mini" onClick={addLine}>+ Lägg till rad</button>
          </div>

          <p className="muted small">
            Prissätts automatiskt av systemet vid skapandet.
          </p>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Skapar order…' : 'Skapa order'}
          </button>
        </form>
      )}
    </div>
  )
}
