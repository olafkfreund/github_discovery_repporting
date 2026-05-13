import type { DocHeading } from '../../docs/index'

interface TableOfContentsProps {
  headings: DocHeading[]
}

function scrollToHeading(id: string) {
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

export function TableOfContents({ headings }: TableOfContentsProps) {
  if (headings.length === 0) return null

  return (
    <nav
      aria-label="On this page"
      className="hidden lg:block sticky top-20 w-56 ml-8 self-start"
    >
      <p className="text-xs uppercase tracking-wider text-gray-500 mb-2 font-semibold">
        On this page
      </p>
      <ul className="space-y-1">
        {headings.map((heading) => (
          <li key={heading.id} className={heading.depth === 3 ? 'pl-3' : ''}>
            <button
              onClick={() => scrollToHeading(heading.id)}
              className="text-sm text-gray-600 hover:text-brand-700 text-left w-full truncate leading-snug py-0.5 focus:outline-none focus:ring-2 focus:ring-brand-400 rounded"
            >
              {heading.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
