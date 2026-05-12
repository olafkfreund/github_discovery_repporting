// Usage:
//   import { ErrorPanel } from '../components/ui/ErrorPanel'
//   <ErrorPanel message={error} />
//   <ErrorPanel message={error} onRetry={() => void loadData()} />
//   <ErrorPanel message={error}>
//     <Link to="/customers" className="mt-3 inline-block text-red-700 underline text-sm">Back</Link>
//   </ErrorPanel>

import type { ReactNode } from 'react'

interface ErrorPanelProps {
  message: string
  onRetry?: () => void
  /** Optional extra content rendered below the message (e.g. a back-link) */
  children?: ReactNode
}

export function ErrorPanel({ message, onRetry, children }: ErrorPanelProps) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
      <p className="text-red-700 font-medium">Error</p>
      <p className="text-red-600 text-sm mt-1">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 text-sm text-red-700 underline hover:no-underline"
        >
          Retry
        </button>
      )}
      {children}
    </div>
  )
}
