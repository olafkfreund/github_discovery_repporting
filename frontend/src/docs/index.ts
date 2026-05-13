// Docs registry — loaded at build time via Vite's import.meta.glob.
// All .md files under this directory are parsed and exported as DOCS[].
// The frontmatter contract is validated at load time; an invalid .md file
// will throw during module initialisation so CI catches it early.

export type DocCategory =
  | 'getting-started'
  | 'customers'
  | 'scans'
  | 'reports'
  | 'remediation'
  | 'skills-profiles'
  | 'admin'
  | 'reference'

export const CATEGORY_DISPLAY: Record<DocCategory, string> = {
  'getting-started': 'Getting started',
  customers: 'Customers & Connections',
  scans: 'Scans & Profiles',
  reports: 'Reports',
  remediation: 'Remediation',
  'skills-profiles': 'Skills & Profiles',
  admin: 'Admin & Compliance',
  reference: 'Reference',
}

// The display order of categories in the left nav.
export const CATEGORY_ORDER: DocCategory[] = [
  'getting-started',
  'customers',
  'scans',
  'reports',
  'remediation',
  'skills-profiles',
  'admin',
  'reference',
]

export interface DocHeading {
  depth: 2 | 3
  text: string
  id: string
}

export interface Doc {
  slug: string
  title: string
  category: DocCategory
  order: number
  summary: string
  audience: ('end-user' | 'admin')[]
  last_reviewed: string
  body: string
  headings: DocHeading[]
}

// ---------------------------------------------------------------------------
// Hand-rolled frontmatter parser — no gray-matter / js-yaml dep.
// ---------------------------------------------------------------------------

const VALID_CATEGORIES = new Set<string>([
  'getting-started',
  'customers',
  'scans',
  'reports',
  'remediation',
  'skills-profiles',
  'admin',
  'reference',
])

const VALID_AUDIENCES = new Set<string>(['end-user', 'admin'])

function assertString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Doc frontmatter: field "${field}" must be a non-empty string`)
  }
  return value.trim()
}

function assertNumber(value: unknown, field: string): number {
  const n = Number(value)
  if (isNaN(n)) {
    throw new Error(`Doc frontmatter: field "${field}" must be a number, got "${String(value)}"`)
  }
  return n
}

function assertDocCategory(value: unknown, field: string): DocCategory {
  const s = assertString(value, field)
  if (!VALID_CATEGORIES.has(s)) {
    throw new Error(
      `Doc frontmatter: "${field}" must be one of [${[...VALID_CATEGORIES].join(', ')}], got "${s}"`,
    )
  }
  return s as DocCategory
}

function assertAudienceArray(value: unknown, field: string): ('end-user' | 'admin')[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`Doc frontmatter: field "${field}" must be a non-empty array`)
  }
  return value.map((v: unknown) => {
    const s = typeof v === 'string' ? v.trim() : ''
    if (!VALID_AUDIENCES.has(s)) {
      throw new Error(
        `Doc frontmatter: "${field}" entries must be "end-user" or "admin", got "${s}"`,
      )
    }
    return s as 'end-user' | 'admin'
  })
}

// Parse inline YAML array: [end-user, admin] or [admin]
function parseInlineArray(raw: string): string[] {
  const inner = raw.trim().replace(/^\[/, '').replace(/\]$/, '')
  return inner
    .split(',')
    .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
    .filter(Boolean)
}

// Parse frontmatter block into a plain object.
// Handles simple key: value pairs and inline arrays.
function parseFrontmatterBlock(block: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const line of block.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const colonIdx = trimmed.indexOf(':')
    if (colonIdx === -1) continue
    const key = trimmed.slice(0, colonIdx).trim()
    const rawValue = trimmed.slice(colonIdx + 1).trim()
    if (!key) continue

    if (rawValue.startsWith('[')) {
      result[key] = parseInlineArray(rawValue)
    } else {
      result[key] = rawValue
    }
  }
  return result
}

// Slugify heading text the same way rehype-slug does:
// toLowerCase, collapse non-alphanumeric runs to '-', trim leading/trailing '-'.
function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

// Extract h2/h3 headings from markdown body (ATX style only: ## / ###).
function extractHeadings(body: string): DocHeading[] {
  const headings: DocHeading[] = []
  for (const line of body.split('\n')) {
    const h2 = line.match(/^## (.+)$/)
    if (h2) {
      const text = h2[1].trim()
      headings.push({ depth: 2, text, id: slugifyHeading(text) })
      continue
    }
    const h3 = line.match(/^### (.+)$/)
    if (h3) {
      const text = h3[1].trim()
      headings.push({ depth: 3, text, id: slugifyHeading(text) })
    }
  }
  return headings
}

function parseDoc(raw: string): Doc {
  // The file must start with a frontmatter block delimited by `---`.
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/m)
  if (!match) {
    throw new Error('Doc: missing frontmatter block (expected file to start with ---)')
  }
  const [, frontmatterBlock, body] = match
  const fm = parseFrontmatterBlock(frontmatterBlock)

  const slug = assertString(fm['slug'], 'slug')
  const title = assertString(fm['title'], 'title')
  const category = assertDocCategory(fm['category'], 'category')
  const order = assertNumber(fm['order'], 'order')
  const summary = assertString(fm['summary'], 'summary')
  const audience = assertAudienceArray(fm['audience'], 'audience')
  const last_reviewed = assertString(fm['last_reviewed'], 'last_reviewed')

  const headings = extractHeadings(body)

  return { slug, title, category, order, summary, audience, last_reviewed, body, headings }
}

// ---------------------------------------------------------------------------
// Load all .md files eagerly at build time.
// ---------------------------------------------------------------------------

const modules = import.meta.glob('./*.md', { query: '?raw', import: 'default', eager: true })

export const DOCS: Doc[] = Object.entries(modules).map(([_path, raw]) => {
  if (typeof raw !== 'string') {
    throw new Error(`Doc: unexpected non-string raw import for path "${_path}"`)
  }
  return parseDoc(raw)
})

// ---------------------------------------------------------------------------
// Lookup helpers.
// ---------------------------------------------------------------------------

export function getDocBySlug(slug: string): Doc | undefined {
  return DOCS.find((d) => d.slug === slug)
}

export function getDocsByCategory(category: DocCategory): Doc[] {
  return DOCS.filter((d) => d.category === category).sort((a, b) => a.order - b.order)
}
