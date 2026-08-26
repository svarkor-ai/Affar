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

// Invoices (C16). InvoiceOut carries total + lines + payments.
// Status transitions per contract. Inline advance + a modal-free
// expand for lines/payment detail would bloat this scaffold; the list
// shows the essentials and actions advance status. Payment recording
// lives in the Payments view / Payment form here for paid+ invoices.
export default function Invoices() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canAdvance = user && ['admin', 'finance'].includes(user.role)

  const reload = useCallback(() => {
    setLoading(true)
    api.listInvoices(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

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
          </span>
        )}
      />

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
