// Usage:
//   import { Spinner } from '../components/ui/Spinner'
//   <Spinner />
//   <Spinner className="h-48" />

interface SpinnerProps {
  /** Outer wrapper className — used to control the container height/alignment context */
  className?: string
}

export function Spinner({ className = 'h-64' }: SpinnerProps) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
    </div>
  )
}
