import { useState, useRef, useCallback, useEffect, KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDocsSearch } from '../../hooks/useDocsSearch'
import { CATEGORY_DISPLAY } from '../../docs/index'
import type { FuseResult } from 'fuse.js'
import type { Doc } from '../../docs/index'

interface DocSearchBoxProps {
  /** Optional extra className on the wrapper div */
  className?: string
  /** If true, renders a larger, centred variant for the Help home page */
  large?: boolean
}

export function DocSearchBox({ className = '', large = false }: DocSearchBoxProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<FuseResult<Doc>[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const navigate = useNavigate()
  const search = useDocsSearch()

  const handleChange = useCallback(
    (value: string) => {
      setQuery(value)
      setActiveIndex(-1)
      if (value.trim()) {
        setResults(search(value))
      } else {
        setResults([])
      }
    },
    [search],
  )

  const handleSelect = useCallback(
    (slug: string) => {
      setQuery('')
      setResults([])
      setActiveIndex(-1)
      navigate(`/help/${slug}`)
    },
    [navigate],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (results.length === 0) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((i) => Math.min(i + 1, results.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((i) => Math.max(i - 1, -1))
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault()
        const item = results[activeIndex]
        if (item) handleSelect(item.item.slug)
      } else if (e.key === 'Escape') {
        setQuery('')
        setResults([])
        setActiveIndex(-1)
        inputRef.current?.blur()
      }
    },
    [results, activeIndex, handleSelect],
  )

  // Scroll the active list item into view.
  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const li = listRef.current.children[activeIndex] as HTMLElement | undefined
      li?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIndex])

  const inputSizeClass = large
    ? 'w-full max-w-xl px-4 py-3 text-base rounded-lg'
    : 'w-full px-3 py-2 text-sm rounded-md'

  return (
    <div className={`relative ${className}`}>
      <input
        ref={inputRef}
        type="search"
        role="searchbox"
        aria-label="Search docs"
        placeholder="Search docs..."
        value={query}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        className={`${inputSizeClass} border border-gray-300 bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent`}
      />

      {results.length > 0 && (
        <ul
          ref={listRef}
          className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-y-auto"
          role="listbox"
          aria-label="Search results"
        >
          {results.map((result, idx) => {
            const doc = result.item
            const isActive = idx === activeIndex
            return (
              <li
                key={doc.slug}
                role="option"
                aria-selected={isActive}
              >
                <button
                  className={`w-full text-left px-4 py-3 hover:bg-brand-50 focus:bg-brand-50 focus:outline-none ${isActive ? 'bg-brand-50' : ''}`}
                  onClick={() => handleSelect(doc.slug)}
                  onMouseEnter={() => setActiveIndex(idx)}
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-medium text-sm text-gray-900">{doc.title}</span>
                    <span className="text-xs text-brand-600 bg-brand-50 border border-brand-200 px-1.5 py-0.5 rounded-full">
                      {CATEGORY_DISPLAY[doc.category]}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 truncate">
                    {doc.summary.slice(0, 120)}
                  </p>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
