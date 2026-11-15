# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import new_test_user

from ..dolibarr_site.messages import TEMPLATES
from ..dolibarr_site.tests.fixtures import FILENAME, demo_zip_bytes
from .common import DolibarrImportCase


class TestI18n(DolibarrImportCase):
    def load_fr(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["erplibre_website_import_from_dolibarr"],
            ["fr_CA"],
            overwrite=True,
        )

    def test_every_template_has_a_fr_ca_text(self):
        self.load_fr()
        env = self.env(context=dict(self.env.context, lang="fr_CA"))
        untranslated = [
            code
            for code, (_severity, template) in TEMPLATES.items()
            if env._(template) == template
        ]
        self.assertEqual(untranslated, [])

    def test_lines_follow_the_run_language_under_the_superuser(self):
        self.load_fr()
        user = new_test_user(
            self.env,
            login="example_fr_admin",
            groups="base.group_user,base.group_system",
            lang="fr_CA",
        )
        run = (
            self.env["dolibarr.website.import"]
            .with_user(user)
            ._create_from_cli(
                {
                    "website_id": self.website.id,
                    "zip_bytes": demo_zip_bytes(),
                    "zip_filename": FILENAME,
                    "lang": user.lang,
                }
            )
        )
        run.with_user(self.env.ref("base.user_root")).with_context(
            lang=None
        )._process()
        line = self.run_lines(run, "foreign_lang_skipped")
        self.assertEqual(
            line.message,
            "Page standalone-fr (fr, /standalone-fr.php) écartée : non choisie",
        )
