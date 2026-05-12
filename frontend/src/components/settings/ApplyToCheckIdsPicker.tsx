// Usage:
//   import { ApplyToCheckIdsPicker } from '../components/settings/ApplyToCheckIdsPicker'
//   <ApplyToCheckIdsPicker value={ids} onChange={setIds} allCheckIds={allCheckIds} />

import { useState, useRef, useCallback } from 'react'

interface Props {
  value: string[]
  onChange: (next: string[]) => void
  allCheckIds: string[]
  disabled?: boolean
}

export function ApplyToCheckIdsPicker({ value, onChange, allCheckIds, disabled = false }: Props) {
  const [inputValue, setInputValue] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const filtered = allCheckIds.filter(
    (id) =>
      !value.includes(id) &&
      id.toLowerCase().includes(inputValue.toLowerCase()),
  )

  const addId = useCallback(
    (id: string) => {
      onChange([...value, id])
      setInputValue('')
      setActiveIndex(-1)
      setIsOpen(false)
      inputRef.current?.focus()
    },
    [value, onChange],
  )

  const removeId = useCallback(
    (id: string) => {
      onChange(value.filter((v) => v !== id))
    },
    [value, onChange],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value)
    setIsOpen(e.target.value.length > 0)
    setActiveIndex(-1)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setIsOpen(false)
      setActiveIndex(-1)
      return
    }
    if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
      removeId(value[value.length - 1])
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setIsOpen(true)
      setActiveIndex((prev) => Math.min(prev + 1, filtered.length - 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((prev) => Math.max(prev - 1, 0))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0 && activeIndex < filtered.length) {
        addId(filtered[activeIndex])
      }
    }
  }

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <p className="text-xs text-gray-400 italic">Any check (general skill)</p>
      )}

      {/* Selected chips */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-800 rounded text-xs font-mono"
            >
              {id}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeId(id)}
                  className="text-gray-500 hover:text-gray-800 leading-none"
                  aria-label={`Remove ${id}`}
                >
                  &times;
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Input + dropdown */}
      {!disabled && (
        <div className="relative">
          <input
            ref={inputRef}
            type="search"
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => inputValue.length > 0 && setIsOpen(true)}
            onBlur={() => setTimeout(() => setIsOpen(false), 150)}
            placeholder="Type to search check IDs…"
            className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full"
            autoComplete="off"
            aria-autocomplete="list"
            aria-controls="check-id-listbox"
            aria-activedescendant={activeIndex >= 0 ? `check-id-option-${activeIndex}` : undefined}
          />
          {isOpen && filtered.length > 0 && (
            <ul
              id="check-id-listbox"
              ref={listRef}
              role="listbox"
              className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto"
            >
              {filtered.slice(0, 50).map((id, idx) => (
                <li
                  key={id}
                  id={`check-id-option-${idx}`}
                  role="option"
                  aria-selected={idx === activeIndex}
                  onMouseDown={() => addId(id)}
                  className={`px-3 py-1.5 text-sm font-mono cursor-pointer ${
                    idx === activeIndex
                      ? 'bg-brand-50 text-brand-900'
                      : 'text-gray-800 hover:bg-gray-50'
                  }`}
                >
                  {id}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
