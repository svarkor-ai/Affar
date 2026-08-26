import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'
import { useAuth } from '../auth.context.jsx'
import DataTable from '../components/DataTable.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import Money from '../components/Money.jsx'

const PO_FLOW = { draft: ['ordered'], ordered: ['received'], received: [] }

// Purchase orders (C19). PurchaseOrderIn carries supplier + lines
// with unit_cost ON THE WIRE (PO-scoped — unlike sales orders, C18).
export default function Purchase() {
  const { token, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const canEdit = user && ['admin', 'procurement'].includes(user.role)

  const [suppliers, setSuppliers] = useState([])
  const [items, setItems] = useState([])

  const reload = useCallback(() => {
    setLoading(true)
    api.listPurchaseOrders(token).then((d) => setRows(d || [])).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [token])
  useEffect(() => { reload() }, [reload])

  useEffect(() => {
    if (!canEdit) return
    api.listSuppliers(token).then((d) => setSuppliers(d || [])).catch(() => {})
    api.listItems(token, { active: 1 }).then((d) => setItems(d || [])).catch(() => {})
  }, [canEdit, token])

  const [supplierId, setSupplierId] = useState('')
  const [lines, setLines] = useState([{ item_id: '', qty: 1, unit_cost: '' }])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  function updateLine(i, field, value) { setLines(lines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln))) }
  function addLine() { setLines([...lines, { item_id: '', qty: 1, unit_cost: '' }]) }
  function removeLine(i) { setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : [{ item_id: '', qty: 1, unit_cost: '' }]) }

  async function onCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!supplierId) { setFormError('Välj en leverantör.'); return }
    const clean = lines.filter((ln) => ln.item_id)
    if (clean.length === 0) { setFormError('Lägg till minst en inköpsrad med vald artikel.'); return }
    setSaving(true)
    try {
      await api.createPurchaseOrder(token, {
        supplier_id: Number(supplierId),
        lines: clean.map((ln) => ({
          item_id: Number(ln.item_id),
          qty: Number(ln.qty) || 1,
          unit_cost: ln.unit_cost,
        })),
      })
      setSupplierId(''); setLines([{ item_id: '', qty: 1, unit_cost: '' }])
      setNotice('Inköpsordern skapades.')
      reload()
    } catch (err) { setFormError(err.message) } finally { setSaving(false) }
  }

  async function advance(po) {
    const next = PO_FLOW[po.status]?.[0]
    if (!next) return
    try {
      await api.setPurchaseStatus(token, po.id, next)
      setNotice(`Inköpsordern ${po.id} uppdaterades till "${next}".`)
      reload()
    } catch (err) { setError(err.message) }
  }

  const columns = [
    { key: 'id', label: 'Nr', render: (r) => <span className="mono">#{r.id}</span> },
    {
      key: 'supplier_id', label: 'Leverantör', render: (r) =>
        r.supplier_name || (suppliers.find((s) => s.id === r.supplier_id)?.name) || `#${r.supplier_id}`,
    },
    { key: 'status', label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'total', label: 'Totalt', align: 'num', render: (r) => <Money value={r.total} /> },
  ]

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Inköp</h2>
          <p>Inköpsorder till leverantörer, med enhetskostnad.</p>
        </div>
      </div>

      {notice && <p className="notice-success" role="status">{notice}</p>}

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        emptyText="Inga inköpsorder ännu."
        ariaLabel="Inköpslista"
        keyOf={(r) => r.id}
        actions={(r) =>
          PO_FLOW[r.status]?.[0] && (
            <button type="button" className="btn btn-mini" onClick={() => advance(r)}>
              → {PO_FLOW[r.status][0]}
            </button>
          )
        }
      />

      {canEdit && (
        <form className="card" onSubmit={onCreate} noValidate>
          <h3>Ny inköpsorder</h3>
          {formError && <p className="notice-error" role="alert">{formError}</p>}

          <div className="field">
            <label htmlFor="supplier_id">Leverantör</label>
            <select id="supplier_id" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">— välj leverantör —</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div className="order-lines">
            {lines.map((ln, i) => (
              <div className="order-line" key={i}>
                <div className="field line" style={{ flexGrow: 2 }}>
                  <label htmlFor={`po-item-${i}`}>Artikel</label>
                  <select id={`po-item-${i}`} value={ln.item_id} onChange={(e) => updateLine(i, 'item_id', e.target.value)}>
                    <option value="">— välj artikel —</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.sku} — {it.name}</option>
                    ))}
                  </select>
                </div>
                <div className="field line" style={{ flexBasis: '80px' }}>
                  <label htmlFor={`po-qty-${i}`}>Antal</label>
                  <input id={`po-qty-${i}`} type="number" min="1" value={ln.qty} onChange={(e) => updateLine(i, 'qty', e.target.value)} />
                </div>
                <div className="field line" style={{ flexBasis: '120px' }}>
                  <label htmlFor={`po-cost-${i}`}>Enhetskostnad (kr)</label>
                  <input id={`po-cost-${i}`} inputMode="decimal" value={ln.unit_cost} onChange={(e) => updateLine(i, 'unit_cost', e.target.value)} placeholder="0,00" />
                </div>
                <button type="button" className="btn btn-mini btn-ghost" onClick={() => removeLine(i)} aria-label="Ta bort rad">Ta bort</button>
              </div>
            ))}
            <button type="button" className="btn btn-mini" onClick={addLine}>+ Lägg till rad</button>
          </div>

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Skapar inköpsorder…' : 'Skapa inköpsorder'}
          </button>
        </form>
      )}
    </div>
  )
}
