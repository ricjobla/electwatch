/**
 * API base: empty uses same-origin `/api` (Vite dev proxy or nginx → backend).
 * Override with `VITE_API_URL` when serving the SPA from a different origin.
 */
export function apiBase() {
  const base = import.meta.env.VITE_API_URL ?? ''
  return base.endsWith('/') ? base.slice(0, -1) : base
}

export async function fetchJson(path, options = {}) {
  const url = path.startsWith('http') ? path : `${apiBase()}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text.slice(0, 200)}` : ''}`)
  }
  return res.json()
}

/** @param {{ from?: string, to?: string, status?: string, region?: string, limit?: number }} params */
export function calendarQuery(params = {}) {
  const sp = new URLSearchParams()
  if (params.from) sp.set('from', params.from)
  if (params.to) sp.set('to', params.to)
  if (params.status) sp.set('status', params.status)
  if (params.region) sp.set('region', params.region)
  sp.set('limit', String(params.limit ?? 500))
  return `/api/calendar?${sp.toString()}`
}
