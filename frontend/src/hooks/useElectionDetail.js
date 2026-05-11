import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '../lib/api'

export function useElectionDetail(electionId) {
  return useQuery({
    queryKey: ['election', electionId],
    queryFn: () =>
      fetchJson(`/api/elections/${encodeURIComponent(electionId)}`),
    enabled: Boolean(electionId),
    refetchInterval: (query) =>
      query.state.data?.status === 'live' ? 60_000 : false,
  })
}
