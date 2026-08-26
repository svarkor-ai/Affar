// ============================================================
// Affär — typed fetch client (contract C24).
// One function per backend contract. Everything except `track()`
// (the single public lookup) sends `Authorization: Bearer <token>`.
//
// The backend is the authority on money/roles (C23/C25). This
// client is presentational: it sends plain strings/numbers and
// lets the server normalize DECIMAL + gate roles. It never
// renders user data it was not asked to show.
// ============================================================

const BASE = '/api'

async function request(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' }
  if (token) headers['Authorization'] = 'Bearer ' + token
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    throw new Error('Kunde inte nå servern. Kontrollera anslutningen och försök igen.')
  }

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  if (!res.ok) {
    const detail = data && data.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join('; ')
          : (detail && detail.message) || 'Förfrågan misslyckades (' + res.status + ').'
    throw new Error(msg)
  }
  return data
}

// ---------- auth (C6) ----------
export async function login(username, password) {
  const data = await request('/auth/login', { method: 'POST', body: { username, password } })
  return data // { access_token, user }
}
export function me(token) {
  return request('/auth/me', { token })
}

// ---------- items / catalog (C8) ----------
export function listItems(token, { active = 1 } = {}) {
  return request('/items?active=' + active, { token })
}
export function getItem(token, id) { return request('/items/' + id, { token }) }
export function createItem(token, item) { return request('/items', { token, method: 'POST', body: item }) }
export function updateItem(token, id, item) { return request('/items/' + id, { token, method: 'PUT', body: item }) }

// ---------- customers (C10) ----------
export function listCustomers(token) { return request('/customers', { token }) }
export function getCustomer(token, id) { return request('/customers/' + id, { token }) }
export function createCustomer(token, customer) { return request('/customers', { token, method: 'POST', body: customer }) }
export function updateCustomer(token, id, customer) { return request('/customers/' + id, { token, method: 'PUT', body: customer }) }

// ---------- suppliers (C12) ----------
export function listSuppliers(token) { return request('/suppliers', { token }) }
export function getSupplier(token, id) { return request('/suppliers/' + id, { token }) }
export function createSupplier(token, supplier) { return request('/suppliers', { token, method: 'POST', body: supplier }) }
export function updateSupplier(token, id, supplier) { return request('/suppliers/' + id, { token, method: 'PUT', body: supplier }) }

// ---------- orders (C14) — OrderIn carries NO price (server derives) ----------
export function createOrder(token, orderIn) { return request('/orders', { token, method: 'POST', body: orderIn }) }
export function listOrders(token) { return request('/orders', { token }) }
export function getOrder(token, id) { return request('/orders/' + id, { token }) }
// The ONLY order lifecycle transition the backend exposes is draft ->
// confirmed via POST /orders/{id}/confirm (C14 rev-2). There is no
// shipped/delivered transition endpoint — orders are matched to an
// invoice, and delivery tracking is recorded elsewhere (teddy's card).
export function confirmOrder(token, id) { return request('/orders/' + id + '/confirm', { token, method: 'POST' }) }

// ---------- invoicing (C16) ----------
export function createInvoiceFromOrder(token, orderId) { return request('/orders/' + orderId + '/invoice', { token, method: 'POST' }) }
export function listInvoices(token) { return request('/invoices', { token }) }
export function getInvoice(token, id) { return request('/invoices/' + id, { token }) }
export function setInvoiceStatus(token, id, status) { return request('/invoices/' + id + '/status', { token, method: 'PATCH', body: { status } }) }

// ---------- payments (C17) ----------
export function recordPayment(token, invoiceId, paymentIn) { return request('/invoices/' + invoiceId + '/payment', { token, method: 'POST', body: paymentIn }) }
export function reconcile(token, invoiceId) { return request('/invoices/' + invoiceId + '/reconcile', { token, method: 'POST' }) }
export function listPayments(token) { return request('/payments', { token }) }

// ---------- purchase (C19) ----------
export function createPurchaseOrder(token, poIn) { return request('/purchase-orders', { token, method: 'POST', body: poIn }) }
export function listPurchaseOrders(token) { return request('/purchase-orders', { token }) }
export function getPurchaseOrder(token, id) { return request('/purchase-orders/' + id, { token }) }
export function setPurchaseStatus(token, id, status) { return request('/purchase-orders/' + id + '/status', { token, method: 'PATCH', body: { status } }) }

// ---------- tracking (C21 rev-2 / C20) ----------
// The ONLY tracking route is the public GET /api/tracking/{tracking_id}.
// The backend exposes no create-delivery-track and no staff track surface.
export function track(trackingId) { return request('/tracking/' + trackingId) }
