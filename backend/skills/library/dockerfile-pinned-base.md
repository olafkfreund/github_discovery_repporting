---
name: dockerfile-pinned-base
description: Explains how to pin Docker base images to digest SHAs to prevent unexpected changes from upstream image updates.
category: container_security
applies_to:
  - CNTR-002
  - CNTR-004
triggers:
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - docker
  - pinning
  - supply-chain
---

# Dockerfile Pinned Base Image

Referencing a Docker base image by tag (e.g. `FROM python:3.12-slim`) means the image
content can change between builds.  The registry owner can push a new image under the
same tag, silently introducing different dependencies, libraries, or even malicious
code.  Pinning to the image digest (SHA256) makes every build reproducible.

## Pinning Syntax

```dockerfile
# Tag-only (not reproducible — the tag can move).
FROM python:3.12-slim

# Digest-pinned (reproducible — the digest is immutable).
FROM python:3.12-slim@sha256:a8140fce2dc93e8b2b8f2f7a1d4e5b0a1d3f2e1c4b7a9d8e6f5c2a0b3d4e5f6a  # 3.12.7
```

## Finding the Current Digest

```bash
# Pull the image and inspect.
docker pull python:3.12-slim
docker inspect python:3.12-slim --format '{{ index .RepoDigests 0 }}'
# Output: python@sha256:a8140fce...

# Alternatively, use crane (does not pull the full image).
crane digest python:3.12-slim
```

## Automating Updates

Manual digest maintenance is impractical.  Delegate it to tooling:

### Renovate

```json
{
  "extends": ["config:base"],
  "dockerfile": {
    "pinDigests": true
  }
}
```

Renovate will open PRs to update pinned digests when upstream images publish new tags.

### Dependabot

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
```

Note: Dependabot updates tags but does not currently pin to digests.  Renovate is
preferred for digest-level pinning.

## Multi-Stage Builds

Pin every stage, including intermediate build stages:

```dockerfile
FROM node:20-alpine@sha256:abc123...  AS builder  # node 20.11.0
WORKDIR /app
COPY package*.json .
RUN npm ci

FROM nginx:1.27-alpine@sha256:def456...  # nginx 1.27.0
COPY --from=builder /app/dist /usr/share/nginx/html
```

## Base Image Selection

In addition to pinning, choose minimal base images:

- Prefer `*-slim` or `*-alpine` variants — fewer installed packages mean a smaller
  attack surface and faster vulnerability scans.
- Use `distroless` images for statically compiled languages (Go, Rust) — they contain
  no shell or package manager.
- Avoid `:latest` even as an intermediate step — it makes `docker build --no-cache`
  non-deterministic.
