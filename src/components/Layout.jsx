import { useAuth } from '../auth.context.jsx'

// App shell: topbar (brand, who, logout) + role-gated nav + page.
// Nav items are gated on the same capability set as the backend
// routers (C4/C25) via `can()` from the auth context. `track` is the
// public lookup, always visible.
const NAV = [
  { key: 'track', label: 'Kundspårning', href: '#/track', cap: null },
  { key: 'orders', label: 'Order', href: '#/orders', cap: 'orders' },
  { key: 'invoices', label: 'Fakturor', href: '#/invoices', cap: 'invoices' },
  { key: 'payments', label: 'Betalningar', href: '#/payments', cap: 'payments' },
  { key: 'items', label: 'Artiklar', href: '#/items', cap: 'items' },
  { key: 'customers', label: 'Kunder', href: '#/customers', cap: 'customers' },
  { key: 'suppliers', label: 'Leverantörer', href: '#/suppliers', cap: 'suppliers' },
  { key: 'purchase', label: 'Inköp', href: '#/purchase', cap: 'purchase' },
]

function currentPath() {
  const m = window.location.hash.match(/^#\/([^/]+)/)
  return m ? m[1] : ''
}

export default function Layout({ children }) {
  const { user, roleLabel, logout, can } = useAuth()
  const active = currentPath()
  const items = NAV.filter((n) => n.cap === null || can(n.cap))

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">Affär</div>
        <div className="who">
          <span>{user?.username}</span>
          <span className="role-tag">{roleLabel}</span>
          <button type="button" className="logout" onClick={logout}>
            Logga ut
          </button>
        </div>
      </header>
      <nav className="nav" aria-label="Huvudmeny">
        {items.map((n) => (
          <a key={n.key} href={n.href} className={active === n.key || (n.key === 'track' && active === '') ? 'active' : ''}>
            {n.label}
          </a>
        ))}
      </nav>
      <main className="page">{children}</main>
    </div>
  )
}
