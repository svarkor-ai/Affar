// Read-only DECIMAL money display (C25). The backend owns all
// money values (Decimal 12,2); this component only FORMATS what it
// is given — it never performs arithmetic and never fabricates a
// value. Swedish locale formatting (kr).
export default function Money({ value, currency = 'kr' }) {
  if (value === null || value === undefined || value === '') {
    return <span className="muted">—</span>
  }
  const num = Number(value)
  if (Number.isNaN(num)) {
    // Never guess at an unparsable wire value — show it untouched.
    return <span>{String(value)}</span>
  }
  const formatted = new Intl.NumberFormat('sv-SE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
  return (
    <span className="num">
      {formatted}&nbsp;{currency}
    </span>
  )
}
