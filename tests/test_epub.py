import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ebooklib import epub

import epub_content
from config import Config


def make_epub(path, title="The Title", author="The Author"):
    book = epub.EpubBook()
    book.set_identifier("idX")
    if title is not None:
        book.set_title(title)
    if author is not None:
        book.add_author(author)
    c1 = epub.EpubHtml(title="Chapter One", file_name="chap1.xhtml", lang="en")
    c1.content = "<html><body><h1>Chapter One</h1><p>Hello world</p></body></html>"
    book.add_item(c1)
    book.toc = (epub.Link("chap1.xhtml", "Chapter 1", "chap1"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c1]
    epub.write_epub(str(path), book)
    return path


class ResolveEpubHrefTests(unittest.TestCase):
    def test_sibling_relative_to_document(self):
        self.assertEqual(
            epub_content._resolve_epub_href("a.xhtml", "OEBPS/text/b.xhtml"),
            "OEBPS/text/a.xhtml",
        )

    def test_parent_traversal(self):
        self.assertEqual(
            epub_content._resolve_epub_href("../images/x.png", "OEBPS/text/b.xhtml"),
            "OEBPS/images/x.png",
        )

    def test_url_decodes_escapes(self):
        self.assertEqual(
            epub_content._resolve_epub_href("a%20b.xhtml", "OEBPS/c.xhtml"),
            "OEBPS/a b.xhtml",
        )

    def test_current_dir_segments_collapse(self):
        self.assertEqual(epub_content._resolve_epub_href("./a.xhtml", ""), "a.xhtml")


class ResolveTocHrefTests(unittest.TestCase):
    def test_empty_href(self):
        self.assertEqual(epub_content._resolve_toc_href("", {}), "")

    def test_in_page_anchor_passthrough(self):
        self.assertEqual(epub_content._resolve_toc_href("#frag", {}), "#frag")

    def test_document_resolves_via_id_map(self):
        self.assertEqual(
            epub_content._resolve_toc_href("chap1.xhtml", {"chap1.xhtml": "epub-s1"}),
            "#epub-s1",
        )

    def test_fragment_takes_precedence(self):
        self.assertEqual(
            epub_content._resolve_toc_href("chap1.xhtml#sec", {"chap1.xhtml": "epub-s1"}),
            "#sec",
        )

    def test_unknown_document_returns_empty(self):
        self.assertEqual(epub_content._resolve_toc_href("nope.xhtml", {}), "")


class ExtractTocTests(unittest.TestCase):
    def test_flat_entries_resolve_anchors(self):
        items = [SimpleNamespace(title="A", href="chap1.xhtml")]
        result = epub_content._extract_toc(items, {"chap1.xhtml": "epub-s1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "A")
        self.assertEqual(result[0].anchor, "#epub-s1")
        self.assertEqual(result[0].children, [])

    def test_nested_sections(self):
        items = [(
            SimpleNamespace(title="Part", href=""),
            [SimpleNamespace(title="Child", href="#x")],
        )]
        result = epub_content._extract_toc(items, {})
        self.assertEqual(result[0].title, "Part")
        self.assertEqual(len(result[0].children), 1)
        self.assertEqual(result[0].children[0].title, "Child")
        self.assertEqual(result[0].children[0].anchor, "#x")


class ReadEpubMetaTests(unittest.TestCase):
    def test_reads_title_and_author(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_epub(Path(d) / "book.epub", title="Dune", author="Frank Herbert")
            meta = epub_content.read_epub_meta(p)
            self.assertEqual(meta.title, "Dune")
            self.assertEqual(meta.author, "Frank Herbert")
            self.assertEqual(meta.sort_key, ("dune", "frank herbert"))

    def test_falls_back_to_filename_when_no_title(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_epub(Path(d) / "myfile.epub", title=None, author=None)
            meta = epub_content.read_epub_meta(p)
            self.assertEqual(meta.title, "myfile")
            self.assertEqual(meta.author, "")
            # no author sorts to the end
            self.assertEqual(meta.sort_key, ("myfile", "\xff"))

    def test_unreadable_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "broken.epub"
            p.write_text("not an epub")
            meta = epub_content.read_epub_meta(p)
            self.assertEqual(meta.title, "broken")  # stem fallback
            self.assertEqual(meta.author, "")


class BuildBookHtmlTests(unittest.TestCase):
    def test_produces_sectioned_html_and_toc(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_epub(Path(d) / "book.epub")
            html, toc = epub_content.build_book_html(str(p), Path(d), Config())
            self.assertIn('class="epub-ch"', html)
            self.assertIn("Hello world", html)
            self.assertIn("id=\"epub-s1\"", html)
            self.assertEqual([t.title for t in toc], ["Chapter 1"])
            self.assertEqual(toc[0].anchor, "#epub-s1")


class StatusHtmlTests(unittest.TestCase):
    def test_embeds_body_and_colours(self):
        cfg = Config(reader_bg="#abcdef", sidebar_text="#123456")
        html = epub_content.status_html("<p>Hi</p>", cfg)
        self.assertIn("<p>Hi</p>", html)
        self.assertIn("#abcdef", html)
        self.assertIn("#123456", html)


if __name__ == "__main__":
    unittest.main()
