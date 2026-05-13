import { useParams, Link } from 'react-router-dom'
import { getDocBySlug, type Doc } from '../../docs/index'
import { MarkdownRenderer } from '../../components/help/MarkdownRenderer'
import { TableOfContents } from '../../components/help/TableOfContents'

// ---------------------------------------------------------------------------
// DocFooter
// ---------------------------------------------------------------------------

function formatReviewDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function DocFooter({ doc }: { doc: Doc }) {
  const editUrl = `https://github.com/olafkfreund/github_discovery_repporting/edit/main/frontend/src/docs/${doc.slug}.md`

  return (
    <footer className="mt-12 pt-6 border-t border-gray-200 flex flex-col gap-1 text-sm text-gray-500">
      <span>Last reviewed: {formatReviewDate(doc.last_reviewed)}</span>
      <a
        href={editUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="text-brand-600 hover:underline w-fit"
      >
        Edit on GitHub
      </a>
    </footer>
  )
}

// ---------------------------------------------------------------------------
// NotFoundDoc
// ---------------------------------------------------------------------------

function NotFoundDoc({ slug }: { slug: string | undefined }) {
  return (
    <div className="py-12 text-center">
      <h1 className="text-2xl font-bold text-gray-800 mb-2">Article not found</h1>
      {slug && (
        <p className="text-gray-500 mb-4">
          No article with slug <code className="bg-gray-100 px-1 rounded">{slug}</code> exists.
        </p>
      )}
      <Link to="/help" className="text-brand-600 hover:underline text-sm">
        Back to Help & Docs
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DocPage
// ---------------------------------------------------------------------------

export function DocPage() {
  const { slug } = useParams<{ slug: string }>()
  const doc = slug ? getDocBySlug(slug) : undefined

  if (!doc) return <NotFoundDoc slug={slug} />

  return (
    <div className="flex gap-8">
      <article className="flex-1 min-w-0" aria-labelledby="doc-title">
        <h1
          id="doc-title"
          className="text-3xl font-bold text-gray-900 mb-2"
        >
          {doc.title}
        </h1>
        <p className="text-gray-600 mb-6">{doc.summary}</p>
        <MarkdownRenderer source={doc.body} />
        <DocFooter doc={doc} />
      </article>
      <TableOfContents headings={doc.headings} />
    </div>
  )
}
