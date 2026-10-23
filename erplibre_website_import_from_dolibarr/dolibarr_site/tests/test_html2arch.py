# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import ast
import hashlib
import unittest
from unittest import mock

from lxml import etree
from lxml import html as lhtml

from .. import html2arch
from ..html2arch import (
    MAX_TEXT,
    DictResolver,
    apply_script_policy,
    blog_style_key,
    clean_fragment,
    clean_head,
    finalize,
    fragment_html,
    head_arch,
    head_key,
    page_arch,
    post_content,
    sanitize_svg,
    script_counts,
    script_summary,
    style_allowed,
    url_allowed,
    view_key,
)
from ..model import MenuItem, Options, Page, PageError, Site
from ..php import ATTR_TOKEN_RE, assemble, neutralise, tokenize
from ..urls import rewrite_links
from ..xml_safe import parse_xml_safely

HOSTS = ["fonts.googleapis.com", "use.fontawesome.com", "cdnjs.cloudflare.com"]


def clean(source, keep_scripts=True):
    findings = []
    root = clean_fragment(source, "p", findings, keep_scripts=keep_scripts)
    return root, fragment_html(root), {f.code: f for f in findings}


class CleanCases:
    def test_qweb_source_is_inert(self):
        root, out, codes = clean(
            '<div t-out="1" groups="base.group_user" data-oe-model="x">a</div>'
            '<t t-call="website.layout"/><p title="{{ 7*7 }}">b</p>'
        )
        self.assertNotIn("t-out", out)
        self.assertNotIn("t-call", out)
        self.assertNotIn("groups", out)
        self.assertNotIn("data-oe-model", out)
        self.assertIsNone(root.find(".//t"))
        self.assertEqual(root.find(".//p").get("title"), "{{ 7*7 }}")
        self.assertIn("unsafe_markup_removed", codes)

    def test_entities_stay_text(self):
        root, _out, _codes = clean("<p>&nbsp;x&lt;y &lt;script&gt;</p>")
        self.assertEqual(root.text_content(), "\xa0x<y <script>")
        self.assertIsNone(root.find(".//script"))

    def test_attribute_names_and_control_chars(self):
        root, out, _codes = clean(
            '<a :class="y" xlink:href="/x" contenteditable="true">t\x01</a>'
        )
        link = root.find(".//a")
        self.assertEqual(link.get("href"), "/x")
        self.assertEqual(link.get("contenteditable"), "false")
        self.assertNotIn(":class", out)
        self.assertNotIn("\x01", out)

    def test_depth_limit(self):
        with self.assertRaises(PageError):
            clean("<div>" * 257 + "x" + "</div>" * 257)

    def test_unsafe_markup_removed(self):
        root, out, codes = clean(
            '<base href="http://www.example.org/"><object data="x"></object>'
            '<iframe srcdoc="<b>x</b>" src="https://www.example.org/m">'
            '</iframe><iframe src="http://www.example.org/n"></iframe>'
            '<a href="java&#9;script:alert(1)">j</a>'
            '<svg><set attributeName="href" to="javascript:alert(1)"/></svg>'
            '<meta name="google-site-verification" content="x"><title>t</title>'
            '<p style="width:expression(alert(1))">s</p>'
            '<p style="background:url(javascript:x)">u</p>'
            '<p style="color:red">ok</p><img src="data:image/png;base64,AA==">'
            '<a href="data:text/html,x">d</a>',
            keep_scripts=False,
        )
        for needle in (
            "<base",
            "<object",
            "srcdoc",
            "http://www.example.org/n",
            "javascript",
            "<set",
            "<meta",
            "<title",
            "expression",
            "data:text",
        ):
            self.assertNotIn(needle, out)
        self.assertIn('src="https://www.example.org/m"', out)
        self.assertIn("color:red", out)
        self.assertIn("data:image/png", out)
        self.assertIn("unsafe_markup_removed", codes)

    def test_forms_to_odoo_controller_removed(self):
        _root, out, codes = clean(
            '<form action="/website/form/mail.mail" method="post">'
            '<input name="email_to" value="someone@example.org"></form>'
            '<form action="/search"><input name="email_to"><textarea'
            ' name="email_cc"></textarea><input name="q"></form>'
            '<span data-for="f1" data-values="{}"></span>'
        )
        self.assertNotIn("/website/form", out)
        self.assertNotIn("email_", out)
        self.assertNotIn("data-for", out)
        self.assertIn('name="q"', out)
        self.assertIn("form_removed", codes)

    def test_style_rewritten_by_the_cleaner_is_reported(self):
        for css in (
            "a{b:expression(1)}",
            "a{background:url(javascript:alert(1))}",
        ):
            _root, out, codes = clean("<style>%s</style>" % css, False)
            self.assertNotIn(css, out)
            self.assertIn(
                "<style> rewritten",
                codes["unsafe_markup_removed"].params["what"],
                css,
            )
            root = lhtml.fragment_fromstring(
                "<style>%s</style>" % css, create_parent="div"
            )
            findings = []
            apply_script_policy(root, "p", findings, keep_scripts=False)
            self.assertIn(
                "<style> rewritten",
                findings_what(findings, "unsafe_markup_removed"),
            )
        _root, _out, codes = clean("<style>a{color:red}</style>", False)
        self.assertNotIn("unsafe_markup_removed", codes)

    def test_encoded_form_action_is_removed(self):
        for action in (
            "/Website/%66orm/mail.mail",
            "/website%2Fform/mail.mail",
            "/website/%2566orm/mail.mail",
        ):
            _root, out, codes = clean(
                '<form action="%s" method="post"><input name="n"></form>'
                % action
            )
            self.assertNotIn("<form", out, action)
            self.assertIn("form_removed", codes, action)

    def test_reserved_form_ids_are_refused(self):
        _root, out, codes = clean(
            '<form id="dolibarr_form_1" action="/x"></form>'
            '<p id=" Dolibarr_Form_2">p</p><p id="dolibarr-form">q</p>'
        )
        self.assertNotIn("dolibarr_form_", out.lower())
        self.assertIn('id="dolibarr-form"', out)
        self.assertIn(
            "reserved id", codes["unsafe_markup_removed"].params["what"]
        )

    def test_script_counting_and_policy(self):
        source = (
            "<script>var a=1;</script><script src='/medias/js/k/a.js'></script>"
            '<p onclick="x()">p</p><a href="javascript:void(0)">j</a>'
            '<iframe src="https://www.example.org/v"></iframe>'
        )
        root, _out, _codes = clean(source)
        count, detail = script_summary(script_counts(root))
        self.assertEqual(count, 5)
        self.assertEqual(
            detail,
            "inline scripts: 1; script files: 1; on* handlers: 1;"
            " javascript: URLs: 1; iframes: 1",
        )
        findings = []
        apply_script_policy(root, "p", findings, keep_scripts=False)
        out = fragment_html(root)
        self.assertNotIn("<script", out)
        self.assertNotIn("onclick", out)
        self.assertNotIn("javascript", out)
        self.assertIn("<iframe", out)
        self.assertEqual([f.code for f in findings], ["script_removed"])
        root, _out, _codes = clean(source)
        findings = []
        apply_script_policy(root, "p", findings, keep_scripts=True)
        self.assertIn("<script", fragment_html(root))
        self.assertEqual([f.code for f in findings], ["script_kept"])

    def test_markers_only_when_trusted(self):
        source = '<dolibarr-q id="1"></dolibarr-q>'
        _root, out, _codes = clean(source)
        self.assertNotIn("dolibarr-q", out)
        root = clean_fragment(source, "p", [], trusted_markers=True)
        self.assertIsNotNone(root.find("dolibarr-q"))

    def test_marker_iframe_src_kept_only_when_trusted(self):
        source = '<iframe src="DOLIBARRQ4Q"></iframe>'
        findings = []
        root = clean_fragment(source, "p", findings, trusted_markers=True)
        self.assertEqual(root.find("iframe").get("src"), "DOLIBARRQ4Q")
        self.assertEqual(findings, [])
        for src in ("DOLIBARRQ4Q", "x DOLIBARRQ4Q", "dolibarrq4q"):
            _root, out, codes = clean('<iframe src="%s"></iframe>' % src)
            self.assertNotIn("<iframe", out)
            self.assertIn(
                "non-https iframe",
                codes["unsafe_markup_removed"].params["what"],
            )
        for src in ("x DOLIBARRQ4Q", "http://e.test/DOLIBARRQ4Q", ""):
            root = clean_fragment(
                '<iframe src="%s"></iframe>' % src,
                "p",
                [],
                trusted_markers=True,
            )
            self.assertIsNone(root.find("iframe"), src)

    def test_url_and_style_rules(self):
        self.assertTrue(url_allowed("page.php?a=b:c", "href", False))
        self.assertTrue(url_allowed("mailto:x@example.org", "href", False))
        self.assertFalse(url_allowed(" JaVa\tScRiPt:x", "href", False))
        self.assertTrue(url_allowed("javascript:x", "href", True))
        self.assertFalse(url_allowed("data:image/png;base64,A", "href", True))
        self.assertFalse(url_allowed("vbscript:x", "href", True))
        self.assertFalse(style_allowed("background:url('data:image/png,A')"))
        self.assertFalse(style_allowed("@import 'x.css'"))
        self.assertTrue(style_allowed("background:url('/medias/a.png')"))

    def test_head_rules(self):
        findings = []
        out = clean_head(
            '<meta name="google-site-verification" content="x">'
            '<meta http-equiv="refresh" content="0;url=http://www.example.org">'
            "<title>T</title><base href='/'>"
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css?f=A">'  # noqa: E501
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/x/bootstrap.min.css">'  # noqa: E501
            '<link rel="stylesheet" href="https://css.example.org/site.css">'
            '<link rel="icon" href="/favicon.ico">'
            '<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>'  # noqa: E501
            "<script>$(function(){})</script><style>b{}</style>",
            "p",
            findings,
            HOSTS,
        )
        self.assertIn("fonts.googleapis.com", out)
        self.assertIn("<style>", out)
        self.assertIn("$(function", out)
        for gone in (
            "verification",
            "refresh",
            "<title",
            "<base",
            "bootstrap",
            "css.example.org",
            "favicon",
            "jquery-3",
        ):
            self.assertNotIn(gone, out)
        codes = sorted({f.code for f in findings})
        self.assertEqual(
            codes,
            [
                "css_external_removed",
                "head_asset_dropped",
                "inline_script_needs_jquery",
            ],
        )

    def test_svg(self):
        data, removed = sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg"'
            b' xmlns:xlink="http://www.w3.org/1999/xlink" onload="x()">'
            b"<script>alert(1)</script><foreignObject><p/></foreignObject>"
            b'<use xlink:href="https://www.example.org/s.svg#a"/>'
            b'<use href="#local"/><animate attributeName="href" to="x"/>'
            b'<rect width="1" height="1"/></svg>'
        )
        for needle in (
            b"onload",
            b"<script",
            b"foreignObject",
            b"example.org",
            b"<animate",
        ):
            self.assertNotIn(needle, data)
        self.assertIn(b'href="#local"', data)
        self.assertIn(b"<rect", data)
        self.assertTrue(removed)
        entity = (
            b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM'
            b' "file:///etc/hostname">]><svg>&x;</svg>'
        )
        with self.assertRaises(ValueError):
            sanitize_svg(entity)
        with self.assertRaises(ValueError):
            parse_xml_safely(entity)
        self.assertEqual(parse_xml_safely(b"<a><b/></a>").tag, "a")
        self.assertIsInstance(parse_xml_safely(b"<a/>"), etree._Element)

    def test_translated_text_is_cleaned_like_any_source(self):
        # trans() output is markup too; the same gate applies to it.
        for trusted in (False, True):
            root = clean_fragment(
                '<a href="javascript:alert(1)" onclick="x()">a</a>'
                '<span onclick="y()" ONMOUSEOVER="z()" t-esc="1">b</span>'
                '<dolibarr-q id="1" onclick="w()" t-out="2"></dolibarr-q>',
                "p",
                [],
                keep_scripts=False,
                trusted_markers=trusted,
            )
            out = fragment_html(root)
            for needle in ("javascript", "onclick", "onmouseover", "t-"):
                self.assertNotIn(needle, out.lower())

    def test_obfuscated_schemes_are_refused(self):
        hostile = [
            "JaVaScRiPt:alert(1)",
            "java&#x09;script:alert(1)",
            "java&#10;script:alert(1)",
            "&#106;avascript:alert(1)",
            "&#x6A;&#x61;vascript&colon;alert(1)",
            "jav&Tab;ascript:alert(1)",
            "  \x01javascript:alert(1)",
            "java\x00script:alert(1)",
            "vbscript:msgbox(1)",
            "VBScript:msgbox(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
            "DATA:text/html,x",
            "\\javascript:alert(1)",
        ]
        for value in hostile:
            for attr in ("href", "src", "action", "poster"):
                source = '<a %s="%s">x</a>' % (attr, value)
                _root, out, _codes = clean(source, keep_scripts=False)
                low = out.lower()
                for needle in ("script:", "data:", "&colon;"):
                    self.assertNotIn(needle, low, source)
        self.assertFalse(url_allowed("j\ta\nv\x0da script:x", "href", False))
        self.assertFalse(url_allowed("&#x6A;avascript:x", "href", False))

    def test_qweb_attributes_removed_in_any_case(self):
        _root, out, _codes = clean(
            '<p T-OUT="1" t-att-href="x" T-Call="y" ONCLICK="z()">a</p>'
            '<t T-IF="1">b</t>',
            keep_scripts=False,
        )
        for needle in ("t-out", "t-att", "t-call", "t-if", "onclick", "<t"):
            self.assertNotIn(needle, out.lower())

    def test_unclosed_script_does_not_swallow_the_page(self):
        source = "<script>a<p>after</p>"
        root, out, _codes = clean(source, keep_scripts=False)
        self.assertNotIn("<script", out.lower())
        self.assertIsNone(root.find(".//script"))
        self.assertEqual(root.find(".//p").text, "after")
        self.assertNotIn("a<", out)
        root, out, _codes = clean(source, keep_scripts=True)
        self.assertEqual(root.find(".//script").text, "a")
        self.assertEqual(root.find(".//p").text, "after")

    def test_unclosed_script_variants(self):
        for source in (
            "<SCRIPT src=x>a<p>after</p>",
            "<p>b</p><script>a\n<div>after</div>",
            "<style>a{}<p>after</p>",
            "<script>a</script><script>b<p>after</p>",
        ):
            root, out, _codes = clean(source, keep_scripts=False)
            self.assertNotIn("<script", out.lower(), source)
            self.assertIn("after", root.text_content(), source)
        # An unclosed script that is the last thing in the source.
        root, out, _codes = clean("<p>x</p><script>a", keep_scripts=False)
        self.assertNotIn("script", out)
        self.assertEqual(root.find(".//p").text, "x")

    def test_script_may_hold_a_lone_less_than(self):
        root, _out, _codes = clean(
            "<script>for(i=0;i<n;i++){c()}</script><p>z</p>"
        )
        self.assertEqual(root.find(".//script").text, "for(i=0;i<n;i++){c()}")
        self.assertEqual(root.find(".//p").text, "z")
        root, _out, _codes = clean("<style>a>b{}</style><p>z</p>")
        self.assertIsNotNone(root.find(".//style"))

    def test_raw_text_that_can_break_out_is_dropped(self):
        # '</' and '<!--' are what can end or escape a raw-text element
        # once the stored HTML is parsed in another context.
        for body in ("a='</b>';", "x<!--y", "x<!-- y -->"):
            for tag in ("script", "style"):
                source = "<%s>%s</%s><p>z</p>" % (tag, body, tag)
                root, _out, codes = clean(source)
                self.assertIsNone(root.find(".//" + tag), source)
                self.assertEqual(root.find(".//p").text, "z")
                self.assertIn("unsafe_markup_removed", codes)

    def test_body_import_of_a_foreign_host_writes_a_finding(self):
        _root, out, codes = clean(
            "<style>@import url(https://evil.example/x.css);</style>"
        )
        self.assertNotIn("evil", out)
        self.assertIn("unsafe_markup_removed", codes)
        self.assertIn("@import", codes["unsafe_markup_removed"].params["what"])

    def test_policy_leaves_no_script_from_a_nested_namespace(self):
        root, out, _codes = clean(
            "<svg:script>alert(1)</svg:script><p>k</p>", keep_scripts=False
        )
        apply_script_policy(root, "p", [], keep_scripts=False)
        self.assertNotIn("<", fragment_html(root).replace("<p>k</p>", ""))
        self.assertNotIn("alert(1)", root.text_content())

    def test_style_escapes_are_refused(self):
        self.assertFalse(style_allowed("width:expr\\65 ssion(alert(1))"))
        self.assertTrue(style_allowed("color:red;margin:0 auto"))

    def _stored(self, source):
        """Analysis clean, serialisation, re-parse, render-time policy."""
        root = clean_fragment(source, "p", [], keep_scripts=True)
        stored = fragment_html(root)
        again = lhtml.fragment_fromstring(stored, create_parent="div")
        apply_script_policy(again, "p", [], keep_scripts=False)
        return stored, fragment_html(again)

    def test_raw_text_in_foreign_content_is_dropped(self):
        for source in (
            "<svg><style><img src=x onerror=alert(1)></style></svg>",
            "<math><style><img src=x onerror=alert(1)></style></math>",
            "<svg><script>a</script></svg>",
            "<style>@import url(https://evil.example/x.css);</style>",
            "<style>@IMPORT 'https://evil.example/x.css';</style>",
        ):
            stored, out = self._stored(source)
            for text in (stored, out):
                for needle in ("onerror", "<img", "evil.example", "<script"):
                    self.assertNotIn(needle, text, source)
        _root, _out, codes = clean(
            "<svg><style><img src=x onerror=alert(1)></style></svg>"
        )
        self.assertIn("unsafe_markup_removed", codes)

    def test_policy_alone_is_as_strong_as_a_direct_clean(self):
        for source in (
            "<svg><style><img src=x onerror=alert(1)></style></svg>",
            "<style>@import url(https://evil.example/x.css);</style>",
            '<a href="javascript:x" onclick="y()">a</a><form action='
            '"/website/form/mail.mail"></form>',
        ):
            root = lhtml.fragment_fromstring(source, create_parent="div")
            apply_script_policy(root, "p", [], keep_scripts=False)
            out = fragment_html(root)
            for needle in ("onerror", "evil.example", "javascript", "onclick"):
                self.assertNotIn(needle, out, source)

    def test_reference_spelled_marker_token_is_inert(self):
        for spelled in (
            "DOLIBARR&#81;1Q",
            "&#x44;OLIBARRQ1Q",
            "DOLIBARR&#x51 1Q",
        ):
            self.assertNotRegex(neutralise(spelled), "(?i)DOLIBARRQ\\d+Q")
        self.assertEqual(neutralise("DOLIBARR&#81;7Q"), "DOLIBARRX7X")
        self.assertEqual(neutralise("&#100;olibarr-&#113;"), "dolibarr_xq")
        for trusted in (False, True):
            for source in (
                '<p title="DOLIBARR&#81;1Q">x</p>',
                '<p title="&#x44;OLIBARRQ1Q">x</p>',
                "<p>DOLIBARR&#81;1Q</p>",
                "<p>&#100;olibarr-q id=1</p>",
            ):
                if trusted:
                    source = assemble(tokenize(source), {}).html
                out = fragment_html(
                    clean_fragment(source, "p", [], trusted_markers=trusted)
                )
                self.assertNotRegex(out, "DOLIBARRQ\\d+Q")
        head = clean_head(
            '<link rel="stylesheet" href="DOLIBARR&#81;1Q">', "p", [], HOSTS
        )
        self.assertNotRegex(head, "DOLIBARRQ\\d+Q")

    def test_css_url_rules_ignore_case_and_comments(self):
        for value in (
            "background:URL(data:image/png,A)",
            "background:Url(ftp://x/a)",
            'background:image-set("data:image/png,A" 1x)',
            "background:-webkit-image-set('ftp://x/a' 1x)",
            "background:src('ftp://x/a')",
            "x:expre/**/ssion(1)",
            "x:EXPRESSION(1)",
            "b:url(java/**/script:x)",
        ):
            self.assertFalse(style_allowed(value), value)
        self.assertTrue(style_allowed("background:URL('/medias/a.png')"))
        self.assertTrue(
            style_allowed('background:image-set("/a.png" 1x, "/b.png" 2x)')
        )

    def test_css_host_allow_list_cannot_be_bypassed(self):
        for href in (
            "https:/\\evil.example/x.css",
            "\\\\evil.example/x.css",
            "/\\evil.example/x.css",
            "//evil.example/x.css",
            "https://evil.example\\@fonts.googleapis.com/x.css",
            "https:evil.example/x.css",
            "ht\ttps://evil.example/x.css",
        ):
            findings = []
            out = clean_head(
                '<link rel="stylesheet" href="%s">' % href,
                "p",
                findings,
                HOSTS,
            )
            self.assertNotIn("evil", out, href)
            self.assertIn(
                "css_external_removed", [f.code for f in findings], href
            )
        findings = []
        out = clean_head(
            "<style>@import url(https://evil.example/x.css);</style>"
            "<style>@import 'https://fonts.googleapis.com/c.css';</style>"
            "<style>@import 'local.css';</style>",
            "p",
            findings,
            HOSTS,
        )
        self.assertNotIn("evil", out)
        self.assertIn("fonts.googleapis.com", out)
        self.assertIn("local.css", out)
        self.assertEqual([f.code for f in findings], ["css_external_removed"])

    def test_svg_foreign_namespaces_and_animations(self):
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg"'
            b' xmlns:h="http://www.w3.org/1999/xhtml"'
            b' xmlns:xlink="http://www.w3.org/1999/xlink">%s</svg>'
        )
        for inner in (
            b'<h:iframe srcdoc="&lt;b&gt;"/>',
            b'<h:object data="javascript:alert(1)"/>',
            b'<h:meta http-equiv="refresh" content="0;url=x"/>',
            b'<set attributeName=" href" to="javascript:alert(1)"/>',
            b'<set attributeName="onclick" to="alert(1)"/>',
            b'<animate attributeName="xlink:href" to="x"/>',
            b"<style>@import url(https://evil.example/x.css)</style>",
            b"<handler>x</handler>",
            b"<listener>x</listener>",
        ):
            data, removed = sanitize_svg(svg % inner)
            for needle in (
                b"iframe",
                b"object",
                b"meta",
                b"<set",
                b"<animate",
                b"<style",
                b"handler",
                b"listener",
                b"evil",
            ):
                self.assertNotIn(needle, data, inner)
            self.assertTrue(removed, inner)
        data, _removed = sanitize_svg(svg % b'<rect width="1"/>')
        self.assertIn(b"<rect", data)

    def test_svg_root_must_be_svg(self):
        for data in (
            b"<html><body><script>x</script></body></html>",
            b"<div/>",
            b'<svgx xmlns="http://www.w3.org/2000/svg"/>',
        ):
            with self.assertRaises(ValueError, msg=data):
                sanitize_svg(data)
        data, _removed = sanitize_svg(b"<svg><rect/></svg>")
        self.assertIn(b"<rect", data)

    def test_html_animation_target_is_normalised(self):
        _root, out, codes = clean(
            '<svg><set attributeName=" HREF" to="x"/>'
            '<set attributeName="onclick" to="y"/></svg>'
        )
        self.assertNotIn("<set", out)
        self.assertIn("unsafe_markup_removed", codes)

    def test_xml_entities_refused_in_any_encoding(self):
        text = '<!DOCTYPE s [<!ENTITY x SYSTEM "file:///x">]><svg>&x;</svg>'
        for enc in ("utf-16", "utf-16-le", "utf-16-be", "utf-32"):
            data = text.encode(enc)
            with self.assertRaises(ValueError, msg=enc):
                sanitize_svg(data)
            # A document libxml2 cannot read at all is an XML error, not
            # an accepted one.
            with self.assertRaises((ValueError, etree.XMLSyntaxError)):
                parse_xml_safely(data)

    def test_data_attributes_cannot_drive_the_form_widget(self):
        root, out, codes = clean(
            '<section class="s_website_form"><form action="/website/for"'
            ' data-model_name="m/mail.mail"'
            ' data-success-page="javascript:alert(document.cookie)">'
            '<select name="email_to"></select>'
            '<button name="email_bcc"></button><input name="q"></form>'
            "</section>",
            keep_scripts=False,
        )
        for needle in ("javascript", "email_", "<select", "<button"):
            self.assertNotIn(needle, out)
        self.assertIn('name="q"', out)
        self.assertIn('data-model_name="m/mail.mail"', out)
        self.assertTrue(codes)
        _root, out, codes = clean(
            '<div data-x="JaVa&#9;Script:1" data-v="vbscript:x"'
            ' data-d="data:text/html,x" data-n="Note: hi" data-y="{}"'
            ' data-z="10:30"></div>',
            keep_scripts=False,
        )
        for name in ("data-x", "data-v", "data-d"):
            self.assertNotIn(name, out)
        self.assertIn('data-n="Note: hi"', out)
        self.assertIn('data-y="{}"', out)
        self.assertIn('data-z="10:30"', out)
        self.assertIn("script_removed", codes)

    def test_head_reports_what_it_drops(self):
        findings = []
        out = clean_head(
            '<link rel="stylesheet" href="data:text/css,b{}">'
            '<link rel="stylesheet" t-att-href="x" data-oe-id="1"'
            ' href="/a.css" ::x="1">',
            "p",
            findings,
            HOSTS,
        )
        self.assertNotIn("data:", out)
        self.assertNotIn("t-att", out)
        self.assertIn("/a.css", out)
        codes = sorted(f.code for f in findings)
        self.assertEqual(
            codes, ["head_asset_dropped", "unsafe_markup_removed"]
        )

    def test_count_and_policy_agree_on_encoded_schemes(self):
        source = (
            '<a href="java&#9;script:x">j</a><a href="jav&#10;ascript:y">k</a>'
        )
        root = clean_fragment(source, "p", [], keep_scripts=True)
        before = script_summary(script_counts(root))
        again = lhtml.fragment_fromstring(
            fragment_html(root), create_parent="div"
        )
        self.assertEqual(script_summary(script_counts(again)), before)
        self.assertEqual(before[0], 2)
        apply_script_policy(again, "p", [], keep_scripts=False)
        self.assertNotIn("script:", fragment_html(again).lower())

    def test_use_with_external_href_is_removed(self):
        _root, out, _codes = clean(
            '<svg><use href="https://evil.example/x.svg#a"/>'
            '<use xlink:href="#local"/></svg>'
        )
        self.assertNotIn("evil", out)
        self.assertIn('href="#local"', out)

    def test_css_escapes_cannot_hide_an_import(self):
        for css in (
            "@\\69mport url(https://evil.example/x.css);",
            "@import url(\\68ttps://evil.example/x.css);",
            '@import "\\68ttps://evil.example/x.css";',
            '@\\49MPORT "//evil.example/x.css";',
            '@import "\\2f\\2f evil.example/x.css";',
        ):
            source = "<style>%s</style>" % css
            findings = []
            out = clean_head(source, "p", findings, HOSTS)
            self.assertNotIn("evil", out, css)
            self.assertTrue(findings, css)
            for keep in (True, False):
                root, out, codes = clean(source, keep_scripts=keep)
                self.assertNotIn("evil", out, css)
                self.assertIn("unsafe_markup_removed", codes, css)

    def test_unicode_digits_do_not_forge_a_token(self):
        for ref in ("&#1633;", "&#xFF11;", "&#x661;"):
            for trusted in (False, True):
                source = '<p data-x="DOLIBARRQ%sQ">DOLIBARRQ%sQ</p>' % (
                    ref,
                    ref,
                )
                if trusted:
                    source = assemble(tokenize(source), {}).html
                out = fragment_html(
                    clean_fragment(source, "p", [], trusted_markers=trusted)
                )
                self.assertEqual(ATTR_TOKEN_RE.findall(out), [], source)

    def test_huge_numeric_references_do_not_raise(self):
        digits = "1" * 5000
        self.assertEqual(neutralise("&#%s;" % digits), "&#%s;" % digits)
        self.assertEqual(neutralise("&#x%s;" % digits), "&#x%s;" % digits)
        self.assertFalse(url_allowed("&#%s;" % digits, "href", False))
        for source in (
            '<a href="&amp;#%s;">x</a>' % digits,
            '<a href="&#%s;">x</a>' % digits,
            '<p style="a:&amp;#%s;">x</p>' % digits,
        ):
            try:
                clean(source, keep_scripts=False)
            except PageError:
                pass

    def test_prefixed_attribute_name_still_targets_href(self):
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><a><set'
            b' xmlns:z="http://www.w3.org/1999/xlink" attributeName="z:href"'
            b' to="javascript:alert(1)"/></a></svg>'
        )
        data, removed = sanitize_svg(svg)
        self.assertNotIn(b"<set", data)
        self.assertTrue(removed)
        _root, out, _codes = clean(
            '<svg><a><set attributeName="z:href" to="javascript:x"/></a></svg>'
        )
        self.assertNotIn("<set", out)

    def test_relative_body_import_is_dropped_consistently(self):
        source = '<style>@import url("/local.css")</style><p>k</p>'
        root, out, codes = clean(source, keep_scripts=True)
        self.assertIn("/local.css", out)
        self.assertNotIn("unsafe_markup_removed", codes)
        again = lhtml.fragment_fromstring(out, create_parent="div")
        findings = []
        apply_script_policy(again, "p", findings, keep_scripts=False)
        self.assertNotIn("local.css", fragment_html(again))
        self.assertIn("unsafe_markup_removed", [f.code for f in findings])
        _root, out, codes = clean(source, keep_scripts=False)
        self.assertNotIn("local.css", out)
        self.assertIn("unsafe_markup_removed", codes)

    def test_svg_use_keeps_only_fragments(self):
        data, removed = sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<use href="data:image/svg+xml,x"/><use href="#a"/>'
            b'<image href="data:image/png;base64,AA=="/></svg>'
        )
        self.assertNotIn(b"data:image/svg", data)
        self.assertIn(b'href="#a"', data)
        self.assertIn(b"data:image/png", data)
        self.assertTrue(removed)

    def test_head_assets_lose_event_handlers(self):
        findings = []
        out = clean_head(
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css"'
            ' onload="alert(1)"><style onclick="x()">b{}</style>',
            "p",
            findings,
            HOSTS,
        )
        self.assertNotIn("onload", out)
        self.assertNotIn("onclick", out)
        self.assertIn("fonts.googleapis.com", out)
        self.assertIn("unsafe_markup_removed", [f.code for f in findings])

    def _assert_style_dropped(self, css):
        """css in a <style> goes, with a finding, in head and body."""
        source = "<style>%s</style><p>k</p>" % css
        findings = []
        out = clean_head(source, "p", findings, ("fonts.googleapis.com",))
        self.assertNotIn("<style", out, css)
        self.assertTrue(findings, css)
        for keep in (True, False):
            _root, out, codes = clean(source, keep_scripts=keep)
            self.assertNotIn("<style", out, (css, keep))
            self.assertIn("<p>k</p>", out, (css, keep))
            self.assertIn("unsafe_markup_removed", codes, (css, keep))
            root = lhtml.fragment_fromstring(source, create_parent="div")
            findings = []
            apply_script_policy(root, "p", findings, keep_scripts=keep)
            if not keep:
                self.assertNotIn("<style", fragment_html(root), css)
                self.assertIn(
                    "unsafe_markup_removed", [f.code for f in findings], css
                )

    def test_style_with_a_backslash_is_dropped(self):
        for css in (
            "@import url(\\68\r\nttps://evil.example/x.css);",
            "@\\69\r\nmport url(https://evil.example/x.css);",
            "@\\69mport url(https://evil.example/x.css);",
            "@import url(\\68ttps://evil.example/x.css);",
            '@import "\\68ttps://evil.example/x.css";',
            '@\\49MPORT "//evil.example/x.css";',
            '@import "\\2f\\2f evil.example/x.css";',
            "p{content:'\\201C'}",
        ):
            self._assert_style_dropped(css)

    def test_import_is_read_on_the_raw_text(self):
        for css in (
            '@import "/*"; @import url(https://evil.example/x.css); /* */',
            "@import '/*'; @import url(https://evil.example/x.css);",
            '@import url("/*") ; @import "https://evil.example/x.css";',
            "@import url(\r\n https://evil.example/x.css);",
            "@import\f'//evil.example/x.css';",
            "@import/**/url(https://evil.example/x.css);",
            "@import url(data:text/css,p{});",
            "@import url(https://evil.example/x.css",
            "/* @import */ p{color:red}",
        ):
            self._assert_style_dropped(css)

    def test_allowed_styles_are_kept(self):
        findings = []
        out = clean_head(
            '<style>@import url("https://fonts.googleapis.com/css?family=X");'
            "</style><style>p{color:red}</style>"
            "<style>@IMPORT\r\n url( '/local.css' )\n;</style>",
            "p",
            findings,
            ("fonts.googleapis.com",),
        )
        self.assertIn("fonts.googleapis.com/css?family=X", out)
        self.assertIn("p{color:red}", out)
        self.assertIn("/local.css", out)
        self.assertEqual(findings, [])
        for keep in (True, False):
            _root, out, codes = clean(
                "<style>p{color:red}</style>", keep_scripts=keep
            )
            self.assertIn("p{color:red}", out)
            self.assertEqual(codes, {})

    def test_unreadable_reference_fails_closed(self):
        digits = "1" * 5000
        source = (
            '<div data-success-page="javascript:alert(document.cookie)//'
            '&amp;#%s;">x</div>' % digits
        )
        _root, out, _codes = clean(source, keep_scripts=False)
        self.assertNotIn("data-success-page", out)
        root = lhtml.fragment_fromstring(source, create_parent="div")
        apply_script_policy(root, "p", [], keep_scripts=False)
        self.assertNotIn("javascript", fragment_html(root))
        self.assertFalse(
            style_allowed("width:expression(alert(1));x:&#" + digits + ";")
        )
        self.assertFalse(url_allowed("x&#%s;" % digits, "href", True))


class TestClean(CleanCases, unittest.TestCase):
    pass


COMPANY = {
    "name": "Example Co",
    "email": "info@example.org",
    "phone": "+1 555 0100",
    "website": "https://www.example.org",
    "zip": "H0H 0H0",
    "city": "Exampleville",
    "street": "1 Example Street",
    "address": "1 Example Street\nExampleville H0H 0H0",
    "map_url": "https://maps.example.org/?q=1+Example+Street",
}
BODY = (
    '<h1><dolibarr-q id="1"></dolibarr-q></h1>'
    '<a href="mailto:DOLIBARRQ2Q">m</a>'
    '<p><dolibarr-q id="3"></dolibarr-q> &lt;script&gt;x&lt;/script&gt;</p>'
    '<iframe src="DOLIBARRQ4Q"></iframe>'
    '<dolibarr-q id="5"></dolibarr-q><dolibarr-q id="6"></dolibarr-q>'
    '<dolibarr-q id="7"></dolibarr-q>'
    '<dolibarr-loop id="8"><a href="DOLIBARRQ9Q.php">'
    '<dolibarr-q id="10"></dolibarr-q></a></dolibarr-loop>'
    '<form action="/search.php"><input name="s" value="DOLIBARRQ11Q">'
    '<input type="hidden" name="token" value="DOLIBARRQ12Q"></form>'
    '<form method="post" action=""><input name="email"></form>'
    '<a href="dolibarr-page:about#x">a</a><a href="dolibarr-page:gone">g</a>'
    '<img src="dolibarr-media:image/exemplesite/logo.png">'
    '<img src="dolibarr-media:image/exemplesite/missing.png">'
    '<img src="dolibarr-logo:"><p title="{{ 7*7 }}">t</p>'
    '<p class="x DOLIBARRQ13Q">c</p>'
)
NODES = {
    "1": {"kind": "company", "field": "name"},
    "2": {"kind": "company", "field": "email"},
    "3": {
        "kind": "text",
        "value": "<b>Home</b>",
        "key": "Home",
        "exact": True,
    },
    "4": {"kind": "map"},
    "5": {"kind": "address"},
    "6": {"kind": "include", "ref": "cta"},
    "7": {"kind": "include", "ref": "header"},
    "8": {"kind": "blog_loop", "limit": 3, "line": 4},
    "9": {"kind": "blog_field", "field": "url"},
    "10": {"kind": "blog_field", "field": "title"},
    "11": {"kind": "search_value"},
    "12": {"kind": "drop_element"},
    "13": {"kind": "title"},
}
# Untrusted payload text: QWeb directives, template interpolation in its
# three syntaxes, and markup that tries to leave a raw-text element.
PROBES = (
    "<t t-out=\"__import__('os')\"/>",
    "{{7*7}}",
    "#{y}",
    "%(a)s",
    "</title><script>x</script>",
    '<b t-att-x="1">',
)
EXPRESSION_NAMES = {"res_company", "main_object", "blog", "website", "request"}
DIRECTIVES = {
    "t-name",
    "t-call",
    "t-set",
    "t-value",
    "t-out",
    "t-field",
    "t-options",
    "t-foreach",
    "t-as",
}
TEMPLATES = {
    "website.layout",
    "erplibre_website_import_from_dolibarr.contact_form",
    "erplibre_website_import_from_dolibarr.social_links",
    "erplibre_website_import_from_dolibarr.blog_post_list",
}


def site():
    home = Page(
        ref="home",
        title="Home",
        body_html=BODY,
        qweb_nodes=NODES,
        has_contact_handler=True,
        head_html=(
            '<link rel="stylesheet" href="https://fonts.googleapis.com/x">'
            "<script>var a;</script>"
        ),
    )
    cta = Page(
        ref="cta",
        body_html='<div class="cta"><dolibarr-q id="1"></dolibarr-q></div>',
        qweb_nodes={"1": {"kind": "company", "field": "phone"}},
        analysis_status="container",
    )
    header = Page(
        ref="header", body_html="<nav>n</nav>", analysis_status="container"
    )
    return Site(
        source_key="exemplesite",
        pages=[home, cta, header],
        containers={"header": "header", "cta": "content"},
        head_assets=(
            '<link rel="stylesheet" href="https://fonts.googleapis.com/y">'
        ),
    )


RESOLVER = DictResolver(
    pages={"about": "/about", "home": "/home"},
    media={"image/exemplesite/logo.png": "/medias/image/exemplesite/logo.png"},
    blog_id=7,
    website_id=3,
)


def render(body, nodes=None, target="page", opts=None, resolver=None, **kw):
    """Arch (page) or content (post) of one page added to site()."""
    s = site()
    page = Page(
        ref="p", title="T", body_html=body, qweb_nodes=nodes or {}, **kw
    )
    s.pages.append(page)
    findings = []
    build = page_arch if target == "page" else post_content
    out = build(
        page, s, resolver or RESOLVER, COMPANY, opts or Options(), findings
    )
    return out, findings


class Titled:
    def __init__(self, name):
        self.name = name


def _strip_constants(expr):
    """Expression source with every string literal emptied."""

    class Empty(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                return ast.copy_location(ast.Constant(""), node)
            return node

    return ast.unparse(Empty().visit(ast.parse(expr, mode="eval")))


class RenderCases:
    def assert_arch_is_safe(self, arch, forbidden=()):
        """Every QWeb directive of arch comes from the engine's templates.

        Expressions parse as Python, use only the engine's names, and hold
        source text only inside string literals; t-call and t-name name
        fixed templates; every <t> carries a directive.
        """
        root = etree.fromstring(arch)
        for el in root.iter():
            if el.tag == "t":
                self.assertTrue(
                    any(k.startswith("t-") for k in el.attrib), arch
                )
            self.assertNotEqual(el.tag, "script")
            self.assertNotEqual(el.tag, "title")
            for name, value in el.attrib.items():
                self.assertFalse(name.startswith("data-oe-"), name)
                self.assertNotEqual(name, "groups")
                if not name.startswith("t-"):
                    continue
                self.assertFalse(name.startswith("t-attf"), name)
                self.assertTrue(
                    name in DIRECTIVES or name.startswith("t-att-"), name
                )
                if name == "t-name":
                    self.assertTrue(value.startswith("dolibarr_import.k"))
                    continue
                if name == "t-call":
                    self.assertTrue(
                        value in TEMPLATES
                        or value.startswith("dolibarr_import.k"),
                        value,
                    )
                    continue
                if name in ("t-as", "t-set"):
                    self.assertRegex(value, r"^[a-z_]+$")
                    continue
                tree = ast.parse(value, mode="eval")
                names = {
                    n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                }
                self.assertLessEqual(names, EXPRESSION_NAMES, value)
                code = _strip_constants(value)
                for text in forbidden:
                    self.assertNotIn(text, code)

    def test_keys(self):
        self.assertEqual(
            view_key("exemplesite", "home"),
            "dolibarr_import.k%s.home"
            % hashlib.sha1(b"exemplesite").hexdigest()[:12],
        )
        self.assertTrue(head_key("k").endswith(".head"))
        self.assertTrue(blog_style_key("k").endswith(".blog_style"))
        for ref in ("../x", "a b", "x'}", ""):
            with self.assertRaises(PageError):
                view_key("exemplesite", ref)

    def test_page_arch(self):
        findings = []
        s = site()
        arch = page_arch(
            s.page("home"), s, RESOLVER, COMPANY, Options(), findings
        )
        self.assert_arch_is_safe(arch)
        root = etree.fromstring(arch)
        self.assertEqual(root.get("t-name"), view_key("exemplesite", "home"))
        calls = sorted(e.get("t-call") for e in root.iter() if e.get("t-call"))
        self.assertEqual(
            calls,
            sorted(
                [
                    "website.layout",
                    head_key("exemplesite"),
                    "erplibre_website_import_from_dolibarr.contact_form",
                ]
            ),
        )
        self.assertIn('t-out="res_company.name"', arch)
        self.assertIn(
            "t-att-href=\"'mailto:' + (res_company.email or '')\"", arch
        )
        self.assertIn("google_map_link(13) + '&amp;output=embed'", arch)
        self.assertIn('t-field="res_company.partner_id"', arch)
        self.assertIn('t-out="res_company.phone"', arch)
        self.assertNotIn("<nav>", arch)
        self.assertIn(
            "t-foreach=\"request.env['blog.post'].search([('blog_id', '=', 7)",
            arch,
        )
        self.assertIn("limit=3)", arch)
        self.assertIn("t-att-href=\"(blog.website_url or '')\"", arch)
        self.assertIn('t-out="blog.name"', arch)
        self.assertIn('action="/website/search"', arch)
        self.assertIn("t-att-value=\"request.params.get('search', '')\"", arch)
        self.assertNotIn('name="token"', arch)
        self.assertIn('href="/about#x"', arch)
        self.assertIn('href="/gone.php"', arch)
        self.assertIn('src="/medias/image/exemplesite/logo.png"', arch)
        self.assertIn('src="/medias/image/exemplesite/missing.png"', arch)
        self.assertIn(
            "t-att-src=\"'/web/image/website/%s/logo' % website.id\"", arch
        )
        self.assertIn('title="{{ 7*7 }}"', arch)
        self.assertNotIn("t-attf", arch)
        self.assertIn("t-att-class=\"'x ' + (main_object.name or '')\"", arch)
        self.assertIn("&amp;lt;script&amp;gt;", arch)
        self.assertIn("<b>Home</b>", arch)
        wrap = root.find(".//div[@id='wrap']")
        span = root.find(".//span[@data-for='dolibarr_form_1']")
        self.assertIsNotNone(span)
        self.assertIsNone(wrap.find(".//span[@data-for]"))
        self.assertIn("fonts.googleapis.com/x", arch)
        self.assertNotIn("var a;", arch)
        self.assertIn("t-value=\"'bodywebsite bodywebpage-home'\"", arch)
        self.assertNotIn("DOLIBARRQ", arch)
        self.assertNotIn("dolibarr-", arch.replace("dolibarr_", ""))
        codes = sorted({f.code for f in findings})
        for code in (
            "container_inlined",
            "form_replaced",
            "missing_media",
            "script_removed",
            "search_rewired",
            "unresolved_link",
        ):
            self.assertIn(code, codes)

    def test_post_content_is_frozen(self):
        findings = []
        s = site()
        html = post_content(
            s.page("home"), s, RESOLVER, COMPANY, Options(), findings
        )
        self.assertTrue(html.startswith('<div class="bodywebsite">'))
        self.assertIn("<h1>Example Co</h1>", html)
        self.assertIn('href="mailto:info@example.org"', html)
        self.assertIn("1 Example Street<br>Exampleville H0H 0H0", html)
        self.assertIn("&amp;output=embed", html)
        self.assertIn('src="/web/image/website/3/logo"', html)
        self.assertNotIn(" t-", html)
        self.assertNotIn("blog.name", html)
        self.assertNotIn("<form", html)
        self.assertIn('class="x Home"', html)
        self.assertNotIn("DOLIBARRQ", html)
        self.assertNotIn("dolibarr-", html)
        self.assertIn("php_removed", {f.code for f in findings})
        plain = post_content(
            s.page("home"),
            s,
            RESOLVER,
            COMPANY,
            Options(style_blog_posts=False),
            [],
        )
        self.assertFalse(plain.startswith('<div class="bodywebsite">'))

    def test_head_arch(self):
        s = site()
        arch = head_arch(
            s,
            "/dolibarr-import/exemplesite/styles.css?v=abcd1234",
            "/dolibarr-import/exemplesite/javascript.js",
            RESOLVER,
            Options(keep_scripts=True),
            [],
        )
        self.assert_arch_is_safe(arch.replace("<script", "<x-script"))
        root = etree.fromstring(arch)
        self.assertEqual(root.get("t-name"), head_key("exemplesite"))
        self.assertEqual(
            root[0].get("href"),
            "/dolibarr-import/exemplesite/styles.css?v=abcd1234",
        )
        self.assertEqual(root[1].tag, "script")
        self.assertIn("fonts.googleapis.com/y", arch)
        no_js = head_arch(s, "/c.css", "/j.js", RESOLVER, Options(), [])
        self.assertNotIn("<script", no_js)
        for bad in ("//evil.example/x.css", "javascript:x", "/a b"):
            with self.assertRaises(ValueError):
                head_arch(s, bad, "", RESOLVER, Options(), [])

    def test_lookalike_marker_never_expands(self):
        s = site()
        body = assemble(
            tokenize(
                '<p class="DOLIBARRQ1Q"><dolibarr-q id="1"></dolibarr-q></p>'
            ),
            {},
        ).html
        home = Page(
            ref="p",
            body_html=body,
            qweb_nodes={"1": {"kind": "company", "field": "name"}},
        )
        s.pages.append(home)
        arch = page_arch(home, s, RESOLVER, COMPANY, Options(), [])
        self.assertNotIn("res_company", arch)

    def test_finalize_limits(self):
        deep = etree.Element("t")
        cursor = deep
        for _i in range(260):
            cursor = etree.SubElement(cursor, "div")
        with self.assertRaises(PageError):
            finalize(deep, "p")
        with_comment = etree.Element("t")
        with_comment.append(etree.Comment("c"))
        with self.assertRaises(PageError):
            finalize(with_comment, "p")

    def test_untrusted_payload_text_stays_inert(self):
        body = (
            '<p><dolibarr-q id="1"></dolibarr-q></p>'
            '<p title="DOLIBARRQ2Q" class="DOLIBARRQ3Q DOLIBARRQ2Q">x</p>'
            '<textarea><dolibarr-q id="1"></dolibarr-q></textarea>'
        )
        for probe in PROBES:
            nodes = {
                "1": {"kind": "text", "value": probe, "exact": True},
                "2": {"kind": "text", "value": probe, "exact": True},
                "3": {"kind": "title"},
            }
            arch, _findings = render(body, nodes, seo_title=probe)
            self.assert_arch_is_safe(
                arch, forbidden=("__import__", "7*7", "#{", "%(")
            )
            root = etree.fromstring(arch)
            wrap = root.find(".//div[@id='wrap']")
            self.assertLessEqual(
                {e.tag for e in wrap.iter()},
                {"div", "p", "textarea", "b"},
                "the probe adds no active element: %s" % probe,
            )
            self.assertNotIn("t-att-x", arch)
            dynamic = root.find(".//p[@t-att-class]").get("t-att-class")
            plain = root.find(".//p[@title]").get("title")
            value = eval(  # noqa: S307 - the engine's own output, no builtins
                compile(dynamic, "arch", "eval"),
                {"__builtins__": {}, "main_object": Titled("N")},
            )
            self.assertEqual(value, "N " + plain)
            post, _findings = render(body, nodes, "post", seo_title=probe)
            post_root = lhtml.fragment_fromstring(post)
            for el in post_root.iter():
                self.assertNotIn(el.tag, ("t", "script", "title"))
                self.assertFalse(
                    any(k.startswith("t-") for k in el.attrib), post
                )

    def test_source_qweb_never_reaches_the_arch(self):
        body = (
            '<div t-out="1" T-Call="x" data-oe-model="m" groups="g">a</div>'
            '<t t-call="evil.view"><b>kept</b></t><!-- c --><?pi x?>'
            '<p><T t-raw="2">t</T></p>'
        )
        for keep in (False, True):
            arch, _findings = render(body, opts=Options(keep_scripts=keep))
            self.assert_arch_is_safe(arch.replace("<script", "<x-script"))
            self.assertNotIn("evil", arch)
            self.assertIn("<b>kept</b>", arch)
            root = etree.fromstring(arch)
            wrap = root.find(".//div[@id='wrap']")
            self.assertEqual(
                [e.tag for e in wrap.iter()], ["div", "div", "b", "p"]
            )

    def test_finalize_reparse_adds_nothing(self):
        view = etree.Element("t", {"t-name": "dolibarr_import.kx.p"})
        div = etree.SubElement(view, "div", {"title": '"><t t-out="1"/>'})
        div.text = '<t t-out="x"/> &lt;t&gt; &#116;-out &#68;OLIBARRQ1Q'
        etree.SubElement(div, "p", {"class": "&#116;-out &amp;lt;t"})
        arch = finalize(view, "p")
        root = etree.fromstring(arch)
        self.assertEqual([e.tag for e in root.iter()], ["t", "div", "p"])
        self.assertEqual(
            [sorted(e.attrib) for e in root.iter()],
            [["t-name"], ["title"], ["class"]],
        )
        # QWeb writes arch text as is: one level of escape remains.
        self.assertEqual(
            root[0].text,
            "&lt;t t-out=&#34;x&#34;/&gt; &amp;lt;t&amp;gt; &amp;#116;-out"
            " &amp;#68;OLIBARRQ1Q",
        )
        self.assertEqual(root[0][0].get("class"), "&#116;-out &amp;lt;t")

    def test_entity_spelled_markers_stay_inert(self):
        nodes = {"1": {"kind": "company", "field": "name"}}
        for source in (
            '<p class="&#68;OLIBARRQ1Q">a</p>',
            '<p class="DOLIBARRQ&#1633;Q">a</p>',
            "<p>&#68;OLIBARRQ1Q &lt;dolibarr-q id=&quot;1&quot;&gt;</p>",
        ):
            body = assemble(tokenize(source), {}).html
            arch, _findings = render(body, nodes)
            self.assertNotIn("res_company", arch, source)
            self.assertNotIn("DOLIBARRQ1Q", arch, source)
        arch, _findings = render('<p class="DOLIBARRQ١Q">a</p>', nodes)
        self.assertNotIn("res_company", arch)

    def test_markers_in_textarea_and_title(self):
        nodes = {
            "1": {"kind": "company", "field": "name"},
            "2": {"kind": "company", "field": "phone"},
        }
        arch, findings = render(
            '<textarea title="DOLIBARRQ2Q"><dolibarr-q id="1">'
            "</dolibarr-q></textarea>"
            '<title><dolibarr-q id="2"></dolibarr-q></title>',
            nodes,
        )
        area = etree.fromstring(arch).find(".//textarea")
        self.assertEqual(area[0].get("t-out"), "res_company.name")
        self.assertEqual(area.get("t-att-title"), "(res_company.phone or '')")
        self.assertNotIn("<title", arch)
        self.assertNotIn("DOLIBARRQ", arch)
        self.assertNotIn("dolibarr-q", arch)
        self.assertIn(
            "<title>", findings_what(findings, "unsafe_markup_removed")
        )
        post, _findings = render(
            '<textarea><dolibarr-q id="1"></dolibarr-q></textarea>',
            nodes,
            "post",
        )
        self.assertIn("<textarea>Example Co</textarea>", post)

    def test_blog_limit_is_at_least_one(self):
        arch, _findings = render(
            '<dolibarr-loop id="1"><p>x</p></dolibarr-loop>'
            '<dolibarr-q id="2"></dolibarr-q>',
            {
                "1": {"kind": "blog_loop", "limit": 0},
                "2": {"kind": "blog_list", "limit": 0},
            },
        )
        self.assertIn("limit=1)", arch)
        self.assertNotIn("limit=0", arch)
        self.assertIn('t-set="blog_limit" t-value="1"', arch)

    def test_blog_fields_need_a_loop(self):
        arch, _findings = render(
            '<a href="DOLIBARRQ1Q.php"><dolibarr-q id="2"></dolibarr-q></a>',
            {
                "1": {"kind": "blog_field", "field": "url"},
                "2": {"kind": "blog_field", "field": "title"},
            },
        )
        self.assertNotIn("blog.", arch)

    def test_removals_are_accounted(self):
        loop = '<dolibarr-loop id="1"><h3>card</h3></dolibarr-loop>'
        form = '<form method="post" action="p.php"><input name="n"></form>'
        _post, findings = render(
            loop + form + '<dolibarr-q id="2"></dolibarr-q>',
            {
                "1": {"kind": "blog_loop", "limit": 3, "line": 12},
                "2": {"kind": "social", "line": 20},
            },
            "post",
            has_contact_handler=True,
        )
        removed = {
            f.params["code"]: f.params
            for f in findings
            if f.code == "php_removed"
        }
        self.assertEqual(removed["blog loop"]["line"], "12")
        self.assertEqual(removed["blog loop"]["bytes"], str(len(loop)))
        self.assertEqual(removed["contact form"]["bytes"], str(len(form)))
        self.assertEqual(removed["social links loop"]["line"], "20")

    def test_links_resolve_before_the_script_policy(self):
        body = (
            '<a href="dolibarr-page:about?a=1#b">a</a>'
            '<img src="dolibarr-media:image/exemplesite/logo.png"'
            ' srcset="dolibarr-media:image/exemplesite/logo.png 2x">'
            "<div style=\"background:url('dolibarr-media:image/exemplesite/"
            "logo.png')\">d</div>"
            '<a href="javascript:alert(1)" onclick="x()">j</a>'
        )
        for target in ("page", "post"):
            out, _findings = render(body, target=target)
            self.assertIn('href="/about?a=1#b"', out)
            self.assertIn('src="/medias/image/exemplesite/logo.png"', out)
            self.assertIn(
                'srcset="/medias/image/exemplesite/logo.png 2x"', out
            )
            self.assertIn("url('/medias/image/exemplesite/logo.png')", out)
            self.assertNotIn("javascript", out)
            self.assertNotIn("onclick", out)

    def test_markers_in_script_vectors_are_policed(self):
        nodes = {"1": {"kind": "company", "field": "name"}}
        arch, _findings = render(
            '<a onclick="DOLIBARRQ1Q" href="javascript:DOLIBARRQ1Q">a</a>'
            '<iframe src="http://x.example.org/DOLIBARRQ1Q"></iframe>',
            nodes,
        )
        self.assertNotIn("res_company", arch)
        self.assertNotIn("onclick", arch)
        self.assertNotIn("<iframe", arch)

    def test_resolver_output_must_be_a_site_path(self):
        hostile = DictResolver(
            pages={
                "a": "//evil.example/a",
                "b": "javascript:alert(1)",
                "c": "",
                "d": "/\\evil.example",
                "e": "/ok",
            },
            media={"image/exemplesite/x.png": "https://evil.example/x"},
        )
        arch, findings = render(
            '<a href="dolibarr-page:a">1</a><a href="dolibarr-page:b">2</a>'
            '<a href="dolibarr-page:c">3</a><a href="dolibarr-page:d">4</a>'
            '<a href="dolibarr-page:e?//evil.example">5</a>'
            '<a href="dolibarr-page:x?//evil.example">6</a>'
            '<img src="dolibarr-media:image/exemplesite/x.png">',
            resolver=hostile,
        )
        hrefs = [e.get("href") for e in etree.fromstring(arch).iter("a")]
        self.assertEqual(
            hrefs,
            [
                "/a.php",
                "/b.php",
                "/c.php",
                "/d.php",
                "/ok?//evil.example",
                "/x.php?//evil.example",
            ],
        )
        self.assertIn('src="/medias/image/exemplesite/x.png"', arch)
        codes = [f.code for f in findings]
        self.assertEqual(codes.count("unresolved_link"), 5)
        self.assertEqual(codes.count("missing_media"), 1)

    def test_style_text_is_byte_exact(self):
        styles = (
            "&#64;import url(//evil.example/x.css)",
            'a{content:"&#92;66"}',
        )
        body = "".join("<style>%s</style>" % css for css in styles)
        head = "".join("<style>%s</style>" % css for css in styles)
        for keep in (False, True):
            arch, _findings = render(
                body, head_html=head, opts=Options(keep_scripts=keep)
            )
            root = etree.fromstring(arch)
            texts = [el.text for el in root.iter("style")]
            self.assertEqual(texts, list(styles) * 2)
            self.assertNotIn("@import", arch)
            self.assertNotIn("\\", arch)
        s = site()
        s.head_assets = head
        arch = head_arch(s, "", "", RESOLVER, Options(), [])
        self.assertEqual(
            [el.text for el in etree.fromstring(arch).iter("style")],
            list(styles),
        )

    def test_menu_labels_are_not_rendered(self):
        s = site()
        s.menu = [MenuItem(label="<t t-out=\"'menu-probe'\"/>", target="/")]
        arch = page_arch(s.page("home"), s, RESOLVER, COMPANY, Options(), [])
        self.assertNotIn("menu-probe", arch)

    def test_include_cycle_and_depth(self):
        s = site()
        chain = [
            Page(
                ref="c%d" % i,
                body_html='<i>%d</i><dolibarr-q id="1"></dolibarr-q>' % i,
                qweb_nodes={"1": {"kind": "include", "ref": "c%d" % (i + 1)}},
                analysis_status="container",
            )
            for i in range(30)
        ]
        chain.append(
            Page(
                ref="loop",
                body_html='<dolibarr-q id="1"></dolibarr-q>',
                qweb_nodes={"1": {"kind": "include", "ref": "loop"}},
            )
        )
        s.pages.extend(chain)
        findings = []
        page = Page(
            ref="p",
            body_html='<dolibarr-q id="1"></dolibarr-q>'
            '<dolibarr-q id="2"></dolibarr-q>'
            '<dolibarr-q id="3"></dolibarr-q>',
            qweb_nodes={
                "1": {"kind": "include", "ref": "c0"},
                "2": {"kind": "include", "ref": "loop"},
                "3": {"kind": "include", "ref": "nowhere"},
            },
        )
        arch = page_arch(page, s, RESOLVER, COMPANY, Options(), findings)
        self.assertIn("<i>19</i>", arch)
        self.assertNotIn("<i>20</i>", arch)
        codes = sorted(
            f.params["code"] for f in findings if f.code == "php_removed"
        )
        self.assertEqual(
            codes,
            [
                "includeContainer c20: include deeper than 20 levels",
                "includeContainer loop: include cycle",
                "includeContainer nowhere: missing container",
            ],
        )

    def test_include_budget(self):
        s = site()
        s.pages.append(
            Page(
                ref="wide",
                body_html='<dolibarr-q id="1"></dolibarr-q>' * 3,
                qweb_nodes={"1": {"kind": "include", "ref": "leaf"}},
            )
        )
        s.pages.append(Page(ref="leaf", body_html="<i>leaf</i>"))
        many = Page(
            ref="p",
            body_html='<dolibarr-q id="1"></dolibarr-q>' * 100,
            qweb_nodes={"1": {"kind": "include", "ref": "wide"}},
        )
        findings = []
        arch = page_arch(many, s, RESOLVER, COMPANY, Options(), findings)
        self.assertEqual(arch.count("<i>leaf</i>"), 150)
        self.assertIn(
            "includeContainer wide: more than 200 includes",
            {f.params.get("code") for f in findings},
        )

    def test_resolved_urls_never_become_markers(self):
        nodes = {
            "1": {"kind": "company", "field": "name"},
            "3": {"kind": "drop_element"},
        }
        marker = '<p><dolibarr-q id="1"></dolibarr-q></p>'
        for source, home in (
            (
                '<img src="/medias/image/exemplesite/%44OLIBARRQ1Q.png">',
                "home",
            ),
            ('<a href="index.php?pageref=%44OLIBARRQ1Q">x</a>', "home"),
            ('<a href="/">home</a>', "DOLIBARRQ3Q"),
        ):
            for keep in (False, True):
                body = marker + stored(source, home=home)
                arch, findings = render(
                    body, nodes, opts=Options(keep_scripts=keep)
                )
                root = etree.fromstring(arch)
                live = [
                    (el.tag, name)
                    for el in root.iter()
                    for name in el.attrib
                    if name.startswith("t-att")
                ]
                self.assertEqual(live, [], source)
                self.assertEqual(arch.count("res_company"), 1, source)
                self.assertEqual(
                    len(root.findall(".//img")) + len(root.findall(".//a")),
                    1,
                    "the element is kept, not dropped: %s" % source,
                )
        lookalike = DictResolver(pages={"a": "/DOLIBARRQ1Q"})
        arch, findings = render(
            marker + '<a href="dolibarr-page:a">a</a>',
            nodes,
            resolver=lookalike,
        )
        self.assertIn('href="/a.php"', arch)
        self.assertIn("unresolved_link", {f.code for f in findings})

    def test_expanded_values_meet_the_element_rules(self):
        body = (
            '<form method="post" action="DOLIBARRQ1Q">'
            '<input type="hidden" name="DOLIBARRQ2Q" value="someone@evil.test">'
            '<input name="DOLIBARRQ3Q"><button>s</button></form>'
            '<p><input name="DOLIBARRQ2Q" value="v"></p>'
        )
        nodes = {
            "1": {"kind": "text", "value": "/website/form/mail.mail"},
            "2": {"kind": "text", "value": "email_to"},
            "3": {"kind": "text", "value": "email_cc"},
        }
        for keep in (False, True):
            for target in ("page", "post"):
                out, findings = render(
                    body, nodes, target, opts=Options(keep_scripts=keep)
                )
                self.assertNotIn("website/form", out)
                self.assertNotIn("email_to", out)
                self.assertNotIn("email_cc", out)
                self.assertNotIn("someone@evil.test", out)
                self.assertIn("form_removed", {f.code for f in findings})
        dynamic = (
            '<form method="post" action="/x?DOLIBARRQ1Q"><input name="a">'
            '</form><iframe src="https://x.example.org/?q=DOLIBARRQ1Q">'
            '</iframe><input name="DOLIBARRQ1Q">'
        )
        for keep in (False, True):
            arch, findings = render(
                dynamic,
                {"1": {"kind": "company", "field": "name"}},
                opts=Options(keep_scripts=keep),
            )
            self.assertNotIn("res_company", arch)
            self.assertIn(
                "dynamic",
                findings_what(findings, "unsafe_markup_removed"),
            )

    def test_refused_dynamic_iframe_src_drops_the_iframe(self):
        arch, findings = render(
            '<p>kept</p><iframe src="https://x.example.org/?q=DOLIBARRQ1Q">'
            "</iframe>",
            {"1": {"kind": "company", "field": "name"}},
        )
        self.assertIn("kept", arch)
        self.assertNotIn("iframe", arch)
        self.assertIn(
            "dynamic iframe src",
            findings_what(findings, "unsafe_markup_removed"),
        )

    def test_source_text_needs_a_fixed_scheme_in_urls(self):
        nodes = {"1": {"kind": "title"}}
        arch, findings = render(
            '<a href="DOLIBARRQ1Q">a</a><a href="/t/DOLIBARRQ1Q">b</a>'
            '<p style="color:DOLIBARRQ1Q">c</p><p class="DOLIBARRQ1Q">d</p>',
            nodes,
        )
        root = etree.fromstring(arch)
        links = root.findall(".//a")
        self.assertEqual(dict(links[0].attrib), {})
        self.assertEqual(
            links[1].get("t-att-href"), "'/t/' + (main_object.name or '')"
        )
        self.assertIsNone(root.find(".//p[@t-att-style]"))
        self.assertIsNotNone(root.find(".//p[@t-att-class]"))
        self.assertIn(
            "dynamic a href", findings_what(findings, "unsafe_markup_removed")
        )

    def test_bare_slash_prefix_does_not_bind_source_text(self):
        """A live title such as "/evil.example.org" after "/" would
        make a link to another host."""
        arch, findings = render(
            '<a href="/DOLIBARRQ1Q">a</a>', {"1": {"kind": "title"}}
        )
        self.assertNotIn("main_object", arch)
        self.assertIn(
            "dynamic a href", findings_what(findings, "unsafe_markup_removed")
        )
        self.assertEqual(dict(etree.fromstring(arch).find(".//a").attrib), {})

    def test_source_text_binds_only_to_inert_attributes(self):
        nodes = {
            "1": {"kind": "blog_loop", "limit": 3},
            "2": {"kind": "blog_field", "field": "title"},
        }
        source = (
            '<dolibarr-loop id="1"><svg><a><animate attributeName="DOLIBARRQ2Q"'
            ' to="javascript:alert(document.domain)" begin="0s" fill="freeze"/>'
            '<text y="20">x</text></a><set attributeName="DOLIBARRQ2Q"'
            ' to="javascript:1"/><set attributeName="DOLIBARRQ2Q" to="/ok"/>'
            '</svg><p class="DOLIBARRQ2Q" title="DOLIBARRQ2Q"'
            ' aria-label="DOLIBARRQ2Q" lang="DOLIBARRQ2Q" id="DOLIBARRQ2Q">'
            "t</p></dolibarr-loop>"
        )
        for keep in (False, True):
            root = clean_fragment(
                source, "p", [], keep_scripts=keep, trusted_markers=True
            )
            body = fragment_html(root)
            for target in ("page", "post"):
                out, findings = render(
                    body, nodes, target, opts=Options(keep_scripts=keep)
                )
                self.assertNotIn("javascript", out)
                self.assertNotIn("attributename", out.lower())
                if target == "post":
                    continue
                arch = etree.fromstring(out)
                para = arch.find(".//p")
                self.assertEqual(
                    sorted(para.attrib),
                    ["t-att-aria-label", "t-att-class", "t-att-title"],
                )
                what = findings_what(findings, "unsafe_markup_removed")
                self.assertIn("dynamic set attributename", what)
                self.assertIn("dynamic p id", what)

    def test_animation_values_are_url_checked(self):
        for tag in ("animate", "set", "animateMotion", "animateTransform"):
            for attr in ("to", "from", "values", "by"):
                value = (
                    "0;javascript:alert(1)"
                    if attr == "values"
                    else (" jav&#x09;ascript:alert(1)")
                )
                body = '<svg><a><%s attributeName="x" %s="%s"/></a></svg>' % (
                    tag,
                    attr,
                    value,
                )
                for keep in (False, True):
                    _root, out, codes = clean(body, keep_scripts=keep)
                    self.assertNotIn("ascript", out, (tag, attr))
                    if attr != "by":  # not allow-listed: stripped silently
                        self.assertIn("unsafe_markup_removed", codes)
                    arch, findings = render(
                        body, opts=Options(keep_scripts=keep)
                    )
                    self.assertNotIn("ascript", arch, (tag, attr))
        _root, out, _codes = clean(
            '<svg><rect><animate attributeName="x" from="0" to="10"'
            ' values="0;5;10"/></rect></svg>'
        )
        self.assertIn('values="0;5;10"', out)

    def test_marker_action_form_is_the_pages_own(self):
        body = (
            '<form method="post" action="DOLIBARRQ1Q"><input name="n"></form>'
        )
        nodes = {"1": {"kind": "text", "value": "/thanks"}}
        arch, findings = render(body, nodes, has_contact_handler=True)
        self.assertIn(
            't-call="erplibre_website_import_from_dolibarr.contact_form"', arch
        )
        self.assertNotIn("<form", arch)
        self.assertIn("form_replaced", {f.code for f in findings})
        arch, findings = render(body, nodes)
        self.assertIn('<form method="post" action="/thanks">', arch)
        self.assertNotIn("contact_form", arch)
        self.assertNotIn("form_replaced", {f.code for f in findings})

    def test_raw_text_payload_in_foreign_content_is_dropped(self):
        payloads = (
            "<style>&#64;import url(//evil.example/x.css);</style>",
            '<style>&#x40;import "//evil.example/y.css";</style>',
            "<style>a{}<img src=x onerror=alert(1)></style>",
        )
        for payload in payloads:
            nodes = {"1": {"kind": "text", "value": payload}}
            for wrapper in ("svg", "math"):
                body = '<%s><dolibarr-q id="1"></dolibarr-q></%s>' % (
                    wrapper,
                    wrapper,
                )
                for keep in (False, True):
                    for target in ("page", "post"):
                        out, findings = render(
                            body,
                            nodes,
                            target,
                            opts=Options(keep_scripts=keep),
                        )
                        self.assertNotIn("<style", out, payload)
                        self.assertNotIn("evil", out, payload)
                        self.assertNotIn("onerror", out, payload)
                        self.assertIn(
                            "<style>",
                            findings_what(findings, "unsafe_markup_removed"),
                        )
        s = site()
        s.pages.append(
            Page(
                ref="cst",
                body_html="<style>&#64;import url(//evil.example/x.css);</style>",
                analysis_status="container",
            )
        )
        page = Page(
            ref="p",
            body_html='<svg><dolibarr-q id="1"></dolibarr-q></svg>',
            qweb_nodes={"1": {"kind": "include", "ref": "cst"}},
        )
        for keep in (False, True):
            arch = page_arch(
                page, s, RESOLVER, COMPANY, Options(keep_scripts=keep), []
            )
            self.assertNotIn("<style", arch)

    def test_media_names_resolve(self):
        names = ("a b,c(1).png", "a(1).png", "été.png")
        media = {
            "image/exemplesite/%s"
            % name: "/medias/image/exemplesite/%s"
            % name
            for name in names
        }
        resolver = DictResolver(media=media, website_id=3)
        body = stored(
            '<img src="/medias/image/exemplesite/a b,c(1).png">'
            "<div style=\"background:url('/medias/image/exemplesite/"
            "a(1).png')\">d</div>"
            '<img src="/medias/image/exemplesite/été.png">'
        )
        for keep in (False, True):
            for target in ("page", "post"):
                out, findings = render(
                    body,
                    target=target,
                    resolver=resolver,
                    opts=Options(keep_scripts=keep),
                )
                self.assertNotIn("dolibarr-", out)
                self.assertNotIn(
                    "missing_media", {f.code for f in findings}, out
                )
                self.assertIn("/medias/image/exemplesite/a%20b,c(1).png", out)
                self.assertIn("url('/medias/image/exemplesite/a(1).png')", out)
                self.assertIn(
                    "/medias/image/exemplesite/%C3%A9t%C3%A9.png", out
                )
        out, findings = render(
            '<img src="dolibarr-media:image/exemplesite/%2e%2e/x.png">'
            "<div style=\"background:url('dolibarr-media:image/other/x.png')\">"
            "d</div>",
            opts=Options(keep_scripts=True),
        )
        self.assertNotIn("..", out)
        self.assertNotIn("dolibarr-", out)
        unknown, findings = render(
            "<div style=\"background:url('dolibarr-media:image/exemplesite/"
            "n(1).png')\">d</div>",
            opts=Options(keep_scripts=True),
        )
        self.assertIn("url('/medias/image/exemplesite/n(1).png')", unknown)
        self.assertIn("missing_media", {f.code for f in findings})

    def test_inlined_page_size_is_bounded(self):
        s = site()
        s.pages.append(
            Page(
                ref="big",
                body_html="<p>%s</p>" % ("a" * (MAX_TEXT // 150)),
                analysis_status="container",
            )
        )
        page = Page(
            ref="p",
            body_html='<dolibarr-q id="1"></dolibarr-q>' * 160,
            qweb_nodes={"1": {"kind": "include", "ref": "big"}},
        )
        for build in (page_arch, post_content):
            with self.assertRaisesRegex(PageError, "larger than 10 MB"):
                build(page, s, RESOLVER, COMPANY, Options(), [])
        page.body_html = '<dolibarr-q id="1"></dolibarr-q>' * 140
        page_arch(page, s, RESOLVER, COMPANY, Options(), [])

    def test_inlining_stops_once_the_size_cap_is_passed(self):
        s = site()
        s.pages.append(
            Page(
                ref="big",
                body_html="<p>%s</p>" % ("a" * (MAX_TEXT // 20)),
                analysis_status="container",
            )
        )
        page = Page(
            ref="p",
            body_html='<dolibarr-q id="1"></dolibarr-q>' * 200,
            qweb_nodes={"1": {"kind": "include", "ref": "big"}},
        )
        with mock.patch.object(
            html2arch, "_parse", wraps=html2arch._parse
        ) as parsed:
            with self.assertRaisesRegex(PageError, "larger than 10 MB"):
                page_arch(page, s, RESOLVER, COMPANY, Options(), [])
        # The page itself, then about 20 inlines: never all 200.
        self.assertLessEqual(parsed.call_count, 22)

    def test_srcset_url_with_comma_resolves_whole(self):
        resolver = DictResolver(
            media={
                "image/exemplesite/a,b.png": "/medias/image/exemplesite/a,b.png",
                "image/exemplesite/c.png": "/medias/image/exemplesite/c.png",
            }
        )
        body = stored(
            '<img srcset="image/exemplesite/a,b.png 1x,'
            ' image/exemplesite/c.png 2x">'
        )
        for keep in (False, True):
            for target in ("page", "post"):
                out, findings = render(
                    body,
                    target=target,
                    resolver=resolver,
                    opts=Options(keep_scripts=keep),
                )
                self.assertIn(
                    'srcset="/medias/image/exemplesite/a,b.png 1x,'
                    ' /medias/image/exemplesite/c.png 2x"',
                    out,
                )
                self.assertNotIn("missing_media", {f.code for f in findings})

    def test_contact_form_removal_has_a_line(self):
        _post, findings = render(
            '<p>a</p>\n<p>b</p>\n<form method="post" action="">'
            '<input name="n"></form>',
            target="post",
            has_contact_handler=True,
        )
        removed = [
            f.params
            for f in findings
            if f.params.get("code") == "contact form"
        ]
        self.assertEqual(removed[0]["line"], "3")

    def test_text_size_limits(self):
        big = "<" * (MAX_TEXT // 4 + 1)
        view = etree.Element("t", {"t-name": "dolibarr_import.kx.p"})
        etree.SubElement(view, "p").text = big
        with self.assertRaisesRegex(PageError, "text node larger"):
            finalize(view, "p")
        view = etree.Element("t", {"t-name": "dolibarr_import.kx.p"})
        etree.SubElement(view, "p").text = "a" * (MAX_TEXT // 4 + 1)
        finalize(view, "p")
        page = Page(
            ref="p",
            body_html='<p><dolibarr-q id="1"></dolibarr-q></p>',
            qweb_nodes={"1": {"kind": "company", "field": "name"}},
        )
        company = dict(COMPANY, name="a" * (MAX_TEXT + 1))
        with self.assertRaisesRegex(PageError, "text node larger"):
            post_content(page, site(), RESOLVER, company, Options(), [])


def stored(source, home="home", keep=True):
    """Body HTML as the pipeline stores it: assembled, cleaned, tokenized."""
    asm = assemble(tokenize(source), {})
    root = clean_fragment(
        asm.html, "p", [], keep_scripts=keep, trusted_markers=True
    )
    rewrite_links(root, "exemplesite", home)
    return fragment_html(root)


def findings_what(findings, code):
    return " ".join(
        f.params.get("what", "") for f in findings if f.code == code
    )


class TestRender(RenderCases, unittest.TestCase):
    pass


class Company:
    """Stand-in for res_company when a t-att- expression is evaluated."""

    def __init__(self, **values):
        for field in ("name", "email", "phone", "website"):
            setattr(self, field, values.get(field, False))


# Company values a user with contact rights can set after the import.
HOSTILE_VALUES = (
    "java\tscript:alert(document.domain)//",
    "javascript:alert(1)",
    " javascript:alert(1)",
    "JavaScript:alert(1)",
    "\x01javascript:alert(1)",
    "data:text/html,x",
    "vbscript:x",
    "mailto:x@example.org",
    "//evil.example/x",
)


def live_value(arch, tag, attr, **company):
    """Value a visitor gets for tag's t-att-<attr>, or None when unbound."""
    el = etree.fromstring(arch).find(".//%s" % tag)
    expr = el.get("t-att-%s" % attr) if el is not None else None
    if expr is None:
        return None
    return eval(
        expr, {"__builtins__": {}}, {"res_company": Company(**company)}
    )


class TestCompanyValues(unittest.TestCase):
    def render_one(self, body, field):
        return render(body, {"1": {"kind": "company", "field": field}})

    def test_bare_url_values_are_guarded(self):
        benign = {
            "email": ("info@example.org", "mailto:info@example.org"),
            "phone": ("+1 555 0100", "tel:+1 555 0100"),
            "website": ("https://www.example.org", "https://www.example.org"),
        }
        for field, (value, expected) in benign.items():
            for suffix in ("", "/x"):
                arch, _findings = self.render_one(
                    '<a href="DOLIBARRQ1Q%s">a</a>' % suffix, field
                )
                self.assertEqual(
                    live_value(arch, "a", "href", **{field: value}),
                    expected + suffix,
                    field,
                )
                self.assertEqual(live_value(arch, "a", "href"), "", field)
                for hostile in HOSTILE_VALUES:
                    got = live_value(arch, "a", "href", **{field: hostile})
                    self.assertTrue(
                        url_allowed(got, "href", False), (field, got)
                    )
                    self.assertNotIn("//evil", got[:7], (field, got))
        arch, _findings = self.render_one(
            '<a href="DOLIBARRQ1Q">a</a>', "website"
        )
        self.assertEqual(
            live_value(arch, "a", "href", website="http://example.org"),
            "http://example.org",
        )

    def test_fixed_prefix_binds_the_value(self):
        for prefix, field in (
            ("mailto:", "email"),
            ("tel:", "phone"),
            ("/c/", "name"),
            ("https://h.example.org/", "name"),
            ("HTTPS://h.example.org/p?q=", "name"),
        ):
            arch, _findings = self.render_one(
                '<a href="%sDOLIBARRQ1Q">a</a>' % prefix, field
            )
            self.assertEqual(
                live_value(arch, "a", "href", **{field: "v"}),
                prefix + "v",
                prefix,
            )

    def test_unsafe_prefix_or_value_is_refused(self):
        for href, field in (
            ("/DOLIBARRQ1Q", "name"),
            ("java DOLIBARRQ1Q", "name"),
            ("DOLIBARRQ1Q", "name"),
            ("DOLIBARRQ1Q", "city"),
            ("https://h.example.orgDOLIBARRQ1Q", "name"),
            ("http://h.example.org/DOLIBARRQ1Q", "name"),
            ("#DOLIBARRQ1Q", "name"),
        ):
            arch, findings = self.render_one(
                '<a href="%s">a</a>' % href, field
            )
            self.assertNotIn("res_company", arch, href)
            self.assertIn(
                "dynamic a href",
                findings_what(findings, "unsafe_markup_removed"),
                href,
            )

    def test_active_attributes_are_refused(self):
        for html in (
            '<p style="color:DOLIBARRQ1Q">x</p>',
            '<p id="DOLIBARRQ1Q">x</p>',
            '<p data-x="DOLIBARRQ1Q">x</p>',
            '<img srcset="/a/DOLIBARRQ1Q 2x">',
            '<svg><rect><animate attributeName="DOLIBARRQ1Q" to="1"/>'
            "</rect></svg>",
            '<svg><a><set attributeName="href" to="DOLIBARRQ1Q"/></a></svg>',
            '<svg><rect><animate attributeName="x" values="DOLIBARRQ1Q"/>'
            "</rect></svg>",
            '<svg><rect><animate attributeName="x" from="/a/DOLIBARRQ1Q"/>'
            "</rect></svg>",
        ):
            for field in ("name", "email"):
                arch, findings = self.render_one(html, field)
                self.assertNotIn("res_company", arch, html)
                self.assertTrue(
                    findings_what(findings, "unsafe_markup_removed"), html
                )

    def test_animation_refuses_every_live_value(self):
        for node in (
            {"kind": "logo"},
            {"kind": "title"},
            {"kind": "company", "field": "name"},
        ):
            arch, _findings = render(
                '<svg><rect><animate attributeName="x"'
                ' from="/a/DOLIBARRQ1Q" to="DOLIBARRQ1Q"/></rect></svg>',
                {"1": node},
            )
            self.assertNotIn("t-att-", arch, node)

    def test_inert_attributes_still_bind(self):
        arch, _findings = self.render_one(
            '<p title="DOLIBARRQ1Q" class="c DOLIBARRQ1Q"'
            ' aria-label="DOLIBARRQ1Q">x</p>'
            '<img alt="DOLIBARRQ1Q" src="/a.png">',
            "email",
        )
        root = etree.fromstring(arch)
        para = root.find(".//p")
        self.assertEqual(
            sorted(k for k in para.attrib if k.startswith("t-att-")),
            ["t-att-aria-label", "t-att-class", "t-att-title"],
        )
        self.assertEqual(
            root.find(".//img").get("t-att-alt"), "(res_company.email or '')"
        )
