# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""What a second import of the same site keeps, updates and reports."""

from unittest import mock

from odoo.exceptions import ValidationError

from ..dolibarr_site.html2arch import blog_style_key
from ..dolibarr_site.tests.fixtures import demo_zip_bytes
from .common import DolibarrImportCase

CHANGED = ("We make examples.", "We make better examples.")
# The label of the header link to the about page.
RENAMED = ('about.php\\">About<', 'about.php\\">About the company<')
TRACKED = (
    "website.page",
    "ir.ui.view",
    "website.menu",
    "website.rewrite",
    "ir.attachment",
)


class TestReimport(DolibarrImportCase):
    def cli(self, **opts):
        edit = opts.pop("edit", None)
        drop = opts.pop("drop_pages", ())
        run = self.cli_import(
            zip_bytes=demo_zip_bytes(
                sql_edit=(lambda sql: sql.replace(*edit)) if edit else None,
                drop_pages=drop,
            ),
            **opts,
        )
        self.assertEqual(run.state, "done", run.error or "")
        return run

    def counts(self):
        domain = [("website_id", "=", self.website.id)]
        counts = {
            model: self.env[model]
            .with_context(active_test=False)
            .search_count(domain)
            for model in TRACKED
        }
        counts["blog.post"] = self.env["blog.post"].search_count(
            [("blog_id.website_id", "=", self.website.id)]
        )
        return counts

    def about(self):
        return self.env["website.page"].search(
            [("website_id", "=", self.website.id), ("url", "=", "/about")]
        )

    def test_identical_reimport_changes_nothing(self):
        self.cli()
        before = self.counts()
        second = self.cli()
        self.assertEqual(self.counts(), before)
        maps = self.env["dolibarr.website.import.map"].search(
            [("website_id", "=", self.website.id)]
        )
        self.assertEqual(maps.mapped("last_import_id"), second)
        self.assertEqual(set(maps.mapped("last_action")), {"unchanged"})
        self.assertFalse(self.run_lines(second, "stale_record"))
        self.assertFalse(self.run_lines(second, "local_edit_kept"))

    def test_changed_source_updates_same_records(self):
        self.cli()
        page = self.about()
        key = page.view_id.key
        run = self.cli(edit=CHANGED)
        self.assertEqual(self.about(), page)
        self.assertEqual(page.view_id.key, key)
        self.assertIn("We make better examples.", page.view_id.arch_db)
        self.assertEqual(
            run._writer()._map_line("page", "about").last_action, "updated"
        )
        self.assertIn("We make better examples.", self.url_open("/about").text)

    def test_local_edit_kept_then_overwritten(self):
        self.cli()
        view = self.about().view_id
        view.arch_db = view.arch_db.replace("We make examples.", "LOCAL EDIT")
        run = self.cli(edit=CHANGED)
        self.assertTrue(self.run_lines(run, "local_edit_kept"))
        self.assertIn("LOCAL EDIT", view.arch_db)
        self.assertIn("LOCAL EDIT", self.url_open("/about").text)
        again = self.cli(edit=CHANGED)
        self.assertTrue(self.run_lines(again, "local_edit_kept"))
        forced = self.cli(edit=CHANGED, overwrite_local_edits=True)
        self.assertTrue(self.run_lines(forced, "local_edit_overwritten"))
        self.assertIn("We make better examples.", view.arch_db)
        self.assertNotIn("LOCAL EDIT", view.arch_db)
        self.assertNotIn("LOCAL EDIT", self.url_open("/about").text)

    def test_unpublished_page_stays_unpublished(self):
        self.cli()
        page = self.about()
        page.is_published = False
        run = self.cli(edit=CHANGED)
        self.assertFalse(page.is_published)
        self.assertTrue(self.run_lines(run, "local_edit_kept"))
        self.assertEqual(self.url_open("/about").status_code, 404)

    def test_reimport_starts_with_options_unchecked(self):
        first = self.cli(overwrite_local_edits=True, keep_scripts=True)
        self.assertTrue(first.overwrite_local_edits)
        self.assertTrue(first.keep_scripts)
        new = self.env["dolibarr.website.import"].browse(
            first.action_reimport()["res_id"]
        )
        self.assertNotEqual(new, first)
        self.assertFalse(new.overwrite_local_edits)
        self.assertFalse(new.keep_scripts)
        self.assertEqual(new.state, "to_review")

    def test_stale_post_is_only_reported(self):
        self.cli()
        post = self.env["blog.post"].search(
            [
                ("name", "=", "Second news"),
                ("blog_id.website_id", "=", self.website.id),
            ]
        )
        url = post.website_url
        run = self.cli(drop_pages=["news-2"])
        stale = self.run_lines(run, "stale_record").filtered(
            lambda line: line.page_ref == "news-2"
        )
        self.assertEqual(len(stale), 1)
        self.assertIn("absent from source", stale.message)
        self.assertTrue(post.exists() and post.is_published)
        self.assertTrue(
            self.env["website.rewrite"].search(
                [
                    ("url_from", "=", "/news-2.php"),
                    ("website_id", "=", self.website.id),
                ]
            )
        )
        self.assertTrue(run._writer()._map_line("post", "news-2").exists())
        self.assertEqual(self.url_open(url).status_code, 200)
        response = self.url_open("/news-2.php", allow_redirects=False)
        self.assertEqual(response.status_code, 301)

    def test_moved_menu_entry_keeps_its_place(self):
        self.cli()
        about = self.env["website.menu"].search(
            [("name", "=", "About"), ("website_id", "=", self.website.id)]
        )
        about.sequence = 1
        run = self.cli(edit=RENAMED)
        self.assertEqual(about.name, "About the company")
        self.assertEqual(about.sequence, 1)
        line = run._writer()._map_line("menu", "/dolibarr-page:about")
        self.assertEqual(
            (line.res_id, line.last_action), (about.id, "updated")
        )
        self.assertFalse(self.run_lines(run, "local_edit_kept"))

    def test_copy_on_write_of_layout_keeps_one_style_view(self):
        self.cli()
        layout = self.env.ref("website.layout")
        layout.with_context(website_id=self.website.id).write(
            {"name": "Main layout, edited"}
        )
        run = self.cli()
        views = (
            self.env["ir.ui.view"]
            .with_context(active_test=False)
            .search(
                [
                    ("key", "=", blog_style_key("exemplesite")),
                    ("website_id", "=", self.website.id),
                ]
            )
        )
        self.assertEqual(len(views), 1)
        self.assertEqual(views.inherit_id.website_id, self.website)
        self.assertFalse(self.run_lines(run, "recreated"))
        post = self.env["blog.post"].search(
            [
                ("name", "=", "First news"),
                ("blog_id.website_id", "=", self.website.id),
            ]
        )
        self.assertIn(
            "/dolibarr-import/exemplesite/styles.css",
            self.url_open(post.website_url).text,
        )


class TestReimportAfterFailure(DolibarrImportCase):
    """A page whose write fails is reported once, as an error, and never
    as a record absent from the source; it stays unpublished."""

    def failing(self, ref="about"):
        """Patch of _map_upsert that fails page ref after writing it, so
        the savepoint of that page has something to undo."""
        cls = type(self.env["dolibarr.website.import"])
        original = cls._map_upsert

        def failing(self, kind, name, *args, **kwargs):
            result = original(self, kind, name, *args, **kwargs)
            if kind == "page" and name == ref:
                raise ValidationError("broken arch")
            return result

        return mock.patch.object(cls, "_map_upsert", failing)

    def assert_reported_once(self, run):
        self.assertEqual(run.state, "done", run.error or "")
        errors = self.run_lines(run, "page_error")
        self.assertEqual(errors.mapped("page_ref"), ["about"])
        self.assertIn("broken arch", errors.message)
        self.assertFalse(
            self.run_lines(run, "stale_record").filtered(
                lambda line: line.page_ref == "about"
                or "about" in (line.message or "")
            )
        )

    def page(self):
        return self.env["website.page"].search(
            [("website_id", "=", self.website.id), ("url", "=", "/about")]
        )

    def test_failed_page_is_one_error_and_stays_hidden(self):
        with self.failing():
            first = self.cli_import()
        self.assert_reported_once(first)
        self.assertFalse(self.page().is_published)
        self.assertEqual(self.url_open("/about").status_code, 404)
        self.assertEqual(self.url_open("/Equipe").status_code, 200)
        with self.failing():
            second = self.cli_import()
        self.assert_reported_once(second)
        self.assertFalse(self.page().is_published)
        self.assertEqual(self.url_open("/about").status_code, 404)
        third = self.cli_import()
        self.assertFalse(self.run_lines(third, "page_error"))
        self.assertTrue(self.page().is_published)
        self.assertEqual(self.url_open("/about").status_code, 200)

    def test_failed_rewrite_keeps_the_published_page(self):
        self.cli_import()
        with self.failing():
            run = self.cli_import(
                zip_bytes=demo_zip_bytes(
                    sql_edit=lambda sql: sql.replace(*CHANGED)
                )
            )
        self.assert_reported_once(run)
        self.assertTrue(self.page().is_published)
        self.assertIn("We make examples.", self.url_open("/about").text)
