import { Link } from 'react-router-dom'

import { countdownLabel, daysUntil, formatLongDate } from '../lib/dates'
import { flagEmoji } from '../lib/flagEmoji'
import LiveBadge from './LiveBadge'

const STATUS_PILL = {
  upcoming: 'bg-emerald-950/70 text-emerald-300',
  live: 'bg-amber-950/70 text-amber-300',
  complete: 'bg-slate-800 text-slate-400',
}

const URGENCY_BORDER = (days, status) => {
  if (status === 'live') return 'border-amber-500/70'
  if (days === null || days < 0) return 'border-slate-800'
  if (days <= 14) return 'border-rose-600/80'
  if (days <= 30) return 'border-amber-500/70'
  if (days <= 90) return 'border-emerald-600/70'
  return 'border-slate-800'
}

/**
 * One election as a clickable card.
 *
 * Linkable: /election/:id. The whole card is the click surface; nested links
 * (country chip) prevent propagation so clicking the chip routes to the
 * country page instead.
 */
export default function ElectionCard({ election }) {
  if (!election) return null
  const days = daysUntil(election.election_date)
  const urgency = URGENCY_BORDER(days, election.status)
  const flag = flagEmoji(election.country_id)

  return (
    <Link
      to={`/election/${encodeURIComponent(election.id)}`}
      className={`group relative flex flex-col gap-3 rounded-lg border ${urgency} bg-slate-900/40 p-4 transition hover:bg-slate-900/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            <span aria-hidden="true">{flag}</span>
            {election.country_id ? (
              <Link
                to={`/country/${encodeURIComponent(election.country_id)}`}
                onClick={(e) => e.stopPropagation()}
                className="rounded px-1 hover:bg-slate-800 hover:text-slate-200"
              >
                {election.country_id}
              </Link>
            ) : null}
            {election.country_name ? (
              <span className="truncate text-slate-400 normal-case tracking-normal">
                {election.country_name}
              </span>
            ) : null}
          </div>
          <h3 className="mt-1 line-clamp-2 font-serif text-base font-medium leading-snug text-slate-100">
            {election.title}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <LiveBadge status={election.status} />
          <span
            className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${
              STATUS_PILL[election.status] ?? STATUS_PILL.complete
            }`}
          >
            {election.status}
          </span>
        </div>
      </div>

      <div className="flex items-end justify-between gap-3 border-t border-slate-800/80 pt-3 font-mono text-xs text-slate-500">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-600">
            Date
          </div>
          <div className="mt-0.5 text-slate-300">
            {formatLongDate(election.election_date)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-slate-600">
            Countdown
          </div>
          <div
            className={`mt-0.5 tabular-nums ${
              days !== null && days >= 0 && days <= 30
                ? 'text-rose-300'
                : 'text-slate-300'
            }`}
          >
            {countdownLabel(election.election_date)}
          </div>
        </div>
      </div>

      {election.type ? (
        <div className="absolute right-3 top-3 hidden font-mono text-[10px] uppercase tracking-wider text-slate-600 group-hover:block">
          {election.type}
        </div>
      ) : null}
    </Link>
  )
}
