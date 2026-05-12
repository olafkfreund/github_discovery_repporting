// AgentStepTimeline — scrollable step list with follow-tail behaviour (issue #30)
//
// Usage:
//   <AgentStepTimeline steps={steps} followTail={followTail} onScrollChange={setFollowTail} />

import { useRef, useEffect } from 'react'
import type { AgentStep } from '../../types/agents'
import { AgentStepCard } from './AgentStepCard'

interface Props {
  steps: AgentStep[]
  followTail: boolean
  onScrollChange: (atBottom: boolean) => void
}

const BOTTOM_THRESHOLD = 50 // px from bottom before we consider "not at bottom"

export function AgentStepTimeline({ steps, followTail, onScrollChange }: Props) {
  const listRef = useRef<HTMLOListElement>(null)
  const bottomRef = useRef<HTMLLIElement>(null)
  const prevLengthRef = useRef(steps.length)

  // Scroll to bottom when a new step is appended while following tail
  useEffect(() => {
    const newLength = steps.length
    if (followTail && newLength > prevLengthRef.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
    prevLengthRef.current = newLength
  }, [steps.length, followTail])

  // Scroll listener: detect when user has scrolled away from the bottom
  useEffect(() => {
    const el = listRef.current
    if (!el) return

    const handleScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      const atBottom = distFromBottom <= BOTTOM_THRESHOLD
      onScrollChange(atBottom)
    }

    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [onScrollChange])

  if (steps.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic py-4">
        No steps yet — waiting for the agent to start…
      </p>
    )
  }

  return (
    <ol
      ref={listRef}
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      className="divide-y divide-gray-100 overflow-y-auto max-h-[60vh] pr-1"
    >
      {steps
        .slice()
        .sort((a, b) => a.step_index - b.step_index)
        .map((step) => (
          <AgentStepCard key={step.id} step={step} />
        ))}
      {/* Invisible anchor for scroll-to-bottom */}
      <li ref={bottomRef} aria-hidden="true" />
    </ol>
  )
}
