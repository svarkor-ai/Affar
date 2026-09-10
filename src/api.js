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

// MC 707.2 G2 — prefix-säker BASE. Baked "/api" would resolve to the site
// root and miss the /affar/ prefix behind the public reverse proxy. A base
// with no leading slash resolves against the CURRENT PAGE URL (e.g.
// sibbamala.com/affar/ + "api/..." = sibbamala.com/affar/api/...), so the
// SPA never requests anything outside its own prefix. Hash routes (#/...) do
// not affect the base. Tests override window.location for path-accuracy.
const BASE = 'api'

function apiUrl(path) {
  const base = (typeof window !== 'undefined' && window.location
    ? window.location.href
    : 'file:///')
  return new URL(BASE + path, base).href
}

async function request(path, { token, method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' }
  if (token) headers['Authorization'] = 'Bearer ' + token
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(apiUrl(path), {
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
// MC 1175.5 — avaktivering (flaggan heter `active` på C8-ytan, ActivePatch på wire)
export function setItemActive(token, id, is_active) { return request('/items/' + id + '/active', { token, method: 'PATCH', body: { is_active } }) }

// ---------- customers (C10) ----------
export function listCustomers(token) { return request('/customers', { token }) }
export function getCustomer(token, id) { return request('/customers/' + id, { token }) }
export function createCustomer(token, customer) { return request('/customers', { token, method: 'POST', body: customer }) }
export function updateCustomer(token, id, customer) { return request('/customers/' + id, { token, method: 'PUT', body: customer }) }
// MC 1175.5 — avaktivering (ny order till avaktiverad kund -> 410)
export function setCustomerActive(token, id, is_active) { return request('/customers/' + id + '/active', { token, method: 'PATCH', body: { is_active } }) }

// ---------- suppliers (C12) ----------
export function listSuppliers(token) { return request('/suppliers', { token }) }
export function getSupplier(token, id) { return request('/suppliers/' + id, { token }) }
export function createSupplier(token, supplier) { return request('/suppliers', { token, method: 'POST', body: supplier }) }
export function updateSupplier(token, id, supplier) { return request('/suppliers/' + id, { token, method: 'PUT', body: supplier }) }
// MC 1175.5 — avaktivering (ny PO till avaktiverad leverantör -> 410)
export function setSupplierActive(token, id, is_active) { return request('/suppliers/' + id + '/active', { token, method: 'PATCH', body: { is_active } }) }

// ---------- orders (C14) — OrderIn carries NO price (server derives) ----------
export function createOrder(token, orderIn) { return request('/orders', { token, method: 'POST', body: orderIn }) }
export function listOrders(token) { return request('/orders', { token }) }
export function getOrder(token, id) { return request('/orders/' + id, { token }) }
// The ONLY order lifecycle transition the backend exposes is draft ->
// confirmed via POST /orders/{id}/confirm (C14 rev-2). There is no
// shipped/delivered transition endpoint — orders are matched to an
// invoice, and delivery tracking is recorded elsewhere (teddy's card).
export function confirmOrder(token, id) { return request('/orders/' + id + '/confirm', { token, method: 'POST' }) }
// MC 1175.1 — draft edits. Replace the whole line set (remove/add/change qty,
// {item_id, qty} only — the server re-snapshots prices, C14) and cancel a
// draft. Both are draft-only server-side (409/410 otherwise) and [admin,sales].
export function updateOrderLines(token, id, lines) { return request('/orders/' + id, { token, method: 'PATCH', body: { lines } }) }
export function cancelOrder(token, id) { return request('/orders/' + id + '/status', { token, method: 'PATCH', body: { status: 'cancel' } }) }

// ---------- invoicing (C16) ----------
export function createInvoiceFromOrder(token, orderId) { return request('/orders/' + orderId + '/invoice', { token, method: 'POST' }) }
export function listInvoices(token) { return request('/invoices', { token }) }
export function getInvoice(token, id) { return request('/invoices/' + id, { token }) }
// MC 1175.2 — invoice rättning + makulering. Replace the whole line set
// ({item_id?, description?, qty} only — prices stay server-owned, C14); only a
// draft/issued invoice is editable server-side (paid -> 409, cancelled -> 410).
// Makulering goes through the status patch with "cancel" and requires the
// invoice to be fully refunded first (net payments == 0).
export function updateInvoiceLines(token, id, lines) { return request('/invoices/' + id, { token, method: 'PATCH', body: { lines } }) }
export function cancelInvoice(token, id) { return request('/invoices/' + id + '/status', { token, method: 'PATCH', body: { status: 'cancel' } }) }
export function setInvoiceStatus(token, id, status) { return request('/invoices/' + id + '/status', { token, method: 'PATCH', body: { status } }) }

// ---------- payments (C17) ----------
export function recordPayment(token, invoiceId, paymentIn) { return request('/invoices/' + invoiceId + '/payment', { token, method: 'POST', body: paymentIn }) }
export function reconcile(token, invoiceId) { return request('/invoices/' + invoiceId + '/reconcile', { token, method: 'POST' }) }
export function listPayments(token) { return request('/payments', { token }) }
// MC 1175.3 — makulering av felaktig betalning. Append-only: servern lägger
// en NEGATIV rad kopplad till originalet (cancels_payment_id), aldrig raderat.
export function cancelPayment(token, paymentId) { return request('/payments/' + paymentId + '/cancel', { token, method: 'POST' }) }

// ---------- purchase (C19) ----------
export function createPurchaseOrder(token, poIn) { return request('/purchase-orders', { token, method: 'POST', body: poIn }) }
export function listPurchaseOrders(token) { return request('/purchase-orders', { token }) }
export function getPurchaseOrder(token, id) { return request('/purchase-orders/' + id, { token }) }
export function setPurchaseStatus(token, id, status) { return request('/purchase-orders/' + id + '/status', { token, method: 'PATCH', body: { status } }) }
// MC 1175.4 — purchase rättbara. Replace the whole draft line set
// ({item_id, qty, unit_cost} — cost is wire-supplied purchase-side, C18; the
// server recomputes line_total). Only a draft is editable (ordered -> 409,
// cancelled -> 410). Makulering goes through the status patch with "cancel"
// (draft/ordered only; received is 409, cancelled terminal).
export function updatePurchaseOrderLines(token, id, lines) { return request('/purchase-orders/' + id, { token, method: 'PATCH', body: { lines } }) }
export function cancelPurchaseOrder(token, id) { return request('/purchase-orders/' + id + '/status', { token, method: 'PATCH', body: { status: 'cancel' } }) }

// ---------- tracking (C21 rev-2 / C20) ----------
// The ONLY tracking route is the public GET /api/tracking/{tracking_id}.
// The backend exposes no create-delivery-track and no staff track surface.
export function track(trackingId) { return request('/tracking/' + trackingId) }

// ---------- admin users (MC 1120.1) — admin-role only ----------
export function listAdminUsers(token) { return request('/admin/users', { token }) }
export function createAdminUser(token, user) { return request('/admin/users', { token, method: 'POST', body: user }) }
export function updateAdminUser(token, id, patch) { return request('/admin/users/' + id, { token, method: 'PATCH', body: patch }) }
