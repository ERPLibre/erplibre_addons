# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from lxml import etree
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

from ..dolibarr_site.tests.fixtures import FILENAME, demo_zip_bytes
from .common import DolibarrImportCase


class TestWizardReview(DolibarrImportCase):
    def wizard(self, **vals):
        values = {
            "website_id": self.website.id,
            "zip_file": base64.b64encode(demo_zip_bytes()),
            "zip_filename": FILENAME,
        }
        values.update(vals)
        return self.env["dolibarr.website.import.wizard"].create(values)

    def analyse(self, **vals):
        action = self.wizard(**vals).action_analyse()
        return self.env["dolibarr.website.import"].browse(action["res_id"])

    def row(self, run, ref):
        return run.page_ids.filtered(lambda r: r.ref == ref)

    def designer(self):
        return new_test_user(
            self.env,
            login="example_designer_wizard",
            groups="base.group_user,website.group_website_designer",
        )

    def form_arch(self, model, view_type="form"):
        view = self.env[model].get_view(view_type=view_type)
        return etree.fromstring(view["arch"])

    def test_key_prefilled_and_previous_key_warning(self):
        self.assertEqual(self.wizard().source_key, "exemplesite")
        self.assertFalse(self.wizard().previous_key)
        self.make_run(source_key="otherkey", state="done")
        self.assertEqual(self.wizard().previous_key, "otherkey")

    def test_invalid_key_refused(self):
        with self.assertRaises(UserError):
            self.wizard(source_key="a{{1+1}}").action_analyse()

    def test_analyse_writes_nothing_and_rows_follow_rules(self):
        pages = self.env["website.page"].search_count(
            [("website_id", "=", self.website.id)]
        )
        posts = self.env["blog.post"].search_count([])
        run = self.analyse()
        self.assertEqual(run.state, "to_review")
        self.assertEqual(run.lang, self.env.lang or self.env.user.lang)
        self.assertEqual(
            self.env["website.page"].search_count(
                [("website_id", "=", self.website.id)]
            ),
            pages,
        )
        self.assertEqual(self.env["blog.post"].search_count([]), posts)
        foreign = self.row(run, "standalone-fr")
        self.assertFalse(foreign.include)
        foreign.include = True
        with self.assertRaises(UserError):
            self.row(run, "about-fr").include = True
        legacy = self.row(run, "legacy")
        self.assertEqual(legacy.php_plan, "remove")
        self.assertGreater(legacy.php_removed_bytes, 0)
        self.assertIn("inline scripts", self.row(run, "unsafe").script_detail)
        run.keep_scripts = True
        self.assertTrue(run.keep_scripts)

    def test_site_head_scripts_are_in_the_review(self):
        zip_bytes = demo_zip_bytes(
            extra={"containers/htmlheader.html": b"<script>var b;</script>"}
        )
        run = self.analyse(zip_file=base64.b64encode(zip_bytes))
        self.assertEqual(run.site_script_count, 1)
        self.assertIn("inline scripts: 1", run.site_script_detail)
        page = self.form_arch("dolibarr.website.import").find(
            ".//page[@name='scripts']"
        )
        names = [field.get("name") for field in page.iter("field")]
        self.assertIn("site_script_count", names)
        self.assertIn("site_script_detail", names)

    def test_empty_key_has_its_own_message(self):
        wizard = self.wizard(zip_filename="export.zip")
        wizard.source_key = False
        with self.assertRaisesRegex(UserError, "Give the source key"):
            wizard.action_analyse()

    def test_run_views_create_nothing_and_hide_open_in_draft(self):
        form = self.form_arch("dolibarr.website.import")
        listing = self.form_arch("dolibarr.website.import", "list")
        self.assertEqual(form.get("create"), "0")
        self.assertEqual(listing.get("create"), "0")
        for name in ("action_open_website", "action_open_blog"):
            button = form.find(".//button[@name='%s']" % name)
            self.assertIn("draft", button.get("invisible") or "", name)

    def test_run_lang_is_the_user_lang(self):
        run = self.analyse()
        self.assertEqual(run.lang, self.env.user.lang)

    def test_choice_flow_across_runs(self):
        first = self.analyse()
        self.row(first, "standalone-fr").include = True
        first.action_import()
        page = self.env["website.page"].search(
            [
                ("website_id", "=", self.website.id),
                ("url", "=", "/standalone-fr"),
            ]
        )
        self.assertTrue(page)
        self.assertTrue(self.run_lines(first, "foreign_lang_page"))
        second = self.env["dolibarr.website.import"].browse(
            first.action_reimport()["res_id"]
        )
        again = self.row(second, "standalone-fr")
        self.assertTrue(again.include and again.imported_before)
        again.include = False
        second.action_import()
        self.assertTrue(page.exists())
        stale = self.run_lines(second, "stale_record").filtered(
            lambda line: line.page_ref == "standalone-fr"
        )
        self.assertIn("dropped by choice", stale.message)
        third = self.analyse()
        self.assertFalse(self.row(third, "standalone-fr").include)

    def test_start_over_prefills_from_run(self):
        run = self.analyse(blog_name="News")
        action = run.action_start_over()
        wizard = (
            self.env["dolibarr.website.import.wizard"]
            .with_context(**action["context"])
            .create({})
        )
        self.assertEqual(
            (wizard.source_key, wizard.blog_name), ("exemplesite", "News")
        )
        self.assertTrue(wizard.zip_file)

    def test_start_over_from_a_done_run_gives_a_run_to_review(self):
        done = self.make_run()
        done.action_start()
        self.assertEqual(done.state, "done")
        action = done.action_start_over()
        self.assertEqual(action["res_model"], "dolibarr.website.import.wizard")
        self.assertEqual(
            action["context"]["dolibarr_import_from_run"], done.id
        )
        wizard = (
            self.env["dolibarr.website.import.wizard"]
            .with_context(**action["context"])
            .create({})
        )
        self.assertEqual(wizard.website_id, done.website_id)
        self.assertEqual(wizard.source_key, done.source_key)
        self.assertTrue(wizard.zip_file)
        new = self.env["dolibarr.website.import"].browse(
            wizard.action_analyse()["res_id"]
        )
        self.assertNotEqual(new, done)
        self.assertEqual(new.state, "to_review")
        self.assertTrue(new.page_ids)

    def test_non_system_user_refused(self):
        designer = self.designer()
        with self.assertRaises(AccessError):
            self.env["dolibarr.website.import.wizard"].with_user(
                designer
            ).create({"website_id": self.website.id, "zip_filename": FILENAME})

    def test_analyse_checks_the_group(self):
        wizard = self.wizard()
        runs = self.env["dolibarr.website.import"].search([])
        with self.assertRaises(AccessError):
            wizard.with_user(self.designer()).action_analyse()
        self.assertEqual(self.env["dolibarr.website.import"].search([]), runs)

    def test_line_open_without_record_returns_false(self):
        run = self.analyse()
        bare = self.env["dolibarr.website.import.line"].create(
            {"import_id": run.id, "code": run.line_ids[:1].code}
        )
        self.assertFalse(bare.res_model)
        self.assertFalse(bare.action_open())
        with_record = bare.copy({"res_model": "website", "res_id": 1})
        action = with_record.action_open()
        self.assertEqual(action["res_model"], "website")
        self.assertEqual(action["res_id"], 1)

    def test_site_level_line_shows_without_a_row_link(self):
        run = self.analyse()
        line = self.env["dolibarr.website.import.line"].create(
            {
                "import_id": run.id,
                "code": run.line_ids[:1].code,
                "page_ref": "",
                "message": "site level",
            }
        )
        data = line.read(["page_ref", "message", "res_model", "res_id"])[0]
        self.assertFalse(data["page_ref"])
        self.assertEqual(
            self.env["dolibarr.website.import.line"]._fields["page_ref"].type,
            "char",
        )
        self.assertFalse(line.action_open())

    def test_form_view_contract(self):
        arch = self.form_arch("dolibarr.website.import")
        state = arch.xpath("//header/field[@name='state']")[0]
        self.assertEqual(state.get("widget"), "statusbar")
        self.assertIn(state.get("readonly"), ("1", "True", "true"))
        self.assertFalse(state.get("options"))
        pages = [p.get("name") for p in arch.xpath("//notebook/page")]
        self.assertEqual(
            pages,
            [
                "review",
                "scripts",
                "summary",
                "findings",
                "records",
                "source",
            ],
        )
        zip_field = arch.xpath("//field[@name='zip_file']")[0]
        self.assertIn("draft", zip_field.get("readonly"))
        self.assertFalse(arch.xpath("//*[@attrs]"))
        self.assertTrue(
            arch.xpath("//page[@name='review']//field[@name='page_ids']")
        )
        opener = arch.xpath("//field[@name='line_ids']//button")[0]
        self.assertEqual(opener.get("invisible"), "not res_model")

    def test_menus_are_system_only(self):
        for xmlid in (
            "menu_dolibarr_website_import_wizard",
            "menu_dolibarr_website_import_runs",
        ):
            menu = self.env.ref(
                "erplibre_website_import_from_dolibarr." + xmlid
            )
            self.assertEqual(menu.groups_id, self.env.ref("base.group_system"))
            self.assertEqual(
                menu.parent_id,
                self.env.ref("website.menu_website_global_configuration"),
            )
