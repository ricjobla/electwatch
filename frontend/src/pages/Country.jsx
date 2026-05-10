import { Link, useParams } from 'react-router-dom'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useQueries } from '@tanstack/react-query'

import ElectionCard from '../components/ElectionCard'
import { useCountryElections } from '../hooks/useCountryElections'
import { fetchJson } from '../lib/api'
import { partyColor } from '../lib/partyColors'
import { flagEmoji } from '../lib/flagEmoji'

function isoYear(yearOffset) {
  const d = new Date()
  d.setFullYear(d.getFullYear() + yearOffset)
  return d.toISOString().slice(0, 10)
}

/**
 * Country detail page: header, elections grouped upcoming/historic,
 * historic-trend line chart of vote shares per top party.
 *
 * Uses the existing list endpoints; no additional backend calls.
 */
export default function Country() {
  const { iso = '' } = useParams()
  const isoUpper = iso.toUpperCase()

  const { data, isLoading, error } = useCountryElections(isoUpper, {
    from: isoYear(-30),
    to: isoYear(5),
    limit: 500,
  })
  const elections = data?.elections ?? []

  const todayIso = new Date().toISOString().slice(0, 10)
  const upcoming = elections.filter((e) => e.election_date >= todayIso)
  const historic = elections
    .filter((e) => e.election_date < todayIso)
    .slice()
    .reverse()

  // Pull vote-share details for each historic election so we can plot a trend.
  // Limit to the most recent 10 historic elections for a readable chart.
  const trendElections = historic.slice(0, 10).reverse()
  const trendQueries = useQueries({
    queries: trendElections.map((e) => ({
      queryKey: ['election', e.id],
      queryFn: () => fetchJson(`/api/elections/${encodeURIComponent(e.id)}`),
    })),
  })
  const allTrendsLoaded =
    trendQueries.length > 0 && trendQueries.every((q) => q.isSuccess)

  const trendData = allTrendsLoaded
    ? trendQueries.map((q, i) => ({
        election: trendElections[i],
        detail: q.data,
      }))
    : null

  const { rows, partyKeys, partyColors, partyLabels } =
    buildTrendSeries(trendData)

  const countryName =
    elections[0]?.country_name ||
    isoUpper

  return (
    <section className="space-y-8">
      <header className="border-b border-slate-800 pb-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
          <Link to="/" className="hover:text-slate-200">
            ← Dashboard
          </Link>
        </p>
        <div className="mt-2 flex items-center gap-3">
          <span aria-hidden="true" className="text-3xl">
            {flagEmoji(isoUpper)}
          </span>
          <div>
            <h2 className="font-serif text-3xl tracking-tight text-slate-50">
              {countryName}
            </h2>
            <p className="font-mono text-xs uppercase tracking-wider text-slate-500">
              {isoUpper}
            </p>
          </div>
        </div>
      </header>

      {isLoading && (
        <p className="font-mono text-sm text-slate-500">Loading…</p>
      )}
      {error && (
        <p className="font-mono text-sm text-red-400">{String(error.message)}</p>
      )}

      {!isLoading && !error && (
        <>
          <div>
            <h3 className="mb-3 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              Upcoming ({upcoming.length})
            </h3>
            {upcoming.length === 0 ? (
              <p className="font-mono text-xs text-slate-500">
                No upcoming elections tracked.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {upcoming.map((e) => (
                  <ElectionCard key={e.id} election={e} />
                ))}
              </div>
            )}
          </div>

          {trendData && rows.length > 1 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
                Historic vote-share trend (top {partyKeys.length} parties)
              </h3>
              <div className="mt-3" style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={rows}
                    margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
                  >
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="year"
                      stroke="#475569"
                      tick={{ fontSize: 11, fill: '#94a3b8' }}
                    />
                    <YAxis
                      stroke="#475569"
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 11, fill: '#94a3b8' }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(2,6,23,0.95)',
                        border: '1px solid rgb(51 65 85)',
                        borderRadius: 6,
                        color: '#e2e8f0',
                        fontSize: 12,
                      }}
                      formatter={(v) =>
                        typeof v === 'number' ? `${v.toFixed(1)}%` : v
                      }
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
                    />
                    {partyKeys.map((k) => (
                      <Line
                        key={k}
                        type="monotone"
                        dataKey={k}
                        name={partyLabels[k]}
                        stroke={partyColors[k]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-3 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              Historic ({historic.length})
            </h3>
            {historic.length === 0 ? (
              <p className="font-mono text-xs text-slate-500">
                No historic elections in this dataset.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {historic.map((e) => (
                  <ElectionCard key={e.id} election={e} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}

/**
 * Pivot detailed election results into a long-form table for the line chart.
 *
 * Returns:
 *   rows       — [{ year, [partyId]: voteShare, ... }, ...]
 *   partyKeys  — chart series ids (top-N by avg share across all elections)
 *   partyColors, partyLabels — display metadata keyed by partyKey
 *
 * Computation is cheap (≤ 10 elections × ~10 parties), so we recompute on
 * every render rather than fight React Compiler's manual-memo preservation.
 */
function buildTrendSeries(trendData) {
  if (!trendData) {
    return { rows: [], partyKeys: [], partyColors: {}, partyLabels: {} }
  }
  const totals = new Map()
  const labels = new Map()
  const colors = new Map()
  const perRow = []
  for (const { election, detail } of trendData) {
    const row = { year: election.election_date.slice(0, 4) }
    for (const r of detail.results || []) {
      if (r.party_id == null) continue
      if (typeof r.vote_share !== 'number') continue
      row[r.party_id] = r.vote_share
      totals.set(r.party_id, (totals.get(r.party_id) ?? 0) + r.vote_share)
      labels.set(r.party_id, r.party_short_name || r.party_name || r.party_id)
      colors.set(r.party_id, partyColor(r))
    }
    perRow.push(row)
  }
  const partyKeys = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([id]) => id)
  const partyColors = Object.fromEntries(
    partyKeys.map((k) => [k, colors.get(k) || '#64748b']),
  )
  const partyLabels = Object.fromEntries(
    partyKeys.map((k) => [k, labels.get(k) || k]),
  )
  return { rows: perRow, partyKeys, partyColors, partyLabels }
}
