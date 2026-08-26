import { useEffect, useState } from 'react'
import * as api from '../api.js'
import StatusBadge from '../components/StatusBadge.jsx'

// Public customer tracking view (C21/I5). Reachable at #/track and
// #/track/{tracking_id}. Uses the UNAUTHENTICATED lookup only — the
// response carries { tracking_id, status, events:[{status,at}] } and
// deliberately NO note and NO carrier (rev-3).
function formatWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat('sv-SE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

function TrackResult({ trackingId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setData(null)
    api
      .track(trackingId)
      .then((d) => {
        if (cancelled) return
        setData(d)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message || 'Kunde inte hämta spårningen.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [trackingId])

  if (loading) {
    return <p className="loading" role="status">Läser in spårning…</p>
  }
  if (error) {
    return (
      <div className="card">
        <p className="notice-error" role="alert">{error}</p>
        <p className="muted">
          Kontrollera att spårnings-id:t är rätt. Det står på kvittot eller i
          leveransbekräftelsen.
        </p>
      </div>
    )
  }
  if (!data) return null

  // Decide which timeline events are "done": the current status index.
  const order = ['placed', 'in-warehouse', 'in-transit', 'out-for-delivery', 'delivered']
  const currentIndex = order.indexOf(data.status)

  return (
    <div className="card">
      <div className="track-hero">
        <span className="tid">{data.tracking_id}</span>
        <h1>Leveransstatus: {data.status}</h1>
      </div>

      {data.events?.length ? (
        <ul className="timeline">
          {data.events.map((ev, i) => {
            const isDone = order.indexOf(ev.status) <= currentIndex
            return (
              <li key={i} className={isDone ? 'done' : ''}>
                <span className="dot" aria-hidden="true" />
                <div className="when">{formatWhen(ev.at)}</div>
                <div className="what">
                  <StatusBadge status={ev.status} />
                </div>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="empty">Inga spårningshändelser ännu.</p>
      )}
    </div>
  )
}

export default function Track() {
  const [input, setInput] = useState('')
  const [lookedUp, setLookedUp] = useState(null)

  // If navigated to #/track/{id}, start with that id.
  useEffect(() => {
    const m = window.location.hash.match(/^#\/track\/(.+)$/)
    if (m) {
      const id = decodeURIComponent(m[1])
      setInput(id)
      setLookedUp(id)
    }
  }, [])

  function onSubmit(e) {
    e.preventDefault()
    const id = input.trim()
    if (!id) return
    setLookedUp(id)
    // Update the hash so the result is deep-linkable.
    window.location.hash = `#/track/${encodeURIComponent(id)}`
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h2>Kundspårning</h2>
          <p>Följ din leverans med spårnings-id från kvittot.</p>
        </div>
      </div>

      <form className="card" onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor="tracking_id">Spårnings-id</label>
          <input
            id="tracking_id"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="t.ex. a1b2c3d4e5f6a7b8c9d0e1f2…"
            autoComplete="off"
          />
        </div>
        <button type="submit" className="btn btn-primary">Sök leverans</button>
      </form>

      {lookedUp ? <TrackResult key={lookedUp} trackingId={lookedUp} /> : null}
    </div>
  )
}
