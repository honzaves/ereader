"""Turn an EPUB file into displayable content: metadata, table of contents,
and a single self-contained HTML document. No Qt dependencies."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import ebooklib
from ebooklib import epub

from config import Config


# ── Book metadata ─────────────────────────────────────────────────────────────

@dataclass
class BookMeta:
    path: Path
    title: str
    author: str
    sort_key: tuple[str, str]


def read_epub_meta(path: Path) -> BookMeta:
    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
        raw_titles = book.get_metadata("DC", "title")
        raw_creators = book.get_metadata("DC", "creator")
        title = raw_titles[0][0].strip() if raw_titles else ""
        author = raw_creators[0][0].strip() if raw_creators else ""
    except Exception:
        title, author = "", ""
    display_title = title or path.stem  # fall back to filename when no title
    sort_author = author.lower() if author else "\xff"  # no-author sorts to end
    # Sort by the title actually shown in the list; author breaks ties.
    return BookMeta(path=path, title=display_title, author=author,
                    sort_key=(display_title.lower(), sort_author))


# ── TOC ───────────────────────────────────────────────────────────────────────

@dataclass
class TocEntry:
    title: str
    anchor: str                        # in-page "#id", empty if unresolvable
    children: list["TocEntry"] = field(default_factory=list)


def _resolve_toc_href(href: str, doc_id_map: dict[str, str]) -> str:
    if not href:
        return ""
    if href.startswith("#"):
        return href
    path_part, _, fragment = href.partition("#")
    canonical = _resolve_epub_href(path_part, "")  # TOC hrefs are root-relative
    if fragment:
        return f"#{fragment}"
    sid = doc_id_map.get(canonical, "")
    return f"#{sid}" if sid else ""


def _extract_toc(items, doc_id_map: dict[str, str]) -> list[TocEntry]:
    result = []
    for item in items:
        if isinstance(item, tuple):
            section, children = item
            title = getattr(section, "title", "") or ""
            href = getattr(section, "href", "") or ""
            anchor = _resolve_toc_href(href, doc_id_map)
            result.append(TocEntry(
                title=title,
                anchor=anchor,
                children=_extract_toc(children, doc_id_map),
            ))
        else:
            title = getattr(item, "title", "") or ""
            href = getattr(item, "href", "") or ""
            result.append(TocEntry(
                title=title,
                anchor=_resolve_toc_href(href, doc_id_map),
            ))
    return result


# ── EPUB → HTML ───────────────────────────────────────────────────────────────

def _resolve_epub_href(src: str, doc_name: str) -> str:
    src = unquote(src)
    parts: list[str] = []
    for part in (Path(doc_name).parent / src).as_posix().split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in (".", ""):
            parts.append(part)
    return "/".join(parts)


def build_book_html(path: str, img_dir: Path, cfg: Config) -> tuple[str, list[TocEntry]]:
    book = epub.read_epub(path, options={"ignore_ncx": True})

    img_map: dict[str, str] = {}
    img_cache: dict[str, str] = {}
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_IMAGE:
            continue
        data = item.get_content()
        if not data:
            continue
        key = hashlib.md5(data).hexdigest()
        if key not in img_cache:
            ext = (item.media_type or "image/jpeg").split("/")[-1].replace("jpeg", "jpg")
            (img_dir / f"{key}.{ext}").write_bytes(data)
            img_cache[key] = f"img/{key}.{ext}"
        img_map[item.get_name()] = img_cache[key]

    css_parts: list[str] = []
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_STYLE:
            continue
        css_text = item.get_content().decode("utf-8", errors="ignore")
        doc_name = item.get_name()

        def rewrite_css_url(m, dn=doc_name):
            url = m.group(1).strip("'\" ")
            if url.startswith(("data:", "http", "file:")):
                return m.group(0)
            rel = img_map.get(_resolve_epub_href(url, dn))
            return f"url('{rel}')" if rel else m.group(0)

        css_parts.append(re.sub(r"url\(([^)]+)\)", rewrite_css_url, css_text))

    # Build a map from canonical epub href → section id so cross-doc links resolve.
    spine_items = []
    doc_id_map: dict[str, str] = {}
    for i, (item_id, _) in enumerate(book.spine):
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        section_id = f"epub-s{i}"
        doc_id_map[item.get_name()] = section_id
        spine_items.append((item, section_id))

    body_parts: list[str] = []
    for item, section_id in spine_items:
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        doc_name = item.get_name()

        body_m = re.search(r"<body[^>]*>(.*?)</body>", raw_html,
                           re.IGNORECASE | re.DOTALL)
        body_html = body_m.group(1) if body_m else raw_html

        def rewrite_img_src(m, dn=doc_name):
            src = m.group(1)
            if src.startswith(("data:", "http", "file:")):
                return m.group(0)
            rel = img_map.get(_resolve_epub_href(src, dn))
            return f'src="{rel}"' if rel else m.group(0)

        def rewrite_href(m, dn=doc_name):
            href = m.group(1)
            if href.startswith(("#", "http", "mailto:", "data:", "file:")):
                return m.group(0)
            path_part, _, fragment = href.partition("#")
            if path_part:
                canonical = _resolve_epub_href(path_part, dn)
                sid = doc_id_map.get(canonical, "")
            else:
                sid = doc_id_map.get(dn, "")
            if fragment:
                return f'href="#{fragment}"'
            if sid:
                return f'href="#{sid}"'
            return m.group(0)

        body_html = re.sub(r'src=["\']([^"\']+)["\']', rewrite_img_src,
                           body_html, flags=re.IGNORECASE)
        body_html = re.sub(r'href=["\']([^"\']+)["\']', rewrite_href,
                           body_html, flags=re.IGNORECASE)
        body_parts.append(f'<section class="epub-ch" id="{section_id}">{body_html}</section>')

    font_css = f"font-family: {cfg.font_family};" if cfg.font_family else ""
    default_css = f"""
        * {{ box-sizing: border-box; }}
        html, body {{
            background-color: {cfg.book_bg};
            color: {cfg.text_color};
            font-size: {cfg.font_size}px;
            {font_css}
            margin: 0; padding: 0;
        }}
        body {{
            max-width: 800px;
            margin: 0 auto;
            padding: 24px;
            line-height: 1.6;
        }}
        img {{ max-width: 100%; height: auto; display: block; margin: 1em auto; }}
        .epub-ch {{
            margin-bottom: 2em;
            padding-bottom: 2em;
            border-bottom: 1px solid #333;
        }}
        .epub-ch:last-child {{ border-bottom: none; margin-bottom: 0; }}
    """
    book_css = "".join(f"<style>{css}</style>" for css in css_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{default_css}</style>
{book_css}
</head>
<body>{"".join(body_parts)}</body>
</html>"""

    toc = _extract_toc(book.toc, doc_id_map)
    return html, toc


def status_html(body: str, cfg: Config) -> str:
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        f'body{{background:{cfg.reader_bg};color:{cfg.sidebar_text};'
        f'display:flex;align-items:center;justify-content:center;'
        f'height:100vh;margin:0;font-family:system-ui;font-size:16px;}}'
        f'</style></head><body>{body}</body></html>'
    )
