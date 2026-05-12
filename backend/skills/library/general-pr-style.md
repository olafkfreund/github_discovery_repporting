---
name: general-pr-style
description: Cross-cutting style guidance for writing clear pull request titles, descriptions, and commit messages.
category: general
applies_to: []
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - pull-request
  - commit-messages
  - communication
---

# General Pull Request Style

Clear pull request descriptions reduce review friction and improve the searchability of
the repository's history.  This skill applies across all repositories regardless of
the language or domain.

## PR Title

A good PR title follows the Conventional Commits format:

```
<type>(<scope>): <short summary in imperative mood>
```

Examples:

```
feat(auth): add PKCE flow for public OAuth clients
fix(api): return 400 instead of 500 for malformed JSON body
chore(deps): update boto3 to 1.34.0
refactor(billing): extract InvoiceCalculator from OrderService
docs(readme): add local development setup instructions
```

Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `perf`, `ci`, `build`,
`revert`.

Keep the title under 72 characters so it displays without truncation in most UIs.

## PR Description

Use a structured template:

```markdown
## Summary

One paragraph explaining what this change does and why.

## Motivation

What problem does this solve?  Link to the issue or ticket this addresses.

Closes #123

## Changes

- List the main logical changes made (not a diff summary).
- Highlight anything non-obvious about the implementation approach.

## Testing

Describe how the change was tested:
- Unit tests added: yes/no — which files.
- Integration tests: yes/no.
- Manual testing steps if relevant.

## Checklist

- [ ] Tests pass locally.
- [ ] Documentation updated if behaviour changed.
- [ ] No unrelated changes included.
- [ ] Breaking changes documented in CHANGELOG or migration notes.
```

Add this template to `.github/pull_request_template.md` to make it the default for
all new PRs in the repository.

## Commit Messages

Individual commits should also be readable in isolation:

- **Subject line** — imperative mood, under 72 characters, no trailing period.
- **Body** — explain *why*, not *what*.  The diff shows what changed; the body explains
  the reasoning.
- **Trailer** — reference the issue or ticket: `Refs: #123` or `Fixes: #123`.

```
fix(checkout): prevent double-charge on payment retry

The payment gateway occasionally returns a timeout without charging the
customer.  The previous code retried immediately, which could succeed on
the second attempt even if the first had gone through asynchronously.

Add an idempotency key derived from the cart ID and attempt number so
the gateway deduplicates the request server-side.

Fixes: #456
```

## Review Response Etiquette

- Address every comment before re-requesting review, even if just to explain why
  no change was made.
- Use the "Resolve conversation" button only after the issue is actually resolved.
- Keep discussion threads on-topic; take tangential discussions to a separate issue.
