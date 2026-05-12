// Usage:
//   import { useSkills } from '../hooks/useSkills'
//   const { skills, loading, error, reload, toggleEnabled } = useSkills(customerId)

import { useState, useCallback, useEffect } from 'react'
import { api } from '../api/client'
import type { Skill, SkillCreatePayload, SkillUpdatePayload } from '../types/skills'

interface UseSkillsResult {
  skills: Skill[]
  loading: boolean
  error: string | null
  reload: () => Promise<void>
  createSkill: (payload: SkillCreatePayload) => Promise<Skill>
  updateSkill: (name: string, payload: SkillUpdatePayload) => Promise<Skill>
  deleteSkill: (name: string) => Promise<void>
  toggleEnabled: (name: string, enabled: boolean) => Promise<void>
}

export function useSkills(customerId: string | null): UseSkillsResult {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!customerId) {
      setSkills([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await api.listSkills(customerId)
      setSkills(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load skills')
    } finally {
      setLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    let cancelled = false
    if (!customerId) {
      setSkills([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    api
      .listSkills(customerId)
      .then((data) => {
        if (!cancelled) setSkills(data)
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load skills')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [customerId])

  const createSkill = useCallback(
    async (payload: SkillCreatePayload): Promise<Skill> => {
      if (!customerId) throw new Error('No customer selected')
      const created = await api.createSkill(customerId, payload)
      // Optimistically prepend
      setSkills((prev) => [created, ...prev])
      return created
    },
    [customerId],
  )

  const updateSkill = useCallback(
    async (name: string, payload: SkillUpdatePayload): Promise<Skill> => {
      if (!customerId) throw new Error('No customer selected')
      const updated = await api.updateSkill(customerId, name, payload)
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? updated : s)),
      )
      return updated
    },
    [customerId],
  )

  const deleteSkill = useCallback(
    async (name: string): Promise<void> => {
      if (!customerId) throw new Error('No customer selected')
      // Optimistic remove
      setSkills((prev) => prev.filter((s) => s.name !== name))
      try {
        await api.deleteSkill(customerId, name)
      } catch (err) {
        // Roll back on failure
        await reload()
        throw err
      }
    },
    [customerId, reload],
  )

  const toggleEnabled = useCallback(
    async (name: string, enabled: boolean): Promise<void> => {
      if (!customerId) throw new Error('No customer selected')
      // Optimistic update
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? { ...s, enabled } : s)),
      )
      try {
        const updated = await api.updateSkill(customerId, name, { enabled })
        setSkills((prev) => prev.map((s) => (s.name === name ? updated : s)))
      } catch (err) {
        // Roll back
        setSkills((prev) =>
          prev.map((s) => (s.name === name ? { ...s, enabled: !enabled } : s)),
        )
        throw err
      }
    },
    [customerId],
  )

  return { skills, loading, error, reload, createSkill, updateSkill, deleteSkill, toggleEnabled }
}
