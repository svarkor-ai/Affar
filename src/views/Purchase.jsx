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
    api.listSuppliers(token).then((d) => setSuppliers((d || []).filter((s) => s.is_active !== false))).catch(() => {})
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

  const [editId, setEditId] = useState(null)
  const [editLines, setEditLines] = useState([])
  const [editError, setEditError] = useState(null)
  const [editSaving, setEditSaving] = useState(false)

  function startEdit(po) {
    setEditId(po.id)
    setEditError(null)
    setEditLines(po.lines.map((ln) => ({ item_id: ln.item_id, qty: ln.qty, unit_cost: ln.unit_cost })))
  }
  function stopEdit() { setEditId(null); setEditLines([]); setEditError(null) }
  function updateEditLine(i, field, value) { setEditLines(editLines.map((ln, idx) => (idx === i ? { ...ln, [field]: value } : ln))) }
  function addEditLine() { setEditLines([...editLines, { item_id: '', qty: 1, unit_cost: '' }]) }
  function removeEditLine(i) { setEditLines(editLines.length > 1 ? editLines.filter((_, idx) => idx !== i) : [{ item_id: '', qty: 1, unit_cost: '' }]) }

  async function onSaveEdit(e) {
    e.preventDefault()
    setEditError(null)
    const clean = editLines.filter((ln) => ln.item_id)
    if (clean.length === 0) { setEditError('Lägg till minst en inköpsrad med vald artikel.'); return }
    setEditSaving(true)
    try {
      await api.updatePurchaseOrderLines(token, editId, clean.map((ln) => ({
        item_id: Number(ln.item_id),
        qty: Number(ln.qty) || 1,
        unit_cost: ln.unit_cost,
      })))
      setNotice(`Inköpsordern ${editId} uppdaterades.`)
      stopEdit()
      reload()
    } catch (err) { setEditError(err.message) } finally { setEditSaving(false) }
  }

  async function onCancelPo(po) {
    if (!window.confirm(`Makulera inköpsorder ${po.id}? Detta går inte att ångra.`)) return
    try {
      await api.cancelPurchaseOrder(token, po.id)
      setNotice(`Inköpsordern ${po.id} makulerades.`)
      if (editId === po.id) stopEdit()
      reload()
    } catch (err) { setError(err.message) }
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
          (canEdit && r.status === 'draft' && editId !== r.id) || PO_FLOW[r.status]?.[0] || (canEdit && ['draft', 'ordered'].includes(r.status)) ? (
            <span className="row-actions">
              {canEdit && r.status === 'draft' && editId !== r.id && (
                <button type="button" className="btn btn-mini" onClick={() => startEdit(r)}>Redigera</button>
              )}
              {PO_FLOW[r.status]?.[0] && (
                <button type="button" className="btn btn-mini" onClick={() => advance(r)}>
                  → {PO_FLOW[r.status][0]}
                </button>
              )}
              {canEdit && ['draft', 'ordered'].includes(r.status) && (
                <button type="button" className="btn btn-mini btn-ghost" onClick={() => onCancelPo(r)}>Makulera</button>
              )}
            </span>
          ) : null
        }
      />

      {editId !== null && (
        <form className="card" onSubmit={onSaveEdit} noValidate role="group" aria-label={`Redigera inköpsorder ${editId}`}>
          <h3>Redigera inköpsorder #{editId}</h3>
          <p className="muted small">Endast utkast kan redigeras. Enhetskostnaden sätts per leverantör; radtotalen räknas om av systemet.</p>
          {editError && <p className="notice-error" role="alert">{editError}</p>}
          <div className="order-lines">
            {editLines.map((ln, i) => (
              <div className="order-line" key={i}>
                <div className="field line" style={{ flexGrow: 2 }}>
                  <label htmlFor={`edit-po-item-${i}`}>Artikel</label>
                  <select id={`edit-po-item-${i}`} value={ln.item_id} onChange={(e) => updateEditLine(i, 'item_id', e.target.value)}>
                    <option value="">— välj artikel —</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.sku} — {it.name}</option>
                    ))}
                  </select>
                </div>
                <div className="field line" style={{ flexBasis: '80px' }}>
                  <label htmlFor={`edit-po-qty-${i}`}>Antal</label>
                  <input id={`edit-po-qty-${i}`} type="number" min="1" value={ln.qty} onChange={(e) => updateEditLine(i, 'qty', e.target.value)} />
                </div>
                <div className="field line" style={{ flexBasis: '120px' }}>
                  <label htmlFor={`edit-po-cost-${i}`}>Enhetskostnad (kr)</label>
                  <input id={`edit-po-cost-${i}`} inputMode="decimal" value={ln.unit_cost} onChange={(e) => updateEditLine(i, 'unit_cost', e.target.value)} placeholder="0,00" />
                </div>
                <button type="button" className="btn btn-mini btn-ghost" onClick={() => removeEditLine(i)} aria-label="Ta bort rad">Ta bort</button>
              </div>
            ))}
            <button type="button" className="btn btn-mini" onClick={addEditLine}>+ Lägg till rad</button>
          </div>
          <span className="row-actions">
            <button type="submit" className="btn btn-primary" disabled={editSaving}>{editSaving ? 'Sparar…' : 'Spara ändringar'}</button>
            <button type="button" className="btn btn-ghost" onClick={stopEdit}>Avbryt redigering</button>
          </span>
        </form>
      )}

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
