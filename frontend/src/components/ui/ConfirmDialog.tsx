// Usage:
//   import { ConfirmDialog } from '../components/ui/ConfirmDialog'
//
//   const [dialogOpen, setDialogOpen] = useState(false)
//   const [pendingId, setPendingId] = useState<string | null>(null)
//
//   // Trigger the dialog instead of window.confirm():
//   const handleDeleteClick = (id: string) => {
//     setPendingId(id)
//     setDialogOpen(true)
//   }
//
//   <ConfirmDialog
//     open={dialogOpen}
//     title="Delete Customer"
//     message={`Delete customer "${name}"? This action cannot be undone.`}
//     onConfirm={() => { setDialogOpen(false); void performDelete(pendingId!) }}
//     onCancel={() => { setDialogOpen(false); setPendingId(null) }}
//     confirmLabel="Delete"
//     variant="danger"
//   />

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
  /** Label for the confirm button. Defaults to "Delete". */
  confirmLabel?: string
  /** "danger" renders a red confirm button; "default" renders an indigo button. */
  variant?: 'danger' | 'default'
}

export function ConfirmDialog({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  confirmLabel = 'Delete',
  variant = 'danger',
}: ConfirmDialogProps) {
  if (!open) return null

  const confirmClasses =
    variant === 'danger'
      ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500 text-white'
      : 'bg-brand-600 hover:bg-brand-700 focus:ring-brand-500 text-white'

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onCancel}
      aria-modal="true"
      role="dialog"
      aria-labelledby="confirm-dialog-title"
    >
      {/* Panel — stop click from bubbling to backdrop */}
      <div
        className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="text-base font-semibold text-gray-900"
        >
          {title}
        </h2>
        <p className="mt-2 text-sm text-gray-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md
                       border border-gray-300 hover:bg-gray-50
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 text-sm font-medium rounded-md
                        focus:outline-none focus:ring-2 focus:ring-offset-2
                        ${confirmClasses}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
