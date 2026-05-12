// Usage:
//   import ProfileBadge from '../components/settings/ProfileBadge'
//
//   <ProfileBadge
//     profileSlug={instructions.profile_slug}
//     profileDisplayName="Standard"
//     updatedAt={instructions.updated_at}
//     onReplace={() => setReplaceDialogOpen(true)}
//   />

import { formatDate } from '../../utils/format'

interface Props {
  profileSlug: string
  profileDisplayName: string
  /** ISO timestamp — rendered with formatDate */
  updatedAt: string
  /** Opens the Replace-with-profile dialog */
  onReplace: () => void
}

export default function ProfileBadge({ profileDisplayName, updatedAt, onReplace }: Props) {
  return (
    <div
      className="bg-brand-50 border border-brand-100 text-brand-900 rounded-md px-3 py-2 text-xs
                 flex items-center justify-between gap-2 mb-4"
    >
      <span>
        Based on <strong>{profileDisplayName}</strong> profile &middot; saved {formatDate(updatedAt, 'date')}
      </span>
      <button
        type="button"
        onClick={onReplace}
        aria-label="Replace agent instructions with a different profile"
        className="text-brand-700 hover:text-brand-900 underline whitespace-nowrap"
      >
        Replace with profile&hellip;
      </button>
    </div>
  )
}
