# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest
from unittest import mock

from lxml import etree

from .. import pipeline
from ..html2arch import DictResolver
from ..messages import finding
from ..model import Options, Page, PageError, Site, SourceError
from ..pipeline import (
    all_findings,
    apply_choices,
    build_from_zip,
    css_url,
    js_url,
    render_site,
)
from .fixtures import FILENAME, demo_zip_bytes
from .test_html2arch import COMPANY

IMPORTED = ["Equipe", "about", "blog", "contact", "home", "legacy", "unsafe"]


def render(opts=None):
    opts = opts or Options(filename=FILENAME)
    site = apply_choices(build_from_zip(demo_zip_bytes(), opts), [])
    resolver = DictResolver(
        pages={ref: "/" + ref for ref in IMPORTED}
        | {
            "news-1": "/blog/news-4/first-news-1",
            "news-2": "/blog/news-4/second-news-2",
        },
        media={m.relpath: "/medias/" + m.relpath for m in site.media},
        blog_id=4,
        website_id=2,
    )
    return site, render_site(site, resolver, COMPANY, opts)


def include_page(ref, target, status="import"):
    return Page(
        ref=ref,
        title=ref,
        body_html='<p>%s</p><dolibarr-q id="1"></dolibarr-q>' % ref,
        qweb_nodes={"1": {"kind": "include", "ref": target}},
        analysis_status=status,
    )


def small_site(pages, containers):
    return Site(source_key="exemplesite", pages=pages, containers=containers)


def render_small(site, opts=None):
    opts = opts or Options()
    return render_site(site, DictResolver(blog_id=1), COMPANY, opts)


class RenderSiteCases:
    def test_render_demo(self):
        site, rendered = render()
        self.assertEqual(sorted(rendered.pages), IMPORTED)
        self.assertEqual(sorted(rendered.posts), ["news-1", "news-2"])
        home = rendered.pages["home"]
        etree.fromstring(home)
        self.assertIn("limit=2)", home)
        self.assertIn('t-out="res_company.name"', home)
        self.assertNotIn("REMOVED-MARKER", rendered.pages["legacy"])
        unsafe = rendered.pages["unsafe"]
        for gone in ("<script", "<base", "srcdoc", "email_to", "javascript"):
            self.assertNotIn(gone, unsafe)
        contact = rendered.pages["contact"]
        self.assertIn(
            "erplibre_website_import_from_dolibarr.contact_form", contact
        )
        self.assertIn('data-for="dolibarr_form_1"', contact)
        self.assertNotIn('name="token"', contact)
        blog = rendered.pages["blog"]
        self.assertIn(
            "erplibre_website_import_from_dolibarr.blog_post_list", blog
        )
        self.assertIn('t-value="4"', blog)
        self.assertIn('t-value="5"', blog)
        self.assertIn('t-out="res_company.phone"', rendered.pages["about"])
        self.assertIn("Example Co", rendered.posts["news-1"])
        self.assertIn(css_url(site), rendered.head_arch)
        self.assertNotIn("<script", rendered.head_arch)
        codes = {f.code for f in rendered.findings}
        self.assertIn("container_inlined", codes)
        self.assertIn("script_removed", codes)
        self.assertNotIn("unresolved_link", codes)
        self.assertEqual(rendered.site_css, site.site_css)
        self.assertIn(
            "foreign_lang_skipped", {f.code for f in all_findings(site)}
        )

    def test_keep_scripts(self):
        _site, rendered = render(Options(filename=FILENAME, keep_scripts=True))
        self.assertIn("<script", rendered.pages["unsafe"])
        self.assertIn("script_kept", {f.code for f in rendered.findings})

    def test_asset_urls(self):
        site, _rendered = render()
        url = css_url(site)
        self.assertRegex(
            url, r"^/dolibarr-import/exemplesite/styles\.css\?v=[0-9a-f]{8}$"
        )
        site.site_css = "  \n"
        self.assertEqual(css_url(site), "")
        self.assertEqual(js_url(site), "")
        site.site_js = "var a;"
        self.assertEqual(
            js_url(site), "/dolibarr-import/exemplesite/javascript.js"
        )

    def test_asset_urls_need_a_valid_key(self):
        site, _rendered = render()
        site.site_js = "var a;"
        for key in ("", "a b", "../x", "k'", "k/x"):
            site.source_key = key
            for build_url in (css_url, js_url):
                with self.assertRaises(SourceError, msg=key):
                    build_url(site)

    def test_unusable_containers_are_never_rendered(self):
        # containers lists a skipped target, a missing ref and the home
        # page; only pages with the import status are rendered, and an
        # include of a skipped or missing ref inlines nothing.
        skipped = Page(
            ref="lib",
            body_html="<p>SKIPPED-BODY</p>",
            analysis_status="skipped",
        )
        home = include_page("home", "lib")
        other = include_page("other", "ghost")
        third = include_page("third", "home")
        site = small_site(
            [home, other, third, skipped],
            {"lib": "content", "ghost": "content", "home": "content"},
        )
        site.home_ref = "home"
        rendered = render_small(site)
        self.assertEqual(sorted(rendered.pages), ["home", "other", "third"])
        self.assertEqual(rendered.posts, {})
        for arch in rendered.pages.values():
            self.assertNotIn("SKIPPED-BODY", arch)
        self.assertNotIn("SKIPPED-BODY", rendered.head_arch)
        text = " ".join(str(f.params) for f in rendered.findings)
        self.assertIn("lib", text)
        self.assertIn("ghost", text)
        self.assertNotIn(
            "lib", {f.params.get("container") for f in rendered.findings}
        )
        self.assertNotIn(
            "ghost", {f.params.get("container") for f in rendered.findings}
        )

    def test_content_container_is_inlined_not_rendered(self):
        content = Page(
            ref="cta", body_html="<p>CTA</p>", analysis_status="container"
        )
        site = small_site(
            [include_page("home", "cta"), content], {"cta": "content"}
        )
        rendered = render_small(site)
        self.assertEqual(sorted(rendered.pages), ["home"])
        self.assertIn("CTA", rendered.pages["home"])

    def test_page_error_skips_the_page_only(self):
        deep = Page(ref="deep", body_html="<div>" * 257 + "x" + "</div>" * 257)
        site = small_site([deep, include_page("ok", "nowhere")], {})
        rendered = render_small(site)
        self.assertEqual(sorted(rendered.pages), ["ok"])
        errors = [f for f in rendered.findings if f.code == "page_error"]
        self.assertEqual([f.page_ref for f in errors], ["deep"])

    def test_site_level_findings_stay_site_level(self):
        # A head error names the site head or nothing at all: the line is
        # kept as it is, in rendered.findings, and no page carries it.
        site = small_site([include_page("home", "nowhere")], {})
        self.assertNotEqual(render_small(site).head_arch, "")
        for ref in ("htmlheader.html", ""):
            with mock.patch.object(
                pipeline.html2arch,
                "head_arch",
                side_effect=PageError(ref, "site head too large"),
            ):
                rendered = render_small(site)
            self.assertEqual(rendered.head_arch, "")
            self.assertEqual(sorted(rendered.pages), ["home"])
            (error,) = [f for f in rendered.findings if f.code == "page_error"]
            self.assertEqual(error.page_ref, ref)
            self.assertEqual(error.params["ref"], ref)
            self.assertEqual(site.pages[0].findings, [])

    def test_build_page_errors_stay_on_the_site(self):
        site = small_site([include_page("home", "nowhere")], {})
        site.findings.append(
            finding(
                "page_error", page_ref="htmlheader.html", ref="x", reason="r"
            )
        )
        site.findings.append(
            finding("page_error", page_ref="", ref="", reason="r")
        )
        rendered = render_small(site)
        self.assertEqual(
            [f for f in rendered.findings if f.code == "page_error"], []
        )
        refs = [
            f.page_ref for f in all_findings(site) if f.code == "page_error"
        ]
        self.assertEqual(sorted(refs), ["", "htmlheader.html"])
        self.assertEqual(site.pages[0].findings, [])


class TestRenderSite(RenderSiteCases, unittest.TestCase):
    pass
