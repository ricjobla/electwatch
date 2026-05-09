import { Fragment, useMemo, useState } from 'react'

import { useCalendar } from '../hooks/useCalendar'
import { useElectionDetail } from '../hooks/useElectionDetail'

function fmtInputDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatDisplayDate(iso) {
  if (!iso) return '—'
  const [y, mo, da] = iso.split('-').map(Number)
  const d = new Date(y, mo - 1, da)
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function daysUntilElection(iso) {
  if (!iso) return null
  const [y, mo, da] = iso.split('-').map(Number)
  const target = new Date(y, mo - 1, da)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  const diff = Math.round((target - today) / 86400000)
  return diff
}

function ElectionResultsPanel({ electionId }) {
  const { data, isLoading, error } = useElectionDetail(electionId)

  if (isLoading) {
    return (
      <div className="border-t border-slate-800 bg-slate-950/80 px-4 py-3 font-mono text-xs text-slate-500">
        Loading results…
      </div>
    )
  }
  if (error) {
    return (
      <div className="border-t border-slate-800 bg-red-950/20 px-4 py-3 font-mono text-xs text-red-400">
        {String(error.message)}
      </div>
    )
  }
  if (!data?.results?.length) {
    return (
      <div className="border-t border-slate-800 bg-slate-950/80 px-4 py-3 font-mono text-xs text-slate-500">
        No party results stored for this election yet (run ParlGov ingest).
      </div>
    )
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950/80 px-4 py-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
        Results ({data.results.length})
      </div>
      <div className="max-h-56 overflow-auto rounded border border-slate-800">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 bg-slate-900 font-mono uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-2 py-1.5">Party</th>
              <th className="px-2 py-1.5 text-right">Votes %</th>
              <th className="px-2 py-1.5 text-right">Seats</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {data.results.map((r, i) => (
              <tr
                key={`${r.party_id ?? i}-${i}`}
                className="border-t border-slate-800/80"
              >
                <td className="px-2 py-1.5 font-medium">
                  <span
                    className="mr-2 inline-block h-2 w-2 rounded-sm align-middle"
                    style={{
                      backgroundColor: r.party_color_hex || '#64748b',
                    }}
                  />
                  {r.party_name ?? r.party_id ?? '—'}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {r.vote_share != null ? `${r.vote_share.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400">
                  {r.seats_won ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ElectionsDashboard() {
  const today = useMemo(() => new Date(), [])
  const defaultFrom = useMemo(() => {
    const d = new Date(today)
    d.setFullYear(d.getFullYear() - 2)
    return fmtInputDate(d)
  }, [today])
  const defaultTo = useMemo(() => {
    const d = new Date(today)
    d.setFullYear(d.getFullYear() + 2)
    return fmtInputDate(d)
  }, [today])

  const [from, setFrom] = useState(defaultFrom)
  const [to, setTo] = useState(defaultTo)
  const [status, setStatus] = useState('')
  const [region, setRegion] = useState('europe')

  const params = useMemo(
    () => ({
      from,
      to,
      ...(status ? { status } : {}),
      ...(region.trim() ? { region: region.trim() } : {}),
      limit: 750,
    }),
    [from, to, status, region],
  )

  const { data, isLoading, error, refetch, isFetching } = useCalendar(params)
  const elections = data?.elections ?? []

  const [expandedId, setExpandedId] = useState(null)

  const toggleRow = (id) => {
    setExpandedId((cur) => (cur === id ? null : id))
  }

  return (
    <section className="space-y-6">
      <header className="border-b border-slate-800 pb-4">
        <h2 className="font-serif text-2xl tracking-tight text-slate-50">
          Elections
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Calendar from <code className="text-slate-500">GET /api/calendar</code>.
          Expand a row for party results (
          <code className="text-slate-500">GET /api/elections/{'{id}'}</code>
          ). Seed historic data with ParlGov; upcoming 2026 rows with Wikidata
          ingest.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
          From
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
          />
        </label>
        <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
          To
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
          />
        </label>
        <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="min-w-[140px] rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
          >
            <option value="">All</option>
            <option value="upcoming">Upcoming</option>
            <option value="live">Live</option>
            <option value="complete">Complete</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
          Region contains
          <input
            type="text"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="europe"
            className="w-40 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-slate-500"
          />
        </label>
        <button
          type="button"
          onClick={() => refetch()}
          className="ml-auto rounded border border-slate-600 bg-slate-800/80 px-3 py-2 font-mono text-xs uppercase tracking-wider text-slate-200 hover:bg-slate-700"
        >
          Refresh
        </button>
      </div>

      {isLoading && (
        <p className="font-mono text-sm text-slate-500">Loading calendar…</p>
      )}
      {error && (
        <div className="rounded border border-red-900/60 bg-red-950/30 px-4 py-3 font-mono text-sm text-red-300">
          <p className="font-semibold">Could not reach API</p>
          <p className="mt-1 text-red-400/90">{String(error.message)}</p>
          <p className="mt-2 text-xs text-red-400/70">
            For local dev run backend on port 8000 and ensure Vite proxies `/api`.
          </p>
        </div>
      )}

      {!isLoading && !error && elections.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/30 px-6 py-10 text-center">
          <p className="font-serif text-lg text-slate-300">No elections in range</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Seed the database from{' '}
            <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
              backend/
            </code>
            :{' '}
            <code className="font-mono text-xs text-slate-400">
              python -m app.ingest.parlgov
            </code>{' '}
            and{' '}
            <code className="font-mono text-xs text-slate-400">
              python -m app.ingest.wikidata --year 2026
            </code>
            .
          </p>
        </div>
      )}

      {elections.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/50 px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            <span>{elections.length} elections</span>
            {isFetching && !isLoading && (
              <span className="text-slate-600">Updating…</span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead className="border-b border-slate-800 bg-slate-950 font-mono text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Country</th>
                  <th className="px-4 py-3">Election</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Δ days</th>
                </tr>
              </thead>
              <tbody className="text-slate-200">
                {elections.map((row) => {
                  const d = daysUntilElection(row.election_date)
                  const expanded = expandedId === row.id
                  return (
                    <Fragment key={row.id}>
                      <tr
                        className={`cursor-pointer border-t border-slate-800/90 hover:bg-slate-900/60 ${expanded ? 'bg-slate-900/40' : ''}`}
                        onClick={() => toggleRow(row.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            toggleRow(row.id)
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-expanded={expanded}
                      >
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">
                          {formatDisplayDate(row.election_date)}
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs text-slate-500">
                            {row.country_id ?? '—'}
                          </span>
                          <span className="ml-2 text-slate-300">
                            {row.country_name ?? ''}
                          </span>
                        </td>
                        <td className="max-w-md px-4 py-3 font-medium leading-snug text-slate-100">
                          {row.title}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${
                              row.status === 'upcoming'
                                ? 'bg-emerald-950/80 text-emerald-400'
                                : row.status === 'live'
                                  ? 'bg-amber-950/80 text-amber-400'
                                  : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-500">
                          {d === null ? '—' : d === 0 ? 'Today' : d > 0 ? `+${d}` : d}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="border-t border-slate-800 bg-slate-950/50">
                          <td colSpan={5} className="p-0">
                            <ElectionResultsPanel electionId={row.id} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
