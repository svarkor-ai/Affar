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

// Orders (C14; MC 1175.1 edits). Create order with customer + lines
// (item_id + qty — NO price; the server derives line prices and the total,
// C23/C14). Drafts are inline-editable (lines/qty) and cancellable;
// confirmed+ orders keep only their lifecycle actions.
export default function Orders() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canEdit = user && ['admin', 'sales'].includes(user.role)

  const [customers, setCustomers] = useState([])
  const [items, setItems] = useState([])

  // MC 1369.4 — order_id -> invoice map so an already-invoiced order shows a
  // "Fakturerad" marker instead of a Fakturera button that would just 409.
  // Invoices GET is admin/finance-only: on failure (e.g. 403) fall back
  // silently to the previous behaviour, never blank the page.
  const [invoiceByOrder, setInvoiceByOrder] = useState({})
  const loadInvoices = useCallback(() => {
    let alive = true
    api.listInvoices(token)
      .then((d) => {
        if (!alive) return
        const map = {}
        for (const inv of d || []) {
          if (inv && inv.order_id != null) map[inv.order_id] = inv
        }
        setInvoiceByOrder(map)
      })
      .catch(() => {})
    return () => { alive = false }
  }, [token])
  useEffect(() => loadInvoices(), [loadInvoices])

  const reload = useCallback(() => {
    setLoading(true)
    api.listOrders(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  // options for create form
  useEffect(() => {
    if (!canEdit) return
    api.listCustomers(token).then((d) => setCustomers((d || []).filter((c) => c.is_active !== false))).catch(() => {})
    api.listItems(token, { active: 1 }).then((d) => setItems(d || [])).catch(() => {})
  }, [canEdit, token])

  // create form
  const [custId, setCustId] = useState('')
  const [lines, setLines] = useState([{ item_id: '', qty: 1 }])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  // MC 1175.1 — inline draft edit (one order at a time)
  const [editId, setEditId] = useState(null)
  const [editLines, setEditLines] = useState([])
  const [editError, setEditError] = useState(null)
  const [editSaving, setEditSaving] = useState(false)

  function updateLine(i, field, value) {
    setLines(lines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln)))
  }
  function addLine() { setLines([...lines, { item_id: '', qty: 1 }]) }
  function removeLine(i) { setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ item_id: '', qty: 1 }]) }

  function startEdit(order) {
    setEditError(null)
    setEditId(order.id)
    setEditLines(order.lines.map((ln) => ({ item_id: ln.item_id, qty: ln.qty })))
  }
  function cancelEditForm() { setEditId(null); setEditLines([]); setEditError(null) }
  function updateEditLine(i, field, value) {
    setEditLines(editLines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln)))
  }
  function addEditLine() { setEditLines([...editLines, { item_id: '', qty: 1 }]) }
  function removeEditLine(i) { setEditLines(editLines.length > 1 ? editLines.filter((_, idx) => idx !== i) : [{ item_id: '', qty: 1 }]) }

  async function saveEdit() {
    const clean = editLines.filter((ln) => ln.item_id)
    if (clean.length === 0) { setEditError('Lägg till minst en orderrad med vald artikel.'); return }
    setEditSaving(true)
    setEditError(null)
    try {
      // Replace the whole line set; the server re-snapshots prices (C14).
      await api.updateOrderLines(token, editId, clean.map((ln) => ({ item_id: Number(ln.item_id), qty: Number(ln.qty) || 1 })))
      setNotice(`Ordern ${editId} uppdaterades.`)
      cancelEditForm()
      reload()
    } catch (err) { setEditError(err.message) } finally { setEditSaving(false) }
  }

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

  async function cancel(order) {
    if (!window.confirm(`Avbryt order ${order.id}? Detta går inte att ångra.`)) return
    try {
      await api.cancelOrder(token, order.id)
      setNotice(`Ordern ${order.id} avbröts.`)
      if (editId === order.id) cancelEditForm()
      reload()
    } catch (err) {
      setError(err.message)
    }
  }

  async function makeInvoice(order) {
    try {
      await api.createInvoiceFromOrder(token, order.id)
      setNotice(`Faktura skapades för order ${order.id}.`)
      loadInvoices()
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
            {canEdit && r.status === 'draft' && editId !== r.id && (
              <button type="button" className="btn btn-mini" onClick={() => startEdit(r)}>
                Redigera
              </button>
            )}
            {r.status === 'draft' && (
              <button type="button" className="btn btn-mini" onClick={() => confirm(r)}>
                Bekräfta
              </button>
            )}
            {canEdit && r.status === 'draft' && (
              <button type="button" className="btn btn-mini btn-ghost" onClick={() => cancel(r)}>
                Avbryt
              </button>
            )}
            {r.status === 'confirmed' && (invoiceByOrder[r.id] ? (
              <span className="muted">Fakturerad{invoiceByOrder[r.id].invoice_no ? ` (${invoiceByOrder[r.id].invoice_no})` : ''}</span>
            ) : (
              <button type="button" className="btn btn-mini" onClick={() => makeInvoice(r)}>
                Fakturera
              </button>
            ))}
          </span>
        )}
      />

      {editId !== null && (
        <div className="card" role="group" aria-label={`Redigera order ${editId}`}>
          <h3>Redigera order #{editId}</h3>
          <p className="muted small">
            Endast utkast kan redigeras. Priset sätts om av systemet från aktuella artikelpriser.
          </p>
          {editError && <p className="notice-error" role="alert">{editError}</p>}
          <div className="order-lines">
            {editLines.map((ln, i) => (
              <div className="order-line" key={i}>
                <div className="field line" style={{ flexGrow: 2 }}>
                  <label htmlFor={`edit-line-item-${i}`}>Artikel</label>
                  <select
                    id={`edit-line-item-${i}`}
                    value={ln.item_id}
                    onChange={(e) => updateEditLine(i, 'item_id', e.target.value)}
                  >
                    <option value="">— välj artikel —</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.sku} — {it.name}</option>
                    ))}
                  </select>
                </div>
                <div className="field line" style={{ flexBasis: '80px' }}>
                  <label htmlFor={`edit-line-qty-${i}`}>Antal</label>
                  <input
                    id={`edit-line-qty-${i}`}
                    type="number"
                    min="1"
                    value={ln.qty}
                    onChange={(e) => updateEditLine(i, 'qty', e.target.value)}
                  />
                </div>
                <button type="button" className="btn btn-mini btn-ghost" onClick={() => removeEditLine(i)} aria-label="Ta bort rad">
                  Ta bort
                </button>
              </div>
            ))}
            <button type="button" className="btn btn-mini" onClick={addEditLine}>+ Lägg till rad</button>
          </div>
          <span className="row-actions">
            <button type="button" className="btn btn-primary" onClick={saveEdit} disabled={editSaving}>
              {editSaving ? 'Sparar…' : 'Spara ändringar'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={cancelEditForm}>Avbryt redigering</button>
          </span>
        </div>
      )}

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
