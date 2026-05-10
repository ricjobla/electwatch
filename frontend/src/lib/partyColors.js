/**
 * Party color registry.
 *
 * Two layers:
 *   1. Hand-coded colors keyed by canonicalized party name (covers the parties
 *      that drive the visual signal — large social-democratic / conservative
 *      / green / far-right blocs across Europe).
 *   2. Deterministic HSL fallback derived from the party id or name so even
 *      uncovered parties get a stable, distinguishable swatch.
 *
 * The registry uses casefolded, alphanumeric-only keys so we don't trip on
 * punctuation/diacritics ("Vänsterpartiet (kommunisterna)" → "vansterpartiet").
 *
 * Sources for canonical hex values: each party's wikipedia article color +
 * Wikipedia's "List of political parties by colour" reference. Where multiple
 * shades exist we pick the one used in the party's logo / infobox.
 */

const RAW_REGISTRY = {
  // Sweden
  'socialdemokraterna': '#e8112d',
  'moderaterna': '#52bdec',
  'sverigedemokraterna': '#dddd00',
  'vansterpartiet': '#af0000',
  'centerpartiet': '#009933',
  'kristdemokraterna': '#231977',
  'liberalerna': '#006ab3',
  'miljopartiet': '#83cf39',

  // Germany
  'spd': '#e3000f',
  'cdu': '#000000',
  'csu': '#0070b8',
  'cducsu': '#000000',
  'gruene': '#1aa037',
  'diegruene': '#1aa037',
  'bundnis90diegrunen': '#1aa037',
  'fdp': '#ffed00',
  'afd': '#009ee0',
  'dielinke': '#be3075',
  'linke': '#be3075',
  'bsw': '#7d2c70',

  // France
  'lrem': '#ffeb00',
  'renaissance': '#ffeb00',
  'rn': '#0d378a',
  'frontnational': '#0d378a',
  'rassemblementnational': '#0d378a',
  'lfi': '#cc2443',
  'lafranceinsoumise': '#cc2443',
  'lr': '#0066cc',
  'lesrepublicains': '#0066cc',
  'ps': '#ff8080',
  'eelv': '#00c000',

  // UK
  'labour': '#e4003b',
  'labourparty': '#e4003b',
  'conservative': '#0087dc',
  'conservativeandunionistparty': '#0087dc',
  'conservativeparty': '#0087dc',
  'libdems': '#faa61a',
  'liberaldemocrats': '#faa61a',
  'snp': '#fdf38e',
  'reformuk': '#12b6cf',
  'green': '#02a95c',
  'greenparty': '#02a95c',

  // Spain
  'pp': '#1d84cf',
  'partidopopular': '#1d84cf',
  'psoe': '#ee1c25',
  'vox': '#5ac035',
  'sumar': '#ed1c25',
  'podemos': '#592c82',
  'cs': '#eb6109',
  'ciudadanos': '#eb6109',

  // Italy
  'fdi': '#0c4471',
  'fratelliditalia': '#0c4471',
  'pd': '#ee2e24',
  'partitodemocratico': '#ee2e24',
  'm5s': '#ffeb3b',
  'movimento5stelle': '#ffeb3b',
  'lega': '#138808',
  'fi': '#005eb8',
  'forzaitalia': '#005eb8',

  // Hungary
  'fidesz': '#fa9d22',
  'jobbik': '#73b34c',
  'mszp': '#ff0000',

  // Poland
  'pis': '#000d8f',
  'po': '#ff7f00',
  'platformaobywatelska': '#ff7f00',
  'konfederacja': '#1a3865',

  // Pan-European groupings (used as fallbacks for unmapped parties).
  'epp': '#3399ff',
  'sd': '#e60000',
  'renew': '#ffd700',
  'greensefa': '#009b48',
  'identityanddemocracy': '#0066cc',
  'theleft': '#990000',
}

function canonical(name) {
  if (!name) return ''
  return String(name)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}

function hashSeed(input) {
  let h = 5381
  const s = String(input ?? '')
  for (let i = 0; i < s.length; i += 1) {
    h = ((h << 5) + h) ^ s.charCodeAt(i)
  }
  return Math.abs(h)
}

/**
 * Deterministic HSL → hex fallback.
 *
 * Spread hues across the wheel; keep saturation/lightness in a band that
 * stays legible on the dark dashboard background.
 */
function fallbackHex(seed) {
  const h = hashSeed(seed) % 360
  const s = 55 + (hashSeed(`${seed}/sat`) % 25) // 55–80
  const l = 45 + (hashSeed(`${seed}/light`) % 12) // 45–57
  return hslToHex(h, s, l)
}

function hslToHex(h, s, l) {
  const sNorm = s / 100
  const lNorm = l / 100
  const c = (1 - Math.abs(2 * lNorm - 1)) * sNorm
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = lNorm - c / 2
  let rgb
  if (h < 60) rgb = [c, x, 0]
  else if (h < 120) rgb = [x, c, 0]
  else if (h < 180) rgb = [0, c, x]
  else if (h < 240) rgb = [0, x, c]
  else if (h < 300) rgb = [x, 0, c]
  else rgb = [c, 0, x]
  const toHex = (v) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${toHex(rgb[0])}${toHex(rgb[1])}${toHex(rgb[2])}`
}

const REGISTRY = Object.fromEntries(
  Object.entries(RAW_REGISTRY).map(([k, v]) => [canonical(k), v]),
)

/**
 * Resolve a party color.
 *
 * Lookup order: explicit hex from the DB → registry hit (canonical name or
 * short name) → deterministic HSL fallback derived from id/name.
 *
 * @param {{ party_color_hex?: string|null, party_name?: string|null,
 *           party_short_name?: string|null, party_id?: string|null }} party
 */
export function partyColor(party) {
  if (!party) return '#64748b'
  const explicit = party.party_color_hex || party.color_hex
  if (typeof explicit === 'string' && /^#[0-9a-fA-F]{6}$/.test(explicit)) {
    return explicit
  }
  const candidates = [
    party.party_short_name,
    party.short_name,
    party.party_name,
    party.name,
  ].filter(Boolean)
  for (const candidate of candidates) {
    const hit = REGISTRY[canonical(candidate)]
    if (hit) return hit
  }
  const seed = party.party_id || party.id || party.party_name || party.name || ''
  return fallbackHex(seed)
}

/** Test hook only. */
export const __test = { canonical, REGISTRY, fallbackHex }
