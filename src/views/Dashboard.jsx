import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'
import Money from '../components/Money.jsx'

// MC 1182.9 — Dashboard: monthly sales, AR-aging, stock balance.
// Pure read view over the three /api/reports/* endpoints; the backend owns
// every number (C23/C25) — this view only formats. A section whose report
// the role may not read (403) renders as "no access", not an error.
function Section({ title, subtitle, children }) {
  return (
    <section className="card dash-section">
      <h3>{title}</h3>
      <p className="muted">{subtitle}</p>
      {children}
    </section>
  )
}

function MonthlySales({ token }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api.monthlySalesReport(token).then(setRows).catch((e) => setError(e.message))
  }, [token])
  if (error) return <p className="notice-error" role="alert">{error}</p>
  if (!rows) return <p className="loading" role="status">Läser in…</p>
  const max = Math.max(...rows.map((r) => Number(r.total)), 1)
  return (
    <ul className="dash-bars" aria-label="Månadsförsäljning">
      {rows.map((r) => (
        <li key={r.month}>
          <span className="dash-bar-label mono">{r.month}</span>
          <span className="dash-bar-track">
            <span
              className="dash-bar-fill"
              style={{ width: Math.round((Number(r.total) / max) * 100) + '%' }}
            />
          </span>
          <span className="dash-bar-value"><Money value={r.total} /></span>
        </li>
      ))}
    </ul>
  )
}

function ArAging({ token }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api.arAgingReport(token).then(setData).catch((e) => setError(e.message))
  }, [token])
  if (error) return <p className="notice-error" role="alert">{error}</p>
  if (!data) return <p className="loading" role="status">Läser in…</p>
  const order = ['0-30', '31-60', '61-90', '90+']
  return (
    <div className="dash-aging">
      <p>
        Totalt utestående: <strong><Money value={data.total_outstanding} /></strong>
      </p>
      <table className="data" aria-label="AR-aging">
        <thead>
          <tr><th>Dagar efter fakturadatum</th><th className="num">Utestående</th></tr>
        </thead>
        <tbody>
          {order.map((k) => (
            <tr key={k}>
              <td>{k} dagar</td>
              <td className="num"><Money value={data.buckets[k] ?? 0} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StockBalance({ token }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api.stockBalanceReport(token).then(setData).catch((e) => setError(e.message))
  }, [token])
  if (error) return <p className="notice-error" role="alert">{error}</p>
  if (!data) return <p className="loading" role="status">Läser in…</p>
  const columns = [
    { key: 'sku', label: 'SKU', render: (r) => <span className="mono">{r.sku}</span> },
    { key: 'name', label: 'Artikel' },
    { key: 'qty_on_hand', label: 'Saldo', align: 'num' },
    { key: 'unit_price', label: 'Styckpris', align: 'num', render: (r) => <Money value={r.unit_price} /> },
    { key: 'stock_value', label: 'Värde', align: 'num', render: (r) => <Money value={r.stock_value} /> },
  ]
  return (
    <div className="stack">
      <p>Lagersaldo totalt: <strong><Money value={data.total_value} /></strong></p>
      <DataTable
        columns={columns}
        rows={data.items}
        loading={false}
        error={null}
        emptyText="Inga artiklar registrerade."
        ariaLabel="Lagersaldo"
        keyOf={(r) => r.item_id}
      />
    </div>
  )
}

export default function Dashboard() {
  const { token, can } = useAuth()
  const [salesErr, setSalesErr] = useState(null)
  const [agingErr, setAgingErr] = useState(null)
  const [stockErr, setStockErr] = useState(null)

  // Probe once so a 403 renders as "no access" instead of an error alert.
  useEffect(() => {
    if (!can('invoices')) { setSalesErr('no-access'); setAgingErr('no-access') }
    if (!can('items')) setStockErr('no-access')
  }, [can])

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Rapporter</h2>
          <p>Månadsförsäljning, kundfordringar och lagersaldo.</p>
        </div>
      </div>

      <Section title="Månadsförsäljning" subtitle="Fakturerat per månad (skickade + betalda fakturor).">
        {salesErr === 'no-access'
          ? <p className="muted">Du saknar behörighet för den här rapporten.</p>
          : <MonthlySales token={token} />}
      </Section>

      <Section title="Kundfordringar (AR-aging)" subtitle="Utestående per åldersbucket, dagar efter fakturadatum.">
        {agingErr === 'no-access'
          ? <p className="muted">Du saknar behörighet för den här rapporten.</p>
          : <ArAging token={token} />}
      </Section>

      <Section title="Lagersaldo" subtitle="Saldo och värde per artikel (till unit_price).">
        {stockErr === 'no-access'
          ? <p className="muted">Du saknar behörighet för den här rapporten.</p>
          : <StockBalance token={token} />}
      </Section>
    </div>
  )
}
