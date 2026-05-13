import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import { NavLink } from 'react-router-dom'
import type { ComponentProps } from 'react'

// ---------------------------------------------------------------------------
// Custom component types — we use the props that ReactMarkdown passes through.
// ---------------------------------------------------------------------------

type AnchorProps = ComponentProps<'a'>
type CodeProps = ComponentProps<'code'> & { inline?: boolean }

function CustomLink({ href, children, ...rest }: AnchorProps) {
  if (!href) return <span {...rest}>{children}</span>

  // Internal links (start with /) use NavLink so React Router handles them.
  if (href.startsWith('/')) {
    return (
      <NavLink
        to={href}
        className="text-brand-600 hover:underline"
      >
        {children}
      </NavLink>
    )
  }

  // External links open in a new tab with security attributes.
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-brand-600 hover:underline"
      {...rest}
    >
      {children}
    </a>
  )
}

function CustomCode({ inline, children, ...rest }: CodeProps) {
  if (inline) {
    return (
      <code
        className="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono text-gray-800"
        {...rest}
      >
        {children}
      </code>
    )
  }
  // Block code — no extra styling; the <pre> wrapper handles it.
  return <code {...rest}>{children}</code>
}

// ---------------------------------------------------------------------------
// MarkdownRenderer
// ---------------------------------------------------------------------------

interface MarkdownRendererProps {
  source: string
}

export function MarkdownRenderer({ source }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSlug, [rehypeAutolinkHeadings, { behavior: 'wrap' }]]}
      components={{
        h1: ({ children, ...props }) => (
          <h1 className="text-3xl font-bold text-gray-900 mb-4" {...props}>
            {children}
          </h1>
        ),
        h2: ({ children, ...props }) => (
          <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-3 scroll-mt-20" {...props}>
            {children}
          </h2>
        ),
        h3: ({ children, ...props }) => (
          <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-2 scroll-mt-20" {...props}>
            {children}
          </h3>
        ),
        p: ({ children, ...props }) => (
          <p className="text-gray-700 leading-relaxed mb-4" {...props}>
            {children}
          </p>
        ),
        ul: ({ children, ...props }) => (
          <ul className="list-disc pl-6 mb-4 space-y-1 text-gray-700" {...props}>
            {children}
          </ul>
        ),
        ol: ({ children, ...props }) => (
          <ol className="list-decimal pl-6 mb-4 space-y-1 text-gray-700" {...props}>
            {children}
          </ol>
        ),
        li: ({ children, ...props }) => (
          <li className="leading-relaxed" {...props}>
            {children}
          </li>
        ),
        a: ({ href, children, ...props }) => (
          <CustomLink href={href} {...props}>
            {children}
          </CustomLink>
        ),
        code: ({ children, className, ...props }) => {
          // react-markdown passes className like "language-xxx" on block code.
          // Inline code has no className.
          const isInline = !className
          return (
            <CustomCode inline={isInline} className={className} {...props}>
              {children}
            </CustomCode>
          )
        },
        pre: ({ children, ...props }) => (
          <pre
            className="bg-gray-50 border border-gray-200 rounded p-3 text-sm font-mono overflow-x-auto mb-4"
            {...props}
          >
            {children}
          </pre>
        ),
        table: ({ children, ...props }) => (
          <div className="overflow-x-auto mb-4">
            <table className="min-w-full border border-gray-200 rounded text-sm" {...props}>
              {children}
            </table>
          </div>
        ),
        thead: ({ children, ...props }) => (
          <thead className="bg-gray-50" {...props}>
            {children}
          </thead>
        ),
        th: ({ children, ...props }) => (
          <th
            className="px-3 py-2 text-left font-semibold text-gray-700 border-b border-gray-200"
            {...props}
          >
            {children}
          </th>
        ),
        td: ({ children, ...props }) => (
          <td className="px-3 py-2 border-b border-gray-100 text-gray-700" {...props}>
            {children}
          </td>
        ),
        blockquote: ({ children, ...props }) => (
          <blockquote
            className="border-l-4 border-brand-200 pl-4 italic text-gray-600 mb-4"
            {...props}
          >
            {children}
          </blockquote>
        ),
        hr: ({ ...props }) => <hr className="border-gray-200 my-8" {...props} />,
      }}
    >
      {source}
    </ReactMarkdown>
  )
}
