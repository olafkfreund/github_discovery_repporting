// Usage:
//   import { SkillsTable } from '../components/settings/SkillsTable'
//   <SkillsTable skills={skills} onRowClick={setEditing} onToggle={toggleEnabled} />

import type { Skill } from '../../types/skills'
import { CategoryBadge } from './CategoryBadge'

const MAX_CHECK_IDS_SHOWN = 2

interface Props {
  skills: Skill[]
  onRowClick: (skill: Skill) => void
  onToggle: (skill: Skill, enabled: boolean) => Promise<void>
}

function SourcePill({ source }: { source: Skill['source'] }) {
  if (source === 'builtin') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-100 text-brand-900">
        BUILT-IN
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-900">
      CUSTOM
    </span>
  )
}

function CheckIdChips({ ids }: { ids: string[] }) {
  const visible = ids.slice(0, MAX_CHECK_IDS_SHOWN)
  const extra = ids.length - visible.length
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((id) => (
        <span
          key={id}
          className="inline-flex items-center px-1.5 py-0.5 bg-gray-100 text-gray-800 rounded text-xs font-mono"
        >
          {id}
        </span>
      ))}
      {extra > 0 && (
        <span className="inline-flex items-center px-1.5 py-0.5 text-xs text-gray-500">
          +{extra} more
        </span>
      )}
      {ids.length === 0 && (
        <span className="text-xs text-gray-400 italic">any</span>
      )}
    </div>
  )
}

export function SkillsTable({ skills, onRowClick, onToggle }: Props) {
  if (skills.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
        <p className="text-gray-500 font-medium">No skills match the current filters</p>
        <p className="text-gray-400 text-sm mt-1">Try adjusting the filter criteria.</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Type
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Name
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Category
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Applies to
            </th>
            <th scope="col" className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
              Enabled
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {skills.map((skill) => (
            <tr
              key={skill.name}
              role="button"
              tabIndex={0}
              onClick={() => onRowClick(skill)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onRowClick(skill)
                }
              }}
              className="hover:bg-gray-50 cursor-pointer focus:outline-none focus:bg-brand-50 transition-colors"
              aria-label={`Edit skill ${skill.name}`}
            >
              <td className="px-4 py-3 whitespace-nowrap">
                <SourcePill source={skill.source} />
              </td>
              <td className="px-4 py-3">
                <div className="text-sm font-medium text-gray-900">{skill.name}</div>
                {skill.description && (
                  <div className="text-xs text-gray-500 mt-0.5 max-w-xs truncate">{skill.description}</div>
                )}
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                <CategoryBadge category={skill.category} />
              </td>
              <td className="px-4 py-3">
                <CheckIdChips ids={skill.applies_to_check_ids} />
              </td>
              <td
                className="px-4 py-3 text-center"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  role="switch"
                  checked={skill.enabled}
                  onChange={(e) => { void onToggle(skill, e.target.checked) }}
                  aria-label={`${skill.enabled ? 'Disable' : 'Enable'} skill ${skill.name}`}
                  className="h-4 w-4 text-brand-600 border-gray-300 rounded focus:ring-brand-500 cursor-pointer"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
