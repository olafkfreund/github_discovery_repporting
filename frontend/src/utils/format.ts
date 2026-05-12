// Usage:
//   import { formatDate } from '../utils/format'
//   formatDate(scan.started_at)   // => "3/4/2026, 14:05:00" or "—" for null
//   formatDate(scan.started_at, 'date')  // => "3/4/2026" (date only)

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
