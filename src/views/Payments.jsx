import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'
import Money from '../components/Money.jsx'

function formatWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('sv-SE', { dateStyle: 'short', timeStyle: 'short' }).format(d)
}

// Payments (C17) — read-only ledger of recorded payments. Amount is a
// Decimal(12,2) owned by the server; this view only formats it.
export default function Payments() {
  const { token } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(() => {
    setLoading(true)
    api.listPayments(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  const columns = [
    { key: 'id', label: 'Nr', render: (r) => <span className="mono">#{r.id}</span> },
    {
      key: 'invoice_id', label: 'Faktura', render: (r) =>
        r.invoice_id != null ? <span className="mono">#{r.invoice_id}</span> : <span className="muted">—</span>,
    },
    { key: 'method', label: 'Metod', render: (r) => (r.method || '—') },
    { key: 'amount', label: 'Belopp', align: 'num', render: (r) => <Money value={r.amount} /> },
    { key: 'date', label: 'Datum', render: (r) => formatWhen(r.created_at || r.date) },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Betalningar</h2>
          <p>Registrerade inbetalningar.</p>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga betalningar registrerade ännu."
        ariaLabel="Betalningslista"
        keyOf={(r) => r.id}
      />
    </div>
  )
}
