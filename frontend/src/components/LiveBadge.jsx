/**
 * Pulse-animated "LIVE" pill, used on cards when an election is mid-tally.
 *
 * Uses Tailwind's animate-ping for the halo and a static dot to keep the
 * label readable. Hidden when status !== 'live'.
 */
export default function LiveBadge({ status, className = '' }) {
  if (status !== 'live') return null
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full bg-red-950/70 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-red-300 ${className}`}
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
      </span>
      Live
    </span>
  )
}
