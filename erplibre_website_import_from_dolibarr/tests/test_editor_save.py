# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""An imported page saved through the website editor.

The editor's server side is replayed over HTTP: a designer loads the
page, which Odoo renders with inherit_branding, and the section to save
is the element that carries data-oe-id and data-oe-xpath there. Its
outerHTML goes, with its text nodes escaped once more as the editor
does, to ir.ui.view.save over JSON-RPC.
"""

import copy
import html

from lxml import html as lhtml

from ..dolibarr_site.tests.fixtures import demo_zip_bytes
from .common import DolibarrImportCase

INTRO = "<p>Plain introduction.</p>"
# Text that reads as markup or as an expression once unescaped: it must
# stay text after the editor round trip.
TRICKY = (
    "<p>Plain introduction. a &amp; b &lt;b&gt;bold&lt;/b&gt; {{ 1234*3 }}</p>"
)
SNIPPET = (
    '<section class="s_text_block" data-snippet="s_text_block">'
    '<div class="container"><p>New snippet</p></div></section>'
)
# Elements whose text the editor sends as it is (wysiwyg.js,
# _getEscapedElement).
RAW_TEXT = ("object", "iframe", "script", "style")


def _kept_as_is(el):
    """True when the editor leaves the text directly inside el alone:
    el or one of its ancestors is a RAW_TEXT element or a field of a
    record other than a view (data-oe-model other than ir.ui.view)."""
    for node in (el, *el.iterancestors()):
        if node.tag in RAW_TEXT:
            return True
        model = node.get("data-oe-model")
        if model and model != "ir.ui.view":
            return True
    return False


def editor_value(element, extra=None):
    """outerHTML of element as the website editor sends it to save().

    extra, an HTML fragment, is appended inside element first, as a
    snippet dropped at its end. The text nodes that _kept_as_is() does
    not exclude are HTML-escaped once, then serialised, which escapes
    them again. One difference with a browser is left: lxml writes a
    no-break space as &#160; where outerHTML writes &nbsp;, which parse
    to the same text.
    """
    clone = copy.deepcopy(element)
    clone.tail = None
    if extra:
        clone.append(lhtml.fragment_fromstring(extra))
    for el in clone.iter():
        if not isinstance(el.tag, str):
            continue
        if el.text and not _kept_as_is(el):
            el.text = html.escape(el.text, quote=False)
        parent = el.getparent()
        if parent is not None and el.tail and not _kept_as_is(parent):
            el.tail = html.escape(el.tail, quote=False)
    return lhtml.tostring(clone, encoding="unicode")


class TestEditorSave(DolibarrImportCase):
    def import_site(self, **kw):
        run = self.cli_import(
            zip_bytes=demo_zip_bytes(
                sql_edit=lambda sql: sql.replace(INTRO, TRICKY), **kw
            )
        )
        self.assertEqual(run.state, "done", run.error or "")
        return run

    def home(self):
        return self.env["website.page"].search(
            [("website_id", "=", self.website.id), ("url", "=", "/home")]
        )

    def branded(self, css_class):
        """The branded element of /home with css_class, as a designer
        receives it."""
        self.authenticate("admin", "admin")
        response = self.url_open("/home")
        self.assertEqual(response.status_code, 200)
        tree = lhtml.fromstring(response.text)
        (element,) = tree.xpath(
            "//*[@data-oe-xpath][contains(concat(' ', @class, ' '),"
            " ' %s ')]" % css_class
        )
        return element

    def save(self, element, extra=None):
        """ir.ui.view.save of element, as a designer, like the editor."""
        self.authenticate("admin", "admin")
        self.make_jsonrpc_request(
            "/web/dataset/call_kw/ir.ui.view/save",
            {
                "model": "ir.ui.view",
                "method": "save",
                "args": [
                    int(element.get("data-oe-id")),
                    editor_value(element, extra),
                    element.get("data-oe-xpath"),
                ],
                "kwargs": {
                    "context": {
                        "website_id": self.website.id,
                        "lang": "en_US",
                        "delay_translations": False,
                    }
                },
            },
        )

    def visitor_home(self):
        self.authenticate(None, None)
        response = self.url_open("/home")
        self.assertEqual(response.status_code, 200)
        return self.section(response.text)

    def test_snippet_between_qweb_sections_keeps_qweb(self):
        self.import_site()
        view = self.home().view_id
        intro = self.branded("intro")
        self.assertEqual(int(intro.get("data-oe-id")), view.id)
        self.assertEqual(intro.get("data-oe-model"), "ir.ui.view")
        before = self.visitor_home()
        self.save(intro, SNIPPET)
        view.invalidate_recordset()
        saved = view.arch_db
        self.assertIn("New snippet", saved)
        self.assertIn('t-out="res_company.name"', saved)
        self.assertIn("t-foreach", saved)
        self.assertIn(
            "erplibre_website_import_from_dolibarr.social_links", saved
        )
        self.assertEqual(view.website_id, self.website)
        after = self.visitor_home()
        self.assertIn("New snippet", after)
        self.assertIn("Example Co", after)
        self.assertIn("info@example.org", after)
        self.assertIn("First news", after)
        # The text escaped by the import is still text once saved.
        for text in ("a &amp; b &lt;b&gt;bold&lt;/b&gt;", "{{ 1234*3 }}"):
            self.assertIn(text, before)
            self.assertIn(text, after)
        self.assertNotIn("<b>bold", after)
        self.assertNotIn("3702", after)

    def test_saved_page_is_a_local_edit_on_reimport(self):
        self.import_site()
        view = self.home().view_id
        self.save(self.branded("intro"), SNIPPET)
        same = self.import_site()
        self.assertFalse(self.run_lines(same, "local_edit_kept"))
        self.assertIn("New snippet", self.visitor_home())
        changed = self.cli_import(
            zip_bytes=demo_zip_bytes(
                sql_edit=lambda sql: sql.replace(INTRO, TRICKY).replace(
                    "Plain introduction.", "Changed introduction."
                )
            )
        )
        kept = self.run_lines(changed, "local_edit_kept")
        self.assertEqual(kept.mapped("page_ref"), ["home"])
        home = self.visitor_home()
        self.assertIn("New snippet", home)
        self.assertNotIn("Changed introduction.", home)
        forced = self.cli_import(
            zip_bytes=demo_zip_bytes(
                sql_edit=lambda sql: sql.replace(
                    "Plain introduction.", "Changed introduction."
                )
            ),
            overwrite_local_edits=True,
        )
        self.assertTrue(self.run_lines(forced, "local_edit_overwritten"))
        view.invalidate_recordset()
        self.assertNotIn("New snippet", view.arch_db)
        self.assertIn("Changed introduction.", self.visitor_home())
