import os
import io
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import re

import requests
from pypdf import PdfReader
import pdfplumber


logger = logging.getLogger(__name__)


def download_file_to_bytes(url: str) -> bytes:
    """Download a file from an http(s) URL or read from local /uploads path.

    If the URL starts with http, fetch over the network. Otherwise, if it contains
    '/uploads/', map to local uploads folder relative to project root and read bytes.
    Returns empty bytes on failure.
    """
    try:
        logger.info("download_file_to_bytes: start url=%s", url)
        # Prefer local mapping for anything under /uploads/, even if the URL is http(s)
        if "/uploads/" in url:
            filename = url.split("/uploads/")[-1]
            project_root = Path(__file__).resolve().parents[3]
            backend_dir = Path(__file__).resolve().parents[2]
            candidates = [
                project_root / "uploads" / filename,
                backend_dir / "uploads" / filename,
                Path("uploads") / filename,
            ]
            for p in candidates:
                if p.exists():
                    logger.info("download_file_to_bytes: reading local path=%s", str(p))
                    data = p.read_bytes()
                    logger.info("download_file_to_bytes: local bytes=%d", len(data))
                    return data
            logger.warning("download_file_to_bytes: no local file found for %s (checked %s)", filename, ", ".join(str(c) for c in candidates))
            # If it was an http URL to uploads and local not found, only then consider http fetch
            # Avoid self-fetch deadlocks for local hosts
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if host in {"0.0.0.0", "127.0.0.1", "localhost"}:
                logger.warning("download_file_to_bytes: skipping HTTP fetch for local host=%s to avoid timeout; returning empty", host)
                return b""
            # else fall through to http fetch below

        # HTTP(S) fetch for non-uploads or when local mapping not applicable
        if url.startswith("http://") or url.startswith("https://"):
            # Shorter timeout for potentially slow sources; callers handle empty result
            timeout = 15
            try:
                resp = requests.get(url, timeout=timeout)
                resp.raise_for_status()
                logger.info("download_file_to_bytes: http fetched bytes=%d from %s", len(resp.content), url)
                return resp.content
            except requests.RequestException as re:
                logger.exception("download_file_to_bytes: http fetch failed for %s: %s", url, re)
                return b""
        # Fallback: if path exists directly
        path = Path(url)
        if path.exists():
            logger.info("download_file_to_bytes: reading direct path=%s", str(path))
            data = path.read_bytes()
            logger.info("download_file_to_bytes: direct bytes=%d", len(data))
            return data
    except Exception as e:
        logger.exception("download_file_to_bytes: error for url=%s: %s", url, e)
    return b""


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract full text from a PDF given as bytes. Returns empty string on failure.

    Attempts pypdf first, then falls back to pdfminer.six if needed. Logs counts and extractor used.
    """
    if not file_bytes:
        logger.warning("extract_pdf_text: empty file bytes")
        return ""
    # Try pypdf first
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                texts.append("")
        text = "\n".join([t for t in texts if t])
        logger.info("extract_pdf_text: pypdf extracted chars=%d", len(text))
        if text.strip():
            return text
    except Exception as e:
        logger.warning("extract_pdf_text: pypdf failed: %s", e)

    # Fallback to pdfminer.six
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        text = pdfminer_extract_text(io.BytesIO(file_bytes)) or ""
        logger.info("extract_pdf_text: pdfminer extracted chars=%d", len(text))
        return text
    except Exception as e:
        logger.exception("extract_pdf_text: pdfminer failed: %s", e)
        return ""


def to_markdown(text: str) -> str:
    """Convert extracted plain text into lightweight Markdown.

    - Normalizes newlines
    - Converts common bullet glyphs to markdown dashes
    - Trims trailing spaces per line
    - Collapses 3+ blank lines to at most 2
    """
    if not text:
        return ""
    # Normalize line endings
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Convert common bullet characters to '- '
    bullet_chars = ["•", "◦", "·", "‣", "▪", "▫", "●", "○"]
    for ch in bullet_chars:
        t = t.replace(f"\n{ch} ", "\n- ")
        t = t.replace(f"\n{ch}\t", "\n- ")
        t = t.replace(f"\n{ch}", "\n- ")
    # Normalize hyphen bullets ' - ' and '* '
    lines = t.split("\n")
    norm_lines = []
    bullet_re = re.compile(r"^\s*[\-\*]\s+")
    numbered_re = re.compile(r"^\s*(\d+)[\.)]\s+")
    for ln in lines:
        ln2 = ln
        # Numbered lists to '1. '
        m = numbered_re.match(ln2)
        if m:
            num = m.group(1)
            ln2 = numbered_re.sub(f"{num}. ", ln2, count=1)
        # Normalize bullets to '- '
        if bullet_re.match(ln2):
            ln2 = bullet_re.sub("- ", ln2, count=1)
        norm_lines.append(ln2)
    # Add markdown headings for likely titles (uppercase dominant and not too long)
    md_ready = []
    for ln in norm_lines:
        stripped = ln.strip()
        if stripped and not stripped.startswith(('- ', '* ', '1.')):
            letters = re.sub(r"[^A-Za-z]", "", stripped)
            if letters and stripped == stripped.upper() and len(stripped) <= 80:
                ln = f"### {stripped.title()}"
        md_ready.append(ln)
    # Trim trailing spaces per line
    lines = [ln.rstrip() for ln in md_ready]
    # Collapse 3+ blank lines
    md_lines = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                md_lines.append("")
        else:
            blank_run = 0
            md_lines.append(ln)
    md = "\n".join(md_lines).strip()
    logger.info("to_markdown: produced markdown chars=%d", len(md))
    return md


def _render_md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    # Clean cells: replace newlines and escape pipes
    clean = []
    for r in rows:
        clean.append([(c or "").replace("\n", "<br>").replace("|", "\\|") for c in r])
    header = clean[0]
    # If header has any empty cells, synthesize header
    if any(cell.strip() == "" for cell in header):
        header = [f"Col{i+1}" for i in range(len(header))]
        body = clean
    else:
        body = clean[1:]
    line_header = "| " + " | ".join(header) + " |"
    line_sep = "| " + " | ".join(["---"] * len(header)) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join([line_header, line_sep, *body_lines])


def extract_pdf_markdown(file_bytes: bytes) -> str:
    """Extract Markdown from PDF bytes using pdfplumber with heuristics for headings, lists, code, and tables.

    Falls back to empty string if anything fails; caller will handle fallback.
    """
    if not file_bytes:
        logger.warning("extract_pdf_markdown: empty file bytes")
        return ""
    try:
        out_lines: list[str] = []
        tables_rendered = 0
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # Gather chars for font size heuristics
                chars = page.chars or []
                avg_size = 0.0
                if chars:
                    avg_size = sum(float(c.get("size", 0.0) or 0.0) for c in chars) / max(len(chars), 1)

                # Build lines from chars grouped by y (top)
                lines_map: dict[float, list[dict]] = {}
                for ch in chars:
                    top = float(ch.get("top", 0.0))
                    key = round(top, 1)
                    lines_map.setdefault(key, []).append(ch)
                line_keys = sorted(lines_map.keys())

                # Detect tables
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []

                # Render text lines first
                code_block_open = False
                last_indent = 0.0
                for y in line_keys:
                    line_chars = sorted(lines_map[y], key=lambda c: float(c.get("x0", 0.0)))
                    if not line_chars:
                        continue
                    text_line = "".join(c.get("text", "") for c in line_chars)
                    if not text_line.strip():
                        if code_block_open:
                            out_lines.append("")
                        else:
                            out_lines.append("")
                        continue
                    # Indentation heuristic
                    indent = float(line_chars[0].get("x0", 0.0))
                    indent_level = 0
                    try:
                        indent_level = int(max(0, (indent - last_indent)) // 20)
                    except Exception:
                        indent_level = 0
                    # Heading heuristic: average size of line vs page avg
                    line_avg = sum(float(c.get("size", 0.0) or 0.0) for c in line_chars) / max(len(line_chars), 1)
                    heading_prefix = ""
                    if line_avg > avg_size * 1.6:
                        heading_prefix = "# "
                    elif line_avg > avg_size * 1.3:
                        heading_prefix = "## "
                    elif line_avg > avg_size * 1.15:
                        heading_prefix = "### "

                    # Code line heuristic: monospaced font or code char ratio
                    fontnames = " ".join((c.get("fontname", "") or "") for c in line_chars).lower()
                    code_chars = sum(1 for ch in text_line if ch in "{}();<>[]`|/\\_")
                    is_code_line = ("mono" in fontnames or "courier" in fontnames or (len(text_line) > 0 and code_chars / max(len(text_line), 1) > 0.25))

                    # List detection
                    stripped = text_line.lstrip()
                    bullet = None
                    if re.match(r"^[\-\*]\s+", stripped):
                        bullet = "- "
                    elif re.match(r"^\d+[\.)]\s+", stripped):
                        num = re.match(r"^(\d+)[\.)]\s+", stripped).group(1)
                        bullet = f"{num}. "
                    elif stripped[:1] in {"•", "◦", "·", "‣", "▪", "▫", "●", "○"}:
                        bullet = "- "

                    # Bold/italic at line level (approximate)
                    is_bold = any("bold" in ((span.get("fontname", "") or "").lower()) for span in line_chars)
                    is_italic = any(
                        ("italic" in ((span.get("fontname", "") or "").lower())) or 
                        ("oblique" in ((span.get("fontname", "") or "").lower()))
                        for span in line_chars
                    ) 
                    content = text_line.strip()
                    if is_bold:
                        content = f"**{content}**"
                    if is_italic:
                        content = f"_{content}_"

                    # Code block grouping
                    if is_code_line and not code_block_open:
                        out_lines.append("```")
                        code_block_open = True
                    if not is_code_line and code_block_open:
                        out_lines.append("```")
                        code_block_open = False

                    if bullet:
                        out_lines.append("  " * indent_level + bullet + content)
                    elif heading_prefix:
                        # Avoid wrapping headings with bold/italic markers
                        h_content = text_line.strip()
                        out_lines.append(f"{heading_prefix}{h_content}")
                    else:
                        out_lines.append(content)

                    last_indent = indent

                if code_block_open:
                    out_lines.append("```")
                    code_block_open = False

                # Append tables at end of page (simple approach)
                for tbl in tables:
                    if not tbl:
                        continue
                    md_tbl = _render_md_table(tbl)
                    if md_tbl.strip():
                        tables_rendered += 1
                        out_lines.append("")
                        out_lines.append(md_tbl)
                        out_lines.append("")

        md = "\n".join(out_lines)
        # Post-process: collapse 3+ blank lines
        md = re.sub(r"\n{3,}", "\n\n", md).strip()
        logger.info("extract_pdf_markdown: produced markdown chars=%d", len(md))
        return md
    except Exception as e:
        logger.exception("extract_pdf_markdown: pdfplumber failed: %s", e)
        return ""


