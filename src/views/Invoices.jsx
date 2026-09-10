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

const INVOICE_FLOW = { draft: ['issued'], issued: ['paid'], paid: [] }

// Invoices (C16; MC 1175.2 edits). InvoiceOut carries total + lines +
// payments. Issued (not yet paid) invoices are inline line-editable and
// cancellable (makulering — only after a full refund); paid keeps only
// status/payment actions. Status transitions per contract.
export default function Invoices() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canAdvance = user && ['admin', 'finance'].includes(user.role)

  const [items, setItems] = useState([])

  const reload = useCallback(() => {
    setLoading(true)
    api.listInvoices(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  // options for the edit form (only needed by editors)
  useEffect(() => {
    if (!canAdvance) return
    api.listItems(token, { active: 1 }).then((d) => setItems(d || [])).catch(() => {})
  }, [canAdvance, token])

  // MC 1175.2 — inline edit of one invoice's lines at a time
  const [editId, setEditId] = useState(null)
  const [editLines, setEditLines] = useState([])
  const [editError, setEditError] = useState(null)
  const [editSaving, setEditSaving] = useState(false)

  function startEdit(inv) {
    setEditError(null)
    // The list view does not carry lines — fetch the invoice detail first.
    api.getInvoice(token, inv.id)
      .then((full) => {
        setEditId(full.id)
        setEditLines((full.lines || []).map((ln) => ({ item_id: ln.item_id ?? '', description: ln.description, qty: ln.qty })))
      })
      .catch((err) => setEditError(err.message))
  }
  function cancelEditForm() { setEditId(null); setEditLines([]); setEditError(null) }
  function updateEditLine(i, field, value) {
    setEditLines(editLines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln)))
  }
  function addEditLine() { setEditLines([...editLines, { item_id: '', description: '', qty: 1 }]) }
  function removeEditLine(i) { setEditLines(editLines.length > 1 ? editLines.filter((_, idx) => idx !== i) : [{ item_id: '', description: '', qty: 1 }]) }

  async function saveEdit() {
    const clean = editLines.filter((ln) => ln.item_id || (ln.description || '').trim())
    if (clean.length === 0) { setEditError('Lägg till minst en rad med artikel eller beskrivning.'); return }
    setEditSaving(true)
    setEditError(null)
    try {
      // Replace the whole line set; the server keeps prices server-side (C14).
      await api.updateInvoiceLines(token, editId, clean.map((ln) => {
        const out = { qty: Number(ln.qty) || 1 }
        if (ln.item_id) out.item_id = Number(ln.item_id)
        else out.description = ln.description.trim()
        return out
      }))
      setNotice(`Fakturan ${editId} rättad.`)
      cancelEditForm()
      reload()
    } catch (err) { setEditError(err.message) } finally { setEditSaving(false) }
  }

  async function makulera(inv) {
    if (!window.confirm(`Makulera faktura ${inv.id}? Kräver att alla betalningar är makulerade (netto noll). Detta går inte att ångra.`)) return
    try {
      await api.cancelInvoice(token, inv.id)
      setNotice(`Fakturan ${inv.id} makulerades.`)
      if (editId === inv.id) cancelEditForm()
      reload()
    } catch (err) { setError(err.message) }
  }

  async function advance(inv) {
    const next = INVOICE_FLOW[inv.status]?.[0]
    if (!next) return
    try {
      await api.setInvoiceStatus(token, inv.id, next)
      setNotice(`Fakturan ${inv.id} uppdaterades till "${next}".`)
      reload()
    } catch (err) { setError(err.message) }
  }

  const [payInvId, setPayInvId] = useState(null)
  const [pAmount, setPAmount] = useState('')
  const [pMethod, setPMethod] = useState('bank')
  const [payBusy, setPayBusy] = useState(false)

  async function onPay(e, invId) {
    e.preventDefault()
    try {
      await api.recordPayment(token, invId, { amount: pAmount, method: pMethod })
      setNotice('Betalning registrerad.')
      setPayInvId(null); setPAmount('')
      reload()
    } catch (err) { setError(err.message) } finally { setPayBusy(false) }
  }

  // MC 1175.3 — makulering av enskild betalning (append-only kreditverksrad).
  // När fakturans sista betalning makuleras fallar den tillbaka till "issued"
  // och kan då makuleras (T2 kräver netto noll).
  const [payDetailId, setPayDetailId] = useState(null)
  const [payDetail, setPayDetail] = useState(null)
  const [payDetailBusy, setPayDetailBusy] = useState(false)

  function openPayments(inv) {
    setPayDetailId(inv.id); setPayDetail(null); setError(null)
    api.getInvoice(token, inv.id).then(setPayDetail).catch((e) => setError(e.message))
  }
  function closePayments() { setPayDetailId(null); setPayDetail(null) }

  async function makuleraPayment(p) {
    if (!window.confirm(`Makulera betalning ${p.id} (${p.amount} kr)? En kreditverksrad läggs till — originalet raderas inte.`)) return
    setPayDetailBusy(true)
    try {
      await api.cancelPayment(token, p.id)
      setNotice(`Betalning ${p.id} makulerad.`)
      const inv = await api.getInvoice(token, payDetailId)
      setPayDetail(inv)
      reload()
    } catch (err) { setError(err.message) } finally { setPayDetailBusy(false) }
  }

  const columns = [
    { key: 'id', label: 'Nr', render: (r) => <span className="mono">#{r.id}</span> },
    {
      key: 'order_id', label: 'Order', render: (r) =>
        r.order_id != null ? <span className="mono">#{r.order_id}</span> : <span className="muted">—</span>,
    },
    { key: 'status', label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'total', label: 'Totalt', align: 'num', render: (r) => <Money value={r.total} /> },
    { key: 'due_date', label: 'Förfallo', render: (r) => r.due_date || <span className="muted">—</span> },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Fakturor</h2>
          <p>Fakturadrift: dra ut från order, skicka och betala.</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga fakturor ännu. Fakturera en bekräftad order."
        ariaLabel="Fakturalista"
        keyOf={(r) => r.id}
        actions={(r) => (
          <span className="row-actions">
            {canAdvance && r.status === 'issued' && editId !== r.id && (
              <button type="button" className="btn btn-mini" onClick={() => startEdit(r)}>
                Redigera
              </button>
            )}
            {canAdvance && INVOICE_FLOW[r.status]?.[0] && (
              <button type="button" className="btn btn-mini" onClick={() => advance(r)}>
                → {INVOICE_FLOW[r.status][0]}
              </button>
            )}
            {canAdvance && r.status === 'issued' && (
              <button type="button" className="btn btn-mini" onClick={() => setPayInvId(payInvId === r.id ? null : r.id)}>
                Betala
              </button>
            )}
            {canAdvance && r.status !== 'cancelled' && (
              <button type="button" className="btn btn-mini" onClick={() => openPayments(r)}>
                Betalningar
              </button>
            )}
            {canAdvance && r.status !== 'cancelled' && (
              <button type="button" className="btn btn-mini btn-ghost" onClick={() => makulera(r)}>
                Makulera
              </button>
            )}
          </span>
        )}
      />

      {editId !== null && (
        <div className="card" role="group" aria-label={`Redigera faktura ${editId}`}>
          <h3>Redigera faktura #{editId}</h3>
          <p className="muted small">
            Endast obetalade fakturor kan redigeras. Priset hämtas från befintliga rader eller artikelregistret — aldrig från formuläret.
          </p>
          {editError && <p className="notice-error" role="alert">{editError}</p>}
          <div className="order-lines">
            {editLines.map((ln, i) => (
              <div className="order-line" key={i}>
                <div className="field line" style={{ flexGrow: 2 }}>
                  <label htmlFor={`edit-inv-line-item-${i}`}>Artikel</label>
                  <select
                    id={`edit-inv-line-item-${i}`}
                    value={ln.item_id}
                    onChange={(e) => updateEditLine(i, 'item_id', e.target.value)}
                  >
                    <option value="">— fri rad (beskrivning) —</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.sku} — {it.name}</option>
                    ))}
                  </select>
                </div>
                {!ln.item_id && (
                  <div className="field line" style={{ flexGrow: 2 }}>
                    <label htmlFor={`edit-inv-line-desc-${i}`}>Beskrivning</label>
                    <input
                      id={`edit-inv-line-desc-${i}`}
                      value={ln.description}
                      onChange={(e) => updateEditLine(i, 'description', e.target.value)}
                    />
                  </div>
                )}
                <div className="field line" style={{ flexBasis: '80px' }}>
                  <label htmlFor={`edit-inv-line-qty-${i}`}>Antal</label>
                  <input
                    id={`edit-inv-line-qty-${i}`}
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

      {payDetailId !== null && (
        <div className="card" role="group" aria-label={`Betalningar faktura ${payDetailId}`}>
          <h3>Betalningar — faktura #{payDetailId}</h3>
          {!payDetail && <p className="muted">Laddar…</p>}
          {payDetail && (payDetail.payments || []).length === 0 && (
            <p className="muted">Inga betalningar registrerade.</p>
          )}
          {payDetail && (payDetail.payments || []).length > 0 && (
            <ul className="stack" aria-label="Betalningslista">
              {payDetail.payments.map((p) => (
                <li key={p.id} className="row-actions">
                  <span className="mono">#{p.id}</span>
                  <Money value={p.amount} />
                  <span className="muted">{p.method}</span>
                  {p.cancels_payment_id != null && (
                    <span className="muted small">(kreditverksrad — makulerar #{p.cancels_payment_id})</span>
                  )}
                  {p.amount > 0 && p.cancels_payment_id == null && (
                    <button type="button" className="btn btn-mini btn-ghost" disabled={payDetailBusy} onClick={() => makuleraPayment(p)}>
                      Makulera betalning
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {payDetail && (
            <p className="muted small">
              Netto registrerat: <Money value={payDetail.payments.reduce((s, p) => s + Number(p.amount), 0).toFixed(2)} /> av {payDetail.total}
            </p>
          )}
          <button type="button" className="btn btn-ghost" onClick={closePayments}>Stäng</button>
        </div>
      )}

      {payInvId && (
        <form className="card" onSubmit={(e) => onPay(e, payInvId)} noValidate>
          <h3>Registrera betalning — faktura #{payInvId}</h3>
          <div className="fieldset-inline">
            <div className="field line">
              <label htmlFor="p-amount">Belopp (kr)</label>
              <input id="p-amount" inputMode="decimal" value={pAmount} onChange={(e) => setPAmount(e.target.value)} placeholder="0,00" required />
            </div>
            <div className="field line">
              <label htmlFor="p-method">Metod</label>
              <select id="p-method" value={pMethod} onChange={(e) => setPMethod(e.target.value)}>
                <option value="bank">Bank</option>
                <option value="cash">Kontant</option>
                <option value="card">Kort</option>
              </select>
            </div>
          </div>
          <div className="row-actions">
            <button type="submit" className="btn btn-primary" disabled={payBusy}>{payBusy ? 'Registrerar…' : 'Registrera betalning'}</button>
            <button type="button" className="btn btn-ghost" onClick={() => setPayInvId(null)}>Avbryt</button>
          </div>
        </form>
      )}
    </div>
  )
}
