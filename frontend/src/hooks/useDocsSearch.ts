import { useCallback } from 'react'
import Fuse, { type FuseResult } from 'fuse.js'
import { DOCS, type Doc } from '../docs/index'

// Lazy singleton — Fuse index is built once on first search call, not at
// module load time, so it doesn't block the initial page render.
let _fuse: Fuse<Doc> | null = null

function getFuse(): Fuse<Doc> {
  if (!_fuse) {
    _fuse = new Fuse(DOCS, {
      keys: [
        { name: 'title', weight: 3 },
        { name: 'summary', weight: 2 },
        { name: 'headings.text', weight: 1.5 },
        { name: 'body', weight: 1 },
      ],
      threshold: 0.35,
      ignoreLocation: true,
    })
  }
  return _fuse
}

/**
 * Returns a stable search function backed by a lazy Fuse.js index over DOCS.
 * Usage:
 *   const search = useDocsSearch()
 *   const results = search('my query')  // FuseResult<Doc>[]
 */
export function useDocsSearch(): (query: string) => FuseResult<Doc>[] {
  return useCallback((query: string) => {
    if (!query.trim()) return []
    return getFuse().search(query, { limit: 8 })
  }, [])
}
