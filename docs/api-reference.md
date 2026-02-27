# API Reference

All endpoints are prefixed with `/api`. The API uses JSON for request/response bodies and returns standard HTTP status codes.

## Health

### `GET /api/health`

Liveness probe.

**Response:** `200 OK`
```json
{"status": "ok"}
```

---

## Customers

### `POST /api/customers/`

Create a new customer. A URL-friendly slug is auto-generated from the name.

**Request Body:**
```json
{
  "name": "Acme Corp",
  "contact_email": "admin@acme.com",
  "notes": "Enterprise customer"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "contact_email": "admin@acme.com",
  "notes": "Enterprise customer",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### `GET /api/customers/`

List all customers. Supports pagination via `?skip=0&limit=100`.

### `GET /api/customers/{customer_id}`

Get a single customer by UUID.

### `PUT /api/customers/{customer_id}`

Partial update. Slug is regenerated if name changes.

### `DELETE /api/customers/{customer_id}`

Delete customer and all associated records (connections, scans, findings, reports). Returns `204 No Content`.

---

## Platform Connections

### `POST /api/customers/{customer_id}/connections`

Register a platform connection. Credentials are Fernet-encrypted before storage.

**Request Body:**
```json
{
  "platform": "github",
  "display_name": "GitHub Org",
  "org_or_group": "my-org",
  "auth_type": "token",
  "credentials": {"token": "ghp_..."},
  "base_url": null
}
```

### `GET /api/customers/{customer_id}/connections`

List all connections for a customer.

### `PUT /api/connections/{connection_id}`

Update connection fields. Re-encrypts credentials if supplied.

### `DELETE /api/connections/{connection_id}`

Delete a connection. Returns `204 No Content`.

### `POST /api/connections/{connection_id}/validate`

Live credential validation against the platform API. On success, stamps `last_validated_at`.

**Response:** `200 OK`
```json
{
  "valid": true,
  "message": "Connection validated successfully"
}
```

---

## Scans

### `POST /api/customers/{customer_id}/scans`

Trigger a new scan. The scan runs asynchronously in the background.

**Request Body:**
```json
{
  "connection_id": "uuid"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "status": "pending",
  "customer_id": "uuid",
  "connection_id": "uuid",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### `GET /api/customers/{customer_id}/scans`

List all scans for a customer, ordered newest first.

### `GET /api/scans/{scan_id}`

Get a scan by UUID. Includes status, timestamps, total repos, and error message if failed.

### `GET /api/scans/{scan_id}/findings`

List findings for a scan. Supports query filters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter by category enum value |
| `severity` | string | Filter by severity level |
| `status` | string | Filter by check status |

**Response:** Array of finding objects with check details, status, evidence, and score.

### `GET /api/scans/{scan_id}/scores`

Get per-category scores for a scan.

**Response:** Array of score objects:
```json
[
  {
    "category": "repo_governance",
    "score": 8.5,
    "max_score": 12.0,
    "weight": 0.10,
    "finding_count": 12,
    "pass_count": 8,
    "fail_count": 3
  }
]
```

---

## Reports

### `POST /api/scans/{scan_id}/reports`

Generate a PDF report for a completed scan. Runs asynchronously.

**Request Body:**
```json
{
  "title": "Q1 2024 DevOps Assessment",
  "template_id": "uuid (optional)"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "status": "pending",
  "scan_id": "uuid"
}
```

### `GET /api/reports/{report_id}`

Get full report metadata including AI summary, recommendations, scores, and DORA level.

### `GET /api/reports/{report_id}/download`

Stream the generated PDF file.

**Response:** `200 OK` with `Content-Type: application/pdf`

### `GET /api/customers/{customer_id}/reports`

List all reports for a customer, newest first.

### Report Templates

### `GET /api/templates`

List all report templates.

### `POST /api/templates`

Create a new report template.

**Request Body:**
```json
{
  "name": "Custom Template",
  "description": "Template with custom branding",
  "accent_color": "#1a73e8",
  "include_sections": ["executive_summary", "category_detail", "recommendations"],
  "custom_css": "..."
}
```

### `PUT /api/templates/{template_id}`

Update a report template (full replacement).

---

## Dashboard

### `GET /api/dashboard/stats`

Aggregate platform statistics.

**Response:**
```json
{
  "total_customers": 12,
  "total_scans": 45,
  "total_reports": 30,
  "recent_scan_count": 8
}
```

### `GET /api/dashboard/recent-scans`

The 10 most recently created scans across all customers.
