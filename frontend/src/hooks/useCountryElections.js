import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '../lib/api'

/**
 * Fetch elections for one country. ``isoCode`` may be null/empty (in which
 * case the query is disabled).
 *
 * @param {string|null} isoCode
 * @param {{ from?: string, to?: string, limit?: number }} [params]
 */
export function useCountryElections(isoCode, params = {}) {
  const enabled = Boolean(isoCode && /^[A-Za-z]{2}$/.test(isoCode))
  const sp = new URLSearchParams()
  if (params.from) sp.set('from', params.from)
  if (params.to) sp.set('to', params.to)
  if (params.limit) sp.set('limit', String(params.limit))
  const path = `/api/countries/${encodeURIComponent(
    String(isoCode || '').toUpperCase(),
  )}/elections${sp.toString() ? `?${sp.toString()}` : ''}`
  return useQuery({
    enabled,
    queryKey: ['countryElections', isoCode, params],
    queryFn: () => fetchJson(path),
  })
}
