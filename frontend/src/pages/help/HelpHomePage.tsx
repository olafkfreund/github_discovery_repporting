import { Link } from 'react-router-dom'
import { DocSearchBox } from '../../components/help/DocSearchBox'
import {
  CATEGORY_ORDER,
  CATEGORY_DISPLAY,
  getDocsByCategory,
  type DocCategory,
} from '../../docs/index'

// ---------------------------------------------------------------------------
// Inline SVG icons for each category — book-open style, no external lib.
// ---------------------------------------------------------------------------

const CATEGORY_ICONS: Record<DocCategory, React.ReactNode> = {
  'getting-started': (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
      />
    </svg>
  ),
  customers: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
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
  ),
  scans: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
      />
    </svg>
  ),
  reports: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
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
  ),
  remediation: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
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
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  'skills-profiles': (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
      />
    </svg>
  ),
  admin: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
      />
    </svg>
  ),
  reference: (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-6 w-6 text-brand-600"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
}

// ---------------------------------------------------------------------------
// Category card
// ---------------------------------------------------------------------------

function CategoryCard({ category }: { category: DocCategory }) {
  const docs = getDocsByCategory(category)
  const topDocs = docs.slice(0, 3)

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-brand-300 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        {CATEGORY_ICONS[category]}
        <h2 className="text-sm font-semibold text-gray-900">{CATEGORY_DISPLAY[category]}</h2>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        {docs.length} {docs.length === 1 ? 'article' : 'articles'}
      </p>
      {topDocs.length > 0 ? (
        <ul className="space-y-1">
          {topDocs.map((doc) => (
            <li key={doc.slug}>
              <Link
                to={`/help/${doc.slug}`}
                className="text-xs text-brand-600 hover:underline block truncate"
              >
                {doc.title}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-gray-400 italic">Coming soon</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// HelpHomePage
// ---------------------------------------------------------------------------

export function HelpHomePage() {
  return (
    <div>
      {/* Hero */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Help & Docs</h1>
        <p className="text-gray-600 text-lg">
          Everything you need to set up, scan, report, and remediate.
        </p>
      </div>

      {/* Search — large centred variant */}
      <div className="flex justify-center mb-10">
        <DocSearchBox large className="w-full max-w-xl" />
      </div>

      {/* Category card grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {CATEGORY_ORDER.map((category) => (
          <CategoryCard key={category} category={category} />
        ))}
      </div>

      {/* Docs version footer */}
      <p className="text-xs text-gray-500 mt-10">Docs version: BPS-tool v1.0.1</p>
    </div>
  )
}
