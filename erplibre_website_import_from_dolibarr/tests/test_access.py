# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from .common import DolibarrImportCase

ACTIONS = (
    "action_start",
    "action_import",
    "action_resume",
    "action_cancel",
    "action_start_over",
    "action_reimport",
    "action_open_website",
    "action_open_blog",
)


class TestAccess(DolibarrImportCase):
    def designer(self):
        return new_test_user(
            self.env,
            login="example_designer",
            groups="base.group_user,website.group_website_designer",
        )

    def test_designer_without_system_group_is_refused(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        row = run.page_ids.filtered(lambda r: r.ref == "standalone-fr")
        designer = self.designer()
        with self.assertRaises(AccessError):
            run.with_user(designer).action_import()
        with self.assertRaises(AccessError):
            row.with_user(designer).include = True
        with self.assertRaises(AccessError):
            run.with_user(designer).read(["state"])

    def test_every_action_checks_the_group(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        designer = self.designer()
        runs = self.env["dolibarr.website.import"].search([])
        for name in ACTIONS:
            with self.assertRaises(AccessError, msg=name):
                getattr(run.with_user(designer), name)()
        self.assertEqual(run.state, "to_review")
        self.assertEqual(self.env["dolibarr.website.import"].search([]), runs)
        line = run.line_ids[:1]
        with self.assertRaises(AccessError):
            line.with_user(designer).action_open()

    def test_process_checks_the_group(self):
        run = self.make_run()
        with self.assertRaises(AccessError):
            run.with_user(self.designer())._process()

    def test_langs_dir_context_needs_the_superuser(self):
        run = self.make_run()
        admin = new_test_user(
            self.env,
            login="example_admin_langs",
            groups="base.group_user,base.group_system",
        )
        context = {"dolibarr_langs_dir": "/nonexistent/langs"}
        options = run.with_user(admin).with_context(**context)
        self.assertEqual(options._engine_options().langs_dir, "")
        self.assertEqual(
            run.with_context(**context)._engine_options().langs_dir,
            "/nonexistent/langs",
        )
