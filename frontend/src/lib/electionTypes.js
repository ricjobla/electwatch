export const CURATED_ELECTION_TYPES = [
  'municipal',
  'legislative',
  'local',
  'general',
  'parliamentary',
  'presidential',
  'senate',
  'referendum',
  'european_parliament',
]

export function mergeElectionTypes(serverTypes = []) {
  const byLowercase = new Map()

  for (const type of [...serverTypes, ...CURATED_ELECTION_TYPES]) {
    if (!type) continue

    const key = type.toLowerCase()
    if (!byLowercase.has(key)) {
      byLowercase.set(key, type)
    }
  }

  return [...byLowercase.values()].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: 'base' }),
  )
}
