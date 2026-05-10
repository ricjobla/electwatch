import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Map, Source } from 'react-map-gl/maplibre'

/**
 * URL of the bundled Natural Earth Admin-0 1:50m countries GeoJSON.
 *
 * Lives in `frontend/public/` so Vite serves it from the same origin and
 * the browser caches it. Property `ISO_A2_EH` is used as the feature id
 * (via `promoteId`) because plain `ISO_A2` is `-99` for several relevant
 * countries (Norway, France, Kosovo).
 */
const COUNTRIES_GEOJSON = '/world-countries-50m.geojson'

const PALETTE = {
  bg: '#0f1117',
  neutral: '#2a3344',
  stroke: '#1b2434',
  hoverStroke: '#94a3b8',
  selectedStroke: '#f1f5f9',
}

/**
 * Single source of truth for the choropleth colors. Both the fill paint
 * expression and the legend chips below are generated from this list, so
 * adding/removing a bucket is one edit.
 */
const LEGEND_BUCKETS = [
  { id: 'urgent_hot', label: '≤14d', color: '#dc2626' },
  { id: 'urgent_warm', label: '15–30d', color: '#d97706' },
  { id: 'window', label: '31–90d', color: '#059669' },
  { id: 'distant', label: '>90d', color: '#475569' },
  { id: 'past', label: 'past 12mo', color: '#374151' },
  { id: 'none', label: 'None', color: PALETTE.neutral },
]

/**
 * Turn LEGEND_BUCKETS into a MapLibre `match` expression that maps the
 * `bucket` feature-state to a fill color. The `none` bucket is left out
 * because it is the default fallback.
 */
const FILL_COLOR_EXPRESSION = [
  'match',
  ['feature-state', 'bucket'],
  ...LEGEND_BUCKETS.flatMap((b) =>
    b.id === 'none' ? [] : [b.id, b.color],
  ),
  PALETTE.neutral,
]

const INITIAL_VIEW = { longitude: 14, latitude: 53, zoom: 3.2 }

/** Minimal blank style: no tile sources, just a dark background layer. */
const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': PALETTE.bg },
    },
  ],
}

const FILL_LAYER = {
  id: 'countries-fill',
  type: 'fill',
  source: 'countries',
  paint: {
    'fill-color': FILL_COLOR_EXPRESSION,
    'fill-opacity': [
      'case',
      ['boolean', ['feature-state', 'hover'], false],
      0.95,
      0.78,
    ],
  },
}

const LINE_LAYER = {
  id: 'countries-line',
  type: 'line',
  source: 'countries',
  paint: {
    'line-color': [
      'case',
      ['boolean', ['feature-state', 'selected'], false],
      PALETTE.selectedStroke,
      ['boolean', ['feature-state', 'hover'], false],
      PALETTE.hoverStroke,
      PALETTE.stroke,
    ],
    'line-width': [
      'case',
      ['boolean', ['feature-state', 'selected'], false],
      1.6,
      ['boolean', ['feature-state', 'hover'], false],
      0.9,
      0.4,
    ],
  },
}

function calendarDaysUntil(dateInput) {
  if (dateInput == null) return null
  const t = new Date(dateInput)
  if (Number.isNaN(t.getTime())) return null
  const today = new Date()
  const utcToday = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate(),
  )
  const utcTarget = Date.UTC(
    t.getUTCFullYear(),
    t.getUTCMonth(),
    t.getUTCDate(),
  )
  return Math.round((utcTarget - utcToday) / 86400000)
}

/**
 * Decide which colour bucket a country falls into based on the next or
 * most recent election date stored for it. Past >12 months is collapsed
 * into "none" because the country had no election in our display window.
 */
function bucketForDate(rawDate) {
  const days = calendarDaysUntil(rawDate)
  if (days === null) return 'none'
  if (days >= 0 && days <= 14) return 'urgent_hot'
  if (days >= 0 && days <= 30) return 'urgent_warm'
  if (days >= 0 && days <= 90) return 'window'
  if (days > 90) return 'distant'
  if (days >= -365) return 'past'
  return 'none'
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
 * MapLibre-powered global choropleth.
 *
 * @param {Object} props
 * @param {Record<string, string|Date|number|null>} [props.nextElectionByCountry]
 *   ISO2 → next-or-most-recent election date string. Drives the fill color.
 * @param {(iso: string) => void} [props.onCountryClick]
 * @param {string|null} [props.selectedIso2]
 * @param {string} [props.className]
 */
export default function WorldMap({
  nextElectionByCountry = {},
  onCountryClick = () => {},
  selectedIso2 = null,
  className = '',
}) {
  const mapRef = useRef(null)
  const [sourceReady, setSourceReady] = useState(false)
  const [tooltip, setTooltip] = useState(null)
  const hoveredIsoRef = useRef(null)
  const prevBucketIsosRef = useRef(new Set())
  const prevSelectedRef = useRef(null)

  const nextByIsoUpper = useMemo(() => {
    const out = {}
    for (const [k, v] of Object.entries(nextElectionByCountry || {})) {
      out[String(k).toUpperCase()] = v
    }
    return out
  }, [nextElectionByCountry])

  const handleLoad = useCallback((evt) => {
    const map = evt.target
    const markReady = () => {
      if (map.isSourceLoaded('countries')) setSourceReady(true)
    }
    if (map.isSourceLoaded('countries')) {
      setSourceReady(true)
      return
    }
    map.on('sourcedata', markReady)
    return () => map.off('sourcedata', markReady)
  }, [])

  // Apply choropleth bucket via feature-state whenever the data changes.
  useEffect(() => {
    if (!sourceReady || !mapRef.current) return
    const map = mapRef.current.getMap()
    const newIsos = new Set(Object.keys(nextByIsoUpper))
    for (const iso of prevBucketIsosRef.current) {
      if (!newIsos.has(iso)) {
        map.removeFeatureState({ source: 'countries', id: iso }, 'bucket')
      }
    }
    for (const iso of newIsos) {
      map.setFeatureState(
        { source: 'countries', id: iso },
        { bucket: bucketForDate(nextByIsoUpper[iso]) },
      )
    }
    prevBucketIsosRef.current = newIsos
  }, [sourceReady, nextByIsoUpper])

  // Selected-country outline.
  useEffect(() => {
    if (!sourceReady || !mapRef.current) return
    const map = mapRef.current.getMap()
    const next = selectedIso2 ? String(selectedIso2).toUpperCase() : null
    if (prevSelectedRef.current && prevSelectedRef.current !== next) {
      map.setFeatureState(
        { source: 'countries', id: prevSelectedRef.current },
        { selected: false },
      )
    }
    if (next) {
      map.setFeatureState({ source: 'countries', id: next }, { selected: true })
    }
    prevSelectedRef.current = next
  }, [sourceReady, selectedIso2])

  const handleMouseMove = useCallback(
    (evt) => {
      const map = evt.target
      const f = evt.features?.[0]
      const prev = hoveredIsoRef.current
      if (prev && (!f || prev !== f.id)) {
        map.setFeatureState({ source: 'countries', id: prev }, { hover: false })
        hoveredIsoRef.current = null
      }
      if (!f) {
        setTooltip(null)
        return
      }
      if (f.id !== prev) {
        map.setFeatureState({ source: 'countries', id: f.id }, { hover: true })
        hoveredIsoRef.current = f.id
      }
      const iso = String(f.id || '').toUpperCase()
      const next = nextByIsoUpper[iso]
      const days = next != null ? calendarDaysUntil(next) : null
      let subtitle = 'No upcoming election tracked'
      if (next != null && days !== null) {
        subtitle =
          days < 0
            ? `Last election: ${formatElectionDate(next)}`
            : `Next: ${formatElectionDate(next)} · ${days}d`
      }
      const name =
        f.properties?.NAME_EN ||
        f.properties?.NAME_LONG ||
        f.properties?.NAME ||
        iso
      setTooltip({
        iso,
        name,
        subtitle,
        x: evt.originalEvent.clientX,
        y: evt.originalEvent.clientY,
      })
    },
    [nextByIsoUpper],
  )

  const handleMouseLeave = useCallback(() => {
    if (hoveredIsoRef.current && mapRef.current) {
      const map = mapRef.current.getMap()
      map.setFeatureState(
        { source: 'countries', id: hoveredIsoRef.current },
        { hover: false },
      )
      hoveredIsoRef.current = null
    }
    setTooltip(null)
  }, [])

  const handleClick = useCallback(
    (evt) => {
      const f = evt.features?.[0]
      if (!f) return
      const iso = String(f.id || '').toUpperCase()
      if (iso && iso !== '-99') onCountryClick(iso)
    },
    [onCountryClick],
  )

  const handleZoomIn = useCallback(() => {
    mapRef.current?.getMap().zoomIn({ duration: 220 })
  }, [])

  const handleZoomOut = useCallback(() => {
    mapRef.current?.getMap().zoomOut({ duration: 220 })
  }, [])

  const handleReset = useCallback(() => {
    mapRef.current?.getMap().flyTo({
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      bearing: 0,
      pitch: 0,
      essential: true,
    })
  }, [])

  return (
    <div
      className={`relative w-full overflow-hidden rounded-lg border border-slate-800/80 ${className}`}
      style={{
        backgroundColor: PALETTE.bg,
        backgroundImage: `
          linear-gradient(rgba(148, 163, 184, 0.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148, 163, 184, 0.035) 1px, transparent 1px)
        `,
        backgroundSize: '28px 28px',
      }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 px-3 pt-3">
        <div className="pointer-events-auto flex flex-wrap items-end justify-between gap-3 rounded-md border border-slate-800/90 bg-slate-950/75 px-3 py-2 backdrop-blur">
          <div>
            <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              Electoral horizon
            </h2>
            <p className="mt-0.5 font-serif text-base leading-tight tracking-tight text-slate-100">
              Global overview
            </p>
          </div>
          <Legend />
        </div>
      </div>

      <Map
        ref={mapRef}
        initialViewState={INITIAL_VIEW}
        mapStyle={BLANK_STYLE}
        minZoom={1}
        maxZoom={8}
        dragRotate={false}
        touchPitch={false}
        attributionControl={false}
        interactiveLayerIds={['countries-fill']}
        onLoad={handleLoad}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        cursor={tooltip ? 'pointer' : 'grab'}
        style={{ width: '100%', height: '100%', minHeight: 480 }}
      >
        <Source
          id="countries"
          type="geojson"
          data={COUNTRIES_GEOJSON}
          promoteId="ISO_A2_EH"
        >
          <Layer {...FILL_LAYER} />
          <Layer {...LINE_LAYER} />
        </Source>
      </Map>

      <ControlPanel
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onReset={handleReset}
      />

      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded border border-slate-700/90 bg-slate-950/95 px-3 py-2 shadow-xl backdrop-blur-sm"
          style={{ left: tooltip.x + 14, top: tooltip.y + 14 }}
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

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
      {LEGEND_BUCKETS.map((b) => (
        <span key={b.id} className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-2.5 rounded-sm border border-slate-800"
            style={{ backgroundColor: b.color }}
            aria-hidden="true"
          />
          {b.label}
        </span>
      ))}
    </div>
  )
}

function ControlPanel({ onZoomIn, onZoomOut, onReset }) {
  return (
    <div className="absolute bottom-3 left-3 z-10 flex flex-col overflow-hidden rounded border border-slate-700 bg-slate-950/85 shadow backdrop-blur">
      <ControlButton onClick={onZoomIn} label="Zoom in">
        +
      </ControlButton>
      <ControlButton
        onClick={onZoomOut}
        label="Zoom out"
        className="border-t border-slate-800"
      >
        −
      </ControlButton>
      <ControlButton
        onClick={onReset}
        label="Reset view"
        className="border-t border-slate-800 font-mono text-[10px]"
      >
        RST
      </ControlButton>
    </div>
  )
}

function ControlButton({ onClick, label, children, className = '' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`flex h-8 w-8 items-center justify-center font-serif text-base text-slate-200 transition hover:bg-slate-800 ${className}`}
    >
      {children}
    </button>
  )
}
