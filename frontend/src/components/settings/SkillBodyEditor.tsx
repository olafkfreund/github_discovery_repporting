// Usage:
//   import { SkillBodyEditor } from '../components/settings/SkillBodyEditor'
//   <SkillBodyEditor value={body} onChange={setBody} />

const DEFAULT_MAX = 50_000

interface Props {
  value: string
  onChange: (next: string) => void
  disabled?: boolean
  maxLength?: number
}

export function SkillBodyEditor({
  value,
  onChange,
  disabled = false,
  maxLength = DEFAULT_MAX,
}: Props) {
  return (
    <div>
      <textarea
        rows={20}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        maxLength={maxLength}
        className={[
          'font-mono text-sm border border-gray-300 rounded-md p-3',
          'focus:ring-2 focus:ring-brand-500 focus:border-brand-500 w-full',
          'resize-y',
          disabled ? 'bg-gray-50 cursor-not-allowed' : 'bg-white',
        ].join(' ')}
        placeholder="Write the skill body in Markdown…"
      />
      <p className="mt-1 text-xs text-gray-500">
        {value.length.toLocaleString()} / {maxLength.toLocaleString()} characters
      </p>
    </div>
  )
}
