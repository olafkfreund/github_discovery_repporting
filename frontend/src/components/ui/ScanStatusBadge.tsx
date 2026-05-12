// Usage:
//   import { ScanStatusBadge, STATUS_CLASSES } from '../components/ui/ScanStatusBadge'
//   <ScanStatusBadge status={scan.status} />

export const STATUS_CLASSES: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  scanning: 'bg-blue-100 text-blue-800',
  analyzing: 'bg-blue-100 text-blue-800',
  generating_report: 'bg-purple-100 text-purple-800',
  pending: 'bg-gray-100 text-gray-700',
  failed: 'bg-red-100 text-red-800',
}

interface ScanStatusBadgeProps {
  status: string
}

export function ScanStatusBadge({ status }: ScanStatusBadgeProps) {
  const classes = STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${classes}`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}
