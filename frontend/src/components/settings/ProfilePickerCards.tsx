// Usage:
//   import ProfilePickerCards from '../components/settings/ProfilePickerCards'
//
//   <ProfilePickerCards
//     profiles={profiles}
//     loadingSlug={loadingProfileSlug}
//     onPick={handleProfilePick}
//     disabled={profilesLoading}
//   />

import type { AgentProfile } from '../../types/agentInstructions'
import { Spinner } from '../ui/Spinner'

interface Props {
  profiles: AgentProfile[]
  /** Which slug is currently being fetched; shows a spinner in that card. */
  loadingSlug: string | null
  /** Called with the slug when a profile card is clicked, or null for blank. */
  onPick: (slug: string | null) => void
  disabled?: boolean
}

export default function ProfilePickerCards({ profiles, loadingSlug, onPick, disabled = false }: Props) {
  return (
    <section aria-labelledby="picker-heading">
      <h3 id="picker-heading" className="text-sm font-medium text-gray-700 mb-3">
        Pick a starting profile{' '}
        <span className="font-normal text-gray-500">(You can edit it after.)</span>
      </h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
        {profiles.map((profile) => {
          const isLoading = loadingSlug === profile.slug
          return (
            <button
              key={profile.slug}
              type="button"
              onClick={() => onPick(profile.slug)}
              disabled={disabled}
              aria-label={`Start with ${profile.display_name} profile`}
              className="bg-white border border-gray-200 rounded-lg p-4 text-left transition-colors
                         hover:border-brand-600 hover:shadow-sm
                         focus:outline-none focus:ring-2 focus:ring-brand-500
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="text-sm font-semibold text-gray-900 block">
                {profile.display_name}
              </span>
              <span className="text-xs text-gray-500 mt-1 line-clamp-2 block">
                {profile.short_description}
              </span>
              <span className="mt-3 inline-flex items-center text-xs font-medium text-brand-700">
                {isLoading ? (
                  <Spinner className="h-4" />
                ) : (
                  'Start with this'
                )}
              </span>
            </button>
          )
        })}
      </div>

      <button
        type="button"
        onClick={() => onPick(null)}
        disabled={disabled}
        aria-label="Start with a blank document"
        className="mt-4 text-sm text-gray-600 underline hover:text-gray-900
                   disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Start with a blank document
      </button>
    </section>
  )
}
