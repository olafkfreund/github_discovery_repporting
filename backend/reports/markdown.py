from __future__ import annotations

"""Markdown report renderer — generates structured .md files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _md_table(headers: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    """Build a Markdown pipe table.

    ``align`` entries: ``"l"`` (left, default), ``"r"`` (right), ``"c"`` (center).
    """
    if align is None:
        align = ["l"] * len(headers)

    sep_map = {"l": ":---", "r": "---:", "c": ":---:"}
    sep = [sep_map.get(a, ":---") for a in align]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in rows:
        # Escape pipes in cell values
        escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")

    return "\n".join(lines)


class MarkdownRenderer:
    """Generate structured Markdown files from report data."""

    def generate_markdown(self, report_data: dict, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        writers = [
            ("00-cover.md", self._write_cover),
            ("01-executive-summary.md", self._write_executive_summary),
            ("02-category-detail.md", self._write_category_detail),
            ("03-recommendations.md", self._write_recommendations),
            ("04-benchmarks.md", self._write_benchmarks),
            ("05-appendix-findings.md", self._write_findings),
        ]

        for filename, writer in writers:
            content = writer(report_data)
            (output_dir / filename).write_text(content, encoding="utf-8")

        logger.info("Markdown report generated in: %s", output_dir)
        return output_dir

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    def _write_cover(self, data: dict) -> str:
        lines = [
            f"# {data.get('report_title', 'DevOps Assessment Report')}",
            "",
            f"**Customer:** {data.get('customer_name', '')}",
            f"**Organisation:** {data.get('org_name', '')}",
            f"**Scan ID:** {data.get('scan_id', '')}",
            f"**Generated:** {data.get('generated_at', '')}",
            f"**Platform:** {data.get('platform_display_name', data.get('platform', ''))}",
            "",
            f"**Overall Score:** {data.get('overall_score', 0):.1f}%",
            f"**DORA Level:** {data.get('dora_level', '')}",
            "",
        ]
        return "\n".join(lines)

    def _write_executive_summary(self, data: dict) -> str:
        lines = [
            "# Executive Summary",
            "",
            data.get("executive_summary", ""),
            "",
            "## Overall Maturity Assessment",
            "",
            data.get("overall_maturity", ""),
            "",
        ]

        risk_highlights = data.get("risk_highlights", [])
        if risk_highlights:
            lines.append("## Risk Highlights")
            lines.append("")
            for risk in risk_highlights:
                lines.append(f"- {risk}")
            lines.append("")

        return "\n".join(lines)

    def _write_category_detail(self, data: dict) -> str:
        lines = ["# Category Detail", ""]

        category_scores: dict = data.get("category_scores", {})
        narratives = {n["category"]: n for n in data.get("category_narratives", [])}
        findings_by_cat = data.get("findings_by_category", {})

        for category, score in category_scores.items():
            lines.append(f"## {category}")
            lines.append("")
            lines.append(f"**Score:** {score:.1f}%")
            lines.append("")

            narrative = narratives.get(category, {})

            strengths = narrative.get("strengths", [])
            if strengths:
                lines.append("### Strengths")
                lines.append("")
                for s in strengths:
                    lines.append(f"- {s}")
                lines.append("")

            weaknesses = narrative.get("weaknesses", [])
            if weaknesses:
                lines.append("### Weaknesses")
                lines.append("")
                for w in weaknesses:
                    lines.append(f"- {w}")
                lines.append("")

            cat_findings = findings_by_cat.get(category, [])
            if cat_findings:
                lines.append("### Key Findings")
                lines.append("")
                headers = ["Check ID", "Name", "Severity", "Status", "Score"]
                rows = [
                    [
                        f.get("check_id", ""),
                        f.get("check_name", ""),
                        f.get("severity", ""),
                        f.get("status", ""),
                        str(f.get("score", 0)),
                    ]
                    for f in cat_findings
                ]
                lines.append(_md_table(headers, rows, ["l", "l", "l", "l", "r"]))
                lines.append("")

        return "\n".join(lines)

    def _write_recommendations(self, data: dict) -> str:
        lines = ["# Recommendations", ""]

        recs = data.get("recommendations", [])
        if recs:
            # Summary table
            headers = ["Priority", "Title", "Category", "Effort", "Impact"]
            rows = [
                [
                    rec.get("priority", ""),
                    rec.get("title", ""),
                    rec.get("category", ""),
                    rec.get("effort", ""),
                    rec.get("impact", ""),
                ]
                for rec in recs
            ]
            lines.append(_md_table(headers, rows))
            lines.append("")

            # Detailed cards
            lines.append("## Details")
            lines.append("")
            for i, rec in enumerate(recs, start=1):
                lines.append(f"### {i}. {rec.get('title', '')}")
                lines.append("")
                lines.append(f"**Priority:** {rec.get('priority', '')}")
                lines.append(f"**Category:** {rec.get('category', '')}")
                lines.append(f"**Effort:** {rec.get('effort', '')}")
                lines.append(f"**Impact:** {rec.get('impact', '')}")
                lines.append("")
                lines.append(rec.get("description", ""))
                lines.append("")
                check_ids = rec.get("related_check_ids", [])
                if check_ids:
                    lines.append(f"**Related Checks:** {', '.join(check_ids)}")
                    lines.append("")

        return "\n".join(lines)

    def _write_benchmarks(self, data: dict) -> str:
        lines = ["# Benchmark Comparisons", ""]

        benchmarks = data.get("benchmark_comparisons", [])
        if benchmarks:
            headers = ["Framework", "Level", "Summary"]
            rows = [
                [
                    b.get("framework", ""),
                    b.get("level", ""),
                    b.get("summary", ""),
                ]
                for b in benchmarks
            ]
            lines.append(_md_table(headers, rows))
            lines.append("")

        return "\n".join(lines)

    def _write_findings(self, data: dict) -> str:
        lines = ["# Appendix: All Findings", ""]

        findings = data.get("all_findings", [])
        if findings:
            headers = ["Check ID", "Name", "Category", "Severity", "Status", "Detail", "Score"]
            rows = [
                [
                    f.get("check_id", ""),
                    f.get("check_name", ""),
                    f.get("category", ""),
                    f.get("severity", ""),
                    f.get("status", ""),
                    (f.get("detail", "") or "")[:100],
                    str(f.get("score", 0)),
                ]
                for f in findings
            ]
            lines.append(_md_table(headers, rows, ["l", "l", "l", "l", "l", "l", "r"]))
            lines.append("")

        return "\n".join(lines)
