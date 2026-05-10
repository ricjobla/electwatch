import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ComposableMap,
  Geographies,
  Geography,
} from 'react-simple-maps'

/**
 * Spec URL (GitHub `master` often 404s; identical bundle on `v2`).
 * @see https://raw.githubusercontent.com/zcreativelabs/react-simple-maps/master/topojson-maps/world-110m.json
 */
const WORLD_110M_PRIMARY =
  'https://raw.githubusercontent.com/zcreativelabs/react-simple-maps/master/topojson-maps/world-110m.json'
const WORLD_110M_FALLBACK =
  'https://raw.githubusercontent.com/zcreativelabs/react-simple-maps/v2/topojson-maps/world-110m.json'

/** REGION_UN misses several states relevant to a European elections scope. */
const EUROPE_ISO2_EXTRA = new Set([
  'CY',
  'GE',
  'AM',
  'AZ',
  'TR',
])

const PALETTE = {
  /** ≤30 days — urgent (red → amber) */
  urgentHot: '#dc2626',
  urgentWarm: '#d97706',
  /** 31–90 days */
  window: '#059669',
  /** Tracked but beyond 90 days */
  distant: '#475569',
  /** No upcoming election in dataset */
  neutral: '#2a3344',
  stroke: '#1b2434',
  strokeHover: '#64748b',
}

function isEuropeanGeometry(geo) {
  const p = geo.properties
  if (!p?.ISO_A2 || p.ISO_A2 === '-99') return false
  if (p.REGION_UN === 'Europe') return true
  return EUROPE_ISO2_EXTRA.has(String(p.ISO_A2).toUpperCase())
}

function calendarDaysUntil(dateInput) {
  const t = new Date(dateInput)
  if (Number.isNaN(t.getTime())) return null
  const today = new Date()
  const utcToday = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate(),
  )
  const utcTarget = Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate())
  return Math.round((utcTarget - utcToday) / 86400000)
}

function fillForIso(isoUpper, nextByIsoUpper) {
  const raw = nextByIsoUpper[isoUpper]
  if (raw === undefined || raw === null) return PALETTE.neutral
  const days = calendarDaysUntil(raw)
  if (days === null) return PALETTE.neutral
  if (days < 0) return PALETTE.neutral
  if (days <= 30) return days <= 14 ? PALETTE.urgentHot : PALETTE.urgentWarm
  if (days <= 90) return PALETTE.window
  return PALETTE.distant
}

function formatElectionDate(raw) {
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * @param {Object} props
 * @param {Record<string, string | Date | number>} [props.nextElectionByCountry] ISO2 → next upcoming election date
 * @param {(isoCode: string) => void} [props.onCountryClick]
 * @param {string|null} [props.selectedIso2] currently focused country (renders an outline)
 */
export default function EuropeMap({
  nextElectionByCountry = {},
  onCountryClick = () => {},
  selectedIso2 = null,
}) {
  const [topology, setTopology] = useState(null)
  const [topoError, setTopoError] = useState(null)

  const nextByIsoUpper = useMemo(() => {
    const out = {}
    for (const [k, v] of Object.entries(nextElectionByCountry)) {
      out[String(k).toUpperCase()] = v
    }
    return out
  }, [nextElectionByCountry])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      for (const url of [WORLD_110M_PRIMARY, WORLD_110M_FALLBACK]) {
        try {
          const res = await fetch(url)
          if (!res.ok) continue
          const json = await res.json()
          if (!cancelled) {
            setTopology(json)
            setTopoError(null)
            return
          }
        } catch {
          /* try next */
        }
      }
      if (!cancelled) setTopoError('Unable to load map data.')
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const [tooltip, setTooltip] = useState(null)

  const handleGeoMouseEnter = useCallback(
    (geo, evt) => {
      const iso = String(geo.properties.ISO_A2 || '').toUpperCase()
      const name =
        geo.properties.NAME_EN ||
        geo.properties.NAME_LONG ||
        geo.properties.NAME ||
        iso
      const next = iso ? nextByIsoUpper[iso] : undefined
      const days =
        next !== undefined && next !== null ? calendarDaysUntil(next) : null
      let subtitle = 'No upcoming election tracked'
      if (next != null && days !== null) {
        if (days < 0)
          subtitle = `Last: ${formatElectionDate(next)}`
        else subtitle = `Next: ${formatElectionDate(next)} (${days}d)`
      }
      setTooltip({
        iso,
        name,
        subtitle,
        x: evt.clientX,
        y: evt.clientY,
      })
    },
    [nextByIsoUpper],
  )

  const handleGeoMouseMove = useCallback((evt) => {
    setTooltip((prev) =>
      prev ? { ...prev, x: evt.clientX, y: evt.clientY } : prev,
    )
  }, [])

  const handleGeoMouseLeave = useCallback(() => setTooltip(null), [])

  return (
    <div
      className="relative w-full overflow-hidden rounded-lg border border-slate-800/80"
      style={{
        backgroundColor: '#0f1117',
        backgroundImage: `
          linear-gradient(rgba(148, 163, 184, 0.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148, 163, 184, 0.035) 1px, transparent 1px)
        `,
        backgroundSize: '28px 28px',
      }}
    >
      <div className="relative px-4 pb-3 pt-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2 border-b border-slate-800/90 pb-3">
          <div>
            <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              Electoral horizon
            </h2>
            <p className="mt-1 font-serif text-lg tracking-tight text-slate-100">
              Continental overview
            </p>
          </div>
          <div className="flex flex-wrap gap-4 font-mono text-[10px] uppercase tracking-wider text-slate-500">
            <span className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-sm"
                style={{ backgroundColor: PALETTE.urgentHot }}
              />
              ≤30d
            </span>
            <span className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-sm"
                style={{ backgroundColor: PALETTE.window }}
              />
              31–90d
            </span>
            <span className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-sm"
                style={{ backgroundColor: PALETTE.neutral }}
              />
              None
            </span>
          </div>
        </div>

        {topoError && (
          <p className="font-mono text-xs text-amber-600/90">{topoError}</p>
        )}

        {!topology && !topoError && (
          <div className="flex h-[420px] items-center justify-center font-mono text-xs text-slate-600">
            Loading topology…
          </div>
        )}

        {topology && (
          <ComposableMap
            projection="geoAzimuthalEqualArea"
            projectionConfig={{
              rotate: [-14.0, -53.0, 0],
              scale: 1660,
            }}
            width={880}
            height={520}
            style={{ width: '100%', height: 'auto', maxWidth: '100%' }}
          >
            <Geographies geography={topology}>
              {({ geographies }) =>
                geographies.filter(isEuropeanGeometry).map((geo) => {
                  const iso = String(geo.properties.ISO_A2 || '').toUpperCase()
                  const fill = fillForIso(iso, nextByIsoUpper)
                  const clickable = Boolean(iso && iso !== '-99')
                  const isSelected =
                    selectedIso2 &&
                    iso === String(selectedIso2).toUpperCase()
                  const stroke = isSelected ? '#f1f5f9' : PALETTE.stroke
                  const strokeWidth = isSelected ? 1.6 : 0.45
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      fill={fill}
                      stroke={stroke}
                      strokeWidth={strokeWidth}
                      style={{
                        default: {
                          outline: 'none',
                          cursor: clickable ? 'pointer' : 'default',
                          transition: 'fill 0.15s ease, stroke 0.15s ease',
                        },
                        hover: {
                          outline: 'none',
                          fill,
                          stroke: isSelected ? '#f1f5f9' : PALETTE.strokeHover,
                          strokeWidth: isSelected ? 1.8 : 0.65,
                          filter: 'brightness(1.08)',
                          cursor: clickable ? 'pointer' : 'default',
                        },
                        pressed: { outline: 'none' },
                      }}
                      onMouseEnter={(e) => handleGeoMouseEnter(geo, e)}
                      onMouseMove={handleGeoMouseMove}
                      onMouseLeave={handleGeoMouseLeave}
                      onClick={() => {
                        if (clickable) onCountryClick(iso)
                      }}
                    />
                  )
                })
              }
            </Geographies>
          </ComposableMap>
        )}
      </div>

      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded border border-slate-700/90 bg-slate-950/95 px-3 py-2 shadow-xl backdrop-blur-sm"
          style={{
            left: tooltip.x + 14,
            top: tooltip.y + 14,
          }}
        >
          <div className="font-serif text-sm font-medium tracking-tight text-slate-100">
            {tooltip.name}
          </div>
          <div className="mt-1 font-mono text-[11px] leading-snug text-slate-500">
            {tooltip.iso}
          </div>
          <div className="mt-2 border-t border-slate-800 pt-2 font-mono text-[11px] text-slate-400">
            {tooltip.subtitle}
          </div>
        </div>
      )}
    </div>
  )
}
