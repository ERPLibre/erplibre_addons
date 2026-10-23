# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import struct
import types
import zipfile
from unittest import mock

from lxml import etree
from odoo.exceptions import AccessError, ValidationError

from ..dolibarr_site import html2arch, pipeline, zipsource
from ..dolibarr_site.model import Media, MenuItem, Options, PageError
from ..dolibarr_site.tests.fixtures import FILENAME, demo_zip_bytes, png_bytes
from ..dolibarr_site.tests.test_html2arch import RenderCases
from ..models import dolibarr_website_import_writer as writer_module
from ..models.dolibarr_website_import_writer import (
    BudgetExhausted,
    WriterResolver,
)
from .common import DolibarrImportCase

IMAGES = "medias/image/websitekey/"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32
SVG_NS = b'xmlns="http://www.w3.org/2000/svg"'


def page_row(rowid, ref, title="Row", content="<p>row</p>"):
    """One more llx_website_page INSERT for the demo dump."""
    return (
        "INSERT INTO llx_website_page(rowid, fk_page, fk_website, pageurl,"
        " aliasalt, title, description, lang, image, keywords, status,"
        " date_creation, tms, import_key, grabbed_from, type_container,"
        " htmlheader, content, author_alias, allowed_in_frames)"
        " VALUES(%d__+MAX_llx_website_page__, null, __WEBSITE_ID__, '%s',"
        " '', '%s', '', '', '', '', '1', '2025-01-13 10:00:00',"
        " '2025-01-13 10:00:00', null, '', 'page', '', '%s', '', 0);\n"
        % (rowid, ref, title, content)
    )


EQUIPE_COPY = page_row(17, "equipe", "Lower team", "<p>lower</p>")
# Style text with characters that an extra parse and serialise would
# rewrite: the stored arch must keep them byte for byte.
STYLED = page_row(
    18,
    "styled",
    "Styled",
    '<style>.a > p::after { content: "a&amp;b" }</style>'
    "<p>a &amp; b &lt;c&gt;</p>",
)
SITE_JS = (
    b"<?php // BEGIN PHP\n$websitekey = basename(__DIR__);\n// END PHP ?>\n"
    b"console.log(1);\n"
)
OTHER_CSS = (
    b"<?php // BEGIN PHP\n$websitekey = basename(__DIR__);\n// END PHP ?>\n"
    b".other { color: blue; }\n"
)


def build(**kw):
    data = kw.pop("data", None) or demo_zip_bytes(**kw)
    opts = Options(filename=FILENAME)
    source = zipsource.open_zip(data, opts)
    return pipeline.build_from_zip(data, opts, source=source), source


def corrupt_member(data, name):
    """Zip bytes where the stored member name fails its CRC check."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        info = zf.getinfo(name)
    raw = bytearray(data)
    name_len, extra_len = struct.unpack_from(
        "<HH", raw, info.header_offset + 26
    )
    start = info.header_offset + 30 + name_len + extra_len
    raw[start + 20] ^= 0xFF
    return bytes(raw)


def stored_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestWriterPasses(DolibarrImportCase):
    def _attachment(self, relpath):
        return self.env["ir.attachment"].search(
            [
                ("url", "=", "/medias/" + relpath),
                ("website_id", "=", self.website.id),
            ]
        )

    def test_map_upsert_policy(self):
        run = self.make_run()._writer()

        def vals(url_to):
            return {
                "name": "Dolibarr exemplesite: /x.php",
                "url_from": "/x.php",
                "url_to": url_to,
                "redirect_type": "301",
                "website_id": self.website.id,
            }

        def digest(url_to):
            return run._hash(
                {
                    "url_from": "/x.php",
                    "url_to": url_to,
                    "redirect_type": "301",
                }
            )

        def upsert(writer, url_to):
            return writer._map_upsert(
                "redirect",
                "/x.php",
                "website.rewrite",
                vals(url_to),
                digest(url_to),
            )

        rec, action = upsert(run, "/x")
        self.assertEqual(action, "created")
        self.assertEqual(upsert(run, "/x")[1], "created")
        again = self.make_run()._writer()
        self.assertEqual(upsert(again, "/x")[1], "unchanged")
        self.assertEqual(upsert(again, "/y")[1], "updated")
        self.assertEqual(rec.url_to, "/y")
        rec.url_to = "/local"
        self.assertEqual(upsert(again, "/z")[1], "kept_local")
        self.assertEqual(rec.url_to, "/local")
        self.assertTrue(self.run_lines(again, "local_edit_kept"))
        other = self.make_run(overwrite_local_edits=True)._writer()
        self.assertEqual(upsert(other, "/z")[1], "updated")
        self.assertEqual(rec.url_to, "/z")
        self.assertTrue(self.run_lines(other, "local_edit_overwritten"))
        rec.unlink()
        recreated, action = upsert(other, "/z")
        self.assertEqual(action, "recreated")
        self.assertTrue(recreated.exists())
        self.assertTrue(self.run_lines(other, "recreated"))
        line = other._map_line("redirect", "/x.php")
        self.assertEqual(
            (line.res_id, line.last_import_id), (recreated.id, other)
        )

    def test_map_upsert_same_hash_keeps_a_local_edit_silently(self):
        run = self.make_run()._writer()
        digest = run._hash({"url_to": "/x"})
        vals = {
            "name": "Dolibarr exemplesite: /s.php",
            "url_from": "/s.php",
            "url_to": "/x",
            "redirect_type": "301",
            "website_id": self.website.id,
        }
        rec = run._map_upsert(
            "redirect", "/s.php", "website.rewrite", vals, digest
        )[0]
        rec.url_to = "/local"
        later = self.make_run(overwrite_local_edits=True)._writer()
        self.assertEqual(
            later._map_upsert(
                "redirect", "/s.php", "website.rewrite", vals, digest
            )[1],
            "unchanged",
        )
        self.assertEqual(rec.url_to, "/local")
        self.assertFalse(later.line_ids)

    def test_writer_context_and_access(self):
        run = self.make_run()._writer()
        context = run.env.context
        self.assertEqual(context["website_id"], self.website.id)
        self.assertEqual(context["allowed_company_ids"], [self.company.id])
        for key in (
            "dolibarr_website_import",
            "mail_create_nolog",
            "mail_create_nosubscribe",
            "tracking_disable",
        ):
            self.assertTrue(context[key], key)
        employee = self.env["res.users"].create(
            {
                "name": "Writer employee",
                "login": "writer_employee",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            self.make_run().with_user(employee)._writer()

    def test_blog_is_created_once_and_never_renamed(self):
        run = self.make_run(blog_name="News")._writer()
        blog = run._ensure_blog()
        self.assertEqual((blog.name, blog.website_id), ("News", self.website))
        later = self.make_run(blog_name="Other name")._writer()
        self.assertEqual(later._ensure_blog(), blog)
        self.assertEqual(blog.name, "News")
        self.assertFalse(blog.message_follower_ids)

    def test_media(self):
        site, source = build(extra={IMAGES + "page.html": b"<p/>"})
        run = self.make_run()._writer()
        found = run._write_media(site, source)
        logo = found["image/exemplesite/logo.png"]
        self.assertEqual(logo, "/medias/image/exemplesite/logo.png")
        att = self._attachment("image/exemplesite/logo.png")
        self.assertEqual(
            (att.mimetype, att.public, att.res_model, att.res_id, att.name),
            ("image/png", True, "ir.ui.view", 0, "logo.png"),
        )
        self.assertEqual(att.raw, png_bytes())
        self.assertEqual(
            self._attachment("image/exemplesite/cover.webp").mimetype,
            "image/webp",
        )
        svg = self._attachment("image/exemplesite/icon.svg")
        self.assertEqual(svg.mimetype, "image/svg+xml")
        self.assertNotIn(b"onload", svg.raw)
        self.assertTrue(self.run_lines(run, "svg_sanitised"))
        self.assertTrue(self.run_lines(run, "media_skipped_type"))
        self.assertNotIn("image/exemplesite/page.html", found)
        self.assertFalse(run.line_ids.filtered("page_ref"))
        count = self.env["ir.attachment"].search_count(
            [("website_id", "=", self.website.id)]
        )
        again = self.make_run()._writer()
        self.assertEqual(again._write_media(site, source), found)
        self.assertEqual(
            self.env["ir.attachment"].search_count(
                [("website_id", "=", self.website.id)]
            ),
            count,
        )
        self.assertEqual(
            again._map_line("media", "image/exemplesite/logo.png").last_action,
            "unchanged",
        )

    def test_media_url_conflict(self):
        self.env["ir.attachment"].create(
            {
                "name": "logo.png",
                "datas": base64.b64encode(png_bytes()),
                "url": "/medias/image/exemplesite/logo.png",
                "website_id": self.website.id,
                "public": True,
            }
        )
        site, source = build()
        run = self.make_run()._writer()
        url = run._write_media(site, source)["image/exemplesite/logo.png"]
        self.assertTrue(url.startswith("/web/content/"))
        self.assertTrue(self.run_lines(run, "media_url_conflict"))
        again = self.make_run()._writer()
        self.assertEqual(
            again._write_media(site, source)["image/exemplesite/logo.png"], url
        )
        self.assertFalse(self.run_lines(again, "local_edit_kept"))

    def test_local_edit_survives_a_later_url_conflict(self):
        site, source = build()
        relpath = "image/exemplesite/icon.svg"
        self.make_run()._writer()._write_media(site, source)
        icon = self._attachment(relpath)
        icon.name = "renamed.svg"
        self.env["ir.attachment"].create(
            {
                "name": "other.svg",
                "raw": b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                "url": "/medias/" + relpath,
                "website_id": False,
                "public": True,
            }
        )
        for _round in range(2):
            run = self.make_run()._writer()
            run._write_media(site, source)
            line = run._map_line("media", relpath)
            self.assertEqual(line.last_action, "kept_local")
            self.assertTrue(self.run_lines(run, "local_edit_kept"))
            self.assertFalse(self.run_lines(run, "media_url_conflict"))
            self.assertEqual(
                (icon.name, icon.url), ("renamed.svg", "/medias/" + relpath)
            )

    def test_map_line_to_a_foreign_record_is_not_trusted(self):
        site, source = build()
        relpath = "image/exemplesite/logo.png"
        partner = self.env["res.partner"].create({"name": "Private"})
        private = self.env["ir.attachment"].create(
            {
                "name": "private.txt",
                "raw": b"private",
                "res_model": "res.partner",
                "res_id": partner.id,
            }
        )
        run = self.make_run()._writer()
        run._map_create("media", relpath, private, "stale", "created")
        found = run._write_media(site, source)
        self.assertEqual(
            (private.name, private.raw, private.public, private.url),
            ("private.txt", b"private", False, False),
        )
        line = run._map_line("media", relpath)
        self.assertNotEqual(line.res_id, private.id)
        self.assertEqual(found[relpath], "/medias/" + relpath)
        rewrite = self.env["website.rewrite"].create(
            {
                "name": "Foreign",
                "url_from": "/f.php",
                "url_to": "/f",
                "redirect_type": "301",
            }
        )
        self.env["dolibarr.website.import.map"].create(
            {
                "website_id": self.website.id,
                "source_key": run.source_key,
                "kind": "page",
                "ref": "about",
                "res_model": rewrite._name,
                "res_id": rewrite.id,
            }
        )
        records = run._ensure_page_records(site, run._ensure_blog())
        self.assertEqual(records["about"]._name, "website.page")
        self.assertTrue(rewrite.exists())

    def test_media_url_of_a_page_is_not_taken_over(self):
        self.env["website.page"].create(
            {
                "name": "Page at a media path",
                "type": "qweb",
                "arch": "<t t-call='website.layout'/>",
                "url": "/medias/image/exemplesite/LOGO.png",
                "website_id": self.website.id,
            }
        )
        site, source = build()
        run = self.make_run()._writer()
        url = run._write_media(site, source)["image/exemplesite/logo.png"]
        self.assertTrue(url.startswith("/web/content/"))
        self.assertTrue(self.run_lines(run, "media_url_conflict"))

    def test_media_type_comes_from_the_content(self):
        hostile = {
            IMAGES + "html.png": b"<html><script>alert(1)</script></html>",
            IMAGES
            + "svg.jpg": b"<svg "
            + SVG_NS
            + b"><script>x</script></svg>",
            IMAGES
            + "page.svg": b"<html><body><script>x</script></body></html>",
            IMAGES
            + "xhtml.svg": (
                b'<html xmlns="http://www.w3.org/1999/xhtml">'
                b"<script>x</script></html>"
            ),
            IMAGES + "markup.css": b"<!DOCTYPE html><script>x</script>",
            IMAGES + "text.woff": b"just text, not a font",
            IMAGES + "empty.gif": b"",
        }
        site, source = build(
            extra=dict(hostile, **{IMAGES + "photo.png": JPEG})
        )
        run = self.make_run()._writer()
        found = run._write_media(site, source)
        skipped = set(
            self.run_lines(run, "media_skipped_type").mapped("message")
        )
        for name in hostile:
            relpath = "image/exemplesite/" + name[len(IMAGES) :]
            self.assertNotIn(relpath, found)
            self.assertFalse(self._attachment(relpath), relpath)
            self.assertTrue(
                any(relpath in message for message in skipped), relpath
            )
        self.assertEqual(
            self._attachment("image/exemplesite/photo.png").mimetype,
            "image/jpeg",
        )

    def test_svg_is_always_sanitised(self):
        svg = (
            b"<svg " + SVG_NS + b' xmlns:x="http://www.w3.org/1999/xlink">'
            b"<script>alert(1)</script>"
            b"<foreignObject><div>x</div></foreignObject>"
            b'<a x:href="javascript:alert(1)"><rect onclick="x()"/></a></svg>'
        )
        entity = (
            b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY e "x">]>'
            b"<svg " + SVG_NS + b">&e;</svg>"
        )
        site, source = build(
            extra={IMAGES + "evil.svg": svg, IMAGES + "entity.svg": entity}
        )
        run = self.make_run(keep_scripts=True)._writer()
        found = run._write_media(site, source)
        stored = self._attachment("image/exemplesite/evil.svg").raw
        for needle in (b"script", b"foreignObject", b"javascript", b"onclick"):
            self.assertNotIn(needle, stored)
        self.assertNotIn("image/exemplesite/entity.svg", found)
        self.assertFalse(self._attachment("image/exemplesite/entity.svg"))
        self.assertTrue(
            self.run_lines(run, "media_skipped_type").filtered(
                lambda line: "entity.svg" in line.message
            )
        )

    def test_js_media_only_with_keep_scripts(self):
        extra = {"medias/js/websitekey/app.js": b"console.log(1);\n"}
        site, source = build(extra=extra)
        run = self.make_run()._writer()
        self.assertNotIn(
            "js/exemplesite/app.js", run._write_media(site, source)
        )
        self.assertFalse(self._attachment("js/exemplesite/app.js"))
        self.assertEqual(len(self.run_lines(run, "script_removed")), 1)
        self.assertFalse(self.run_lines(run, "media_skipped_type"))
        kept = self.make_run(keep_scripts=True)._writer()
        self.assertEqual(
            kept._write_media(site, source)["js/exemplesite/app.js"],
            "/medias/js/exemplesite/app.js",
        )
        self.assertEqual(
            self._attachment("js/exemplesite/app.js").mimetype,
            "application/javascript",
        )
        self.assertTrue(self.run_lines(kept, "script_kept"))

    def test_unreadable_media_is_skipped_alone(self):
        with zipfile.ZipFile(io.BytesIO(demo_zip_bytes())) as zf:
            files = {name: zf.read(name) for name in zf.namelist()}
        files[IMAGES + "broken.png"] = png_bytes() * 4
        data = corrupt_member(stored_zip(files), IMAGES + "broken.png")
        site, source = build(data=data)
        run = self.make_run()._writer()
        found = run._write_media(site, source)
        self.assertNotIn("image/exemplesite/broken.png", found)
        self.assertIn("image/exemplesite/logo.png", found)
        self.assertFalse(self._attachment("image/exemplesite/broken.png"))
        error = self.run_lines(run, "media_unreadable")
        self.assertEqual(error.url, "/medias/image/exemplesite/broken.png")

    def test_media_relpath_is_checked_again(self):
        site, source = build()
        logo = next(m for m in site.media if m.relpath.endswith("logo.png"))
        for relpath in (
            "/web/login",
            "web/content/1",
            "image/exemplesite/../../website/info",
            "image/otherkey/logo.png",
            'image/exemplesite/a"b.png',
        ):
            site.media.append(Media(relpath=relpath, zip_name=logo.zip_name))
        run = self.make_run()._writer()
        found = run._write_media(site, source)
        self.assertEqual(len(self.run_lines(run, "media_name_refused")), 5)
        self.assertTrue(
            all(url.startswith("/medias/image/") for url in found.values())
        )
        self.assertFalse(
            self.env["ir.attachment"].search(
                [
                    ("website_id", "=", self.website.id),
                    "|",
                    ("url", "=like", "/web%"),
                    ("url", "like", ".."),
                ]
            )
        )

    def test_budget_stops_between_media(self):
        site, source = build()
        run = self.make_run()._writer()
        # A spent budget still lets each pass write one record, so every
        # batch makes progress.
        stopped = False
        try:
            run._write_media(site, source, deadline=0.0)
        except BudgetExhausted:
            stopped = True
        self.assertTrue(stopped)
        first = self.env["ir.attachment"].search(
            [
                ("url", "=like", "/medias/%"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertEqual(len(first), 1)
        line = run._map_line("media", first.url[len("/medias/") :])
        self.assertEqual(line.res_id, first.id)
        line.unlink()
        first.unlink()
        clock = iter([1.0, 5.0])
        fake_time = mock.Mock(monotonic=lambda: next(clock))
        # A plain try keeps the writes: assertRaises rolls back to a
        # savepoint, and this test reads what the stop left behind.
        stopped = False
        with mock.patch.object(writer_module, "time", fake_time):
            try:
                run._write_media(site, source, deadline=2.0)
            except BudgetExhausted:
                stopped = True
        self.assertTrue(stopped)
        written = self.env["ir.attachment"].search(
            [
                ("url", "=like", "/medias/%"),
                ("website_id", "=", self.website.id),
            ]
        )
        self.assertEqual(len(written), 1)
        maps = self.env["dolibarr.website.import.map"].search(
            [("kind", "=", "media"), ("website_id", "=", self.website.id)]
        )
        self.assertEqual(set(maps.mapped("res_id")), set(written.ids))

    def test_max_media_caps_the_run(self):
        site, source = build()
        run = self.make_run(max_media=1)._writer()
        self.assertEqual(len(run._write_media(site, source)), 1)
        self.assertTrue(self.run_lines(run, "media_capped"))

    def test_shells_and_route_conflict(self):
        site, _source = build()
        run = self.make_run()._writer()
        records = run._ensure_page_records(site, run._ensure_blog())
        self.assertEqual(records["about"].url, "/about")
        self.assertEqual(records["Equipe"].url, "/Equipe")
        self.assertEqual(records["blog"].url, "/blog-page")
        self.assertEqual(self.run_lines(run, "url_conflict").page_ref, "blog")
        self.assertEqual(records["news-1"]._name, "blog.post")
        self.assertFalse(records["news-1"].is_published)
        self.assertEqual(records["news-1"].author_id, self.company.partner_id)
        self.assertNotIn("standalone-fr", records)
        self.assertNotIn("about-fr", records)
        for ref in ("header", "footer", "cta", "_lib", "config"):
            self.assertNotIn(ref, records)
        about = records["about"]
        self.assertEqual(about.website_id, self.website)
        self.assertTrue(about.key.startswith("dolibarr_import.k"))
        self.assertEqual(
            self.make_run()
            ._writer()
            ._ensure_page_records(site, run._ensure_blog()),
            records,
        )

    def test_unusable_containers_get_no_record(self):
        site, _source = build()
        site.containers["ghost"] = "content"
        site.containers["htmlheader.html"] = "content"
        run = self.make_run()._writer()
        records = run._ensure_page_records(site, run._ensure_blog())
        for ref in ("ghost", "htmlheader.html", "header", "cta"):
            self.assertNotIn(ref, records)
        maps = self.env["dolibarr.website.import.map"].search(
            [("website_id", "=", self.website.id), ("kind", "=", "page")]
        )
        self.assertEqual(
            set(maps.mapped("ref")),
            {
                ref
                for ref, rec in records.items()
                if rec._name == "website.page"
            },
        )

    def test_route_and_existing_page_urls_are_moved_aside(self):
        run = self.make_run()._writer()
        for ref in ("web", "blog", "contactus", "odoo"):
            self.assertEqual(
                run._target_url(ref), ("/%s-page" % ref, "/" + ref)
            )
        self.assertEqual(run._target_url("about"), ("/about", None))
        self.env["website.page"].create(
            {
                "name": "Legal",
                "type": "qweb",
                "arch": "<t t-call='website.layout'/>",
                "url": "/Legal",
                "website_id": self.website.id,
            }
        )
        self.assertEqual(run._target_url("legal"), ("/legal-page", "/legal"))
        self.env["website.page"].create(
            {
                "name": "Web page",
                "type": "qweb",
                "arch": "<t t-call='website.layout'/>",
                "url": "/web-page",
                "website_id": self.website.id,
            }
        )
        self.assertEqual(run._target_url("web"), ("/web-page-1", "/web"))
        self.env["ir.attachment"].create(
            {
                "name": "promo.png",
                "datas": base64.b64encode(png_bytes()),
                "url": "/promo",
                "website_id": self.website.id,
                "public": True,
            }
        )
        self.assertEqual(run._target_url("promo"), ("/promo-page", "/promo"))

    def test_case_colliding_refs_get_distinct_urls(self):
        site, _source = build(sql_edit=lambda sql: sql + EQUIPE_COPY)
        run = self.make_run()._writer()
        records = run._ensure_page_records(site, run._ensure_blog())
        self.assertEqual(records["Equipe"].url, "/Equipe")
        self.assertEqual(records["equipe"].url, "/equipe-page")
        conflict = self.run_lines(run, "url_conflict").filtered(
            lambda line: line.page_ref == "equipe"
        )
        self.assertTrue(conflict)

    def test_page_ref_equal_to_a_route(self):
        rows = page_row(18, "web") + page_row(19, "contactus")
        site, _source = build(sql_edit=lambda sql: sql + rows)
        run = self.make_run()._writer()
        records = run._ensure_page_records(site, run._ensure_blog())
        self.assertEqual(records["web"].url, "/web-page")
        self.assertEqual(records["contactus"].url, "/contactus-page")

    def test_deleted_page_is_recreated(self):
        site, _source = build()
        run = self.make_run()._writer()
        blog = run._ensure_blog()
        about = run._ensure_page_records(site, blog)["about"]
        about_id = about.id
        about.unlink()
        again = self.make_run()._writer()
        new = again._ensure_page_records(site, blog)["about"]
        self.assertNotEqual(new.id, about_id)
        self.assertEqual(new.url, "/about")
        line = again._map_line("page", "about")
        self.assertEqual(
            (line.res_id, line.last_action), (new.id, "recreated")
        )
        self.assertTrue(self.run_lines(again, "recreated"))

    def test_company_values_come_from_the_website_company(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        run = (
            self.make_run()
            ._writer()
            .with_context(allowed_company_ids=[other.id, self.company.id])
        )
        values = run._company_values()
        self.assertEqual(values["name"], "Example Co")
        self.assertEqual(values["email"], "info@example.org")
        self.assertIn("1 Example Street", values["address"])
        self.assertTrue(values["map_url"].startswith("https://"))

    def test_resolver(self):
        site, source = build()
        run = self.make_run()._writer()
        blog = run._ensure_blog()
        media = run._write_media(site, source)
        records = run._ensure_page_records(site, blog)
        resolver = WriterResolver(records, media, blog, self.website)
        self.assertEqual(resolver.page_url("about"), "/about")
        self.assertEqual(
            resolver.page_url("news-1"), records["news-1"].website_url
        )
        self.assertIsNone(resolver.page_url("htmlheader.html"))
        self.assertIsNone(resolver.page_url("missing"))
        self.assertEqual(
            resolver.media_url("image/exemplesite/logo.png"),
            "/medias/image/exemplesite/logo.png",
        )
        self.assertIsNone(resolver.media_url("image/exemplesite/none.png"))
        self.assertEqual(resolver.blog_id(), blog.id)
        self.assertEqual(resolver.website_id(), self.website.id)


class TestWriterSite(DolibarrImportCase):
    def write_demo(self, run=None, choices=(), **kw):
        site, source = build(**kw)
        site = pipeline.apply_choices(site, list(choices))
        run = run or self.make_run()
        run._writer()._write_site(site, source, Options(filename=FILENAME))
        return run

    def page(self, url):
        return self.env["website.page"].search(
            [("website_id", "=", self.website.id), ("url", "=", url)]
        )

    def rendered_by(self, run, **kw):
        """Write the demo site; return (run, RenderedSite it wrote)."""
        seen = []
        render_site = pipeline.render_site

        def spy(*args):
            seen.append(render_site(*args))
            return seen[-1]

        with mock.patch.object(writer_module.pipeline, "render_site", spy):
            self.write_demo(run=run, **kw)
        return seen[0]

    def test_pages_posts_assets(self):
        blog_messages = self.env["mail.message"].search_count(
            [("model", "=", "blog.blog")]
        )
        run = self.write_demo()
        home = self.page("/home")
        self.assertIn("res_company.name", home.view_id.arch_db)
        self.assertTrue(home.view_id.key.startswith("dolibarr_import.k"))
        self.assertEqual(
            home.website_meta_description, "Welcome to the example company"
        )
        head = run._view_by_key(html2arch.head_key("exemplesite"))
        self.assertTrue(head)
        css = self.env["ir.attachment"].search(
            [("url", "=", "/dolibarr-import/exemplesite/styles.css")]
        )
        self.assertEqual(css.mimetype, "text/css")
        post = self.env["blog.post"].search([("name", "=", "First news")])
        self.assertTrue(post.is_published)
        self.assertEqual(str(post.published_date), "2025-03-04 05:06:07")
        self.assertIn("Example Co", post.content)
        self.assertIn("cover.webp", post.cover_properties)
        self.assertEqual(post.author_id, self.company.partner_id)
        self.assertEqual(
            self.env["mail.message"].search_count(
                [("model", "=", "blog.blog")]
            ),
            blog_messages,
        )
        self.assertTrue(self.run_lines(run, "footer_not_imported"))
        self.assertEqual(self.website.homepage_url, "/home")
        style = run._view_by_key(html2arch.blog_style_key("exemplesite"))
        self.assertTrue(style.inherit_id)
        arch = etree.fromstring(style.arch_db)
        self.assertEqual(
            arch.xpath("//link")[0].get("href").split("?")[0],
            "/dolibarr-import/exemplesite/styles.css",
        )

    def test_pages_are_served(self):
        self.write_demo()
        for url in ("/about", "/Equipe", "/home"):
            response = self.url_open(url)
            self.assertEqual(response.status_code, 200, url)
        self.assertIn("styles.css?v=", self.url_open("/about").text)

    def test_arches_are_stored_as_rendered(self):
        run = self.make_run()
        rendered = self.rendered_by(
            run, sql_edit=lambda sql: sql + STYLED, extra={}
        )
        self.assertIn(
            '<style>.a &gt; p::after { content: "a&amp;amp;b" }</style>',
            rendered.pages["styled"],
        )
        writer = run._writer()
        for ref, arch in rendered.pages.items():
            line = writer._map_line("page", ref)
            page = self.env["website.page"].browse(line.res_id)
            self.assertEqual(page.view_id.arch_db, arch, ref)
            RenderCases.assert_arch_is_safe(self, page.view_id.arch_db)
        head = run._view_by_key(html2arch.head_key("exemplesite"))
        self.assertEqual(head.arch_db, rendered.head_arch)
        RenderCases.assert_arch_is_safe(self, head.arch_db)
        style = run._view_by_key(html2arch.blog_style_key("exemplesite"))
        for el in etree.fromstring(style.arch_db).iter():
            for name in ("expr", "position"):
                if el.get(name):
                    self.assertIn(el.get(name), ("//head", "inside"))

    def test_site_js_only_with_keep_scripts(self):
        extra = {"containers/javascript.js.php": SITE_JS}
        url = "/dolibarr-import/exemplesite/javascript.js"
        run = self.write_demo(extra=extra)
        self.assertFalse(self.env["ir.attachment"].search([("url", "=", url)]))
        removed = self.run_lines(run, "script_removed").filtered(
            lambda line: "javascript.js" in line.message
        )
        self.assertTrue(removed)
        head = run._view_by_key(html2arch.head_key("exemplesite"))
        self.assertNotIn("javascript.js", head.arch_db)
        kept = self.write_demo(
            run=self.make_run(keep_scripts=True), extra=extra
        )
        js = self.env["ir.attachment"].search([("url", "=", url)])
        self.assertEqual(js.mimetype, "application/javascript")
        self.assertEqual(js.raw, b"console.log(1);\n")
        self.assertIn(url, head.arch_db)
        self.assertTrue(self.run_lines(kept, "script_kept"))

    def test_menus_are_appended_after_existing_entries(self):
        root = self.website.menu_id
        before = root.child_id.sorted("sequence").mapped("name")
        run = self.write_demo()
        after = root.child_id.sorted("sequence").mapped("name")
        self.assertEqual(after[: len(before)], before)
        self.assertEqual(after[len(before) :], ["About", "Team", "Blog page"])
        skipped = self.run_lines(run, "menu_skipped_existing_url")
        self.assertEqual(len(skipped), 2)
        about = root.child_id.filtered(lambda menu: menu.name == "About")
        self.assertEqual(about.page_id, self.page("/about"))
        self.write_demo()
        self.assertEqual(
            root.child_id.sorted("sequence").mapped("name"), after
        )

    def test_menu_targets_are_checked_before_writing(self):
        site, _source = build()
        site.menu = [
            MenuItem(label="<b>Bold</b> & co", target="/shop-x"),
            MenuItem(label="Relative", target="//www.example.org/x"),
            MenuItem(label="Script", target="javascript:alert(1)"),
            MenuItem(label="Outside", target="https://www.example.org/x"),
            MenuItem(
                label="Parent",
                target="dolibarr-page:bad",
                children=[MenuItem(label="Child", target="/child-x")],
            ),
        ]
        bad = types.SimpleNamespace(
            _name="blog.post", website_url="//www.example.org/p", id=0
        )
        run = self.make_run()._writer()
        run._write_menus(site, {"bad": bad})
        names = self.website.menu_id.child_id.mapped("name")
        self.assertIn("<b>Bold</b> & co", names)
        self.assertIn("Outside", names)
        self.assertIn("Child", names)
        for label in ("Relative", "Script", "Parent"):
            self.assertNotIn(label, names)
        urls = self.env["website.menu"].search(
            [("website_id", "=", self.website.id)]
        )
        for url in urls.mapped("url"):
            self.assertFalse((url or "").startswith("//"), url)

    def test_menu_cap(self):
        site, _source = build()
        site.menu = [
            MenuItem(label="Entry %d" % i, target="/entry-%d" % i)
            for i in range(writer_module.MENU_CAP + 5)
        ]
        run = self.make_run()._writer()
        run._write_menus(site, {})
        maps = self.env["dolibarr.website.import.map"].search(
            [("website_id", "=", self.website.id), ("kind", "=", "menu")]
        )
        self.assertEqual(len(maps), writer_module.MENU_CAP)
        self.assertEqual(len(self.run_lines(run, "menu_capped")), 1)

    def test_redirects(self):
        self.write_demo()
        rewrites = self.env["website.rewrite"].search(
            [("website_id", "=", self.website.id)]
        )
        pairs = {r.url_from: (r.url_to, r.redirect_type) for r in rewrites}
        self.assertEqual(pairs["/about.php"], ("/about", "301"))
        self.assertEqual(pairs["/a-propos.php"], ("/about", "301"))
        self.assertEqual(pairs["/Equipe.php"], ("/Equipe", "301"))
        self.assertEqual(pairs["/index.php"], ("/", "301"))
        self.assertEqual(pairs["/blog.php"], ("/blog-page", "301"))

    def test_rewrite_conflict(self):
        self.env["website.rewrite"].create(
            {
                "name": "Someone else",
                "url_from": "/about.php",
                "url_to": "/contactus",
                "redirect_type": "301",
                "website_id": self.website.id,
            }
        )
        run = self.write_demo()
        self.assertEqual(
            self.run_lines(run, "rewrite_conflict").url, "/about.php"
        )

    def test_stale_records_are_only_reported(self):
        self.write_demo()
        post = self.env["blog.post"].search([("name", "=", "Second news")])
        run = self.write_demo(drop_pages=["news-2"])
        stale = self.run_lines(run, "stale_record").filtered(
            lambda line: line.page_ref == "news-2"
        )
        self.assertTrue(stale)
        self.assertIn("absent from source", stale.message)
        self.assertTrue(post.exists() and post.is_published)
        self.assertTrue(
            self.env["website.rewrite"].search(
                [("url_from", "=", "/news-2.php")]
            )
        )

    def test_page_dropped_by_choice_is_reported_as_such(self):
        choice = [types.SimpleNamespace(ref="standalone-fr", include=True)]
        self.write_demo(choices=choice)
        run = self.write_demo()
        stale = self.run_lines(run, "stale_record").filtered(
            lambda line: line.page_ref == "standalone-fr"
        )
        self.assertIn("dropped by choice", stale.message)

    def test_alias_of_a_page_dropped_by_choice(self):
        def alias(sql):
            return sql.replace(
                "__WEBSITE_ID__, 'standalone-fr', '',",
                "__WEBSITE_ID__, 'standalone-fr', 'autonome',",
            )

        choice = [types.SimpleNamespace(ref="standalone-fr", include=True)]
        self.write_demo(choices=choice, sql_edit=alias)
        run = self.write_demo(sql_edit=alias)
        stale = self.run_lines(run, "stale_record").filtered(
            lambda line: "/autonome.php" in line.message
        )
        self.assertEqual(len(stale), 1)
        self.assertIn("dropped by choice", stale.message)

    def test_no_home_keeps_homepage_url(self):
        self.write_demo(
            sql_edit=lambda sql: "\n".join(
                line
                for line in sql.split("\n")
                if "fk_default_home" not in line
            )
        )
        self.assertFalse(self.website.homepage_url)
        self.assertTrue(self.page("/home"))

    def test_page_line_of_another_website_is_not_trusted(self):
        other = self.env["website"].create({"name": "Other site"})
        foreign = self.env["website.page"].create(
            {
                "name": "Foreign about",
                "type": "qweb",
                "arch": "<t t-call='website.layout'/>",
                "url": "/about",
                "website_id": other.id,
            }
        )
        arch = foreign.view_id.arch_db
        self.write_demo()
        line = self.make_run()._writer()._map_line("page", "about")
        line.res_id = foreign.id
        run = self.write_demo(run=self.make_run(overwrite_local_edits=True))
        self.assertEqual(foreign.view_id.arch_db, arch)
        self.assertEqual(foreign.name, "Foreign about")
        self.assertNotEqual(line.res_id, foreign.id)
        page = self.env["website.page"].browse(line.res_id)
        self.assertEqual(page.website_id, self.website)
        self.assertIn("About", page.view_id.arch_db)
        self.assertTrue(self.run_lines(run, "recreated"))

    def test_foreign_records_of_every_kind_are_not_trusted(self):
        other = self.env["website"].create({"name": "Other site"})
        writer = self.make_run()._writer()
        rewrite = self.env["website.rewrite"].create(
            {
                "name": "Other",
                "url_from": "/o.php",
                "url_to": "/o",
                "redirect_type": "301",
                "website_id": other.id,
            }
        )
        menu = self.env["website.menu"].create(
            {"name": "Other", "url": "/o", "website_id": other.id}
        )
        views = self.env["ir.ui.view"].create(
            [
                {
                    "name": "Other %d" % i,
                    "type": "qweb",
                    "arch": "<t t-name='x%d'/>" % i,
                    "website_id": other.id,
                }
                for i in range(2)
            ]
        )
        blog = self.env["blog.blog"].create(
            {"name": "Other", "website_id": other.id}
        )
        post = self.env["blog.post"].create({"name": "P", "blog_id": blog.id})
        for kind, record in (
            ("redirect", rewrite),
            ("menu", menu),
            ("head_view", views[0]),
            ("blog_style_view", views[1]),
            ("post", post),
        ):
            line = writer._map_create(kind, "x", record, "", "created")
            self.assertFalse(
                writer._line_record(kind, line, record._name), kind
            )
            owner = blog if kind == "post" else record
            owner.website_id = self.website
            self.assertEqual(
                writer._line_record(kind, line, record._name), record, kind
            )

    def test_edited_copy_on_write_view_is_kept(self):
        run = self.write_demo()
        key = html2arch.blog_style_key("exemplesite")
        style = run._view_by_key(key)
        layout = self.env.ref("website.layout")
        layout.with_context(website_id=self.website.id).write(
            {"name": layout.name}
        )
        self.assertFalse(style.exists())
        moved = run._view_by_key(key)
        self.assertTrue(moved)
        edited = moved.arch_db.replace("inside", "before")
        moved.with_context(no_cow=True).arch_db = edited
        extra = {"containers/styles.css.php": OTHER_CSS}
        again = self.write_demo(extra=extra)
        self.assertEqual(moved.arch_db, edited)
        self.assertTrue(
            self.run_lines(again, "local_edit_kept").filtered(
                lambda line: "blog_style" in line.message
            )
        )
        line = again._writer()._map_line("blog_style_view", "blog_style")
        self.assertEqual(
            (line.res_id, line.last_action), (moved.id, "kept_local")
        )

    def test_moved_view_is_updated_when_not_edited(self):
        run = self.write_demo()
        key = html2arch.blog_style_key("exemplesite")
        layout = self.env.ref("website.layout")
        layout.with_context(website_id=self.website.id).write(
            {"name": layout.name}
        )
        moved = run._view_by_key(key)
        again = self.write_demo(extra={"containers/styles.css.php": OTHER_CSS})
        self.assertFalse(self.run_lines(again, "local_edit_kept"))
        line = again._writer()._map_line("blog_style_view", "blog_style")
        self.assertEqual(line.res_id, moved.id)
        self.assertNotIn(
            pipeline.css_url(build()[0]).split("=")[1], moved.arch_db
        )

    def test_failing_page_is_skipped_alone(self):
        site, source = build()
        run = self.make_run()._writer()
        cls = type(run)
        original = cls._map_upsert

        def failing(self, kind, ref, *args, **kwargs):
            result = original(self, kind, ref, *args, **kwargs)
            if kind == "page" and ref == "about":
                raise ValidationError("broken arch")
            return result

        with mock.patch.object(cls, "_map_upsert", failing):
            run._write_site(site, source, Options(filename=FILENAME))
        error = self.run_lines(run, "page_error")
        self.assertEqual(error.page_ref, "about")
        self.assertIn("broken arch", error.message)
        about = self.page("/about")
        self.assertNotIn("About", about.view_id.arch_db)
        self.assertEqual(run._map_line("page", "about").content_hash, "")
        self.assertIn("Team", self.page("/Equipe").view_id.arch_db)
        self.assertTrue(run._map_line("page", "Equipe").content_hash)
        self.assertFalse(about.is_published)
        self.assertTrue(self.page("/Equipe").is_published)
        self.assertEqual(self.url_open("/about").status_code, 404)

    def failing_page(self, run, failing_ref="about"):
        """Patch of _map_upsert that fails one page after writing it."""
        cls = type(run)
        original = cls._map_upsert

        def failing(self, kind, ref, *args, **kwargs):
            result = original(self, kind, ref, *args, **kwargs)
            if kind == "page" and ref == failing_ref:
                raise ValidationError("broken arch")
            return result

        return mock.patch.object(cls, "_map_upsert", failing)

    def test_failing_page_is_not_reported_stale(self):
        self.write_demo()
        site, source = build()
        run = self.make_run()._writer()
        with self.failing_page(run):
            run._write_site(site, source, Options(filename=FILENAME))
        self.assertEqual(self.run_lines(run, "page_error").page_ref, "about")
        self.assertFalse(
            self.run_lines(run, "stale_record").filtered(
                lambda line: line.page_ref == "about"
            )
        )

    def test_failing_home_page_is_not_the_homepage(self):
        site, source = build()
        run = self.make_run()._writer()
        with self.failing_page(run, site.home_ref):
            run._write_site(site, source, Options(filename=FILENAME))
        self.assertEqual(self.run_lines(run, "page_error").page_ref, "home")
        self.assertFalse(self.website.homepage_url)
        self.assertNotEqual(self.url_open("/").status_code, 404)
        again = self.make_run()._writer()
        again._write_site(site, source, Options(filename=FILENAME))
        self.assertEqual(self.website.homepage_url, "/home")

    def test_moved_view_is_not_reported_recreated(self):
        run = self.write_demo()
        key = html2arch.blog_style_key("exemplesite")
        layout = self.env.ref("website.layout")
        layout.with_context(website_id=self.website.id).write(
            {"name": layout.name}
        )
        moved = run._view_by_key(key)
        again = self.write_demo()
        self.assertFalse(self.run_lines(again, "recreated"))
        line = again._writer()._map_line("blog_style_view", "blog_style")
        self.assertEqual(
            (line.res_id, line.last_action), (moved.id, "unchanged")
        )

    def test_page_og_image_is_a_local_path(self):
        site, source = build()
        run = self.make_run()._writer()
        blog = run._ensure_blog()
        records = run._ensure_page_records(site, blog)
        relpath = "image/exemplesite/logo.png"
        site.page("about").image_relpath = relpath
        media = {relpath: "//cdn.example.test/logo.png"}
        resolver = WriterResolver(records, media, blog, self.website)
        rendered = pipeline.render_site(
            site, resolver, run._company_values(), Options()
        )
        run._write_pages(site, rendered, records, resolver)
        self.assertFalse(records["about"].website_meta_og_img)
        media[relpath] = "/medias/" + relpath
        again = self.make_run()._writer()
        again._write_pages(site, rendered, records, resolver)
        self.assertEqual(
            records["about"].website_meta_og_img, "/medias/" + relpath
        )

    def test_budget_stops_between_pages(self):
        site, source = build()
        run = self.make_run()._writer()
        blog = run._ensure_blog()
        media = run._write_media(site, source)
        records = run._ensure_page_records(site, blog)
        resolver = WriterResolver(records, media, blog, self.website)
        rendered = pipeline.render_site(
            site, resolver, run._company_values(), Options()
        )
        clock = iter([1.0, 1.5, 5.0, 6.0, 7.0])
        fake_time = mock.Mock(monotonic=lambda: next(clock))
        stopped = False
        with mock.patch.object(writer_module, "time", fake_time):
            try:
                run._write_pages(site, rendered, records, resolver, 2.0)
            except BudgetExhausted:
                stopped = True
        self.assertTrue(stopped)
        maps = self.env["dolibarr.website.import.map"].search(
            [("website_id", "=", self.website.id), ("kind", "=", "page")]
        )
        written = maps.filtered("content_hash")
        self.assertEqual(len(written), 2)
        for line in maps:
            page = self.env["website.page"].browse(line.res_id)
            self.assertTrue(page.exists())
            self.assertEqual(
                bool(line.content_hash),
                't-call="dolibarr_import' in page.view_id.arch_db,
            )

    def test_site_level_page_error(self):
        def broken(*args, **kwargs):
            raise PageError("htmlheader.html", "site head too large")

        with mock.patch.object(pipeline.html2arch, "head_arch", broken):
            run = self.write_demo()
        error = self.run_lines(run, "page_error")
        self.assertEqual(error.page_ref, "htmlheader.html")
        self.assertFalse(error.res_id)
        head = run._view_by_key(html2arch.head_key("exemplesite"))
        self.assertIn("styles.css", head.arch_db)
        self.assertIn("res_company.name", self.page("/home").view_id.arch_db)

    def test_write_site_checks_access(self):
        site, source = build()
        run = self.make_run()._writer()
        with mock.patch.object(
            type(run),
            "_check_import_access",
            side_effect=AccessError("denied"),
        ):
            with self.assertRaises(AccessError):
                run._write_site(site, source, Options(filename=FILENAME))
