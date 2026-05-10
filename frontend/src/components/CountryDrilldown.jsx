import { Link } from 'react-router-dom'

import { useCountryElections } from '../hooks/useCountryElections'
import { countdownLabel, formatLongDate } from '../lib/dates'
import { flagEmoji } from '../lib/flagEmoji'

/**
 * Overlay summary for one country. Shown when the user clicks a country
 * on the WorldMap; deep-links to the full country page.
 *
 * Fetches a 2-year window centered on today and splits into upcoming /
 * recent. Dismiss via the close button or by clicking another country.
 */
export default function CountryDrilldown({ isoCode, onClose }) {
  const fromIso = useToWindow(-1)
  const toIso = useToWindow(2)
  const { data, isLoading, error } = useCountryElections(isoCode, {
    from: fromIso,
    to: toIso,
    limit: 200,
  })

  if (!isoCode) return null

  const elections = data?.elections ?? []
  const todayIso = new Date().toISOString().slice(0, 10)
  const upcoming = elections
    .filter((e) => e.election_date >= todayIso)
    .slice(0, 3)
  const recent = elections
    .filter((e) => e.election_date < todayIso)
    .slice(-3)
    .reverse()

  return (
    <aside
      aria-label={`Country detail for ${isoCode}`}
      className="rounded-lg border border-slate-800 bg-slate-900/80 p-4 backdrop-blur"
    >
      <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            <span aria-hidden="true">{flagEmoji(isoCode)}</span>
            <span>{isoCode}</span>
          </div>
          <h3 className="mt-1 truncate font-serif text-lg text-slate-100">
            {elections[0]?.country_name || isoCode}
          </h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-700 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-400 hover:bg-slate-800"
          aria-label="Close country panel"
        >
          ✕
        </button>
      </div>

      {isLoading && (
        <p className="py-4 font-mono text-xs text-slate-500">Loading…</p>
      )}
      {error && (
        <p className="py-4 font-mono text-xs text-red-400">
          {String(error.message)}
        </p>
      )}

      {!isLoading && !error && (
        <>
          <Section title="Upcoming">
            {upcoming.length === 0 ? (
              <p className="font-mono text-xs text-slate-500">
                None tracked.
              </p>
            ) : (
              <ul className="space-y-2">
                {upcoming.map((e) => (
                  <ElectionRow key={e.id} election={e} />
                ))}
              </ul>
            )}
          </Section>

          <Section title="Recent">
            {recent.length === 0 ? (
              <p className="font-mono text-xs text-slate-500">
                None in the last 12 months.
              </p>
            ) : (
              <ul className="space-y-2">
                {recent.map((e) => (
                  <ElectionRow key={e.id} election={e} muted />
                ))}
              </ul>
            )}
          </Section>

          <div className="mt-4 border-t border-slate-800 pt-3">
            <Link
              to={`/country/${encodeURIComponent(isoCode)}`}
              className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800/60 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-slate-200 hover:bg-slate-700"
            >
              Full country page →
            </Link>
          </div>
        </>
      )}
    </aside>
  )
}

function Section({ title, children }) {
  return (
    <div className="mt-3">
      <h4 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
        {title}
      </h4>
      {children}
    </div>
  )
}

function ElectionRow({ election, muted = false }) {
  return (
    <li
      className={`rounded border border-slate-800 ${
        muted ? 'bg-slate-950/60' : 'bg-slate-950/80'
      } px-3 py-2`}
    >
      <Link
        to={`/election/${encodeURIComponent(election.id)}`}
        className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
      >
        <div className="flex items-baseline justify-between gap-2 text-sm">
          <div className="min-w-0 truncate font-medium text-slate-100">
            {election.title}
          </div>
          <div className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            {election.status}
          </div>
        </div>
        <div className="mt-0.5 flex justify-between font-mono text-[11px] text-slate-500">
          <span>{formatLongDate(election.election_date)}</span>
          <span className="tabular-nums">
            {countdownLabel(election.election_date)}
          </span>
        </div>
      </Link>
    </li>
  )
}

function useToWindow(yearsOffset) {
  const d = new Date()
  d.setFullYear(d.getFullYear() + yearsOffset)
  return d.toISOString().slice(0, 10)
}
