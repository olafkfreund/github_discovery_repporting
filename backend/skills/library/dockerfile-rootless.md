---
name: dockerfile-rootless
description: Guides authoring rootless Dockerfiles that drop privileges before the application entrypoint.
category: container_security
applies_to:
  - CNTR-001
  - CNTR-003
  - CNTR-005
triggers:
  - remediation
  - scan_enrichment
version: 1
authored_by: builtin
tags:
  - docker
  - rootless
  - least-privilege
---

# Dockerfile Rootless Pattern

Running container processes as root is the single most common container security
misconfiguration.  A container escape from a root-running process gives the attacker
host-level privileges.  This skill explains how to author a Dockerfile that drops
to a non-root user before the application starts.

## Pattern

```dockerfile
FROM python:3.12-slim

# Create a dedicated non-root user and group.
# Using a numeric UID/GID (1001) ensures portability across base image changes.
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

# Copy dependency manifests first (improves layer caching).
COPY --chown=appuser:appgroup requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source with correct ownership.
COPY --chown=appuser:appgroup . .

# Drop to non-root before ENTRYPOINT/CMD.
USER appuser

EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Key Rules

1. **Use a numeric UID** — Kubernetes `securityContext.runAsNonRoot: true` validates
   the numeric UID, not the string name.  Using `USER appuser` alone fails this check
   if the base image maps the name to UID 0.
2. **Create the user in a single `RUN` layer** — combining `groupadd` and `useradd`
   avoids an intermediate layer with world-writable home directories.
3. **Set `--chown` on `COPY` instructions** — this avoids a separate `chown` step
   that would duplicate layer size.
4. **Do not install packages as root in the final stage** — if you need root for
   package installation, use a multi-stage build and copy only the built artefacts.

## Multi-Stage Example

```dockerfile
# Build stage (root is acceptable here — it never runs).
FROM python:3.12 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Runtime stage (rootless).
FROM python:3.12-slim
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/sh appuser
COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup src/ /app/
USER 1001
WORKDIR /app
ENTRYPOINT ["python", "main.py"]
```

## Kubernetes SecurityContext

Pair the rootless Dockerfile with an explicit Kubernetes security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
```

## Verification

```bash
docker build -t myimage .
docker inspect myimage --format '{{ .Config.User }}'
# Expected output: 1001 (or "appuser")
```
