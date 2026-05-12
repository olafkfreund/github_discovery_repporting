import { NavLink } from 'react-router-dom'
import { useAgentRunsLiveCount } from '../../hooks/useAgentRunsLiveCount'

interface NavItem {
  to: string
  label: string
  end?: boolean
  icon: React.ReactNode
  badge?: React.ReactNode
}

interface NavGroup {
  label: string
  items: NavItem[]
}

// Inline SVG: home / dashboard
const IconHome = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
    />
  </svg>
)

// Inline SVG: users / customers
const IconUsers = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
)

// Inline SVG: activity pulse / agents running
const IconActivity = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
)

// Inline SVG: cog / settings
const IconCog = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-5 w-5"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
)

function NavItemLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        [
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-brand-600 text-white'
            : 'text-gray-300 hover:bg-gray-800 hover:text-white',
        ].join(' ')
      }
    >
      {item.icon}
      <span className="flex-1">{item.label}</span>
      {item.badge}
    </NavLink>
  )
}

export default function Sidebar() {
  const { count } = useAgentRunsLiveCount()

  const navGroups: NavGroup[] = [
    {
      label: 'Operations',
      items: [
        { to: '/', label: 'Dashboard', end: true, icon: IconHome },
        { to: '/customers', label: 'Customers', icon: IconUsers },
        {
          to: '/agents',
          label: 'Agents Running',
          icon: IconActivity,
          // Badge only shown when count > 0
          badge:
            count > 0 ? (
              <span className="bg-accent-400 text-brand-900 text-xs font-semibold rounded-full px-1.5 py-0.5 ml-auto">
                {count}
              </span>
            ) : undefined,
        },
      ],
    },
    {
      label: 'Configuration',
      items: [{ to: '/settings', label: 'Settings', icon: IconCog }],
    },
  ]

  return (
    <aside className="flex flex-col w-64 min-h-screen bg-gray-900 text-white">
      {/* App title */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-700">
        <div className="flex-shrink-0 w-8 h-8 bg-brand-500 rounded-lg flex items-center justify-center">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5 text-white"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-tight">DevOps Discovery</p>
          <p className="text-xs text-gray-400">Reporting Platform</p>
        </div>
      </div>

      {/* Navigation — two groups: Operations and Configuration */}
      <nav className="flex-1 px-3 py-4">
        {navGroups.map((group) => (
          <div key={group.label}>
            <div className="text-xs uppercase tracking-wider text-gray-500 px-3 pt-4 pb-1">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => (
                <NavItemLink key={item.to} item={item} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-700">
        <p className="text-xs text-gray-500">BPS-tool</p>
        <p className="text-xs text-gray-600">v1.0.1</p>
      </div>
    </aside>
  )
}
