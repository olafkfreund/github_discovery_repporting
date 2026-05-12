// Usage:
//   import { PathGlobsEditor } from '../components/settings/PathGlobsEditor'
//
//   <PathGlobsEditor
//     label="Allowed path globs"
//     helpText="Only files matching these globs may be modified. Empty = no restriction."
//     globs={draft.allowed_path_globs ?? []}
//     onChange={(next) => setDraft((d) => ({ ...d, allowed_path_globs: next }))}
//     placeholder="src/**&#10;tests/**"
//   />

import { useId, useState } from 'react'

interface Props {
  label: string
  helpText: string
  globs: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}

function globsToText(globs: string[]): string {
  return globs.join('\n')
}

function textToGlobs(text: string): string[] {
  return [
    ...new Set(
      text
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    ),
  ]
}

export function PathGlobsEditor({ label, helpText, globs, onChange, placeholder }: Props) {
  const textareaId = useId()
  const [localValue, setLocalValue] = useState(() => globsToText(globs))

  // Sync local value when parent globs change (e.g. on discard / delete)
  const externalText = globsToText(globs)
  if (localValue !== externalText && document.activeElement?.id !== textareaId) {
    setLocalValue(externalText)
  }

  const handleBlur = () => {
    const next = textToGlobs(localValue)
    setLocalValue(globsToText(next)) // normalise whitespace
    onChange(next)
  }

  const lineCount = localValue.split('\n').filter((l) => l.trim().length > 0).length

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={textareaId} className="block text-sm font-medium text-gray-700">
        {label}
      </label>
      <p className="text-xs text-gray-500">{helpText}</p>
      <textarea
        id={textareaId}
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        onBlur={handleBlur}
        rows={6}
        spellCheck={false}
        placeholder={placeholder}
        className="font-mono text-sm border border-gray-300 rounded-md p-2
                   focus:ring-2 focus:ring-brand-500 focus:border-brand-500
                   resize-y w-full"
      />
      <p className="text-xs text-gray-400">
        {lineCount} glob{lineCount !== 1 ? 's' : ''} &middot; one per line
      </p>
    </div>
  )
}
