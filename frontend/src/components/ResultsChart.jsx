import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { partyColor } from '../lib/partyColors'

/**
 * Horizontal bar chart of party vote shares for one election.
 *
 * Bars are colored from the party color registry (with a deterministic HSL
 * fallback). Hover tooltip shows the party name, vote share, and seat count.
 *
 * @param {Object} props
 * @param {Array<{party_name?: string, party_short_name?: string, vote_share?: number, seats_won?: number, party_color_hex?: string, party_id?: string}>} props.results
 * @param {number} [props.maxRows=12] truncate at top-N parties (sorted by vote share)
 * @param {string} [props.height='auto'] CSS height; defaults to N * 28px capped to maxRows
 */
export default function ResultsChart({ results = [], maxRows = 12, height }) {
  const filtered = (results || [])
    .filter((r) => r && (r.vote_share != null || r.seats_won != null))
    .map((r) => ({
      ...r,
      _label: r.party_short_name || r.party_name || r.party_id || '—',
      _share: typeof r.vote_share === 'number' ? r.vote_share : 0,
      _color: partyColor(r),
    }))
    .sort((a, b) => b._share - a._share)
    .slice(0, maxRows)

  if (filtered.length === 0) {
    return (
      <div className="rounded border border-dashed border-slate-700 bg-slate-900/30 p-6 text-center font-mono text-xs text-slate-500">
        No party-level results stored for this election yet.
      </div>
    )
  }

  const computedHeight =
    typeof height === 'number'
      ? `${height}px`
      : height || `${Math.max(180, filtered.length * 32 + 48)}px`

  return (
    <div className="w-full" style={{ height: computedHeight }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={filtered}
          layout="vertical"
          margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
          barCategoryGap={6}
        >
          <XAxis
            type="number"
            domain={[0, (max) => Math.max(10, Math.ceil(max + 2))]}
            tickFormatter={(v) => `${v}%`}
            stroke="#475569"
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="_label"
            width={140}
            stroke="#475569"
            tick={{ fontSize: 11, fill: '#cbd5f5' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: 'rgba(148,163,184,0.08)' }}
            contentStyle={{
              background: 'rgba(2,6,23,0.95)',
              border: '1px solid rgb(51 65 85)',
              borderRadius: 6,
              color: '#e2e8f0',
              fontSize: 12,
            }}
            formatter={(_, _name, ctx) => {
              const r = ctx?.payload || {}
              const lines = []
              if (r._share != null) lines.push(`${r._share.toFixed(2)}%`)
              if (r.seats_won != null) lines.push(`${r.seats_won} seats`)
              return [lines.join(' · '), r.party_name || r._label]
            }}
            labelFormatter={() => ''}
          />
          <Bar dataKey="_share" radius={[2, 2, 2, 2]}>
            {filtered.map((row) => (
              <Cell key={row.party_id ?? row._label} fill={row._color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
