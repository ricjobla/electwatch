import { partyColor } from '../lib/partyColors'

/**
 * Sorted, color-coded list of parties for an election. Optional click handler
 * for hover-syncing or drill-down.
 *
 * @param {{ results: Array, onSelect?: (party_id: string) => void }} props
 */
export default function PartyLegend({ results = [], onSelect }) {
  const rows = (results || [])
    .filter(Boolean)
    .map((r) => ({ ...r, _color: partyColor(r) }))
    .sort((a, b) => (b.vote_share ?? 0) - (a.vote_share ?? 0))

  if (rows.length === 0) {
    return (
      <p className="font-mono text-xs text-slate-500">No party results.</p>
    )
  }

  return (
    <ul className="divide-y divide-slate-800/80 rounded-md border border-slate-800 bg-slate-900/40">
      {rows.map((r, i) => {
        const key = r.party_id ?? `${r.party_name ?? '—'}-${i}`
        const inner = (
          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <div className="flex min-w-0 items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: r._color }}
                aria-hidden="true"
              />
              <span className="truncate text-sm text-slate-200">
                {r.party_name ?? r._label ?? r.party_id}
              </span>
              {r.party_short_name ? (
                <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
                  {r.party_short_name}
                </span>
              ) : null}
            </div>
            <div className="shrink-0 font-mono text-xs text-slate-400 tabular-nums">
              {r.vote_share != null ? `${r.vote_share.toFixed(1)}%` : '—'}
              {r.seats_won != null ? (
                <span className="ml-2 text-slate-500">{r.seats_won}s</span>
              ) : null}
            </div>
          </div>
        )
        return (
          <li key={key}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(r.party_id)}
                className="block w-full text-left hover:bg-slate-800/50"
              >
                {inner}
              </button>
            ) : (
              inner
            )}
          </li>
        )
      })}
    </ul>
  )
}
