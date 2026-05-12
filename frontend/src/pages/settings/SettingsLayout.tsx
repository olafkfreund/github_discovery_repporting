import { useRef } from 'react'
import { NavLink, Outlet, useMatch } from 'react-router-dom'
import CustomerPicker from '../../components/settings/CustomerPicker'

interface TabDefinition {
  to: string
  label: string
}

const TABS: TabDefinition[] = [
  { to: '/settings/llm-providers', label: 'LLM Providers' },
  { to: '/settings/remediation-policy', label: 'Remediation Policy' },
  { to: '/settings/agent-instructions', label: 'Agent Instructions' },
  { to: '/settings/global', label: 'Global' },
]

export default function SettingsLayout() {
  const isGlobal = useMatch('/settings/global')
  const tabRefs = useRef<(HTMLAnchorElement | null)[]>([])

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const focusedIndex = tabRefs.current.findIndex(
      (el) => el === document.activeElement,
    )
    if (focusedIndex === -1) return

    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (focusedIndex + 1) % TABS.length
      tabRefs.current[next]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (focusedIndex - 1 + TABS.length) % TABS.length
      tabRefs.current[prev]?.focus()
    }
  }

  return (
    <div className="flex flex-col min-h-full">
      {/* Customer picker — hidden on Global tab */}
      {!isGlobal && <CustomerPicker />}

      {/* Sub-tab navigation */}
      <div className="border-b border-gray-200 bg-white px-6 pt-4 pb-0">
        <div
          role="tablist"
          aria-label="Settings sections"
          className="flex gap-1"
          onKeyDown={handleKeyDown}
        >
          {TABS.map((tab, idx) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              role="tab"
              ref={(el) => {
                tabRefs.current[idx] = el
              }}
              className={({ isActive }) =>
                [
                  'px-4 py-2 text-sm font-medium rounded-md mb-2 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500',
                  isActive
                    ? 'bg-brand-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100',
                ].join(' ')
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
      </div>

      {/* Active sub-page */}
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  )
}
