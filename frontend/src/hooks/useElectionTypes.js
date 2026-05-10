import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '../lib/api'

/**
 * Distinct ``Election.type`` values from the backend; used to populate the
 * dashboard's election-type filter dropdown.
 *
 * Cached for 5 minutes — types change rarely (only when new ingest sources
 * arrive).
 */
export function useElectionTypes() {
  return useQuery({
    queryKey: ['electionTypes'],
    queryFn: () => fetchJson('/api/elections/types'),
    staleTime: 5 * 60 * 1000,
  })
}
