// Usage:
//   import { CategoryBadge } from '../components/settings/CategoryBadge'
//   <CategoryBadge category="cicd" />

const CATEGORY_CLASSES: Record<string, string> = {
  repo_governance:    'bg-orange-100 text-orange-800',
  identity_access:    'bg-red-100 text-red-800',
  cicd:               'bg-emerald-100 text-emerald-800',
  secrets_mgmt:       'bg-yellow-100 text-yellow-800',
  dependencies:       'bg-blue-100 text-blue-800',
  sast:               'bg-purple-100 text-purple-800',
  dast:               'bg-fuchsia-100 text-fuchsia-800',
  container_security: 'bg-cyan-100 text-cyan-800',
  code_quality:       'bg-pink-100 text-pink-800',
  sdlc_process:       'bg-teal-100 text-teal-800',
  compliance:         'bg-rose-100 text-rose-800',
  collaboration:      'bg-lime-100 text-lime-800',
  disaster_recovery:  'bg-amber-100 text-amber-800',
  monitoring:         'bg-sky-100 text-sky-800',
  migration:          'bg-violet-100 text-violet-800',
  platform_arch:      'bg-indigo-100 text-indigo-800',
  general:            'bg-gray-100 text-gray-800',
}

const CATEGORY_DISPLAY: Record<string, string> = {
  repo_governance:    'Repo Governance',
  identity_access:    'Identity & Access',
  cicd:               'CI/CD',
  secrets_mgmt:       'Secrets Mgmt',
  dependencies:       'Dependencies',
  sast:               'SAST',
  dast:               'DAST',
  container_security: 'Container Security',
  code_quality:       'Code Quality',
  sdlc_process:       'SDLC Process',
  compliance:         'Compliance',
  collaboration:      'Collaboration',
  disaster_recovery:  'Disaster Recovery',
  monitoring:         'Monitoring',
  migration:          'Migration',
  platform_arch:      'Platform Architecture',
  general:            'General',
}

interface Props {
  category: string
}

export function CategoryBadge({ category }: Props) {
  const klass = CATEGORY_CLASSES[category] ?? 'bg-gray-100 text-gray-800'
  const display = CATEGORY_DISPLAY[category] ?? category
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${klass}`}>
      {display}
    </span>
  )
}
