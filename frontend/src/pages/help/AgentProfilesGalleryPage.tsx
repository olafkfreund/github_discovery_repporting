// AgentProfilesGalleryPage — read-only browser for the AGENTS.md profile
// catalogue. Lists the four built-in profiles as cards; clicking a card
// opens a centred modal that renders the full markdown body.

import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { MarkdownRenderer } from '../../components/help/MarkdownRenderer'
import type { AgentProfile } from '../../types/agentInstructions'

// ---------------------------------------------------------------------------
// Profile modal
// ---------------------------------------------------------------------------

interface ProfileModalProps {
  profile: AgentProfile | null
  onClose: () => void
}

function ProfileModal({ profile, onClose }: ProfileModalProps) {
  const [body, setBody] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!profile) return
    setLoading(true)
    setError(null)
    setBody(null)
    api
      .getAgentProfileContent(profile.slug)
      .then((res) => setBody(res.body))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to load profile'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [profile])

  useEffect(() => {
    if (!profile) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    setTimeout(() => closeButtonRef.current?.focus(), 0)
    return () => window.removeEventListener('keydown', handler)
  }, [profile, onClose])

  if (!profile) return null

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-modal-title"
    >
      <button
        type="button"
        aria-label="Close profile"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      <div className="relative bg-white shadow-xl rounded-lg w-full max-w-3xl max-h-[85vh] flex flex-col">
        <header className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 id="profile-modal-title" className="text-lg font-semibold text-gray-900">
            {profile.display_name}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 px-3 py-1 rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            Close
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {body !== null && !loading && !error && <MarkdownRenderer source={body} />}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AgentProfilesGalleryPage
// ---------------------------------------------------------------------------

export default function AgentProfilesGalleryPage() {
  const [profiles, setProfiles] = useState<AgentProfile[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openProfile, setOpenProfile] = useState<AgentProfile | null>(null)
  const lastCardRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    api
      .listAgentProfiles()
      .then(setProfiles)
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to load profiles'
        setError(message)
      })
  }, [])

  const handleClose = () => {
    setOpenProfile(null)
    setTimeout(() => lastCardRef.current?.focus(), 0)
  }

  if (error) {
    return (
      <div className="py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">AGENTS.md Profiles</h1>
        <p className="text-red-600">{error}</p>
      </div>
    )
  }

  if (profiles === null) {
    return (
      <div className="py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">AGENTS.md Profiles</h1>
        <p className="text-gray-500">Loading profiles…</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-2">AGENTS.md Profiles</h1>
      <p className="text-gray-600 mb-6">
        Profiles are starter AGENTS.md bundles tuned for a regulatory or operational context.
        Pick one as a starting point on a customer&apos;s Agent Instructions page, then
        customise as required. Click a card to read the full profile.
      </p>

      {profiles.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">No profiles available.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {profiles.map((profile) => (
            <button
              key={profile.slug}
              type="button"
              onClick={(e) => {
                lastCardRef.current = e.currentTarget
                setOpenProfile(profile)
              }}
              className="text-left p-5 border border-gray-200 rounded-lg bg-white hover:border-brand-400 hover:shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-brand-500 flex flex-col gap-2"
            >
              <h3 className="text-lg font-semibold text-gray-900">{profile.display_name}</h3>
              <p className="text-sm text-gray-600 flex-1">{profile.short_description}</p>
              <span className="text-sm font-medium text-brand-600">
                Read the full profile →
              </span>
            </button>
          ))}
        </div>
      )}

      <ProfileModal profile={openProfile} onClose={handleClose} />
    </div>
  )
}
