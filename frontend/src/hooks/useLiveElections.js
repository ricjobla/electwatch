import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '../lib/api'

/**
 * Poll ``GET /api/live`` so the dashboard can tighten calendar refresh while
 * tallies are in progress.
 */
export function useLiveElections(queryOptions = {}) {
  return useQuery({
    queryKey: ['live'],
    queryFn: () => fetchJson('/api/live'),
    refetchInterval: (query) =>
      (query.state.data?.elections?.length ?? 0) > 0 ? 60_000 : false,
    ...queryOptions,
  })
}
