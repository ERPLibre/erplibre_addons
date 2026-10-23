# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""What a visitor gets after a zip import, checked over HTTP."""

import base64
import json
import re

import lxml.html
from lxml import etree

from odoo.tests.common import new_test_user

from ..dolibarr_site.tests.fixtures import demo_zip_bytes
from .common import DolibarrImportCase
from .test_writer import page_row

# A page whose markup tries every way into QWeb or the browser: engine
# directives, template expressions, an inline script, an event handler,
# a script URL and markup encoded as text. None of it may be live once
# served; the text parts stay visible as text.
HOSTILE = page_row(
    17,
    "hostile",
    "Hostile",
    '<div class="probe" t-att-class="1234*3" t-att-data-x="1234*3">T-ATT</div>'
    '<t t-out="1234*3"/><p t-esc="1234*3">OUT-MARK</p>'
    '<p title="{{ 1234*3 }}">{{ 1234*3 }} #{1234*3}</p>'
    "<script>window.hostile = 1;</script>"
    '<img src="image/__WEBSITE_KEY__/logo.png" onerror="window.hostile=2">'
    '<a href="javascript:window.hostile=3">jslink</a>'
    "<p>&lt;script&gt;window.hostile = 4&lt;/script&gt;</p>",
)

# Company values in URL attributes and in an SVG animation. The values
# are benign at import; a user with contact rights changes them later.
COMPANY_LINKS = page_row(
    19,
    "companylinks",
    "Company links",
    '<a class="mail" href="<?php echo $mysoc->email ?>">m</a>'
    '<a class="site" href="<?php echo $mysoc->url ?>">w</a>'
    '<a class="tel" href="tel:<?php echo $mysoc->phone ?>">t</a>'
    '<svg><a><animate attributeName="<?php echo $mysoc->name ?>"'
    ' to="<?php echo $mysoc->email ?>" values="<?php echo $mysoc->email ?>"'
    ' begin="0s" fill="freeze"/><text y="20">x</text></a></svg>',
)
_BLANKS = re.compile(r"[\x00-\x20]")


class TestImportZip(DolibarrImportCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.run_record = cls.cli_import(
            zip_bytes=demo_zip_bytes(
                sql_edit=lambda sql: sql + HOSTILE + COMPANY_LINKS
            )
        )

    def get(self, url, **kw):
        return self.url_open(url, allow_redirects=False, **kw)

    def lines(self, code):
        return self.run_lines(self.run_record, code)

    def test_state(self):
        self.assertEqual(
            self.run_record.state, "done", self.run_record.error or ""
        )
        self.assertFalse(self.lines("page_error"))

    def test_home(self):
        response = self.get("/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn("info@example.org", response.text)
        body = re.search(r"<body[^>]*class=\"([^\"]*)\"", response.text)
        self.assertIn("bodywebsite", body.group(1).split())
        self.assertIn("/dolibarr-import/exemplesite/styles.css", response.text)
        self.assertIn("Plain introduction.", response.text)
        self.assertIn("Example Co", self.section(response.text))

    def test_redirects(self):
        for url, target in (
            ("/about.php", "/about"),
            ("/a-propos.php", "/about"),
            ("/Equipe.php", "/Equipe"),
        ):
            response = self.get(url)
            self.assertEqual(response.status_code, 301, url)
            self.assertTrue(response.headers["Location"].endswith(target), url)
        response = self.get("/equipe")
        self.assertIn(response.status_code, (301, 302, 303, 308))
        self.assertTrue(response.headers["Location"].endswith("/Equipe"))
        self.assertEqual(self.get("/Equipe").status_code, 200)

    def test_media_and_css_scope(self):
        response = self.get("/medias/image/exemplesite/logo.png")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["Content-Type"].startswith("image/png")
        )
        self.assertNotIn("/dolibarr-import/", self.get("/contactus").text)

    def test_media_headers_over_http(self):
        """Each imported file is served with the type its bytes prove,
        nosniff, and no script: the SVG loses its handler."""
        for url, mimetype in (
            ("/medias/image/exemplesite/logo.png", "image/png"),
            ("/medias/image/exemplesite/cover.webp", "image/webp"),
            ("/medias/image/exemplesite/icon.svg", "image/svg+xml"),
            ("/dolibarr-import/exemplesite/styles.css", "text/css"),
        ):
            response = self.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertEqual(
                response.headers["Content-Type"].split(";")[0], mimetype, url
            )
            self.assertEqual(
                response.headers.get("X-Content-Type-Options"), "nosniff", url
            )
        svg = self.get("/medias/image/exemplesite/icon.svg")
        self.assertIn(b"<svg", svg.content)
        self.assertIn(b"<rect", svg.content)
        for gone in (b"onload", b"alert", b"<script"):
            self.assertNotIn(gone, svg.content)
        self.assertIn(
            "default-src 'none'", svg.headers.get("Content-Security-Policy")
        )
        self.assertEqual(
            self.get("/medias/image/exemplesite/javascript.js").status_code,
            404,
        )

    def test_blog_post(self):
        post = self.env["blog.post"].search(
            [
                ("name", "=", "First news"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertEqual(str(post.published_date), "2025-03-04 05:06:07")
        self.assertEqual(
            json.loads(post.cover_properties)["background-image"],
            "url('/medias/image/exemplesite/cover.webp')",
        )
        self.assertFalse(post.blog_id.message_ids)
        page = self.get(post.website_url)
        self.assertEqual(page.status_code, 200)
        self.assertIn("/dolibarr-import/exemplesite/styles.css", page.text)
        self.assertIn("First news for Example Co.", page.text)

    def test_blog_page_moved_and_lists_posts(self):
        response = self.get("/blog-page")
        self.assertEqual(response.status_code, 200)
        self.assertIn("First news", response.text)
        self.assertEqual(self.lines("url_conflict").page_ref, "blog")
        location = self.get("/blog.php").headers["Location"]
        self.assertTrue(location.endswith("/blog-page"), location)

    def test_contact_form_posts(self):
        page = self.get("/contact").text
        signature = re.search(
            r'name="website_form_signature"[^>]*value="([^"]+)"', page
        ) or re.search(
            r'value="([^"]+)"[^>]*name="website_form_signature"', page
        )
        self.assertTrue(signature)
        self.assertIn('data-for="dolibarr_form_1"', page)
        response = self.url_open(
            "/website/form/mail.mail",
            data={
                "email_to": "info@example.org",
                "website_form_signature": signature.group(1),
                "name": "Visitor",
                "email_from": "visitor@example.org",
                "subject": "Hello",
                "description": "A question",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"id"', response.text)

    def test_unsafe_page(self):
        response = self.get("/unsafe")
        self.assertEqual(response.status_code, 200)
        self.assertIn("bodywebpage-unsafe", response.text)
        wrap = self.section(response.text)
        self.assertIn('src="https://www.example.org/embed"', wrap)
        for gone in (
            "<base",
            "srcdoc",
            "document.title",
            "/website/form/mail.mail",
            "javascript:",
            "<script",
        ):
            self.assertNotIn(gone, wrap)
        for code in (
            "unsafe_markup_removed",
            "script_removed",
            "form_removed",
        ):
            self.assertTrue(
                self.lines(code).filtered(
                    lambda line: line.page_ref == "unsafe"
                ),
                code,
            )

    def test_hostile_page_is_inert(self):
        response = self.get("/hostile")
        self.assertEqual(response.status_code, 200)
        wrap = self.section(response.text)
        self.assertIn("T-ATT", wrap)
        self.assertIn("OUT-MARK", wrap)
        self.assertNotIn("3702", wrap)
        self.assertIn("{{ 1234*3 }} #{1234*3}", wrap)
        self.assertIn('title="{{ 1234*3 }}"', wrap)
        self.assertIn("&lt;script&gt;window.hostile = 4", wrap)
        for gone in (
            "<script",
            "onerror",
            "javascript:",
            "window.hostile=",
            "t-att",
            "t-out",
            "t-esc",
        ):
            self.assertNotIn(gone, wrap)
        self.assertIn("jslink", wrap)
        codes = self.run_record.line_ids.filtered(
            lambda line: line.page_ref == "hostile"
        ).mapped("code")
        self.assertIn("script_removed", codes)
        self.assertIn("unsafe_markup_removed", codes)

    def test_company_values_edited_later_stay_inert(self):
        """A contact editor sets script URLs as company values after the
        import: no served link or animation carries one."""
        user = new_test_user(
            self.env,
            login="contact_editor",
            groups="base.group_user,base.group_partner_manager",
        )
        self.company.partner_id.with_user(user).write(
            {
                "email": "java\tscript:alert(document.domain)//",
                "website": "javascript:alert(1)",
                "phone": "javascript:alert(2)",
                "name": "href",
            }
        )
        self.assertEqual(self.company.email[:4], "java")
        response = self.get("/companylinks")
        self.assertEqual(response.status_code, 200)
        wrap = lxml.html.fromstring(response.text).get_element_by_id("wrap")
        links = {a.get("class"): a.get("href") for a in wrap.iter("a")}
        self.assertEqual(links["mail"], "")
        self.assertEqual(links["site"], "")
        for el in wrap.iter():
            for name in ("href", "to", "from", "values", "by"):
                value = _BLANKS.sub("", el.get(name) or "").lower()
                self.assertNotIn("javascript", value, (el.tag, name))
        for tag in ("animate", "set"):
            for el in wrap.iter(tag):
                self.assertNotEqual(el.get("attributename"), "href")
        page = self.env["website.page"].search(
            [
                ("url", "=", "/companylinks"),
                ("website_id", "=", self.website.id),
            ]
        )
        arch = etree.fromstring(page.view_id.arch_db)
        for tag in ("animate", "set"):
            for el in arch.iter(tag):
                live = [k for k in el.attrib if k.startswith("t-")]
                self.assertEqual(live, [], tag)

    def test_other_pages(self):
        translation = self.lines("skipped_translation")
        self.assertEqual(
            (translation.lang, translation.url), ("fr", "/fr/about-fr.php")
        )
        skipped = self.lines("foreign_lang_skipped")
        self.assertEqual(
            (skipped.lang, skipped.url), ("fr", "/standalone-fr.php")
        )
        self.assertEqual(self.get("/about-fr").status_code, 404)
        self.assertEqual(self.get("/standalone-fr").status_code, 404)
        legacy = self.get("/legacy")
        self.assertEqual(legacy.status_code, 200)
        self.assertNotIn("REMOVED-MARKER", legacy.text)
        removed = self.lines("php_removed").filtered(
            lambda line: line.page_ref == "legacy"
        )
        self.assertTrue(
            any(
                "HTML bytes removed" in line.message
                and " 0 HTML" not in line.message
                for line in removed
            )
        )
        self.assertEqual(
            sorted(self.lines("skipped_container_type").mapped("page_ref")),
            ["_lib", "config"],
        )
        for url in ("/_lib", "/config"):
            self.assertEqual(self.get(url).status_code, 404, url)

    def test_menu(self):
        names = self.website.menu_id.child_id.sorted("sequence").mapped("name")
        self.assertEqual(names[:3], ["Home", "Blog", "Contact us"])
        self.assertEqual(names[-3:], ["About", "Team", "Blog page"])
        self.assertEqual(len(self.lines("menu_skipped_existing_url")), 2)
        nav = self.section(self.get("/").text, "<header", "</header>")
        spans = [
            nav.find("<span>%s</span>" % label)
            for label in ("Home", "Contact us", "About", "Team", "Blog page")
        ]
        self.assertNotIn(-1, spans)
        self.assertEqual(spans, sorted(spans))

    def test_media_rules(self):
        svg = self.env["ir.attachment"].search(
            [
                ("url", "=", "/medias/image/exemplesite/icon.svg"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertNotIn(b"onload", base64.b64decode(svg.datas))
        self.assertFalse(
            self.env["ir.attachment"].search([("url", "like", "bad')")])
        )
        self.assertTrue(self.lines("media_name_refused"))


class TestImportTwoCompanies(DolibarrImportCase):
    """The same zip imported on the websites of two companies.

    Site B has its own host, so each request reaches one website only.
    Each site gets the values of its own company, and a page that only
    one site imported is never served on the other one's host.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other = cls.env["res.company"].create(
            {
                "name": "Second Sample Ltd",
                "email": "info@second.example.org",
                "phone": "+1 555 0199",
            }
        )
        cls.env.user.company_ids |= cls.other
        cls.host_b = cls.base_url().replace("127.0.0.1", "localhost")
        cls.website_b = cls.env["website"].create(
            {
                "name": "Second site",
                "domain": cls.host_b,
                "company_id": cls.other.id,
            }
        )
        cls.run_a = cls.cli_import()
        cls.run_b = cls.cli_import(
            website=cls.website_b,
            zip_bytes=demo_zip_bytes(
                sql_edit=lambda sql: sql.replace(
                    "We make examples.", "Site B text."
                ),
                drop_pages=["Equipe"],
            ),
        )

    def get_b(self, path):
        return self.url_open(self.host_b + path, allow_redirects=False)

    def get_a(self, path):
        return self.url_open(path, allow_redirects=False)

    def test_runs(self):
        for run in (self.run_a, self.run_b):
            self.assertEqual(run.state, "done", run.error or "")

    def test_post_freezes_its_own_company(self):
        post = self.env["blog.post"].search(
            [
                ("name", "=", "First news"),
                ("website_id", "=", self.website_b.id),
            ]
        )
        self.assertIn("Second Sample Ltd", post.content)
        self.assertNotIn("Example Co", post.content)
        self.assertEqual(post.author_id, self.other.partner_id)
        mine = self.env["blog.post"].search(
            [
                ("name", "=", "First news"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertIn("Example Co", mine.content)
        self.assertNotEqual(mine, post)
        served = self.url_open(self.host_b + post.website_url)
        self.assertEqual(served.status_code, 200)
        self.assertIn("First news for Second Sample Ltd.", served.text)
        self.assertNotIn("Example Co", self.section(served.text))

    def test_pages_render_each_company(self):
        home_b = self.section(self.get_b("/home").text)
        self.assertIn("info@second.example.org", home_b)
        self.assertNotIn("info@example.org", home_b)
        home_a = self.section(self.get_a("/home").text)
        self.assertIn("info@example.org", home_a)
        self.assertNotIn("second.example.org", home_a)

    def test_nothing_leaks_across_websites(self):
        about_b = self.get_b("/about")
        self.assertEqual(about_b.status_code, 200)
        self.assertIn("Site B text.", about_b.text)
        self.assertNotIn("We make examples.", about_b.text)
        about_a = self.get_a("/about")
        self.assertIn("We make examples.", about_a.text)
        self.assertNotIn("Site B text.", about_a.text)
        self.assertEqual(self.get_a("/Equipe").status_code, 200)
        self.assertEqual(self.get_b("/Equipe").status_code, 404)
        self.assertEqual(self.get_b("/Equipe.php").status_code, 404)
        self.assertEqual(self.get_a("/Equipe.php").status_code, 301)
        for website in (self.website, self.website_b):
            logo = self.env["ir.attachment"].search(
                [
                    ("url", "=", "/medias/image/exemplesite/logo.png"),
                    ("website_id", "=", website.id),
                ]
            )
            self.assertEqual(len(logo), 1)
        self.assertEqual(
            self.get_b("/medias/image/exemplesite/logo.png").status_code, 200
        )
        blogs = self.env["blog.post"].search(
            [("blog_id.website_id", "=", self.website_b.id)]
        )
        self.assertEqual(
            set(blogs.mapped("blog_id.website_id")), {self.website_b}
        )
        self.assertEqual(self.website_b.homepage_url, "/home")
