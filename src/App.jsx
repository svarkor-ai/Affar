import { useEffect, useState } from 'react'
import { useAuth } from './auth.context.jsx'
import Layout from './components/Layout.jsx'
import Login from './views/Login.jsx'
import Track from './views/Track.jsx'
import Orders from './views/Orders.jsx'
import Invoices from './views/Invoices.jsx'
import Payments from './views/Payments.jsx'
import Items from './views/Items.jsx'
import Customers from './views/Customers.jsx'
import Suppliers from './views/Suppliers.jsx'
import Purchase from './views/Purchase.jsx'

// Map a route key -> { view, cap } (cap null = always reachable when
// authed; gated view pushes to a fallback if the user lacks the cap).
const ROUTES = {
  '': { view: Home, cap: null },
  track: { view: Track, cap: null },
  orders: { view: Orders, cap: 'orders' },
  invoices: { view: Invoices, cap: 'invoices' },
  payments: { view: Payments, cap: 'payments' },
  items: { view: Items, cap: 'items' },
  customers: { view: Customers, cap: 'customers' },
  suppliers: { view: Suppliers, cap: 'suppliers' },
  purchase: { view: Purchase, cap: 'purchase' },
}

function Home() {
  const { user, roleLabel } = useAuth()
  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Välkommen, {user?.username}</h2>
          <p>Roll: {roleLabel}. Använd menyn ovan.</p>
        </div>
      </div>
      <div className="card">
        <p>
          Affär är ett komplett affärssystem: order → faktura → betalning,
          leveransspårning och inköp. Vilka moduler du ser beror på din roll.
        </p>
      </div>
    </div>
  )
}

function useHash() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onHash = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return hash
}

function AuthedApp() {
  const { status, can } = useAuth()

  const seg = useHash().replace(/^#\//, '').split('/')[0]
  const route = ROUTES[seg] || ROUTES['']
  const View = route.view

  // Direct-URL guard: hide the view when the user lacks the capability.
  if (route.cap && !can(route.cap)) {
    return (
      <Layout>
        <div className="page-header">
          <h2>Ingen åtkomst</h2>
          <p className="muted">Du saknar behörighet för den här vyn.</p>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <View key={seg} />
    </Layout>
  )
}

export default function App() {
  const { status } = useAuth()
  if (status === 'loading') {
    return <div className="loading-screen"><div className="loading" role="status">Läser in…</div></div>
  }
  if (status === 'anonymous') {
    return <Login />
  }
  return <AuthedApp />
}
