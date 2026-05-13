---
slug: getting-started
title: Getting Started with BPS
category: getting-started
order: 10
summary: Learn how BPS scans GitHub, GitLab, and Azure DevOps organisations and turns findings into auditable remediation PRs in five minutes.
audience: [end-user, admin]
last_reviewed: 2026-05-13
---

# Getting Started with BPS

BPS (Best Practice Scanner) is a multi-platform DevOps assessment tool that scans your GitHub, GitLab, and Azure DevOps organisations, evaluates repositories against industry best practices, uses Claude AI for intelligent analysis, and generates auditable PDF/Excel reports — all from a single web interface.

> **Before you begin:** BPS runs entirely within your network. No repository content leaves your infrastructure. Only metadata (branch protection rules, CI/CD configuration presence, dependency manifests) is read during a scan.

## What BPS does

BPS connects to your DevOps platforms using a Personal Access Token (PAT) or equivalent credential. It then runs a 16-domain scanner against every repository in the organisation, checking ~169 controls across areas such as CI/CD pipeline hygiene, secrets management, dependency safety, container security, identity & access, and compliance.

After scanning, BPS sends the aggregated findings — never raw source code — to a Claude AI model running in your configured LLM provider. Claude produces an executive summary, a prioritised list of recommendations, and a remediation roadmap. The results are exported to a PDF report (suitable for board-level review), an Excel workbook (suitable for engineering leads), and a Markdown bundle (suitable for version control).

When you are ready to act on the findings, BPS can open automated remediation Pull Requests through its agentic workflow. The agent runs in your CI environment (or a managed backend worker), is governed by a remediation policy with per-month cost caps, an allow/block path list, and a global kill switch — so you stay in control at all times.

```
┌────────────┐   PAT    ┌────────────────┐   findings   ┌─────────────┐
│  GitHub    │────────► │  Scanner       │────────────► │  AI Analyser│
│  GitLab    │          │  (169 checks)  │              │  (Claude)   │
│  Azure DevOps│        └────────────────┘              └──────┬──────┘
└────────────┘                                                  │ summary +
                                                               │ recommendations
                                                               ▼
                                                     ┌─────────────────┐
                                                     │  Reports        │
                                                     │  PDF / Excel /  │
                                                     │  Markdown Zip   │
                                                     └────────┬────────┘
                                                              │ optionally
                                                              ▼
                                                     ┌─────────────────┐
                                                     │  Agentic        │
                                                     │  Remediation    │
                                                     │  (PRs + audit)  │
                                                     └─────────────────┘
```

## Five-minute quickstart

Follow these steps to get your first scan and report in about five minutes.

1. **Add a customer** — Navigate to [/customers](/customers) and click "Add customer". A *customer* in BPS is a logical grouping (typically a client organisation or a business unit). Give it a name and an optional description.

2. **Connect a platform** — On the customer detail page, click "Add connection" and choose your platform (GitHub, GitLab, or Azure DevOps). Enter your PAT and the organisation or project scope. See [Connecting GitHub / GitLab / Azure DevOps](/help/platform-connections) for the exact PAT scopes required per provider. Click "Test connection" to verify credentials before saving.

3. **Trigger your first scan** — On the customer detail page, click "Run scan". Select the connection you just created. Optionally choose a scan profile (or leave it as the default to scan all 16 domains at full weight). Click "Start scan" and watch the live progress indicator. See [Running your first scan](/help/first-scan) for details on what each status means.

4. **Read the results and download a report** — Once the scan completes, click "View results" to open the [scan results](/help/scan-results) page. Review the category scores, severity bands, and AI-generated recommendations. Use the "Download PDF" or "Download Excel" buttons to get the report. See [Generating and downloading reports](/help/reports) for format details.

5. **Enable agentic remediation when ready** — If you want BPS to open automated PRs, navigate to Settings → Remediation Policy and configure cost caps and the allow/block path list. Then on the scan results page, click "Start remediation". See [Agentic remediation overview](/help/remediation-overview) for the full lifecycle.

## Where to go next

- [Connecting GitHub / GitLab / Azure DevOps](/help/platform-connections) — PAT scopes, org vs project scoping, troubleshooting failed connections.
- [Running your first scan](/help/first-scan) — Step-by-step walkthrough with screenshots of every status state.
- [Reading scan results](/help/scan-results) — How category scores are computed, what the severity bands mean, and how to read the evidence panel.
- [Customising scan profiles](/help/scan-profiles) — Toggle individual checks on/off and tune per-check thresholds for your organisation's risk appetite.
- [Agentic remediation overview](/help/remediation-overview) — Backend vs CI runtime modes, safety nets, and the remediation lifecycle.
- [Compliance & audit](/help/compliance) — The REQ-* compliance framework and the hash-chained audit log.
