# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time
import unittest

from lxml import html as lhtml

from ..css import evaluate_css, is_empty_js, rescope, unwrap_php
from ..html2arch import style_allowed, url_allowed
from ..urls import (
    LOGO,
    MEDIA,
    PAGE,
    is_logo,
    local_path,
    media_relpath,
    page_link,
    rewrite_links,
    rewrite_url,
    split_token,
)

KEY = "exemplesite"

STYLES = (
    "<?php // BEGIN PHP\n$websitekey = basename(__DIR__);\n// END PHP ?>\n"
    "html { color: <?php echo empty($website->maincolor) ? '#123456'"
    " : $website->maincolor; ?>; }\n"
    "body { background: url(medias/image/exemplesite/bg.jpg); }\n"
    ".bodywebsite a::after { content: '<?php echo $website->ref; ?>'; }\n"
    ":root { --x: 1; }\n"
    "@media (max-width: 10px) { body.bodywebsite p, body > div { m: 0 } }\n"
    "h1 { font: <?php echo getDolGlobalString('X') ?: 'serif'; ?>; }\n"
    "h2 { x: <?php echo $conf->global->SECRET; ?>; }\n"
    "<?php // BEGIN PHP\n$tmp = ob_get_contents(); ob_end_clean();"
    " dolWebsiteOutput($tmp, 'css');\n// END PHP"
)

UNSAFE_LITERALS = (
    "red; } body { display: none",
    "a}b",
    "a{b",
    "a<b",
    "a>b",
    "a\\\\b",
    'a"b',
    'a"b',
    "a/*b",
    "@import x",
    "url(http://x.test/a)",
    "a)b(",
    "x" * 100,
)

HOSTILE = (
    "../x.php",
    "medias/image/exemplesite/../../../etc/passwd",
    "medias/image/exemplesite/%2e%2e/x.png",
    "medias/image/exemplesite/%2E%2E/x.png",
    "medias/image/exemplesite/a%2fb.png",
    "medias/image/exemplesite/a%5cb.png",
    "medias/image%2fexemplesite/a.png",
    "medias/image/exemplesite/%252e%252e/x.png",
    "medias\\image\\exemplesite\\a.png",
    "medias/image/exemplesite/..\\x.png",
    "medias/image/exemplesite/a.png%00.js",
    "viewimage.php?modulepart=medias&file=image/exemplesite/../x.png",
    "viewimage.php?modulepart=medias&file=image/exemplesite/%2e%2e/x.png",
    "viewimage.php?modulepart=medias&file=image/exemplesite\\..\\x.png",
    "viewimage.php?modulepart=medias&file=%2e%2e/%2e%2e/etc/passwd",
    "/..%2fabout.php",
    "..\\about.php",
    "/\\evil.example.org/a.php",
    "//evil.example.org/a.php",
    "//evil.example.org/medias/image/exemplesite/a.png",
    "javascript:alert(1)",
    "jav\tascript:alert(1)",
    "JaVaScRiPt:alert(1)//__LOGO_",
    "data:text/html,<b>x</b>",
    "data:image/png;base64,AAAA",
    "about.php?x=1'onload='y",
    "about.php?x=<b>",
    'about.php#a"b',
    "about.php?x=\\1",
)


def cleaner_class(value):
    """What the cleaner decides for an href value."""
    return url_allowed(value, "href", False)


class UrlsCases:
    def test_media_forms(self):
        want = "image/exemplesite/a b.png"
        for url in (
            "/medias/image/exemplesite/a%20b.png",
            "medias/image/exemplesite/a b.png",
            "image/exemplesite/a b.png",
            "/image/exemplesite/a b.png",
            "viewimage.php?modulepart=medias&file=image/exemplesite/a%20b.png",
            "/viewimage.php?modulepart=medias&amp;file=image/exemplesite/a b.png",  # noqa: E501
            "document.php?modulepart=medias&file=image/exemplesite/a b.png",
            "wrapper.php?modulepart=medias&file=image/exemplesite/a b.png",
        ):
            self.assertEqual(media_relpath(url, KEY), want, url)
        self.assertEqual(
            media_relpath("medias/js/exemplesite/app.js", KEY),
            "js/exemplesite/app.js",
        )
        for url in (
            "https://www.example.org/medias/image/exemplesite/a.png",
            "viewimage.php?modulepart=mycompany&file=logo.png",
            "/medias/image/other/a.png",
            "medias/image/exemplesite/../x.png",
        ):
            self.assertIsNone(media_relpath(url, KEY), url)

    def test_page_forms(self):
        cases = {
            "about.php": "dolibarr-page:about",
            "/Equipe.php#team": "dolibarr-page:Equipe#team",
            "news-1.php?x=1": "dolibarr-page:news-1?x=1",
            "/": "dolibarr-page:home",
            "/index.php": "dolibarr-page:home",
            "index.php?website=exemplesite&amp;pageref=about": "dolibarr-page:about",  # noqa: E501
            "/fr/about-fr.php": "dolibarr-page:about-fr",
        }
        for url, token in cases.items():
            self.assertEqual(page_link(url, "home"), token, url)
        for url in (
            "/contactus",
            "https://www.example.org/a.php",
            "#top",
            "mailto:x@example.org",
            "a.html",
        ):
            self.assertIsNone(page_link(url, "home"), url)
        self.assertIsNone(page_link("/", ""))
        self.assertEqual(split_token("dolibarr-page:about#t"), ("about", "#t"))
        self.assertEqual(
            split_token("dolibarr-media:image/k/a.png"), ("image/k/a.png", "")
        )

    def test_logo(self):
        self.assertTrue(
            is_logo(
                "viewimage.php?modulepart=mycompany&file=logos%2Fthumbs%2F__LOGO_SMALL_KEY__"  # noqa: E501
            )
        )
        self.assertTrue(is_logo("/x/__LOGO_KEY__"))
        self.assertFalse(is_logo("/medias/image/k/logo.png"))
        self.assertFalse(is_logo(None))
        # An absolute or scripted value is never laundered into a logo.
        self.assertFalse(is_logo("javascript:alert(1)//__LOGO_"))
        self.assertFalse(is_logo("https://www.example.org/__LOGO_KEY__"))

    def test_rewrite_links(self):
        root = lhtml.fragment_fromstring(
            '<a href="about.php">a</a><img src="image/exemplesite/l.png"'
            ' srcset="image/exemplesite/l.png 1x, /medias/image/exemplesite/'
            'l2.png 2x"><div data-slide-bg="medias/image/exemplesite/s.jpg"'
            " style=\"background:url('medias/image/exemplesite/b.jpg')\">"
            '</div><img src="viewimage.php?modulepart=mycompany&amp;file=x">'
            '<a href="DOLIBARRQ3Q.php">b</a><a href="/contactus">c</a>',
            create_parent="div",
        )
        rewrite_links(root, KEY, "home")
        a, img, div, logo, blog, contact = list(root)
        self.assertEqual(a.get("href"), "dolibarr-page:about")
        self.assertEqual(
            img.get("src"), "dolibarr-media:image/exemplesite/l.png"
        )
        self.assertEqual(
            img.get("srcset"),
            "dolibarr-media:image/exemplesite/l.png 1x,"
            " dolibarr-media:image/exemplesite/l2.png 2x",
        )
        self.assertEqual(
            div.get("data-slide-bg"), "dolibarr-media:image/exemplesite/s.jpg"
        )
        self.assertIn(
            "url('dolibarr-media:image/exemplesite/b.jpg')", div.get("style")
        )
        self.assertEqual(logo.get("src"), "dolibarr-logo:")
        self.assertEqual(blog.get("href"), "DOLIBARRQ3Q.php")
        self.assertEqual(contact.get("href"), "/contactus")

    # -- never widen what the cleaner allowed ---------------------------

    def test_output_is_untouched_or_a_validated_token(self):
        samples = HOSTILE + (
            "about.php",
            "/medias/image/exemplesite/a.png",
            "viewimage.php?modulepart=mycompany&file=logo.png",
            "https://www.example.org/a.php",
            "/",
        )
        for value in samples:
            out = rewrite_url(value, KEY, "home")
            if out is None:
                continue
            if out == LOGO:
                continue
            self.assertTrue(out.startswith((PAGE, MEDIA)), (value, out))
            body, suffix = split_token(out)
            if out.startswith(MEDIA):
                self.assertEqual(suffix, "", (value, out))
                self.assertTrue(body.startswith(("image/", "js/")), out)
                self.assertNotIn("..", body.split("/"), out)
            else:
                self.assertRegex(body, r"^[A-Za-z0-9_-]{1,128}$", out)
            for bad in "'\"\\<> \t\n":
                self.assertNotIn(bad, out, (value, out))
            body_all = out.split(":", 1)[1]
            self.assertFalse(body_all.startswith(("/", "\\")), out)
            self.assertTrue(cleaner_class(body_all), (value, out))
            self.assertFalse(out.startswith(("//", "javascript", "data")))

    def test_hostile_values_stay_untouched(self):
        for value in HOSTILE:
            self.assertIsNone(rewrite_url(value, KEY, "home"), value)
            self.assertIsNone(media_relpath(value, KEY), value)
        root = lhtml.fragment_fromstring(
            "".join(
                '<a href="%s">x</a>'
                % v.replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                for v in HOSTILE
            ),
            create_parent="div",
        )
        before = [a.get("href") for a in root]
        rewrite_links(root, KEY, "home")
        self.assertEqual([a.get("href") for a in root], before)

    def test_untouched_value_keeps_cleaner_verdict(self):
        for value in (
            "https://www.example.org/a.php",
            "mailto:x@example.org",
            "/contactus",
            "#top",
        ):
            self.assertIsNone(rewrite_url(value, KEY, "home"), value)

    def test_marker_tokens_are_never_rewritten(self):
        for value in (
            "DOLIBARRQ3Q.php",
            "/medias/image/exemplesite/DOLIBARRQ12Q.png",
            "about.php?a=DOLIBARRQ1Q",
            "viewimage.php?modulepart=mycompany&file=DOLIBARRQ1Q",
            "/x/__LOGO_DOLIBARRQ1Q__",
        ):
            self.assertIsNone(rewrite_url(value, KEY, "home"), value)
            self.assertIsNone(page_link(value, "home"), value)
            self.assertIsNone(media_relpath(value, KEY), value)
        root = lhtml.fragment_fromstring(
            '<img src="medias/image/exemplesite/DOLIBARRQ2Q.png"'
            ' srcset="image/exemplesite/DOLIBARRQ2Q.png 1x"'
            " style=\"background:url('medias/image/exemplesite/DOLIBARRQ2Q"
            ".png')\">",
            create_parent="div",
        )
        before = dict(root[0].attrib)
        rewrite_links(root, KEY, "home")
        self.assertEqual(dict(root[0].attrib), before)

    def test_home_ref_must_be_a_ref(self):
        self.assertIsNone(page_link("/", "a'b"))
        self.assertIsNone(page_link("/index.php", "../x"))

    def test_page_suffix_alphabet(self):
        self.assertEqual(
            page_link("a.php?x=1&y=%C3%A9#sec-2", "home"),
            "dolibarr-page:a?x=1&y=%C3%A9#sec-2",
        )
        self.assertEqual(
            page_link("a.php#équipe", "home"), "dolibarr-page:a#équipe"
        )
        self.assertIsNone(page_link("a.php?x=1 2", "home"))

    # -- style url() -----------------------------------------------------

    def test_style_rewrite_stays_valid(self):
        for quote in ("'", '"', ""):
            style = "background:url(%smedias/image/exemplesite/b.jpg%s)" % (
                quote,
                quote,
            )
            root = lhtml.fragment_fromstring(
                "<div></div>", create_parent="div"
            )
            root[0].set("style", style)
            rewrite_links(root, KEY, "home")
            out = root[0].get("style")
            self.assertEqual(
                out,
                "background:url('dolibarr-media:image/exemplesite/b.jpg')",
            )
            self.assertNotIn("\\", out)
            self.assertEqual(out.count("'"), 2)
            self.assertNotIn('"', out)
            self.assertTrue(style_allowed(out.replace(MEDIA, "/medias/")), out)

    def test_style_unsafe_left_alone(self):
        for style in (
            "background:url('medias/image/exemplesite/a.png') \\75rl(x)",
            "background:url('medias/image/exemplesite/a\\'.png')",
            "background:url('medias/image/exemplesite/b.jpg",
            "background:url(\"medias/image/exemplesite/b.jpg')",
            "background:url(medias/image/exemplesite/a b.png)",
            "background:url(medias/image/exemplesite/x%29,url(medias/image/"
            "exemplesite/y.png)",
            "background:url(medias/image/exemplesite/a(1).png)",
            "background:url('medias/image/exemplesite/../x.png')",
            "background:url('https://www.example.org/a.png')",
            "background:url('//evil.example.org/a.png')",
            "background:url(javascript:alert(1))",
        ):
            root = lhtml.fragment_fromstring(
                "<div></div>", create_parent="div"
            )
            root[0].set("style", style)
            rewrite_links(root, KEY, "home")
            self.assertEqual(root[0].get("style"), style)

    def test_srcset_commas_and_unchanged(self):
        root = lhtml.fragment_fromstring(
            '<img srcset="image/exemplesite/a,b.png 1x, https://www.example'
            '.org/c.png 2x"><img srcset="https://www.example.org/c.png  2x">',
            create_parent="div",
        )
        rewrite_links(root, KEY, "home")
        self.assertEqual(
            root[0].get("srcset"),
            "dolibarr-media:image/exemplesite/a,b.png 1x,"
            " https://www.example.org/c.png 2x",
        )
        self.assertEqual(
            root[1].get("srcset"), "https://www.example.org/c.png  2x"
        )

    def test_style_unquoted_and_case(self):
        def run(style):
            root = lhtml.fragment_fromstring(
                "<div></div>", create_parent="div"
            )
            root[0].set("style", style)
            rewrite_links(root, KEY, "home")
            return root[0].get("style")

        self.assertEqual(
            run("background:URL(medias/image/exemplesite/a%29b.png)"),
            "background:url('dolibarr-media:image/exemplesite/a)b.png')",
        )
        self.assertEqual(
            run("background:url('medias/image/exemplesite/a(1).png')"),
            "background:url('dolibarr-media:image/exemplesite/a(1).png')",
        )

    def test_logo_strict(self):
        for url in (
            "/medias/image/exemplesite/__LOGO_x.png",
            "a.php?modulepart=mycompany",
            "about.php?x=modulepart=mycompany",
            "viewimage.php?modulepart=mycompany&modulepart=medias",
            "viewimage.php?modulepart=medias&file=__LOGO_A__x",
        ):
            self.assertFalse(is_logo(url), url)
            self.assertNotEqual(rewrite_url(url, KEY, "home"), LOGO, url)
        self.assertTrue(is_logo("viewimage.php?modulepart=mycompany"))

    def test_local_path(self):
        for url in ("/", "/a", "/a/b?c=1#d", "/medias/image/k/a%20b.png"):
            self.assertEqual(local_path(url), url)
        for url in (
            None,
            5,
            "",
            "a",
            "//evil.example",
            "/\\evil.example",
            "/a b",
            "/a\tb",
            "/a\u2028b",
            '/a"b',
            "/a'b",
            "/a<b",
            "/a`b",
            "javascript:alert(1)",
            "https://www.example.org/",
        ):
            self.assertEqual(local_path(url), "", url)

    def test_language_index_is_home(self):
        for url, token in (
            ("/fr/index.php", "dolibarr-page:home"),
            ("fr/index.php", "dolibarr-page:home"),
            ("/fr/index.php#top", "dolibarr-page:home#top"),
            ("/fr_CA/index.php?x=1", "dolibarr-page:home"),
            ("/fr/index.php?pageref=about", "dolibarr-page:about"),
        ):
            self.assertEqual(page_link(url, "home"), token, url)
        self.assertIsNone(page_link("/fr/index.php", ""))
        self.assertIsNone(page_link("/fr/index.php?pageref=../x", "home"))

    def test_medias_logo_name_is_a_media(self):
        url = (
            "viewimage.php?modulepart=medias&file=image/exemplesite/__LOGO_A__"
        )
        self.assertFalse(is_logo(url))
        self.assertEqual(
            rewrite_url(url, KEY, "home"),
            MEDIA + "image/exemplesite/__LOGO_A__",
        )

    def test_srcset_with_blank_in_url_is_untouched(self):
        for srcset in (
            "image/exemplesite/a b.png 1x",
            "image/exemplesite/a.png 1x, image/exemplesite/c d.png 2x",
            "image/exemplesite/a.png 1x 2x",
        ):
            root = lhtml.fragment_fromstring("<img>", create_parent="div")
            root[0].set("srcset", srcset)
            rewrite_links(root, KEY, "home")
            self.assertEqual(root[0].get("srcset"), srcset)

    def test_repeated_keys_untouched(self):
        for url in (
            "viewimage.php?modulepart=medias&file=image/exemplesite/a.png"
            "&file=image/exemplesite/b.png",
            "viewimage.php?modulepart=medias&modulepart=medias"
            "&file=image/exemplesite/a.png",
            "index.php?pageref=a&pageref=b",
        ):
            self.assertIsNone(rewrite_url(url, KEY, "home"), url)

    def test_invalid_pageref_is_not_home(self):
        for url in (
            "index.php?pageref=../x",
            "/index.php?pageref=",
            "/index.php?pageref=a b",
        ):
            self.assertIsNone(page_link(url, "home"), url)
        self.assertEqual(
            page_link("/index.php?x=1", "home"), "dolibarr-page:home"
        )

    def test_page_link_not_accepted_in_media_attributes(self):
        root = lhtml.fragment_fromstring(
            '<img src="about.php"><video poster="about.php"></video>'
            '<img srcset="image/exemplesite/a.png, about.php 2x">'
            '<img src="/">'
            '<a href="about.php">a</a>',
            create_parent="div",
        )
        rewrite_links(root, KEY, "home")
        self.assertEqual(root[0].get("src"), "about.php")
        self.assertEqual(root[1].get("poster"), "about.php")
        self.assertEqual(
            root[2].get("srcset"),
            "dolibarr-media:image/exemplesite/a.png, about.php 2x",
        )
        self.assertEqual(root[3].get("src"), "/")
        self.assertEqual(root[4].get("href"), "dolibarr-page:about")


class CssCases:
    def test_unwrap_uses_dolibarr_expression(self):
        self.assertEqual(
            unwrap_php("<?php // BEGIN PHP\nx\n// END PHP ?>\n\na{}"), "a{}"
        )
        self.assertEqual(unwrap_php(None), "")

    def test_evaluate(self):
        findings = []
        css = evaluate_css(STYLES, "exemplesite", findings)
        self.assertNotIn("<?php", css)
        self.assertNotIn("ob_get_contents", css)
        self.assertIn("html:has(> body.bodywebsite) { color: #123456; }", css)
        self.assertIn("body.bodywebsite { background: url(/medias/image/", css)
        self.assertIn("content: 'exemplesite'", css)
        self.assertIn("html:has(> body.bodywebsite) { --x: 1; }", css)
        self.assertIn("body.bodywebsite p, body.bodywebsite > div", css)
        self.assertIn("font: serif;", css)
        self.assertIn("h2 { x: ; }", css)
        codes = [f.code for f in findings]
        self.assertEqual(codes.count("php_removed"), 1)
        self.assertEqual(codes.count("css_rescoped"), 4)
        removed = [f for f in findings if f.code == "php_removed"][0]
        self.assertEqual(removed.params["context"], "css")
        self.assertIn("SECRET", removed.params["code"])

    def test_short_echo_tag_and_secret_block(self):
        findings = []
        css = evaluate_css(
            "a { b: <?= $website->ref ?>; c: <?php echo dol_hash('x'); ?>; }",
            KEY,
            findings,
        )
        self.assertEqual(css, "a { b: exemplesite; c: ; }")
        self.assertEqual(findings[0].params["code"], "(secret-bearing block)")

    def test_unsafe_literal_is_dropped_with_a_finding(self):
        for lit in UNSAFE_LITERALS:
            for tpl in (
                "a { b: <?php echo empty($website->maincolor) ? '%s'"
                " : $website->maincolor; ?>; }",
                "a { b: <?php echo getDolGlobalString('X') ?: '%s'; ?>; }",
            ):
                findings = []
                css = evaluate_css(tpl % lit, KEY, findings)
                self.assertEqual(css, "a { b: ; }", lit)
                self.assertEqual(
                    [f.code for f in findings], ["php_removed"], lit
                )

    def test_safe_literals_are_kept(self):
        for lit in ("#123456", "rgb(1, 2, 3)", "12px", "Open Sans, serif"):
            css = evaluate_css(
                "a { b: <?php echo getDolGlobalString('X') ?: '%s'; ?>; }"
                % lit,
                KEY,
                [],
            )
            self.assertEqual(css, "a { b: %s; }" % lit)

    def test_key_is_substituted_only_when_valid(self):
        src = "a::after { content: '<?php echo $website->ref; ?>'; }"
        for bad in ("x'};body{}", "../x", "a b", "", "a" * 65, "x;y"):
            findings = []
            css = evaluate_css(src, bad, findings)
            self.assertEqual(css, "a::after { content: ''; }", bad)
            self.assertEqual([f.code for f in findings], ["php_removed"])
        self.assertIn("'my.site-1'", evaluate_css(src, "my.site-1", []))

    def test_rescope_leaves_other_selectors(self):
        findings = []
        css = rescope(
            "a{color:red}/* body { } */.htmlx{}body.bodywebsite{}"
            "@font-face{font-family:x}@keyframes k{from{a:b}}"
            "div{content:'body {'}",
            findings,
        )
        self.assertEqual(
            css,
            "a{color:red}/* body { } */.htmlx{}body.bodywebsite{}"
            "@font-face{font-family:x}@keyframes k{from{a:b}}"
            "div{content:'body {'}",
        )
        self.assertEqual(findings, [])

    def test_rescope_comments_and_strings(self):
        findings = []
        self.assertEqual(
            rescope("/* { */ body { a: b } /* } */ html { c: d }", findings),
            "/* { */ body.bodywebsite { a: b } /* } */ "
            "html:has(> body.bodywebsite) { c: d }",
        )
        self.assertEqual(len(findings), 2)
        self.assertEqual(
            rescope("a, /* x */ body /* y */ { a: b }", []),
            "a, /* x */ body.bodywebsite /* y */ { a: b }",
        )
        same = (
            "a[title='{ body, html }']{a:b}"
            'a::after{content:"} body {"}'
            "a{content:'it\\'s } body {'}"
        )
        self.assertEqual(rescope(same, []), same)
        self.assertEqual(
            rescope("[data-x='a,b'], body{a:b}", []),
            "[data-x='a,b'], body.bodywebsite{a:b}",
        )

    def test_rescope_at_rules(self):
        self.assertEqual(
            rescope(
                "@media print { body { a: b } @supports (a: b) { html { c: d"
                " } } } @layer x { :root { e: f } }",
                [],
            ),
            "@media print { body.bodywebsite { a: b } @supports (a: b) "
            "{ html:has(> body.bodywebsite) { c: d } } } "
            "@layer x { html:has(> body.bodywebsite) { e: f } }",
        )
        keep = "@keyframes body { body { a: b } } @font-face { a: b }"
        self.assertEqual(rescope(keep, []), keep)
        nested = "div { body { a: b } }"
        self.assertEqual(rescope(nested, []), nested)

    def test_rescope_selector_lists(self):
        findings = []
        self.assertEqual(
            rescope("body, .x, html, :root { a: b }", findings),
            "body.bodywebsite, .x, html:has(> body.bodywebsite), "
            "html:has(> body.bodywebsite) { a: b }",
        )
        self.assertEqual(len(findings), 3)
        self.assertEqual(
            rescope("html body { a: b } html > body .x { a: b }", []),
            "body.bodywebsite { a: b } body.bodywebsite .x { a: b }",
        )
        already = "html body.bodywebsite, htmlbody, bodyx, .body { a: b }"
        self.assertEqual(rescope(already, []), already)
        self.assertEqual(
            rescope("body.dark:not(.x) > a, html.dark { a: b }", []),
            "body.bodywebsite.dark:not(.x) > a, "
            "html:has(> body.bodywebsite).dark { a: b }",
        )

    def test_rescope_root_inside_functional_pseudo_class(self):
        same = ":is(:root, .x) a, :not(:root) b, :where(html, body) c { a: b }"
        findings = []
        self.assertEqual(rescope(same, findings), same)
        self.assertEqual(findings, [])

    def test_rescope_survives_malformed_input(self):
        for css in (
            "body { a: b",
            "body {",
            "} } body { a: b }",
            "body { a: 'x",
            "body /* never closed { }",
            "a { b: c } }}}",
            "\\",
            "body\\{",
            ")))) body ,,, { a: b }",
            "",
            "{",
            "@",
            "@media",
        ):
            out = rescope(css, [])
            self.assertIsInstance(out, str, css)
        self.assertEqual(rescope("body { a: b", []), "body.bodywebsite { a: b")
        self.assertEqual(
            rescope("} } body { a: b }", []), "} } body.bodywebsite { a: b }"
        )
        self.assertEqual(rescope("a { b: c", []), "a { b: c")

    def test_large_adversarial_inputs_are_fast(self):
        n = 100000
        cases = (
            "{" * n,
            "}" * n,
            "/*" * n,
            "body{" * n,
            "body{}" * n,
            "@media x{" * n,
            "'" * n,
            "\\" * n,
            "(" * n + "body{}",
            "a," * n + "{}",
            "<?php " * n,
            "<?php // BEGIN PHP " * n,
            "url( " * n,
            "<?php echo " + "'" * n,
        )
        for css in cases:
            start = time.perf_counter()
            findings = []
            out = evaluate_css(css, KEY, findings)
            self.assertIsInstance(out, str)
            self.assertIsInstance(is_empty_js(css), bool)
            self.assertLess(time.perf_counter() - start, 5, css[:12])
            self.assertLessEqual(len(findings), 1000, css[:12])

    def test_many_removed_blocks_are_fast_and_reported_within_a_cap(self):
        start = time.perf_counter()
        findings = []
        out = evaluate_css("<?php x ?>" * 100000, KEY, findings)
        self.assertLess(time.perf_counter() - start, 2)
        self.assertEqual(out, "")
        self.assertEqual(len(findings), 200)
        start = time.perf_counter()
        evaluate_css("<?php x ?>\n" * 100000, KEY, [])
        self.assertLess(time.perf_counter() - start, 2)

    def test_removed_block_line_is_in_the_original_file(self):
        findings = []
        evaluate_css(
            "<?php // BEGIN PHP\n$a = 1;\n\n// END PHP ?>\n\n"
            "a { b: 1 }\nc { d: <?php echo $x; ?> }\n",
            KEY,
            findings,
        )
        self.assertEqual(findings[0].params["line"], "7")
        findings = []
        evaluate_css("a\n<?php x ?>\n<?php y ?>", KEY, findings)
        self.assertEqual([f.params["line"] for f in findings], ["2", "3"])

    def test_media_url_with_traversal_is_not_rewritten_to_a_path(self):
        for src in (
            "url(medias/../../x)",
            "url('medias/../x')",
            'url("medias/a/../x")',
            "url(medias/a\\2e x)",
            "url(medias/%2e%2e/x)",
        ):
            out = evaluate_css("a { b: %s }" % src, KEY, [])
            self.assertNotIn("medias", out, src)
            self.assertNotIn("..", out, src)
        self.assertEqual(
            evaluate_css("a { b: url( 'medias/a b.png' ) }", KEY, []),
            "a { b: url('/medias/a b.png') }",
        )
        self.assertEqual(
            evaluate_css("a { b: url(./medias/x.png) }", KEY, []),
            "a { b: url(/medias/x.png) }",
        )

    def test_protocol_relative_literal_is_refused(self):
        findings = []
        css = evaluate_css(
            "a { b: <?php echo getDolGlobalString('X') ?:"
            " 'url(//evil.example/a.png)'; ?> }",
            KEY,
            findings,
        )
        self.assertEqual(css, "a { b:  }")
        self.assertEqual([f.code for f in findings], ["php_removed"])

    def test_empty_js(self):
        self.assertTrue(is_empty_js("\n/* none */\n// x\n  "))
        self.assertFalse(is_empty_js("// x\nvar a = 1;"))
        self.assertTrue(is_empty_js("/* never closed"))
        self.assertTrue(is_empty_js(None))


class TestUrls(UrlsCases, unittest.TestCase):
    pass


class TestCss(CssCases, unittest.TestCase):
    pass
