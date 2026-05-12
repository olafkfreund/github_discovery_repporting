// JumpToLivePill — floating "Jump to live" button for AgentRunDetailPage (issue #30)
//
// Usage:
//   <JumpToLivePill visible={!followTail} onJump={() => setFollowTail(true)} />

interface Props {
  visible: boolean
  onJump: () => void
}

export function JumpToLivePill({ visible, onJump }: Props) {
  if (!visible) return null

  return (
    <button
      type="button"
      onClick={onJump}
      className="absolute bottom-4 right-4 bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium
                 px-3 py-1.5 rounded-full shadow-md
                 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2
                 transition-colors"
      aria-label="Jump to live — scroll to the latest step"
    >
      ↓ Jump to live
    </button>
  )
}
