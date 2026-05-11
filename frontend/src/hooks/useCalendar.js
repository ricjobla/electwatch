import { useQuery } from '@tanstack/react-query'

import { calendarQuery, fetchJson } from '../lib/api'

export function useCalendar(params, queryOptions = {}) {
  return useQuery({
    queryKey: ['calendar', params],
    queryFn: () => fetchJson(calendarQuery(params)),
    ...queryOptions,
  })
}
