# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Shared setup of the Odoo-side tests: an invented company and website."""

import base64

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from ..dolibarr_site.tests.fixtures import FILENAME, demo_zip_bytes


@tagged("post_install", "-at_install")
class DolibarrImportCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "name": "Example Co",
                "email": "info@example.org",
                "phone": "+1 555 0100",
                "street": "1 Example Street",
                "city": "Exampleville",
                "zip": "H0H 0H0",
            }
        )
        cls.website = cls.env["website"].create(
            {
                "name": "Example site",
                "domain": cls.base_url(),
                "company_id": cls.company.id,
            }
        )

    def make_run(self, zip_bytes=None, **vals):
        values = {
            "website_id": self.website.id,
            "zip_file": base64.b64encode(zip_bytes or demo_zip_bytes()),
            "zip_filename": FILENAME,
            "source_key": "exemplesite",
        }
        values.update(vals)
        Run = self.env["dolibarr.website.import"]
        if "state" in vals:
            Run = Run.with_context(dolibarr_import_state=True)
        return Run.create(values)

    def set_state(self, run, state):
        """Write state as the action methods do."""
        run.with_context(dolibarr_import_state=True).state = state

    def run_lines(self, run, code):
        return run.line_ids.filtered(lambda line: line.code == code)

    @classmethod
    def cli_import(cls, website=None, zip_bytes=None, **opts):
        """A run created and processed as the odoo-bin command does it:
        _create_from_cli, running, then one batch without a budget."""
        values = {
            "website_id": (website or cls.website).id,
            "zip_bytes": zip_bytes or demo_zip_bytes(),
            "zip_filename": FILENAME,
        }
        values.update(opts)
        run = cls.env["dolibarr.website.import"]._create_from_cli(values)
        run._check_no_running_other()
        run._set_state({"state": "running"})
        run._run_inline(None)
        return run

    def section(self, html, start='id="wrap"', end='id="footer"'):
        """The part of a served page between two markers: #wrap by
        default, which holds the imported content and nothing of the
        layout."""
        begin = html.index(start)
        return html[begin : html.index(end, begin)]
