// Accessible, state-complete table wrapper (C25).
// Handles the four states every view needs: loading, empty, error,
// success. `columns` = [{key, label, align:'num'|null, render(row)}].
// Optional `actions` column via a render prop returning React nodes.
export default function DataTable({
  columns,
  rows,
  loading,
  error,
  emptyText = 'Inga rader.',
  keyOf = (r) => r.id,
  actions,
  ariaLabel,
}) {
  if (loading) {
    return <p className="loading" role="status">Läser in…</p>
  }
  if (error) {
    return <p className="notice-error" role="alert">{error}</p>
  }
  if (!rows || rows.length === 0) {
    return <p className="empty">{emptyText}</p>
  }

  return (
    <div className="table-wrap">
      <table className="data" aria-label={ariaLabel}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.align === 'num' ? 'num' : ''}>{c.label}</th>
            ))}
            {actions ? <th className="num">Åtgärder</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={keyOf(row)}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === 'num' ? 'num' : ''}>
                  {c.render ? c.render(row, row[c.key]) : row[c.key]}
                </td>
              ))}
              {actions ? <td className="num">{actions(row)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
