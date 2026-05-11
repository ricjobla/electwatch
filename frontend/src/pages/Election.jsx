import { Link, useParams } from 'react-router-dom'

import LiveBadge from '../components/LiveBadge'
import PartyLegend from '../components/PartyLegend'
import ResultsChart from '../components/ResultsChart'
import { useElectionDetail } from '../hooks/useElectionDetail'
import { countdownLabel, formatLongDate } from '../lib/dates'
import { flagEmoji } from '../lib/flagEmoji'

const STATUS_PILL = {
  upcoming: 'bg-emerald-950/70 text-emerald-300',
  live: 'bg-amber-950/70 text-amber-300',
  complete: 'bg-slate-800 text-slate-400',
}

export default function Election() {
  const { id = '' } = useParams()
  const { data, isLoading, error } = useElectionDetail(id)

  const hasPartialRows =
    data?.results?.some((r) => r.result_type === 'partial') ?? false
  const chartCaption =
    data?.status === 'live' && hasPartialRows
      ? 'Partial results — figures change as more votes are counted.'
      : undefined

  return (
    <section className="space-y-6">
      <header className="border-b border-slate-800 pb-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
          <Link to="/" className="hover:text-slate-200">
            ← Dashboard
          </Link>
        </p>

        {isLoading && (
          <p className="mt-2 font-mono text-sm text-slate-500">Loading…</p>
        )}
        {error && (
          <p className="mt-2 font-mono text-sm text-red-400">
            {String(error.message)}
          </p>
        )}

        {data && (
          <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
                <span aria-hidden="true">{flagEmoji(data.country_id)}</span>
                {data.country_id ? (
                  <Link
                    to={`/country/${encodeURIComponent(data.country_id)}`}
                    className="rounded px-1 hover:bg-slate-800 hover:text-slate-200"
                  >
                    {data.country_id}
                  </Link>
                ) : null}
                {data.country?.name ? (
                  <span className="text-slate-400 normal-case tracking-normal">
                    {data.country.name}
                  </span>
                ) : null}
                {data.type ? (
                  <span className="rounded bg-slate-800/60 px-1.5 py-0.5 normal-case tracking-wide">
                    {String(data.type).replace(/_/g, ' ')}
                  </span>
                ) : null}
              </div>
              <h2 className="mt-1 font-serif text-2xl tracking-tight text-slate-50">
                {data.title}
              </h2>
              <p className="mt-1 font-mono text-xs text-slate-500">
                {formatLongDate(data.election_date)} ·{' '}
                <span className="tabular-nums text-slate-400">
                  {countdownLabel(data.election_date)}
                </span>
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <LiveBadge status={data.status} />
              <span
                className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${
                  STATUS_PILL[data.status] ?? STATUS_PILL.complete
                }`}
              >
                {data.status}
              </span>
            </div>
          </div>
        )}
      </header>

      {data && (
        <>
          {data.status === 'live' &&
          data.reporting_pct != null &&
          Number.isFinite(data.reporting_pct) ? (
            <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-3 font-mono text-xs text-amber-200/90">
              Live tally: approximately{' '}
              <span className="tabular-nums font-semibold">
                {data.reporting_pct.toFixed(1)}%
              </span>{' '}
              of precincts / reporting nodes included in this snapshot.
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="mb-3 font-mono text-[10px] uppercase tracking-wider text-slate-500">
                Results — vote share
              </h3>
              <ResultsChart
                results={data.results || []}
                caption={chartCaption}
              />
            </div>
            <div>
              <h3 className="mb-3 font-mono text-[10px] uppercase tracking-wider text-slate-500">
                Parties
              </h3>
              <PartyLegend results={data.results || []} />
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm">
            <h3 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              Metadata
            </h3>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Field label="Election ID" value={data.id} mono />
              <Field
                label="Wikidata"
                value={data.wikidata_id}
                href={
                  data.wikidata_id
                    ? `https://www.wikidata.org/wiki/${data.wikidata_id}`
                    : null
                }
                mono
              />
              <Field
                label="Source URL"
                value={data.source_url}
                href={data.source_url}
                truncate
              />
              <Field
                label="Wikipedia"
                value={data.wikipedia_url}
                href={data.wikipedia_url}
                truncate
              />
              <Field
                label="Turnout"
                value={
                  data.turnout_pct != null
                    ? `${data.turnout_pct.toFixed(2)}%`
                    : null
                }
              />
              <Field
                label="% reporting (live)"
                value={
                  data.reporting_pct != null
                    ? `${data.reporting_pct.toFixed(2)}%`
                    : null
                }
              />
              <Field
                label="Last updated"
                value={
                  data.last_updated
                    ? new Date(data.last_updated).toLocaleString()
                    : null
                }
              />
            </dl>
            {data.description ? (
              <p className="mt-3 border-t border-slate-800 pt-3 text-slate-300">
                {data.description}
              </p>
            ) : null}
          </div>
        </>
      )}
    </section>
  )
}

function Field({ label, value, href, mono = false, truncate = false }) {
  if (!value) {
    return (
      <div>
        <dt className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
          {label}
        </dt>
        <dd className="text-slate-500">—</dd>
      </div>
    )
  }
  const cls = `${mono ? 'font-mono text-xs' : 'text-sm'} ${
    truncate ? 'block truncate' : ''
  }`
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-slate-200">
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={`${cls} text-sky-400 hover:underline`}
          >
            {value}
          </a>
        ) : (
          <span className={cls}>{value}</span>
        )}
      </dd>
    </div>
  )
}
