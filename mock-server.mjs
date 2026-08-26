// Minimal mock API + static server to exercise the frontend in the
// browser against representative payloads (contract C24/C25 shapes).
// NOT part of the deliverable — a dev aid used to vision-check the UI.
import { createServer } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { join, extname } from 'node:path'

const DIST = '/home/nicke/affar-frontend/dist'
const PORT = process.env.PORT || 4173

const ROLES = ['admin', 'sales', 'finance', 'procurement', 'customer']
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' }

const now = () => new Date().toISOString()

function json(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(obj))
}

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`)
  const p = url.pathname

  // ---- API handlers ----
  if (p === '/api/auth/login' && req.method === 'POST') {
    let body = ''
    req.on('data', (c) => (body += c))
    req.on('end', () => {
      let b = {}
      try { b = JSON.parse(body) } catch {}
      const username = b.username || ''
      if (!ROLES.includes(username)) {
        return json(res, 401, { detail: 'Ogiltiga uppgifter.' })
      }
      return json(res, 200, {
        access_token: 'mock.' + Buffer.from(username).toString('base64url'),
        user: { id: 1, username, role: username, email: username + '@affar.demo' },
      })
    })
    return
  }

  if (p === '/api/auth/me' && req.method === 'GET') {
    const h = req.headers.authorization || ''
    const token = h.replace('Bearer ', '')
    let username = ''
    if (token.startsWith('mock.')) {
      try { username = Buffer.from(token.slice(5), 'base64url').toString('utf8') } catch {}
    }
    if (!username || !ROLES.includes(username)) return json(res, 401, { detail: 'Ej autentiserad.' })
    return json(res, 200, { id: 1, username, role: username, email: username + '@affar.demo' })
  }

  if (p === '/api/orders' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, customer_id: 1, status: 'confirmed', total: '2499.00', created_at: now() },
      { id: 2, customer_id: 2, status: 'shipped', total: '345.50', created_at: now() },
      { id: 3, customer_id: 1, status: 'delivered', total: '12899.00', created_at: now(), tracking_id: 'a1b2c3d4e5f6a7b8c9d0e1f2' },
    ])
  }
  if (p === '/api/items' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, sku: 'SKU-100', name: 'Mekaniskt tangentbord', unit_price: '899.00', qty_on_hand: 24, active: true },
      { id: 2, sku: 'SKU-200', name: '27″ bildskärm', unit_price: '2499.00', qty_on_hand: 8, active: true },
    ])
  }
  if (p === '/api/customers' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, name: 'Nordkabel AB', email: 'order@nordkabel.se', phone: '070-111 22 33', org_no: '556600-1234' },
      { id: 2, name: 'Hem & Fritid', email: 'info@hemfritid.se', phone: '08-555 44 33', org_no: null },
    ])
  }
  if (p === '/api/suppliers' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, name: 'Teknikimporten', contact: 'Anna Li', email: 'anna@teknikimporten.se', phone: '031-123 45' },
    ])
  }
  if (p === '/api/invoices' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, order_id: 1, status: 'issued', total: '2499.00', due_date: '2026-09-24' },
      { id: 2, order_id: 2, status: 'paid', total: '345.50', due_date: '2026-09-15', payments: [{ id: 1, amount: '345.50', method: 'bank' }] },
    ])
  }
  if (p === '/api/payments' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, invoice_id: 2, method: 'bank', amount: '345.50', created_at: now() },
    ])
  }
  if (p === '/api/purchase-orders' && req.method === 'GET') {
    return json(res, 200, [
      { id: 1, supplier_id: 1, status: 'ordered', total: '5800.00' },
    ])
  }

  // tracking: public GET /api/tracking/{tracking_id} only (C21 rev-2) — no
  // staff note/carrier surface to mirror, so the mock returns just the public shape.
  const trackMatch = p.match(/^\/api\/tracking\/([^/]+)$/)
  if (trackMatch && req.method === 'GET') {
    const id = trackMatch[1]
    const events = [
      { status: 'placed', at: now() },
      { status: 'in-warehouse', at: now() },
      { status: 'in-transit', at: now() },
    ]
    const current = 'in-transit'
    return json(res, 200, { tracking_id: id, status: current, events })
  }

  // ---- static SPA ----
  const want = p === '/' ? '/index.html' : p
  const file = join(DIST, want)
  if (existsSync(file) && !existsSync(file).valueOf === false) {
    const data = readFileSync(file)
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' })
    res.end(data)
    return
  }
  // SPA fallback
  const idx = readFileSync(join(DIST, 'index.html'))
  res.writeHead(200, { 'Content-Type': 'text/html' })
  res.end(idx)
})

server.listen(PORT, () => console.log(`mock+static on :${PORT}`))
