# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from ..dolibarr_site import urls
from ..dolibarr_site.messages import finding
from ..models import blog_post
from ..models import dolibarr_website_import_writer as writer_module
from .common import DolibarrImportCase

MODELS = (
    "dolibarr.website.import",
    "dolibarr.website.import.page",
    "dolibarr.website.import.line",
    "dolibarr.website.import.map",
)


class TestModels(DolibarrImportCase):
    def _blog(self, name="Example blog"):
        return self.env["blog.blog"].create(
            {"name": name, "website_id": self.website.id}
        )

    def _post_with_cover(self, cover_properties):
        return self.env["blog.post"].create(
            {
                "name": "With cover",
                "blog_id": self._blog("Covers").id,
                "cover_properties": cover_properties,
            }
        )

    def _user(self, login, xmlids):
        groups = [self.env.ref(xmlid).id for xmlid in xmlids]
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": "%s@example.org" % login,
                "groups_id": [(6, 0, groups)],
            }
        )

    def test_line_message_comes_from_template(self):
        run = self.make_run()
        line = run._add_line(
            finding(
                "foreign_lang_skipped",
                page_ref="standalone-fr",
                lang="fr",
                url="/standalone-fr.php",
                ref="standalone-fr",
            )
        )
        self.assertEqual(
            line.message,
            "Page standalone-fr (fr, /standalone-fr.php) skipped: not chosen",
        )
        self.assertEqual(
            (line.severity, line.page_ref), ("info", "standalone-fr")
        )

    def test_site_level_finding_is_not_looked_up_as_a_page(self):
        run = self.make_run()
        Page = self.env["dolibarr.website.import.page"]
        Page.create(
            {"import_id": run.id, "ref": "htmlheader", "status": "import"}
        )
        for ref in ("", "htmlheader.html", "styles.css.php"):
            with self.subTest(page_ref=ref):
                line = run._add_line(
                    finding(
                        "layout_detected",
                        page_ref=ref,
                        ref="htmlheader",
                        role="header",
                    )
                )
                self.assertEqual(line.page_ref, ref)
                self.assertEqual(line.import_id, run)
                self.assertFalse(line.res_model)
        self.assertEqual(len(run.line_ids), 3)

    def test_map_key_is_unique(self):
        Map = self.env["dolibarr.website.import.map"]
        vals = {
            "website_id": self.website.id,
            "source_key": "exemplesite",
            "kind": "page",
            "ref": "about",
            "res_model": "website.page",
            "res_id": 1,
        }
        Map.create(vals)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                Map.create(vals)

    def test_include_is_editable_only_on_reviewed_foreign_rows(self):
        run = self.make_run()
        Page = self.env["dolibarr.website.import.page"]
        foreign = Page.create(
            {
                "import_id": run.id,
                "ref": "standalone-fr",
                "status": "foreign_unlinked",
            }
        )
        normal = Page.create(
            {
                "import_id": run.id,
                "ref": "about",
                "status": "import",
                "include": True,
            }
        )
        with self.assertRaises(UserError):
            foreign.include = True
        self.set_state(run, "to_review")
        foreign.include = True
        self.assertTrue(foreign.include)
        with self.assertRaises(UserError):
            normal.include = False
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                Page.create(
                    {"import_id": run.id, "ref": "about", "status": "import"}
                )

    def test_include_write_needs_the_system_group(self):
        run = self.make_run(state="to_review")
        Page = self.env["dolibarr.website.import.page"]
        foreign = Page.create(
            {
                "import_id": run.id,
                "ref": "standalone-fr",
                "status": "foreign_unlinked",
            }
        )
        employee = self._user("t17_employee", ["base.group_user"])
        with self.assertRaises(AccessError):
            foreign.with_user(employee).include = True

    def test_publication_guard_only_under_the_context_key(self):
        blog = self._blog()
        Post = self.env["blog.post"]
        before = len(blog.message_ids)
        Post.with_context(dolibarr_website_import=True).create(
            {"name": "Quiet", "blog_id": blog.id, "is_published": True}
        )
        self.assertEqual(len(blog.message_ids), before)
        Post.create({"name": "Loud", "blog_id": blog.id, "is_published": True})
        self.assertGreater(len(blog.message_ids), before)

    def test_publication_guard_covers_write_only_under_the_key(self):
        blog = self._blog()
        Post = self.env["blog.post"]
        quiet = Post.create({"name": "Quiet write", "blog_id": blog.id})
        loud = Post.create({"name": "Loud write", "blog_id": blog.id})
        before = len(blog.message_ids)
        quiet.with_context(dolibarr_website_import=True).write(
            {"is_published": True}
        )
        self.assertTrue(quiet.is_published)
        self.assertEqual(len(blog.message_ids), before)
        loud.write({"is_published": True})
        self.assertGreater(len(blog.message_ids), before)

    def test_cover_url(self):
        post = self._post_with_cover(
            json.dumps(
                {
                    "background-image": "url('/medias/image/exemplesite/cover.webp')"
                }
            )
        )
        self.assertEqual(
            post.dolibarr_import_cover_url,
            "/medias/image/exemplesite/cover.webp",
        )

    def test_cover_url_is_always_a_site_path_or_empty(self):
        hostile = [
            "url('javascript:alert(1)')",
            'url("JaVaScRiPt:alert(1)")',
            "url(' javascript:alert(1)')",
            "url(data:text/html;base64,PHNjcmlwdD4=)",
            "url('data:image/svg+xml,<svg onload=alert(1)>')",
            "url('//evil.example/x.png')",
            "url(//evil.example/x.png)",
            "url('https://evil.example/x.png')",
            "url('http:/evil.example/x.png')",
            "url('ftp://evil.example/x.png')",
            "url('x.png')",
            "url('relative/path.png')",
            r"url('/\\evil.example/x.png')",
            r"url(\\evil.example\x.png)",
            "url('/a b.png')",
            "url('/a<b.png')",
            "url()",
            "none",
            "",
        ]
        for value in hostile:
            with self.subTest(value=value):
                post = self._post_with_cover(
                    json.dumps({"background-image": value})
                )
                self.assertEqual(post.dolibarr_import_cover_url, "")

    def test_cover_url_survives_malformed_cover_properties(self):
        for raw in (
            "not json",
            "[]",
            "null",
            '"text"',
            '{"background-image": 5}',
            "",
        ):
            with self.subTest(raw=raw):
                post = self._post_with_cover(raw)
                self.assertEqual(post.dolibarr_import_cover_url, "")

    def test_cover_url_keeps_a_local_path_among_other_layers(self):
        post = self._post_with_cover(
            json.dumps(
                {
                    "background-image": (
                        "linear-gradient(#000, #fff), url( /medias/a.webp )"
                    )
                }
            )
        )
        self.assertEqual(post.dolibarr_import_cover_url, "/medias/a.webp")

    def test_cover_url_function_name_ignores_case(self):
        post = self._post_with_cover(
            json.dumps({"background-image": "URL('/medias/b.webp')"})
        )
        self.assertEqual(post.dolibarr_import_cover_url, "/medias/b.webp")

    def test_one_local_path_rule(self):
        self.assertIs(blog_post.local_path, urls.local_path)
        self.assertIs(writer_module.local_path, urls.local_path)
        writer = self.make_run()._writer()
        for url in ("/a b", "https://x.example.org/a\tb", "//x.example.org"):
            self.assertIsNone(writer._menu_url(url), url)
        self.assertEqual(writer._menu_url("/a"), "/a")

    def test_run_name_follows_the_website_name(self):
        run = self.make_run()
        self.assertEqual(run.name, "Example site / exemplesite")
        self.website.name = "Renamed site"
        self.env.flush_all()
        run.invalidate_recordset(["name"])
        self.assertEqual(run.name, "Renamed site / exemplesite")

    def test_users_without_the_system_group_cannot_read_or_create(self):
        run = self.make_run()
        users = {
            "internal": self._user("t17_internal", ["base.group_user"]),
            "portal": self._user("t17_portal", ["base.group_portal"]),
            "public": self.env.ref("base.public_user"),
        }
        for label, user in users.items():
            for model in MODELS:
                with self.subTest(user=label, model=model):
                    Model = self.env[model].with_user(user)
                    with self.assertRaises(AccessError):
                        Model.search([])
                    with self.assertRaises(AccessError):
                        Model.create({})
            with self.subTest(user=label, what="run record"):
                with self.assertRaises(AccessError):
                    run.with_user(user).read(["name"])

    def test_system_administrator_has_full_access(self):
        admin = self._user("t17_admin", ["base.group_system"])
        run = self.make_run().with_user(admin)
        self.assertTrue(run.read(["name"]))
        run._check_import_access()
        for model in MODELS:
            self.assertTrue(
                self.env[model].with_user(admin).has_access("unlink")
            )

    def test_import_access_gate_needs_the_system_group(self):
        run = self.make_run()
        employee = self._user("t17_plain", ["base.group_user"])
        admin = self._user("t17_sys", ["base.group_system"])
        with self.assertRaises(AccessError):
            run.with_user(employee)._check_import_access()
        run.with_user(admin)._check_import_access()
        run.sudo()._check_import_access()

    def test_orm_check_access_hook_is_intact(self):
        run = self.make_run()
        employee = self._user("t17_orm", ["base.group_user"])
        admin = self._user("t17_orm_sys", ["base.group_system"])
        self.assertIsNone(run.with_user(admin)._check_access("read"))
        denied = run.with_user(employee)._check_access("read")
        self.assertEqual(len(denied), 2)
        records, error = denied
        self.assertEqual(records, run.with_user(employee))
        self.assertIsInstance(error(), AccessError)

    def test_imported_refs_come_from_last_import_run(self):
        Map = self.env["dolibarr.website.import.map"]
        older = self.make_run(state="done", import_done=True)
        last = self.make_run(state="done", import_done=True)
        base = {
            "website_id": self.website.id,
            "source_key": "exemplesite",
            "kind": "page",
            "res_model": "website.page",
        }
        Map.create(
            dict(base, ref="standalone-fr", res_id=1, last_import_id=older.id)
        )
        Map.create(dict(base, ref="about", res_id=2, last_import_id=last.id))
        current = self.make_run()
        self.assertEqual(current._last_import_run(), last)
        self.assertEqual(current._imported_refs(), {"about"})
