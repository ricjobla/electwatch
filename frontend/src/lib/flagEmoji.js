/**
 * ISO 3166-1 alpha-2 -> flag emoji.
 *
 * Each emoji-flag is two regional indicator code points; we synthesize them
 * from the ISO2 letters. Returns an empty string for invalid input.
 *
 *     flagEmoji('SE') -> '🇸🇪'
 *     flagEmoji('xx') -> ''
 */
export function flagEmoji(iso2) {
  if (typeof iso2 !== 'string') return ''
  const code = iso2.trim().toUpperCase()
  if (!/^[A-Z]{2}$/.test(code)) return ''
  const A = 0x1f1e6 // regional indicator A
  return String.fromCodePoint(
    A + (code.charCodeAt(0) - 65),
    A + (code.charCodeAt(1) - 65),
  )
}
