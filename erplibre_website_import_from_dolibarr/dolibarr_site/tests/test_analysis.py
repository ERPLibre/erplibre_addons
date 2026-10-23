# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from .. import __main__ as cli
from .. import html2arch
from ..html2arch import DictResolver, page_arch
from ..messages import finding
from ..model import Options, PageChoice, SourceError
from ..pipeline import all_findings, analyse, apply_choices, build_from_zip
from .fixtures import FILENAME, demo_zip_bytes

HOME_MAP = (
    '<iframe src=\\"https://maps.example.org/embed?q=<?php echo'
    ' urlencode($mysoc->getFullAddress()); ?>\\"></iframe>'
)


def build(opts=None, **kw):
    return build_from_zip(
        demo_zip_bytes(**kw), opts or Options(filename=FILENAME)
    )


def codes_of(site, ref=None):
    return [
        f.code for f in all_findings(site) if ref is None or f.page_ref == ref
    ]


class BuildCases:
    @classmethod
    def site(cls):
        if not hasattr(cls, "_site"):
            cls._site = build()
        return cls._site

    def test_classification(self):
        site = self.site()
        status = {p.ref: (p.analysis_status, p.kind) for p in site.pages}
        self.assertEqual(site.home_ref, "home")
        self.assertEqual(status["home"], ("import", "page"))
        self.assertEqual(status["about"], ("import", "page"))
        self.assertEqual(status["Equipe"], ("import", "page"))
        self.assertEqual(status["blog"], ("import", "page"))
        self.assertEqual(status["news-1"], ("import", "post"))
        self.assertEqual(status["news-2"], ("import", "post"))
        self.assertEqual(status["header"][0], "container")
        self.assertEqual(status["footer"][0], "container")
        self.assertEqual(status["cta"][0], "container")
        self.assertEqual(status["about-fr"][0], "translation")
        self.assertEqual(status["standalone-fr"][0], "foreign_unlinked")
        self.assertEqual(status["_lib"][0], "skipped")
        self.assertEqual(status["config"][0], "skipped")
        self.assertEqual(site.page("about-fr").translates_ref, "about")
        self.assertEqual(
            site.containers,
            {"header": "header", "footer": "footer", "cta": "content"},
        )
        translation = [
            f for f in all_findings(site) if f.code == "skipped_translation"
        ][0]
        self.assertEqual(
            (translation.lang, translation.url), ("fr", "/fr/about-fr.php")
        )
        self.assertEqual(codes_of(site, "_lib"), ["skipped_container_type"])

    def test_php_pass(self):
        site = self.site()
        home = site.page("home")
        self.assertEqual(home.php_plan, "translated")
        kinds = sorted({n["kind"] for n in home.qweb_nodes.values()})
        self.assertEqual(
            kinds,
            [
                "address",
                "blog_field",
                "blog_loop",
                "company",
                "include",
                "map",
                "social",
                "text",
            ],
        )
        self.assertIn(
            "dolibarr-media:image/exemplesite/logo.png", home.body_html
        )
        self.assertIn("<dolibarr-loop", home.body_html)
        legacy = site.page("legacy")
        self.assertEqual(legacy.php_plan, "remove")
        self.assertGreater(legacy.php_removed_bytes, 0)
        self.assertNotIn("REMOVED-MARKER", legacy.body_html)
        self.assertIn("kept after unbalanced", legacy.body_html)
        self.assertIn("after orphan", legacy.body_html)
        legacy_codes = codes_of(site, "legacy")
        for code in ("php_removed", "php_unbalanced", "php_unpaired"):
            self.assertIn(code, legacy_codes)
        contact = site.page("contact")
        self.assertTrue(contact.has_contact_handler)
        self.assertEqual(contact.php_plan, "translated")
        self.assertNotIn("Sent", contact.body_html)
        unsafe = site.page("unsafe")
        self.assertGreater(unsafe.script_count, 0)
        self.assertIn("inline scripts: 1", unsafe.script_detail)
        self.assertNotIn("verification", unsafe.head_html)
        for code in (
            "unsafe_markup_removed",
            "form_removed",
            "head_asset_dropped",
        ):
            self.assertIn(code, codes_of(site, "unsafe"))
        self.assertIn("literal_placeholder", codes_of(site, "about"))
        self.assertIn("author_alias_ignored", codes_of(site, "news-1"))

    def test_site_assets_menu_and_covers(self):
        site = self.site()
        self.assertIn("html:has(> body.bodywebsite)", site.site_css)
        self.assertIn("color: #336699", site.site_css)
        self.assertIn("url(/medias/image/exemplesite/logo.png)", site.site_css)
        self.assertEqual(site.site_js, "")
        self.assertIn("fonts.googleapis.com", site.head_assets)
        self.assertNotIn("jquery", site.head_assets)
        self.assertEqual(
            [(i.label, i.target) for i in site.menu],
            [
                ("Home", "dolibarr-page:home"),
                ("About", "dolibarr-page:about"),
                ("Team", "dolibarr-page:Equipe"),
                ("Blog page", "dolibarr-page:blog"),
                ("Contact", "/contactus"),
            ],
        )
        self.assertEqual(
            site.page("news-1").image_relpath, "image/exemplesite/cover.webp"
        )
        self.assertIn("media_matched_by_name", codes_of(site, "news-1"))
        self.assertEqual(
            site.page("news-2").image_relpath, "image/exemplesite/logo.png"
        )
        self.assertIn("layout_detected", codes_of(site))
        self.assertIn("media_name_refused", codes_of(site))
        self.assertEqual(site.langs_source.split(" ")[0], "bundled")

    def test_no_home_row_leaves_home_ref_empty(self):
        site = build(
            sql_edit=lambda sql: "\n".join(
                line
                for line in sql.split("\n")
                if "fk_default_home" not in line
            )
        )
        self.assertEqual(site.home_ref, "")
        self.assertEqual(site.page("home").analysis_status, "import")

    def test_page_error_skips_one_page(self):
        deep = "<div>" * 300 + "x" + "</div>" * 300
        site = build(
            sql_edit=lambda sql: sql.replace(
                "<section><h2>Blog page</h2></section>", deep
            )
        )
        self.assertEqual(site.page("blog").analysis_status, "skipped")
        self.assertIn("page_error", codes_of(site, "blog"))
        self.assertEqual(site.page("about").analysis_status, "import")

    def test_garbage_is_source_error(self):
        with self.assertRaises(SourceError):
            build_from_zip(b"PK not really", Options(filename=FILENAME))

    def test_clean_runs_before_link_rewriting(self):
        site = self.site()
        header = site.page("header").body_html
        self.assertIn('href="dolibarr-page:home"', header)
        self.assertIn('href="dolibarr-page:Equipe"', header)
        self.assertIn('href="/contactus"', header)
        self.assertIn("<script>", site.page("unsafe").body_html)

    def test_map_iframe_with_marker_src_survives_cleaning(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                HOME_MAP,
                '<iframe src=\\"<?php echo'
                ' urlencode($mysoc->getFullAddress()); ?>\\"></iframe>',
            )
        )
        home = site.page("home")
        self.assertRegex(home.body_html, r'<iframe src="DOLIBARRQ\d+Q">')
        self.assertIn("map", {n["kind"] for n in home.qweb_nodes.values()})
        arch = page_arch(
            home,
            site,
            DictResolver(blog_id=1, website_id=1),
            {},
            Options(),
            [],
        )
        self.assertIn("google_map_link(13)", arch)

    def test_hand_spelled_marker_cannot_keep_an_iframe(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                "<p>We make examples.</p>",
                "<p>We make examples.</p>"
                '<iframe src=\\"DOLIBARRQ1Q\\"></iframe>'
                '<iframe src=\\"DOLIBARR&#81;1Q\\"></iframe>',
            )
        )
        about = site.page("about")
        self.assertNotIn("<iframe", about.body_html)
        self.assertNotIn("DOLIBARRQ1Q", about.body_html)
        removed = [
            f for f in about.findings if f.code == "unsafe_markup_removed"
        ]
        self.assertIn("non-https iframe", removed[0].params["what"])

    def test_removed_php_is_accounted(self):
        site = self.site()
        for page in site.pages:
            if page.analysis_status == "skipped":
                continue
            removed = [f for f in page.findings if f.code == "php_removed"]
            self.assertEqual(
                sum(int(f.params["bytes"]) for f in removed),
                page.php_removed_bytes,
                page.ref,
            )
            for item in removed:
                self.assertTrue(item.params["line"].isdigit())
                self.assertTrue(item.params["code"])
        contact = site.page("contact")
        dropped = [
            f
            for f in contact.findings
            if f.code == "php_removed"
            and f.params["code"].startswith("if (GETPOST('action')")
        ]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].params["line"], "2")
        sent = len('<p class="sent">Sent</p><p class="failed">Failed</p>')
        self.assertEqual(int(dropped[0].params["bytes"]), sent)
        self.assertEqual(contact.php_removed_bytes, sent)
        self.assertEqual(contact.php_unknown_blocks, 0)
        legacy = site.page("legacy")
        self.assertGreater(legacy.php_unknown_blocks, 0)
        self.assertGreater(
            len([f for f in legacy.findings if f.code == "php_removed"]), 3
        )

    def test_oversized_text_is_refused_before_parsing(self):
        # Two-byte characters: the limit counts UTF-8 bytes, not characters.
        big = "\u00e9" * (html2arch.MAX_TEXT // 2)
        site = build(
            opts=Options(
                filename=FILENAME,
                zip_limits={
                    "max_ratio": 100000,
                    "max_sql": 64 * 2**20,
                    "max_container": 64 * 2**20,
                },
            ),
            extra={
                "containers/htmlheader.html": (
                    "<style>%s</style>" % big
                ).encode("utf-8")
            },
            sql_edit=lambda sql: sql.replace(
                "<section><h2>Blog page</h2></section>",
                "<p>%s</p><p>TAIL</p>" % big,
            ).replace(
                '<meta name=\\"google-site-verification\\"',
                "<style>%s</style><meta" % big,
            ),
        )
        for ref in ("blog", "unsafe"):
            page = site.page(ref)
            self.assertEqual(page.analysis_status, "skipped", ref)
            self.assertEqual(page.body_html, "", ref)
            self.assertIn("page_error", codes_of(site, ref))
        self.assertEqual(site.page("about").analysis_status, "import")
        self.assertEqual(site.head_assets, "")
        self.assertIn("page_error", codes_of(site, "htmlheader.html"))

    def test_edge_includes(self):
        site = self.site()
        self.assertEqual(site.page("home").edge_includes, ["header", "footer"])
        self.assertEqual(
            site.page("about").edge_includes, ["header", "footer"]
        )
        self.assertEqual(site.page("cta").edge_includes, ["", ""])
        self.assertEqual(site.page("news-1").edge_includes, ["", ""])
        self.assertEqual(site.page("header").edge_includes, ["", ""])

    def test_unexpected_errors_are_not_swallowed(self):
        with mock.patch.object(
            html2arch, "clean_fragment", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                build()

    def test_duplicate_refs_keep_the_first_row(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                "__WEBSITE_ID__, 'Equipe', ", "__WEBSITE_ID__, 'about', "
            )
        )
        self.assertEqual([p.ref for p in site.pages].count("about"), 1)
        self.assertIn("We make examples.", site.page("about").body_html)
        self.assertNotIn("Team", site.page("about").body_html)
        self.assertNotIn("page_error", codes_of(site, "about"))
        errors = [f for f in all_findings(site) if f.code == "page_error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("duplicate ref", errors[0].params["reason"])
        self.assertIn("row 5", errors[0].params["reason"])

    def test_slug_collisions_keep_the_first_row(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                "__WEBSITE_ID__, 'Equipe', ", "__WEBSITE_ID__, 'a b', "
            ).replace("__WEBSITE_ID__, 'contact', ", "__WEBSITE_ID__, 'a-b', ")
        )
        self.assertEqual([p.ref for p in site.pages].count("a-b"), 1)
        kept = site.page("a-b")
        self.assertEqual(kept.title, "Our team")
        self.assertIn('class="team"', kept.body_html)
        self.assertNotIn("<form", kept.body_html)
        self.assertIn("ref_slugified", codes_of(site, "a-b"))
        self.assertIn(
            "duplicate ref",
            " ".join(
                f.params["reason"]
                for f in all_findings(site)
                if f.code == "page_error"
            ),
        )

    def test_slugified_duplicate_leaves_no_slug_finding(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                "__WEBSITE_ID__, 'Equipe', ", "__WEBSITE_ID__, 'a-b', "
            ).replace("__WEBSITE_ID__, 'contact', ", "__WEBSITE_ID__, 'a b', ")
        )
        self.assertEqual(site.page("a-b").title, "Our team")
        self.assertNotIn("ref_slugified", codes_of(site))
        self.assertNotIn("page_error", codes_of(site, "a-b"))

    def test_duplicate_rowid_keeps_the_first_row(self):
        def add_rows(sql):
            cta = next(
                line
                for line in sql.split("\n")
                if line.startswith("INSERT") and "'cta', " in line
            )
            rows = [
                cta.replace("16__+MAX", "%d__+MAX" % rowid).replace(
                    "'cta', ", "'%s', " % ref
                )
                for rowid, ref in ((3, "r1"), (4, "r2"))
            ]
            return sql + "\n" + "\n".join(rows) + "\n"

        site = build(sql_edit=add_rows)
        self.assertEqual(site.home_ref, "home")
        self.assertEqual(site.page("about-fr").translates_ref, "about")
        self.assertIsNone(site.page("r1"))
        self.assertIsNone(site.page("r2"))
        reasons = [
            f.params["reason"]
            for f in all_findings(site)
            if f.code == "page_error"
        ]
        self.assertEqual(len(reasons), 2)
        for reason, rowid in zip(reasons, (3, 4)):
            self.assertIn("duplicate rowid", reason)
            self.assertIn("row %d" % rowid, reason)

    def test_invalid_row_before_a_kept_ref_is_site_level(self):
        def add_row(sql):
            lines = sql.split("\n")
            at = next(
                i
                for i, line in enumerate(lines)
                if line.startswith("INSERT") and "'cta', " in line
            )
            bad = (
                lines[at]
                .replace("16__+MAX", "31__+MAX")
                .replace(
                    "'Call to action', '', ''", "'Call to action', '', 'x!'"
                )
            )
            fk = (
                lines[at]
                .replace("16__+MAX", "32__+MAX")
                .replace(
                    "__+MAX_llx_website_page__, null,",
                    "__+MAX_llx_website_page__, 'q',",
                )
            )
            return "\n".join(lines[:at] + [bad, fk] + lines[at:])

        site = build(sql_edit=add_row)
        self.assertEqual(site.page("cta").source_id, 16)
        errors = [f for f in all_findings(site) if f.code == "page_error"]
        self.assertEqual(len(errors), 2)
        for error, rowid in zip(errors, (31, 32)):
            self.assertEqual(error.page_ref, "")
            self.assertEqual(error.params["ref"], "cta")
            self.assertIn("row %d" % rowid, error.params["reason"])
        self.assertNotIn("page_error", codes_of(site, "cta"))

    def test_invalid_row_numbers_skip_the_row(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                "VALUES(5__+MAX_llx_website_page__,", "VALUES('abc',"
            )
            .replace("VALUES(6__+MAX_llx_website_page__,", "VALUES(1.5,")
            .replace(
                "4__+MAX_llx_website_page__, __WEBSITE_ID__, 'about-fr'",
                "'zz', __WEBSITE_ID__, 'about-fr'",
            )
        )
        for ref in ("Equipe", "contact", "about-fr"):
            self.assertIsNone(site.page(ref), ref)
            self.assertIn("page_error", codes_of(site, ref))
        self.assertEqual(site.page("about").analysis_status, "import")

    def test_dump_without_pages_is_not_a_dolibarr_site(self):
        for sql in ("", "garbage", "SELECT 1;", "-- File generated --;"):
            with self.assertRaises(SourceError, msg=sql):
                build(sql_edit=lambda _sql, sql=sql: sql)

    def test_page_error_resets_the_page_state(self):
        deep = "<div>" * 300 + "<?php foo(); ?>x" + "</div>" * 300
        site = build(
            sql_edit=lambda sql: sql.replace(
                "<section><h2>Blog page</h2></section>", deep
            )
        )
        blog = site.page("blog")
        self.assertEqual(blog.analysis_status, "skipped")
        self.assertEqual([f.code for f in blog.findings], ["page_error"])
        self.assertEqual(
            (
                blog.php_plan,
                blog.php_mode,
                blog.php_unknown_blocks,
                blog.php_removed_bytes,
            ),
            ("none", "static", 0, 0),
        )

    def test_head_php_is_reported(self):
        site = build(
            sql_edit=lambda sql: sql.replace(
                '<meta name=\\"google-site-verification\\"',
                '<?php echo $headvar; ?><meta name=\\"x\\"',
            )
        )
        unsafe = site.page("unsafe")
        removed = [f for f in unsafe.findings if f.code == "php_removed"]
        self.assertEqual(
            [f.params["code"] for f in removed], ["echo $headvar"]
        )
        self.assertEqual(unsafe.php_plan, "remove")
        self.assertEqual(unsafe.php_unknown_blocks, 1)
        self.assertNotIn("headvar", unsafe.head_html)


class TestBuild(BuildCases, unittest.TestCase):
    pass


def rows_of(site, opts, imported=frozenset()):
    return {row.ref: row for row in analyse(site, opts, imported)}


def run_inspect(argv):
    """(exit code, stdout, stderr) of the inspect command."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["inspect"] + argv)
    return code, out.getvalue(), err.getvalue()


class AnalyseCases:
    def test_rows_and_defaults(self):
        rows = rows_of(build(), Options())
        fr = rows["standalone-fr"]
        self.assertEqual(
            (fr.status, fr.include, fr.lang), ("foreign_unlinked", False, "fr")
        )
        self.assertEqual(fr.source_url, "/standalone-fr.php")
        tr = rows["about-fr"]
        self.assertEqual((tr.status, tr.include), ("translation", False))
        self.assertEqual(
            (tr.source_url, tr.translates_ref), ("/fr/about-fr.php", "about")
        )
        about = rows["about"]
        self.assertEqual(
            (about.status, about.include, about.target_url),
            ("import", True, "/about"),
        )
        self.assertEqual(rows["footer"].status, "container")
        self.assertEqual(rows["legacy"].php_plan, "remove")
        self.assertGreater(rows["legacy"].php_removed_bytes, 0)
        self.assertEqual(
            (rows["news-1"].kind, rows["news-1"].target_url), ("post", "")
        )
        self.assertEqual(rows["_lib"].status, "skipped")
        self.assertGreater(rows["unsafe"].script_count, 0)

    def test_head_scripts_are_counted(self):
        head = (
            "<script>var a = 1;</script>"
            '<script src=\\"https://cdn.example.net/x.js\\"></script>'
        )
        site = build(
            sql_edit=lambda sql: sql.replace(
                '<meta name=\\"google-site-verification\\"'
                ' content=\\"abc123\\">',
                head,
            ),
            extra={"containers/htmlheader.html": b"<script>var b;</script>"},
        )
        rows = rows_of(site, Options())
        plain = rows_of(build(), Options())["unsafe"]
        unsafe = rows["unsafe"]
        self.assertEqual(unsafe.script_count, plain.script_count + 2)
        self.assertIn("cdn.example.net", unsafe.script_detail)
        self.assertEqual(site.site_script_count, 1)
        self.assertIn("inline scripts: 1", site.site_script_detail)
        hosted = build(
            extra={
                "containers/htmlheader.html": (
                    b'<script src="https://fonts.googleapis.com/a.js">'
                    b"</script>"
                )
            }
        )
        self.assertEqual(hosted.site_script_count, 1)
        self.assertNotIn("fonts.googleapis.com", hosted.site_script_detail)

    def test_imported_before_keeps_page(self):
        rows = rows_of(build(), Options(), {"standalone-fr"})
        self.assertTrue(rows["standalone-fr"].include)
        self.assertTrue(rows["standalone-fr"].imported_before)

    def test_choice_order(self):
        site = build()

        def include(**kw):
            return rows_of(site, Options(**kw))["standalone-fr"].include

        self.assertTrue(include(include_unlinked_langs=True))
        self.assertTrue(include(include_page_refs=["standalone-fr"]))
        self.assertFalse(
            include(
                include_unlinked_langs=True, skip_page_refs=["standalone-fr"]
            )
        )
        self.assertFalse(
            include(
                include_page_refs=["standalone-fr"],
                skip_page_refs=["standalone-fr"],
            )
        )

    def test_choice_ignored(self):
        site = build()
        analyse(
            site,
            Options(
                include_page_refs=["about-fr", "nope"],
                skip_page_refs=["about"],
            ),
        )
        ignored = sorted(
            f.params["ref"]
            for f in site.findings
            if f.code == "choice_ignored"
        )
        self.assertEqual(ignored, ["about", "about-fr", "nope"])

    def test_apply_choices(self):
        site = build()
        kept = apply_choices(site, [PageChoice("standalone-fr", True)])
        self.assertEqual(kept.page("standalone-fr").analysis_status, "import")
        page_codes = [
            f.code for f in kept.findings if f.page_ref == "standalone-fr"
        ]
        self.assertEqual(page_codes, ["foreign_lang_page"])
        dropped = apply_choices(site, [PageChoice("standalone-fr", False)])
        self.assertIsNone(dropped.page("standalone-fr"))
        self.assertEqual(dropped.dropped_refs, ["standalone-fr"])
        skipped = [
            f for f in dropped.findings if f.code == "foreign_lang_skipped"
        ][0]
        self.assertEqual(
            (skipped.lang, skipped.url), ("fr", "/standalone-fr.php")
        )
        self.assertIsNone(apply_choices(site, []).page("standalone-fr"))

    def test_apply_choices_returns_a_copy(self):
        site = build()
        before = json.dumps(site.to_json(), sort_keys=True)
        out = apply_choices(site, [PageChoice("standalone-fr", False)])
        self.assertIsNot(out, site)
        self.assertEqual(json.dumps(site.to_json(), sort_keys=True), before)
        self.assertEqual(
            site.page("standalone-fr").analysis_status, "foreign_unlinked"
        )
        self.assertEqual(site.dropped_refs, [])
        out.pages[0].title = "changed"
        self.assertEqual(json.dumps(site.to_json(), sort_keys=True), before)

    def test_inspect_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / FILENAME
            path.write_bytes(demo_zip_bytes())
            code, out, err = run_inspect(
                ["--zip", str(path), "--include-page", "standalone-fr"]
            )
        self.assertEqual((code, err), (0, ""))
        data = json.loads(out)
        pages = {row["ref"]: row for row in data["pages"]}
        self.assertTrue(pages["standalone-fr"]["include"])
        self.assertEqual(data["site"]["source_key"], "exemplesite")
        self.assertTrue(
            any(f["code"] == "layout_detected" for f in data["findings"])
        )

    def test_site_level_finding_stays_off_the_rows(self):
        zip_bytes = demo_zip_bytes(
            sql_edit=lambda sql: sql.replace(
                "__WEBSITE_ID__, 'Equipe', ", "__WEBSITE_ID__, 'about', "
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / FILENAME
            path.write_bytes(zip_bytes)
            code, out, _err = run_inspect(["--zip", str(path)])
        self.assertEqual(code, 0)
        data = json.loads(out)
        site_level = [
            f
            for f in data["findings"]
            if f["code"] == "page_error" and f["page_ref"] == ""
        ]
        self.assertEqual(len(site_level), 1)
        self.assertIn("duplicate ref", site_level[0]["params"]["reason"])
        self.assertEqual(
            [row for row in data["pages"] if "page_error" in json.dumps(row)],
            [],
        )
        site = build()
        site.findings.append(finding("page_error", ref="x", reason="r"))
        self.assertEqual(
            [r.ref for r in analyse(site, Options())],
            [p.ref for p in site.pages],
        )

    def test_oversized_file_refused_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / FILENAME
            with open(path, "wb") as handle:
                handle.truncate(513 * 1024 * 1024)
            with mock.patch.object(
                pathlib.Path, "read_bytes", side_effect=AssertionError
            ):
                code, out, err = run_inspect(["--zip", str(path)])
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("limit", err)
        self.assertNotIn("Traceback", err)

    def test_unusable_input_exits_with_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "absent.zip"
            bad = pathlib.Path(tmp) / FILENAME
            bad.write_bytes(b"not a zip at all")
            for path in (missing, bad, pathlib.Path(tmp)):
                code, out, err = run_inspect(["--zip", str(path)])
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertNotIn("Traceback", err)

    def test_choice_ignored_is_idempotent(self):
        site = build()
        opts = Options(
            include_page_refs=["nope", "nope"], skip_page_refs=["nope"]
        )
        analyse(site, opts)
        analyse(site, opts)
        ignored = [f for f in site.findings if f.code == "choice_ignored"]
        self.assertEqual([f.params["ref"] for f in ignored], ["nope"])

    def test_special_files_refused_without_hanging(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = pathlib.Path(tmp) / "pipe.zip"
            os.mkfifo(fifo)
            paths = [fifo]
            if os.path.exists("/dev/zero"):
                link = pathlib.Path(tmp) / "zero.zip"
                link.symlink_to("/dev/zero")
                paths.append(link)
            for path in paths:
                code, out, err = run_inspect(["--zip", str(path)])
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertIn("regular file", err)

    def test_file_growing_past_the_limit_is_refused(self):
        real = os.stat
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / FILENAME
            path.write_bytes(b"x" * 200)
            small = mock.Mock(st_mode=real(path).st_mode, st_size=10)
            limits = mock.Mock(max_total=100)
            with mock.patch.object(
                cli.zipsource.os, "stat", return_value=small
            ):
                with mock.patch.object(
                    cli.zipsource.ZipLimits,
                    "from_options",
                    return_value=limits,
                ):
                    code, out, err = run_inspect(["--zip", str(path)])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("limit", err)
        self.assertEqual(len(err.strip().splitlines()), 1)


class TestAnalyse(AnalyseCases, unittest.TestCase):
    pass
