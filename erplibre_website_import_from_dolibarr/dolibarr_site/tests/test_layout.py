# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time
import unittest

from ..layout import MAX_LABEL, MAX_MENU_ITEMS, detect_layout, extract_menu
from ..model import Page

NAV = (
    '<nav><a href="dolibarr-page:home">Logo</a></nav>'
    '<ul class="menu">'
    '<li><a href="dolibarr-page:home"><dolibarr-q id="1"></dolibarr-q></a></li>'  # noqa: E501
    '<li><a href="dolibarr-page:about">About</a><ul>'
    '<li><a href="dolibarr-page:Equipe">Team</a><ul>'
    '<li><a href="dolibarr-page:deep">Deep</a></li></ul></li></ul></li>'
    '<li><a href="/contactus">Contact</a></li>'
    '<li><a href="https://www.example.org/" target="_blank">  Out\n</a></li>'
    "</ul>"
)


def page(ref, includes=(), edges=("", ""), status="import"):
    return Page(
        ref=ref,
        includes=list(includes),
        edge_includes=list(edges),
        analysis_status=status,
    )


def menu_of(html, nodes=None):
    return extract_menu(Page(ref="h", body_html=html, qweb_nodes=nodes or {}))


class LayoutCases:
    def test_detect_layout_by_usage(self):
        pages = [
            page("home", ["header", "footer"], ("header", "footer")),
            page("about", ["header", "footer", "cta"], ("header", "footer")),
            page("blog", ["header", "cta"], ("header", "cta")),
            page("x", ["cta"], ("", "")),
            page("tr", ["header"], ("header", ""), status="translation"),
            page("plain"),
        ]
        self.assertEqual(
            detect_layout(pages), {"header": "header", "footer": "footer"}
        )

    def test_detect_layout_needs_half(self):
        pages = [
            page("a", ["menu"], ("menu", "")),
            page("b", ["x"], ("", "")),
            page("c", ["x"], ("", "")),
        ]
        self.assertEqual(detect_layout(pages), {})

    def test_extract_menu(self):
        header = Page(
            ref="header",
            body_html=NAV,
            qweb_nodes={"1": {"kind": "text", "value": "<b>Home</b>"}},
        )
        items, findings = extract_menu(header)
        self.assertEqual(
            [(i.label, i.target) for i in items],
            [
                ("Home", "dolibarr-page:home"),
                ("About", "dolibarr-page:about"),
                ("Contact", "/contactus"),
                ("Out", "https://www.example.org/"),
            ],
        )
        self.assertTrue(items[3].new_window)
        self.assertEqual(
            [(c.label, c.target) for c in items[1].children],
            [("Team", "dolibarr-page:Equipe"), ("Deep", "dolibarr-page:deep")],
        )
        self.assertEqual([f.code for f in findings], ["menu_flattened"])

    def test_no_menu(self):
        self.assertEqual(
            extract_menu(Page(ref="h", body_html="<p>x</p>")), ([], [])
        )  # noqa: E501

    def test_labels_are_plain_text(self):
        html = (
            "<ul>"
            '<li><a href="dolibarr-page:a">&lt;img src=x&gt;Home</a></li>'
            '<li><a href="dolibarr-page:b">{{7*7}}</a></li>'
            '<li><a href="dolibarr-page:c"><b>Bo</b>\x01ld\u202e  x\n y</a></li>'  # noqa: E501
            '<li><a href="dolibarr-page:d">&amp;lt;b&amp;gt;</a></li>'
            '<li><a href="dolibarr-page:e"><dolibarr-q id="1"></dolibarr-q></a></li>'  # noqa: E501
            '<li><a href="dolibarr-page:f">%s</a></li>'
            "</ul>" % ("z" * 1000)
        )
        nodes = {
            "1": {
                "kind": "text",
                "value": "<img src=x onerror=1>Home &amp; <script>1</script>",
            }
        }
        items, _ = menu_of(html, nodes)
        labels = [i.label for i in items]
        self.assertEqual(labels[0], "<img src=x>Home")
        self.assertEqual(labels[1], "{{7*7}}")
        self.assertEqual(labels[2], "Bold x y")
        self.assertEqual(labels[3], "&lt;b&gt;")  # decoded once
        self.assertEqual(labels[4], "Home &")
        self.assertEqual(labels[5], "z" * MAX_LABEL)

    def test_label_of_bad_marker_value(self):
        html = '<ul><li><a href="dolibarr-page:a"><dolibarr-q id="1"></dolibarr-q>T</a></li></ul>'  # noqa: E501
        for value in (None, 5, "", ["x"]):
            items, _ = menu_of(html, {"1": {"kind": "text", "value": value}})
            self.assertEqual(items[0].label, "T")

    def test_unsafe_targets_are_left_out(self):
        bad = [
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "data:text/html,x",
            "",
            "#",
            "#top",
            "dolibarr-page:",
            "dolibarr-page:a b",
            "dolibarr-page:../x",
            "dolibarr-media:image/k/a.png",
            "//evil.example.org/",
            "ftp://x.example.org/",
            "http:///nohost",
            "https://x.example.org/a b",
        ]
        html = (
            '<ul>%s<li><a href="dolibarr-page:ok">Ok</a></li></ul>'
            % "".join(
                '<li><a href="%s">L</a></li>' % b.replace('"', "&quot;")
                for b in bad
            )
        )
        items, _ = menu_of(html)
        self.assertEqual([i.target for i in items], ["dolibarr-page:ok"])

    def test_userinfo_ports_and_format_characters_are_refused(self):
        bad = [
            "https://a@x.example.org/",
            "https://a:b@x.example.org/",
            "https://x.example.org:99999/",
            "https://x.example.org:port/",
            "/a\u200bb",
            "/a\u202eb",
            "/a\u0085b",
            "dolibarr-page:a\u200b",
            "https://x.example.org/\u2066",
        ]
        html = (
            '<ul>%s<li><a href="https://x.example.org:8443/">Ok</a></li></ul>'
            % "".join('<li><a href="%s">L</a></li>' % b for b in bad)
        )
        items, _ = menu_of(html)
        self.assertEqual(
            [i.target for i in items], ["https://x.example.org:8443/"]
        )

    def test_four_levels_flatten_once(self):
        html = (
            '<ul><li><a href="dolibarr-page:a">A</a><ul>'
            '<li><a href="dolibarr-page:b">B</a><ul>'
            '<li><a href="dolibarr-page:c">C</a><ul>'
            '<li><a href="dolibarr-page:d">D</a></li>'
            "</ul></li></ul></li></ul></li></ul>"
        )
        items, findings = menu_of(html)
        self.assertEqual([i.label for i in items], ["A"])
        self.assertEqual([c.label for c in items[0].children], ["B", "C", "D"])
        self.assertEqual(
            sorted(f.params["label"] for f in findings), ["C", "D"]
        )

    def test_suffix_kept_when_plain_and_dropped_when_odd(self):
        html = (
            "<ul>"
            '<li><a href="dolibarr-page:a?x=1#f">A</a></li>'
            '<li><a href="dolibarr-page:b#a&quot;&gt;">B</a></li>'
            "</ul>"
        )
        items, _ = menu_of(html)
        self.assertEqual(
            [i.target for i in items],
            ["dolibarr-page:a?x=1#f", "dolibarr-page:b"],
        )

    def test_dropped_parent_promotes_children(self):
        html = (
            '<ul><li><a href="javascript:x">P</a><ul>'
            '<li><a href="dolibarr-page:k">Kid</a></li></ul></li></ul>'
        )
        items, _ = menu_of(html)
        self.assertEqual([i.label for i in items], ["Kid"])

    def test_nav_without_list_and_hostile_nesting_of_nav(self):
        items, _ = menu_of(
            '<nav><a href="dolibarr-page:a">A</a>'
            '<a href="javascript:x">J</a></nav>'
        )
        self.assertEqual([i.label for i in items], ["A"])
        html = (
            '<nav><ul><li><nav><a href="dolibarr-page:a">A</a></nav>'
            '</li><li><a href="dolibarr-page:b">B</a></li></ul></nav>'
        )
        items, _ = menu_of(html)
        self.assertTrue(all(i.target.startswith("dolibarr") for i in items))

    def test_deep_nesting_gives_a_finding_not_an_exception(self):
        for depth in (300, 5000, 100000):
            html = "<ul><li>" * depth + '<a href="dolibarr-page:a">A</a>'
            items, findings = menu_of(html)
            self.assertIsInstance(items, list)
            codes = {f.code for f in findings}
            self.assertLessEqual(codes, {"page_error", "menu_flattened"})
        html = "<div>" * 100000 + '<a href="dolibarr-page:a">A</a>'
        menu_of(html)
        menu_of("<nav>" * 50000 + '<a href="dolibarr-page:a">A</a>')

    def test_many_links_are_capped_in_linear_time(self):
        link = '<li><a href="dolibarr-page:p">L</a></li>'
        start = time.monotonic()
        items, findings = menu_of("<ul>%s</ul>" % (link * 10000))
        self.assertEqual(len(items), MAX_MENU_ITEMS)
        self.assertEqual([f.code for f in findings], ["menu_capped"])
        nested = "<ul><li>" * 200 + link * 5000 + "</li></ul>" * 200
        menu_of(nested)
        nested = "<nav>" * 100 + link * 5000
        menu_of(nested)
        self.assertLess(time.monotonic() - start, 10)

    def test_nested_containers_stay_linear(self):
        a = '<a href="dolibarr-page:p">L</a>'
        html = ("<nav><ul><li>" + a) * 120 + "</li></ul></nav>" * 120
        start = time.monotonic()
        menu_of(html * 40)
        self.assertLess(time.monotonic() - start, 5)

    def test_marker_text_is_never_html(self):
        html = '<ul><li><a href="dolibarr-page:a"><dolibarr-q id="1"></dolibarr-q></a></li></ul>'  # noqa: E501
        items, _ = menu_of(
            html, {"1": {"kind": "text", "value": "&lt;script&gt;x"}}
        )
        self.assertEqual(items[0].label, "<script>x")


class TestLayout(LayoutCases, unittest.TestCase):
    pass
