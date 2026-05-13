// Usage:
//   import { formatDate, formatRelative, formatDuration, nextMonthStart } from '../utils/format'
//   formatDate(scan.started_at)             // => "3/4/2026, 14:05:00" or "—" for null
//   formatDate(scan.started_at, 'date')     // => "3/4/2026" (date only)
//   formatRelative(run.started_at)          // => "2m ago" | "just now" | "3d ago"
//   formatDuration(run.started_at, run.finished_at)  // => "02:14" | "1h30m" | "2d 3h"
//   nextMonthStart('2026-05-01T00:00:00Z')  // => "2026-06-01T00:00:00.000Z"

/**
 * Format an ISO date string using the browser locale.
 * Returns "—" for null/undefined/empty values.
 */
export function formatDate(
  dateStr: string | null | undefined,
  format: 'datetime' | 'date' = 'datetime'
): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  return format === 'date' ? d.toLocaleDateString() : d.toLocaleString()
}

/**
 * Format an ISO date string as a human-readable relative time.
 * Returns "—" for null/undefined/invalid values.
 *
 * Examples: "just now", "5m ago", "3h ago", "12d ago", or locale date for >30d.
 */
export function formatRelative(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  const seconds = Math.floor((Date.now() - d.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString()
}

/**
 * Return the ISO-8601 string for the first day of the month following the given date.
 * Uses UTC to avoid timezone-dependent offsets.
 *
 * Example: nextMonthStart('2026-05-01T00:00:00Z') => '2026-06-01T00:00:00.000Z'
 */
export function nextMonthStart(isoDate: string): string {
  const d = new Date(isoDate)
  d.setUTCMonth(d.getUTCMonth() + 1)
  d.setUTCDate(1)
  d.setUTCHours(0, 0, 0, 0)
  return d.toISOString()
}

/**
 * Format duration between two ISO date strings as a human-readable string.
 * If end is omitted the duration is measured to now (for live runs).
 * Returns "—" for null/undefined/invalid start values.
 *
 * Examples: "02:14" (<1h), "1h30m" (<24h), "2d 3h" (>=24h)
 */
export function formatDuration(
  start: string | null | undefined,
  end: string | null | undefined
): string {
  if (!start) return '—'
  const startMs = new Date(start).getTime()
  if (isNaN(startMs)) return '—'
  const endMs = end ? new Date(end).getTime() : Date.now()
  if (isNaN(endMs) || endMs < startMs) return '—'
  const seconds = Math.floor((endMs - startMs) / 1000)
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return `${h}h${m}m`
  }
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  return `${d}d ${h}h`
}
