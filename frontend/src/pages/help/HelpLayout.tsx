import { Outlet, NavLink } from 'react-router-dom'
import { DocSearchBox } from '../../components/help/DocSearchBox'
import {
  CATEGORY_ORDER,
  CATEGORY_DISPLAY,
  getDocsByCategory,
  type DocCategory,
} from '../../docs/index'

// ---------------------------------------------------------------------------
// Left-nav section for a single category.
// ---------------------------------------------------------------------------

function CategorySection({ category }: { category: DocCategory }) {
  const docs = getDocsByCategory(category)
  if (docs.length === 0) return null

  return (
    <div>
      <h3 className="text-xs uppercase tracking-wider text-gray-500 mt-6 mb-1 first:mt-0 font-semibold px-1">
        {CATEGORY_DISPLAY[category]}
      </h3>
      <ul>
        {docs.map((doc) => (
          <li key={doc.slug}>
            <NavLink
              to={`/help/${doc.slug}`}
              className={({ isActive }) =>
                isActive
                  ? 'block px-3 py-1.5 text-sm bg-brand-50 text-brand-900 border-l-2 border-brand-600 rounded-r'
                  : 'block px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 border-l-2 border-transparent rounded-r'
              }
            >
              {doc.title}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// HelpLayout — three-column shell with left nav, centre content, right TOC.
// The right TOC column is painted by DocPage via its own TableOfContents.
// ---------------------------------------------------------------------------

export function HelpLayout() {
  return (
    <>
      {/* Skip link for keyboard / screen-reader users */}
      <a
        href="#help-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-brand-600 text-white px-3 py-1 rounded z-50"
      >
        Skip to content
      </a>

      <div className="flex min-h-full">
        {/* Left nav */}
        <aside className="w-64 shrink-0 border-r border-gray-200 px-4 py-6 overflow-y-auto sticky top-0 h-screen">
          <div className="mb-4">
            <DocSearchBox />
          </div>

          <nav aria-label="Help categories">
            {/* Categorised article links */}
            {CATEGORY_ORDER.map((category) => (
              <CategorySection key={category} category={category} />
            ))}

            {/* Live references group — pages from #56, linked now so nav is complete */}
            <div>
              <h3 className="text-xs uppercase tracking-wider text-gray-500 mt-6 mb-1 font-semibold px-1">
                Live references
              </h3>
              <ul>
                <li>
                  <NavLink
                    to="/help/skills-lib"
                    className={({ isActive }) =>
                      isActive
                        ? 'block px-3 py-1.5 text-sm bg-brand-50 text-brand-900 border-l-2 border-brand-600 rounded-r'
                        : 'block px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 border-l-2 border-transparent rounded-r'
                    }
                  >
                    Skills Library
                  </NavLink>
                </li>
                <li>
                  <NavLink
                    to="/help/profiles"
                    className={({ isActive }) =>
                      isActive
                        ? 'block px-3 py-1.5 text-sm bg-brand-50 text-brand-900 border-l-2 border-brand-600 rounded-r'
                        : 'block px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 border-l-2 border-transparent rounded-r'
                    }
                  >
                    AGENTS.md Profiles
                  </NavLink>
                </li>
              </ul>
            </div>
          </nav>
        </aside>

        {/* Centre content — Outlet renders child routes */}
        <main
          id="help-main"
          tabIndex={-1}
          className="flex-1 px-8 py-8 max-w-3xl focus:outline-none"
        >
          <Outlet />
        </main>
      </div>
    </>
  )
}
