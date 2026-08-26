// Reusable status badge. `kind` maps a status value to a badge
// colour class so the CSS stays declarative (see styles.css).
const KIND_CLASS = {
  // order
  draft: 'badge-draft',
  confirmed: 'badge-confirmed',
  shipped: 'badge-shipped',
  delivered: 'badge-delivered',
  // invoice
  issued: 'badge-issued',
  paid: 'badge-paid',
  // purchase
  ordered: 'badge-ordered',
  received: 'badge-received',
  // tracking
  placed: 'badge-placed',
  'in-warehouse': 'badge-in-warehouse',
  'in-transit': 'badge-in-transit',
  'out-for-delivery': 'badge-out-for-delivery',
}

export default function StatusBadge({ status }) {
  const cls = KIND_CLASS[status] || 'badge-draft'
  const label = status
    ? status.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase())
    : '—'
  return <span className={`badge ${cls}`}>{label}</span>
}
