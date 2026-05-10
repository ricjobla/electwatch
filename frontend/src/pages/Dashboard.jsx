import { useMemo, useState } from 'react'

import CountryDrilldown from '../components/CountryDrilldown'
import ElectionCard from '../components/ElectionCard'
import WorldMap from '../components/WorldMap'
import { useCalendar } from '../hooks/useCalendar'
import { useElectionTypes } from '../hooks/useElectionTypes'
import { mergeElectionTypes } from '../lib/electionTypes'

function isoToday(yearOffset = 0) {
  const d = new Date()
  d.setFullYear(d.getFullYear() + yearOffset)
  return d.toISOString().slice(0, 10)
}

/**
 * Compute ISO2 -> next-upcoming-election-date from a calendar response.
 *
 * Used to feed WorldMap's color scale. We pick the earliest future date per
 * country (today inclusive); if none, fall back to the most recent past
 * date so the country still gets a "tracked" tone.
 */
function nextElectionByCountry(elections) {
  const todayIso = isoToday(0)
  const next = {}
  const last = {}
  for (const e of elections || []) {
    const iso = (e.country_id || '').toUpperCase()
    if (!iso) continue
    if (e.election_date >= todayIso) {
      if (!next[iso] || e.election_date < next[iso]) next[iso] = e.election_date
    } else if (!last[iso] || e.election_date > last[iso]) {
      last[iso] = e.election_date
    }
  }
  return { ...last, ...next }
}

export default function Dashboard() {
  const [from, setFrom] = useState(() => isoToday(-1))
  const [to, setTo] = useState(() => isoToday(2))
  const [status, setStatus] = useState('')
  const [type, setType] = useState('')
  const [selectedIso, setSelectedIso] = useState(null)

  const params = useMemo(
    () => ({
      from,
      to,
      ...(status ? { status } : {}),
      ...(type ? { type } : {}),
      region: 'europe',
      limit: 1500,
    }),
    [from, to, status, type],
  )

  const { data, isLoading, error, refetch, isFetching } = useCalendar(params)
  const elections = useMemo(() => data?.elections ?? [], [data])

  const { data: typeOptions = [] } = useElectionTypes()

  const nextByIso = useMemo(
    () => nextElectionByCountry(elections),
    [elections],
  )
  const mergedTypeOptions = useMemo(
    () => mergeElectionTypes(typeOptions),
    [typeOptions],
  )

  return (
    <section className="space-y-6">
      <header className="border-b border-slate-800 pb-4">
        <h2 className="font-serif text-2xl tracking-tight text-slate-50">
          Dashboard
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Hover the map for country detail, click a country to pin it. Cards
          below show the full filtered calendar — click any card to drill into
          results.
        </p>
      </header>

      <Filters
        from={from}
        to={to}
        status={status}
        type={type}
        typeOptions={mergedTypeOptions}
        onChangeFrom={setFrom}
        onChangeTo={setTo}
        onChangeStatus={setStatus}
        onChangeType={setType}
        onRefresh={() => refetch()}
        loading={isFetching}
      />

      <div className="relative">
        <WorldMap
          nextElectionByCountry={nextByIso}
          onCountryClick={setSelectedIso}
          selectedIso2={selectedIso}
          className="h-[68vh] min-h-[520px]"
        />
        {selectedIso && (
          <div className="absolute top-3 right-3 z-20 max-h-[calc(100%-1.5rem)] w-[360px] overflow-y-auto shadow-2xl">
            <CountryDrilldown
              isoCode={selectedIso}
              onClose={() => setSelectedIso(null)}
            />
          </div>
        )}
      </div>

      {isLoading && (
        <p className="font-mono text-sm text-slate-500">Loading calendar…</p>
      )}
      {error && (
        <div className="rounded border border-red-900/60 bg-red-950/30 px-4 py-3 font-mono text-sm text-red-300">
          <p className="font-semibold">Could not reach API</p>
          <p className="mt-1 text-red-400/90">{String(error.message)}</p>
        </div>
      )}

      {!isLoading && !error && elections.length === 0 && (
        <EmptyState />
      )}

      {elections.length > 0 && (
        <CalendarGrid
          elections={elections}
          isFetching={isFetching && !isLoading}
        />
      )}
    </section>
  )
}

function Filters({
  from,
  to,
  status,
  type,
  typeOptions,
  onChangeFrom,
  onChangeTo,
  onChangeStatus,
  onChangeType,
  onRefresh,
  loading,
}) {
  return (
    <div className="grid grid-cols-2 gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4 sm:grid-cols-4 lg:flex lg:flex-wrap lg:items-end lg:gap-4">
      <FilterField label="From">
        <input
          type="date"
          value={from}
          onChange={(e) => onChangeFrom(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
        />
      </FilterField>
      <FilterField label="To">
        <input
          type="date"
          value={to}
          onChange={(e) => onChangeTo(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
        />
      </FilterField>
      <FilterField label="Status">
        <select
          value={status}
          onChange={(e) => onChangeStatus(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
        >
          <option value="">All</option>
          <option value="upcoming">Upcoming</option>
          <option value="live">Live</option>
          <option value="complete">Complete</option>
        </select>
      </FilterField>
      <FilterField label="Type">
        <select
          value={type}
          onChange={(e) => onChangeType(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-sans text-sm text-slate-200 outline-none focus:border-slate-500"
        >
          <option value="">Any</option>
          {typeOptions.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </FilterField>
      <div className="col-span-2 flex sm:col-span-4 lg:col-auto lg:ml-auto">
        <button
          type="button"
          onClick={onRefresh}
          className="ml-auto rounded border border-slate-600 bg-slate-800/80 px-3 py-2 font-mono text-xs uppercase tracking-wider text-slate-200 hover:bg-slate-700"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}

function FilterField({ label, children }) {
  return (
    <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
      {label}
      {children}
    </label>
  )
}

function CalendarGrid({ elections, isFetching }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-slate-500">
        <span>{elections.length} elections</span>
        {isFetching && <span className="text-slate-600">Updating…</span>}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {elections.map((e) => (
          <ElectionCard key={e.id} election={e} />
        ))}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
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
  )
}
