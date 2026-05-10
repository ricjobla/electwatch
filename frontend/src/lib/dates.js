import { differenceInCalendarDays, format, parseISO } from 'date-fns'

/** Force-parse an `'YYYY-MM-DD'` ISO string into a Date in local time. */
export function parseElectionDate(iso) {
  if (!iso) return null
  // The API returns plain calendar dates without TZ; parseISO treats those as UTC.
  // We want them to render as "the same day" regardless of viewer TZ, so we
  // normalize via the date-only segment.
  const [head] = String(iso).split('T')
  try {
    return parseISO(head)
  } catch {
    return null
  }
}

/**
 * Calendar days from today (local) to ``iso``. Positive = future, 0 = today,
 * negative = past. Returns null if the input doesn't parse.
 */
export function daysUntil(iso) {
  const d = parseElectionDate(iso)
  if (!d) return null
  return differenceInCalendarDays(d, new Date())
}

/** Long-form display: "Mon, 24 May 2026" — locale-stable for the dashboard. */
export function formatLongDate(iso) {
  const d = parseElectionDate(iso)
  if (!d) return '—'
  return format(d, 'EEE, d MMM yyyy')
}

/** Short stamp for cards: "24 May 2026". */
export function formatShortDate(iso) {
  const d = parseElectionDate(iso)
  if (!d) return '—'
  return format(d, 'd MMM yyyy')
}

/**
 * Human-friendly countdown string.
 *
 * - "Today"
 * - "Tomorrow" / "Yesterday"
 * - "in 5 days" / "5 days ago"
 * - "in 3 weeks" / "in 4 months"
 */
export function countdownLabel(iso) {
  const d = daysUntil(iso)
  if (d === null) return '—'
  if (d === 0) return 'Today'
  if (d === 1) return 'Tomorrow'
  if (d === -1) return 'Yesterday'
  const abs = Math.abs(d)
  let unit = `${abs} days`
  if (abs >= 365) unit = `${Math.round(abs / 365)} year${abs >= 730 ? 's' : ''}`
  else if (abs >= 30) unit = `${Math.round(abs / 30)} month${abs >= 60 ? 's' : ''}`
  else if (abs >= 14) unit = `${Math.round(abs / 7)} weeks`
  return d > 0 ? `in ${unit}` : `${unit} ago`
}
