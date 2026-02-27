from __future__ import annotations

"""WeasyPrint-based PDF rendering for the DevOps Discovery report.

This module is deliberately kept thin: it owns the Jinja2 environment and
the WeasyPrint invocation, nothing else.  All business logic about what goes
into the report lives in :mod:`backend.reports.generator`.
"""

import logging
from pathlib import Path

import jinja2

logger = logging.getLogger(__name__)


class PDFRenderer:
    """Render Jinja2 HTML templates and convert them to PDF via WeasyPrint.

    Parameters:
        templates_dir: Filesystem path to the directory that contains the
            Jinja2 ``.html`` template files.
        styles_dir: Filesystem path to the directory that contains
            ``report.css`` (the print stylesheet).

    Example::

        renderer = PDFRenderer(
            templates_dir=Path("backend/reports/templates"),
            styles_dir=Path("backend/reports/styles"),
        )
        html = renderer.render_report_html(report_data)
        output = renderer.generate_pdf(html, Path("/tmp/report.pdf"))
    """

    # Section template names, rendered in order and stitched into base.html.
    _SECTION_TEMPLATES: tuple[str, ...] = (
        "executive_summary.html",
        "category_detail.html",
        "recommendations.html",
        "benchmarks.html",
        "appendix.html",
    )

    def __init__(self, templates_dir: Path, styles_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._styles_dir = styles_dir
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(templates_dir)),
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.Undefined,
        )
        # Pre-read the CSS so it can be inlined; this avoids WeasyPrint having
        # to resolve a relative file:// URL, which can behave differently
        # across environments.
        self._css_content: str = self._load_css()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_css(self) -> str:
        """Read and return the contents of ``report.css``.

        Returns:
            The raw CSS string, or an empty string if the file is absent.
        """
        css_path = self._styles_dir / "report.css"
        if css_path.exists():
            return css_path.read_text(encoding="utf-8")
        logger.warning("report.css not found at %s; PDF will be unstyled.", css_path)
        return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_html(self, template_name: str, context: dict) -> str:
        """Render a single Jinja2 template to an HTML string.

        Parameters:
            template_name: Filename relative to *templates_dir*
                (e.g. ``"executive_summary.html"``).
            context: Variables to expose to the template.

        Returns:
            Rendered HTML string.

        Raises:
            jinja2.TemplateNotFound: When *template_name* does not exist.
        """
        template = self._env.get_template(template_name)
        return template.render(**context)

    def render_report_html(self, report_data: dict) -> str:
        """Render the complete report as a single self-contained HTML string.

        Each section template is rendered independently using *report_data*
        as the shared context.  The rendered sections are then injected into
        ``base.html`` as the ``content`` block.

        Parameters:
            report_data: Flat dictionary of all values needed by any section
                template.  See :meth:`~backend.reports.generator.ReportGenerator.generate_report`
                for the expected keys.

        Returns:
            Full HTML document string suitable for passing to
            :meth:`generate_pdf`.
        """
        # Render each section independently.
        section_html_parts: list[str] = []
        for template_name in self._SECTION_TEMPLATES:
            try:
                part = self.render_html(template_name, report_data)
                section_html_parts.append(part)
            except jinja2.TemplateNotFound:
                logger.warning(
                    "Section template '%s' not found; skipping.", template_name
                )

        combined_content = "\n".join(section_html_parts)

        # Build the base template context, injecting the pre-rendered
        # section content as a ``content`` block via the Jinja2 environment.
        # Because base.html uses ``{% block content %}{% endblock %}``, we
        # render it by adding the combined sections as a context variable
        # and having the base template reference it.
        base_template_source = (
            "{% extends 'base.html' %}"
            "{% block content %}" + combined_content + "{% endblock %}"
        )
        base_tmpl = self._env.from_string(base_template_source)
        full_context = {
            **report_data,
            "css_content": self._css_content,
        }
        return base_tmpl.render(**full_context)

    def generate_pdf(self, html: str, output_path: Path) -> Path:
        """Convert an HTML string to a PDF file using WeasyPrint.

        Parameters:
            html: Complete HTML document string (as returned by
                :meth:`render_report_html`).
            output_path: Destination path for the generated ``.pdf`` file.
                The parent directory must already exist.

        Returns:
            The resolved *output_path* after the file has been written.

        Raises:
            OSError: When the parent directory does not exist or is not
                writable.
        """
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Generating PDF report at %s", output_path)

        # WeasyPrint resolves any remaining relative URLs against base_url.
        # Pointing it at the styles directory allows @font-face or background
        # image references in the CSS to resolve correctly if they are ever
        # added.
        base_url = self._styles_dir.resolve().as_uri() + "/"

        import weasyprint  # lazy import: requires pango/cairo system libs

        doc = weasyprint.HTML(string=html, base_url=base_url)
        doc.write_pdf(str(output_path))

        logger.info("PDF written (%d bytes)", output_path.stat().st_size)
        return output_path
