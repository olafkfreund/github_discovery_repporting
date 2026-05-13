// Usage:
//   import { SpendProgressBar } from '../components/ui/SpendProgressBar'
//
//   <SpendProgressBar spent={42.50} cap={100.00} />
//   <SpendProgressBar spent={85.00} cap={100.00} className="mt-2" />
//
// Fill colour thresholds:
//   < 80%  -> emerald-500
//   < 95%  -> amber-500
//   >= 95% -> red-600
//
// Returns null when cap === 0 (no cap configured).

interface Props {
  spent: number
  cap: number
  className?: string
}

export function SpendProgressBar({ spent, cap, className = '' }: Props) {
  if (cap === 0) return null

  const ratio = Math.min(1, spent / cap)
  const pct = Math.round(ratio * 100)

  let fillClass = 'bg-emerald-500'
  if (ratio >= 0.95) fillClass = 'bg-red-600'
  else if (ratio >= 0.8) fillClass = 'bg-amber-500'

  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Monthly spend: ${pct}% of cap used`}
      className={`w-full h-1.5 bg-gray-200 rounded-full overflow-hidden ${className}`}
    >
      <div
        className={`h-full rounded-full transition-all duration-300 ${fillClass}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
