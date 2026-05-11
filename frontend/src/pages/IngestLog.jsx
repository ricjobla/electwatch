import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { fetchJson } from '../lib/api'

export default function IngestLog() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['ingest-log'],
    queryFn: () => fetchJson('/api/admin/ingest-log?limit=250'),
    retry: false,
  })

  return (
    <section className="space-y-6">
      <header className="border-b border-slate-800 pb-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
          <Link to="/" className="hover:text-slate-200">
            ← Dashboard
          </Link>
        </p>
        <h2 className="mt-2 font-serif text-2xl tracking-tight text-slate-50">
          Ingest log
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Recent scraper and ingestion events. Requires{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-[11px]">
            ELECTWATCH_DEBUG=true
          </code>{' '}
          on the API process (403 otherwise).
        </p>
      </header>

      {isLoading ? (
        <p className="font-mono text-sm text-slate-500">Loading…</p>
      ) : null}
      {error ? (
        <p className="font-mono text-sm text-red-400">{String(error.message)}</p>
      ) : null}

      {Array.isArray(data) && data.length === 0 ? (
        <p className="font-mono text-sm text-slate-500">No log rows yet.</p>
      ) : null}

      {Array.isArray(data) && data.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/40">
          <table className="w-full min-w-[720px] border-collapse text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-slate-900/80 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">Run at</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Election</th>
                <th className="px-3 py-2">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {data.map((row) => (
                <tr key={row.id} className="hover:bg-slate-900/60">
                  <td className="whitespace-nowrap px-3 py-2 text-slate-400">
                    {row.run_at
                      ? new Date(row.run_at).toLocaleString()
                      : '—'}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">{row.status}</td>
                  <td className="max-w-[140px] truncate px-3 py-2 text-slate-400">
                    {row.source ?? '—'}
                  </td>
                  <td className="max-w-[180px] truncate px-3 py-2">
                    {row.election_id ? (
                      <Link
                        to={`/election/${encodeURIComponent(row.election_id)}`}
                        className="text-sky-400 hover:underline"
                      >
                        {row.election_id}
                      </Link>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="max-w-xl px-3 py-2 text-slate-400">
                    <span className="line-clamp-3 whitespace-pre-wrap">
                      {row.message ?? '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
